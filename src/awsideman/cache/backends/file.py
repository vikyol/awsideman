"""File-based cache backend implementation."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...utils.models import CacheEntry
from ...utils.security import get_secure_logger, input_validator
from ..utils import CachePathManager
from .base import BackendHealthStatus, CacheBackend, CacheBackendError

# Use secure logger instead of standard logger
logger = get_secure_logger(__name__)


class FileBackend(CacheBackend):
    """
    File-based cache backend implementation.

    Stores cache entries as JSON files in the local filesystem.
    Maintains backward compatibility with existing cache files.
    """

    def __init__(self, cache_dir: Optional[str] = None, profile: Optional[str] = None):
        """
        Initialize file backend.

        Args:
            cache_dir: Optional custom cache directory path.
                      Defaults to ~/.awsideman/cache/
            profile: AWS profile name for isolation
        """
        self.cache_dir = cache_dir
        self.profile = profile
        self.path_manager = CachePathManager(cache_dir, profile)
        self.backend_type = "file"

        # Ensure cache directory exists
        try:
            self.path_manager.ensure_cache_directory()
        except Exception as e:
            logger.error(f"Failed to create cache directory: {e}")
            raise CacheBackendError(
                f"Failed to initialize file backend: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def get(self, key: str) -> Optional[bytes]:
        """
        Retrieve raw data from file backend with input validation.

        Args:
            key: Cache key to retrieve

        Returns:
            Raw bytes data if found and not expired, None otherwise

        Raises:
            CacheBackendError: If backend operation fails
        """
        try:
            # Validate cache key
            if not input_validator.validate_cache_key(key):
                logger.security_event(
                    "invalid_cache_key",
                    {
                        "operation": "get",
                        "key": input_validator.sanitize_log_data(key),
                        "backend": "file",
                    },
                    "WARNING",
                )
                raise CacheBackendError(f"Invalid cache key format: {key}")

            cache_file = self.path_manager.get_cache_file_path(key)

            if not cache_file.exists():
                return None

            # Try to read as binary first to detect format
            with open(cache_file, "rb") as f:
                file_content = f.read()

            # Check if it's the new encrypted format
            if len(file_content) >= 4:
                try:
                    # Try to read metadata length
                    metadata_length = int.from_bytes(file_content[:4], byteorder="big")
                    if metadata_length > 0 and metadata_length < len(file_content):
                        # Try to parse metadata
                        metadata_json = file_content[4 : 4 + metadata_length]
                        metadata = json.loads(metadata_json.decode("utf-8"))

                        if metadata.get("encrypted", False):
                            # This is encrypted format
                            # Check if expired
                            if time.time() > metadata["created_at"] + metadata["ttl"]:
                                self._remove_cache_file(cache_file)
                                return None

                            # Return encrypted data
                            encrypted_data = file_content[4 + metadata_length :]
                            logger.debug(f"File backend cache hit for key: {key} (encrypted)")
                            return encrypted_data
                except (ValueError, json.JSONDecodeError, KeyError):
                    # Not the new format, fall through to old format
                    pass

            # Try old JSON format
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)

                # Validate cache data structure
                required_fields = ["data", "created_at", "ttl", "key", "operation"]
                if not all(field in cache_data for field in required_fields):
                    logger.warning(f"Corrupted cache file missing required fields: {cache_file}")
                    self._handle_corrupted_cache_file(cache_file, "missing required fields")
                    return None

                # Create CacheEntry object from loaded data
                cache_entry = CacheEntry(
                    data=cache_data["data"],
                    created_at=cache_data["created_at"],
                    ttl=cache_data["ttl"],
                    key=cache_data["key"],
                    operation=cache_data["operation"],
                )

                # Check if entry has expired
                if cache_entry.is_expired():
                    # Remove expired entry
                    self._remove_cache_file(cache_file)
                    return None

                logger.debug(f"File backend cache hit for key: {key} (plain)")

                # Return serialized data as bytes
                return json.dumps(cache_entry.data).encode("utf-8")

            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"Cannot read cache file as JSON: {cache_file} - {e}")
                self._handle_corrupted_cache_file(cache_file, f"invalid format: {e}")
                return None
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted cache file with invalid JSON: {cache_file} - {e}")
            self._handle_corrupted_cache_file(cache_file, f"invalid JSON: {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Corrupted cache file with invalid data structure: {cache_file} - {e}")
            self._handle_corrupted_cache_file(cache_file, f"invalid data structure: {e}")
            return None
        except PermissionError as e:
            logger.error(f"Permission denied reading cache file {cache_file}: {e}")
            raise CacheBackendError(
                f"Permission denied reading cache file: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )
        except OSError as e:
            logger.error(f"OS error reading cache file {cache_file}: {e}")
            raise CacheBackendError(
                f"OS error reading cache file: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )
        except Exception as e:
            logger.error(f"Unexpected error reading cache for key {key}: {e}")
            raise CacheBackendError(
                f"Unexpected error reading cache: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def set(
        self, key: str, data: bytes, ttl: Optional[int] = None, operation: str = "unknown"
    ) -> None:
        """
        Store raw data to file backend with input validation.

        Args:
            key: Cache key to store data under
            data: Raw bytes data to store (can be encrypted or plain JSON)
            ttl: Optional TTL in seconds. If None, uses default TTL of 3600.
            operation: AWS operation that generated this data

        Raises:
            CacheBackendError: If backend operation fails
        """
        try:
            # Validate cache key
            if not input_validator.validate_cache_key(key):
                logger.security_event(
                    "invalid_cache_key",
                    {
                        "operation": "set",
                        "key": input_validator.sanitize_log_data(key),
                        "backend": "file",
                    },
                    "WARNING",
                )
                raise CacheBackendError(f"Invalid cache key format: {key}")

            # Validate data
            if not isinstance(data, bytes):
                raise CacheBackendError("Data must be bytes")

            # Validate TTL
            if ttl is not None and (not isinstance(ttl, int) or ttl <= 0):
                raise CacheBackendError("TTL must be a positive integer")

            # Use provided TTL or default
            effective_ttl = ttl or 3600  # Default 1 hour

            # Ensure cache directory exists before writing
            try:
                self.path_manager.ensure_cache_directory()
            except Exception as dir_error:
                logger.error(f"Failed to ensure cache directory exists: {dir_error}")
                raise CacheBackendError(
                    f"Failed to ensure cache directory exists: {dir_error}",
                    backend_type=self.backend_type,
                    original_error=dir_error,
                )

            # Try to determine if data is encrypted or plain JSON
            is_encrypted = False
            try:
                # Try to decode as JSON first
                decoded_data = data.decode("utf-8")
                json.loads(decoded_data)  # Test if it's valid JSON
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Data is likely encrypted or binary
                is_encrypted = True

            # Write to cache file
            cache_file = self.path_manager.get_cache_file_path(key)
            temp_file = cache_file.with_suffix(".tmp")

            if is_encrypted:
                # Store encrypted data with metadata
                cache_metadata = {
                    "encrypted": True,
                    "created_at": time.time(),
                    "ttl": effective_ttl,
                    "key": key,
                    "operation": operation,
                    "data_size": len(data),
                }

                # Write metadata as JSON header followed by encrypted data
                with open(temp_file, "wb") as f:
                    # Write metadata header
                    metadata_json = json.dumps(cache_metadata).encode("utf-8")
                    metadata_length = len(metadata_json)

                    # Write: [4 bytes length][metadata JSON][encrypted data]
                    f.write(metadata_length.to_bytes(4, byteorder="big"))
                    f.write(metadata_json)
                    f.write(data)
            else:
                # Handle as plain JSON (backward compatibility)
                try:
                    deserialized_data = json.loads(data.decode("utf-8"))

                    # Create cache entry in old format
                    cache_data = {
                        "data": deserialized_data,
                        "created_at": time.time(),
                        "ttl": effective_ttl,
                        "key": key,
                        "operation": operation,
                    }

                    with open(temp_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=2, default=str)

                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.error(f"Cannot process data for cache key {key}: {e}")
                    raise CacheBackendError(
                        f"Cannot process data for storage: {e}",
                        backend_type=self.backend_type,
                        original_error=e,
                    )

            # Atomic rename
            temp_file.rename(cache_file)
            logger.debug(f"File backend cached data for key: {key} with TTL: {effective_ttl}s")

        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize data for cache key {key}: {e}")
            self._cleanup_temp_file(cache_file)
            raise CacheBackendError(
                f"Failed to serialize data for storage: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )
        except PermissionError as e:
            logger.error(f"Permission denied writing cache file {cache_file}: {e}")
            self._cleanup_temp_file(cache_file)
            raise CacheBackendError(
                f"Permission denied writing cache file: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )
        except OSError as e:
            self._cleanup_temp_file(cache_file)
            if "No space left on device" in str(e):
                logger.error(f"Disk full - cannot write cache file {cache_file}: {e}")
                raise CacheBackendError(
                    f"Disk full - cannot write cache file: {e}",
                    backend_type=self.backend_type,
                    original_error=e,
                )
            else:
                logger.error(f"OS error writing cache file {cache_file}: {e}")
                raise CacheBackendError(
                    f"OS error writing cache file: {e}",
                    backend_type=self.backend_type,
                    original_error=e,
                )
        except Exception as e:
            logger.error(f"Unexpected error writing cache for key {key}: {e}")
            # Only cleanup temp file if cache_file was defined
            try:
                if "cache_file" in locals():
                    self._cleanup_temp_file(cache_file)
            except Exception:
                pass  # Ignore cleanup errors
            raise CacheBackendError(
                f"Unexpected error writing cache: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def invalidate(self, key: Optional[str] = None) -> None:
        """
        Remove cache entries from file backend.

        Args:
            key: Cache key to invalidate. If None, invalidates all cache entries.

        Raises:
            CacheBackendError: If backend operation fails
        """
        try:
            if key is None:
                # Clear all cache entries
                deleted_count = self.path_manager.clear_all_cache_files()
                logger.info(f"File backend cleared all cache entries ({deleted_count} files)")
            else:
                # Clear specific cache entry
                if self.path_manager.delete_cache_file(key):
                    logger.debug(f"File backend invalidated cache entry for key: {key}")
                else:
                    logger.debug(f"File backend cache entry not found for key: {key}")

        except PermissionError as e:
            logger.error(f"Permission denied invalidating cache: {e}")
            raise CacheBackendError(
                f"Permission denied invalidating cache: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )
        except OSError as e:
            logger.error(f"OS error invalidating cache: {e}")
            raise CacheBackendError(
                f"OS error invalidating cache: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )
        except Exception as e:
            logger.error(f"Unexpected error invalidating cache: {e}")
            raise CacheBackendError(
                f"Unexpected error invalidating cache: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def get_stats(self) -> Dict[str, Any]:
        """
        Get file backend statistics.

        Returns:
            Dictionary containing backend statistics and metadata

        Raises:
            CacheBackendError: If backend operation fails
        """
        try:
            cache_files = self.path_manager.list_cache_files()
            total_size = self.path_manager.get_cache_size()

            # Count valid vs expired/corrupted entries
            valid_entries = 0
            expired_entries = 0
            corrupted_entries = 0

            for cache_file in cache_files:
                try:
                    # Try to read as binary first to detect format
                    with open(cache_file, "rb") as f:
                        file_content = f.read()

                    # Check if it's the new encrypted format
                    is_encrypted_format = False
                    if len(file_content) >= 4:
                        try:
                            metadata_length = int.from_bytes(file_content[:4], byteorder="big")
                            if metadata_length > 0 and metadata_length < len(file_content):
                                metadata_json = file_content[4 : 4 + metadata_length]
                                metadata = json.loads(metadata_json.decode("utf-8"))

                                if metadata.get("encrypted", False):
                                    is_encrypted_format = True
                                    # Check if expired
                                    if time.time() > metadata["created_at"] + metadata["ttl"]:
                                        expired_entries += 1
                                    else:
                                        valid_entries += 1
                        except (ValueError, json.JSONDecodeError, KeyError):
                            pass

                    if not is_encrypted_format:
                        # Try old JSON format
                        try:
                            with open(cache_file, "r", encoding="utf-8") as f:
                                cache_data = json.load(f)

                            # Validate cache data structure
                            required_fields = ["data", "created_at", "ttl", "key", "operation"]
                            if not all(field in cache_data for field in required_fields):
                                corrupted_entries += 1
                                continue

                            cache_entry = CacheEntry(
                                data=cache_data["data"],
                                created_at=cache_data["created_at"],
                                ttl=cache_data["ttl"],
                                key=cache_data["key"],
                                operation=cache_data["operation"],
                            )

                            if cache_entry.is_expired():
                                expired_entries += 1
                            else:
                                valid_entries += 1

                        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                            corrupted_entries += 1

                except Exception as e:
                    logger.warning(f"Error reading cache file {cache_file} for stats: {e}")
                    corrupted_entries += 1

            stats = {
                "backend_type": self.backend_type,
                "total_entries": len(cache_files),
                "valid_entries": valid_entries,
                "expired_entries": expired_entries,
                "corrupted_entries": corrupted_entries,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "cache_directory": str(self.path_manager.get_cache_directory()),
            }

            # Add warning if there are corrupted entries
            if corrupted_entries > 0:
                stats["warning"] = f"{corrupted_entries} corrupted cache files detected"

            return stats

        except Exception as e:
            logger.error(f"Error getting file backend stats: {e}")
            raise CacheBackendError(
                f"Error getting backend stats: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def get_recent_entries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent cache entries with metadata.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of dictionaries containing entry metadata
        """
        entries = []

        try:
            # Get cache files either from path_manager or directly from cache directory
            if self.path_manager:
                cache_files = self.path_manager.list_cache_files()
            else:
                # Fallback: list cache files directly from cache directory
                cache_dir = Path(self.cache_dir)
                if not cache_dir.exists():
                    return entries
                cache_files = list(cache_dir.glob("*.json"))

            if not cache_files:
                return entries

            # Sort by modification time (newest first)
            cache_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            for cache_file in cache_files[:limit]:
                try:
                    # Get basic file info
                    stat = cache_file.stat()
                    key = cache_file.stem  # Remove .json extension

                    # Try to read the cache entry JSON to get metadata
                    try:
                        # First try to read as binary to detect if it's encrypted
                        with open(cache_file, "rb") as f:
                            file_content = f.read()

                        # Check if it's the new encrypted format
                        if len(file_content) >= 4:
                            try:
                                # Try to read metadata length
                                metadata_length = int.from_bytes(file_content[:4], byteorder="big")
                                if metadata_length > 0 and metadata_length < len(file_content):
                                    # Try to parse metadata
                                    metadata_json = file_content[4 : 4 + metadata_length]
                                    metadata = json.loads(metadata_json.decode("utf-8"))

                                    if metadata.get("encrypted", False):
                                        # This is encrypted format - extract metadata from header
                                        created_at = metadata.get("created_at", 0)
                                        ttl = metadata.get("ttl", 0)
                                        operation = metadata.get("operation", "unknown")

                                        # Calculate age and remaining TTL
                                        current_time = time.time()
                                        age_seconds = current_time - created_at
                                        remaining_ttl = ttl - age_seconds

                                        # Format TTL information
                                        if remaining_ttl > 0:
                                            ttl_display = f"{remaining_ttl:.0f}s remaining"
                                        else:
                                            ttl_display = "Expired"

                                        # Calculate age
                                        if age_seconds < 60:
                                            age_display = f"{age_seconds:.0f}s ago"
                                        elif age_seconds < 3600:
                                            age_display = f"{age_seconds/60:.0f}m ago"
                                        else:
                                            age_display = f"{age_seconds/3600:.1f}h ago"

                                        entry = {
                                            "key": key,
                                            "operation": operation,
                                            "ttl": ttl_display,
                                            "age": age_display,
                                            "size": f"{stat.st_size} bytes",
                                            "modified": stat.st_mtime,
                                            "file_size": stat.st_size,
                                            "is_expired": remaining_ttl <= 0,
                                        }
                                        entries.append(entry)
                                        continue  # Skip to next file
                            except (ValueError, json.JSONDecodeError, KeyError, UnicodeDecodeError):
                                # Not the new encrypted format, fall through to plain text
                                pass

                        # Try to read as plain text JSON
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cache_data = json.load(f)

                        # Extract metadata from the JSON
                        created_at = cache_data.get("created_at", 0)
                        ttl = cache_data.get("ttl", 0)
                        operation = cache_data.get("operation", "unknown")

                        # Calculate age and remaining TTL
                        current_time = time.time()
                        age_seconds = current_time - created_at
                        remaining_ttl = ttl - age_seconds

                        # Format TTL information
                        if remaining_ttl > 0:
                            ttl_display = f"{remaining_ttl:.0f}s remaining"
                        else:
                            ttl_display = "Expired"

                        # Calculate age
                        if age_seconds < 60:
                            age_display = f"{age_seconds:.0f}s ago"
                        elif age_seconds < 3600:
                            age_display = f"{age_seconds/60:.0f}m ago"
                        else:
                            age_display = f"{age_seconds/3600:.1f}h ago"

                        entry = {
                            "key": key,
                            "operation": operation,
                            "ttl": ttl_display,
                            "age": age_display,
                            "size": f"{stat.st_size} bytes",
                            "modified": stat.st_mtime,
                            "file_size": stat.st_size,
                            "is_expired": remaining_ttl <= 0,
                        }
                        entries.append(entry)

                    except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as e:
                        # If we can't read the JSON, return basic file info
                        logger.debug(f"Could not read cache entry metadata from {cache_file}: {e}")
                        entry = {
                            "key": key,
                            "operation": "unknown",
                            "ttl": "Unknown",
                            "age": "Unknown",
                            "size": f"{stat.st_size} bytes",
                            "modified": stat.st_mtime,
                            "file_size": stat.st_size,
                            "is_expired": False,
                        }
                        entries.append(entry)

                except Exception as e:
                    logger.debug(f"Error reading cache entry metadata from {cache_file}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error getting recent entries from file backend: {e}")

        return entries

    def health_check(self) -> Dict[str, Any]:
        """
        Check if file backend is healthy and accessible.

        Returns:
            Dictionary with health status information
        """
        try:
            # Check if cache directory exists and is accessible
            cache_dir = self.path_manager.get_cache_directory()

            # Test directory access
            if not cache_dir.exists():
                try:
                    self.path_manager.ensure_cache_directory()
                except Exception as e:
                    logger.error(
                        f"File backend health check failed - cannot create cache directory: {e}"
                    )
                    return {
                        "healthy": False,
                        "backend_type": self.backend_type,
                        "message": f"Cannot create cache directory: {e}",
                        "error": str(e),
                    }

            # Test write access by creating a temporary file
            test_file = cache_dir / ".health_check_test"
            try:
                test_file.write_text("health_check")
                test_file.unlink()
                logger.debug("File backend health check passed")
                return {
                    "healthy": True,
                    "backend_type": self.backend_type,
                    "message": "File backend is healthy and accessible",
                }
            except Exception as e:
                logger.error(
                    f"File backend health check failed - cannot write to cache directory: {e}"
                )
                return {
                    "healthy": False,
                    "backend_type": self.backend_type,
                    "message": f"Cannot write to cache directory: {e}",
                    "error": str(e),
                }

        except Exception as e:
            logger.error(f"File backend health check failed with unexpected error: {e}")
            return {
                "healthy": False,
                "backend_type": self.backend_type,
                "message": f"Unexpected error during health check: {e}",
                "error": str(e),
            }

    def get_detailed_health_status(self) -> BackendHealthStatus:
        """
        Get detailed health status of the file backend.

        Returns:
            BackendHealthStatus object with detailed information
        """
        start_time = time.time()

        try:
            # Check if cache directory exists and is accessible
            cache_dir = self.path_manager.get_cache_directory()

            # Test directory access
            if not cache_dir.exists():
                try:
                    self.path_manager.ensure_cache_directory()
                except Exception as e:
                    response_time = (time.time() - start_time) * 1000
                    return BackendHealthStatus(
                        is_healthy=False,
                        backend_type=self.backend_type,
                        message=f"Cannot create cache directory: {e}",
                        response_time_ms=response_time,
                        error=e,
                    )

            # Test write access by creating a temporary file
            test_file = cache_dir / ".health_check_test"
            try:
                test_file.write_text("health_check")
                test_file.unlink()

                response_time = (time.time() - start_time) * 1000
                return BackendHealthStatus(
                    is_healthy=True,
                    backend_type=self.backend_type,
                    message="File backend is healthy and accessible",
                    response_time_ms=response_time,
                )
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                return BackendHealthStatus(
                    is_healthy=False,
                    backend_type=self.backend_type,
                    message=f"Cannot write to cache directory: {e}",
                    response_time_ms=response_time,
                    error=e,
                )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return BackendHealthStatus(
                is_healthy=False,
                backend_type=self.backend_type,
                message=f"Unexpected error during health check: {e}",
                response_time_ms=response_time,
                error=e,
            )

    def _remove_cache_file(self, cache_file: Path) -> None:
        """
        Remove a cache file safely.

        Args:
            cache_file: Path to cache file to remove
        """
        try:
            if cache_file.exists():
                cache_file.unlink()
                logger.debug(f"Removed expired cache file: {cache_file}")
        except PermissionError as e:
            logger.error(f"Permission denied removing cache file {cache_file}: {e}")
        except OSError as e:
            logger.error(f"OS error removing cache file {cache_file}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error removing cache file {cache_file}: {e}")

    def _handle_corrupted_cache_file(self, cache_file: Path, reason: str) -> None:
        """
        Handle a corrupted cache file by removing it and logging the issue.

        Args:
            cache_file: Path to the corrupted cache file
            reason: Reason why the file is considered corrupted
        """
        try:
            if cache_file.exists():
                cache_file.unlink()
                logger.info(f"Removed corrupted cache file {cache_file}: {reason}")
        except Exception as e:
            logger.error(f"Failed to remove corrupted cache file {cache_file}: {e}")

    def _cleanup_temp_file(self, cache_file: Optional[Path]) -> None:
        """
        Clean up temporary file if it exists.

        Args:
            cache_file: Path to the cache file (temp file will have .tmp suffix)
        """
        if cache_file is None:
            return

        temp_file = cache_file.with_suffix(".tmp")
        try:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")
