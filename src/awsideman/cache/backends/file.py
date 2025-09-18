"""File-based cache backend implementation."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...encryption.aes import AESEncryption
from ...encryption.key_manager import KeyManager
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

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        profile: Optional[str] = None,
        encryption_enabled: bool = True,
    ):
        """
        Initialize file backend.

        Args:
            cache_dir: Optional custom cache directory path.
                      Defaults to ~/.awsideman/cache/
            profile: AWS profile name for isolation
            encryption_enabled: Whether to enable encryption for stored data
        """
        self.cache_dir = cache_dir
        self.profile = profile
        self.path_manager = CachePathManager(cache_dir, profile)
        self.backend_type = "file"
        self.encryption_enabled = encryption_enabled

        # Initialize encryption system if enabled
        self.encryption_provider = None
        if self.encryption_enabled:
            try:
                key_manager = KeyManager()
                self.encryption_provider = AESEncryption(key_manager)
                logger.debug("File backend encryption initialized successfully")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize encryption, falling back to unencrypted storage: {e}"
                )
                self.encryption_enabled = False

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

                            # Decrypt the data if encryption is enabled
                            encrypted_data = file_content[4 + metadata_length :]

                            if self.encryption_enabled and self.encryption_provider:
                                try:
                                    # Decrypt the data
                                    decrypted_data = self.encryption_provider.decrypt(
                                        encrypted_data
                                    )

                                    # Re-serialize as pickle to match the expected format
                                    import pickle

                                    pickled_data = pickle.dumps(decrypted_data)

                                    logger.debug(
                                        f"File backend cache hit for key: {key} (encrypted and decrypted)"
                                    )
                                    return pickled_data

                                except Exception as e:
                                    logger.error(f"Failed to decrypt data for key {key}: {e}")
                                    # Remove corrupted encrypted file
                                    self._remove_cache_file(cache_file)
                                    return None
                            else:
                                # Encryption is disabled, return raw data (shouldn't happen with new format)
                                logger.warning(
                                    f"Found encrypted data but encryption is disabled for key: {key}"
                                )
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

            # data is guaranteed to be bytes by type annotation

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

            # Write to cache file
            cache_file = self.path_manager.get_cache_file_path(key)
            temp_file = cache_file.with_suffix(".tmp")

            if self.encryption_enabled and self.encryption_provider:
                # Encrypt the data before storing
                try:
                    # First, deserialize the pickled data to get the original data structure
                    import pickle

                    entry_data = pickle.loads(data)

                    # Encrypt the data using the encryption provider
                    encrypted_data = self.encryption_provider.encrypt(entry_data)

                    # Store encrypted data with metadata
                    cache_metadata = {
                        "encrypted": True,
                        "created_at": time.time(),
                        "ttl": effective_ttl,
                        "key": key,
                        "operation": operation,
                        "data_size": len(encrypted_data),
                        "encryption_type": self.encryption_provider.get_encryption_type(),
                    }

                    # Write metadata as JSON header followed by encrypted data
                    with open(temp_file, "wb") as f:
                        # Write metadata header
                        metadata_json = json.dumps(cache_metadata).encode("utf-8")
                        metadata_length = len(metadata_json)

                        # Write: [4 bytes length][metadata JSON][encrypted data]
                        f.write(metadata_length.to_bytes(4, byteorder="big"))
                        f.write(metadata_json)
                        f.write(encrypted_data)

                    logger.debug(f"Stored encrypted cache entry for key: {key}")

                except Exception as e:
                    logger.error(f"Failed to encrypt data for key {key}: {e}")
                    # Fall back to unencrypted storage
                    self._store_unencrypted_data(temp_file, data, key, operation, effective_ttl)
            else:
                # Store unencrypted data (backward compatibility)
                self._store_unencrypted_data(temp_file, data, key, operation, effective_ttl)

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

    def _store_unencrypted_data(
        self, temp_file: Path, data: bytes, key: str, operation: str, ttl: int
    ) -> None:
        """
        Store unencrypted data in the old JSON format for backward compatibility.

        Args:
            temp_file: Temporary file path to write to
            data: Raw bytes data to store
            key: Cache key
            operation: Operation name
            ttl: TTL in seconds
        """
        try:
            # Try to decode as JSON first (for backward compatibility)
            decoded_data = data.decode("utf-8")
            deserialized_data = json.loads(decoded_data)

            # Create cache entry in old format
            cache_data = {
                "data": deserialized_data,
                "created_at": time.time(),
                "ttl": ttl,
                "key": key,
                "operation": operation,
            }

            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, default=str)

        except (json.JSONDecodeError, UnicodeDecodeError):
            # Data is not JSON, store as binary with metadata (pickled data)
            cache_metadata = {
                "encrypted": False,
                "created_at": time.time(),
                "ttl": ttl,
                "key": key,
                "operation": operation,
                "data_size": len(data),
            }

            # Write metadata as JSON header followed by raw data
            with open(temp_file, "wb") as f:
                # Write metadata header
                metadata_json = json.dumps(cache_metadata).encode("utf-8")
                metadata_length = len(metadata_json)

                # Write: [4 bytes length][metadata JSON][raw data]
                f.write(metadata_length.to_bytes(4, byteorder="big"))
                f.write(metadata_json)
                f.write(data)

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

            # For performance with large numbers of files, use sampling approach
            total_files = len(cache_files)

            if total_files == 0:
                valid_entries = 0
                expired_entries = 0
                corrupted_entries = 0
            else:
                # Sample up to 50 files for detailed analysis to avoid performance issues
                sample_size = min(50, total_files)
                if total_files <= 50:
                    sample_files = cache_files
                else:
                    # Take every nth file to get a representative sample
                    step = total_files // sample_size
                    sample_files = cache_files[::step][:sample_size]

                # Count valid vs expired/corrupted entries in sample
                valid_entries = 0
                expired_entries = 0
                corrupted_entries = 0

                for cache_file in sample_files:
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

                # Extrapolate sample results to total files
                if sample_size > 0:
                    valid_ratio = valid_entries / sample_size
                    expired_ratio = expired_entries / sample_size
                    corrupted_ratio = corrupted_entries / sample_size

                    valid_entries = int(total_files * valid_ratio)
                    expired_entries = int(total_files * expired_ratio)
                    corrupted_entries = int(total_files * corrupted_ratio)

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
        entries: List[Dict[str, Any]] = []

        try:
            # Get cache files either from path_manager or directly from cache directory
            if self.path_manager:
                cache_files = self.path_manager.list_cache_files()
            else:
                # Fallback: list cache files directly from cache directory
                if self.cache_dir is None:
                    return entries
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

                                        # Get the actual cache key from metadata
                                        actual_key = metadata.get("key", key)

                                        # Try to parse as hierarchical key first
                                        from ..key_builder import CacheKeyBuilder

                                        key_components = CacheKeyBuilder.parse_key(actual_key)

                                        # Check if this is a hierarchical key (has colons)
                                        if (
                                            ":" in actual_key
                                            and key_components.get("resource_type") != actual_key
                                        ):
                                            # This is a hierarchical key
                                            resource_type = key_components.get(
                                                "resource_type", "other"
                                            )
                                            operation_from_key = key_components.get(
                                                "operation", operation
                                            )

                                        else:
                                            # This is a hash-based key, extract info from operation name
                                            operation_name = actual_key
                                            if operation_name.startswith("list_"):
                                                operation_from_key = "list"
                                                if "user" in operation_name:
                                                    resource_type = "user"
                                                elif "group" in operation_name:
                                                    resource_type = "group"
                                                elif "permission_set" in operation_name:
                                                    resource_type = "permission_set"
                                                elif "assignment" in operation_name:
                                                    resource_type = "assignment"
                                                elif "account" in operation_name:
                                                    resource_type = "account"
                                                elif "organizational_unit" in operation_name:
                                                    resource_type = "organizational_unit"
                                                else:
                                                    resource_type = "other"
                                            elif operation_name.startswith("describe_"):
                                                operation_from_key = "describe"
                                                if "user" in operation_name:
                                                    resource_type = "user"
                                                elif "group" in operation_name:
                                                    resource_type = "group"
                                                elif "permission_set" in operation_name:
                                                    resource_type = "permission_set"
                                                elif "assignment" in operation_name:
                                                    resource_type = "assignment"
                                                elif "account" in operation_name:
                                                    resource_type = "account"
                                                else:
                                                    resource_type = "other"
                                            else:
                                                operation_from_key = operation_name
                                                resource_type = "other"

                                        entry = {
                                            "key": key,
                                            "operation": operation_from_key,
                                            "resource": resource_type,
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

                        # Get the actual cache key from the cache data
                        actual_key = cache_data.get("key", key)

                        # Try to parse as hierarchical key first
                        from ..key_builder import CacheKeyBuilder

                        key_components = CacheKeyBuilder.parse_key(actual_key)

                        # Check if this is a hierarchical key (has colons)
                        if ":" in actual_key and key_components.get("resource_type") != actual_key:
                            # This is a hierarchical key
                            resource_type = key_components.get("resource_type", "other")
                            operation_from_key = key_components.get("operation", operation)
                        else:
                            # This is a hash-based key, extract info from operation name
                            operation_name = actual_key
                            if operation_name.startswith("list_"):
                                operation_from_key = "list"
                                if "user" in operation_name:
                                    resource_type = "user"
                                elif "group" in operation_name:
                                    resource_type = "group"
                                elif "permission_set" in operation_name:
                                    resource_type = "permission_set"
                                elif "assignment" in operation_name:
                                    resource_type = "assignment"
                                elif "account" in operation_name:
                                    resource_type = "account"
                                elif "organizational_unit" in operation_name:
                                    resource_type = "organizational_unit"
                                else:
                                    resource_type = "other"
                            elif operation_name.startswith("describe_"):
                                operation_from_key = "describe"
                                if "user" in operation_name:
                                    resource_type = "user"
                                elif "group" in operation_name:
                                    resource_type = "group"
                                elif "permission_set" in operation_name:
                                    resource_type = "permission_set"
                                elif "assignment" in operation_name:
                                    resource_type = "assignment"
                                elif "account" in operation_name:
                                    resource_type = "account"
                                else:
                                    resource_type = "other"
                            else:
                                operation_from_key = operation_name
                                resource_type = "other"

                        entry = {
                            "key": key,
                            "operation": operation_from_key,
                            "resource": resource_type,
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
                        # Parse the cache key to extract resource type and operation
                        from ..key_builder import CacheKeyBuilder

                        key_components = CacheKeyBuilder.parse_key(key)
                        resource_type = key_components.get("resource_type", "other")
                        operation_from_key = key_components.get("operation", "unknown")

                        entry = {
                            "key": key,
                            "operation": operation_from_key,
                            "resource": resource_type,
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

    def health_check(self) -> bool:
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
                    return False

            # Test write access by creating a temporary file
            test_file = cache_dir / ".health_check_test"
            try:
                test_file.write_text("health_check")
                test_file.unlink()
                logger.debug("File backend health check passed")
                return True
            except Exception as e:
                logger.error(
                    f"File backend health check failed - cannot write to cache directory: {e}"
                )
                return False

        except Exception as e:
            logger.error(f"File backend health check failed with unexpected error: {e}")
            return False

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

    def cleanup_expired_files(self) -> int:
        """
        Clean up expired cache files from the filesystem.

        This method scans all cache files and removes those that have expired.
        It's more efficient than checking files individually during access.

        Returns:
            Number of expired files removed

        Raises:
            CacheBackendError: If cleanup operation fails
        """
        try:
            # Get all cache files
            if self.path_manager:
                cache_files = self.path_manager.list_cache_files()
            else:
                # Fallback: list cache files directly from cache directory
                if self.cache_dir is None:
                    return 0
                cache_dir = Path(self.cache_dir)
                if not cache_dir.exists():
                    return 0
                cache_files = list(cache_dir.glob("*.json"))

            if not cache_files:
                return 0

            removed_count = 0
            current_time = time.time()

            for cache_file in cache_files:
                try:
                    # Check if file is expired without loading full content
                    if self._is_file_expired(cache_file, current_time):
                        self._remove_cache_file(cache_file)
                        removed_count += 1
                        logger.debug(f"Removed expired cache file: {cache_file}")

                except Exception as e:
                    logger.warning(f"Error checking/removing cache file {cache_file}: {e}")
                    continue

            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} expired cache files")

            return removed_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired cache files: {e}")
            raise CacheBackendError(
                f"Failed to cleanup expired cache files: {e}",
                backend_type=self.backend_type,
                original_error=e,
            )

    def _is_file_expired(self, cache_file: Path, current_time: float) -> bool:
        """
        Check if a cache file is expired without loading full content.

        Args:
            cache_file: Path to cache file
            current_time: Current timestamp

        Returns:
            True if file is expired, False otherwise
        """
        try:
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
                            # Check if expired
                            return current_time > float(metadata["created_at"]) + float(
                                metadata["ttl"]
                            )
                except (ValueError, json.JSONDecodeError, KeyError):
                    # Not the new format, fall through to old format
                    pass

            # Try old JSON format - only read the first part to get TTL info
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    # Read only the first few lines to get TTL info
                    content = f.read(1024)  # Read first 1KB

                    # Try to extract created_at and ttl from the JSON
                    if '"created_at"' in content and '"ttl"' in content:
                        # Parse just the relevant fields
                        import re

                        created_at_match = re.search(r'"created_at":\s*(\d+(?:\.\d+)?)', content)
                        ttl_match = re.search(r'"ttl":\s*(\d+)', content)

                        if created_at_match and ttl_match:
                            created_at = float(created_at_match.group(1))
                            ttl = int(ttl_match.group(1))
                            return current_time > created_at + ttl

            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                # If we can't parse it, consider it expired
                return True

            # If we can't determine expiration, consider it not expired
            return False

        except Exception:
            # If there's any error reading the file, consider it expired
            return True
