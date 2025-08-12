# Multi-Account Operations

This document provides comprehensive guidance on using awsideman's multi-account operations feature to manage permission set assignments across multiple AWS accounts efficiently.

## Overview

Multi-account operations allow you to assign or revoke permission sets to/from users across multiple AWS accounts in a single command. This feature is designed for large enterprises managing hundreds of accounts and provides:

- Bulk assignment/revocation across filtered account sets
- Real-time progress tracking for long-running operations
- Dry-run capabilities for safe previewing
- Configurable batch processing for optimal performance
- Comprehensive error handling and reporting

## Commands

### Multi-Account Assignment

Assign a permission set to a user across multiple accounts:

```bash
awsideman assignment assign <permission-set-name> <principal-name> --filter <filter-expression> [OPTIONS]
```

### Multi-Account Revocation

Revoke a permission set from a user across multiple accounts:

```bash
awsideman assignment revoke <permission-set-name> <principal-name> --filter <filter-expression> [OPTIONS]
```

## Command Options

| Option | Description | Default | Required |
|--------|-------------|---------|----------|
| `--filter` | Account filter expression (wildcard or tag-based) | None | Yes |
| `--principal-type` | Type of principal (USER or GROUP) | USER | No |
| `--dry-run` | Preview operations without making changes | False | No |
| `--batch-size` | Number of accounts to process concurrently | 10 | No |
| `--profile` | AWS profile to use | Default profile | No |

## Account Filtering

### Wildcard Filtering

Use `*` to target all accounts in your organization:

```bash
# Assign ReadOnlyAccess to john.doe across all accounts
awsideman assignment assign ReadOnlyAccess john.doe --filter "*"
```

### Tag-Based Filtering

Filter accounts using tag key-value pairs:

```bash
# Target only production accounts
awsideman assignment assign PowerUserAccess jane.smith --filter "tag:Environment=Production"

# Target development accounts
awsideman assignment revoke DeveloperAccess old.user --filter "tag:Environment=Development"
```

### Multiple Tag Filtering

Use multiple `--filter-tag` flags for complex filtering:

```bash
# Target accounts that are both Production and in US-East region
awsideman assignment assign SecurityAuditor audit.user \
  --filter-tag Environment=Production \
  --filter-tag Region=us-east-1
```

## Usage Examples

### Example 1: Basic Multi-Account Assignment

Assign a permission set to a user across all accounts:

```bash
awsideman assignment assign ReadOnlyAccess john.doe --filter "*"
```

**Expected Output:**
```
🔍 Resolving accounts with filter: *
✅ Found 45 accounts matching filter

🔍 Resolving permission set: ReadOnlyAccess
✅ Permission set ARN: arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-abcdef1234567890

🔍 Resolving principal: john.doe
✅ Principal ID: 12345678-1234-1234-1234-123456789012

📋 Multi-Account Assignment Preview:
   • Permission Set: ReadOnlyAccess
   • Principal: john.doe (USER)
   • Target Accounts: 45
   • Operation: ASSIGN

Processing accounts... ████████████████████████████████████████ 45/45 (100%)

✅ Multi-account assignment completed successfully!

📊 Results Summary:
   • Total Accounts: 45
   • Successful: 43
   • Failed: 2
   • Success Rate: 95.6%
   • Duration: 2m 15s
```

### Example 2: Tag-Based Filtering with Dry Run

Preview assignment to production accounts only:

```bash
awsideman assignment assign PowerUserAccess jane.smith \
  --filter "tag:Environment=Production" \
  --dry-run
```

**Expected Output:**
```
🔍 Resolving accounts with filter: tag:Environment=Production
✅ Found 12 accounts matching filter

🔍 Resolving permission set: PowerUserAccess
✅ Permission set ARN: arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef

🔍 Resolving principal: jane.smith
✅ Principal ID: 87654321-4321-4321-4321-210987654321

📋 DRY RUN - Multi-Account Assignment Preview:
   • Permission Set: PowerUserAccess
   • Principal: jane.smith (USER)
   • Target Accounts: 12
   • Operation: ASSIGN

🎯 Accounts that would be affected:
   1. prod-account-1 (123456789012) - Environment=Production
   2. prod-account-2 (123456789013) - Environment=Production
   3. prod-account-3 (123456789014) - Environment=Production
   ...
   12. prod-account-12 (123456789023) - Environment=Production

⚠️  DRY RUN MODE: No actual changes were made.
    Remove --dry-run flag to execute the operation.
```

### Example 3: Multi-Account Revocation

Revoke access from a user across development accounts:

```bash
awsideman assignment revoke DeveloperAccess former.employee \
  --filter "tag:Environment=Development" \
  --batch-size 5
```

**Expected Output:**
```
🔍 Resolving accounts with filter: tag:Environment=Development
✅ Found 8 accounts matching filter

🔍 Resolving permission set: DeveloperAccess
✅ Permission set ARN: arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-fedcba0987654321

🔍 Resolving principal: former.employee
✅ Principal ID: 11111111-2222-3333-4444-555555555555

📋 Multi-Account Revocation Preview:
   • Permission Set: DeveloperAccess
   • Principal: former.employee (USER)
   • Target Accounts: 8
   • Operation: REVOKE
   • Batch Size: 5

Processing accounts... ████████████████████████████████████████ 8/8 (100%)

✅ Multi-account revocation completed successfully!

📊 Results Summary:
   • Total Accounts: 8
   • Successful: 6
   • Skipped: 2 (assignment not found)
   • Failed: 0
   • Success Rate: 100%
   • Duration: 45s
```

