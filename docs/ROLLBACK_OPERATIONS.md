# Rollback Operations Documentation

This document provides comprehensive guidance for using the rollback operations feature in awsideman CLI.

## Overview

The rollback operations feature provides a safety net for permission set assignments and revocations by automatically tracking all operations and allowing you to undo them when needed. This feature is essential for maintaining operational safety when managing permissions across multiple AWS accounts.

## Key Features

- **Automatic Operation Tracking**: All permission set assignments and revocations are automatically logged
- **Operation History**: View detailed history of all operations with filtering capabilities
- **Safe Rollback**: Undo specific operations with validation and confirmation
- **Dry-Run Support**: Preview rollback operations before executing them
- **Batch Processing**: Efficient rollback of operations affecting multiple accounts
- **State Verification**: Verify current AWS state before and after rollback operations
- **Idempotent Operations**: Safe to run rollback multiple times without side effects
- **Comprehensive Logging**: Detailed audit trail of all rollback operations

## Commands

### rollback list

List historical permission set operations with filtering and formatting options.

```bash
awsideman rollback list [OPTIONS]
```

**Options:**
- `--operation-type [assign|revoke]`: Filter by operation type
- `--principal TEXT`: Filter by principal name (user or group)
- `--permission-set TEXT`: Filter by permission set name
- `--days INTEGER`: Show operations from last N days (default: 30)
- `--format [table|json]`: Output format (default: table)
- `--profile TEXT`: AWS profile to use
- `--help`: Show help message and exit

**Examples:**
```bash
# List all operations from the last 7 days
awsideman rollback list --days 7

# List only assignment operations
awsideman rollback list --operation-type assign

# List operations for a specific user
awsideman rollback list --principal john.doe

# List operations for a specific permission set
awsideman rollback list --permission-set ReadOnlyAccess

# Get detailed JSON output
awsideman rollback list --format json --days 14
```

### rollback apply

Apply rollback for a specific operation by ID.

```bash
awsideman rollback apply [OPTIONS] OPERATION_ID
```

**Options:**
- `--dry-run`: Preview rollback without making changes
- `--yes, -y`: Skip confirmation prompts and proceed automatically
- `--batch-size INTEGER`: Number of rollback actions to process in parallel (1-20, default: 10)
- `--profile TEXT`: AWS profile to use
- `--help`: Show help message and exit

**Examples:**
```bash
# Preview rollback for an operation
awsideman rollback apply --dry-run abc123-def456-ghi789

# Apply rollback with confirmation
awsideman rollback apply abc123-def456-ghi789

# Apply rollback without confirmation
awsideman rollback apply --yes abc123-def456-ghi789

# Apply rollback with custom batch size
awsideman rollback apply --batch-size 5 abc123-def456-ghi789
```

### rollback status

Show rollback system status and statistics.

```bash
awsideman rollback status [OPTIONS]
```

**Options:**
- `--profile TEXT`: AWS profile to use
- `--help`: Show help message and exit

**Example:**
```bash
awsideman rollback status
```

## Input Formats and Examples

### Operation List Output

The `rollback list` command displays operations in a table format by default:

```
┌──────────────────────────────────────┬─────────────────────┬───────────┬─────────────┬─────────────────┬──────────┬─────────────┐
│ Operation ID                         │ Timestamp           │ Type      │ Principal   │ Permission Set  │ Accounts │ Status      │
├──────────────────────────────────────┼─────────────────────┼───────────┼─────────────┼─────────────────┼──────────┼─────────────┤
│ abc123-def456-ghi789                 │ 2024-01-15 10:30:00 │ assign    │ john.doe    │ ReadOnlyAccess  │ 3        │ completed   │
│ def456-ghi789-jkl012                 │ 2024-01-15 09:15:00 │ revoke    │ DevTeam     │ PowerUserAccess │ 5        │ completed   │
│ ghi789-jkl012-mno345                 │ 2024-01-14 16:45:00 │ assign    │ jane.smith  │ AdminAccess     │ 1        │ rolled_back │
└──────────────────────────────────────┴─────────────────────┴───────────┴─────────────┴─────────────────┴──────────┴─────────────┘
```

### JSON Output Format

When using `--format json`, the output includes detailed operation information:

