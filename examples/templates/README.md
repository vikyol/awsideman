# Template Examples

This directory contains example templates for common AWS Identity Center permission assignment scenarios.

## Available Examples

### 1. Developer Access Template (`developer-access.yaml`)
**Purpose**: Standard developer access across development accounts
**Use Case**: Grant developers access to development and staging environments
**Features**:
- Tag-based account targeting
- Multiple permission sets (DeveloperAccess, ReadOnlyAccess)
- Exclusion of production accounts
- Group and individual user assignments

### 2. Admin Access Template (`admin-access.yaml`)
**Purpose**: Administrative access for production accounts
**Use Case**: Grant system administrators and security teams access to production
**Features**:
- Production environment targeting
- High-security permission sets
- Emergency access for incident response
- Compliance team access

### 3. Read-Only Access Template (`readonly-access.yaml`)
**Purpose**: Read-only access for monitoring and compliance
**Use Case**: Grant auditors and business users read access to production
**Features**:
- Read-only permission sets
- Compliance and monitoring access
- Business user access
- Security monitoring access

### 4. DevOps Access Template (`devops-access.yaml`)
**Purpose**: DevOps engineer access for infrastructure management
**Use Case**: Grant DevOps teams access to infrastructure and platform accounts
**Features**:
- Infrastructure management permissions
- Multi-environment access
- Platform engineering access
- Monitoring and logging access

## Using These Examples

### 1. Copy and Customize
```bash
# Copy an example template
cp examples/templates/developer-access.yaml ./my-templates/

# Edit the template for your needs
# Update metadata, entities, permission sets, and targets
```

### 2. Validate Before Use
```bash
# Validate the template
awsideman templates validate ./my-templates/developer-access.yaml

# Validate with verbose output
awsideman templates validate ./my-templates/developer-access.yaml --verbose
```

### 3. Preview Execution
```bash
# Preview what would happen
awsideman templates preview ./my-templates/developer-access.yaml

# Preview with JSON output
awsideman templates preview ./my-templates/developer-access.yaml --format json
```

### 4. Apply the Template
```bash
# Apply with confirmation
awsideman templates apply ./my-templates/developer-access.yaml

# Dry run first
awsideman templates apply ./my-templates/developer-access.yaml --dry-run
```

## Customization Guide

### Update Metadata
```yaml
metadata:
  name: "my-custom-template"
  description: "Custom template for my organization"
  author: "Your Name"
  version: "1.0"
  tags:
    organization: "my-company"
    purpose: "custom-access"
```

### Update Entities
```yaml
entities:
  - "user:your-username"
  - "group:your-team"
  - "group:your-department"
```

### Update Permission Sets
```yaml
permission_sets:
  - "YourCustomPermissionSet"
  - "ReadOnlyAccess"
  - "DeveloperAccess"
```

### Update Targets
```yaml
targets:
  # Specific accounts
  account_ids:
    - "111111111111"
    - "222222222222"

  # Tag-based targeting
  account_tags:
    Environment: "your-environment"
    Team: "your-team"
    Purpose: "your-purpose"

  # Exclude accounts
  exclude_accounts:
    - "999999999999"
```

## Template Patterns

### Simple Single Assignment
```yaml
metadata:
  name: "simple-template"
  description: "Simple single assignment template"

assignments:
  - entities:
      - "group:developers"
    permission_sets:
      - "DeveloperAccess"
    targets:
      account_tags:
        Environment: "development"
```

### Multi-Environment Template
```yaml
metadata:
  name: "multi-environment"
  description: "Access across multiple environments"

assignments:
  # Development
  - entities: ["group:developers"]
    permission_sets: ["DeveloperAccess"]
    targets:
      account_tags:
        Environment: "development"

  # Staging
  - entities: ["group:developers"]
    permission_sets: ["DeveloperAccess"]
    targets:
      account_tags:
        Environment: "staging"

  # Production (restricted)
  - entities: ["group:senior-developers"]
    permission_sets: ["ReadOnlyAccess"]
    targets:
      account_tags:
        Environment: "production"
```

### Role-Based Template
```yaml
metadata:
  name: "role-based-access"
  description: "Access based on user roles"

assignments:
  # Developers
  - entities: ["group:developers"]
    permission_sets: ["DeveloperAccess"]
    targets:
      account_tags:
        Environment: "development"

  # DevOps Engineers
  - entities: ["group:devops-engineers"]
    permission_sets: ["DevOpsAccess", "InfrastructureManagement"]
    targets:
      account_tags:
        Purpose: "infrastructure"

  # Security Team
  - entities: ["group:security-team"]
    permission_sets: ["SecurityAudit", "ReadOnlyAccess"]
    targets:
      account_tags:
        Environment: "production"
```

## Best Practices

### 1. Naming Conventions
- Use descriptive, lowercase names with hyphens
- Include environment or purpose in the name
- Use consistent versioning

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

## Testing Templates

### 1. Start with Development
Always test templates in development environments first:
```bash
# Test in development
awsideman templates apply dev-template.yaml --dry-run

# Verify results
awsideman templates preview dev-template.yaml
```

### 2. Use Dry Run
Always use `--dry-run` before applying to production:
```bash
# Preview production changes
awsideman templates apply prod-template.yaml --dry-run

# Review the output carefully
# Only apply when confident
```

### 3. Validate Changes
After applying, validate the changes:
```bash
# Check assignments were created
aws sso list-account-assignments \
  --instance-arn <instance-arn> \
  --account-id <account-id>
```

## Troubleshooting

### Common Issues
1. **Template not found**: Check file path and ensure file exists
2. **Validation errors**: Review error messages and fix template structure
3. **Permission denied**: Verify AWS credentials and permissions
4. **Account not found**: Check account IDs and tag values

### Getting Help
- Use `awsideman templates --help` for command help
- Check the troubleshooting guide in `docs/template-troubleshooting.md`
- Review validation error messages for specific guidance
- Consult AWS Identity Center documentation for permission set details

## Contributing Examples

When adding new examples:

1. **Follow the naming convention**: `purpose-access.yaml`
2. **Include comprehensive metadata**: name, description, author, version, tags
3. **Use realistic examples**: Include common permission sets and account patterns
4. **Add documentation**: Include comments explaining the template structure
5. **Test the template**: Ensure it validates and can be previewed
6. **Update this README**: Add the new example to the list above

## Related Documentation

- [Template Format Documentation](../docs/template-format.md)
- [Template Troubleshooting Guide](../docs/template-troubleshooting.md)
- [CLI Command Reference](../docs/cli-commands.md)
- [Configuration Guide](../docs/configuration.md)
