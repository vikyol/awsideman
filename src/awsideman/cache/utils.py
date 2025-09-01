"""Cache utilities for managing cache directory structure and file operations."""

import hashlib
from pathlib import Path
from typing import Optional


class CachePathManager:
    """Manages cache directory structure and file path utilities."""

    def __init__(self, base_cache_dir: Optional[str] = None, profile: Optional[str] = None):
        """Initialize cache path manager.

        Args:
            base_cache_dir: Optional custom cache directory path.
                          Defaults to ~/.awsideman/cache/
            profile: AWS profile name for isolation
        """
        if base_cache_dir:
            self.cache_dir = Path(base_cache_dir)
        else:
            self.cache_dir = Path.home() / ".awsideman" / "cache"

        # Add profile isolation
        profile_name = profile or "default"
        self.cache_dir = self.cache_dir / "profiles" / profile_name

    def ensure_cache_directory(self) -> None:
        """Create cache directory if it doesn't exist.

        Raises:
            OSError: If directory cannot be created due to permissions or disk space
            PermissionError: If insufficient permissions to create directory
        """
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(
                f"Permission denied creating cache directory {self.cache_dir}: {e}"
            )
        except OSError as e:
            if "No space left on device" in str(e):
                raise OSError(f"Disk full - cannot create cache directory {self.cache_dir}: {e}")
            else:
                raise OSError(f"Cannot create cache directory {self.cache_dir}: {e}")

    def get_cache_file_path(self, cache_key: str) -> Path:
        """Generate file path for a cache key.

        Args:
            cache_key: The cache key to generate path for

        Returns:
            Path object for the cache file
        """
        # Use hash of cache key as filename to avoid filesystem issues
        filename = hashlib.sha256(cache_key.encode()).hexdigest() + ".json"
        return self.cache_dir / filename

    def generate_cache_key(self, operation: str, params: dict) -> str:
        """Generate a deterministic cache key from operation and parameters.

        Args:
            operation: AWS operation name
            params: Dictionary of parameters

        Returns:
            Deterministic cache key string
        """
        # Sort parameters to ensure consistent key generation
        sorted_params = sorted(params.items()) if params else []
        key_data = f"{operation}:{sorted_params}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get_cache_directory(self) -> Path:
        """Get the cache directory path.

        Returns:
            Path object for the cache directory
        """
        return self.cache_dir

    def cache_file_exists(self, cache_key: str) -> bool:
        """Check if cache file exists for given key.

        Args:
            cache_key: The cache key to check

        Returns:
            True if cache file exists, False otherwise
        """
        return self.get_cache_file_path(cache_key).exists()

    def delete_cache_file(self, cache_key: str) -> bool:
        """Delete cache file for given key.

        Args:
            cache_key: The cache key to delete

        Returns:
            True if file was deleted, False if it didn't exist

        Raises:
            PermissionError: If insufficient permissions to delete file
            OSError: If file cannot be deleted due to OS error
        """
        try:
            cache_file = self.get_cache_file_path(cache_key)
            if cache_file.exists():
                cache_file.unlink()
                return True
            return False
        except PermissionError as e:
            raise PermissionError(f"Permission denied deleting cache file {cache_file}: {e}")
        except OSError as e:
            raise OSError(f"Cannot delete cache file {cache_file}: {e}")

    def clear_all_cache_files(self) -> int:
        """Delete all cache files in the cache directory.

        Returns:
            Number of files deleted

        Note:
            Continues deleting files even if some deletions fail.
            Errors are logged but don't stop the operation.
        """
        if not self.cache_dir.exists():
            return 0

        deleted_count = 0
        failed_count = 0

        try:
            cache_files = list(self.cache_dir.glob("*.json"))
        except OSError as e:
            # If we can't even list the directory, log and return
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Cannot list cache directory {self.cache_dir}: {e}")
            return 0

        for cache_file in cache_files:
            try:
                cache_file.unlink()
                deleted_count += 1
            except PermissionError as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Permission denied deleting cache file {cache_file}: {e}")
                failed_count += 1
            except OSError as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"OS error deleting cache file {cache_file}: {e}")
                failed_count += 1
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error deleting cache file {cache_file}: {e}")
                failed_count += 1

        if failed_count > 0:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to delete {failed_count} cache files out of {len(cache_files)} total"
            )

        return deleted_count

    def get_cache_size(self) -> int:
        """Get total size of cache directory in bytes.

        Returns:
            Total size in bytes

        Note:
            Continues calculating size even if some files cannot be accessed.
            Errors are logged but don't stop the operation.
        """
        if not self.cache_dir.exists():
            return 0

        total_size = 0
        failed_count = 0

        try:
            cache_files = list(self.cache_dir.glob("*.json"))
        except OSError as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Cannot list cache directory {self.cache_dir}: {e}")
            return 0

        for cache_file in cache_files:
            try:
                total_size += cache_file.stat().st_size
            except (OSError, PermissionError) as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Cannot get size of cache file {cache_file}: {e}")
                failed_count += 1
            except Exception as e:
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error getting size of cache file {cache_file}: {e}")
                failed_count += 1

        if failed_count > 0:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to get size for {failed_count} cache files")

        return total_size

    def list_cache_files(self) -> list[Path]:
        """List all cache files in the cache directory.

        Returns:
            List of Path objects for cache files

        Note:
            Returns empty list if directory cannot be accessed.
            Errors are logged but don't raise exceptions.
        """
        if not self.cache_dir.exists():
            return []

        try:
            return list(self.cache_dir.glob("*.json"))
        except OSError as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Cannot list cache directory {self.cache_dir}: {e}")
            return []
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error listing cache directory {self.cache_dir}: {e}")
            return []
