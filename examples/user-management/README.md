# User Management Examples

This directory contains examples for managing users in AWS Identity Center using awsideman.

## Get User Details with Group Memberships

The `user get` command now displays comprehensive user information including all group memberships in a single view.

### Basic Usage

```bash
# Get user details by username (includes group memberships)
poetry run awsideman user get john.doe

# Get user details by email (includes group memberships)
poetry run awsideman user get admin@example.com

# Get user details by user ID (includes group memberships)
poetry run awsideman user get 12345678-1234-1234-1234-123456789012
```

### Advanced Options

```bash
# Use a specific AWS profile
poetry run awsideman user get developer --profile dev-account

# Get user details across different environments
poetry run awsideman user get admin@company.com --profile production
poetry run awsideman user get admin@company.com --profile staging
```

### Output Format

The command displays comprehensive user information including:

**User Details:**
- User ID, Username, Display Name
- Contact information (emails, phone numbers, addresses)
- Status and timestamps
- Custom attributes

**Group Memberships:**
- Group ID
- Group Name (Display Name)
- Description
- Membership ID

### Use Cases

- **Access Reviews**: See complete user profile including all group memberships
- **Troubleshooting**: Understand user access and group assignments in one view
- **Compliance**: Audit user information and group memberships for security reviews
- **User Lifecycle**: Verify complete user profile during onboarding/offboarding
- **Multi-account**: Get user details across different AWS profiles and regions

### Examples

```bash
# Check complete profile of a new employee
poetry run awsideman user get sarah.johnson

# Verify admin user complete profile
poetry run awsideman user get admin@company.com

# Audit user across multiple accounts
poetry run awsideman user get john.doe --profile eu-account
poetry run awsideman user get john.doe --profile us-account
```

### Benefits of Integration

By integrating group memberships into the `user get` command:

- **Single Command**: Get all user information in one operation
- **Better UX**: No need to run separate commands for user details and group memberships
- **Consistent Output**: All user information displayed in a unified format
- **Efficient Workflow**: Streamlined user management operations
