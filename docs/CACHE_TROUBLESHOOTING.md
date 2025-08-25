# Cache Troubleshooting Guide

This guide helps diagnose and resolve cache-related issues in awsideman. It covers common problems, diagnostic steps, and solutions.

## Quick Diagnostic Commands

### Check Cache Status
```bash
# Basic cache status
awsideman cache status

# Detailed statistics
awsideman cache status --detailed

# Recent cache activity
awsideman cache status --recent-entries 20
```

### Emergency Cache Operations
```bash
# Clear entire cache
awsideman cache clear

# Bypass cache for specific command
awsideman user list --no-cache

# Disable caching temporarily
export AWSIDEMAN_CACHE_DISABLED=true
awsideman user list
```

## Common Issues and Solutions

### 1. Stale Data Issues

**Symptoms:**
- Commands show outdated information
- Recent changes not reflected in list operations
- Inconsistent data between different commands

**Diagnostic Steps:**
```bash
# Check if data is fresh with --no-cache
awsideman user list --no-cache

# Compare with cached version
awsideman user list

# Check cache statistics for hit rates
awsideman cache status --detailed
```

**Solutions:**

#### Solution 1: Clear Specific Cache Entries
```bash
# Clear user-related cache
awsideman cache clear --pattern "user:*"

# Clear group-related cache
awsideman cache clear --pattern "group:*"

# Clear all list operations
awsideman cache clear --pattern "*:list:*"
```

#### Solution 2: Check Invalidation Rules
```python
# Verify invalidation is working
from awsideman.cache.manager import CacheManager
from awsideman.cache.invalidation import CacheInvalidationEngine

cache_manager = CacheManager()
invalidation_engine = CacheInvalidationEngine(cache_manager)

# Test invalidation
count = invalidation_engine.invalidate_for_operation("update", "user", "user-123")
print(f"Invalidated {count} entries")
```

#### Solution 3: Reduce TTL for Volatile Data
```python
# Configure shorter TTL for frequently changing data
cache_manager = CacheManager()
cache_manager.set_default_ttl(timedelta(minutes=5))  # Reduce from 15 minutes
```

### 2. Cache Performance Issues

**Symptoms:**
- Slow command execution
- High memory usage
- Frequent cache misses

**Diagnostic Steps:**
```bash
# Check cache hit rates
awsideman cache status

# Monitor memory usage
awsideman cache status --memory-details

# Check for cache backend errors
grep "CacheError" /var/log/awsideman.log
```

**Solutions:**

#### Solution 1: Optimize Cache Configuration
```bash
# Configure memory limits
export AWSIDEMAN_CACHE_MAX_SIZE_MB=200

# Enable compression for large entries
export AWSIDEMAN_CACHE_COMPRESSION=true

# Use disk backend for persistence
export AWSIDEMAN_CACHE_BACKEND=disk
export AWSIDEMAN_CACHE_DIR=/var/cache/awsideman
```

#### Solution 2: Tune TTL Values
```python
# Configure TTL based on data volatility
ttl_config = {
    "user:list": timedelta(minutes=10),
    "user:describe": timedelta(minutes=30),
    "group:members": timedelta(minutes=5),
    "permission_set:list": timedelta(hours=2)
}
```

#### Solution 3: Monitor and Alert
```python
# Set up cache monitoring
def monitor_cache_health():
    cache_manager = CacheManager()
    stats = cache_manager.get_stats()

    if stats.hit_rate_percentage < 70:
        logger.warning(f"Low cache hit rate: {stats.hit_rate_percentage:.1f}%")

    if stats.memory_usage_bytes > 100 * 1024 * 1024:  # 100MB
        logger.warning(f"High memory usage: {stats.memory_usage_bytes / 1024 / 1024:.1f}MB")
```

### 3. Cache Backend Errors

**Symptoms:**
- "CacheBackendError" in logs
- Intermittent cache failures
- Cache operations timing out

**Diagnostic Steps:**
```bash
# Check cache backend health
awsideman cache health

# Test cache operations
awsideman cache test

# Check filesystem permissions (disk backend)
ls -la /var/cache/awsideman/

# Check available disk space
df -h /var/cache/awsideman/
```

**Solutions:**

#### Solution 1: Fix Filesystem Issues
```bash
# Create cache directory with proper permissions
sudo mkdir -p /var/cache/awsideman
sudo chown $(whoami):$(whoami) /var/cache/awsideman
sudo chmod 755 /var/cache/awsideman

# Clean up corrupted cache files
rm -rf /var/cache/awsideman/*
```

#### Solution 2: Switch to Memory Backend
```bash
# Temporarily use memory backend
export AWSIDEMAN_CACHE_BACKEND=memory
awsideman user list
```

#### Solution 3: Configure Circuit Breaker
```python
# Adjust circuit breaker settings
cache_manager = CacheManager()
cache_manager.configure_circuit_breaker(
    failure_threshold=10,    # Allow more failures before opening
    recovery_timeout=30      # Shorter recovery time
)
```

