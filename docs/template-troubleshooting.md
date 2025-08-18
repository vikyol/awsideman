# Template Troubleshooting Guide

## Common Issues and Solutions

This guide helps you resolve common problems when working with AWS Identity Center templates.

## Template Parsing Issues

### Invalid YAML/JSON Format

**Symptoms:**
- Error: "Invalid YAML format" or "Invalid JSON format"
- Template fails to load

**Common Causes:**
- Incorrect indentation in YAML
- Missing quotes around values with special characters
- Trailing commas in JSON
- Mixed tabs and spaces

**Solutions:**
1. Use a YAML/JSON validator to check syntax
2. Ensure consistent indentation (2 spaces recommended)
3. Quote values containing special characters
4. Remove trailing commas in JSON

**Example Fix:**
```yaml
# Incorrect
metadata:
  name: my template  # Space in name without quotes
  tags:
    environment: production
    team: backend

# Correct
metadata:
  name: "my template"  # Quoted name
  tags:
    environment: "production"
    team: "backend"
```

### File Not Found

**Symptoms:**
- Error: "Template file not found"
- File path issues

**Solutions:**
1. Check file path is correct
2. Use absolute paths if needed
3. Verify file exists and is readable
4. Check file permissions

**Example:**
```bash
# Check if file exists
ls -la ./templates/my-template.yaml

# Use absolute path
awsideman templates validate /full/path/to/template.yaml
```

## Validation Issues

### Missing Required Fields

**Symptoms:**
- Error: "Required field missing"
- Template validation fails

**Required Fields:**
- `metadata.name`
- `metadata.description`
- `assignments` (non-empty list)

**Example Fix:**
```yaml
# Incorrect - missing description
metadata:
  name: "my-template"

# Correct
metadata:
  name: "my-template"
  description: "Template description"
```

### Invalid Entity Format

**Symptoms:**
- Error: "Invalid entity format"
- Entity resolution fails

**Correct Format:**
- Users: `user:username`
- Groups: `group:groupname`

**Example Fix:**
```yaml
# Incorrect
entities:
  - "john.doe"        # Missing user: prefix
  - "developers"      # Missing group: prefix

# Correct
entities:
  - "user:john.doe"
  - "group:developers"
```

### Permission Set Not Found

**Symptoms:**
- Error: "Permission set not found"
- Validation fails on permission sets

**Solutions:**
1. Check permission set name spelling
2. Verify permission set exists in AWS Identity Center
3. Use exact permission set names
4. Check AWS profile and region

**Example:**
```bash
# List available permission sets
aws sso list-permission-sets --instance-arn <instance-arn>

# Get permission set details
aws sso describe-permission-set \
  --instance-arn <instance-arn> \
  --permission-set-arn <permission-set-arn>
```

### Account Resolution Issues

**Symptoms:**
- Error: "Account not found"
- Tag-based targeting fails

**Solutions:**
1. Verify account IDs are correct (12 digits)
2. Check account tags exist and are spelled correctly
3. Ensure AWS credentials have access to accounts
4. Verify account is part of the organization

**Example:**
```bash
# List accounts in organization
aws organizations list-accounts

# Check account tags
aws organizations list-tags-for-resource --resource-id <account-id>
```

## AWS Connection Issues

### No SSO Instance Found

**Symptoms:**
- Error: "No SSO instances found"
- Cannot connect to AWS Identity Center

**Solutions:**
1. Check AWS credentials and profile
2. Verify region has SSO enabled
3. Ensure user has SSO permissions
4. Check SSO instance configuration

**Example:**
```bash
# Check AWS profile
aws configure list --profile <profile-name>

# List SSO instances
aws sso list-instances --region <region>
```

### Permission Denied

**Symptoms:**
- Error: "Permission denied"
- "Insufficient permissions"

**Solutions:**
1. Check IAM user/role permissions
2. Verify SSO permissions
3. Check cross-account role configuration
4. Ensure proper AWS profile

**Required Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sso:ListInstances",
        "sso:ListPermissionSets",
        "sso:ListAccounts",
        "sso:CreateAccountAssignment",
        "sso:DeleteAccountAssignment"
      ],
      "Resource": "*"
    }
  ]
}
```

### Network/Connection Issues

**Symptoms:**
- Error: "Connection timeout"
- "Request timeout"
- "DNS resolution failed"

**Solutions:**
1. Check network connectivity
2. Verify firewall settings
3. Check proxy configuration
4. Increase timeout settings

**Example:**
```bash
# Test AWS connectivity
aws sts get-caller-identity

