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

awsideman provides multiple filtering strategies to target specific accounts for multi-account operations:

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

### Organizational Unit (OU) Filtering

Target accounts based on their organizational structure. This is particularly useful for enterprises with well-defined organizational hierarchies:

```bash
# Target accounts in the Security organizational unit
awsideman assignment assign SecurityAuditor john.doe --ou-filter "Root/Security"

# Target accounts in nested organizational units
awsideman assignment assign DeveloperAccess dev.team --ou-filter "Root/Development/TeamA"

# Target accounts in the Production OU
awsideman assignment assign ReadOnlyAccess monitoring.user --ou-filter "Root/Production"
```

**Important Notes:**
- OU paths must include the "Root" prefix (e.g., "Root/Security", not just "Security")
- OU paths are case-sensitive and must match your organization's exact structure
- Use `awsideman org tree` to view your organization's OU structure

### Regex Pattern Filtering

Filter accounts by name patterns using regular expressions:

```bash
# Target all production accounts (names containing "prod")
awsideman assignment assign ReadOnlyAccess john.doe --account-pattern "prod-.*"

# Target accounts with specific naming conventions
awsideman assignment assign AdminAccess admin.user --account-pattern ".*-prod-.*"

# Target staging accounts
awsideman assignment assign DeveloperAccess dev.team --account-pattern "staging-.*"

# Target accounts in specific regions
awsideman assignment assign ReadOnlyAccess john.doe --account-pattern ".*-us-east-1"
```

**Regex Pattern Examples:**
- `prod-.*` - Accounts starting with "prod-"
- `.*-prod-.*` - Accounts containing "-prod-" anywhere in the name
- `staging-.*` - Accounts starting with "staging-"
- `.*-us-east-1` - Accounts ending with "-us-east-1"

### Explicit Account List

Specify exact account IDs for precise targeting:

```bash
# Target specific accounts by ID
awsideman assignment assign ReadOnlyAccess john.doe --accounts "123456789012,987654321098"

# Target a single account
awsideman assignment assign AdminAccess admin.user --accounts "123456789012"

# Target multiple accounts with mixed formats
awsideman assignment assign DeveloperAccess dev.team \
  --accounts "123456789012,987654321098,111111111111"
```

### Combined Filtering Strategies

You can combine different filtering approaches for complex scenarios:

```bash
# Target production accounts in the Security OU
awsideman assignment assign SecurityAuditor john.doe \
  --ou-filter "Root/Security" \
  --filter "tag:Environment=Production"

# Target accounts with specific names in Development OU
awsideman assignment assign DeveloperAccess dev.team \
  --ou-filter "Root/Development" \
  --account-pattern "dev-.*"
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

### Example 6: Organizational Unit (OU) Filtering

Assign permissions to accounts in specific organizational units:

```bash
# Assign SecurityAuditor to john.doe across all Security OU accounts
awsideman assignment assign SecurityAuditor john.doe --ou-filter "Root/Security"
```

**Expected Output:**
```
Account Filter: Accounts in organizational unit: Root/Security
Found 3 account(s) matching filter criteria.

Accounts to be processed:
  1. Security-Monitoring (123456789012)
  2. Security-Logs (987654321098)
  3. Security-Audit (111111111111)

🔍 Resolving permission set: SecurityAuditor
✅ Permission set ARN: arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-fedcba0987654321

🔍 Resolving principal: john.doe
✅ Principal ID: 12345678-1234-1234-1234-123456789012

📋 Multi-Account Assignment Preview:
   • Permission Set: SecurityAuditor
   • Principal: john.doe (USER)
   • Target Accounts: 3
   • Operation: ASSIGN

Processing accounts... ████████████████████████████████████████ 3/3 (100%)

✅ Multi-account assignment completed successfully!

📊 Results Summary:
   • Total Accounts: 3
   • Successful: 3
   • Failed: 0
   • Success Rate: 100%
   • Duration: 15s
```

### Example 7: Regex Pattern Filtering

Target accounts using name patterns:

```bash
# Assign ReadOnlyAccess to monitoring users across all production accounts
awsideman assignment assign ReadOnlyAccess monitoring.user --account-pattern "prod-.*"
```

**Expected Output:**
```
Account Filter: Accounts matching pattern: prod-.*
Found 8 account(s) matching filter criteria.

