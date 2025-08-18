# Template Format Documentation

## Overview

AWS Identity Center templates provide a declarative way to manage permission assignments across multiple accounts. Templates are YAML or JSON files that define who gets what access to which accounts.

## Template Structure

A template consists of two main sections:

1. **Metadata** - Information about the template
2. **Assignments** - The actual permission assignments to be created

### Basic Template Structure

```yaml
metadata:
  name: "template-name"
  description: "Template description"
  version: "1.0"
  author: "Author Name"
  # ... other metadata fields

assignments:
  - entities: ["user:username", "group:groupname"]
    permission_sets: ["PermissionSetName"]
    targets:
      account_ids: ["123456789012"]
      # or
      account_tags:
        Environment: "production"
```

## Metadata Section

The metadata section provides information about the template and its purpose.

### Required Fields

- **name** (string): Unique identifier for the template
- **description** (string): Human-readable description of what the template does

### Optional Fields

- **version** (string): Template version (default: "1.0")
- **author** (string): Who created the template
- **created_at** (datetime): When the template was created
- **updated_at** (datetime): When the template was last updated
- **tags** (object): Key-value pairs for categorization

### Metadata Example

```yaml
metadata:
  name: "developer-access"
  description: "Standard developer access for development accounts"
  version: "1.0"
  author: "DevOps Team"
  created_at: "2024-01-15T10:00:00Z"
  updated_at: "2024-01-15T10:00:00Z"
  tags:
    environment: "development"
    team: "developers"
    access_level: "standard"
```

## Assignments Section

The assignments section defines the actual permission assignments to be created.

### Assignment Structure

Each assignment has three components:

1. **entities**: Who gets access (users and/or groups)
2. **permission_sets**: What access they get
3. **targets**: Which accounts they get access to

### Entities

Entities can be specified in two formats:

- **Users**: `user:username`
- **Groups**: `group:groupname`

#### Entity Examples

```yaml
entities:
  - "user:john.doe"
  - "user:jane.smith"
  - "group:developers"
  - "group:frontend-team"
```

### Permission Sets

Permission sets define the level of access granted. You can specify:

- Permission set names (e.g., "DeveloperAccess")
- Permission set ARNs (e.g., "arn:aws:sso:::permissionSet/ps-1234567890abcdef0")

#### Permission Set Examples

```yaml
permission_sets:
  - "DeveloperAccess"
  - "ReadOnlyAccess"
  - "PowerUserAccess"
```

### Targets

Targets define which accounts the assignments apply to. You can use:

- **Account IDs**: Direct account identification
- **Account Tags**: Tag-based filtering
- **Exclude Accounts**: Accounts to explicitly exclude

#### Target Examples

```yaml
targets:
  # Specific account IDs
  account_ids:
    - "123456789012"
    - "234567890123"

  # Tag-based filtering
  account_tags:
    Environment: "production"
    Team: "backend"
    Purpose: "infrastructure"

  # Exclude specific accounts
  exclude_accounts:
    - "999999999999"  # Highly restricted account
```

## Complete Template Examples

### Simple Developer Access Template

```yaml
metadata:
  name: "simple-developer-access"
  description: "Basic developer access for development accounts"
  version: "1.0"
  author: "DevOps Team"

assignments:
  - entities:
      - "group:developers"
    permission_sets:
      - "DeveloperAccess"
    targets:
      account_tags:
        Environment: "development"
```

### Complex Multi-Environment Template

```yaml
metadata:
  name: "multi-environment-access"
  description: "Access management across multiple environments"
  version: "1.0"
  author: "Security Team"
  tags:
    scope: "multi-environment"
    security_level: "medium"

assignments:
  # Development environment
  - entities:
      - "group:developers"
      - "group:qa-engineers"
    permission_sets:
      - "DeveloperAccess"
      - "ReadOnlyAccess"
    targets:
      account_tags:
        Environment: "development"

  # Staging environment
  - entities:
      - "group:developers"
      - "group:qa-engineers"
      - "group:product-managers"
    permission_sets:
      - "DeveloperAccess"
      - "ReadOnlyAccess"
    targets:
      account_tags:
        Environment: "staging"

  # Production environment (restricted)
  - entities:
      - "group:senior-developers"
      - "group:devops-engineers"
    permission_sets:
      - "ReadOnlyAccess"
      - "EmergencyAccess"
    targets:
      account_tags:
        Environment: "production"
      exclude_accounts:
        - "111111111111"  # Critical production account
```