### 4. Thread Safety Issues

**Symptoms:**
- Inconsistent cache behavior in multi-threaded environments
- Race conditions during cache operations
- Deadlocks or hanging operations

**Diagnostic Steps:**
```python
# Test thread safety
import threading
from awsideman.cache.manager import CacheManager

def test_thread_safety():
    def worker():
        cache_manager = CacheManager()
        for i in range(100):
            cache_manager.set(f"thread_key_{i}", f"data_{i}")
            data = cache_manager.get(f"thread_key_{i}")
            assert data == f"data_{i}"

    threads = []
    for _ in range(10):
        thread = threading.Thread(target=worker)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    print("Thread safety test passed")
```

**Solutions:**

#### Solution 1: Verify Singleton Behavior
```python
# Ensure all threads use the same instance
def verify_singleton():
    instances = []

    def get_instance():
        instances.append(CacheManager())

    threads = []
    for _ in range(10):
        thread = threading.Thread(target=get_instance)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # All instances should be the same
    assert all(instance is instances[0] for instance in instances)
```

#### Solution 2: Use Thread-Safe Operations
```python
# Use atomic operations where possible
cache_manager = CacheManager()

# Thread-safe increment
def safe_increment(key: str):
    with cache_manager._lock:  # Use internal lock if available
        current = cache_manager.get(key) or 0
        cache_manager.set(key, current + 1)
```

### 5. Memory Leaks

**Symptoms:**
- Continuously increasing memory usage
- Cache never evicts old entries
- System running out of memory

**Diagnostic Steps:**
```bash
# Monitor memory usage over time
while true; do
    awsideman cache status --memory-details
    sleep 60
done

# Check for memory leaks in Python
pip install memory-profiler
python -m memory_profiler your_script.py
```

**Solutions:**

#### Solution 1: Configure LRU Eviction
```python
# Enable LRU eviction
cache_manager = CacheManager()
cache_manager.configure_storage(
    backend_type="memory",
    config={
        "max_entries": 1000,      # Limit number of entries
        "eviction_policy": "lru"  # Use LRU eviction
    }
)
```

#### Solution 2: Set Memory Limits
```bash
# Configure memory limits
export AWSIDEMAN_CACHE_MAX_SIZE_MB=100

# Monitor and enforce limits
awsideman cache status --enforce-limits
```

#### Solution 3: Periodic Cache Cleanup
```python
# Schedule periodic cleanup
import schedule
import time

def cleanup_cache():
    cache_manager = CacheManager()

    # Remove expired entries
    cache_manager.cleanup_expired()

    # Enforce size limits
    cache_manager.enforce_limits()

# Run cleanup every hour
schedule.every().hour.do(cleanup_cache)

while True:
    schedule.run_pending()
    time.sleep(60)
```

## Advanced Troubleshooting

### Debug Cache Key Generation

```python
from awsideman.cache.key_builder import CacheKeyBuilder

# Test cache key generation
key_builder = CacheKeyBuilder()

# Debug key generation
key = key_builder.build_key(
    resource_type="user",
    operation="list",
    identifier="all",
    params={"identity_store_id": "d-1234567890"}
)
print(f"Generated key: {key}")

# Verify key consistency
key1 = key_builder.build_key("user", "list", "all", {"store": "123"})
key2 = key_builder.build_key("user", "list", "all", {"store": "123"})
assert key1 == key2, "Keys should be identical for same parameters"
```

### Debug Invalidation Patterns

```python
from awsideman.cache.invalidation import CacheInvalidationEngine
from awsideman.cache.manager import CacheManager

# Test invalidation patterns
cache_manager = CacheManager()
invalidation_engine = CacheInvalidationEngine(cache_manager)

# Add test data
test_keys = [
    "user:list:all",
    "user:describe:user-123",
    "group:list:all",
    "group:members:group-456"
]

for key in test_keys:
    cache_manager.set(key, f"data_for_{key}")

# Test invalidation
count = invalidation_engine.invalidate_for_operation("update", "user", "user-123")
print(f"Invalidated {count} entries")

# Check remaining keys
for key in test_keys:
    data = cache_manager.get(key)
    print(f"{key}: {'EXISTS' if data else 'INVALIDATED'}")
```

### Monitor Cache Circuit Breaker

```python
from awsideman.cache.manager import CacheManager

def monitor_circuit_breaker():
    cache_manager = CacheManager()
    circuit_breaker = cache_manager._circuit_breaker

    print(f"Circuit Breaker State: {circuit_breaker.state}")
    print(f"Failure Count: {circuit_breaker.failure_count}")
    print(f"Last Failure Time: {circuit_breaker.last_failure_time}")

    if circuit_breaker.state == "OPEN":
        print("WARNING: Circuit breaker is OPEN - cache is disabled")
    elif circuit_breaker.state == "HALF_OPEN":
        print("INFO: Circuit breaker is HALF_OPEN - testing recovery")
```

