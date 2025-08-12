# Account Cache Optimization

This document describes the account cache optimization features in awsideman that dramatically improve performance for multi-account operations.

## Problem

When using wildcard filters (`*`) to target all accounts in an organization, the original implementation was slow because it:

1. Built the entire organization hierarchy by traversing all OUs recursively
2. Called `get_account_details()` for each individual account
3. Each `get_account_details()` call made multiple API calls (describe_account, list_tags_for_resource, list_parents)
4. Used short cache TTLs (1 hour) for account data that rarely changes

For organizations with 29+ accounts, this could take 30+ seconds.

## Solution

The optimization introduces a multi-tier caching strategy:

### 1. Organization Snapshot Cache
- Caches the complete list of all accounts in the organization for 24 hours
- Single cache entry contains all account details needed for filtering
- Eliminates the need to traverse the organization hierarchy repeatedly

### 2. Account Count Validation
- Maintains a separate cache of the total account count (1 hour TTL)
- Used to detect when the organization structure has changed
- Allows cache invalidation only when necessary

### 3. Extended Cache TTLs
- Organization structure operations: 24 hours (rarely change)
- Account details: 12 hours (account metadata changes infrequently)
- Account tags: 12 hours (tags don't change often)

### 4. Intelligent Cache Rebuilding
- When organization snapshot expires but account count is unchanged, attempts to rebuild from individual account cache entries
- Falls back to fresh API calls only when necessary

## Performance Impact

**Before optimization:**
- 29 accounts: ~30 seconds
- Multiple API calls per account
- Cache misses on every wildcard operation

**After optimization:**
- First run: ~5-10 seconds (builds cache)
- Subsequent runs: <1 second (uses cached snapshot)
- 95%+ reduction in API calls for repeated operations

## Usage

The optimization is automatic and transparent. No code changes are needed in existing commands.

### Cache Management

Check account cache status:
```bash
awsideman cache accounts
```

Clear only account-related cache (when organization changes):
```bash
awsideman cache clear --accounts-only
```

Clear all cache:
```bash
awsideman cache clear
```

### Configuration

The optimization uses these cache TTLs by default:

```yaml
cache:
  operation_ttls:
    # Organization structure (24 hours)
    list_roots: 86400
    list_organizational_units_for_parent: 86400
    list_accounts_for_parent: 86400
    list_parents: 86400

    # Account details (12 hours)
    describe_account: 43200
    list_tags_for_resource: 43200

    # Organization snapshot (24 hours)
    org_snapshot: 86400

    # Account count validation (1 hour)
    account_count: 3600
```

You can customize these in your `~/.awsideman/config.yaml`:

```yaml
cache:
  enabled: true
  default_ttl: 3600
  operation_ttls:
    describe_account: 86400  # Cache account details for 24 hours
    list_roots: 172800       # Cache organization roots for 48 hours
```

## When to Clear Cache

Clear account cache when:
- New accounts are added to the organization
- Accounts are removed from the organization
- Account tags or metadata are updated
- Organization structure (OUs) changes

The system automatically detects account count changes, but manual cache clearing may be needed for metadata updates.

## Monitoring

Use `awsideman cache accounts` to monitor:
- Organization snapshot cache age and status
- Account count cache status
- Performance recommendations
- Cache configuration validation

## Technical Details

### Cache Keys
- Organization snapshot: `org_snapshot_v1`
- Account count: `org_account_count_v1`
- Individual accounts: `account_details_{account_id}`

### Cache Backends
The optimization works with all supported cache backends:
- File-based cache (default)
- DynamoDB cache
- Hybrid cache

### Error Handling
- Graceful fallback to fresh API calls if cache operations fail
- Individual account failures don't prevent processing other accounts
- Comprehensive logging for troubleshooting

## Migration

Existing installations automatically benefit from the optimization. No migration steps are required.

The first wildcard operation after upgrading will be slower as it builds the initial cache, but subsequent operations will be dramatically faster.