```json
{
  "operations": [
    {
      "operation_id": "abc123-def456-ghi789",
      "timestamp": "2024-01-15T10:30:00Z",
      "operation_type": "assign",
      "principal_id": "user-123456789",
      "principal_type": "USER",
      "principal_name": "john.doe",
      "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123456789/ps-123456789",
      "permission_set_name": "ReadOnlyAccess",
      "account_ids": ["123456789012", "234567890123", "345678901234"],
      "account_names": ["Production", "Staging", "Development"],
      "results": [
        {
          "account_id": "123456789012",
          "success": true,
          "error": null,
          "duration_ms": 1500
        }
      ],
      "metadata": {
        "source": "bulk_assign",
        "input_file": "assignments.csv",
        "batch_size": 10
      },
      "rolled_back": false,
      "rollback_operation_id": null
    }
  ]
}
```

## Configuration

### Rollback Settings

Configure rollback behavior in your `~/.awsideman/config.yaml`:

```yaml
rollback:
  # Enable/disable rollback tracking
  enabled: true

  # Directory for storing operation logs
  storage_directory: "~/.awsideman/operations"

  # Number of days to retain operation logs
  retention_days: 90

  # Automatically clean up old operations
  auto_cleanup: true

  # Maximum number of operations to store
  max_operations: 10000

  # Require confirmation for rollback operations
  confirmation_required: true

  # Default to dry-run mode
  dry_run_default: false
```

### Environment Variables

Override configuration using environment variables:

```bash
# Enable/disable rollback tracking
export AWSIDEMAN_ROLLBACK_ENABLED=true

# Set storage directory
export AWSIDEMAN_ROLLBACK_STORAGE_DIR="/custom/path/operations"

# Set retention period
export AWSIDEMAN_ROLLBACK_RETENTION_DAYS=60

# Disable confirmation prompts
export AWSIDEMAN_ROLLBACK_CONFIRMATION_REQUIRED=false
```

## Common Use Cases

### 1. Reviewing Recent Operations

Before making changes, review what operations have been performed recently:

```bash
# Check operations from the last 24 hours
awsideman rollback list --days 1

# Check only assignment operations
awsideman rollback list --operation-type assign --days 7
```

### 2. Rolling Back Incorrect Assignments

If you accidentally assigned the wrong permission set:

```bash
# First, list recent operations to find the operation ID
awsideman rollback list --days 1

# Preview the rollback
awsideman rollback apply --dry-run abc123-def456-ghi789

# Apply the rollback
awsideman rollback apply abc123-def456-ghi789
```

### 3. Rolling Back Bulk Operations

If a bulk operation had unintended consequences:

```bash
# Find the bulk operation
awsideman rollback list --days 1 --format json | grep "bulk_assign"

# Preview the rollback
awsideman rollback apply --dry-run def456-ghi789-jkl012

# Apply with larger batch size for faster processing
awsideman rollback apply --batch-size 15 def456-ghi789-jkl012
```

### 4. Auditing Permission Changes

Review all permission changes for compliance:

```bash
# Get detailed JSON output for the last 30 days
awsideman rollback list --format json --days 30 > permission_audit.json

# Filter for specific users or groups
awsideman rollback list --principal "admin-group" --days 90
```

## Best Practices

### 1. Regular Operation Review

- Review operations daily using `rollback list`
- Use filtering to focus on specific principals or permission sets
- Monitor for unexpected operations that might indicate security issues

### 2. Safe Rollback Procedures

- Always use `--dry-run` first to preview rollback operations
- Verify the operation details before applying rollback
- Consider the impact on users before rolling back assignments
- Document the reason for rollbacks in your change management system

### 3. Configuration Management

- Set appropriate retention periods based on your compliance requirements
- Enable auto-cleanup to prevent storage issues
- Use environment variables for CI/CD environments
- Regularly backup operation logs for long-term audit trails

### 4. Monitoring and Alerting

- Monitor rollback system status regularly
- Set up alerts for failed operations
- Track rollback frequency to identify process issues
- Review operation patterns to optimize permission management

## Troubleshooting

### Common Issues and Solutions

#### 1. Operation Not Found

**Error:** `Operation with ID 'abc123' not found`

**Causes:**
- Incorrect operation ID
- Operation older than retention period
- Operation logs corrupted or deleted

**Solutions:**
```bash
# Verify operation ID from list
awsideman rollback list --days 90

# Check rollback system status
awsideman rollback status

# Verify storage directory exists and is accessible
ls -la ~/.awsideman/operations/
```

#### 2. Already Rolled Back

**Error:** `Operation 'abc123' has already been rolled back`

**Causes:**
- Operation was previously rolled back
- Attempting to rollback a rollback operation

**Solutions:**
```bash
# Check operation status
awsideman rollback list --format json | grep "abc123"

# Look for the original operation if this is a rollback operation
awsideman rollback list --days 90 --format json
```

#### 3. State Mismatch