Accounts to be processed:
  1. prod-web-01 (123456789012)
  2. prod-web-02 (123456789013)
  3. prod-api-01 (123456789014)
  4. prod-api-02 (123456789015)
  5. prod-db-01 (123456789016)
  6. prod-db-02 (123456789017)
  7. prod-cache-01 (123456789018)
  8. prod-cache-02 (123456789019)

🔍 Resolving permission set: ReadOnlyAccess
✅ Permission set ARN: arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef

🔍 Resolving principal: monitoring.user
✅ Principal ID: 87654321-4321-4321-4321-210987654321

📋 Multi-Account Assignment Preview:
   • Permission Set: ReadOnlyAccess
   • Principal: monitoring.user (USER)
   • Target Accounts: 8
   • Operation: ASSIGN

Processing accounts... ████████████████████████████████████████ 8/8 (100%)

✅ Multi-account assignment completed successfully!

📊 Results Summary:
   • Total Accounts: 8
   • Successful: 8
   • Failed: 0
   • Success Rate: 100%
   • Duration: 45s
```

### Example 8: Explicit Account List

Target specific accounts by ID:

```bash
# Assign DeveloperAccess to dev.team across specific development accounts
awsideman assignment assign DeveloperAccess dev.team \
  --accounts "123456789012,987654321098,111111111111"
```

**Expected Output:**
```
Account Filter: Explicit account list: 3 accounts
Found 3 account(s) matching filter criteria.

Accounts to be processed:
  1. dev-web-01 (123456789012)
  2. dev-api-01 (987654321098)
  3. dev-db-01 (111111111111)

🔍 Resolving permission set: DeveloperAccess
✅ Permission set ARN: arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-fedcba0987654321

🔍 Resolving principal: dev.team
✅ Principal ID: 11111111-2222-3333-4444-555555555555

📋 Multi-Account Assignment Preview:
   • Permission Set: DeveloperAccess
   • Principal: dev.team (GROUP)
   • Target Accounts: 3
   • Operation: ASSIGN

Processing accounts... ████████████████████████████████████████ 3/3 (100%)

✅ Multi-account assignment completed successfully!

📊 Results Summary:
   • Total Accounts: 3
   • Successful: 3
   • Failed: 0
   • Success Rate: 100%
   • Duration: 20s
```

### Example 9: Combined Filtering Strategies

Use multiple filtering approaches for complex scenarios:

```bash
# Assign SecurityAuditor to audit.user across Production accounts in Security OU
awsideman assignment assign SecurityAuditor audit.user \
  --ou-filter "Root/Security" \
  --filter "tag:Environment=Production"
```

**Expected Output:**
```
Account Filter: Accounts in organizational unit: Root/Security with tag: Environment=Production
Found 2 account(s) matching filter criteria.

Accounts to be processed:
  1. Security-Prod-Monitoring (123456789012) - Environment=Production
  2. Security-Prod-Logs (987654321098) - Environment=Production

🔍 Resolving permission set: SecurityAuditor
✅ Permission set ARN: arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-fedcba0987654321

🔍 Resolving principal: audit.user
✅ Principal ID: 22222222-3333-4444-5555-666666666666

📋 Multi-Account Assignment Preview:
   • Permission Set: SecurityAuditor
   • Principal: audit.user (USER)
   • Target Accounts: 2
   • Operation: ASSIGN

Processing accounts... ████████████████████████████████████████ 2/2 (100%)

✅ Multi-account assignment completed successfully!

📊 Results Summary:
   • Total Accounts: 2
   • Successful: 2
   • Failed: 0
   • Success Rate: 100%
   • Duration: 12s
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

### Large-Scale Operation Optimization

For operations targeting hundreds or thousands of accounts, consider these strategies:

#### 1. **Progressive Scaling**
Start with smaller batch sizes and gradually increase:

```bash
# Start with small batch size for initial testing
awsideman assignment assign ReadOnlyAccess john.doe --filter "*" --batch-size 5 --dry-run

# Increase batch size for production run
awsideman assignment assign ReadOnlyAccess john.doe --filter "*" --batch-size 15
```

#### 2. **Time-Based Execution**
Run large operations during off-peak hours:

```bash
# Run during low-traffic periods
awsideman assignment assign ReadOnlyAccess john.doe \
  --filter "*" \
  --batch-size 20 \
  --continue-on-error
```

#### 3. **Chunked Processing**
Break large operations into smaller chunks using specific filters:

