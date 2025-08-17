# Rollback Procedures for Permission Cloning

## Overview

The rollback system provides comprehensive undo capabilities for all permission cloning operations. This document covers rollback procedures, best practices, and troubleshooting for both copy and clone operations.

## Rollback System Architecture

### What Gets Tracked

The rollback system automatically tracks:

- **Operation Metadata**: Type, timestamp, user, source, target
- **Changes Made**: Specific assignments added or permission sets created
- **Original State**: What existed before the operation
- **Filter Context**: Any filters that were applied during the operation
- **Dependencies**: Relationships between operations

### Rollback Data Storage

- **Local Storage**: Rollback data is stored locally with the operation logs
- **Retention Policy**: Default 30-day retention (configurable)
- **Automatic Cleanup**: Old rollback data is automatically purged
- **Backup Integration**: Rollback data can be backed up with other operation logs

## Core Rollback Commands

### List Available Operations

```bash
# List all available rollback operations
awsideman rollback list

# List with detailed information
awsideman rollback list --detailed

# List operations from specific date range
awsideman rollback list --since "2024-08-01" --until "2024-08-16"

# List only specific operation types
awsideman rollback list --type copy
awsideman rollback list --type clone
```

### Execute Rollback

```bash
# Rollback specific operation
awsideman rollback execute --operation-id <operation-id>

# Rollback latest operation
awsideman rollback execute --latest

# Preview rollback without executing
awsideman rollback execute --operation-id <operation-id> --preview

# Force rollback (skip confirmations)
awsideman rollback execute --operation-id <operation-id> --force

# Partial rollback (continue on errors)
awsideman rollback execute --operation-id <operation-id> --partial
```

### Inspect Operations

```bash
# Get detailed information about an operation
awsideman rollback inspect --operation-id <operation-id>

# Check rollback status
awsideman rollback status

# Validate rollback data integrity
awsideman rollback validate --operation-id <operation-id>
```

## Copy Operation Rollback

### Understanding Copy Rollback

Copy operation rollback removes **only** the assignments that were added during the copy operation. It does **not** affect:
- Assignments that already existed on the target
- Assignments that were manually added after the copy
- Assignments that were modified after the copy

### Copy Rollback Process

1. **Validation**: Verify the operation exists and can be rolled back
2. **Current State Check**: Compare current assignments with rollback data
3. **Assignment Removal**: Remove assignments that were added during copy
4. **Verification**: Confirm assignments were successfully removed
5. **Cleanup**: Remove rollback data after successful completion

### Example: Copy Rollback

```bash
# Original copy operation
awsideman copy --from user:alice --to user:bob

# Later, rollback the copy
awsideman rollback execute --operation-id copy-20240816-143022-abc123
```

**Rollback Output:**
```
Rolling Back Copy Operation
==========================

Operation: copy-20240816-143022-abc123
Source: user:alice (Alice Smith)
Target: user:bob (Bob Jones)
Date: 2024-08-16 14:30:22

Analyzing current state...
✓ Found 4 assignments to remove
✓ Found 1 assignment to preserve (existed before copy)

Removing assignments added during copy:
Progress: [████████████████████] 100% (4/4)

✓ DeveloperAccess → Development (123456789012)
✓ DeveloperAccess → Staging (234567890123)
✓ ReadOnlyAccess → Production (345678901234)
✓ PowerUserAccess → Sandbox (456789012345)

Preserving pre-existing assignments:
- ReadOnlyAccess → Sandbox (456789012345) [existed before copy]

Rollback completed successfully!
Bob now has the same permissions as before the copy operation.
```

## Clone Operation Rollback

### Understanding Clone Rollback

Clone operation rollback completely removes the cloned permission set, including:
- The permission set itself
- All policies attached to it
- All assignments using the permission set
- All configuration settings

### Clone Rollback Process

1. **Dependency Check**: Identify all assignments using the cloned permission set
2. **Assignment Removal**: Remove all assignments using the permission set
3. **Policy Detachment**: Remove all attached policies
4. **Permission Set Deletion**: Delete the permission set itself
5. **Verification**: Confirm complete removal
6. **Cleanup**: Remove rollback data

### Example: Clone Rollback

```bash
# Original clone operation
awsideman clone --name PowerUserAccess --to DeveloperAccess

# Later, rollback the clone
awsideman rollback execute --operation-id clone-20240816-143522-def456
```