**Error:** `Current AWS state doesn't match expected state for rollback`

**Causes:**
- Manual changes made outside of awsideman
- Concurrent operations by other users
- AWS Identity Center synchronization issues

**Solutions:**
```bash
# Use dry-run to see current state
awsideman rollback apply --dry-run abc123-def456-ghi789

# Check current assignments
awsideman assignment list --principal john.doe

# Verify permission set exists
awsideman permission-set list
```

#### 4. AWS API Errors

**Error:** `AWS API error: Rate limit exceeded`

**Causes:**
- Too many concurrent operations
- AWS service throttling
- Insufficient permissions

**Solutions:**
```bash
# Reduce batch size
awsideman rollback apply --batch-size 3 abc123-def456-ghi789

# Check AWS permissions
aws sts get-caller-identity

# Wait and retry
sleep 60 && awsideman rollback apply abc123-def456-ghi789
```

#### 5. Storage Issues

**Error:** `Unable to write to operation log`

**Causes:**
- Insufficient disk space
- Permission issues with storage directory
- Storage directory doesn't exist

**Solutions:**
```bash
# Check disk space
df -h ~/.awsideman/

# Check directory permissions
ls -la ~/.awsideman/operations/

# Create directory if missing
mkdir -p ~/.awsideman/operations/

# Check configuration
awsideman rollback status
```

### Diagnostic Commands

#### Check System Health
```bash
# Overall rollback system status
awsideman rollback status

# Check configuration
cat ~/.awsideman/config.yaml | grep -A 10 rollback

# Verify storage directory
ls -la ~/.awsideman/operations/
```

#### Validate Operation Logs
```bash
# Check log file integrity
python -m json.tool ~/.awsideman/operations/operations.json

# Count operations
jq '.operations | length' ~/.awsideman/operations/operations.json

# Find specific operation
jq '.operations[] | select(.operation_id == "abc123")' ~/.awsideman/operations/operations.json
```

#### Test Rollback Functionality
```bash
# Test with dry-run
awsideman rollback apply --dry-run <operation-id>

# Verify AWS connectivity
aws sso list-instances --profile <profile>

# Check Identity Center status
aws sso-admin list-permission-sets --instance-arn <instance-arn>
```

## Security Considerations

### 1. Operation Log Security

- Operation logs contain sensitive information about permission assignments
- Ensure proper file permissions on the storage directory (700)
- Consider encrypting operation logs for highly sensitive environments
- Regularly audit access to operation logs

### 2. Rollback Authorization

- Verify users have appropriate permissions before allowing rollbacks
- Consider implementing approval workflows for rollback operations
- Log all rollback operations for audit purposes
- Restrict rollback capabilities to authorized personnel only

### 3. Audit Trail Integrity

- Protect operation logs from tampering
- Implement backup and recovery procedures for operation logs
- Consider using immutable storage for long-term audit requirements
- Regular integrity checks on operation log files

## Performance Considerations

### 1. Batch Size Optimization

- Start with default batch size (10) and adjust based on performance
- Reduce batch size if encountering rate limits
- Increase batch size for faster processing of large rollbacks
- Monitor AWS API usage and adjust accordingly

### 2. Storage Management

- Enable auto-cleanup to prevent storage bloat
- Set appropriate retention periods based on requirements
- Monitor storage usage regularly
- Consider archiving old operation logs

### 3. Operation Filtering

- Use specific filters to reduce processing time
- Avoid broad date ranges when possible
- Use JSON format only when detailed information is needed
- Cache frequently accessed operation data

## Integration Examples

### 1. CI/CD Pipeline Integration

```bash
#!/bin/bash
# rollback-safety-check.sh

# Check for recent operations before deployment
RECENT_OPS=$(awsideman rollback list --days 1 --format json)

if [ "$(echo $RECENT_OPS | jq '.operations | length')" -gt 0 ]; then
    echo "Recent permission changes detected. Review before proceeding:"
    awsideman rollback list --days 1
    exit 1
fi
```

### 2. Automated Rollback Script

```bash
#!/bin/bash
# emergency-rollback.sh

OPERATION_ID=$1

if [ -z "$OPERATION_ID" ]; then
    echo "Usage: $0 <operation-id>"
    exit 1
fi

# Preview rollback
echo "Previewing rollback for operation: $OPERATION_ID"
awsideman rollback apply --dry-run "$OPERATION_ID"

# Confirm with user
read -p "Proceed with rollback? (y/N): " confirm
if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
    awsideman rollback apply --yes "$OPERATION_ID"
else
    echo "Rollback cancelled"
fi
```

### 3. Monitoring Script

