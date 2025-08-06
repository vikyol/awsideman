# Bulk Operations Documentation

This document provides comprehensive guidance for using the bulk operations feature in awsideman CLI.

## Overview

The bulk operations feature allows you to efficiently manage multiple permission set assignments using input files with human-readable names. The system automatically resolves names to AWS resource identifiers and provides preview, validation, and progress tracking capabilities.

## Key Features

- **Human-Readable Names**: Use principal names, permission set names, and account names instead of IDs/ARNs
- **Automatic Resolution**: Names are automatically resolved to AWS resource identifiers
- **Multiple Formats**: Support for both CSV and JSON input formats
- **Preview Mode**: See what changes will be made before applying them
- **Dry-Run Validation**: Validate input files without making any changes
- **Batch Processing**: Configurable parallel processing for better performance
- **Error Handling**: Continue processing on errors or stop on first failure
- **Progress Tracking**: Real-time progress updates with Rich terminal output
- **Comprehensive Reporting**: Detailed success/failure reports with error details

## Commands

### bulk assign

Bulk assign permission sets from input file using human-readable names.

```bash
awsideman bulk assign [OPTIONS] INPUT_FILE
```

**Options:**
- `--dry-run`: Validate input and show preview without making changes
- `--continue-on-error/--stop-on-error`: Continue processing on individual failures (default: continue)
- `--batch-size INTEGER`: Number of assignments to process in parallel (1-50, default: 10)
- `--profile TEXT`: AWS profile to use (uses default if not specified)
- `--help`: Show help message and exit

### bulk revoke

Bulk revoke permission sets from input file using human-readable names.

```bash
awsideman bulk revoke [OPTIONS] INPUT_FILE
```

**Options:**
- `--dry-run`: Validate input and show preview without making changes
- `--continue-on-error/--stop-on-error`: Continue processing on individual failures (default: continue)
- `--batch-size INTEGER`: Number of assignments to process in parallel (1-50, default: 10)
- `--force, -f`: Skip confirmation prompts and proceed automatically
- `--profile TEXT`: AWS profile to use (uses default if not specified)
- `--help`: Show help message and exit

## File Formats

### CSV Format

**Required Columns:**
- `principal_name`: Name of the user or group (human-readable identifier)
- `permission_set_name`: Name of the permission set (human-readable identifier)
- `account_name`: Name of the AWS account (human-readable identifier)

**Optional Columns:**
- `principal_type`: Type of principal ("USER" or "GROUP", defaults to "USER")
- `account_id`: AWS account ID (will be resolved from name if not provided)
- `permission_set_arn`: ARN of the permission set (will be resolved from name if not provided)
- `principal_id`: ID of the user or group (for reference, will be resolved from name)

**Example CSV:**
```csv
principal_name,permission_set_name,account_name,principal_type
john.doe,ReadOnlyAccess,Production,USER
Developers,PowerUserAccess,Development,GROUP
jane.smith,AdministratorAccess,Staging,USER
DevOps-Team,AdministratorAccess,Production,GROUP
```

### JSON Format

The JSON format uses a structured format with an `assignments` array.

**Required Fields:**
- `principal_name`: Name of the user or group
- `permission_set_name`: Name of the permission set
- `account_name`: Name of the AWS account

**Optional Fields:**
- `principal_type`: Type of principal ("USER" or "GROUP", defaults to "USER")
- `account_id`: AWS account ID
- `permission_set_arn`: ARN of the permission set
- `principal_id`: ID of the user or group

**Example JSON:**
```json
{
  "assignments": [
    {
      "principal_name": "john.doe",
      "permission_set_name": "ReadOnlyAccess",
      "account_name": "Production",
      "principal_type": "USER"
    },
    {
      "principal_name": "Developers",
      "permission_set_name": "PowerUserAccess",
      "account_name": "Development",
      "principal_type": "GROUP"
    }
  ]
}
```

## Name Resolution

The bulk operations feature automatically resolves human-readable names to AWS resource identifiers:

