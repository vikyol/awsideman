# Cache Key Patterns and Invalidation Rules

This document defines the cache key patterns used throughout awsideman and the invalidation rules that ensure cache consistency when data changes.

## Cache Key Structure

### Hierarchical Key Format

All cache keys follow a consistent hierarchical structure:

```
{resource_type}:{operation}:{identifier}:{sub_identifier}:{params_hash}
```

**Components:**
- `resource_type`: The AWS resource type (user, group, permission_set, assignment)
- `operation`: The operation being performed (list, describe, create, update, delete)
- `identifier`: The primary identifier (resource ID, "all" for lists)
- `sub_identifier`: Optional secondary identifier (for nested resources)
- `params_hash`: Optional hash of operation parameters for uniqueness

### Key Building Rules

1. **Consistency**: Same parameters always generate identical keys
2. **Uniqueness**: Different parameters generate different keys
3. **Hierarchy**: Keys support wildcard pattern matching
4. **Readability**: Keys are human-readable for debugging

## Resource Type Patterns

### User Operations

#### List Operations
```
user:list:all                                    # List all users
user:list:all:filter:{filter_hash}              # Filtered user list
user:list:all:search:{search_term}              # Search users
```

#### Individual User Operations
```
user:describe:{user_id}                          # Get user details
user:describe:{user_id}:{identity_store_id}     # User in specific store
user:groups:{user_id}                           # User's group memberships
user:assignments:{user_id}                      # User's permission assignments
user:attributes:{user_id}                       # User's custom attributes
```

#### User Management Operations
```
user:create:{user_id}                           # Created user (for rollback)
user:update:{user_id}                           # Updated user (for rollback)
user:delete:{user_id}                           # Deleted user (for rollback)
```

### Group Operations

#### List Operations
```
group:list:all                                  # List all groups
group:list:all:filter:{filter_hash}            # Filtered group list
group:list:all:search:{search_term}            # Search groups
```

#### Individual Group Operations
```
group:describe:{group_id}                       # Get group details
group:describe:{group_id}:{identity_store_id}  # Group in specific store
group:members:{group_id}                        # Group member list
group:members:{group_id}:users                  # Only user members
group:members:{group_id}:groups                 # Only group members
group:assignments:{group_id}                    # Group's permission assignments
```

#### Group Management Operations
```
group:create:{group_id}                         # Created group
group:update:{group_id}                         # Updated group
group:delete:{group_id}                         # Deleted group
group:add_member:{group_id}:{member_id}         # Added member
group:remove_member:{group_id}:{member_id}      # Removed member
```

### Permission Set Operations

#### List Operations
```
permission_set:list:all                         # List all permission sets
permission_set:list:all:{instance_arn_hash}    # Permission sets for instance
permission_set:list:provisioned:{account_id}   # Provisioned to account
```

#### Individual Permission Set Operations
```
permission_set:describe:{permission_set_arn}                    # Get details
permission_set:describe:{permission_set_arn}:{instance_arn}    # With instance
permission_set:policies:{permission_set_arn}                   # Attached policies
permission_set:policies:{permission_set_arn}:managed          # Managed policies only
permission_set:policies:{permission_set_arn}:inline           # Inline policies only
permission_set:boundaries:{permission_set_arn}                 # Permission boundaries
```

#### Permission Set Management Operations
```
permission_set:create:{permission_set_arn}      # Created permission set
permission_set:update:{permission_set_arn}      # Updated permission set
permission_set:delete:{permission_set_arn}      # Deleted permission set
permission_set:provision:{permission_set_arn}:{account_id}  # Provisioned to account
```

### Assignment Operations

#### List Operations
```
assignment:list:{account_id}                                    # All assignments for account
assignment:list:{account_id}:{permission_set_arn}             # Specific permission set
assignment:list:user:{user_id}                                 # User's assignments
assignment:list:group:{group_id}                               # Group's assignments
assignment:list:permission_set:{permission_set_arn}           # Permission set assignments
```

#### Individual Assignment Operations
```
assignment:describe:{account_id}:{permission_set_arn}:{principal_id}  # Specific assignment
assignment:status:{account_id}:{permission_set_arn}:{principal_id}    # Assignment status
```

#### Assignment Management Operations
```
assignment:create:{account_id}:{permission_set_arn}:{principal_id}    # Created assignment
assignment:delete:{account_id}:{permission_set_arn}:{principal_id}    # Deleted assignment
```

## Parameter Hashing

### When to Use Parameter Hashing

Parameter hashing is used when:
1. Operation parameters affect the result
2. Parameters are complex or lengthy
3. Multiple parameter combinations exist

