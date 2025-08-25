"""Cache management and storage backends.

This package provides comprehensive caching functionality including:
- Cache management and coordination
- Multiple storage backend implementations
- Cache-specific utilities and configurations
- AWS client caching integration
"""

# AWS client caching
from .aws_client import (
    CachedAWSClient,
    CachedIdentityCenterClient,
    CachedIdentityStoreClient,
    CachedOrganizationsClient,
    create_cached_client,
)

# Backend implementations
from .backends.base import CacheBackend
from .backends.dynamodb import DynamoDBBackend
from .backends.file import FileBackend
from .backends.hybrid import HybridBackend
from .config import AdvancedCacheConfig

# Error handling and circuit breaker
from .errors import (
    CacheBackendError,
    CacheConfigurationError,
    CacheError,
    CacheInvalidationError,
    CacheKeyError,
    CacheSerializationError,
    CircuitBreaker,
    CircuitBreakerState,
    GracefulDegradationMixin,
    handle_cache_error,
)
from .factory import BackendFactory
from .interfaces import ICacheManager

# Cache invalidation
from .invalidation import (
    CacheInvalidationEngine,
    invalidate_assignment_cache,
    invalidate_group_cache,
    invalidate_permission_set_cache,
    invalidate_user_cache,
)

# Cache key generation
from .key_builder import (
    CacheKeyBuilder,
    CacheKeyValidationError,
    assignment_list_key,
    group_describe_key,
    group_list_key,
    group_members_key,
    permission_set_list_key,
    user_describe_key,
    user_list_key,
)

# Core cache management
from .manager import CacheManager
from .utils import CachePathManager

# Cache models and metrics - removed legacy models


__all__ = [
    # Core components
    "CacheManager",  # Primary cache manager (singleton)
    "ICacheManager",
    "CachePathManager",
    "BackendFactory",
    "AdvancedCacheConfig",
    # Cache key generation
    "CacheKeyBuilder",
    "CacheKeyValidationError",
    "user_list_key",
    "user_describe_key",
    "group_list_key",
    "group_describe_key",
    "group_members_key",
    "permission_set_list_key",
    "assignment_list_key",
    # Cache invalidation
    "CacheInvalidationEngine",
    "invalidate_user_cache",
    "invalidate_group_cache",
    "invalidate_permission_set_cache",
    "invalidate_assignment_cache",
    # Cache models and metrics - removed legacy models
    # Error handling and circuit breaker
    "CacheError",
    "CacheBackendError",
    "CacheInvalidationError",
    "CacheSerializationError",
    "CacheKeyError",
    "CacheConfigurationError",
    "CircuitBreaker",
    "CircuitBreakerState",
    "GracefulDegradationMixin",
    "handle_cache_error",
    # AWS client caching
    "CachedAWSClient",
    "CachedIdentityCenterClient",
    "CachedIdentityStoreClient",
    "CachedOrganizationsClient",
    "create_cached_client",
    # Backend interface and implementations
    "CacheBackend",
    "FileBackend",
    "DynamoDBBackend",
    "HybridBackend",
]

__version__ = "1.0.0"
