# Access Reviews Examples

This directory contains examples for using the basic access reviews feature in awsideman.

## Overview

The access reviews feature provides basic functionality to export permissions for:
- Specific AWS accounts
- Specific principals (users or groups)
- Specific permission sets

This is a simplified implementation focused on data export rather than the comprehensive access review workflow outlined in the full specification.

## Commands

### Export Account Permissions

Export all permissions assigned to a specific AWS account:

```bash
# Basic table output
awsideman access-review export-account 123456789012

# JSON output
awsideman access-review export-account 123456789012 --format json

# CSV output to file
awsideman access-review export-account 123456789012 --format csv --output account_permissions.csv

# Include inactive assignments
awsideman access-review export-account 123456789012 --include-inactive
```

### Export Principal Permissions

Export all permissions for a specific user or group:

```bash
# Export user permissions across all accounts (requires Organizations access)
awsideman access-review export-principal john.doe@example.com

# Export user permissions for a specific account (works without Organizations access)
awsideman access-review export-principal john.doe@example.com --account-id 123456789012

# Export group permissions
awsideman access-review export-principal Developers --type GROUP --account-id 123456789012

# Auto-detect principal type (searches users first, then groups)
awsideman access-review export-principal AdminGroup --account-id 123456789012

# JSON output
awsideman access-review export-principal jane.smith --format json --account-id 123456789012

# CSV output to file
awsideman access-review export-principal PowerUsers --format csv --output user_permissions.csv --account-id 123456789012
```

### Export Permission Set Assignments

Export all assignments for a specific permission set:

```bash
# Basic table output across all accounts (requires Organizations access)
awsideman access-review export-permission-set ReadOnlyAccess

# Export for a specific account (works without Organizations access)
awsideman access-review export-permission-set ReadOnlyAccess --account-id 123456789012

# JSON output
awsideman access-review export-permission-set PowerUserAccess --format json --account-id 123456789012

# CSV output to file
awsideman access-review export-permission-set AdministratorAccess --format csv --output admin_assignments.csv --account-id 123456789012
```

## Output Formats

### Table Format (Default)

Displays results in a formatted table with columns:
- Account (name and ID)
- Principal (name)
- Type (USER or GROUP)
- Permission Set (name)
- Status

### JSON Format

Structured JSON output including:
- Export metadata (timestamp, totals)
- Detailed assignment information
- Principal and permission set details

### CSV Format

CSV file with columns:
- account_id
- account_name
- principal_id
- principal_name
- principal_type
- permission_set_arn
- permission_set_name
- permission_set_description
- status
- export_timestamp

## Use Cases

### Security Audits

```bash
# Export all permissions for a production account
awsideman access-review export-account 123456789012 --format csv --output prod_audit.csv

# Review permissions for privileged users in a specific account
awsideman access-review export-principal admin.user@company.com --format json --account-id 123456789012

# Review permissions for privileged users across all accounts (requires Organizations access)
awsideman access-review export-principal admin.user@company.com --format json
```

### Compliance Reporting

```bash
# Generate reports for all admin permission sets in a specific account
awsideman access-review export-permission-set AdministratorAccess --format csv --output admin_report.csv --account-id 123456789012
awsideman access-review export-permission-set PowerUserAccess --format csv --output power_user_report.csv --account-id 123456789012

# Generate reports across all accounts (requires Organizations access)
awsideman access-review export-permission-set AdministratorAccess --format csv --output admin_report_all_accounts.csv
```

### Access Reviews

```bash
# Review permissions for departing employee in a specific account
awsideman access-review export-principal former.employee@company.com --format table --account-id 123456789012

# Review permissions for departing employee across all accounts (requires Organizations access)
awsideman access-review export-principal former.employee@company.com --format table

# Review group memberships and permissions
awsideman access-review export-principal ContractorGroup --type GROUP --format json --account-id 123456789012
```

## Working with Organizations Access Limitations

### Account-Specific Queries (Recommended)

If you don't have AWS Organizations access, use the `--account-id` option to target specific accounts:

```bash
# Works without Organizations access
awsideman access-review export-principal john.doe@example.com --account-id 123456789012
awsideman access-review export-permission-set ReadOnlyAccess --account-id 123456789012

# Requires Organizations access (will show warning if not available)
awsideman access-review export-principal john.doe@example.com
awsideman access-review export-permission-set ReadOnlyAccess
```

### Multi-Account Workflows

For multi-account environments without Organizations access, you can script the account-specific commands:

```bash
#!/bin/bash
# Script to check permissions across multiple accounts
ACCOUNTS=("123456789012" "234567890123" "345678901234")
PRINCIPAL="admin.user@company.com"

for account in "${ACCOUNTS[@]}"; do
    echo "Checking account: $account"
    awsideman access-review export-principal "$PRINCIPAL" --account-id "$account" --format csv --output "permissions_${account}.csv"
done
```

## Limitations

This basic implementation has some limitations compared to the full access reviews specification:

1. **No Workflow Management**: No scheduling, reminders, or approval workflows
2. **No Historical Tracking**: No tracking of review decisions or changes over time
3. **Organizations Access**: Cross-account enumeration requires AWS Organizations read permissions (use `--account-id` for single-account queries)
4. **No Recommendations**: No intelligent suggestions for access optimization
5. **No Web Interface**: Command-line only

## Future Enhancements

The full access reviews specification includes additional features that could be implemented:

- Scheduled review workflows
- Approval and revocation capabilities
- Historical audit trails
- Intelligent access recommendations
- Web-based user interface
- Integration with notification systems
- Automated compliance reporting

## Configuration

The access reviews commands use the same configuration as other awsideman commands:

```bash
# Configure AWS profile and SSO instance
awsideman profile add my-profile --region us-east-1
awsideman sso set arn:aws:sso:::instance/ssoins-123 d-123456789

# Use specific profile
awsideman access-review export-account 123456789012 --profile my-profile
```

## Error Handling

Common error scenarios and solutions:

### Profile Not Configured
```
Error: No profile specified and no default profile set.
```
**Solution**: Configure a profile with `awsideman profile add` and set as default.

### SSO Instance Not Configured
```
Error: No SSO instance configured for this profile.
```
**Solution**: Configure SSO instance with `awsideman sso set`.

### Principal Not Found
```
Error: Principal 'username' not found
```
**Solution**: Verify the principal name and type. Use exact usernames or group display names.

### Permission Set Not Found
```
Error: Permission set 'PermissionSetName' not found
```
**Solution**: Verify the permission set name matches exactly (case-sensitive).

### Organizations Access Issues
```
Warning: Unable to access AWS Organizations. Cannot enumerate all accounts.
```
**Solution**: Ensure the AWS credentials have Organizations read permissions, or specify account IDs directly for account-specific queries.
