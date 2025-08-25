# Cache Manager Usage Examples

This document provides practical examples of how to use the unified cache manager when developing new commands for awsideman.

## Basic Cache Manager Usage

### Getting the Cache Manager Instance

```python
from awsideman.cache.manager import CacheManager

# Get the singleton cache manager instance
cache_manager = CacheManager()

# The same instance is returned everywhere
assert CacheManager() is cache_manager  # Always True
```

### Basic Cache Operations

```python
from datetime import timedelta

# Store data in cache
cache_manager.set("my_key", {"data": "value"}, ttl=timedelta(minutes=15))

# Retrieve data from cache
cached_data = cache_manager.get("my_key")
if cached_data is not None:
    print("Cache hit!")
else:
    print("Cache miss - fetch from AWS")

# Check if key exists
if cache_manager.exists("my_key"):
    print("Key exists in cache")

# Invalidate specific entries
cache_manager.invalidate("user:*")  # Invalidate all user-related entries

# Clear entire cache (emergency use only)
cache_manager.clear()
```

## Integrating with AWS Clients

### Example 1: Simple List Command

```python
from awsideman.cache.aws_client import CachedAWSClient
from awsideman.cache.manager import CacheManager
import boto3

def list_permission_sets(identity_store_id: str, instance_arn: str):
    """List permission sets with automatic caching."""

    # Create cached AWS client
    sso_admin_client = boto3.client('sso-admin')
    cached_client = CachedAWSClient(sso_admin_client, CacheManager())

    # This call is automatically cached
    response = cached_client.list_permission_sets(InstanceArn=instance_arn)

    return response['PermissionSets']
```

### Example 2: Command with Manual Cache Key

```python
from awsideman.cache.key_builder import CacheKeyBuilder
from awsideman.cache.manager import CacheManager
from datetime import timedelta

def get_user_groups(identity_store_id: str, user_id: str):
    """Get groups for a user with manual cache management."""

    cache_manager = CacheManager()
    key_builder = CacheKeyBuilder()

    # Build cache key
    cache_key = key_builder.build_key(
        resource_type="user",
        operation="groups",
        identifier=user_id,
        params={"identity_store_id": identity_store_id}
    )

    # Try cache first
    cached_groups = cache_manager.get(cache_key)
    if cached_groups is not None:
        return cached_groups

    # Fetch from AWS
    identity_client = boto3.client('identitystore')
    paginator = identity_client.get_paginator('list_group_memberships_for_member')

    groups = []
    for page in paginator.paginate(
        IdentityStoreId=identity_store_id,
        MemberId={'UserId': user_id}
    ):
        groups.extend(page['GroupMemberships'])

    # Cache the result
    cache_manager.set(cache_key, groups, ttl=timedelta(minutes=10))

    return groups
```

### Example 3: Write Operation with Invalidation

```python
from awsideman.cache.invalidation import CacheInvalidationEngine
from awsideman.cache.manager import CacheManager

def update_user_email(identity_store_id: str, user_id: str, new_email: str):
    """Update user email and invalidate related cache entries."""

    cache_manager = CacheManager()
    invalidation_engine = CacheInvalidationEngine(cache_manager)

    # Perform the update
    identity_client = boto3.client('identitystore')
    response = identity_client.update_user(
        IdentityStoreId=identity_store_id,
        UserId=user_id,
        Operations=[
            {
                'AttributePath': 'emails[primary eq true].value',
                'AttributeValue': new_email
            }
        ]
    )

    # Automatically invalidate related cache entries
    invalidation_engine.invalidate_for_operation("update", "user", user_id)

    return response
```

## Command Implementation Examples

### Example 1: User List Command

```python
import click
from awsideman.cache.aws_client import CachedAWSClient
from awsideman.cache.manager import CacheManager
from awsideman.utils.aws import get_identity_store_client

@click.command()
@click.option('--identity-store-id', required=True, help='Identity Store ID')
@click.option('--no-cache', is_flag=True, help='Bypass cache (debugging only)')
def list_users(identity_store_id: str, no_cache: bool):
    """List all users in the identity store."""

    if no_cache:
        # Direct AWS call for debugging
        client = get_identity_store_client()
        response = client.list_users(IdentityStoreId=identity_store_id)
    else:
        # Use cached client (normal operation)
        client = get_identity_store_client()
        cached_client = CachedAWSClient(client, CacheManager())
        response = cached_client.list_users(IdentityStoreId=identity_store_id)

    # Display results
    for user in response['Users']:
        click.echo(f"User: {user['UserName']} ({user['UserId']})")
```

