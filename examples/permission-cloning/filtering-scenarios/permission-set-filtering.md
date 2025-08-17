# Permission Set Filtering Examples

## Overview

Permission set filtering allows you to exclude sensitive or inappropriate permissions when copying. This is useful when you want to copy most, but not all, of a user's or group's access.

## Exclude Filtering

### Exclude Sensitive Permission Sets

#### Scenario: New Developer Shouldn't Have Admin Access

You want to copy permissions from a senior developer, but exclude administrative access that's inappropriate for junior staff.

```bash
awsideman copy --from user:senior.dev --to user:junior.dev \
  --exclude-permission-sets "AdminAccess,PowerUserAccess"
```

**Preview Output:**
```
Permission Copy Preview (Filtered)
=================================

Source: user:senior.dev (Senior Developer)
Target: user:junior.dev (Junior Developer)

Filter: Exclude permission sets: AdminAccess, PowerUserAccess

Assignments to Copy:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Assignments Filtered Out (Excluded):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ AdminAccess         │ Development     │ 123456789012             │
│ PowerUserAccess     │ Staging         │ 234567890123             │
│ PowerUserAccess     │ Production      │ 345678901234             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Summary:
- 4 assignments will be copied
- 3 assignments excluded for security
- 0 conflicts detected
```

#### Multiple Permission Sets

```bash
# Exclude multiple sensitive permission sets
awsideman copy --from user:senior.admin --to user:junior.dev \
  --exclude-permission-sets "AdminAccess,PowerUserAccess,BillingAccess"
```

#### Single Permission Set

```bash
# Exclude just admin access
awsideman copy --from group:senior-devs --to group:junior-devs \
  --exclude-permission-sets "AdminAccess"
```

## More Exclude Examples

### Copy Everything Except Sensitive Access

#### Scenario: Departing Employee Replacement

You want to copy most permissions but exclude administrative access when replacing a departing employee.

```bash
awsideman copy --from user:departing.admin --to user:replacement.user \
  --exclude-permission-sets "AdminAccess,FullAdminAccess"
```

**Preview Output:**
```
Permission Copy Preview (Filtered)
=================================

Source: user:departing.admin (Departing Admin)
Target: user:replacement.user (Replacement User)

Filter: Exclude permission sets: AdminAccess, FullAdminAccess

Assignments to Copy:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ PowerUserAccess     │ Development     │ 123456789012             │
│ PowerUserAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ DeveloperAccess     │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Assignments Filtered Out (Excluded):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ AdminAccess         │ Development     │ 123456789012             │
│ AdminAccess         │ Staging         │ 234567890123             │
│ FullAdminAccess     │ Production      │ 345678901234             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Summary:
- 4 assignments will be copied
- 3 assignments excluded
- 0 conflicts detected
```

#### Exclude Multiple Permission Sets

```bash
# Exclude several types of elevated access
awsideman copy --from user:contractor --to user:employee \
  --exclude-permission-sets "AdminAccess,PowerUserAccess,BillingAccess"
```

## Account Filtering

### Include Specific Accounts

#### Scenario: Copy Only Non-Production Access

You want to copy permissions but only for development and staging environments.

```bash
awsideman copy --from user:senior.dev --to user:junior.dev \
  --include-accounts "123456789012,234567890123"
```

**Preview Output:**
```
Permission Copy Preview (Filtered)
=================================

Source: user:senior.dev (Senior Developer)
Target: user:junior.dev (Junior Developer)

Filter: Include accounts: 123456789012 (Development), 234567890123 (Staging)

Assignments to Copy:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ PowerUserAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Staging         │ 234567890123             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Assignments Filtered Out:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ PowerUserAccess     │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Summary:
- 4 assignments will be copied
- 2 assignments filtered out
- 0 conflicts detected
```

### Exclude Specific Accounts

#### Scenario: Copy Everything Except Production

You want to copy all permissions except those for production accounts.

```bash
awsideman copy --from user:alice --to user:bob \
  --exclude-accounts "345678901234"
```

**Preview Output:**
```
Permission Copy Preview (Filtered)
=================================

Source: user:alice (Alice Smith)
Target: user:bob (Bob Jones)

Filter: Exclude accounts: 345678901234 (Production)

Assignments to Copy:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ PowerUserAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Assignments Filtered Out (Excluded):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ PowerUserAccess     │ Production      │ 345678901234             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Summary:
- 4 assignments will be copied
- 2 assignments excluded
- 0 conflicts detected
```

## Combined Filtering

### Permission Sets + Accounts

#### Scenario: Copy Non-Production Access Without Admin Rights

You want to copy permissions for development environments but exclude administrative access.

```bash
awsideman copy --from user:senior.dev --to user:junior.dev \
  --exclude-permission-sets "AdminAccess,PowerUserAccess" \
  --include-accounts "123456789012,234567890123"
```