```bash
#!/bin/bash
# rollback-monitor.sh

# Check rollback system health
STATUS=$(awsideman rollback status)
echo "$STATUS"

# Alert on high rollback frequency
ROLLBACKS_TODAY=$(awsideman rollback list --days 1 --format json | jq '[.operations[] | select(.operation_type == "rollback")] | length')

if [ "$ROLLBACKS_TODAY" -gt 5 ]; then
    echo "WARNING: High rollback frequency detected ($ROLLBACKS_TODAY rollbacks today)"
    # Send alert to monitoring system
fi
```

## Advanced Usage

### 1. Bulk Rollback Operations

While not directly supported, you can script multiple rollbacks:

```bash
#!/bin/bash
# bulk-rollback.sh

# Get operations from a specific time period
OPERATIONS=$(awsideman rollback list --days 1 --format json | jq -r '.operations[].operation_id')

for op_id in $OPERATIONS; do
    echo "Rolling back operation: $op_id"
    awsideman rollback apply --dry-run "$op_id"

    read -p "Proceed with this rollback? (y/N): " confirm
    if [ "$confirm" = "y" ]; then
        awsideman rollback apply --yes "$op_id"
    fi
done
```

### 2. Custom Filtering and Reporting

```bash
#!/bin/bash
# custom-rollback-report.sh

# Generate custom report
awsideman rollback list --format json --days 30 | jq '
{
  "summary": {
    "total_operations": (.operations | length),
    "assignments": [.operations[] | select(.operation_type == "assign")] | length,
    "revocations": [.operations[] | select(.operation_type == "revoke")] | length,
    "rollbacks": [.operations[] | select(.operation_type == "rollback")] | length
  },
  "by_principal": [.operations | group_by(.principal_name) | .[] | {
    "principal": .[0].principal_name,
    "operations": length
  }],
  "by_permission_set": [.operations | group_by(.permission_set_name) | .[] | {
    "permission_set": .[0].permission_set_name,
    "operations": length
  }]
}'
```

### 3. Compliance Reporting

```bash
#!/bin/bash
# compliance-report.sh

# Generate compliance report for the last quarter
awsideman rollback list --format json --days 90 > quarterly_operations.json

# Extract key metrics
jq '
{
  "reporting_period": "Q1 2024",
  "total_operations": (.operations | length),
  "operations_by_type": [.operations | group_by(.operation_type) | .[] | {
    "type": .[0].operation_type,
    "count": length
  }],
  "high_privilege_operations": [.operations[] | select(.permission_set_name | contains("Admin"))],
  "rollback_frequency": [.operations[] | select(.operation_type == "rollback")] | length
}' quarterly_operations.json > compliance_report.json
```

## Migration and Upgrade

### Upgrading from Previous Versions

If upgrading from a version without rollback support:

1. **Enable Rollback Tracking**
   ```bash
   # Add to config.yaml
   rollback:
     enabled: true
   ```

2. **Initialize Storage Directory**
   ```bash
   mkdir -p ~/.awsideman/operations/
   ```

3. **Verify Configuration**
   ```bash
   awsideman rollback status
   ```

### Data Migration

For organizations with existing audit requirements:

1. **Export Existing Logs**
   ```bash
   # If you have existing logs in a different format
   # Convert them to awsideman format
   ```

2. **Import Historical Data**
   ```bash
   # Use custom scripts to import historical operation data
   # Ensure proper format and validation
   ```

## Support and Resources

### Getting Help

1. **Check System Status**
   ```bash
   awsideman rollback status
   ```

2. **Review Configuration**
   ```bash
   cat ~/.awsideman/config.yaml | grep -A 10 rollback
   ```

3. **Validate Operation Logs**
   ```bash
   python -m json.tool ~/.awsideman/operations/operations.json
   ```

4. **Test Connectivity**
   ```bash
   aws sts get-caller-identity
   ```

### Additional Resources

- [AWS Identity Center Documentation](https://docs.aws.amazon.com/singlesignon/)
- [awsideman GitHub Repository](https://github.com/vikyol/awsideman)
- [Issue Tracker](https://github.com/vikyol/awsideman/issues)
- [Security Best Practices](SECURITY_BEST_PRACTICES.md)

### Contributing

If you encounter issues or have suggestions for improving the rollback functionality:

1. Check existing issues on GitHub
2. Provide detailed error messages and logs
3. Include your configuration (with sensitive data removed)
4. Describe the expected vs. actual behavior

---

*This documentation is part of the awsideman project. For the latest updates and additional resources, visit the [GitHub repository](https://github.com/vikyol/awsideman).*