### Example 2: Group Create Command

```python
import click
from awsideman.cache.invalidation import CacheInvalidationEngine
from awsideman.cache.manager import CacheManager
from awsideman.utils.aws import get_identity_store_client

@click.command()
@click.option('--identity-store-id', required=True, help='Identity Store ID')
@click.option('--group-name', required=True, help='Group name')
@click.option('--description', help='Group description')
def create_group(identity_store_id: str, group_name: str, description: str):
    """Create a new group."""

    client = get_identity_store_client()

    # Create the group
    response = client.create_group(
        IdentityStoreId=identity_store_id,
        DisplayName=group_name,
        Description=description or ""
    )

    # Invalidate group list cache
    cache_manager = CacheManager()
    invalidation_engine = CacheInvalidationEngine(cache_manager)
    invalidation_engine.invalidate_for_operation("create", "group", response['GroupId'])

    click.echo(f"Created group: {group_name} ({response['GroupId']})")
```

### Example 3: Complex Command with Multiple Resources

```python
import click
from awsideman.cache.aws_client import CachedAWSClient
from awsideman.cache.invalidation import CacheInvalidationEngine
from awsideman.cache.manager import CacheManager
from awsideman.utils.aws import get_identity_store_client

@click.command()
@click.option('--identity-store-id', required=True, help='Identity Store ID')
@click.option('--user-id', required=True, help='User ID')
@click.option('--group-id', required=True, help='Group ID')
def add_user_to_group(identity_store_id: str, user_id: str, group_id: str):
    """Add a user to a group."""

    cache_manager = CacheManager()
    client = get_identity_store_client()
    cached_client = CachedAWSClient(client, cache_manager)

    # Verify user exists (uses cache)
    try:
        user = cached_client.describe_user(
            IdentityStoreId=identity_store_id,
            UserId=user_id
        )
    except client.exceptions.ResourceNotFoundException:
        click.echo(f"Error: User {user_id} not found")
        return

    # Verify group exists (uses cache)
    try:
        group = cached_client.describe_group(
            IdentityStoreId=identity_store_id,
            GroupId=group_id
        )
    except client.exceptions.ResourceNotFoundException:
        click.echo(f"Error: Group {group_id} not found")
        return

    # Add user to group
    response = client.create_group_membership(
        IdentityStoreId=identity_store_id,
        GroupId=group_id,
        MemberId={'UserId': user_id}
    )

    # Invalidate relevant cache entries
    invalidation_engine = CacheInvalidationEngine(cache_manager)

    # Invalidate group membership cache
    invalidation_engine.invalidate_for_operation("update", "group", group_id)

    # Invalidate user's group membership cache
    cache_manager.invalidate(f"user:groups:{user_id}*")

    click.echo(f"Added user {user['UserName']} to group {group['DisplayName']}")
```

## Advanced Usage Patterns

### Example 1: Batch Operations with Cache Optimization

```python
from awsideman.cache.manager import CacheManager
from awsideman.cache.key_builder import CacheKeyBuilder
from datetime import timedelta

def batch_get_users(identity_store_id: str, user_ids: list[str]):
    """Get multiple users efficiently using cache."""

    cache_manager = CacheManager()
    key_builder = CacheKeyBuilder()
    client = get_identity_store_client()

    users = {}
    uncached_user_ids = []

    # Check cache for each user
    for user_id in user_ids:
        cache_key = key_builder.build_key(
            resource_type="user",
            operation="describe",
            identifier=user_id,
            params={"identity_store_id": identity_store_id}
        )

        cached_user = cache_manager.get(cache_key)
        if cached_user is not None:
            users[user_id] = cached_user
        else:
            uncached_user_ids.append(user_id)

    # Fetch uncached users from AWS
    for user_id in uncached_user_ids:
        try:
            user = client.describe_user(
                IdentityStoreId=identity_store_id,
                UserId=user_id
            )
            users[user_id] = user

            # Cache the result
            cache_key = key_builder.build_key(
                resource_type="user",
                operation="describe",
                identifier=user_id,
                params={"identity_store_id": identity_store_id}
            )
            cache_manager.set(cache_key, user, ttl=timedelta(minutes=15))

        except client.exceptions.ResourceNotFoundException:
            users[user_id] = None

    return users
```

### Example 2: Custom Cache TTL Based on Data Type