## Performance Optimization

### Cache Warming Strategies

```python
def warm_cache():
    """Pre-populate cache with frequently accessed data."""

    cache_manager = CacheManager()

    # Warm user cache
    users = fetch_all_users()  # Your implementation
    for user in users:
        key = f"user:describe:{user['UserId']}"
        cache_manager.set(key, user, ttl=timedelta(minutes=30))

    # Warm group cache
    groups = fetch_all_groups()  # Your implementation
    for group in groups:
        key = f"group:describe:{group['GroupId']}"
        cache_manager.set(key, group, ttl=timedelta(hours=1))

    print("Cache warming completed")
```

### Batch Cache Operations

```python
def batch_cache_operations(operations: list):
    """Perform multiple cache operations efficiently."""

    cache_manager = CacheManager()

    # Group operations by type
    gets = [op for op in operations if op['type'] == 'get']
    sets = [op for op in operations if op['type'] == 'set']

    # Batch get operations
    results = {}
    for op in gets:
        results[op['key']] = cache_manager.get(op['key'])

    # Batch set operations
    for op in sets:
        cache_manager.set(op['key'], op['data'], op.get('ttl'))

    return results
```

## Monitoring and Alerting

### Cache Health Checks

```python
def cache_health_check():
    """Comprehensive cache health check."""

    cache_manager = CacheManager()
    stats = cache_manager.get_stats()

    health_status = {
        "healthy": True,
        "issues": []
    }

    # Check hit rate
    if stats.hit_rate_percentage < 50:
        health_status["healthy"] = False
        health_status["issues"].append(f"Low hit rate: {stats.hit_rate_percentage:.1f}%")

    # Check memory usage
    memory_mb = stats.memory_usage_bytes / 1024 / 1024
    if memory_mb > 200:  # 200MB limit
        health_status["healthy"] = False
        health_status["issues"].append(f"High memory usage: {memory_mb:.1f}MB")

    # Check error rate
    total_ops = stats.hit_count + stats.miss_count
    if total_ops > 0:
        error_rate = (stats.error_count / total_ops) * 100
        if error_rate > 5:  # 5% error rate threshold
            health_status["healthy"] = False
            health_status["issues"].append(f"High error rate: {error_rate:.1f}%")

    return health_status
```

### Automated Monitoring Script

```bash
#!/bin/bash
# cache_monitor.sh - Monitor cache health and alert on issues

LOG_FILE="/var/log/awsideman_cache_monitor.log"
ALERT_EMAIL="admin@example.com"

check_cache_health() {
    local output=$(awsideman cache status --json 2>&1)
    local exit_code=$?

    if [ $exit_code -ne 0 ]; then
        echo "$(date): Cache status check failed: $output" >> $LOG_FILE
        return 1
    fi

    # Parse JSON output and check metrics
    local hit_rate=$(echo "$output" | jq -r '.hit_rate_percentage')
    local memory_mb=$(echo "$output" | jq -r '.memory_usage_mb')

    if (( $(echo "$hit_rate < 50" | bc -l) )); then
        echo "$(date): Low cache hit rate: $hit_rate%" >> $LOG_FILE
        return 1
    fi

    if (( $(echo "$memory_mb > 200" | bc -l) )); then
        echo "$(date): High memory usage: ${memory_mb}MB" >> $LOG_FILE
        return 1
    fi

    return 0
}

# Run health check
if ! check_cache_health; then
    # Send alert email
    tail -10 $LOG_FILE | mail -s "awsideman Cache Health Alert" $ALERT_EMAIL
fi
```

## Recovery Procedures

### Cache Corruption Recovery

```bash
#!/bin/bash
# recover_cache.sh - Recover from cache corruption

echo "Starting cache recovery procedure..."

# 1. Stop any running awsideman processes
pkill -f awsideman

# 2. Backup corrupted cache
if [ -d "/var/cache/awsideman" ]; then
    mv /var/cache/awsideman /var/cache/awsideman.corrupted.$(date +%Y%m%d_%H%M%S)
fi

# 3. Create fresh cache directory
mkdir -p /var/cache/awsideman
chown $(whoami):$(whoami) /var/cache/awsideman
chmod 755 /var/cache/awsideman

# 4. Test cache functionality
awsideman cache status

echo "Cache recovery completed"
```

### Emergency Cache Disable

```bash
#!/bin/bash
# emergency_disable_cache.sh - Disable cache in emergency

echo "Disabling cache for emergency operations..."

# Set environment variable to disable cache
export AWSIDEMAN_CACHE_DISABLED=true

# Verify cache is disabled
awsideman cache status

echo "Cache disabled. All operations will bypass cache."
echo "To re-enable: unset AWSIDEMAN_CACHE_DISABLED"
```

This troubleshooting guide provides comprehensive coverage of cache-related issues and their solutions, helping users and administrators maintain a healthy cache system.
