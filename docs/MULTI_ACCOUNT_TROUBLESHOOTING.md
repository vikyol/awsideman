# Multi-Account Operations Troubleshooting Guide

This guide helps you diagnose and resolve common issues when using awsideman's multi-account operations.

## Common Error Scenarios

### 1. Account Filter Errors

#### Error: "No accounts found matching filter"

**Symptoms:**
```
❌ Error: No accounts found matching filter: tag:Environment=Prod
```

**Causes:**
- Incorrect tag key or value
- Accounts don't have the specified tags
- Insufficient Organizations permissions

**Solutions:**

1. **Verify tag existence:**
   ```bash
   # List all accounts to see available tags
   awsideman org list-accounts --show-tags
   ```

2. **Check tag case sensitivity:**
   ```bash
   # Tags are case-sensitive
   --filter "tag:Environment=Production"  # ✅ Correct
   --filter "tag:environment=production"  # ❌ Wrong case
   ```

3. **Verify Organizations permissions:**
   ```bash
   # Test Organizations access
   aws organizations list-accounts --profile your-profile
   ```

#### Error: "Invalid filter expression"

**Symptoms:**
```
❌ Error: Invalid filter expression: tag:Environment
```

**Causes:**
- Missing tag value in filter expression
- Incorrect filter syntax

**Solutions:**

1. **Use correct tag filter syntax:**
   ```bash
   # Correct format
   --filter "tag:Key=Value"

   # Common mistakes
   --filter "tag:Key"           # ❌ Missing value
   --filter "Key=Value"         # ❌ Missing 'tag:' prefix
   --filter "tag Key=Value"     # ❌ Space instead of colon
   ```

### 2. Permission Resolution Errors

#### Error: "Permission set not found"

**Symptoms:**
```
❌ Error: Permission set 'ReadOnlyAcces' not found
```

**Causes:**
- Typo in permission set name
- Permission set doesn't exist
- Insufficient SSO permissions

**Solutions:**

1. **List available permission sets:**
   ```bash
   awsideman permission-set list
   ```

2. **Check for typos:**
   ```bash
   # Common typos
   ReadOnlyAcces  → ReadOnlyAccess
   PowerUserAcess → PowerUserAccess
   ```

3. **Verify SSO permissions:**
   ```bash
   # Test SSO access
   aws sso-admin list-permission-sets --instance-arn your-instance-arn
   ```

#### Error: "Principal not found"

**Symptoms:**
```
❌ Error: Principal 'john.doe' not found
```

**Causes:**
- User doesn't exist in Identity Center
- Incorrect username format
- User is in external identity provider

**Solutions:**

1. **List available users:**
   ```bash
   awsideman user list
   ```

2. **Check username format:**
   ```bash
   # Try different formats
   john.doe
   john.doe@company.com
   "John Doe"
   ```

3. **Verify user exists:**
   ```bash
   awsideman user get john.doe
   ```

### 3. Processing Errors

#### Error: "Rate limit exceeded"

**Symptoms:**
```
⚠️  Rate limit exceeded for account 123456789012. Retrying in 5 seconds...
```

**Causes:**
- Too many concurrent requests
- Large batch size
- Other tools making simultaneous requests

**Solutions:**

1. **Reduce batch size:**
   ```bash
   # Reduce from default 10 to 5
   --batch-size 5
   ```

2. **Wait and retry:**
   ```bash
   # The tool automatically retries with exponential backoff
   # Wait for the operation to complete
   ```

3. **Schedule during off-peak hours:**
   ```bash
   # Run large operations during low-traffic periods
   ```

#### Error: "Access denied for account"

**Symptoms:**
```
❌ Failed to process account 123456789012: Access denied
```

**Causes:**
- Insufficient permissions in target account
- Account is suspended or closed
- Cross-account trust issues

**Solutions:**

1. **Check account status:**
   ```bash
   awsideman org list-accounts | grep 123456789012
   ```

2. **Verify cross-account permissions:**
   ```bash
   # Ensure your role has access to the target account
   aws sts assume-role --role-arn arn:aws:iam::123456789012:role/YourRole
   ```

3. **Skip problematic accounts:**
   ```bash
   # Use more specific filters to exclude problematic accounts
   --filter "tag:Environment=Production,Status=Active"
   ```

### 4. Authentication Errors

#### Error: "SSO session expired"

**Symptoms:**
```
❌ Error: SSO session has expired. Please re-authenticate.
```

**Solutions:**

1. **Re-authenticate with SSO:**
   ```bash
   aws sso login --profile your-profile
   ```

2. **Verify profile configuration:**
   ```bash
   aws configure list --profile your-profile
   ```

#### Error: "Invalid AWS credentials"

**Symptoms:**
```
❌ Error: Unable to locate credentials
```

**Solutions:**

