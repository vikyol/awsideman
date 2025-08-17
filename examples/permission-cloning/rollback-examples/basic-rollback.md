# Basic Rollback Procedures

## Overview

Every copy and clone operation creates rollback information that allows you to undo changes. This guide covers the basic rollback procedures and best practices.

## Understanding Rollback Operations

### What Gets Tracked

- **Copy Operations**: All permission assignments that were added
- **Clone Operations**: The entire permission set that was created
- **Timestamps**: When the operation occurred
- **User Context**: Who performed the operation
- **Operation Details**: Source, target, and filters used

### Rollback Limitations

- **Rollback only removes what was added** - it doesn't restore what was already there
- **Time-sensitive** - rollback data may be cleaned up after retention period
- **Permission-dependent** - you need appropriate permissions to rollback

## Basic Rollback Commands

### List Available Rollback Operations

```bash
awsideman rollback list
```

**Expected Output:**
```
Available Rollback Operations
============================

┌──────────────────────────────┬──────────────┬─────────────────────┬─────────────────────────────────┐
│ Operation ID                 │ Type         │ Date                │ Description                     │
├──────────────────────────────┼──────────────┼─────────────────────┼─────────────────────────────────┤
│ copy-20240816-143022-abc123  │ Copy         │ 2024-08-16 14:30:22 │ user:alice → user:bob           │
│ clone-20240816-143522-def456 │ Clone        │ 2024-08-16 14:35:22 │ PowerUserAccess → DeveloperAccess│
│ copy-20240816-144022-ghi789  │ Copy         │ 2024-08-16 14:40:22 │ group:devs → group:qa           │
└──────────────────────────────┴──────────────┴─────────────────────┴─────────────────────────────────┘

Total: 3 operations available for rollback
```

### Rollback Specific Operation

```bash
awsideman rollback execute --operation-id copy-20240816-143022-abc123
```

**Expected Output:**
```
Rolling Back Operation
=====================

Operation ID: copy-20240816-143022-abc123
Type: Permission Copy
Date: 2024-08-16 14:30:22
Source: user:alice (Alice Smith)
Target: user:bob (Bob Jones)

Assignments to Remove:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ PowerUserAccess     │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Progress: [████████████████████] 100% (4/4 assignments)

Results:
✓ Removed DeveloperAccess from bob in Development (123456789012)
✓ Removed DeveloperAccess from bob in Staging (234567890123)
✓ Removed ReadOnlyAccess from bob in Production (345678901234)
✓ Removed PowerUserAccess from bob in Sandbox (456789012345)

Rollback completed successfully!
Bob Jones now has the same permissions as before the copy operation.

Operation copy-20240816-143022-abc123 has been rolled back and removed from rollback history.
```

### Rollback Latest Operation

```bash
awsideman rollback execute --latest
```

This rolls back the most recent operation without needing to specify the operation ID.

## Detailed Rollback Information

### Get Detailed Operation Information

```bash
awsideman rollback list --detailed
```

