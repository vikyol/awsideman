"""Cache manager for handling cache operations with TTL support."""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..encryption.provider import EncryptionError, EncryptionProviderFactory
from ..utils.config import Config
from ..utils.models import CacheConfig, CacheEntry
from .backends.base import CacheBackend, CacheBackendError
from .config import AdvancedCacheConfig
from .factory import BackendFactory
from .utils import CachePathManager

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Core cache manager that handles get/set/invalidate operations with TTL support.

    Provides a simple interface for caching data with automatic expiration
    and pluggable backend/encryption support while maintaining backward compatibility.
    """

    def __init__(
        self,
        config: Optional[Union[CacheConfig, AdvancedCacheConfig]] = None,
        base_cache_dir: Optional[str] = None,
        backend: Optional[CacheBackend] = None,
        encryption_provider: Optional[Any] = None,
    ):
        """Initialize cache manager with configuration-driven initialization.

        This constructor implements automatic backend selection based on configuration,
        with comprehensive error handling and fallback mechanisms to ensure reliability.

        Args:
            config: Cache configuration. If None, loads from config file and environment.
            base_cache_dir: Optional custom cache directory path (for backward compatibility).
            backend: Optional cache backend instance. If None, creates based on config.
            encryption_provider: Optional encryption provider. If None, creates based on config.
        """
        logger.debug("Initializing CacheManager with configuration-driven initialization")

        # Initialize configuration with comprehensive loading and validation
        self.config = self._load_and_validate_configuration(config)

        # Initialize backend and encryption with fallback mechanisms
        self.backend: Optional[CacheBackend] = None
        self.encryption_provider: Optional[Any] = None
        self.path_manager: Optional[CachePathManager] = None

        # Check if this is an advanced configuration
        if isinstance(self.config, AdvancedCacheConfig):
            # For advanced configs, initialize backend/encryption and set path_manager to None
            if self.config.enabled:
                self._initialize_advanced_features(backend, encryption_provider, base_cache_dir)
            self.path_manager = None
        else:
            # For basic configs, always initialize path_manager for legacy methods
            self._initialize_path_manager(base_cache_dir)

            # Only initialize advanced features if cache is enabled
            if self.config.enabled:
                # For basic configs, we don't initialize advanced features
                pass
            else:
                logger.info("Cache is disabled in configuration")

    def _load_and_validate_configuration(
        self, config: Optional[Union[CacheConfig, AdvancedCacheConfig]]
    ) -> Union[CacheConfig, AdvancedCacheConfig]:
        """Load and validate cache configuration with comprehensive error handling.

        Args:
            config: Optional configuration instance

        Returns:
            Validated configuration instance
        """
        if config is not None:
            logger.debug(f"Using provided configuration: {type(config).__name__}")
            # Validate provided configuration if it's advanced config
            if isinstance(config, AdvancedCacheConfig):
                validation_errors = config.validate()
                if validation_errors:
                    logger.warning(f"Configuration validation errors: {validation_errors}")
                    # Log errors but continue - validation errors are warnings, not fatal
                    for field, error in validation_errors.items():
                        logger.warning(f"Config validation - {field}: {error}")
            return config

        # Fast path: Use minimal default configuration for simple initialization
        # This avoids expensive file/environment loading for basic use cases
        logger.debug("No configuration provided, using minimal default configuration")
        return CacheConfig(enabled=True, default_ttl=3600, max_size_mb=100)

    def _load_cache_config(self) -> CacheConfig:
        """Load cache configuration from file with fast path optimization.

        Returns:
            CacheConfig instance
        """
        # Fast path: Check for simple configuration files that don't require advanced features
        try:
            from ..utils.config import Config

            config = Config()

            # If we have a simple cache config, use it directly
            if hasattr(config, "cache") and config.cache:
                cache_config = config.cache
                # Check if this is a simple configuration that can use fast path
                # Even with encryption enabled, if it's just file backend, we can use fast path
                if isinstance(cache_config, dict) and cache_config.get("backend_type") == "file":
                    logger.debug("Using simple file-based cache configuration (fast path)")
                    return CacheConfig(
                        enabled=cache_config.get("enabled", True),
                        default_ttl=cache_config.get("default_ttl", 3600),
                        max_size_mb=cache_config.get("max_size_mb", 100),
                    )
        except Exception:
            pass

        # Fall back to standard configuration loading
        return self._load_cache_config_standard()

    def _is_advanced_config_meaningful(self, config: AdvancedCacheConfig) -> bool:
        """Check if advanced configuration has meaningful non-default settings.

        Args:
            config: Advanced configuration to check

        Returns:
            True if configuration has meaningful advanced settings
        """
        # Check for non-default backend type
        if config.backend_type != "file":
            return True

        # Check for encryption enabled
        if config.encryption_enabled:
            return True

        # Check for non-default DynamoDB settings
        if (
            config.dynamodb_table_name != "awsideman-cache"
            or config.dynamodb_region is not None
            or config.dynamodb_profile is not None
        ):
            return True

        # Check for custom file cache directory
        if config.file_cache_dir is not None:
            return True

        # Check for non-default hybrid settings
        if config.hybrid_local_ttl != 300:
            return True

        return False

    def _load_basic_cache_config(self) -> CacheConfig:
        """Load basic cache configuration as fallback.

        Returns:
            Basic CacheConfig instance
        """
        try:
            return self._load_cache_config_standard()
        except Exception as e:
            logger.error(f"Failed to load basic cache configuration: {e}")
            # Return minimal working configuration as last resort
            logger.warning("Using minimal default cache configuration")
            return CacheConfig(enabled=True, default_ttl=3600, max_size_mb=100)

    def _initialize_path_manager(self, base_cache_dir: Optional[str]) -> None:
        """Initialize path manager for backward compatibility.

        Args:
            base_cache_dir: Optional custom cache directory path
        """
        # For backward compatibility, maintain path_manager for basic config
        if isinstance(self.config, CacheConfig) and not isinstance(
            self.config, AdvancedCacheConfig
        ):
            logger.debug("Initializing path manager for basic configuration")
            self.path_manager = CachePathManager(base_cache_dir)
            # Ensure cache directory exists for backward compatibility
            try:
                self.path_manager.ensure_cache_directory()
                logger.debug(f"Cache directory initialized: {self.path_manager.cache_dir}")
            except Exception as e:
                logger.error(f"Failed to create cache directory: {e}")
                self.config.enabled = False
        else:
            # For advanced config, path_manager is handled by the backend
            self.path_manager = None
            logger.debug("Path manager not needed for advanced configuration")

    def _initialize_advanced_features(
        self,
        backend: Optional[CacheBackend],
        encryption_provider: Optional[Any],
        base_cache_dir: Optional[str],
    ) -> None:
        """Initialize advanced cache features with comprehensive error handling and fallbacks.

        Args:
            backend: Optional backend instance
            encryption_provider: Optional encryption provider
            base_cache_dir: Optional custom cache directory path
        """
        try:
            logger.debug("Initializing advanced cache features")
            self._initialize_backend_and_encryption(backend, encryption_provider, base_cache_dir)
            logger.info(
                f"Successfully initialized cache with backend: {type(self.backend).__name__}, "
                f"encryption: {self.encryption_provider.get_encryption_type() if self.encryption_provider else 'none'}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize advanced cache features: {e}")
            logger.info("Attempting fallback to basic file-based caching")
            try:
                self._fallback_to_basic_cache(base_cache_dir)
                logger.info("Successfully fell back to basic file-based caching")
            except Exception as fallback_error:
                logger.error(f"Fallback to basic cache also failed: {fallback_error}")
                logger.warning("Disabling cache due to initialization failures")
                self.config.enabled = False
                self.backend = None
                self.encryption_provider = None

    def _initialize_backend_and_encryption(
        self,
        backend: Optional[CacheBackend],
        encryption_provider: Optional[Any],
        base_cache_dir: Optional[str],
    ) -> None:
        """Initialize backend and encryption providers with comprehensive error handling.

        Args:
            backend: Optional backend instance
            encryption_provider: Optional encryption provider
            base_cache_dir: Optional custom cache directory path
        """
        # Use advanced configuration if available
        if isinstance(self.config, AdvancedCacheConfig):
            logger.debug(
                f"Initializing advanced cache with backend: {self.config.backend_type}, "
                f"encryption: {self.config.encryption_enabled}"
            )

            # Initialize backend with automatic selection and fallback
            self._initialize_backend(backend, base_cache_dir)

            # Initialize encryption with fallback to no encryption
            self._initialize_encryption(encryption_provider)

        else:
            # For basic config, don't use backend/encryption system for full backward compatibility
            logger.debug(
                "Using basic configuration - backend and encryption handled by legacy methods"
            )
            self.backend = None
            self.encryption_provider = None

    def _initialize_backend(
        self, backend: Optional[CacheBackend], base_cache_dir: Optional[str]
    ) -> None:
        """Initialize cache backend with automatic selection and fallback mechanisms.

        Args:
            backend: Optional backend instance
            base_cache_dir: Optional custom cache directory path
        """
        if backend is not None:
            logger.debug(f"Using provided backend: {type(backend).__name__}")
            self.backend = backend
            return

        # Set file cache directory if provided for backward compatibility
        if (
            isinstance(self.config, AdvancedCacheConfig)
            and base_cache_dir
            and not self.config.file_cache_dir
        ):
            logger.debug(f"Setting file cache directory from base_cache_dir: {base_cache_dir}")
            self.config.file_cache_dir = base_cache_dir

        # Validate backend availability before attempting creation
        if isinstance(
            self.config, AdvancedCacheConfig
        ) and not BackendFactory.validate_backend_availability(self.config.backend_type):
            logger.warning(f"Requested backend '{self.config.backend_type}' is not available")
            available_backends = BackendFactory.get_available_backends()
            logger.info(f"Available backends: {available_backends}")

            # If requested backend is not available, try to use file backend as fallback
            if "file" in available_backends:
                logger.info("Falling back to file backend")
                if isinstance(self.config, AdvancedCacheConfig):
                    original_backend_type = self.config.backend_type
                    self.config.backend_type = "file"
                    try:
                        self.backend = BackendFactory.create_backend(self.config)
                        logger.info(
                            f"Successfully fell back from {original_backend_type} to file backend"
                        )
                        return
                    except Exception as e:
                        logger.error(f"File backend fallback also failed: {e}")
                        raise CacheBackendError(
                            f"Both {original_backend_type} and file backend failed"
                        )
                else:
                    raise CacheBackendError("Cannot fallback backend type for basic configuration")
            else:
                raise CacheBackendError("No available backends found")

        # Create backend with fallback mechanism
        try:
            if isinstance(self.config, AdvancedCacheConfig):
                logger.debug(f"Creating {self.config.backend_type} backend")
                self.backend = BackendFactory.create_backend_with_fallback(self.config)
            else:
                logger.debug("Creating basic file backend")
                # For basic config, create file backend directly
                from .backends.file import FileBackend

                self.backend = FileBackend(cache_dir=base_cache_dir or ".cache")
            logger.debug(f"Successfully created backend: {type(self.backend).__name__}")

            # Test backend health if possible
            try:
                if (
                    self.backend is not None
                    and hasattr(self.backend, "health_check")
                    and callable(self.backend.health_check)
                ):
                    if not self.backend.health_check():
                        logger.warning(
                            f"Backend health check failed for {type(self.backend).__name__}"
                        )
                    else:
                        logger.debug(
                            f"Backend health check passed for {type(self.backend).__name__}"
                        )
            except Exception as health_error:
                logger.debug(f"Backend health check error (non-fatal): {health_error}")

        except CacheBackendError as e:
            logger.error(f"Failed to create cache backend: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating cache backend: {e}")
            raise CacheBackendError(f"Unexpected error creating backend: {e}")

    def _initialize_encryption(self, encryption_provider: Optional[Any]) -> None:
        """Initialize encryption provider with fallback to no encryption.

        Args:
            encryption_provider: Optional encryption provider instance
        """
        if encryption_provider is not None:
            logger.debug(
                f"Using provided encryption provider: {type(encryption_provider).__name__}"
            )
            self.encryption_provider = encryption_provider
            return

        # Determine encryption type from configuration
        encryption_type = "none"
        if isinstance(self.config, AdvancedCacheConfig) and self.config.encryption_enabled:
            encryption_type = self.config.encryption_type
            logger.debug(f"Encryption enabled with type: {encryption_type}")
        else:
            logger.debug("Encryption disabled in configuration")

        # Create encryption provider with fallback
        try:
            self.encryption_provider = EncryptionProviderFactory.create_provider(encryption_type)
            logger.debug(f"Successfully created encryption provider: {encryption_type}")

            # Test encryption provider if it's not the no-encryption provider
            if encryption_type != "none" and self.encryption_provider is not None:
                try:
                    # Test encrypt/decrypt cycle with simple data
                    test_data = {"test": "encryption_test"}
                    encrypted = self.encryption_provider.encrypt(test_data)
                    decrypted = self.encryption_provider.decrypt(encrypted)
                    if decrypted != test_data:
                        raise EncryptionError("Encryption test failed - data mismatch")
                    logger.debug("Encryption provider test successful")
                except Exception as test_error:
                    logger.warning(f"Encryption provider test failed: {test_error}")
                    logger.info("Falling back to no encryption")
                    self.encryption_provider = EncryptionProviderFactory.create_provider("none")

        except EncryptionError as e:
            logger.warning(f"Failed to create encryption provider '{encryption_type}': {e}")
            logger.info("Falling back to no encryption")
            try:
                self.encryption_provider = EncryptionProviderFactory.create_provider("none")
                logger.debug("Successfully fell back to no encryption")
            except Exception as fallback_error:
                logger.error(f"Failed to create no-encryption provider: {fallback_error}")
                raise EncryptionError(
                    f"Failed to initialize any encryption provider: {fallback_error}"
                )
        except Exception as e:
            logger.error(f"Unexpected error creating encryption provider: {e}")
            logger.info("Falling back to no encryption")
            try:
                self.encryption_provider = EncryptionProviderFactory.create_provider("none")
            except Exception as fallback_error:
                raise EncryptionError(
                    f"Failed to initialize encryption: {e}, fallback also failed: {fallback_error}"
                )

    def _fallback_to_basic_cache(self, base_cache_dir):
        """Fallback to basic file-based caching with comprehensive error handling.

        This method implements the fallback mechanism required by requirement 5.4:
        "WHEN advanced features fail THEN the system SHALL gracefully fallback to basic file caching."

        Args:
            base_cache_dir: Optional custom cache directory path
        """
        logger.info("Falling back to basic file-based cache (no advanced features)")

        try:
            # Ensure path_manager exists for basic cache operations
            if self.path_manager is None:
                logger.debug("Creating path manager for basic cache fallback")
                self.path_manager = CachePathManager(base_cache_dir)
                try:
                    self.path_manager.ensure_cache_directory()
                    logger.debug(f"Basic cache directory created: {self.path_manager.cache_dir}")
                except Exception as e:
                    logger.error(f"Failed to create basic cache directory: {e}")
                    raise

            # Create basic file backend with comprehensive error handling
            try:
                from .backends.file import FileBackend

                cache_dir = base_cache_dir or str(Path.home() / ".awsideman" / "cache")
                logger.debug(f"Creating file backend for fallback with directory: {cache_dir}")

                self.backend = FileBackend(cache_dir=cache_dir)
                logger.debug("File backend created successfully for fallback")

                # Test the backend
                if hasattr(self.backend, "health_check") and callable(self.backend.health_check):
                    if not self.backend.health_check():
                        logger.warning("Fallback file backend health check failed")
                    else:
                        logger.debug("Fallback file backend health check passed")

            except ImportError as e:
                logger.error(f"Failed to import FileBackend for fallback: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to create file backend for fallback: {e}")
                raise

            # Create no-encryption provider for basic cache
            try:
                self.encryption_provider = EncryptionProviderFactory.create_provider("none")
                logger.debug("No-encryption provider created for fallback")
            except Exception as e:
                logger.error(f"Failed to create no-encryption provider for fallback: {e}")
                raise

            # Update configuration to reflect fallback state
            if isinstance(self.config, AdvancedCacheConfig):
                logger.debug("Updating configuration to reflect fallback state")
                self.config.backend_type = "file"
                self.config.encryption_enabled = False
                self.config.encryption_type = "none"

            logger.info("Successfully fell back to basic file-based caching")

        except Exception as e:
            logger.error(f"Complete fallback failure - disabling cache: {e}")
            self.config.enabled = False
            self.backend = None
            self.encryption_provider = None
            self.path_manager = None
            raise

    def get(self, key: str) -> Optional[Any]:
        """Retrieve data from cache if it exists and is not expired.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached data if found and not expired, None otherwise
        """
        if not self.config.enabled:
            return None

        # Use backend and encryption if available (preferred path)
        if self.backend and self.encryption_provider:
            return self._get_with_backend(key)

        # Fallback to legacy file-based implementation for backward compatibility
        return self._get_legacy(key)

    def _get_with_backend(self, key: str) -> Optional[Any]:
        """Get data using backend and encryption providers with transparent encryption/decryption."""
        if self.backend is None or self.encryption_provider is None:
            logger.debug("Backend or encryption provider not initialized")
            return None

        try:
            # Get encrypted data from backend
            encrypted_data = self.backend.get(key)
            if encrypted_data is None:
                logger.debug(f"Cache miss for key: {key}")
                return None

            # Decrypt the data transparently
            try:
                decrypted_data = self.encryption_provider.decrypt(encrypted_data)
            except EncryptionError as e:
                logger.warning(f"Failed to decrypt cache data for key {key}: {e}")
                # Invalidate corrupted entry
                try:
                    if self.backend is not None:
                        self.backend.invalidate(key)
                except Exception:
                    pass
                return None

            # The decrypted data should be a structured cache entry
            if isinstance(decrypted_data, dict) and "data" in decrypted_data:
                # This is a structured cache entry with metadata
                cache_entry = CacheEntry(
                    data=decrypted_data["data"],
                    created_at=decrypted_data.get("created_at", time.time()),
                    ttl=decrypted_data.get("ttl", self.config.default_ttl),
                    key=decrypted_data.get("key", key),
                    operation=decrypted_data.get("operation", "unknown"),
                )

                # Check if entry has expired
                if self._is_expired(cache_entry):
                    # Remove expired entry
                    try:
                        if self.backend is not None:
                            self.backend.invalidate(key)
                            logger.debug(f"Removed expired cache entry for key: {key}")
                    except Exception as e:
                        logger.warning(f"Failed to invalidate expired cache entry {key}: {e}")
                    return None

                logger.debug(f"Cache hit for key: {key}")
                return cache_entry.data
            else:
                # This might be raw cached data (for backward compatibility)
                # but we should log this as it's unexpected in the new system
                logger.warning(
                    f"Cache entry for key {key} has unexpected format, returning raw data"
                )
                return decrypted_data

        except CacheBackendError as e:
            logger.warning(f"Backend error retrieving cache for key {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error retrieving cache for key {key}: {e}")
            return None

    def _get_legacy(self, key: str) -> Optional[Any]:
        """Legacy file-based get implementation for backward compatibility."""
        if not self.path_manager:
            return None

        cache_file = None
        try:
            cache_file = self.path_manager.get_cache_file_path(key)

            if not cache_file.exists():
                return None

            # Read cache entry from file
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

    def set(
        self, key: str, data: Any, ttl: Optional[int] = None, operation: str = "unknown"
    ) -> None:
        """Store data in cache with optional TTL override.

        Args:
            key: Cache key to store data under
            data: Data to cache
            ttl: Optional TTL override. If None, uses default TTL.
            operation: AWS operation that generated this data
        """
        if not self.config.enabled:
            return

        # Use backend and encryption if available (preferred path)
        if self.backend and self.encryption_provider:
            self._set_with_backend(key, data, ttl, operation)
        else:
            # Fallback to legacy file-based implementation for backward compatibility
            self._set_legacy(key, data, ttl, operation)

    def _set_with_backend(self, key: str, data: Any, ttl: Optional[int], operation: str) -> None:
        """Set data using backend and encryption providers with transparent encryption."""
        if self.backend is None or self.encryption_provider is None:
            logger.debug("Backend or encryption provider not initialized")
            return

        try:
            # Validate input data - allow dict, list, or other JSON-serializable types
            if not isinstance(data, (dict, list, str, int, float, bool, type(None))):
                logger.warning(
                    f"Cannot cache non-JSON-serializable data for key {key}: {type(data)}"
                )
                return

            # Use provided TTL or get from config
            effective_ttl = ttl or self.config.get_ttl_for_operation(operation)

            # Create structured cache entry with metadata
            cache_data = {
                "data": data,
                "created_at": time.time(),
                "ttl": effective_ttl,
                "key": key,
                "operation": operation,
            }

            # Encrypt the data transparently
            try:
                encrypted_data = self.encryption_provider.encrypt(cache_data)
            except EncryptionError as e:
                logger.error(f"Failed to encrypt cache data for key {key}: {e}")
                return

            # Store encrypted data in backend
            try:
                self.backend.set(key, encrypted_data, effective_ttl, operation)
                logger.debug(
                    f"Cached data for key: {key} with TTL: {effective_ttl}s (backend: {type(self.backend).__name__}, encryption: {self.encryption_provider.get_encryption_type()})"
                )
            except CacheBackendError as e:
                logger.error(f"Backend error storing cache for key {key}: {e}")
                return

        except Exception as e:
            logger.error(f"Unexpected error writing cache for key {key}: {e}")
            # Cache write failures should not break the operation

    def _set_legacy(self, key: str, data: Any, ttl: Optional[int], operation: str) -> None:
        """Legacy file-based set implementation for backward compatibility."""
        if not self.path_manager:
            return

        cache_file = None
        try:
            # Validate input data - allow dict, list, or other JSON-serializable types
            if not isinstance(data, (dict, list, str, int, float, bool, type(None))):
                logger.warning(
                    f"Cannot cache non-JSON-serializable data for key {key}: {type(data)}"
                )
                return

            # Use provided TTL or get from config
            effective_ttl = ttl or self.config.get_ttl_for_operation(operation)

            # Create cache entry
            cache_entry = CacheEntry(
                data=data, created_at=time.time(), ttl=effective_ttl, key=key, operation=operation
            )

            # Prepare data for JSON serialization
            cache_data = {
                "data": cache_entry.data,
                "created_at": cache_entry.created_at,
                "ttl": cache_entry.ttl,
                "key": cache_entry.key,
                "operation": cache_entry.operation,
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
            temp_file = cache_file.with_suffix(".tmp")

            with open(temp_file, "w", encoding="utf-8") as f:
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

        # Use backend if available (preferred path)
        if self.backend:
            self._invalidate_with_backend(key)
        else:
            # Fallback to legacy file-based implementation for backward compatibility
            self._invalidate_legacy(key)

    def _invalidate_with_backend(self, key: Optional[str]) -> None:
        """Invalidate using backend with proper error handling."""
        if self.backend is None:
            logger.debug("Backend not initialized")
            return

        try:
            self.backend.invalidate(key)
            if key is None:
                logger.info(f"Cleared all cache entries (backend: {type(self.backend).__name__})")
            else:
                logger.debug(
                    f"Invalidated cache entry for key: {key} (backend: {type(self.backend).__name__})"
                )
        except CacheBackendError as e:
            logger.error(f"Backend error invalidating cache: {e}")
        except Exception as e:
            logger.error(f"Unexpected error invalidating cache: {e}")

    def _invalidate_legacy(self, key: Optional[str]) -> None:
        """Legacy file-based invalidate implementation for backward compatibility."""
        if not self.path_manager:
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

        temp_file = cache_file.with_suffix(".tmp")
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
        if self.path_manager is None:
            return 0

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
        # Only perform size management for file-based backends
        if not self.path_manager:
            return

        try:
            current_size_bytes = self.path_manager.get_cache_size()
            max_size_bytes = self.config.max_size_bytes()

            if current_size_bytes <= max_size_bytes:
                return  # Cache size is within limits

            current_size_mb = current_size_bytes / (1024 * 1024)
            logger.info(
                f"Cache size ({current_size_mb:.1f} MB) exceeds limit ({self.config.max_size_mb} MB), cleaning up..."
            )

            # Calculate how much we need to free up (aim for 80% of max size to avoid frequent cleanups)
            target_size_bytes = int(max_size_bytes * 0.8)
            bytes_to_free = current_size_bytes - target_size_bytes

            # Remove old entries until we free up enough space
            removed_count = self._cleanup_by_size(bytes_to_free)

            # Get new size after cleanup
            new_size_bytes = self.path_manager.get_cache_size()
            new_size_mb = new_size_bytes / (1024 * 1024)

            logger.info(
                f"Cache cleanup completed: removed {removed_count} entries, "
                f"cache size reduced from {current_size_mb:.1f} MB to {new_size_mb:.1f} MB"
            )

        except Exception as e:
            logger.error(f"Error during cache size management: {e}")

    def _cleanup_by_size(self, bytes_to_free: int) -> int:
        """Clean up cache entries to free up the specified amount of space.

        Args:
            bytes_to_free: Number of bytes to free up

        Returns:
            Number of entries removed
        """
        if self.path_manager is None:
            return 0

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
                        with open(cache_file, "r", encoding="utf-8") as f:
                            cache_data = json.load(f)

                        cache_entry = CacheEntry(
                            data=cache_data["data"],
                            created_at=cache_data["created_at"],
                            ttl=cache_data["ttl"],
                            key=cache_data["key"],
                            operation=cache_data["operation"],
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
                    logger.debug(
                        f"Removed cache file ({status}): {cache_file.name} ({file_size} bytes)"
                    )

                except Exception as e:
                    logger.warning(f"Failed to remove cache file {cache_file}: {e}")

            return removed_count

        except Exception as e:
            logger.error(f"Error during size-based cache cleanup: {e}")
            return 0

    def get_configuration_info(self) -> Dict[str, Any]:
        """Get detailed configuration information for debugging and monitoring.

        Returns:
            Dictionary containing configuration details, backend info, and status
        """
        config_info = {
            "enabled": self.config.enabled,
            "config_type": type(self.config).__name__,
            "backend_type": getattr(self.config, "backend_type", "file"),
            "backend_instance": type(self.backend).__name__ if self.backend else None,
            "encryption_enabled": getattr(self.config, "encryption_enabled", False),
            "encryption_type": getattr(self.config, "encryption_type", "none"),
            "encryption_provider": (
                type(self.encryption_provider).__name__ if self.encryption_provider else None
            ),
            "default_ttl": self.config.default_ttl,
            "max_size_mb": self.config.max_size_mb,
        }

        # Add advanced configuration details if available
        if isinstance(self.config, AdvancedCacheConfig):
            config_info.update(
                {
                    "dynamodb_table_name": self.config.dynamodb_table_name,
                    "dynamodb_region": self.config.dynamodb_region,
                    "dynamodb_profile": self.config.dynamodb_profile,
                    "hybrid_local_ttl": self.config.hybrid_local_ttl,
                    "file_cache_dir": self.config.file_cache_dir,
                }
            )

        # Add backend health status if available
        if self.backend and hasattr(self.backend, "health_check"):
            try:
                config_info["backend_healthy"] = self.backend.health_check()
            except Exception as e:
                config_info["backend_healthy"] = False
                config_info["backend_health_error"] = str(e)

        # Add backend statistics if available
        if self.backend and hasattr(self.backend, "get_stats"):
            try:
                config_info["backend_stats"] = self.backend.get_stats()
            except Exception as e:
                config_info["backend_stats_error"] = str(e)

        return config_info

    def get_cache_size_info(self) -> Dict[str, Any]:
        """Get detailed cache size information.

        Returns:
            Dictionary containing cache size statistics and status
        """
        # Use backend stats if available (preferred path)
        if self.backend:
            try:
                backend_stats = self.backend.get_stats()
                # Enhance backend stats with encryption info
                if isinstance(self.config, AdvancedCacheConfig):
                    backend_stats.update(
                        {
                            "backend_type": self.config.backend_type,
                            "encryption_enabled": self.config.encryption_enabled,
                            "encryption_type": (
                                self.config.encryption_type
                                if self.config.encryption_enabled
                                else "none"
                            ),
                        }
                    )
                return backend_stats
            except Exception as e:
                logger.warning(f"Failed to get stats from backend: {e}")

        # Fallback to legacy implementation for backward compatibility
        if self.path_manager:
            return self._get_size_info_legacy()

        # If neither backend nor path_manager is available, return basic info
        return {
            "enabled": self.config.enabled,
            "backend_type": "unknown",
            "error": "No backend or path manager available",
        }

    def _get_size_info_legacy(self) -> Dict[str, Any]:
        """Legacy cache size info implementation for backward compatibility."""
        if self.path_manager is None:
            return {
                "error": "Path manager not available",
                "current_size_bytes": 0,
                "current_size_mb": 0,
                "max_size_bytes": 0,
                "max_size_mb": 0,
                "usage_percentage": 0,
                "is_over_limit": False,
            }

        try:
            current_size_bytes = self.path_manager.get_cache_size()
            max_size_bytes = self.config.max_size_bytes()

            current_size_mb = current_size_bytes / (1024 * 1024)
            usage_percentage = (
                (current_size_bytes / max_size_bytes * 100) if max_size_bytes > 0 else 0
            )

            return {
                "current_size_bytes": current_size_bytes,
                "current_size_mb": round(current_size_mb, 2),
                "max_size_bytes": max_size_bytes,
                "max_size_mb": self.config.max_size_mb,
                "usage_percentage": round(usage_percentage, 1),
                "is_over_limit": current_size_bytes > max_size_bytes,
                "bytes_over_limit": max(0, current_size_bytes - max_size_bytes),
                "available_space_bytes": max(0, max_size_bytes - current_size_bytes),
                "available_space_mb": round(
                    max(0, max_size_bytes - current_size_bytes) / (1024 * 1024), 2
                ),
            }

        except Exception as e:
            logger.error(f"Error getting cache size info: {e}")
            return {
                "error": str(e),
                "current_size_bytes": 0,
                "current_size_mb": 0,
                "max_size_bytes": self.config.max_size_bytes(),
                "max_size_mb": self.config.max_size_mb,
                "usage_percentage": 0,
                "is_over_limit": False,
            }

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary containing cache statistics
        """
        # Use backend stats if available
        if self.backend:
            return self._get_stats_with_backend()
        else:
            # Fallback to legacy stats for backward compatibility
            return self._get_stats_legacy()

    def _get_stats_with_backend(self) -> Dict[str, Any]:
        """Get cache statistics using backend."""
        if self.backend is None:
            return {
                "enabled": self.config.enabled,
                "backend_type": "unknown",
                "error": "Backend not initialized",
            }

        try:
            # Get backend-specific stats
            backend_stats = self.backend.get_stats()

            # Build comprehensive stats
            stats = {
                "enabled": self.config.enabled,
                "backend_type": getattr(self.config, "backend_type", "file"),
                "encryption_enabled": getattr(self.config, "encryption_enabled", False),
                "encryption_type": getattr(self.config, "encryption_type", "none"),
                "default_ttl": self.config.default_ttl,
                "max_size_mb": self.config.max_size_mb,
                **backend_stats,
            }

            # Ensure consistent total_entries field across all backends
            if "total_entries" not in stats:
                # Map backend-specific fields to total_entries
                if "item_count" in stats:
                    # DynamoDB backend uses item_count
                    stats["total_entries"] = stats["item_count"]
                elif "valid_entries" in stats:
                    # File backend uses valid_entries
                    stats["total_entries"] = stats["valid_entries"]
                else:
                    # Fallback to 0 if no entry count available
                    stats["total_entries"] = 0

            # Add encryption provider info if available
            if self.encryption_provider:
                stats["encryption_provider"] = self.encryption_provider.get_encryption_type()
                stats["encryption_available"] = self.encryption_provider.is_available()

            return stats

        except Exception as e:
            logger.error(f"Error getting cache stats with backend: {e}")
            return {
                "enabled": self.config.enabled,
                "backend_type": getattr(self.config, "backend_type", "unknown"),
                "error": str(e),
            }

    def _get_stats_legacy(self) -> Dict[str, Any]:
        """Legacy cache statistics implementation for backward compatibility."""
        if not self.path_manager:
            return {"enabled": self.config.enabled, "error": "Path manager not available"}

        try:
            cache_files = self.path_manager.list_cache_files()
            total_size = self.path_manager.get_cache_size()

            # Count valid vs expired/corrupted entries
            valid_entries = 0
            expired_entries = 0
            corrupted_entries = 0

            for cache_file in cache_files:
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
                "enabled": self.config.enabled,
                "backend_type": "file",
                "encryption_enabled": False,
                "encryption_type": "none",
                "total_entries": len(cache_files),
                "valid_entries": valid_entries,
                "expired_entries": expired_entries,
                "corrupted_entries": corrupted_entries,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "cache_directory": str(self.path_manager.get_cache_directory()),
                "default_ttl": self.config.default_ttl,
                "max_size_mb": self.config.max_size_mb,
            }

            # Add warning if there are corrupted entries
            if corrupted_entries > 0:
                stats["warning"] = f"{corrupted_entries} corrupted cache files detected"

            return stats

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                "enabled": self.config.enabled,
                "backend_type": "file",
                "error": str(e),
                "cache_directory": (
                    str(self.path_manager.get_cache_directory())
                    if hasattr(self, "path_manager") and self.path_manager
                    else "unknown"
                ),
            }

    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about the current backend and encryption setup.

        Returns:
            Dictionary containing backend and encryption information
        """
        info = {
            "config_type": "advanced" if isinstance(self.config, AdvancedCacheConfig) else "basic",
            "enabled": self.config.enabled,
            "using_backend_system": self.backend is not None
            and self.encryption_provider is not None,
        }

        if isinstance(self.config, AdvancedCacheConfig):
            info.update(
                {
                    "backend_type": self.config.backend_type,
                    "encryption_enabled": self.config.encryption_enabled,
                    "encryption_type": self.config.encryption_type,
                }
            )

            # Add backend-specific info
            if self.config.backend_type == "dynamodb":
                info.update(
                    {
                        "dynamodb_table_name": self.config.dynamodb_table_name,
                        "dynamodb_region": self.config.dynamodb_region,
                        "dynamodb_profile": self.config.dynamodb_profile,
                    }
                )
            elif self.config.backend_type == "hybrid":
                info.update(
                    {
                        "hybrid_local_ttl": self.config.hybrid_local_ttl,
                        "dynamodb_table_name": self.config.dynamodb_table_name,
                        "dynamodb_region": self.config.dynamodb_region,
                    }
                )
            elif self.config.backend_type == "file":
                info.update(
                    {
                        "file_cache_dir": self.config.file_cache_dir,
                    }
                )
        else:
            info.update(
                {
                    "backend_type": "file",
                    "encryption_enabled": False,
                    "encryption_type": "none",
                }
            )

        # Add runtime info about actual backend and encryption instances
        if self.backend:
            try:
                info["backend_health"] = self.backend.health_check()
                info["backend_class"] = type(self.backend).__name__
            except Exception as e:
                info["backend_health"] = False
                info["backend_error"] = str(e)
        else:
            info["backend_health"] = None
            info["backend_class"] = None

        if self.encryption_provider:
            try:
                info["encryption_provider_available"] = self.encryption_provider.is_available()
                info["encryption_provider_type"] = self.encryption_provider.get_encryption_type()
                info["encryption_provider_class"] = type(self.encryption_provider).__name__
            except Exception as e:
                info["encryption_provider_available"] = False
                info["encryption_provider_error"] = str(e)
        else:
            info["encryption_provider_available"] = None
            info["encryption_provider_type"] = None
            info["encryption_provider_class"] = None

        return info

    def get_backend(self) -> Optional[CacheBackend]:
        """Get the current cache backend instance.

        Returns:
            CacheBackend instance if available, None otherwise
        """
        return self.backend

    def get_encryption_provider(self) -> Optional[Any]:
        """Get the current encryption provider instance.

        Returns:
            Encryption provider instance if available, None otherwise
        """
        return self.encryption_provider

    def get_recent_entries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent cache entries with metadata.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of dictionaries containing entry metadata
        """
        entries = []

        try:
            # Try to get entries from backend if available
            if self.backend and hasattr(self.backend, "get_recent_entries"):
                entries = self.backend.get_recent_entries(limit)
            elif self.path_manager:
                # Fallback to legacy file-based approach
                cache_dir = self.path_manager.get_cache_directory()
                if cache_dir.exists():
                    # Look for .json files since that's what CachePathManager creates
                    cache_files = list(cache_dir.glob("*.json"))
                    # Sort by modification time (newest first)
                    cache_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

                    for cache_file in cache_files[:limit]:
                        try:
                            # Read cache entry metadata
                            entry_data = self._read_cache_entry_metadata(cache_file)
                            if entry_data:
                                entries.append(entry_data)
                        except Exception as e:
                            logger.debug(f"Error reading cache entry {cache_file}: {e}")
                            continue
        except Exception as e:
            logger.warning(f"Error getting recent entries: {e}")

        return entries

    def _read_cache_entry_metadata(self, cache_file: Path) -> Optional[Dict[str, Any]]:
        """Read metadata from a cache file without loading the full content.

        Args:
            cache_file: Path to the cache file

        Returns:
            Dictionary containing entry metadata or None if error
        """
        try:
            # Get basic file info
            stat = cache_file.stat()
            # Extract key from filename (remove .json extension)
            key = cache_file.stem

            # Try to read the cache entry JSON to get TTL and other metadata
            try:
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

                return {
                    "key": key,
                    "operation": operation,
                    "ttl": ttl_display,
                    "age": age_display,
                    "size": f"{stat.st_size} bytes",
                    "modified": stat.st_mtime,
                    "file_size": stat.st_size,
                    "is_expired": remaining_ttl <= 0,
                }

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                # If we can't read the JSON, return basic file info
                logger.debug(f"Could not read cache entry metadata from {cache_file}: {e}")
                pass

            # Fallback to basic file metadata
            return {
                "key": key,
                "operation": "unknown",
                "ttl": "Unknown",
                "age": "Unknown",
                "size": f"{stat.st_size} bytes",
                "modified": stat.st_mtime,
                "file_size": stat.st_size,
                "is_expired": False,
            }

        except Exception as e:
            logger.debug(f"Error reading cache entry metadata from {cache_file}: {e}")
            return None

    def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the cache system.

        Returns:
            Dictionary containing health check results
        """
        health = {"enabled": self.config.enabled, "overall_healthy": True, "checks": {}}

        if not self.config.enabled:
            health["checks"]["cache_disabled"] = {"status": "info", "message": "Cache is disabled"}
            return health

        # Check backend health
        if self.backend:
            try:
                backend_healthy = self.backend.health_check()
                health["checks"]["backend"] = {
                    "status": "pass" if backend_healthy else "fail",
                    "message": (
                        "Backend is healthy" if backend_healthy else "Backend health check failed"
                    ),
                }
                if not backend_healthy:
                    health["overall_healthy"] = False
            except Exception as e:
                health["checks"]["backend"] = {
                    "status": "fail",
                    "message": f"Backend health check error: {e}",
                }
                health["overall_healthy"] = False
        else:
            health["checks"]["backend"] = {"status": "fail", "message": "No backend available"}
            health["overall_healthy"] = False

        # Check encryption provider
        if self.encryption_provider:
            try:
                encryption_available = self.encryption_provider.is_available()
                health["checks"]["encryption"] = {
                    "status": "pass" if encryption_available else "fail",
                    "message": (
                        "Encryption provider is available"
                        if encryption_available
                        else "Encryption provider not available"
                    ),
                }
                if not encryption_available:
                    health["overall_healthy"] = False
            except Exception as e:
                health["checks"]["encryption"] = {
                    "status": "fail",
                    "message": f"Encryption provider check error: {e}",
                }
                health["overall_healthy"] = False
        else:
            health["checks"]["encryption"] = {
                "status": "info",
                "message": "No encryption provider (using no encryption)",
            }

        return health

    def _load_cache_config_standard(self) -> CacheConfig:
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
                operation_ttls=cache_config_dict.get("operation_ttl", {}),
                max_size_mb=cache_config_dict.get("max_size_mb", 100),
            )

            logger.debug(
                f"Loaded cache configuration: enabled={cache_config.enabled}, "
                f"default_ttl={cache_config.default_ttl}, "
                f"operation_ttls={len(cache_config.operation_ttls)} operations"
            )

            return cache_config

        except Exception as e:
            logger.warning(f"Failed to load cache configuration, using defaults: {e}")
            # Return default configuration if loading fails
            return CacheConfig()