### Resolution Process

1. **Principal Names** → **Principal IDs**
   - Uses AWS Identity Store API to find users and groups
   - Searches by username for users and display name for groups
   - Results are cached for performance

2. **Permission Set Names** → **Permission Set ARNs**
   - Uses AWS SSO Admin API to find permission sets
   - Searches by permission set name
   - Results are cached for performance

3. **Account Names** → **Account IDs**
   - Uses AWS Organizations API to find accounts
   - Searches by account name
   - Results are cached for performance

### Caching

- Resolution results are cached during processing to improve performance
- Multiple assignments for the same principal/permission set/account reuse cached values
- Cache is automatically cleared between different bulk operations
- Large files benefit significantly from caching

## Usage Examples

### Basic Operations

```bash
# Assign permission sets from CSV file
awsideman bulk assign user-assignments.csv

# Assign permission sets from JSON file
awsideman bulk assign assignments.json

# Revoke permission sets from CSV file
awsideman bulk revoke user-assignments.csv
```

### Validation and Preview

```bash
# Validate input file without making changes
awsideman bulk assign assignments.csv --dry-run

# Preview revoke operations before applying
awsideman bulk revoke assignments.csv --dry-run
```

### Error Handling

```bash
# Continue processing on individual errors (default)
awsideman bulk assign assignments.csv --continue-on-error

# Stop processing on first error
awsideman bulk assign assignments.csv --stop-on-error
```

### Performance Tuning

```bash
# Use smaller batch size for rate-limited environments
awsideman bulk assign assignments.csv --batch-size 5

# Use larger batch size for better throughput
awsideman bulk assign assignments.csv --batch-size 20
```

### Profile Management

```bash
# Use specific AWS profile
awsideman bulk assign assignments.csv --profile production

# Use profile with dry-run
awsideman bulk assign assignments.csv --profile staging --dry-run
```

### Automation

```bash
# Skip confirmation prompts for automated workflows
awsideman bulk revoke assignments.csv --force

# Combine with other options for fully automated processing
awsideman bulk revoke assignments.csv --force --continue-on-error --batch-size 10
```

## Error Handling and Troubleshooting

### Common Issues

#### Name Resolution Errors

**Problem**: Names cannot be resolved to AWS resource identifiers

**Solutions**:
- Verify names match exactly (case-sensitive)
- Check AWS credentials have required permissions
- Ensure profile is configured for correct organization
- Verify resources exist in the target AWS environment

**Required Permissions**:
- Identity Store: `identitystore:ListUsers`, `identitystore:ListGroups`
- SSO Admin: `sso:ListPermissionSets`
- Organizations: `organizations:ListAccounts`

#### Rate Limiting

**Problem**: AWS API rate limits are exceeded

**Solutions**:
- Reduce batch size using `--batch-size 5`
- Check AWS service quotas and limits
- Implement delays between operations if needed
- Contact AWS support for quota increases if necessary

#### File Format Errors

**Problem**: Input file format is invalid

**Solutions**:
- Verify CSV has required columns with correct headers
- Ensure JSON follows the required schema structure
- Check for missing required fields
- Validate file encoding (UTF-8 recommended)

#### Permission Errors

**Problem**: Insufficient AWS permissions

**Solutions**:
- Verify Identity Store read access
- Verify SSO Admin read/write access
- Verify Organizations read access
- Check IAM policies and permission boundaries

### Error Types

#### Validation Errors

- **Missing Required Fields**: Empty principal_name, permission_set_name, or account_name
- **Invalid File Format**: Malformed CSV or JSON structure
- **Schema Violations**: JSON doesn't match required schema

#### Resolution Errors

- **Principal Not Found**: Principal name doesn't exist in Identity Store
- **Permission Set Not Found**: Permission set name doesn't exist
- **Account Not Found**: Account name doesn't exist in organization
- **Multiple Matches**: Name matches multiple resources (ambiguous)

#### Operation Errors