## Template Validation

Templates are automatically validated when used. The validation checks:

1. **Structure**: Required fields are present and correctly formatted
2. **Entities**: Users and groups exist in AWS Identity Center
3. **Permission Sets**: Permission sets exist and are accessible
4. **Accounts**: Account IDs are valid and accessible

### Validation Errors

Common validation errors include:

- Missing required fields
- Invalid entity format
- Non-existent users or groups
- Invalid permission set names
- Invalid account IDs
- Unresolvable tag filters

## Best Practices

### 1. Naming Conventions

- Use descriptive, lowercase names with hyphens
- Include environment or purpose in the name
- Use consistent versioning (e.g., "1.0", "1.1")

### 2. Organization

- Group related assignments together
- Use tags for categorization
- Keep templates focused on a single purpose

### 3. Security

- Follow the principle of least privilege
- Use tag-based targeting when possible
- Explicitly exclude sensitive accounts
- Document security implications

### 4. Maintenance

- Update templates when requirements change
- Version templates appropriately
- Document changes in the description
- Test templates before applying to production

## Template Commands

### Create a Template

```bash
# Create a blank template
awsideman templates create --name "my-template"

# Create an example template
awsideman templates create --name "my-template" --example

# Create with custom metadata
awsideman templates create --name "my-template" \
  --description "My custom template" \
  --author "My Name" \
  --version "1.0"
```

### Validate a Template

```bash
# Basic validation
awsideman templates validate ./templates/my-template.yaml

# Verbose validation
awsideman templates validate ./templates/my-template.yaml --verbose
```

### Preview a Template

```bash
# Preview execution
awsideman templates preview ./templates/my-template.yaml

# Preview with JSON output
awsideman templates preview ./templates/my-template.yaml --format json
```

### Apply a Template

```bash
# Apply with confirmation
awsideman templates apply ./templates/my-template.yaml

# Dry run (preview only)
awsideman templates apply ./templates/my-template.yaml --dry-run

# Apply without confirmation
awsideman templates apply ./templates/my-template.yaml --confirm
```

### Manage Templates

```bash
# List all templates
awsideman templates list

# Show template details
awsideman templates show my-template

# Show with specific format
awsideman templates show my-template --format json
```

## Troubleshooting

### Common Issues

1. **Template not found**: Check file path and ensure file exists
2. **Validation errors**: Review error messages and fix template structure
3. **Permission denied**: Verify AWS credentials and permissions
4. **Account not found**: Check account IDs and tag values

### Debug Tips

- Use `--verbose` flag for detailed output
- Check AWS credentials and profile configuration
- Verify SSO instance configuration
- Review template syntax with YAML/JSON validators

## Advanced Features

### Tag-Based Targeting

Tag-based targeting allows dynamic account selection:

```yaml
targets:
  account_tags:
    Environment: "production"
    Team: "backend"
    Region: "us-west-2"
```

### Exclusion Lists

Exclude specific accounts from tag-based targeting:

```yaml
targets:
  account_tags:
    Environment: "production"
  exclude_accounts:
    - "999999999999"  # Excluded account
```

### Multiple Permission Sets

Assign multiple permission sets to the same entities:

```yaml
entities:
  - "group:developers"
permission_sets:
  - "DeveloperAccess"
  - "ReadOnlyAccess"
  - "CloudWatchReadOnly"
```

## Configuration

Template behavior can be configured using the config command:

```bash
# Show template configuration
awsideman config templates show

# Set template directory
awsideman config templates set storage_directory ~/my-templates

# Set default format
awsideman config templates set default_format yaml

# Reset to defaults
awsideman config templates reset
```

## Support

For additional help with templates:

- Use `awsideman templates --help` for command help
- Check the examples in `examples/templates/` directory
- Review validation error messages for specific guidance
- Consult AWS Identity Center documentation for permission set details
