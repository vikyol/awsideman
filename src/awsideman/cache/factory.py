"""Backend factory for creating cache backend instances."""

import logging

from .backends.base import CacheBackend, CacheBackendError
from .backends.file import FileBackend
from .config import AdvancedCacheConfig

logger = logging.getLogger(__name__)


class BackendFactory:
    """
    Factory class for creating cache backend instances.

    Provides a centralized way to create appropriate backend instances
    based on configuration settings with proper error handling and fallbacks.
    """

    @staticmethod
    def create_backend(config: AdvancedCacheConfig) -> CacheBackend:
        """
        Create a cache backend instance based on configuration.

        Args:
            config: Advanced cache configuration

        Returns:
            CacheBackend instance

        Raises:
            CacheBackendError: If backend creation fails and no fallback is available
        """
        backend_type = config.backend_type.lower()

        try:
            if backend_type == "file":
                return BackendFactory._create_file_backend(config)
            elif backend_type == "dynamodb":
                return BackendFactory._create_dynamodb_backend(config)
            elif backend_type == "hybrid":
                return BackendFactory._create_hybrid_backend(config)
            else:
                logger.error(f"Unknown backend type: {backend_type}")
                raise CacheBackendError(f"Unknown backend type: {backend_type}")

        except CacheBackendError:
            # Re-raise cache backend errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating {backend_type} backend: {e}")
            raise CacheBackendError(
                f"Failed to create {backend_type} backend: {e}",
                backend_type=backend_type,
                original_error=e,
            )

    @staticmethod
    def create_backend_with_fallback(config: AdvancedCacheConfig) -> CacheBackend:
        """
        Create a cache backend instance with automatic fallback to file backend.

        Args:
            config: Advanced cache configuration

        Returns:
            CacheBackend instance (falls back to file backend if primary fails)
        """
        primary_backend = config.backend_type.lower()

        try:
            return BackendFactory.create_backend(config)
        except CacheBackendError as e:
            logger.warning(f"Failed to create {primary_backend} backend: {e}")

            # If primary backend is not file, try to fallback to file backend
            if primary_backend != "file":
                logger.info("Falling back to file backend")
                try:
                    fallback_config = AdvancedCacheConfig(
                        enabled=config.enabled,
                        default_ttl=config.default_ttl,
                        operation_ttls=config.operation_ttls,
                        max_size_mb=config.max_size_mb,
                        backend_type="file",
                        file_cache_dir=config.file_cache_dir,
                    )
                    return BackendFactory._create_file_backend(fallback_config)
                except Exception as fallback_error:
                    logger.error(f"Fallback to file backend also failed: {fallback_error}")
                    raise CacheBackendError(
                        f"Both {primary_backend} backend and file backend fallback failed",
                        backend_type="fallback",
                        original_error=fallback_error,
                    )
            else:
                # Primary backend was file and it failed, no fallback available
                raise

    @staticmethod
    def _create_file_backend(config: AdvancedCacheConfig) -> FileBackend:
        """
        Create a file backend instance.

        Args:
            config: Advanced cache configuration

        Returns:
            FileBackend instance

        Raises:
            CacheBackendError: If file backend creation fails
        """
        try:
            logger.debug(f"Creating file backend with cache_dir: {config.file_cache_dir}")
            return FileBackend(cache_dir=config.file_cache_dir)
        except Exception as e:
            logger.error(f"Failed to create file backend: {e}")
            raise CacheBackendError(
                f"Failed to create file backend: {e}", backend_type="file", original_error=e
            )

    @staticmethod
    def _create_dynamodb_backend(config: AdvancedCacheConfig) -> CacheBackend:
        """
        Create a DynamoDB backend instance.

        Args:
            config: Advanced cache configuration

        Returns:
            DynamoDB backend instance

        Raises:
            CacheBackendError: If DynamoDB backend creation fails
        """
        try:
            # Import DynamoDB backend here to avoid import errors if boto3 is not available
            from .backends.dynamodb import DynamoDBBackend

            logger.debug(
                f"Creating DynamoDB backend with table: {config.dynamodb_table_name}, "
                f"region: {config.dynamodb_region}, profile: {config.dynamodb_profile}"
            )

            return DynamoDBBackend(
                table_name=config.dynamodb_table_name,
                region=config.dynamodb_region,
                profile=config.dynamodb_profile,
            )
        except ImportError as e:
            logger.error(f"DynamoDB backend requires boto3: {e}")
            raise CacheBackendError(
                f"DynamoDB backend requires boto3 to be installed: {e}",
                backend_type="dynamodb",
                original_error=e,
            )
        except Exception as e:
            logger.error(f"Failed to create DynamoDB backend: {e}")
            raise CacheBackendError(
                f"Failed to create DynamoDB backend: {e}", backend_type="dynamodb", original_error=e
            )

    @staticmethod
    def _create_hybrid_backend(config: AdvancedCacheConfig) -> CacheBackend:
        """
        Create a hybrid backend instance.

        Args:
            config: Advanced cache configuration

        Returns:
            Hybrid backend instance

        Raises:
            CacheBackendError: If hybrid backend creation fails
        """
        try:
            # Import hybrid backend here to avoid circular imports
            from .backends.hybrid import HybridBackend

            logger.debug(f"Creating hybrid backend with local_ttl: {config.hybrid_local_ttl}")

            # Create file backend for local cache
            file_backend = BackendFactory._create_file_backend(config)

            # Create DynamoDB backend for remote cache
            dynamodb_backend = BackendFactory._create_dynamodb_backend(config)

            return HybridBackend(
                local_backend=file_backend,
                remote_backend=dynamodb_backend,
                local_ttl=config.hybrid_local_ttl,
            )
        except ImportError as e:
            logger.error(f"Hybrid backend requires additional dependencies: {e}")
            raise CacheBackendError(
                f"Hybrid backend requires additional dependencies: {e}",
                backend_type="hybrid",
                original_error=e,
            )
        except CacheBackendError:
            # Re-raise cache backend errors from sub-backend creation
            raise
        except Exception as e:
            logger.error(f"Failed to create hybrid backend: {e}")
            raise CacheBackendError(
                f"Failed to create hybrid backend: {e}", backend_type="hybrid", original_error=e
            )

    @staticmethod
    def get_available_backends() -> list[str]:
        """
        Get list of available backend types.

        Returns:
            List of available backend type names
        """
        available = ["file"]  # File backend is always available

        # Check if DynamoDB backend is available
        try:
            import boto3  # noqa: F401

            available.append("dynamodb")
            available.append("hybrid")  # Hybrid requires DynamoDB
        except ImportError:
            logger.debug("DynamoDB backend not available (boto3 not installed)")

        return available

    @staticmethod
    def validate_backend_availability(backend_type: str) -> bool:
        """
        Check if a specific backend type is available.

        Args:
            backend_type: Backend type to check

        Returns:
            True if backend is available, False otherwise
        """
        available_backends = BackendFactory.get_available_backends()
        return backend_type.lower() in available_backends

    @staticmethod
    def get_backend_info(backend_type: str) -> dict:
        """
        Get information about a specific backend type.

        Args:
            backend_type: Backend type to get info for

        Returns:
            Dictionary with backend information
        """
        backend_info = {
            "file": {
                "name": "File Backend",
                "description": "Local file-based cache storage",
                "requirements": [],
                "features": ["Local storage", "Fast access", "No network dependency"],
            },
            "dynamodb": {
                "name": "DynamoDB Backend",
                "description": "AWS DynamoDB-based cache storage",
                "requirements": ["boto3"],
                "features": ["Shared cache", "Scalable", "TTL support", "Cross-machine access"],
            },
            "hybrid": {
                "name": "Hybrid Backend",
                "description": "Combination of local file and DynamoDB storage",
                "requirements": ["boto3"],
                "features": ["Local caching", "Remote sharing", "Best of both worlds"],
            },
        }

        info = backend_info.get(
            backend_type.lower(),
            {
                "name": "Unknown Backend",
                "description": "Unknown backend type",
                "requirements": [],
                "features": [],
            },
        )

        # Add availability status
        info["available"] = BackendFactory.validate_backend_availability(backend_type)

        return info
