# Permission Cloning Troubleshooting Guide

## Common Error Messages and Solutions

### Entity Resolution Errors

#### Error: "User 'username' not found"

**Cause**: The specified username doesn't exist in AWS Identity Center.

**Solutions**:
1. Verify the username spelling and case sensitivity
2. Check if the user exists in AWS Identity Center console
3. Ensure you're connected to the correct AWS Identity Center instance
4. Try using the user's email address instead of username if that's how they're identified

```bash
# Verify user exists
awsideman copy --from user:john.doe --to user:jane.smith --preview

# Try with email format if usernames don't work
awsideman copy --from user:john.doe@company.com --to user:jane.smith@company.com --preview
```

#### Error: "Group 'groupname' not found"

**Cause**: The specified group name doesn't exist in AWS Identity Center.

**Solutions**:
1. Check the exact group name in AWS Identity Center console
2. Verify group name spelling and case sensitivity
3. Ensure the group hasn't been deleted or renamed

```bash
# List available groups to verify names
awsideman status check --groups

# Use exact group name from the list
awsideman copy --from group:Developers --to group:QA-Team --preview
```

### Permission Set Errors

#### Error: "Permission set 'PermissionSetName' not found"

**Cause**: The specified permission set doesn't exist.

**Solutions**:
1. Verify permission set name spelling and case sensitivity
2. Check if the permission set exists in AWS Identity Center console
3. Ensure you have permission to access the permission set

```bash
# List available permission sets
awsideman status check --permission-sets

# Use exact permission set name
awsideman clone --name PowerUserAccess --to DeveloperAccess --preview
```

#### Error: "Permission set 'TargetName' already exists"

**Cause**: Trying to clone to a permission set name that already exists.

**Solutions**:
1. Choose a different target name
2. Delete the existing permission set if it's no longer needed
3. Modify the existing permission set instead of cloning

```bash
# Use a different target name
awsideman clone --name PowerUserAccess --to DeveloperAccess-v2

# Or check what exists first
awsideman status check --permission-sets | grep DeveloperAccess
```

### Permission Errors

#### Error: "Access denied: insufficient permissions to read assignments"

**Cause**: Your AWS credentials don't have permission to read permission assignments.

**Required Permissions**:
- `sso:ListAccountAssignments`
- `sso:ListPermissionSets`
- `identitystore:ListUsers`
- `identitystore:ListGroups`

**Solutions**:
1. Contact your AWS administrator to grant necessary permissions
2. Verify your AWS credentials are correct
3. Check if you're using the right AWS profile

```bash
# Check current AWS identity
aws sts get-caller-identity

# Use specific AWS profile if needed
export AWS_PROFILE=your-profile-name
awsideman copy --from user:alice --to user:bob --preview
```

#### Error: "Access denied: insufficient permissions to create assignments"

**Cause**: Your AWS credentials don't have permission to create permission assignments.

**Required Permissions**:
- `sso:CreateAccountAssignment`
- `sso:CreatePermissionSet`
- `sso:PutInlinePolicyToPermissionSet`
- `sso:AttachManagedPolicyToPermissionSet`

**Solutions**:
1. Request additional permissions from your AWS administrator
2. Use preview mode to see what would be changed without making actual changes
3. Work with someone who has the necessary permissions

### Filter Errors

#### Error: "Invalid filter: permission set 'FilterName' not found"

**Cause**: Specified a permission set in exclude filters that doesn't exist.

**Solutions**:
1. Verify permission set names in your filters
2. Use `--preview` to validate filters before executing
3. Remove invalid permission sets from filters

```bash
# Check available permission sets first
awsideman status check --permission-sets

# Use valid permission set names in filters
awsideman copy --from user:alice --to user:bob \
  --exclude-permission-sets "AdminAccess,PowerUserAccess" \
  --preview
```

#### Error: "Invalid filter: account '123456789012' not accessible"

**Cause**: Specified an AWS account ID that you don't have access to.

**Solutions**:
1. Verify the account ID is correct
2. Ensure you have access to the specified account
3. Remove inaccessible accounts from filters

```bash
# List accessible accounts
awsideman status check --accounts

# Use only accessible account IDs
awsideman copy --from user:alice --to user:bob \
  --include-accounts "123456789012,987654321098" \
  --preview
```

### Operation Errors

#### Error: "Operation failed: partial completion with errors"

**Cause**: Some assignments were copied successfully, but others failed.

**Solutions**:
1. Review the detailed error log to identify failed assignments
2. Check if failed assignments have permission conflicts
3. Use rollback if needed, then retry with filters to exclude problematic assignments

```bash
# Check the operation log for details
awsideman rollback list

# Rollback if needed
awsideman rollback execute --operation-id <operation-id>

# Retry with filters to exclude problematic assignments
awsideman copy --from user:alice --to user:bob \
  --exclude-permission-sets "ProblematicPermissionSet"
```

#### Error: "Operation timeout: taking longer than expected"

**Cause**: Large operations may timeout due to AWS API rate limits or network issues.

**Solutions**:
1. Use filters to reduce the scope of the operation
2. Retry the operation (it will skip already completed assignments)
3. Check network connectivity and AWS service status