**Rollback Output:**
```
Rolling Back Clone Operation
===========================

Operation: clone-20240816-143522-def456
Source: PowerUserAccess
Target: DeveloperAccess
Date: 2024-08-16 14:35:22

Step 1: Analyzing dependencies
✓ Found 3 assignments using DeveloperAccess
✓ Found 2 AWS managed policies
✓ Found 2 customer managed policies
✓ Found 1 inline policy

Step 2: Removing assignments
Progress: [████████████████████] 100% (3/3)

✓ user:bob → Development (123456789012)
✓ group:junior-devs → Development (123456789012)
✓ user:alice → Staging (234567890123)

Step 3: Detaching policies
Progress: [████████████████████] 100% (5/5)

✓ AWS managed: PowerUserAccess
✓ AWS managed: IAMReadOnlyAccess
✓ Customer managed: CompanyS3Access
✓ Customer managed: CompanyLoggingAccess
✓ Inline policy removed

Step 4: Deleting permission set
✓ Permission set "DeveloperAccess" deleted

Rollback completed successfully!
Permission set "DeveloperAccess" and all its usage has been completely removed.
```

## Advanced Rollback Scenarios

### Partial Rollback

When some assignments cannot be removed (e.g., manually modified after copy):

```bash
awsideman rollback execute --operation-id copy-20240816-143022-abc123 --partial
```

**Partial Rollback Output:**
```
Partial Rollback Operation
=========================

Attempting to remove 4 assignments...

Results:
✓ DeveloperAccess → Development (123456789012)
✓ DeveloperAccess → Staging (234567890123)
✗ ReadOnlyAccess → Production (345678901234) [Assignment modified - cannot remove]
✓ PowerUserAccess → Sandbox (456789012345)

Partial rollback completed: 3/4 assignments removed
1 assignment requires manual review

Manual cleanup required for:
- ReadOnlyAccess in Production account (345678901234)
  Reason: Assignment was modified after copy operation
  Action: Review and remove manually if appropriate
```

### Cascading Rollback

When rolling back operations that depend on each other:

```bash
# If you cloned a permission set, then copied assignments using it
# Rolling back the clone will also affect the copy operations

awsideman rollback execute --operation-id clone-20240816-143522-def456 --cascade
```

### Batch Rollback

Rolling back multiple related operations:

```bash
# Rollback multiple operations in sequence
awsideman rollback execute --operation-ids "copy-123,copy-456,clone-789"

# Rollback all operations from a specific time period
awsideman rollback execute --since "2024-08-16 14:00" --until "2024-08-16 15:00"
```

## Rollback Safety and Validation

### Pre-Rollback Validation

Before executing rollback, the system validates:

1. **Operation Exists**: The rollback data is available and valid
2. **Current State**: The target entities still exist
3. **Permissions**: You have necessary permissions to remove assignments
4. **Dependencies**: No critical dependencies will be broken
5. **Data Integrity**: Rollback data hasn't been corrupted

### Rollback Preview

Always use preview mode for important rollbacks:

```bash
awsideman rollback execute --operation-id copy-20240816-143022-abc123 --preview
```

**Preview Output:**
```
Rollback Preview
===============

Operation: copy-20240816-143022-abc123
Type: Permission Copy
Target: user:bob (Bob Jones)

WILL BE REMOVED (added during copy):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ PowerUserAccess     │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

WILL BE PRESERVED (existed before copy):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Impact Analysis:
- Bob will lose access to 4 permission assignments
- Bob will retain 1 permission assignment (pre-existing)
- No other users will be affected
- No permission sets will be deleted

This is a preview - no changes will be made.
```

### Rollback Confirmation

For critical operations, the system may require confirmation:

```bash
awsideman rollback execute --operation-id clone-20240816-143522-def456
```

**Confirmation Prompt:**
```
WARNING: This will delete permission set "DeveloperAccess"
This permission set is currently assigned to 3 entities:
- user:bob in Development account
- group:junior-devs in Development account
- user:alice in Staging account

All these assignments will be removed before deleting the permission set.

Are you sure you want to proceed? (yes/no):
```

## Rollback Monitoring and Logging

### Rollback Logging

All rollback operations are comprehensively logged:

```bash
# View rollback logs
awsideman logs rollback --operation-id copy-20240816-143022-abc123

# View all rollback activity
awsideman logs rollback --all

# Export rollback logs for audit
awsideman logs rollback --export --format json > rollback-audit.json
```

### Rollback Metrics

Track rollback success rates and patterns:

```bash
# View rollback statistics
awsideman rollback stats

# View rollback success rate
awsideman rollback stats --success-rate

# View most common rollback reasons
awsideman rollback stats --reasons
```

## Rollback Best Practices

### Before Operations

1. **Plan for Rollback**: Consider rollback implications before major operations
2. **Document Operations**: Keep records of what operations you perform
3. **Test in Non-Production**: Test copy/clone operations in safe environments first
4. **Understand Dependencies**: Know what other systems depend on the permissions

### During Operations

1. **Save Operation IDs**: Keep track of operation IDs for important changes
2. **Monitor Progress**: Watch for any errors during operations
3. **Verify Results**: Check that operations completed as expected

### Rollback Execution

