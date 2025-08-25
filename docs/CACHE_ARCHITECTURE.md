# Cache Manager Architecture Documentation

## Overview

The awsideman cache system has been refactored from multiple, inconsistent cache managers to a single, unified cache manager that provides predictable behavior across all commands. This document explains the architecture, design decisions, and implementation details of the new cache system.

## Architecture Principles

### Single Source of Truth
- **One Cache Manager**: All components use the same singleton cache manager instance
- **Consistent Behavior**: Cache operations behave identically across all commands
- **Thread Safety**: The cache manager is thread-safe for concurrent access

### Automatic Cache Management
- **Transparent Caching**: Users don't need to understand caching internals
- **Smart Invalidation**: Write operations automatically invalidate relevant cache entries
- **Graceful Degradation**: Cache failures fall back to direct AWS API calls

## Core Components

### 1. Cache Manager Singleton

The `CacheManager` class implements the singleton pattern to ensure system-wide consistency:

```python
from awsideman.cache.manager import CacheManager

# Get the singleton instance
cache_manager = CacheManager()

# All parts of the system get the same instance
assert CacheManager() is cache_manager  # True
```

**Key Features:**
- Thread-safe initialization using double-checked locking
- Configurable storage backends (memory, disk)
- Built-in error handling and circuit breaker pattern
- Comprehensive statistics and monitoring

### 2. Cache Storage Backends

The system supports multiple storage backends:

#### Memory Backend (Default)
- Fast in-memory storage using Python dictionaries
- LRU eviction when memory limits are reached
- Configurable TTL (Time To Live) support
- Best for development and testing

#### Disk Backend
- Persistent storage using pickle serialization
- Survives application restarts
- Configurable cache directory
- Best for production environments

```python
# Configure storage backend
cache_manager = CacheManager()
cache_manager.configure_storage(
    backend_type="disk",
    config={
        "cache_dir": "/tmp/awsideman_cache",
        "max_size_mb": 100
    }
)
```

### 3. Cache Key System

Cache keys follow a hierarchical structure that enables targeted invalidation:

```
{resource_type}:{operation}:{identifier}:{sub_identifier}
```

**Examples:**
- `user:list:all` - List all users
- `user:describe:user-123` - Describe specific user
- `group:list:all` - List all groups
- `group:members:group-456` - List group members
- `permission_set:list:all` - List permission sets
- `assignment:list:account-789:permission-set-123` - List assignments

### 4. Cache Invalidation Engine

The invalidation engine automatically determines which cache entries to invalidate based on operations:

```python
from awsideman.cache.invalidation import CacheInvalidationEngine

# Automatic invalidation on write operations
def update_user(user_id: str, **kwargs):
    result = aws_client.update_user(UserId=user_id, **kwargs)

    # This automatically invalidates:
    # - user:list:*
    # - user:describe:user-123
    # - group:members:* (if user is in groups)
    invalidation_engine.invalidate_for_operation("update", "user", user_id)

    return result
```

## Integration with AWS Clients

### Cached AWS Client Wrapper

The `CachedAWSClient` class wraps boto3 clients to provide transparent caching:

```python
from awsideman.cache.aws_client import CachedAWSClient

# Wrap any boto3 client
identity_center_client = boto3.client('identitystore')
cached_client = CachedAWSClient(identity_center_client, cache_manager)

# Read operations are automatically cached
users = cached_client.list_users(IdentityStoreId=store_id)

# Write operations automatically invalidate cache
cached_client.update_user(
    IdentityStoreId=store_id,
    UserId=user_id,
    Operations=[...]
)
```

### Automatic Cache Management

The system automatically handles caching for:

**Read Operations (Cached):**
- `list_*` - All list operations
- `describe_*` - All describe operations
- `get_*` - All get operations

**Write Operations (Invalidate Cache):**
- `create_*` - Create operations
- `update_*` - Update operations
- `delete_*` - Delete operations
- `put_*` - Put operations

## Error Handling and Resilience

### Circuit Breaker Pattern

The cache manager implements a circuit breaker to handle backend failures:

```python
# Circuit breaker configuration
circuit_breaker = CircuitBreaker(
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=60,      # Try again after 60 seconds
    expected_exception=CacheBackendError
)
```

**States:**
- **Closed**: Normal operation, cache requests go through
- **Open**: Cache is bypassed, direct AWS API calls only
- **Half-Open**: Testing if cache backend has recovered

### Graceful Degradation

When cache operations fail:
1. Log the error for debugging
2. Continue with direct AWS API call
3. Return result to user (no interruption)
4. Increment circuit breaker failure count

```python
def get(self, key: str) -> Optional[Any]:
    try:
        return self._storage.get(key)
    except CacheBackendError as e:
        logger.warning(f"Cache get failed for key {key}: {e}")
        return None  # Graceful degradation
```

## Performance Characteristics

### Cache Hit Performance
- **Memory Backend**: < 1ms for cache hits
- **Disk Backend**: < 10ms for cache hits
- **Network Savings**: 100-500ms saved per AWS API call