**Expected Output:**
```
Detailed Rollback Operations
===========================

Operation ID: copy-20240816-143022-abc123
Type: Permission Copy
Date: 2024-08-16 14:30:22
User: alice.admin@company.com
Source: user:alice (Alice Smith)
Target: user:bob (Bob Jones)
Filters: None

Assignments Added (will be removed on rollback):
┌─────────────────────┬─────────────────┬──────────────────────────┬─────────────────────┐
│ Permission Set      │ Account         │ Account ID               │ Assignment Status   │
├─────────────────────┼─────────────────┼──────────────────────────┼─────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │ Active              │
│ DeveloperAccess     │ Staging         │ 234567890123             │ Active              │
│ ReadOnlyAccess      │ Production      │ 345678901234             │ Active              │
│ PowerUserAccess     │ Sandbox         │ 456789012345             │ Active              │
└─────────────────────┴─────────────────┴──────────────────────────┴─────────────────────┘

Assignments Skipped (will not be affected by rollback):
┌─────────────────────┬─────────────────┬──────────────────────────┬─────────────────────┐
│ Permission Set      │ Account         │ Account ID               │ Reason              │
├─────────────────────┼─────────────────┼──────────────────────────┼─────────────────────┤
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │ Already existed     │
└─────────────────────┴─────────────────┴──────────────────────────┴─────────────────────┘

---

Operation ID: clone-20240816-143522-def456
Type: Permission Set Clone
Date: 2024-08-16 14:35:22
User: alice.admin@company.com
Source: PowerUserAccess
Target: DeveloperAccess
Description: "Developer access with limited permissions"

Permission Set Created (will be deleted on rollback):
- Name: DeveloperAccess
- Description: Developer access with limited permissions
- Session Duration: PT8H
- Relay State URL: https://console.aws.amazon.com/
- AWS Managed Policies: 2
- Customer Managed Policies: 2
- Inline Policy: Yes (156 characters)

Current Assignments (will be removed before deletion):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Entity              │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ user:bob            │ Development     │ 123456789012             │
│ group:junior-devs   │ Development     │ 123456789012             │
└─────────────────────┴─────────────────┴──────────────────────────┘
```

### Check Specific Operation Details

```bash
awsideman rollback inspect --operation-id copy-20240816-143022-abc123
```

## Preview Rollback Operations

### Preview What Will Be Rolled Back

```bash
awsideman rollback execute --operation-id copy-20240816-143022-abc123 --preview
```

**Expected Output:**
```
Rollback Preview
===============

Operation ID: copy-20240816-143022-abc123
Type: Permission Copy
Date: 2024-08-16 14:30:22

The following assignments will be REMOVED from user:bob (Bob Jones):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ PowerUserAccess     │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

The following assignments will NOT be affected (were not added by this operation):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Summary:
- 4 assignments will be removed
- 1 assignment will remain (existed before copy)
- Bob will have 1 assignment remaining after rollback

This is a preview - no changes will be made.
To execute this rollback, run:
awsideman rollback execute --operation-id copy-20240816-143022-abc123
```

## Permission Set Clone Rollback

### Rollback Permission Set Creation

```bash
awsideman rollback execute --operation-id clone-20240816-143522-def456
```

**Expected Output:**
```
Rolling Back Permission Set Clone
================================

Operation ID: clone-20240816-143522-def456
Type: Permission Set Clone
Date: 2024-08-16 14:35:22
Source: PowerUserAccess
Target: DeveloperAccess

Checking for existing assignments...
Found 2 assignments using this permission set.

Step 1: Removing assignments that use this permission set
Progress: [████████████████████] 100% (2/2 assignments)

✓ Removed DeveloperAccess from user:bob in Development (123456789012)
✓ Removed DeveloperAccess from group:junior-devs in Development (123456789012)

Step 2: Removing permission set policies
Progress: [████████████████████] 100% (5/5 policies)

✓ Detached AWS managed policy: PowerUserAccess
✓ Detached AWS managed policy: IAMReadOnlyAccess
✓ Detached customer managed policy: CompanyS3Access
✓ Detached customer managed policy: CompanyLoggingAccess
✓ Removed inline policy

Step 3: Deleting permission set
✓ Deleted permission set "DeveloperAccess"

Rollback completed successfully!
Permission set "DeveloperAccess" and all its assignments have been completely removed.

Operation clone-20240816-143522-def456 has been rolled back and removed from rollback history.
```

## Partial Rollback

### When Full Rollback Isn't Possible

Sometimes you can't rollback everything (e.g., some assignments were manually modified). In these cases, you can do a partial rollback:

```bash
awsideman rollback execute --operation-id copy-20240816-143022-abc123 --partial
```