### Hash Generation

```python
import hashlib
import json

def generate_params_hash(params: dict) -> str:
    """Generate consistent hash for parameters."""
    # Sort parameters for consistency
    sorted_params = json.dumps(params, sort_keys=True)

    # Generate SHA-256 hash
    hash_object = hashlib.sha256(sorted_params.encode())

    # Return first 8 characters for readability
    return hash_object.hexdigest()[:8]

# Example usage
params = {
    "identity_store_id": "d-1234567890",
    "filter": {"attribute_path": "UserName", "attribute_value": "john"}
}
params_hash = generate_params_hash(params)  # Returns: "a1b2c3d4"
```

### Examples with Parameter Hashing

```python
# Filtered user list
params = {"filter": {"UserName": "john*"}}
key = f"user:list:all:filter:{generate_params_hash(params)}"
# Result: user:list:all:filter:a1b2c3d4

# Search with pagination
params = {"search": "john", "max_results": 50, "next_token": "abc123"}
key = f"user:list:all:search:{generate_params_hash(params)}"
# Result: user:list:all:search:b2c3d4e5

# Permission set with instance ARN
params = {"instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef"}
key = f"permission_set:list:all:{generate_params_hash(params)}"
# Result: permission_set:list:all:c3d4e5f6
```

## Invalidation Rules

### Basic Invalidation Patterns

#### User Operations
```python
# User create/update/delete invalidates:
user_invalidation_patterns = [
    "user:list:*",                    # All user lists
    f"user:describe:{user_id}",       # Specific user details
    f"user:*:{user_id}",              # All operations for this user
]

# Group membership changes also invalidate:
group_membership_patterns = [
    f"group:members:{group_id}",      # Group member lists
    f"user:groups:{user_id}",         # User's group memberships
]
```

#### Group Operations
```python
# Group create/update/delete invalidates:
group_invalidation_patterns = [
    "group:list:*",                   # All group lists
    f"group:describe:{group_id}",     # Specific group details
    f"group:*:{group_id}",            # All operations for this group
]

# Member add/remove also invalidates:
member_invalidation_patterns = [
    f"group:members:{group_id}",      # Group member list
    f"user:groups:{member_id}",       # Member's group list (if user)
    f"group:members:{member_id}",     # Member's parent groups (if group)
]
```

#### Permission Set Operations
```python
# Permission set create/update/delete invalidates:
permission_set_invalidation_patterns = [
    "permission_set:list:*",                    # All permission set lists
    f"permission_set:describe:{ps_arn}",        # Specific permission set
    f"permission_set:*:{ps_arn}",               # All operations for this PS
    f"assignment:list:permission_set:{ps_arn}", # Assignments using this PS
]

# Policy changes also invalidate:
policy_invalidation_patterns = [
    f"permission_set:policies:{ps_arn}",        # Policy lists
    f"permission_set:boundaries:{ps_arn}",      # Permission boundaries
]
```

#### Assignment Operations
```python
# Assignment create/delete invalidates:
assignment_invalidation_patterns = [
    f"assignment:list:{account_id}",                        # Account assignments
    f"assignment:list:{account_id}:{permission_set_arn}",   # PS assignments
    f"assignment:list:user:{principal_id}",                 # User assignments (if user)
    f"assignment:list:group:{principal_id}",                # Group assignments (if group)
    f"assignment:list:permission_set:{permission_set_arn}", # PS assignments
]
```

### Cross-Resource Invalidation Rules

#### User-Group Relationships
```python
def invalidate_user_group_relationship(user_id: str, group_id: str, operation: str):
    """Invalidate cache for user-group relationship changes."""
    patterns = [
        # User-specific invalidations
        f"user:groups:{user_id}",           # User's group memberships
        f"user:assignments:{user_id}",      # User's assignments (may change via group)

        # Group-specific invalidations
        f"group:members:{group_id}",        # Group's member list

        # List invalidations
        "user:list:*",                      # User lists (membership affects filters)
        "group:list:*",                     # Group lists (member count may change)
    ]
    return patterns
```

#### Permission Set-Assignment Relationships
```python
def invalidate_permission_set_assignments(permission_set_arn: str, account_id: str):
    """Invalidate cache for permission set assignment changes."""
    patterns = [
        # Permission set invalidations
        f"permission_set:describe:{permission_set_arn}",
        "permission_set:list:*",

        # Assignment invalidations
        f"assignment:list:{account_id}",
        f"assignment:list:{account_id}:{permission_set_arn}",
        f"assignment:list:permission_set:{permission_set_arn}",

        # Provisioning status
        f"permission_set:provision:{permission_set_arn}:{account_id}",
    ]
    return patterns
```

