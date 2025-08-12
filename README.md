# awsideman - AWS Identity Center Manager

A comprehensive CLI tool for managing AWS Identity Center operations at scale. Designed for enterprise environments, awsideman simplifies the management of users, groups, permission sets, and assignments across multiple AWS accounts with advanced caching, bulk operations, and security features.

## Features

### Core Identity Management
- **User Management** - Create, update, delete, and list users with filtering and pagination
- **Group Management** - Manage groups and group memberships
- **Permission Set Management** - Create and manage permission sets with policies
- **Assignment Management** - Assign and revoke permission sets to users/groups for specific accounts

### Advanced Operations
- **Bulk Operations** - Process hundreds of assignments from CSV/JSON files with human-readable names
- **Multi-Account Operations** - Assign/revoke permission sets across multiple accounts with filtering
- **AWS Organizations Integration** - Query organization structure, accounts, and policies
- **Name Resolution** - Automatic conversion of human-readable names to AWS resource identifiers
- **Access Reviews** - Export permissions for accounts, principals, or permission sets for auditing and compliance

### Performance & Caching
- **Advanced Caching System** - File-based, DynamoDB, and hybrid cache backends
- **Cache Encryption** - AES-256 encryption for sensitive cached data
- **Configurable TTL** - Flexible cache expiration policies
- **Cache Management** - Status monitoring, health checks, and maintenance commands

### Enterprise Features
- **Profile Management** - Multiple AWS credential profiles with region configuration
- **SSO Instance Configuration** - Manage multiple Identity Center instances
- **Account Filtering** - Target operations using wildcards or account tags
- **Batch Processing** - Configurable parallelism and rate limiting
- **Dry-Run Mode** - Preview changes before execution
- **Progress Tracking** - Real-time progress indicators for long-running operations

### Security & Compliance
- **Encryption at Rest** - Secure cache storage with OS keyring integration
- **Comprehensive Validation** - Input validation and error handling
- **Audit Logging** - Detailed operation logging for compliance
- **Security Best Practices** - Built-in security recommendations and warnings

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/awsideman.git
cd awsideman

# Install using Poetry
poetry install

# Or install in development mode
pip install -e .
```

## Usage

### Basic Commands

```bash
# Show help and version
awsideman --help
awsideman --version

# Configuration and setup
awsideman config validate
awsideman config show
```

### Profile Management

```bash
# Manage AWS credential profiles
awsideman profile list
awsideman profile add my-profile --region us-east-1 --default
awsideman profile update my-profile --region us-west-2
awsideman profile remove my-profile
```

### SSO Instance Management

```bash
# Configure Identity Center instances
awsideman sso list
awsideman sso set arn:aws:sso:::instance/ssoins-12345678901234567 d-12345678ab
awsideman sso info
```

### User Management

```bash
# List and filter users
awsideman user list
awsideman user list --filter UserName=john --limit 10

# Get user details
awsideman user get user-id-12345
awsideman user get john.doe@example.com

# Create and manage users
awsideman user create --username john.doe --email john.doe@example.com --given-name John --family-name Doe
awsideman user update user-id-12345 --email new.email@example.com --display-name "John Doe"
awsideman user delete user-id-12345 --force
```

### Group Management

```bash
# Manage groups and memberships
awsideman group list
awsideman group create --name Developers --description "Development team"
awsideman group add-member group-id-12345 user-id-67890
awsideman group remove-member group-id-12345 user-id-67890
```

### Permission Set Management

```bash
# Manage permission sets
awsideman permission-set list
awsideman permission-set create --name ReadOnlyAccess --description "Read-only access"
awsideman permission-set update ps-12345 --description "Updated description"
awsideman permission-set delete ps-12345
```

### Assignment Management

```bash
# Individual assignments
awsideman assignment list --account-id 123456789012
awsideman assignment assign ReadOnlyAccess john.doe --account 123456789012
awsideman assignment revoke ReadOnlyAccess john.doe --account 123456789012