```bash
# Process by environment instead of all at once
awsideman assignment assign ReadOnlyAccess john.doe --filter "tag:Environment=Production"
awsideman assignment assign ReadOnlyAccess john.doe --filter "tag:Environment=Development"
awsideman assignment assign ReadOnlyAccess john.doe --filter "tag:Environment=Staging"
```

#### 4. **Resource Monitoring**
Monitor system resources during large operations:

```bash
# Use smaller batch size if memory is constrained
awsideman assignment assign ReadOnlyAccess john.doe \
  --filter "*" \
  --batch-size 10 \
  --continue-on-error
```

### Performance Benchmarks

Typical performance metrics for different account counts:

| Account Count | Batch Size | Estimated Duration | Memory Usage |
|---------------|------------|-------------------|--------------|
| 10-50         | 15         | 30s - 2m          | Low          |
| 50-200        | 10         | 2m - 8m           | Medium       |
| 200-500       | 8          | 8m - 25m          | High         |
| 500+          | 5          | 25m+              | Very High    |

### Caching Impact

The built-in caching system significantly improves performance:

- **First run**: Full API calls to resolve accounts and permissions
- **Subsequent runs**: Cached data reduces API calls by 80-90%
- **Cache warming**: Use `awsideman cache warm` to pre-populate cache

```bash
# Warm cache before large operations
awsideman cache warm --resource-type accounts
awsideman cache warm --resource-type permission-sets

# Then run the operation
awsideman assignment assign ReadOnlyAccess john.doe --filter "*"
```

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

### Enterprise Use Cases

#### 1. **New Employee Onboarding**

Automate permission assignment for new employees based on their role and team:

```bash
#!/bin/bash
# onboard-employee.sh

EMPLOYEE_NAME=$1
TEAM=$2
ROLE=$3

echo "Onboarding employee: $EMPLOYEE_NAME (Team: $TEAM, Role: $ROLE)"

# Assign basic read access to all accounts
awsideman assignment assign ReadOnlyAccess "$EMPLOYEE_NAME" --filter "*"

# Assign team-specific access based on organizational structure
case $TEAM in
  "Security")
    awsideman assignment assign SecurityAuditor "$EMPLOYEE_NAME" --ou-filter "Root/Security"
    ;;
  "Development")
    awsideman assignment assign DeveloperAccess "$EMPLOYEE_NAME" --ou-filter "Root/Development"
    ;;
  "Operations")
    awsideman assignment assign OperationsAccess "$EMPLOYEE_NAME" --ou-filter "Root/Operations"
    ;;
esac

# Assign role-specific permissions
case $ROLE in
  "Admin")
    awsideman assignment assign AdminAccess "$EMPLOYEE_NAME" --filter "tag:Environment=Development"
    ;;
  "Developer")
    awsideman assignment assign DeveloperAccess "$EMPLOYEE_NAME" --filter "tag:Environment=Development"
    ;;
  "ReadOnly")
    echo "Read-only access already assigned"
    ;;
esac

echo "Onboarding completed for $EMPLOYEE_NAME"
```

#### 2. **Environment-Based Access Management**

Manage access based on environment and organizational structure:

```bash
#!/bin/bash
# manage-environment-access.sh

ENVIRONMENT=$1
ACTION=$2  # "grant" or "revoke"
PERMISSION_SET=$3
PRINCIPAL=$4

echo "Managing $ENVIRONMENT environment access: $ACTION $PERMISSION_SET for $PRINCIPAL"

case $ACTION in
  "grant")
    # Grant access to production accounts in specific OUs
    if [ "$ENVIRONMENT" = "Production" ]; then
      awsideman assignment assign "$PERMISSION_SET" "$PRINCIPAL" \
        --ou-filter "Root/Production" \
        --filter "tag:Environment=Production"
    else
      awsideman assignment assign "$PERMISSION_SET" "$PRINCIPAL" \
        --filter "tag:Environment=$ENVIRONMENT"
    fi
    ;;
  "revoke")
    # Revoke access from specific environment
    if [ "$ENVIRONMENT" = "Production" ]; then
      awsideman assignment revoke "$PERMISSION_SET" "$PRINCIPAL" \
        --ou-filter "Root/Production" \
        --filter "tag:Environment=Production"
    else
      awsideman assignment revoke "$PERMISSION_SET" "$PRINCIPAL" \
        --filter "tag:Environment=$ENVIRONMENT"
    fi
    ;;
esac

echo "Environment access management completed"
```

#### 3. **Compliance and Audit Operations**

Automate compliance-related permission assignments:

```bash
#!/bin/bash
# compliance-access.sh

COMPLIANCE_TYPE=$1
ACTION=$2

echo "Managing compliance access: $COMPLIANCE_TYPE - $ACTION"

case $COMPLIANCE_TYPE in
  "SOX")
    # Assign SOX compliance access to audit team
    if [ "$ACTION" = "grant" ]; then
      awsideman assignment assign SOXAuditor "audit.team" \
        --ou-filter "Root/Finance" \
        --filter "tag:Compliance=SOX"
    else
      awsideman assignment revoke SOXAuditor "audit.team" \
        --ou-filter "Root/Finance" \
        --filter "tag:Compliance=SOX"
    fi
    ;;
  "PCI")
    # Assign PCI compliance access to security team
    if [ "$ACTION" = "grant" ]; then
      awsideman assignment assign PCIAuditor "security.team" \
        --ou-filter "Root/Security" \
        --filter "tag:Compliance=PCI"
    else
      awsideman assignment revoke PCIAuditor "security.team" \
        --ou-filter "Root/Security" \
        --filter "tag:Compliance=PCI"
    fi
    ;;
esac

echo "Compliance access management completed"
```

#### 4. **Scheduled Maintenance Operations**

Automate periodic permission reviews and updates:

```bash
#!/bin/bash
# scheduled-permission-review.sh

# Run this script via cron for automated permission management

echo "Starting scheduled permission review: $(date)"

# Revoke access from terminated employees (example)
awsideman assignment revoke ReadOnlyAccess "terminated.employee" --filter "*"

# Grant temporary access for contractors
awsideman assignment assign ContractorAccess "contractor.user" \
  --filter "tag:Environment=Development" \
  --filter "tag:AccessType=Temporary"

# Update monitoring access for operations team
awsideman assignment assign MonitoringAccess "ops.team" \
  --ou-filter "Root/Operations" \
  --filter "tag:Environment=Production"

echo "Scheduled permission review completed: $(date)"
```

### CI/CD Integration Examples

#### GitHub Actions Workflow

```yaml
name: Manage AWS SSO Access

on:
  workflow_dispatch:
    inputs:
      username:
        description: 'Username to manage'
        required: true
      action:
        description: 'Action to perform'
        required: true
        default: 'grant'
        type: choice
        options:
        - grant
        - revoke
      permission_set:
        description: 'Permission set name'
        required: true
      environment:
        description: 'Target environment'
        required: true
        default: 'Development'

jobs:
  manage-access:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install awsideman
      run: |
        pip install awsideman

    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1

    - name: Manage SSO Access
      run: |
        if [ "${{ inputs.action }}" = "grant" ]; then
          awsideman assignment assign "${{ inputs.permission_set }}" "${{ inputs.username }}" \
            --filter "tag:Environment=${{ inputs.environment }}" \
            --dry-run

          awsideman assignment assign "${{ inputs.permission_set }}" "${{ inputs.username }}" \
            --filter "tag:Environment=${{ inputs.environment }}"
        else
          awsideman assignment revoke "${{ inputs.permission_set }}" "${{ inputs.username }}" \
            --filter "tag:Environment=${{ inputs.environment }}"
        fi
```

#### GitLab CI Pipeline

```yaml
stages:
  - validate
  - execute

variables:
  AWSIDEMAN_VERSION: "latest"

validate-access:
  stage: validate
  script:
    - pip install awsideman==$AWSIDEMAN_VERSION
    - awsideman assignment assign $PERMISSION_SET $USERNAME \
        --filter "tag:Environment=$ENVIRONMENT" \
        --dry-run
  only:
    - merge_requests

execute-access:
  stage: execute
  script:
    - pip install awsideman==$AWSIDEMAN_VERSION
    - awsideman assignment assign $PERMISSION_SET $USERNAME \
        --filter "tag:Environment=$ENVIRONMENT"
  only:
    - main
  when: manual
```

## Troubleshooting Common Issues

### OU Filter Issues

#### "No accounts found matching the filter criteria"

**Common Causes:**
1. **Incorrect OU path format**: OU paths must include "Root" prefix
2. **Case sensitivity**: OU paths are case-sensitive
3. **Missing OU path data**: Some accounts may not have OU path information

**Solutions:**
```bash
# Check your organization structure
awsideman org tree

# Use correct OU path format
awsideman assignment assign ReadOnlyAccess john.doe --ou-filter "Root/Security"  # ✅ Correct
awsideman assignment assign ReadOnlyAccess john.doe --ou-filter "Security"       # ❌ Incorrect

# Verify OU paths for specific accounts
awsideman org get-account 123456789012
```