```python
from datetime import timedelta

def get_cache_ttl(resource_type: str, operation: str) -> timedelta:
    """Get appropriate TTL based on resource type and operation."""

    ttl_config = {
        "user": {
            "list": timedelta(minutes=10),      # User lists change frequently
            "describe": timedelta(minutes=30),   # User details change less often
        },
        "group": {
            "list": timedelta(minutes=15),
            "describe": timedelta(hours=1),
            "members": timedelta(minutes=5),     # Membership changes frequently
        },
        "permission_set": {
            "list": timedelta(hours=2),          # Permission sets change rarely
            "describe": timedelta(hours=4),
        }
    }

    return ttl_config.get(resource_type, {}).get(operation, timedelta(minutes=15))

def cached_operation(resource_type: str, operation: str, fetch_func):
    """Generic cached operation with appropriate TTL."""

    cache_manager = CacheManager()
    key_builder = CacheKeyBuilder()

    cache_key = key_builder.build_key(resource_type, operation, "data")
    cached_data = cache_manager.get(cache_key)

    if cached_data is not None:
        return cached_data

    # Fetch from AWS
    data = fetch_func()

    # Cache with appropriate TTL
    ttl = get_cache_ttl(resource_type, operation)
    cache_manager.set(cache_key, data, ttl=ttl)

    return data
```

### Example 3: Error Handling with Cache Fallback

```python
from awsideman.cache.errors import CacheError
from awsideman.cache.manager import CacheManager
import logging

logger = logging.getLogger(__name__)

def robust_cached_operation(cache_key: str, fetch_func):
    """Perform cached operation with robust error handling."""

    cache_manager = CacheManager()

    # Try cache first
    try:
        cached_data = cache_manager.get(cache_key)
        if cached_data is not None:
            return cached_data
    except CacheError as e:
        logger.warning(f"Cache get failed for key {cache_key}: {e}")
        # Continue to fetch from AWS

    # Fetch from AWS
    try:
        data = fetch_func()
    except Exception as e:
        logger.error(f"AWS fetch failed: {e}")

        # Try to return stale cache data as last resort
        try:
            stale_data = cache_manager.get(cache_key, ignore_ttl=True)
            if stale_data is not None:
                logger.warning(f"Returning stale cache data for key {cache_key}")
                return stale_data
        except CacheError:
            pass

        # Re-raise the original AWS error
        raise

    # Try to cache the result
    try:
        cache_manager.set(cache_key, data, ttl=timedelta(minutes=15))
    except CacheError as e:
        logger.warning(f"Cache set failed for key {cache_key}: {e}")
        # Continue - we have the data from AWS

    return data
```

## Testing Cache Integration

### Example 1: Unit Test with Mock Cache

```python
import pytest
from unittest.mock import Mock, patch
from awsideman.cache.manager import CacheManager

def test_list_users_with_cache():
    """Test user listing with cache."""

    # Mock the cache manager
    mock_cache = Mock(spec=CacheManager)
    mock_cache.get.return_value = None  # Cache miss

    with patch('awsideman.cache.manager.CacheManager', return_value=mock_cache):
        # Your command logic here
        result = list_users("store-123")

        # Verify cache was checked
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()
```

### Example 2: Integration Test with Real Cache

```python
import pytest
from awsideman.cache.manager import CacheManager

@pytest.fixture
def clean_cache():
    """Provide a clean cache for testing."""
    cache_manager = CacheManager()
    cache_manager.clear()
    yield cache_manager
    cache_manager.clear()

def test_cache_integration(clean_cache):
    """Test cache behavior in integration."""

    # First call should miss cache and fetch from AWS
    result1 = list_users("store-123")

    # Second call should hit cache
    result2 = list_users("store-123")

    # Results should be identical
    assert result1 == result2

    # Verify cache statistics
    stats = clean_cache.get_stats()
    assert stats.hit_count >= 1
    assert stats.miss_count >= 1
```

## Best Practices Summary

### Do's
- Always use `CachedAWSClient` for AWS operations
- Let the invalidation engine handle cache cleanup automatically
- Use appropriate TTL values based on data volatility
- Handle cache misses gracefully (return None checks)
- Use the `--no-cache` flag only for debugging

### Don'ts
- Don't manually manage cache keys unless necessary
- Don't bypass the cache manager singleton pattern
- Don't ignore cache errors - log them for debugging
- Don't use very short TTL values (< 1 minute) without good reason
- Don't clear the entire cache unless it's an emergency

### Performance Tips
- Batch operations when possible to reduce cache overhead
- Use longer TTL for rarely changing data (permission sets)
- Use shorter TTL for frequently changing data (group memberships)
- Monitor cache hit rates and adjust TTL accordingly
- Consider data size when caching large responses

This guide should help developers effectively integrate the unified cache manager into new awsideman commands while following best practices for performance and reliability.