### Advanced Invalidation Scenarios

#### Bulk Operations
```python
def invalidate_bulk_user_operations(user_ids: list[str]):
    """Invalidate cache for bulk user operations."""
    patterns = [
        "user:list:*",  # All user lists affected
    ]

    # Add specific user invalidations
    for user_id in user_ids:
        patterns.extend([
            f"user:describe:{user_id}",
            f"user:*:{user_id}",
        ])

    return patterns
```

#### Cascading Invalidations
```python
def invalidate_group_deletion(group_id: str):
    """Invalidate cache for group deletion with cascading effects."""

    # First, get group members before deletion
    members = get_group_members(group_id)  # From cache or AWS

    patterns = [
        # Group-specific invalidations
        f"group:*:{group_id}",
        "group:list:*",

        # Member invalidations
        *[f"user:groups:{member['UserId']}" for member in members if 'UserId' in member],
        *[f"group:members:{member['GroupId']}" for member in members if 'GroupId' in member],

        # Assignment invalidations (group assignments become invalid)
        f"assignment:list:group:{group_id}",
    ]

    return patterns
```

## Implementation Examples

### Cache Key Builder Usage

```python
from awsideman.cache.key_builder import CacheKeyBuilder

key_builder = CacheKeyBuilder()

# Simple list operation
key = key_builder.build_key("user", "list", "all")
# Result: "user:list:all"

# Describe operation
key = key_builder.build_key("user", "describe", "user-123")
# Result: "user:describe:user-123"

# Complex operation with parameters
key = key_builder.build_key(
    resource_type="user",
    operation="list",
    identifier="all",
    params={"filter": {"UserName": "john*"}}
)
# Result: "user:list:all:filter:a1b2c3d4"

# Nested resource operation
key = key_builder.build_key(
    resource_type="group",
    operation="members",
    identifier="group-456",
    sub_identifier="users"
)
# Result: "group:members:group-456:users"
```

### Invalidation Engine Usage

```python
from awsideman.cache.invalidation import CacheInvalidationEngine
from awsideman.cache.manager import CacheManager

cache_manager = CacheManager()
invalidation_engine = CacheInvalidationEngine(cache_manager)

# Invalidate after user update
count = invalidation_engine.invalidate_for_operation("update", "user", "user-123")
print(f"Invalidated {count} cache entries")

# Invalidate after group membership change
count = invalidation_engine.invalidate_user_group_relationship(
    user_id="user-123",
    group_id="group-456",
    operation="add_member"
)
print(f"Invalidated {count} cache entries for membership change")

# Custom invalidation pattern
count = cache_manager.invalidate("user:list:*")
print(f"Invalidated {count} user list entries")
```

### Pattern Matching Examples

```python
# Wildcard patterns for invalidation
patterns = [
    "user:*",                    # All user operations
    "user:list:*",              # All user list operations
    "user:describe:*",          # All user describe operations
    "*:list:*",                 # All list operations
    "group:members:*",          # All group member operations
    "assignment:list:*",        # All assignment list operations
]

# Test pattern matching
test_keys = [
    "user:list:all",
    "user:describe:user-123",
    "group:list:all",
    "group:members:group-456",
    "assignment:list:account-789"
]

for pattern in patterns:
    matching_keys = [key for key in test_keys if fnmatch.fnmatch(key, pattern)]
    print(f"Pattern '{pattern}' matches: {matching_keys}")
```

## Best Practices

### Key Design Guidelines

1. **Use Consistent Naming**: Always use the same resource type names
2. **Include Context**: Add necessary context (identity_store_id, instance_arn) in parameters
3. **Avoid Deep Nesting**: Keep key hierarchy shallow for better performance
4. **Use Meaningful Identifiers**: Use descriptive operation names

### Invalidation Guidelines

1. **Be Conservative**: Invalidate more rather than less to ensure consistency
2. **Consider Relationships**: Think about cross-resource dependencies
3. **Test Patterns**: Verify invalidation patterns match expected keys
4. **Monitor Performance**: Watch for over-invalidation affecting performance

### Performance Considerations

1. **Pattern Complexity**: Simple patterns perform better than complex regex
2. **Batch Invalidation**: Group related invalidations together
3. **Lazy Invalidation**: Consider lazy invalidation for non-critical data
4. **Cache Warming**: Pre-populate cache after bulk invalidations

This comprehensive guide ensures consistent cache key generation and reliable invalidation across the entire awsideman system.