### Cache Invalidation Performance
- **Pattern Matching**: < 100ms for wildcard invalidation
- **Targeted Invalidation**: < 10ms for specific keys
- **Cross-Resource Rules**: < 50ms for complex invalidation

### Memory Usage
- **Configurable Limits**: Set maximum cache size
- **LRU Eviction**: Automatic cleanup of old entries
- **Compression**: Optional compression for large entries

## Configuration Options

### Environment Variables

```bash
# Cache backend type
export AWSIDEMAN_CACHE_BACKEND=memory  # or 'disk'

# Cache directory (disk backend only)
export AWSIDEMAN_CACHE_DIR=/tmp/awsideman_cache

# Cache size limits
export AWSIDEMAN_CACHE_MAX_SIZE_MB=100

# Cache TTL (in seconds)
export AWSIDEMAN_CACHE_DEFAULT_TTL=900  # 15 minutes

# Disable caching (emergency use)
export AWSIDEMAN_CACHE_DISABLED=false
```

### Programmatic Configuration

```python
from awsideman.cache.manager import CacheManager
from datetime import timedelta

cache_manager = CacheManager()

# Configure storage backend
cache_manager.configure_storage(
    backend_type="disk",
    config={
        "cache_dir": "/var/cache/awsideman",
        "max_size_mb": 500,
        "compression": True
    }
)

# Configure default TTL
cache_manager.set_default_ttl(timedelta(minutes=30))

# Configure circuit breaker
cache_manager.configure_circuit_breaker(
    failure_threshold=10,
    recovery_timeout=120
)
```

## Monitoring and Statistics

### Cache Statistics

```python
# Get cache statistics
stats = cache_manager.get_stats()

print(f"Hit Rate: {stats.hit_rate_percentage:.1f}%")
print(f"Total Entries: {stats.total_entries}")
print(f"Memory Usage: {stats.memory_usage_bytes / 1024 / 1024:.1f} MB")
```

### CLI Status Command

```bash
# View cache status
awsideman cache status

# View detailed statistics
awsideman cache status --detailed

# View recent cache activity
awsideman cache status --recent-entries 20
```

## Migration from Legacy Cache

### Backward Compatibility

The new cache system maintains backward compatibility:

```python
# Legacy code continues to work
from awsideman.utils.cache import get_cache_manager

# This now returns the singleton instance
legacy_cache = get_cache_manager()
assert legacy_cache is CacheManager()  # True
```

### Feature Flags

During migration, feature flags control cache behavior:

```python
# Environment variable controls
USE_UNIFIED_CACHE = os.getenv("AWSIDEMAN_USE_UNIFIED_CACHE", "true")

if USE_UNIFIED_CACHE.lower() == "true":
    cache_manager = CacheManager()  # New unified cache
else:
    cache_manager = LegacyCacheManager()  # Old behavior
```

## Thread Safety

The cache manager is fully thread-safe:

```python
import threading
from awsideman.cache.manager import CacheManager

def worker_function():
    cache_manager = CacheManager()
    # Safe to use from multiple threads
    cache_manager.set("thread_key", "thread_data")
    data = cache_manager.get("thread_key")

# Create multiple threads
threads = []
for i in range(10):
    thread = threading.Thread(target=worker_function)
    threads.append(thread)
    thread.start()

# All threads use the same cache manager instance
for thread in threads:
    thread.join()
```

## Best Practices

### For Command Developers

1. **Use CachedAWSClient**: Always wrap boto3 clients with CachedAWSClient
2. **Let Invalidation Handle Itself**: Don't manually invalidate cache unless necessary
3. **Handle Cache Misses**: Always handle None returns from cache.get()
4. **Use Appropriate TTL**: Set TTL based on data volatility

### For System Administrators

1. **Monitor Hit Rates**: Aim for >80% cache hit rate
2. **Configure Storage**: Use disk backend for production
3. **Set Appropriate Limits**: Configure cache size based on available memory
4. **Monitor Errors**: Watch for cache backend errors in logs

### For Troubleshooting

1. **Check Cache Status**: Use `awsideman cache status` for diagnostics
2. **Clear Cache**: Use `awsideman cache clear` if data seems stale
3. **Disable Caching**: Set `AWSIDEMAN_CACHE_DISABLED=true` for debugging
4. **Check Logs**: Look for cache-related errors in application logs

## Future Enhancements

### Planned Features

1. **Distributed Caching**: Redis backend for multi-instance deployments
2. **Cache Warming**: Pre-populate cache with frequently accessed data
3. **Advanced Metrics**: Detailed performance metrics and alerting
4. **Cache Compression**: Automatic compression for large cache entries
5. **Cache Partitioning**: Separate cache namespaces for different AWS accounts

### Extension Points

The cache system is designed for extensibility:

```python
# Custom storage backend
class CustomCacheBackend(CacheStorage):
    def get(self, key: str) -> Optional[Any]:
        # Custom implementation
        pass

    def set(self, key: str, data: Any, ttl: Optional[timedelta] = None) -> None:
        # Custom implementation
        pass

# Register custom backend
cache_manager.register_backend("custom", CustomCacheBackend)
```

This architecture provides a solid foundation for reliable, performant caching while maintaining simplicity for developers and users.
