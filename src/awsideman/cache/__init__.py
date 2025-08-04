"""Cache management and storage backends.

This package provides comprehensive caching functionality including:
- Cache management and coordination
- Multiple storage backend implementations
- Cache-specific utilities and configurations
- AWS client caching integration
"""

# Core cache management
from .manager import CacheManager
from .utils import CachePathManager
from .factory import BackendFactory
from .config import AdvancedCacheConfig

# Backend implementations
from .backends.base import CacheBackend, CacheBackendError
from .backends.file import FileBackend
from .backends.dynamodb import DynamoDBBackend
from .backends.hybrid import HybridBackend

__all__ = [
    # Core components
    'CacheManager',
    'CachePathManager', 
    'BackendFactory',
    'AdvancedCacheConfig',
    
    # Backend interface and implementations
    'CacheBackend',
    'CacheBackendError',
    'FileBackend',
    'DynamoDBBackend', 
    'HybridBackend',
]

__version__ = '1.0.0'