### Example 4: Group Assignment

Assign a permission set to a group across specific accounts:

```bash
awsideman assignment assign SecurityAuditor "Security Team" \
  --filter "tag:Compliance=Required" \
  --principal-type GROUP
```

### Example 5: Large-Scale Operation with Custom Batch Size

Process a large number of accounts with optimized batch size:

```bash
awsideman assignment assign ReadOnlyAccess monitoring.user \
  --filter "*" \
  --batch-size 20
```

## Performance Considerations

### Batch Size Optimization

The `--batch-size` parameter controls how many accounts are processed concurrently:

- **Small batch size (1-5)**: Lower memory usage, slower overall processing
- **Medium batch size (10-15)**: Balanced performance and resource usage (recommended)
- **Large batch size (20+)**: Faster processing but higher memory usage and potential rate limiting

### Rate Limiting

AWS APIs have rate limits that may affect large-scale operations:

- SSO Admin API: ~10 requests per second
- Organizations API: ~20 requests per second

The tool automatically implements exponential backoff and retry logic when rate limits are encountered.

### Memory Usage

Memory usage scales with:
- Number of target accounts
- Batch size
- Amount of account metadata cached

For operations targeting 500+ accounts, consider:
- Using smaller batch sizes (5-10)
- Running operations during off-peak hours
- Monitoring system memory usage

## Best Practices

### 1. Always Use Dry Run First

Before executing any multi-account operation, use `--dry-run` to preview:

```bash
# Preview the operation
awsideman assignment assign MyPermissionSet user.name --filter "*" --dry-run

# Execute after reviewing
awsideman assignment assign MyPermissionSet user.name --filter "*"
```

### 2. Use Specific Filters

Avoid using wildcard filters (`*`) unless necessary:

```bash
# Preferred: Specific tag-based filtering
awsideman assignment assign DevAccess dev.user --filter "tag:Environment=Development"

# Use with caution: Wildcard filtering
awsideman assignment assign ReadOnly user.name --filter "*"
```

### 3. Monitor Progress for Large Operations

For operations targeting many accounts:
- Use appropriate batch sizes
- Monitor the progress output
- Be prepared for partial failures

### 4. Handle Failures Gracefully

The tool continues processing even if individual accounts fail:
- Review the final summary for failed accounts
- Investigate and retry failed operations separately
- Use single-account commands for troubleshooting specific failures

### 5. Optimize for Your Environment

Adjust batch size based on your environment:

```bash
# For smaller organizations (< 50 accounts)
--batch-size 15

# For medium organizations (50-200 accounts)
--batch-size 10

# For large organizations (200+ accounts)
--batch-size 5
```

## Security Considerations

### Permission Requirements

To use multi-account operations, you need:

1. **SSO Admin permissions** in the management account:
   - `sso:ListPermissionSets`
   - `sso:CreateAccountAssignment`
   - `sso:DeleteAccountAssignment`
   - `sso:ListAccountAssignments`

2. **Organizations permissions** in the management account:
   - `organizations:ListAccounts`
   - `organizations:ListTagsForResource`
   - `organizations:DescribeAccount`

### Audit and Compliance

Multi-account operations are logged in:
- AWS CloudTrail (SSO Admin API calls)
- AWS Config (if enabled)
- Local awsideman logs

Maintain audit trails for:
- Who performed the operation
- Which accounts were affected
- What permission sets were assigned/revoked
- When the operation occurred

### Least Privilege Access

Follow least privilege principles:
- Use specific tag filters instead of wildcards
- Assign minimal necessary permissions
- Regularly review and revoke unused assignments
- Use groups instead of individual user assignments when possible

## Integration with Existing Workflows

### CI/CD Integration

Multi-account operations can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Assign permission set to new user
  run: |
    awsideman assignment assign ReadOnlyAccess ${{ github.event.inputs.username }} \
      --filter "tag:Environment=Production" \
      --dry-run

    # Review and approve before actual execution
    awsideman assignment assign ReadOnlyAccess ${{ github.event.inputs.username }} \
      --filter "tag:Environment=Production"
```

### Automation Scripts

Create wrapper scripts for common operations:

```bash
#!/bin/bash
# assign-new-employee.sh

USERNAME=$1
ENVIRONMENT=${2:-Development}

echo "Assigning permissions for new employee: $USERNAME"

# Assign basic read access across all accounts
awsideman assignment assign ReadOnlyAccess "$USERNAME" --filter "*"

# Assign environment-specific access
awsideman assignment assign DeveloperAccess "$USERNAME" \
  --filter "tag:Environment=$ENVIRONMENT"

echo "Permission assignment completed for $USERNAME"
```

## Next Steps

After mastering multi-account operations:

1. Explore [bulk operations](BULK_OPERATIONS.md) for CSV-based assignments
2. Learn about [caching strategies](../examples/cache-configurations/README.md) for performance optimization
3. Review [security best practices](SECURITY_BEST_PRACTICES.md) for enterprise deployments
4. Set up [monitoring and alerting](MONITORING.md) for large-scale operations