```bash
# Reduce scope with filters
awsideman copy --from group:large-team --to group:new-team \
  --exclude-permission-sets "AdminAccess" \
  --include-accounts "123456789012"

# Check AWS service status
aws sts get-caller-identity
```

## Performance Issues

### Slow Operations

**Symptoms**: Operations taking much longer than expected.

**Causes and Solutions**:

1. **Large number of assignments**
   - Use filters to reduce scope
   - Process in smaller batches
   - Consider using bulk operations for multiple similar operations

2. **AWS API rate limiting**
   - Operations automatically handle rate limiting
   - Reduce concurrent operations
   - Retry during off-peak hours

3. **Network connectivity issues**
   - Check internet connection
   - Verify AWS endpoint accessibility
   - Consider running from AWS environment (EC2, CloudShell)

```bash
# Use filters to reduce scope
awsideman copy --from group:large-team --to group:new-team \
  --include-permission-sets "ReadOnlyAccess" \
  --preview

# Check network connectivity
ping sso.amazonaws.com
```

### Memory Issues

**Symptoms**: Out of memory errors or system slowdown.

**Solutions**:
1. Process smaller batches of assignments
2. Clear cache between operations
3. Increase system memory if possible

```bash
# Clear cache to free memory
awsideman cache clear

# Process with smaller scope
awsideman copy --from user:alice --to user:bob \
  --exclude-permission-sets "AdminAccess" \
  --include-accounts "123456789012"
```

## Rollback Issues

### Rollback Failures

#### Error: "Rollback failed: some assignments could not be removed"

**Cause**: Permissions may have changed since the original operation, or there are dependency issues.

**Solutions**:
1. Review which assignments couldn't be removed
2. Manually remove problematic assignments through AWS console
3. Check for policy dependencies that prevent removal

```bash
# Get detailed rollback information
awsideman rollback list --detailed

# Try partial rollback for specific assignments
awsideman rollback execute --operation-id <operation-id> --partial
```

#### Error: "Rollback operation not found"

**Cause**: The rollback information may have been cleaned up or the operation ID is incorrect.

**Solutions**:
1. Verify the operation ID is correct
2. Check if rollback data has been cleaned up due to retention policies
3. Manually review and remove assignments if necessary

```bash
# List all available rollback operations
awsideman rollback list

# Check rollback retention settings
awsideman rollback status
```

## Data Consistency Issues

### Duplicate Assignments

**Symptoms**: Seeing duplicate assignments or unexpected skipped assignments.

**Solutions**:
1. This is normal behavior - duplicates are automatically skipped
2. Use preview mode to see what will be skipped
3. Review existing assignments on target entity

```bash
# Preview to see what will be skipped
awsideman copy --from user:alice --to user:bob --preview

# Check existing assignments on target
awsideman status inspect --entity user:bob
```

### Stale Cache Data

**Symptoms**: Operations showing outdated information or unexpected results.

**Solutions**:
1. Clear the cache and retry
2. Use `--no-cache` flag if available
3. Wait a few minutes for AWS eventual consistency

```bash
# Clear cache
awsideman cache clear

# Retry operation
awsideman copy --from user:alice --to user:bob --preview
```

## Debugging Steps

### Enable Verbose Logging

```bash
# Enable debug logging
export AWSIDEMAN_LOG_LEVEL=DEBUG
awsideman copy --from user:alice --to user:bob --preview

# Or use verbose flag if available
awsideman copy --from user:alice --to user:bob --preview --verbose
```

### Check System Status

```bash
# Check overall system status
awsideman status check

# Check specific components
awsideman status check --users --groups --permission-sets --accounts
```

### Validate Configuration

```bash
# Check AWS configuration
aws configure list
aws sts get-caller-identity

# Check Identity Center configuration
awsideman status check --identity-center
```

## Getting Help

### Log Collection

When reporting issues, collect these logs:

```bash
# Enable debug logging and capture output
export AWSIDEMAN_LOG_LEVEL=DEBUG
awsideman copy --from user:alice --to user:bob --preview > debug.log 2>&1

# Check system status
awsideman status check > status.log 2>&1

# Check rollback status if applicable
awsideman rollback list > rollback.log 2>&1
```

### Information to Include

When seeking help, provide:

1. **Command executed**: Exact command that failed
2. **Error message**: Complete error message and stack trace
3. **Environment**: AWS region, Identity Center instance, OS
4. **Logs**: Debug logs from the operation
5. **Context**: What you were trying to accomplish
6. **Reproduction**: Steps to reproduce the issue

### Support Channels

1. **Documentation**: Check this guide and main documentation
2. **Examples**: Review example scenarios in the examples directory
3. **Issue Tracker**: Report bugs and feature requests
4. **Community**: Ask questions in community forums

## Prevention Tips

### Before Operations

1. **Always use preview or dry-run mode first**
   - Use `--preview` for quick analysis and overview
   - Use `--dry-run` to test full execution logic
2. **Verify entity names and spelling**
3. **Check your permissions**
4. **Start with small test operations**
5. **Review filters carefully**

### During Operations

1. **Monitor progress and error messages**
2. **Don't interrupt long-running operations**
3. **Keep rollback information safe**

### After Operations

1. **Verify results in AWS console**
2. **Test that permissions work as expected**
3. **Document what was done**
4. **Clean up rollback data when no longer needed**