# Multi-account assignments
awsideman assignment assign ReadOnlyAccess john.doe --filter "*"
awsideman assignment assign PowerUserAccess jane.smith --filter "tag:Environment=Production"
awsideman assignment revoke DeveloperAccess former.employee --filter "tag:Team=DevOps" --dry-run
```

### Bulk Operations

```bash
# Bulk assign from CSV/JSON files
awsideman bulk assign user-assignments.csv
awsideman bulk assign assignments.json --dry-run
awsideman bulk assign mixed-assignments.csv --batch-size 10

# Bulk revoke assignments
awsideman bulk revoke assignments.csv --force
awsideman bulk revoke assignments.json --stop-on-error
```

### Cache Management

```bash
# Cache status and management
awsideman cache status
awsideman cache clear --force
awsideman cache health check

# Advanced cache operations
awsideman cache warm --resource-type users
awsideman cache encryption status
awsideman cache backend test
```

### AWS Organizations

```bash
# Query organization structure
awsideman org list-accounts
awsideman org list-accounts --filter-tag Environment=Production
awsideman org get-account 123456789012
awsideman org list-policies
awsideman org tree
```

### Access Reviews

```bash
# Export permissions for specific account
awsideman access-review export-account 123456789012
awsideman access-review export-account 123456789012 --format csv --output account_permissions.csv

# Export permissions for specific principal
awsideman access-review export-principal john.doe@example.com
awsideman access-review export-principal Developers --type GROUP --format json

# Export assignments for specific permission set
awsideman access-review export-permission-set ReadOnlyAccess --format csv
```

### Example Bulk Operations File Formats

**CSV Format:**
```csv
principal_name,permission_set_name,account_name,principal_type
john.doe,ReadOnlyAccess,Production,USER
Developers,PowerUserAccess,Development,GROUP
jane.smith,AdministratorAccess,Staging,USER
```

**JSON Format:**
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

## Configuration

awsideman supports flexible configuration through YAML files and environment variables:

```yaml
# ~/.awsideman/config.yaml
cache:
  backend: "dynamodb"  # or "file" or "hybrid"
  encryption: true
  ttl:
    default: 3600
    list_users: 1800
  dynamodb:
    table_name: "awsideman-cache"
    region: "us-east-1"

profiles:
  default: "production"

logging:
  level: "INFO"
  file: "~/.awsideman/logs/awsideman.log"
```

See [CONFIGURATION.md](CONFIGURATION.md) for complete configuration options and [examples/cache-configurations/](examples/cache-configurations/) for environment-specific examples.

## Examples

The `examples/` directory contains comprehensive examples:

- **[Bulk Operations](examples/bulk-operations/)** - CSV/JSON file formats and usage patterns
- **[Multi-Account Operations](examples/multi-account-operations/)** - Account filtering, automation scripts, and enterprise workflows
- **[Cache Configurations](examples/cache-configurations/)** - Environment-specific cache setups
- **[Access Reviews](examples/access-reviews/)** - Permission export examples for auditing and compliance

## Development

```bash
# Install development dependencies
poetry install

# Run tests
poetry run pytest

# Run specific test categories
poetry run pytest tests/commands/
poetry run pytest tests/integration/
poetry run pytest tests/performance/

# Code formatting and linting
poetry run black .
poetry run isort .
poetry run ruff check .

# Type checking
poetry run mypy src/

# Validate internal imports
python scripts/validate_internal_imports.py
```

## Architecture

awsideman is built with a modular architecture:

- **Commands** - CLI command implementations
- **AWS Clients** - Cached AWS service clients
- **Cache System** - Pluggable cache backends with encryption
- **Bulk Operations** - File processing and batch operations
- **Utils** - Validation, error handling, and helper functions

## Performance

- **Caching** - Intelligent caching reduces API calls by up to 90%
- **Batch Processing** - Configurable parallelism for bulk operations
- **Name Resolution** - Cached lookups for human-readable names
- **Progress Tracking** - Real-time feedback for long-running operations

## License

MIT
