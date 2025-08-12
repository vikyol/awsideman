"""Cache management and storage backends.

This package provides comprehensive caching functionality including:
- Cache management and coordination
- Multiple storage backend implementations
- Cache-specific utilities and configurations
- AWS client caching integration
"""

# Backend implementations
from .backends.base import CacheBackend, CacheBackendError
from .backends.dynamodb import DynamoDBBackend
from .backends.file import FileBackend
from .backends.hybrid import HybridBackend
from .config import AdvancedCacheConfig
from .factory import BackendFactory

# Core cache management
from .manager import CacheManager
from .utils import CachePathManager

__all__ = [
    # Core components
    "CacheManager",
    "CachePathManager",
    "BackendFactory",
    "AdvancedCacheConfig",
    # Backend interface and implementations
    "CacheBackend",
    "CacheBackendError",
    "FileBackend",
    "DynamoDBBackend",
    "HybridBackend",
]

__version__ = "1.0.0"