1. **Always Preview First**: Use `--preview` to understand rollback impact
2. **Check Current State**: Verify current permissions before rolling back
3. **Have Permissions**: Ensure you have necessary AWS permissions
4. **Plan Timing**: Execute rollbacks during maintenance windows when possible
5. **Communicate Changes**: Inform affected users about permission changes

### After Rollback

1. **Verify Results**: Confirm rollback completed as expected
2. **Test Access**: Verify that remaining permissions work correctly
3. **Update Documentation**: Record what was rolled back and why
4. **Clean Up**: Remove rollback data when no longer needed

## Emergency Rollback Procedures

### Immediate Rollback

For urgent situations requiring immediate rollback:

```bash
# Rollback latest operation immediately
awsideman rollback execute --latest --force

# Rollback specific operation without confirmation
awsideman rollback execute --operation-id <operation-id> --force --no-confirm
```

### Mass Rollback

For rolling back multiple operations quickly:

```bash
# Rollback all operations from the last hour
awsideman rollback execute --since "1 hour ago" --force

# Rollback all copy operations from today
awsideman rollback execute --type copy --since "today" --force
```

### Emergency Contact Procedures

If rollback fails and manual intervention is needed:

1. **Document the Issue**: Capture error messages and current state
2. **Escalate Appropriately**: Contact AWS administrators or security team
3. **Manual Cleanup**: Use AWS console to manually remove problematic assignments
4. **Report Issues**: File bug reports for rollback system failures

## Rollback Data Management

### Retention Policies

Configure rollback data retention based on your needs:

```bash
# Set retention policy to 60 days
awsideman rollback config --retention-days 60

# Set retention policy based on operation type
awsideman rollback config --copy-retention 30 --clone-retention 90
```

### Backup and Recovery

Backup rollback data for compliance and disaster recovery:

```bash
# Export rollback data
awsideman rollback export --output rollback-backup.json

# Import rollback data (disaster recovery)
awsideman rollback import --input rollback-backup.json
```

### Cleanup Procedures

Regular cleanup of old rollback data:

```bash
# Clean up rollback data older than 30 days
awsideman rollback cleanup --older-than 30d

# Clean up completed rollback operations
awsideman rollback cleanup --completed

# Force cleanup (remove all rollback data)
awsideman rollback cleanup --all --force
```

## Troubleshooting Rollback Issues

### Common Rollback Errors

#### Permission Denied
```
Error: Access denied: insufficient permissions to remove assignment
```

**Solutions:**
- Verify you have `sso:DeleteAccountAssignment` permission
- Check if you have permission to modify the target entity
- Use an account with appropriate administrative permissions

#### Assignment Not Found
```
Error: Assignment not found: may have been manually removed
```

**Solutions:**
- Use `--partial` flag to rollback what's possible
- Manually verify current state of assignments
- Consider the rollback partially successful

#### Permission Set In Use
```
Error: Cannot delete permission set: still has active assignments
```

**Solutions:**
- The system should handle this automatically
- If it fails, check for assignments not tracked by rollback system
- Manually remove assignments before retrying

#### Rollback Data Corrupted
```
Error: Rollback data validation failed: checksum mismatch
```

**Solutions:**
- Try to recover from backup if available
- Manually review and clean up based on operation logs
- Report the issue for investigation

### Diagnostic Commands

```bash
# Validate rollback data integrity
awsideman rollback validate --operation-id <operation-id>

# Check rollback system health
awsideman rollback health-check

# Debug rollback issues
awsideman rollback debug --operation-id <operation-id> --verbose
```

## Compliance and Auditing

### Audit Trail

Maintain comprehensive audit trails for rollback operations:

```bash
# Generate audit report
awsideman rollback audit --since "2024-08-01" --format pdf

# Export audit data
awsideman rollback audit --export --format json > audit-trail.json
```

### Compliance Reporting

Generate compliance reports for rollback activities:

```bash
# Generate compliance report
awsideman rollback compliance-report --period monthly

# Generate rollback summary for specific period
awsideman rollback summary --since "2024-08-01" --until "2024-08-31"
```

## Integration with Other Systems

### CI/CD Integration

Integrate rollback capabilities with CI/CD pipelines:

```bash
# Rollback as part of deployment failure
if deployment_failed; then
    awsideman rollback execute --latest --force
fi
```

### Monitoring Integration

Set up monitoring for rollback operations:

```bash
# Send rollback notifications
awsideman rollback execute --operation-id <operation-id> --notify slack://channel

# Log rollback metrics
awsideman rollback execute --operation-id <operation-id> --metrics-endpoint http://metrics.company.com
```

## Related Documentation

- [Permission Cloning User Guide](PERMISSION_CLONING.md)
- [Troubleshooting Guide](PERMISSION_CLONING_TROUBLESHOOTING.md)
- [Basic Rollback Examples](../examples/permission-cloning/rollback-examples/basic-rollback.md)
- [Security Best Practices](SECURITY_BEST_PRACTICES.md)