#### "NetworkOperation: 0" Error

This error typically indicates an issue with the OU filter logic. The fix has been implemented in recent versions.

**If you encounter this error:**
1. Update to the latest version of awsideman
2. Ensure you're using the correct OU path format (e.g., "Root/Security")
3. Check that your AWS credentials are valid and have the necessary permissions

### Regex Pattern Issues

#### Pattern Not Matching Expected Accounts

**Common Issues:**
1. **Incorrect regex syntax**: Ensure your pattern is valid regex
2. **Case sensitivity**: Regex patterns are case-sensitive by default
3. **Special characters**: Escape special regex characters properly

**Solutions:**
```bash
# Test your regex pattern
awsideman assignment assign ReadOnlyAccess john.doe --account-pattern "prod-.*" --dry-run

# Use case-insensitive patterns if needed
awsideman assignment assign ReadOnlyAccess john.doe --account-pattern "(?i)prod-.*" --dry-run

# Escape special characters
awsideman assignment assign ReadOnlyAccess john.doe --account-pattern "prod\-.*" --dry-run
```

### Performance Issues

#### Slow Account Resolution

**Common Causes:**
1. **Large account count**: Organizations with hundreds of accounts
2. **Network latency**: Slow AWS API responses
3. **Cache miss**: First-time operations require full API calls

**Solutions:**
```bash
# Warm cache before large operations
awsideman cache warm --resource-type accounts

# Use smaller batch sizes for large operations
awsideman assignment assign ReadOnlyAccess john.doe --filter "*" --batch-size 5

# Run during off-peak hours
awsideman assignment assign ReadOnlyAccess john.doe --filter "*" --batch-size 10
```

#### Memory Issues During Large Operations

**Symptoms:**
- Operation fails with memory errors
- System becomes unresponsive
- High memory usage in system monitor

**Solutions:**
```bash
# Reduce batch size
awsideman assignment assign ReadOnlyAccess john.doe --filter "*" --batch-size 3

# Process in smaller chunks
awsideman assignment assign ReadOnlyAccess john.doe --filter "tag:Environment=Production"
awsideman assignment assign ReadOnlyAccess john.doe --filter "tag:Environment=Development"
awsideman assignment assign ReadOnlyAccess john.doe --filter "tag:Environment=Staging"
```

### Permission Issues

#### "Access Denied" Errors

**Common Causes:**
1. **Insufficient SSO Admin permissions**
2. **Missing Organizations permissions**
3. **Expired AWS credentials**

**Required Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "sso:ListPermissionSets",
        "sso:CreateAccountAssignment",
        "sso:DeleteAccountAssignment",
        "sso:ListAccountAssignments"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "organizations:ListAccounts",
        "organizations:ListTagsForResource",
        "organizations:DescribeAccount"
      ],
      "Resource": "*"
    }
  ]
}
```

**Solutions:**
```bash
# Check your current permissions
aws sts get-caller-identity

# Verify SSO instance access
awsideman sso info

# Test basic operations
awsideman org list-accounts
```

### Debugging Tips

#### Enable Verbose Logging

```bash
# Set logging level to DEBUG
export AWSIDEMAN_LOG_LEVEL=DEBUG

# Run command with verbose output
awsideman assignment assign ReadOnlyAccess john.doe --ou-filter "Root/Security" --dry-run
```

#### Use Dry-Run Mode

Always test with `--dry-run` before executing:

```bash
# Test the operation first
awsideman assignment assign ReadOnlyAccess john.doe --ou-filter "Root/Security" --dry-run

# Execute after verification
awsideman assignment assign ReadOnlyAccess john.doe --ou-filter "Root/Security"
```

#### Check Cache Status

```bash
# Verify cache is working
awsideman cache status

# Clear cache if needed
awsideman cache clear --force

# Warm cache for better performance
awsideman cache warm --resource-type accounts
```

## Next Steps

After mastering multi-account operations:

1. Explore [bulk operations](BULK_OPERATIONS.md) for CSV-based assignments
2. Learn about [caching strategies](../examples/cache-configurations/README.md) for performance optimization
3. Review [security best practices](SECURITY_BEST_PRACTICES.md) for enterprise deployments
4. Set up [monitoring and alerting](MONITORING.md) for large-scale operations
5. Practice with different filtering strategies in your environment
6. Set up automation scripts for common multi-account operations
