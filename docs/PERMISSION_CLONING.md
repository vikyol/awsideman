# Permission Cloning User Guide

## Overview

The Permission Cloning feature provides AWS Identity Center administrators with efficient tools to copy permission assignments between users and groups, and clone permission sets. This feature reduces manual configuration effort, ensures consistency across similar roles, and accelerates permission management workflows.

## Key Features

- **Assignment Copying**: Copy permission assignments between users and groups
- **Cross-Entity Copying**: Copy permissions from users to groups and vice versa
- **Permission Set Cloning**: Create new permission sets based on existing ones
- **Preview Mode**: See what changes will be made before executing
- **Filtering**: Selectively copy permissions based on permission sets or accounts
- **Rollback Support**: Undo operations if needed
- **Progress Reporting**: Track progress of long-running operations

## Quick Start

### Copy Permissions Between Users

```bash
# Copy all permissions from one user to another
awsideman copy --from user:john.doe --to user:jane.smith

# Preview what would be copied
awsideman copy --from user:john.doe --to user:jane.smith --preview
```

### Copy Permissions Between Groups

```bash
# Copy all permissions from one group to another
awsideman copy --from group:developers --to group:qa-team

# Preview the operation
awsideman copy --from group:developers --to group:qa-team --preview
```

### Copy Permissions Across Entity Types

```bash
# Copy permissions from a user to a group
awsideman copy --from user:john.doe --to group:new-developers

# Copy permissions from a group to a user
awsideman copy --from group:admin-team --to user:new.admin
```

### Clone Permission Sets

```bash
# Clone a permission set with a new name
awsideman clone --name PowerUserAccess --to DeveloperAccess

# Clone with a custom description
awsideman clone --name PowerUserAccess --to DeveloperAccess --description "Developer access with limited permissions"

# Preview the clone operation
awsideman clone --name PowerUserAccess --to DeveloperAccess --preview
```

## Command Reference

### Copy Command

**Syntax**: `awsideman copy --from <source> --to <target> [options]`

**Parameters**:
- `--from`: Source entity in format `user:username` or `group:groupname`
- `--to`: Target entity in format `user:username` or `group:groupname`
- `--preview`: Show detailed preview of what would be copied without making changes
- `--dry-run`: Execute operation logic but skip actual changes (alternative to preview)
- `--exclude-permission-sets`: Skip assignments for specified permission sets (e.g., exclude admin access)
- `--include-accounts`: Only copy assignments for specified AWS accounts
- `--exclude-accounts`: Skip assignments for specified AWS accounts

**Examples**:
```bash
# Basic copy operation
awsideman copy --from user:alice --to user:bob

# Copy excluding sensitive permission sets
awsideman copy --from user:senior.admin --to user:junior.dev --exclude-permission-sets "AdminAccess,BillingAccess"

# Copy with account filtering
awsideman copy --from group:developers --to group:qa-team --include-accounts "123456789012,987654321098"

# Copy excluding multiple permission sets
awsideman copy --from user:departing.employee --to user:replacement --exclude-permission-sets "FullAdminAccess,PowerUserAccess"
```

### Clone Command

**Syntax**: `awsideman clone --name <source> --to <target> [options]`

**Parameters**:
- `--name`: Name of the source permission set to clone
- `--to`: Name for the new permission set
- `--description`: Optional custom description for the new permission set
- `--preview`: Show detailed preview of what would be cloned without making changes
- `--dry-run`: Execute operation logic but skip actual changes (alternative to preview)

**Examples**:
```bash
# Basic clone operation
awsideman clone --name PowerUserAccess --to DeveloperAccess

# Clone with custom description
awsideman clone --name PowerUserAccess --to DeveloperAccess --description "Custom developer access"

# Preview clone operation
awsideman clone --name PowerUserAccess --to DeveloperAccess --preview

# Dry-run clone operation
awsideman clone --name PowerUserAccess --to DeveloperAccess --dry-run
```

## Filtering Options

### Permission Set Filtering

Use permission set filtering to exclude sensitive or inappropriate access:

```bash
# Exclude admin and billing access when copying to junior staff
awsideman copy --from user:senior.manager --to user:junior.employee --exclude-permission-sets "AdminAccess,BillingAccess"

# Exclude multiple sensitive permission sets
awsideman copy --from user:departing.admin --to user:replacement --exclude-permission-sets "FullAdminAccess,SecurityAuditAccess,BillingAccess"
```

### Account Filtering

Use account filtering to copy permissions for specific AWS accounts:

```bash
# Include only specific accounts
awsideman copy --from group:developers --to group:qa-team --include-accounts "123456789012,987654321098"

# Exclude specific accounts
awsideman copy --from group:developers --to group:qa-team --exclude-accounts "555666777888"
```

### Combining Filters

You can combine multiple filters for precise control:

```bash
# Copy permissions for specific accounts, excluding admin access
awsideman copy --from user:senior.dev --to user:junior.dev \
  --exclude-permission-sets "AdminAccess" \
  --include-accounts "123456789012,987654321098"

# Copy all permissions except admin access for non-production accounts
awsideman copy --from user:alice --to user:bob \
  --exclude-permission-sets "FullAdminAccess,PowerUserAccess" \
  --exclude-accounts "999888777666"
```

## Preview and Dry-Run Modes

Always verify operations before executing them using either preview or dry-run mode:

### Preview Mode
Shows a detailed analysis of what would be done:

```bash
# Preview copy operation
awsideman copy --from user:alice --to user:bob --preview

# Preview clone operation
awsideman clone --name PowerUserAccess --to DeveloperAccess --preview
```

Preview output shows:
- Detailed analysis of source and target
- What assignments or configurations will be copied
- Any duplicates that will be skipped
- Potential conflicts or issues
- Summary statistics and warnings

### Dry-Run Mode
Executes the operation logic without making actual changes:

```bash
# Dry-run copy operation
awsideman copy --from user:alice --to user:bob --dry-run

# Dry-run clone operation
awsideman clone --name PowerUserAccess --to DeveloperAccess --dry-run
```

Dry-run output shows:
- Step-by-step execution flow
- What would be done at each step
- Any errors that would occur
- Final results without actual changes

### When to Use Which

- **Use `--preview`** when you want a quick overview and analysis
- **Use `--dry-run`** when you want to test the full execution logic
- Both are safe and make no actual changes

## Progress Reporting

For large operations, the system provides progress updates:

```bash
# Progress is automatically shown for operations with many assignments
awsideman copy --from group:large-team --to group:new-team

# Output example:
# Copying permissions: 45/100 assignments processed (45%)
# Estimated time remaining: 2 minutes
```

## Rollback Operations

All copy and clone operations can be rolled back using the rollback system:

```bash
# List recent operations that can be rolled back
awsideman rollback list

# Rollback a specific operation
awsideman rollback execute --operation-id <operation-id>

# Rollback the most recent operation
awsideman rollback execute --latest
```

## Best Practices

### Before You Start

1. **Use Preview Mode**: Always preview operations before executing them
2. **Verify Entities**: Ensure source and target entities exist and are spelled correctly
3. **Check Permissions**: Verify you have necessary permissions to read from source and write to target
4. **Plan Filters**: Use filters to copy only the permissions you need

### During Operations

1. **Monitor Progress**: Watch progress reports for large operations
2. **Check for Errors**: Review any error messages and warnings
3. **Validate Results**: Verify the operation completed as expected

### After Operations

1. **Review Changes**: Check that the correct permissions were copied
2. **Test Access**: Verify that target entities have the expected access
3. **Document Changes**: Keep records of what was copied for audit purposes
4. **Keep Rollback Info**: Save operation IDs in case rollback is needed

### Security Considerations

1. **Principle of Least Privilege**: Only copy the minimum permissions needed
2. **Review Permissions**: Understand what permissions you're copying
3. **Use Filters**: Exclude sensitive or unnecessary permissions
4. **Audit Changes**: Review all changes in AWS Identity Center console
5. **Time-Bound Access**: Consider if copied permissions should be temporary

## Integration with Other Features

### Bulk Operations

Permission cloning works well with bulk operations:

```bash
# Use bulk operations to copy permissions to multiple targets
# (Prepare a CSV file with copy operations)
awsideman bulk process --file copy-operations.csv
```

### Multi-Account Operations

When working across multiple AWS accounts:

```bash
# Copy permissions for specific accounts only
awsideman copy --from user:alice --to user:bob --include-accounts "account1,account2"
```

### Cache Management

For better performance with large operations:

```bash
# Warm up the cache before large operations
awsideman cache warm --entities --permission-sets

# Clear cache if you encounter stale data
awsideman cache clear
```

## Next Steps

- Review the [Troubleshooting Guide](PERMISSION_CLONING_TROUBLESHOOTING.md) for common issues
- See [Examples](../examples/permission-cloning/) for detailed use case scenarios
- Check [Rollback Procedures](ROLLBACK_OPERATIONS.md) for detailed rollback information
- Read [Security Best Practices](SECURITY_BEST_PRACTICES.md) for security guidelines
