"""Cache manager for handling cache operations with TTL support."""

import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from .cache_utils import CachePathManager
from .models import CacheEntry, CacheConfig
from .config import Config

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Core cache manager that handles get/set/invalidate operations with TTL support.
    
    Provides a simple interface for caching data with automatic expiration
    and file-based JSON storage.
    """
    
    def __init__(self, config: Optional[CacheConfig] = None, base_cache_dir: Optional[str] = None):
        """Initialize cache manager.
        
        Args:
            config: Cache configuration. If None, loads from Config class.
            base_cache_dir: Optional custom cache directory path.
        """
        if config is None:
            # Load cache configuration from Config class
            self.config = self._load_cache_config()
        else:
            self.config = config
            
        self.path_manager = CachePathManager(base_cache_dir)
        
        # Ensure cache directory exists
        try:
            self.path_manager.ensure_cache_directory()
        except Exception as e:
            logger.error(f"Failed to create cache directory: {e}")
            # Disable caching if we can't create the directory
            self.config.enabled = False
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve data from cache if it exists and is not expired.
        
        Args:
            key: Cache key to retrieve
            
        Returns:
            Cached data if found and not expired, None otherwise
        """
        if not self.config.enabled:
            return None
        
        cache_file = None
        try:
            cache_file = self.path_manager.get_cache_file_path(key)
            
            if not cache_file.exists():
                return None
            
            # Read cache entry from file
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Validate cache data structure
            required_fields = ['data', 'created_at', 'ttl', 'key', 'operation']
            if not all(field in cache_data for field in required_fields):
                logger.warning(f"Corrupted cache file missing required fields: {cache_file}")
                self._handle_corrupted_cache_file(cache_file, "missing required fields")
                return None
            
            # Create CacheEntry object from loaded data
            cache_entry = CacheEntry(
                data=cache_data['data'],
                created_at=cache_data['created_at'],
                ttl=cache_data['ttl'],
                key=cache_data['key'],
                operation=cache_data['operation']
            )
            
            # Check if entry has expired
            if self._is_expired(cache_entry):
                # Remove expired entry
                self._remove_cache_file(cache_file)
                return None
            
            logger.debug(f"Cache hit for key: {key}")
            return cache_entry.data
            
        except json.JSONDecodeError as e:
            logger.warning(f"Corrupted cache file with invalid JSON: {cache_file} - {e}")
            if cache_file:
                self._handle_corrupted_cache_file(cache_file, f"invalid JSON: {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Corrupted cache file with invalid data structure: {cache_file} - {e}")
            if cache_file:
                self._handle_corrupted_cache_file(cache_file, f"invalid data structure: {e}")
            return None
        except PermissionError as e:
            logger.error(f"Permission denied reading cache file {cache_file}: {e}")
            return None
        except OSError as e:
            logger.error(f"OS error reading cache file {cache_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading cache for key {key}: {e}")
            if cache_file:
                self._handle_corrupted_cache_file(cache_file, f"unexpected error: {e}")
            return None
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None, operation: str = "unknown") -> None:
        """Store data in cache with optional TTL override.
        
        Args:
            key: Cache key to store data under
            data: Data to cache
            ttl: Optional TTL override. If None, uses default TTL.
            operation: AWS operation that generated this data
        """
        if not self.config.enabled:
            return
        
        cache_file = None
        try:
            # Validate input data - allow dict, list, or other JSON-serializable types
            if not isinstance(data, (dict, list, str, int, float, bool, type(None))):
                logger.warning(f"Cannot cache non-JSON-serializable data for key {key}: {type(data)}")
                return
            
            # Use provided TTL or get from config
            effective_ttl = ttl or self.config.get_ttl_for_operation(operation)
            
            # Create cache entry
            cache_entry = CacheEntry(
                data=data,
                created_at=time.time(),
                ttl=effective_ttl,
                key=key,
                operation=operation
            )
            
            # Prepare data for JSON serialization
            cache_data = {
                'data': cache_entry.data,
                'created_at': cache_entry.created_at,
                'ttl': cache_entry.ttl,
                'key': cache_entry.key,
                'operation': cache_entry.operation
            }
            
            # Ensure cache directory exists before writing
            try:
                self.path_manager.ensure_cache_directory()
            except Exception as dir_error:
                logger.error(f"Failed to ensure cache directory exists: {dir_error}")
                return
            
            # Check cache size before writing and cleanup if needed
            self._check_and_manage_cache_size()
            
            # Write to cache file
            cache_file = self.path_manager.get_cache_file_path(key)
            
            # Write to temporary file first, then rename for atomic operation
            temp_file = cache_file.with_suffix('.tmp')
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, default=str)
            
            # Atomic rename
            temp_file.rename(cache_file)
            logger.debug(f"Cached data for key: {key} with TTL: {effective_ttl}s")
            
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize data for cache key {key}: {e}")
            self._cleanup_temp_file(cache_file)
        except PermissionError as e:
            logger.error(f"Permission denied writing cache file {cache_file}: {e}")
            self._cleanup_temp_file(cache_file)
        except OSError as e:
            if "No space left on device" in str(e):
                logger.error(f"Disk full - cannot write cache file {cache_file}: {e}")
                # Try to clean up some space by removing old cache entries
                self._cleanup_old_entries()
            else:
                logger.error(f"OS error writing cache file {cache_file}: {e}")
            self._cleanup_temp_file(cache_file)
        except Exception as e:
            logger.error(f"Unexpected error writing cache for key {key}: {e}")
            self._cleanup_temp_file(cache_file)
            # Cache write failures should not break the operation
    
    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate specific cache entry or all entries if key is None.
        
        Args:
            key: Cache key to invalidate. If None, invalidates all cache entries.
        """
        if not self.config.enabled:
            return
        
        try:
            if key is None:
                # Clear all cache entries
                deleted_count = self.path_manager.clear_all_cache_files()
                logger.info(f"Cleared all cache entries ({deleted_count} files)")
            else:
                # Clear specific cache entry
                if self.path_manager.delete_cache_file(key):
                    logger.debug(f"Invalidated cache entry for key: {key}")
                else:
                    logger.debug(f"Cache entry not found for key: {key}")
                    
        except PermissionError as e:
            logger.error(f"Permission denied invalidating cache: {e}")
        except OSError as e:
            logger.error(f"OS error invalidating cache: {e}")
        except Exception as e:
            logger.error(f"Unexpected error invalidating cache: {e}")
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry has expired based on TTL.
        
        Args:
            entry: Cache entry to check
            
        Returns:
            True if entry has expired, False otherwise
        """
        return entry.is_expired()
    
    def _remove_cache_file(self, cache_file: Path) -> None:
        """Remove a cache file safely.
        
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
        """Handle a corrupted cache file by removing it and logging the issue.
        
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
        """Clean up temporary file if it exists.
        
        Args:
            cache_file: Path to the cache file (temp file will have .tmp suffix)
        """
        if cache_file is None:
            return
        
        temp_file = cache_file.with_suffix('.tmp')
        try:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")
    
    def _cleanup_old_entries(self, max_entries_to_remove: int = 10) -> int:
        """Clean up old cache entries to free up space.
        
        Args:
            max_entries_to_remove: Maximum number of entries to remove
            
        Returns:
            Number of entries actually removed
        """
        try:
            cache_files = self.path_manager.list_cache_files()
            if not cache_files:
                return 0
            
            # Sort by modification time (oldest first)
            cache_files.sort(key=lambda f: f.stat().st_mtime)
            
            removed_count = 0
            for cache_file in cache_files[:max_entries_to_remove]:
                try:
                    cache_file.unlink()
                    removed_count += 1
                    logger.debug(f"Removed old cache file for cleanup: {cache_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove old cache file {cache_file}: {e}")
            
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} old cache entries to free space")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            return 0
    
    def _check_and_manage_cache_size(self) -> None:
        """Check cache size and perform cleanup if it exceeds the limit.
        
        This method monitors the cache size and automatically removes old entries
        when the cache size exceeds the configured maximum size.
        """
        try:
            current_size_bytes = self.path_manager.get_cache_size()
            max_size_bytes = self.config.max_size_bytes()
            
            if current_size_bytes <= max_size_bytes:
                return  # Cache size is within limits
            
            current_size_mb = current_size_bytes / (1024 * 1024)
            logger.info(f"Cache size ({current_size_mb:.1f} MB) exceeds limit ({self.config.max_size_mb} MB), cleaning up...")
            
            # Calculate how much we need to free up (aim for 80% of max size to avoid frequent cleanups)
            target_size_bytes = int(max_size_bytes * 0.8)
            bytes_to_free = current_size_bytes - target_size_bytes
            
            # Remove old entries until we free up enough space
            removed_count = self._cleanup_by_size(bytes_to_free)
            
            # Get new size after cleanup
            new_size_bytes = self.path_manager.get_cache_size()
            new_size_mb = new_size_bytes / (1024 * 1024)
            
            logger.info(f"Cache cleanup completed: removed {removed_count} entries, "
                       f"cache size reduced from {current_size_mb:.1f} MB to {new_size_mb:.1f} MB")
            
        except Exception as e:
            logger.error(f"Error during cache size management: {e}")
    
    def _cleanup_by_size(self, bytes_to_free: int) -> int:
        """Clean up cache entries to free up the specified amount of space.
        
        Args:
            bytes_to_free: Number of bytes to free up
            
        Returns:
            Number of entries removed
        """
        try:
            cache_files = self.path_manager.list_cache_files()
            if not cache_files:
                return 0
            
            # Create list of (file, size, age) tuples for sorting
            file_info = []
            current_time = time.time()
            
            for cache_file in cache_files:
                try:
                    file_size = cache_file.stat().st_size
                    file_mtime = cache_file.stat().st_mtime
                    file_age = current_time - file_mtime
                    
                    # Try to read cache entry to check if it's expired
                    is_expired = False
                    try:
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            cache_data = json.load(f)
                        
                        cache_entry = CacheEntry(
                            data=cache_data['data'],
                            created_at=cache_data['created_at'],
                            ttl=cache_data['ttl'],
                            key=cache_data['key'],
                            operation=cache_data['operation']
                        )
                        
                        is_expired = cache_entry.is_expired(current_time)
                    except Exception:
                        # If we can't read the file, treat it as expired/corrupted
                        is_expired = True
                    
                    file_info.append((cache_file, file_size, file_age, is_expired))
                    
                except Exception as e:
                    logger.warning(f"Error getting info for cache file {cache_file}: {e}")
                    continue
            
            # Sort by priority: expired first, then by age (oldest first)
            file_info.sort(key=lambda x: (not x[3], x[2]), reverse=False)
            
            # Remove files until we've freed up enough space
            bytes_freed = 0
            removed_count = 0
            
            for cache_file, file_size, file_age, is_expired in file_info:
                if bytes_freed >= bytes_to_free:
                    break
                
                try:
                    cache_file.unlink()
                    bytes_freed += file_size
                    removed_count += 1
                    
                    status = "expired" if is_expired else f"old ({file_age/3600:.1f}h)"
                    logger.debug(f"Removed cache file ({status}): {cache_file.name} ({file_size} bytes)")
                    
                except Exception as e:
                    logger.warning(f"Failed to remove cache file {cache_file}: {e}")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during size-based cache cleanup: {e}")
            return 0
    
    def get_cache_size_info(self) -> Dict[str, Any]:
        """Get detailed cache size information.
        
        Returns:
            Dictionary containing cache size statistics and status
        """
        try:
            current_size_bytes = self.path_manager.get_cache_size()
            max_size_bytes = self.config.max_size_bytes()
            
            current_size_mb = current_size_bytes / (1024 * 1024)
            usage_percentage = (current_size_bytes / max_size_bytes * 100) if max_size_bytes > 0 else 0
            
            return {
                'current_size_bytes': current_size_bytes,
                'current_size_mb': round(current_size_mb, 2),
                'max_size_bytes': max_size_bytes,
                'max_size_mb': self.config.max_size_mb,
                'usage_percentage': round(usage_percentage, 1),
                'is_over_limit': current_size_bytes > max_size_bytes,
                'bytes_over_limit': max(0, current_size_bytes - max_size_bytes),
                'available_space_bytes': max(0, max_size_bytes - current_size_bytes),
                'available_space_mb': round(max(0, max_size_bytes - current_size_bytes) / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"Error getting cache size info: {e}")
            return {
                'error': str(e),
                'current_size_bytes': 0,
                'current_size_mb': 0,
                'max_size_bytes': self.config.max_size_bytes(),
                'max_size_mb': self.config.max_size_mb,
                'usage_percentage': 0,
                'is_over_limit': False
            }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary containing cache statistics
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
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    # Validate cache data structure
                    required_fields = ['data', 'created_at', 'ttl', 'key', 'operation']
                    if not all(field in cache_data for field in required_fields):
                        corrupted_entries += 1
                        continue
                    
                    cache_entry = CacheEntry(
                        data=cache_data['data'],
                        created_at=cache_data['created_at'],
                        ttl=cache_data['ttl'],
                        key=cache_data['key'],
                        operation=cache_data['operation']
                    )
                    
                    if self._is_expired(cache_entry):
                        expired_entries += 1
                    else:
                        valid_entries += 1
                        
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    # Count corrupted files separately from expired
                    corrupted_entries += 1
                except Exception as e:
                    logger.warning(f"Error reading cache file {cache_file} for stats: {e}")
                    corrupted_entries += 1
            
            stats = {
                'enabled': self.config.enabled,
                'total_entries': len(cache_files),
                'valid_entries': valid_entries,
                'expired_entries': expired_entries,
                'corrupted_entries': corrupted_entries,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'cache_directory': str(self.path_manager.get_cache_directory()),
                'default_ttl': self.config.default_ttl,
                'max_size_mb': self.config.max_size_mb
            }
            
            # Add warning if there are corrupted entries
            if corrupted_entries > 0:
                stats['warning'] = f"{corrupted_entries} corrupted cache files detected"
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                'enabled': self.config.enabled,
                'error': str(e),
                'cache_directory': str(self.path_manager.get_cache_directory()) if hasattr(self, 'path_manager') else 'unknown'
            }
    
    def _load_cache_config(self) -> CacheConfig:
        """Load cache configuration from Config class with graceful fallback to defaults.
        
        Returns:
            CacheConfig object with loaded configuration
        """
        try:
            # Load configuration from Config class
            config_manager = Config()
            cache_config_dict = config_manager.get_cache_config()
            
            # Create CacheConfig object from dictionary
            cache_config = CacheConfig(
                enabled=cache_config_dict.get("enabled", True),
                default_ttl=cache_config_dict.get("default_ttl", 3600),
                operation_ttls=cache_config_dict.get("operation_ttls", {}),
                max_size_mb=cache_config_dict.get("max_size_mb", 100)
            )
            
            logger.debug(f"Loaded cache configuration: enabled={cache_config.enabled}, "
                        f"default_ttl={cache_config.default_ttl}, "
                        f"operation_ttls={len(cache_config.operation_ttls)} operations")
            
            return cache_config
            
        except Exception as e:
            logger.warning(f"Failed to load cache configuration, using defaults: {e}")
            # Return default configuration if loading fails
            return CacheConfig()