**Expected Output:**
```
Partial Rollback Operation
=========================

Operation ID: copy-20240816-143022-abc123
Type: Permission Copy
Date: 2024-08-16 14:30:22

Attempting to remove assignments...

Progress: [████████████████████] 100% (4/4 assignments)

Results:
✓ Removed DeveloperAccess from bob in Development (123456789012)
✓ Removed DeveloperAccess from bob in Staging (234567890123)
✗ Failed to remove ReadOnlyAccess from bob in Production (345678901234)
  Error: Assignment not found (may have been manually removed)
✓ Removed PowerUserAccess from bob in Sandbox (456789012345)

Partial rollback completed!
3 of 4 assignments were successfully removed.
1 assignment could not be removed (see errors above).

The operation remains in rollback history in case you want to retry later.
```

## Rollback Best Practices

### Before Rolling Back

1. **Verify the operation** you want to rollback
2. **Check current state** of the target entity
3. **Use preview mode** to see what will be removed
4. **Ensure you have permissions** to remove assignments
5. **Consider the impact** on users who may be using the permissions

### During Rollback

1. **Monitor the progress** for any errors
2. **Don't interrupt** the rollback process
3. **Review any error messages** carefully

### After Rollback

1. **Verify the rollback completed** as expected
2. **Check the target entity** has the expected permissions
3. **Test that remaining permissions** still work
4. **Document the rollback** for audit purposes

## Common Rollback Scenarios

### Emergency Rollback

When you need to quickly undo a problematic operation:

```bash
# Rollback the most recent operation immediately
awsideman rollback execute --latest

# Or rollback a specific problematic operation
awsideman rollback execute --operation-id copy-20240816-143022-abc123
```

### Planned Rollback

When you're testing or need to undo a temporary change:

```bash
# Preview first to confirm what will be removed
awsideman rollback execute --operation-id copy-20240816-143022-abc123 --preview

# Execute the rollback
awsideman rollback execute --operation-id copy-20240816-143022-abc123
```

### Cleanup Rollback

When cleaning up old test operations:

```bash
# List old operations
awsideman rollback list

# Rollback multiple operations
awsideman rollback execute --operation-id test-operation-1
awsideman rollback execute --operation-id test-operation-2
```

## Troubleshooting Rollback Issues

### Operation Not Found

**Error:** `Rollback operation 'copy-20240816-143022-abc123' not found`

**Causes:**
- Operation ID is incorrect
- Rollback data has been cleaned up
- Operation was already rolled back

**Solutions:**
```bash
# List available operations
awsideman rollback list

# Check if operation was already rolled back
awsideman rollback list --history
```

### Permission Denied

**Error:** `Access denied: insufficient permissions to remove assignments`

**Solutions:**
- Ensure you have `sso:DeleteAccountAssignment` permission
- Check if you have permission to modify the target entity
- Contact your AWS administrator for necessary permissions

### Assignment Not Found

**Error:** `Assignment not found: may have been manually removed`

**Solutions:**
- Use `--partial` flag to rollback what's possible
- Manually verify the current state of assignments
- Consider the rollback partially successful

### Permission Set In Use

**Error:** `Cannot delete permission set: still has active assignments`

**Solutions:**
- The rollback process should handle this automatically
- If it fails, manually remove assignments first
- Contact support if the issue persists

## Rollback Data Management

### Retention Policy

Rollback data is typically retained for:
- **30 days** by default
- **Configurable** based on your organization's policy
- **Automatically cleaned up** after retention period

### Manual Cleanup

```bash
# Clean up old rollback data (if supported)
awsideman rollback cleanup --older-than 30d

# Remove specific rollback data after successful verification
awsideman rollback remove --operation-id copy-20240816-143022-abc123
```

## Related Examples

- [Copy Operations](../basic-operations/user-to-user-copy.md)
- [Clone Operations](../basic-operations/permission-set-cloning.md)
- [Filtered Operation Rollback](filtered-operation-rollback.md)
- [Troubleshooting Guide](../../PERMISSION_CLONING_TROUBLESHOOTING.md)