**Preview Output:**
```
Permission Copy Preview (Filtered)
=================================

Source: user:senior.dev (Senior Developer)
Target: user:junior.dev (Junior Developer)

Filters:
- Exclude permission sets: AdminAccess, PowerUserAccess
- Include accounts: 123456789012 (Development), 234567890123 (Staging)

Assignments to Copy:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ ReadOnlyAccess      │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Staging         │ 234567890123             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Assignments Filtered Out:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ AdminAccess         │ Development     │ 123456789012             │
│ PowerUserAccess     │ Development     │ 123456789012             │
│ AdminAccess         │ Staging         │ 234567890123             │
│ PowerUserAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ DeveloperAccess     │ Production      │ 345678901234             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Summary:
- 4 assignments will be copied
- 6 assignments filtered out (4 excluded permissions, 2 excluded accounts)
- 0 conflicts detected
```

### Include + Exclude Combinations

#### Scenario: Copy Development Permissions Except Admin Access

```bash
awsideman copy --from user:senior.dev --to user:junior.dev \
  --include-accounts "123456789012,234567890123" \
  --exclude-permission-sets "AdminAccess,FullAdminAccess"
```

## Advanced Filtering Scenarios

### Contractor Onboarding

#### Copy Safe Access for Contractors

```bash
# Copy permissions but exclude sensitive access and production accounts
awsideman copy --from user:employee.template --to user:contractor.new \
  --exclude-permission-sets "AdminAccess,PowerUserAccess,BillingAccess" \
  --exclude-accounts "345678901234,555666777888"
```

### Team Lead Promotion

#### Copy Team Access Without Admin Rights

```bash
# Copy all team permissions except administrative ones
awsideman copy --from user:current.lead --to user:new.lead \
  --exclude-permission-sets "AdminAccess,BillingAccess,SecurityAuditAccess"
```

### Environment-Specific Access

#### Copy Staging Environment Access Without Admin Rights

```bash
# Copy permissions for staging environment, excluding admin access
awsideman copy --from group:production-team --to group:staging-team \
  --exclude-permission-sets "AdminAccess,PowerUserAccess" \
  --include-accounts "234567890123"
```

### Audit and Compliance

#### Copy Safe Permissions for Audit

```bash
# Copy permissions excluding sensitive access for audit purposes
awsideman copy --from user:production.user --to user:audit.reviewer \
  --exclude-permission-sets "AdminAccess,PowerUserAccess,BillingAccess"
```

## Filter Validation

### Check Available Permission Sets

Before filtering, verify what permission sets exist:

```bash
# List all permission sets
awsideman status check --permission-sets

# Look for specific patterns
awsideman status check --permission-sets | grep -i admin
awsideman status check --permission-sets | grep -i read
```

### Check Available Accounts

Verify account IDs and names:

```bash
# List all accounts
awsideman status check --accounts

# Find specific account IDs
awsideman status check --accounts | grep -i production
awsideman status check --accounts | grep -i development
```

## Common Filter Patterns

### By Environment

```bash
# Development only
--include-accounts "123456789012"

# Non-production
--exclude-accounts "345678901234"

# Staging and development
--include-accounts "123456789012,234567890123"
```

### By Access Level

```bash
# No administrative access (most common)
--exclude-permission-sets "AdminAccess,FullAdminAccess,PowerUserAccess"

# No sensitive access
--exclude-permission-sets "AdminAccess,BillingAccess,SecurityAuditAccess"

# No elevated permissions
--exclude-permission-sets "PowerUserAccess,AdminAccess"
```

### By Role Type

```bash
# Contractor-appropriate access
--exclude-permission-sets "AdminAccess,PowerUserAccess,BillingAccess" --exclude-accounts "345678901234"

# Intern access (development environment only)
--exclude-permission-sets "AdminAccess,PowerUserAccess" --include-accounts "123456789012"

# Temporary access (no sensitive permissions)
--exclude-permission-sets "AdminAccess,BillingAccess,SecurityAccess"
```

## Troubleshooting Filters

### No Assignments Match Filters

**Error:** `No assignments match the specified filters`

**Solutions:**
```bash
# Check what assignments exist first
awsideman copy --from user:alice --to user:bob --preview

# Verify filter values
awsideman status check --permission-sets | grep "YourFilterValue"
awsideman status check --accounts | grep "YourAccountId"

# Try less restrictive filters
awsideman copy --from user:alice --to user:bob --exclude-permission-sets "AdminAccess" --preview
```

### Invalid Filter Values

**Error:** `Invalid filter: permission set 'NonExistentSet' not found`

**Solutions:**
```bash
# List available permission sets
awsideman status check --permission-sets

# Use exact names from the list
awsideman copy --from user:alice --to user:bob --exclude-permission-sets "AdminAccess" --preview
```

## Best Practices

1. **Always preview filtered operations** to verify the filter works as expected
2. **Use descriptive filter combinations** that match your security requirements
3. **Verify filter values exist** before using them in operations
4. **Document filter rationale** for audit and compliance purposes
5. **Test filtered results** to ensure the target has appropriate access
6. **Combine filters thoughtfully** - overly restrictive filters may result in no assignments
7. **Save successful filter patterns** for reuse in similar scenarios

## Related Examples

- [Basic Copy Operations](../basic-operations/user-to-user-copy.md)
- [Cross-Entity Operations](../cross-entity-operations/user-to-group-copy.md)
- [Account Filtering](account-filtering.md)
- [Rollback Procedures](../rollback-examples/filtered-operation-rollback.md)
