# User to User Permission Copy

## Scenario

You need to copy all permission assignments from one user to another. This is common when:
- Onboarding a new employee with the same role
- Replacing someone who left the company
- Setting up backup access for critical roles

## Example: New Developer Onboarding

### Situation
Alice is a senior developer with all the necessary permissions. Bob is a new developer who needs the same access.

### Command

```bash
awsideman copy --from user:alice.smith --to user:bob.jones
```

### Step-by-Step Process

#### 1. Preview the Operation

You can use either `--preview` for a detailed analysis or `--dry-run` to test the execution logic:

```bash
# Option 1: Preview mode (recommended for quick overview)
awsideman copy --from user:alice.smith --to user:bob.jones --preview

# Option 2: Dry-run mode (for testing execution flow)
awsideman copy --from user:alice.smith --to user:bob.jones --dry-run
```

**Expected Preview Output:**
```
Permission Copy Preview
======================

Source: user:alice.smith (Alice Smith)
Target: user:bob.jones (Bob Jones)

Assignments to Copy:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ PowerUserAccess     │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Assignments to Skip (already exist):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Summary:
- 4 assignments will be copied
- 1 assignment will be skipped (duplicate)
- 0 conflicts detected

This is a preview - no changes will be made.
```

#### 2. Execute the Operation

```bash
awsideman copy --from user:alice.smith --to user:bob.jones
```

**Expected Execution Output:**
```
Copying Permissions
==================

Source: user:alice.smith (Alice Smith)
Target: user:bob.jones (Bob Jones)

Progress: [████████████████████] 100% (4/4 assignments)

Results:
✓ DeveloperAccess → Development (123456789012)
✓ DeveloperAccess → Staging (234567890123)
✓ ReadOnlyAccess → Production (345678901234)
✓ PowerUserAccess → Sandbox (456789012345)
- ReadOnlyAccess → Sandbox (456789012345) [SKIPPED - already exists]

Operation completed successfully!

Summary:
- 4 assignments copied
- 1 assignment skipped
- 0 errors
- Rollback ID: copy-20240816-143022-abc123

To undo this operation:
awsideman rollback execute --operation-id copy-20240816-143022-abc123
```

### Verification

#### Check the Results

```bash
# Verify Bob now has the expected permissions
awsideman status inspect --entity user:bob.jones
```

**Expected Output:**
```
User: bob.jones (Bob Jones)
==========================

Permission Assignments:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
│ PowerUserAccess     │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Total: 5 assignments
```

### Rollback (if needed)

If you need to undo the operation:

```bash
awsideman rollback execute --operation-id copy-20240816-143022-abc123
```

**Expected Rollback Output:**
```
Rolling Back Operation
=====================

Operation ID: copy-20240816-143022-abc123
Type: Permission Copy
Date: 2024-08-16 14:30:22

Removing assignments added during copy operation...

Progress: [████████████████████] 100% (4/4 assignments)

Results:
✓ Removed DeveloperAccess from bob.jones in Development (123456789012)
✓ Removed DeveloperAccess from bob.jones in Staging (234567890123)
✓ Removed ReadOnlyAccess from bob.jones in Production (345678901234)
✓ Removed PowerUserAccess from bob.jones in Sandbox (456789012345)

Rollback completed successfully!
Bob Jones now has the same permissions as before the copy operation.
```

## Variations

### Copy with Filters

If you only want to copy specific types of access:

```bash
# Only copy developer-related permissions
awsideman copy --from user:alice.smith --to user:bob.jones \
  --include-permission-sets "DeveloperAccess,PowerUserAccess"

# Only copy permissions for non-production accounts
awsideman copy --from user:alice.smith --to user:bob.jones \
  --exclude-accounts "345678901234"
```

### Copy for Temporary Access

For temporary contractors or short-term access:

```bash
# Copy permissions and document for later removal
awsideman copy --from user:alice.smith --to user:contractor.temp

# Save the rollback ID for later cleanup
echo "copy-20240816-143022-abc123" > contractor-temp-rollback.txt
```

## Common Issues

### User Not Found

**Error:** `User 'bob.jones' not found`

**Solution:** Verify the username format and ensure the user exists:
```bash
# Check if user exists
awsideman status check --users | grep bob.jones

# Try different username formats
awsideman copy --from user:alice.smith --to user:bob.jones@company.com --preview
```

### Permission Denied

**Error:** `Access denied: insufficient permissions to create assignments`

**Solution:** Ensure you have the necessary AWS permissions:
- `sso:CreateAccountAssignment`
- `sso:ListAccountAssignments`
- `identitystore:ListUsers`

### Partial Failure

**Error:** `Operation failed: partial completion with errors`

**Solution:** Review the detailed output and retry failed assignments:
```bash
# Check what failed
awsideman rollback list --detailed

# Retry with filters to exclude problematic assignments
awsideman copy --from user:alice.smith --to user:bob.jones \
  --exclude-permission-sets "ProblematicPermissionSet"
```

## Best Practices

1. **Always preview first** to understand what will be copied
2. **Verify usernames** before executing to avoid typos
3. **Save rollback IDs** for important operations
4. **Test permissions** after copying to ensure they work
5. **Document the change** for audit and compliance purposes
6. **Use filters** when you don't need all permissions copied

## Related Examples

- [Group to Group Copy](group-to-group-copy.md)
- [User to Group Copy](../cross-entity-operations/user-to-group-copy.md)
- [Filtered Copy Operations](../filtering-scenarios/permission-set-filtering.md)
- [Rollback Procedures](../rollback-examples/basic-rollback.md)
