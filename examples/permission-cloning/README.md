# Permission Cloning Examples

This directory contains examples for common permission cloning use cases. Each example includes the command, expected output, and explanation of when to use it.

## Directory Structure

- `basic-operations/` - Simple copy and clone operations
- `filtering-scenarios/` - Examples using various filters
- `cross-entity-operations/` - Copying between users and groups
- `bulk-scenarios/` - Large-scale operations
- `rollback-examples/` - Rollback procedures and best practices
- `troubleshooting/` - Common issues and solutions

## Quick Reference

### Basic Operations

```bash
# Copy user permissions
awsideman copy --from user:alice --to user:bob

# Copy group permissions
awsideman copy --from group:developers --to group:qa-team

# Clone permission set
awsideman clone --name PowerUserAccess --to DeveloperAccess
```

### With Preview

```bash
# Always preview first
awsideman copy --from user:alice --to user:bob --preview
awsideman clone --name PowerUserAccess --to DeveloperAccess --preview
```

### With Filtering

```bash
# Filter by permission sets
awsideman copy --from user:alice --to user:bob --include-permission-sets "ReadOnlyAccess,PowerUserAccess"

# Filter by accounts
awsideman copy --from group:developers --to group:qa-team --include-accounts "123456789012,987654321098"
```

## Use Case Categories

### 1. Employee Onboarding
- Copy permissions from similar role
- Set up new team member access
- Replicate department permissions

### 2. Role Changes
- Promote user to new role
- Transfer permissions between teams
- Update access for job changes

### 3. Team Management
- Set up new teams with existing patterns
- Standardize team permissions
- Manage contractor access

### 4. Permission Set Management
- Create variations of existing permission sets
- Set up environment-specific access
- Maintain permission set templates

### 5. Compliance and Auditing
- Review and replicate approved access patterns
- Ensure consistent permissions across teams
- Document permission changes

## Best Practices Examples

Each example includes:
- **Scenario**: When to use this approach
- **Command**: Exact command to run
- **Preview**: What the preview output looks like
- **Result**: Expected outcome
- **Rollback**: How to undo if needed
- **Notes**: Important considerations

## Getting Started

1. Start with the `basic-operations/` examples
2. Review the scenario that matches your use case
3. Always run with `--preview` first
4. Check the troubleshooting examples if you encounter issues

## Safety Reminders

- **Always preview operations first**
- **Verify entity names before executing**
- **Keep rollback information for important operations**
- **Test permissions after copying**
- **Document changes for audit purposes**