# Check network to AWS endpoints
ping sso.amazonaws.com
```

## Template Execution Issues

### Assignment Already Exists

**Symptoms:**
- Warning: "Assignment already exists"
- Some assignments skipped

**Solutions:**
1. Use `--dry-run` to preview first
2. Check existing assignments
3. Remove conflicting assignments first
4. Use different permission sets

**Example:**
```bash
# Preview what would happen
awsideman templates apply template.yaml --dry-run

# List existing assignments
aws sso list-account-assignments \
  --instance-arn <instance-arn> \
  --account-id <account-id>
```

### Partial Failures

**Symptoms:**
- Some assignments succeed, others fail
- Mixed success/failure results

**Solutions:**
1. Review error messages for each failure
2. Check individual account permissions
3. Verify entity existence in each account
4. Use verbose output for details

**Example:**
```bash
# Apply with verbose output
awsideman templates apply template.yaml --verbose

# Check specific account access
aws sts get-caller-identity --profile <profile>
```

### Rate Limiting

**Symptoms:**
- Error: "Rate limit exceeded"
- "ThrottlingException"

**Solutions:**
1. Wait and retry
2. Reduce batch size in configuration
3. Use exponential backoff
4. Contact AWS support if persistent

**Configuration:**
```bash
# Set smaller batch size
awsideman config templates set execution.batch_size 5

# Enable parallel execution
awsideman config templates set execution.parallel_execution false
```

## Configuration Issues

### Template Directory Not Found

**Symptoms:**
- Error: "Template directory not found"
- Cannot save/load templates

**Solutions:**
1. Create template directory
2. Set correct path in configuration
3. Check directory permissions

**Example:**
```bash
# Create template directory
mkdir -p ~/.awsideman/templates

# Set in configuration
awsideman config templates set storage_directory ~/.awsideman/templates

# Check configuration
awsideman config templates show
```

### Invalid Configuration Values

**Symptoms:**
- Error: "Invalid configuration value"
- Configuration validation fails

**Valid Values:**
- `default_format`: "yaml" or "json"
- `batch_size`: 1-1000
- Boolean values: "true", "false", "1", "0"

**Example:**
```bash
# Set valid values
awsideman config templates set default_format yaml
awsideman config templates set execution.batch_size 10
awsideman config templates set execution.parallel_execution true

# Reset to defaults
awsideman config templates reset
```

## Debugging Tips

### Enable Verbose Output

Use the `--verbose` flag for detailed information:

```bash
awsideman templates validate template.yaml --verbose
awsideman templates preview template.yaml --verbose
awsideman templates apply template.yaml --verbose
```

### Check AWS Configuration

Verify AWS setup:

```bash
# Check credentials
aws sts get-caller-identity

# Check SSO configuration
aws sso list-instances

# Check organization access
aws organizations list-accounts
```

### Validate Template Structure

Use external validators:

```bash
# YAML validation
python -c "import yaml; yaml.safe_load(open('template.yaml'))"

# JSON validation
python -c "import json; json.load(open('template.json'))"
```

### Test with Simple Template

Start with a minimal template:

```yaml
metadata:
  name: "test-template"
  description: "Test template for debugging"

assignments:
  - entities:
      - "user:testuser"
    permission_sets:
      - "ReadOnlyAccess"
    targets:
      account_ids:
        - "123456789012"
```

## Getting Help

### Command Help

```bash
# General help
awsideman templates --help

# Command-specific help
awsideman templates validate --help
awsideman templates apply --help
```

### Error Reporting

When reporting issues, include:

1. Template content (sanitized)
2. Exact error message
3. AWS profile and region
4. Command used
5. awsideman version

### Useful Commands

```bash
# Check version
awsideman --version

# Show configuration
awsideman config show

# Validate configuration
awsideman config validate

# List templates
awsideman templates list

# Show template details
awsideman templates show template-name
```

## Prevention Best Practices

### Template Design

1. **Start Simple**: Begin with basic templates and add complexity
2. **Test First**: Always validate before applying
3. **Use Dry Run**: Preview changes before execution
4. **Version Control**: Track template changes

### Security

1. **Least Privilege**: Grant minimum necessary access
2. **Review Regularly**: Audit templates periodically
3. **Document Purpose**: Clear descriptions for each template
4. **Test Safely**: Use development accounts for testing

### Maintenance

1. **Keep Updated**: Regular template reviews
2. **Clean Up**: Remove unused templates
3. **Monitor Usage**: Track template applications
4. **Backup**: Version control for templates