- **Assignment Already Exists**: For assign operations (logged as warning)
- **Assignment Doesn't Exist**: For revoke operations (logged as warning)
- **API Errors**: AWS service errors or network issues
- **Permission Denied**: Insufficient permissions for operation

### Debugging Tips

1. **Use Dry-Run Mode**: Always test with `--dry-run` first
2. **Check Logs**: Review error messages for specific issues
3. **Verify Names**: Ensure names match exactly (case-sensitive)
4. **Test Small Batches**: Start with small files to identify issues
5. **Check Permissions**: Verify AWS credentials and permissions
6. **Monitor Rate Limits**: Use smaller batch sizes if needed

## Performance Optimization

### Batch Size Guidelines

- **Small files** (< 100 assignments): Use default batch size (10)
- **Medium files** (100-1000 assignments): Consider batch size 10-15
- **Large files** (> 1000 assignments): Use batch size 5-10 and monitor for rate limiting

### Memory Considerations

- Files are processed in chunks to avoid memory issues
- Large files are handled efficiently with streaming processing
- Resolution caching reduces memory usage for repeated names

### Network Optimization

- Connection pooling is used for AWS API calls
- Retry logic with exponential backoff handles transient errors
- Parallel processing improves throughput while respecting rate limits

## Best Practices

### File Preparation

1. **Validate Names**: Ensure all names exist in AWS before processing
2. **Use Consistent Naming**: Follow consistent naming conventions
3. **Test with Small Files**: Start with small test files
4. **Backup Data**: Keep backups of assignment data

### Processing Strategy

1. **Use Dry-Run**: Always validate with `--dry-run` first
2. **Start Small**: Begin with small batch sizes
3. **Monitor Progress**: Watch for errors and rate limiting
4. **Handle Errors**: Use appropriate error handling mode

### Security Considerations

1. **Least Privilege**: Use minimal required AWS permissions
2. **Secure Files**: Protect input files containing sensitive data
3. **Audit Logs**: Review operation logs for security compliance
4. **Profile Management**: Use appropriate AWS profiles for different environments

### Automation Integration

1. **Error Handling**: Implement proper error handling in scripts
2. **Logging**: Capture and store operation logs
3. **Monitoring**: Monitor for failures and performance issues
4. **Rollback Plans**: Have rollback procedures for failed operations

## Integration Examples

### CI/CD Pipeline

```bash
#!/bin/bash
# Example CI/CD integration script

# Validate assignments file
if ! awsideman bulk assign assignments.csv --dry-run; then
    echo "Validation failed, aborting deployment"
    exit 1
fi

# Apply assignments with error handling
if awsideman bulk assign assignments.csv --continue-on-error --batch-size 5; then
    echo "Bulk assignment completed successfully"
else
    echo "Bulk assignment failed, check logs"
    exit 1
fi
```

### Monitoring Script

```bash
#!/bin/bash
# Example monitoring script

LOG_FILE="/var/log/awsideman-bulk.log"

# Run bulk operation with logging
awsideman bulk assign assignments.csv --batch-size 10 2>&1 | tee -a "$LOG_FILE"

# Check for errors
if grep -q "Error" "$LOG_FILE"; then
    echo "Errors detected in bulk operation"
    # Send alert or notification
fi
```

## Support and Resources

### Getting Help

```bash
# Get general help for bulk operations
awsideman bulk --help

# Get specific help for assign command
awsideman bulk assign --help

# Get specific help for revoke command
awsideman bulk revoke --help
```

### Example Files

See the `examples/bulk-operations/` directory for sample input files:
- `sample-user-assignments.csv` - Basic user assignments
- `sample-group-assignments.csv` - Group assignments
- `mixed-assignments.csv` - Mixed user and group assignments
- `validation-errors.csv` - Examples with validation errors

### Additional Documentation

- [Configuration Guide](CONFIGURATION.md) - AWS profile and SSO setup
- [Security Best Practices](SECURITY_BEST_PRACTICES.md) - Security guidelines
- [Environment Variables](ENVIRONMENT_VARIABLES.md) - Configuration options