1. **Set AWS profile:**
   ```bash
   export AWS_PROFILE=your-profile
   # or
   --profile your-profile
   ```

2. **Verify credentials:**
   ```bash
   aws sts get-caller-identity --profile your-profile
   ```

### 5. Performance Issues

#### Issue: "Operation is very slow"

**Symptoms:**
- Long processing times
- High memory usage
- Frequent timeouts

**Solutions:**

1. **Optimize batch size:**
   ```bash
   # For large operations, use smaller batches
   --batch-size 5
   ```

2. **Use more specific filters:**
   ```bash
   # Instead of wildcard
   --filter "*"

   # Use specific tags
   --filter "tag:Environment=Production"
   ```

3. **Monitor system resources:**
   ```bash
   # Check memory usage
   top -p $(pgrep -f awsideman)
   ```

#### Issue: "Memory usage is too high"

**Solutions:**

1. **Reduce batch size:**
   ```bash
   --batch-size 3
   ```

2. **Process in smaller chunks:**
   ```bash
   # Process different environments separately
   awsideman assignment assign PermSet user --filter "tag:Environment=Dev"
awsideman assignment assign PermSet user --filter "tag:Environment=Prod"
   ```

## Diagnostic Commands

### Check System Status

```bash
# Verify AWS connectivity
aws sts get-caller-identity

# Check SSO instance
aws sso-admin list-instances

# List available accounts
awsideman org list-accounts

# Test permission set access
awsideman permission-set list

# Test user access
awsideman user list
```

### Debug Mode

Enable verbose logging for detailed error information:

```bash
# Set debug logging
export AWSIDEMAN_LOG_LEVEL=DEBUG

# Run with verbose output
awsideman assignment assign PermSet user --filter "*" --dry-run -v
```

### Validate Configuration

```bash
# Check configuration
awsideman config show

# Validate cache settings
awsideman cache status

# Test Organizations integration
awsideman org tree
```

## Error Recovery Strategies

### Partial Failure Recovery

When some accounts fail during processing:

1. **Review the failure summary:**
   ```
   📊 Results Summary:
      • Total Accounts: 50
      • Successful: 45
      • Failed: 5
      • Failed Accounts: [123456789012, 123456789013, ...]
   ```

2. **Retry failed accounts individually:**
   ```bash
   # Process failed accounts one by one
   awsideman assignment assign PermSet user --account 123456789012
   awsideman assignment assign PermSet user --account 123456789013
   ```

3. **Investigate specific failures:**
   ```bash
   # Check account status
   awsideman org get-account 123456789012

   # Verify permissions
   awsideman assignment list --account 123456789012
   ```

### Complete Failure Recovery

When the entire operation fails:

1. **Check prerequisites:**
   ```bash
   # Verify authentication
   aws sts get-caller-identity

   # Check SSO access
   aws sso-admin list-instances

   # Verify Organizations access
   aws organizations list-accounts
   ```

2. **Start with dry-run:**
   ```bash
   # Always test with dry-run first
   awsideman assignment assign PermSet user --filter "tag:Env=Test" --dry-run
   ```

3. **Use smaller scope:**
   ```bash
   # Test with a single account first
   awsideman assignment assign PermSet user --account 123456789012
   ```

## Prevention Best Practices

### Pre-Operation Checklist

Before running multi-account operations:

- [ ] Verify AWS authentication (`aws sts get-caller-identity`)
- [ ] Test with `--dry-run` first
- [ ] Use specific filters instead of wildcards
- [ ] Start with small batch sizes
- [ ] Ensure sufficient permissions
- [ ] Check account filter returns expected accounts
- [ ] Verify permission set and principal names exist

### Monitoring and Alerting

Set up monitoring for:

- Failed operations
- High error rates
- Performance degradation
- Rate limiting events
- Authentication failures

### Documentation and Runbooks

Maintain documentation for:

- Common filter patterns for your organization
- Standard permission sets and their purposes
- Emergency procedures for failed operations
- Contact information for account owners
- Escalation procedures for access issues

## Getting Help

### Log Collection

When reporting issues, collect:

```bash
# Enable debug logging
export AWSIDEMAN_LOG_LEVEL=DEBUG

# Run the failing command
awsideman assignment assign PermSet user --filter "*" --dry-run > debug.log 2>&1

# Include system information
aws --version >> debug.log
python --version >> debug.log
awsideman --version >> debug.log
```

### Support Information

Include in support requests:

- Complete error messages
- Command that failed
- Account filter used
- Number of target accounts
- AWS region and SSO instance
- Debug logs (sanitized)
- System information (OS, Python version, awsideman version)

### Community Resources

- GitHub Issues: Report bugs and feature requests
- Documentation: Check for updates and examples
- AWS Support: For AWS-specific issues
- Internal Support: Contact your organization's AWS administrators
