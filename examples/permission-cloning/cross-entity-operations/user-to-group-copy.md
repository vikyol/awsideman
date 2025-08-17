# User to Group Permission Copy

## Scenario

You need to copy permission assignments from a user to a group. This is common when:
- Standardizing team permissions based on an experienced team member
- Setting up group-based access patterns from individual user configurations
- Migrating from user-based to group-based permission management
- Creating template groups based on role models

## Example: Creating Team Permissions from Senior Developer

### Situation
Alice is a senior developer with well-configured permissions. You want to create a "Senior Developers" group with the same permissions so other senior developers can be added to the group instead of copying permissions individually.

### Command

```bash
awsideman copy --from user:alice.smith --to group:senior-developers
```

### Step-by-Step Process

#### 1. Preview the Operation

```bash
awsideman copy --from user:alice.smith --to group:senior-developers --preview
```

**Expected Preview Output:**
```
Permission Copy Preview (Cross-Entity)
=====================================

Source: user:alice.smith (Alice Smith) [USER]
Target: group:senior-developers (Senior Developers) [GROUP]

⚠️  Cross-entity copy: USER → GROUP
This will copy user permissions to a group, making them available to all group members.

Assignments to Copy:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ PowerUserAccess     │ Development     │ 123456789012             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Assignments to Skip (already exist on group):
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ ReadOnlyAccess      │ Development     │ 123456789012             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Impact Analysis:
- Group members will gain access to 5 new permission assignments
- Current group members: 0 (new group)
- Future group members will automatically inherit these permissions

Summary:
- 5 assignments will be copied to group
- 1 assignment will be skipped (duplicate)
- 0 conflicts detected

This is a preview - no changes will be made.
```

#### 2. Execute the Operation

```bash
awsideman copy --from user:alice.smith --to group:senior-developers
```

**Expected Execution Output:**
```
Copying Permissions (Cross-Entity)
=================================

Source: user:alice.smith (Alice Smith) [USER]
Target: group:senior-developers (Senior Developers) [GROUP]

Progress: [████████████████████] 100% (5/5 assignments)

Results:
✓ DeveloperAccess → Development (123456789012)
✓ DeveloperAccess → Staging (234567890123)
✓ PowerUserAccess → Development (123456789012)
✓ ReadOnlyAccess → Production (345678901234)
✓ ReadOnlyAccess → Sandbox (456789012345)
- ReadOnlyAccess → Development (123456789012) [SKIPPED - already exists]

Operation completed successfully!

Summary:
- 5 assignments copied to group
- 1 assignment skipped
- 0 errors
- Rollback ID: copy-20240816-144522-xyz789

Group "senior-developers" now has the same permissions as Alice Smith.
Any users added to this group will automatically inherit these permissions.

To undo this operation:
awsideman rollback execute --operation-id copy-20240816-144522-xyz789
```

### Verification

#### Check Group Permissions

```bash
# Verify the group now has the expected permissions
awsideman status inspect --entity group:senior-developers
```

**Expected Output:**
```
Group: senior-developers (Senior Developers)
============================================

Permission Assignments:
┌─────────────────────┬─────────────────┬──────────────────────────┐
│ Permission Set      │ Account         │ Account ID               │
├─────────────────────┼─────────────────┼──────────────────────────┤
│ DeveloperAccess     │ Development     │ 123456789012             │
│ DeveloperAccess     │ Staging         │ 234567890123             │
│ PowerUserAccess     │ Development     │ 123456789012             │
│ ReadOnlyAccess      │ Development     │ 123456789012             │
│ ReadOnlyAccess      │ Production      │ 345678901234             │
│ ReadOnlyAccess      │ Sandbox         │ 456789012345             │
└─────────────────────┴─────────────────┴──────────────────────────┘

Total: 6 assignments
Group Members: 0 (no members yet)

Note: When users are added to this group, they will automatically
inherit all these permission assignments.
```

#### Add Users to the Group

Now you can add other senior developers to the group:

```bash
# Add users to the group (using AWS CLI or console)
aws identitystore create-group-membership \
  --identity-store-id d-1234567890 \
  --group-id 1234567890-12345678-1234-1234-1234-123456789012 \
  --member-id UserId=9876543210-87654321-8765-4321-8765-876543218765
```

### Use Cases and Variations

#### Creating Department Groups

```bash
# Create marketing team permissions from marketing manager
awsideman copy --from user:marketing.manager --to group:marketing-team

# Create finance team permissions from finance lead
awsideman copy --from user:finance.lead --to group:finance-team

# Create operations team permissions from ops manager
awsideman copy --from user:ops.manager --to group:operations-team
```

#### Creating Role-Based Groups

```bash
# Create junior developer group from senior developer
awsideman copy --from user:senior.dev --to group:junior-developers \
  --exclude-permission-sets "PowerUserAccess,AdminAccess"

# Create contractor group with safe permissions
awsideman copy --from user:employee.template --to group:contractors \
  --exclude-permission-sets "AdminAccess,PowerUserAccess,BillingAccess" \
  --exclude-accounts "345678901234"

# Create intern group with minimal permissions
awsideman copy --from user:junior.dev --to group:interns \
  --exclude-permission-sets "PowerUserAccess,AdminAccess" \
  --include-accounts "123456789012"
```

#### Environment-Specific Groups

```bash
# Create development team group
awsideman copy --from user:dev.lead --to group:dev-team \
  --include-accounts "123456789012,234567890123"

# Create production support group
awsideman copy --from user:prod.support --to group:prod-support-team \
  --include-permission-sets "ReadOnlyAccess,SupportAccess"
```

## Advanced Scenarios

### Migrating from User-Based to Group-Based Management

#### Step 1: Create Groups from Template Users

```bash
# Create groups based on different role templates
awsideman copy --from user:senior.developer --to group:senior-developers
awsideman copy --from user:junior.developer --to group:junior-developers
awsideman copy --from user:qa.engineer --to group:qa-engineers
awsideman copy --from user:devops.engineer --to group:devops-engineers
```

#### Step 2: Add Users to Appropriate Groups

```bash
# Add users to their respective groups (via AWS console or CLI)
# This gives them the same permissions they had individually
```

#### Step 3: Remove Individual User Permissions (Optional)

```bash
# After verifying group permissions work, you can remove individual assignments
# This should be done carefully and with proper testing
```

### Creating Hierarchical Group Structure

```bash
# Create base developer group (exclude admin access)
awsideman copy --from user:base.developer --to group:all-developers \
  --exclude-permission-sets "AdminAccess,PowerUserAccess"

# Create senior developer group (exclude only admin access)
awsideman copy --from user:senior.developer --to group:senior-developers \
  --exclude-permission-sets "AdminAccess"

# Create team lead group (exclude billing and security access)
awsideman copy --from user:team.lead --to group:team-leads \
  --exclude-permission-sets "BillingAccess,SecurityAuditAccess"
```

## Best Practices for User-to-Group Copying

### Planning

1. **Identify Template Users**: Choose users with well-configured, appropriate permissions
2. **Define Group Purpose**: Clearly define what the group represents and who should be in it
3. **Consider Inheritance**: Remember that all group members will inherit these permissions
4. **Plan Group Hierarchy**: Consider how groups relate to each other

### Execution

1. **Always Preview First**: Understand what permissions will be copied
2. **Use Filters Appropriately**: Copy only the permissions relevant to the group's purpose
3. **Verify Group Exists**: Ensure the target group exists before copying
4. **Document the Relationship**: Record which user template was used for the group

### Post-Copy Management

1. **Test Group Permissions**: Verify the permissions work as expected
2. **Add Initial Members**: Add appropriate users to the group
3. **Monitor Usage**: Track how the group permissions are being used
4. **Maintain Consistency**: Keep group permissions aligned with their purpose

## Common Issues and Solutions

### Group Not Found

**Error:** `Group 'senior-developers' not found`

**Solutions:**
```bash
# Verify group exists
awsideman status check --groups | grep senior-developers

# Create the group first (via AWS console or CLI)
aws identitystore create-group \
  --identity-store-id d-1234567890 \
  --display-name "Senior Developers" \
  --description "Senior development team members"
```

### Too Many Permissions

**Issue:** The template user has more permissions than appropriate for the group.

**Solutions:**
```bash
# Use filters to exclude inappropriate permissions
awsideman copy --from user:alice.smith --to group:senior-developers \
  --exclude-permission-sets "AdminAccess,BillingAccess" \
  --exclude-accounts "345678901234"

# Exclude multiple sensitive permission sets
awsideman copy --from user:alice.smith --to group:senior-developers \
  --exclude-permission-sets "AdminAccess,BillingAccess,SecurityAuditAccess"
```

### Unintended Access Expansion

**Issue:** Group members suddenly have more access than expected.

**Solutions:**
1. **Review Group Membership**: Check who is in the group
2. **Audit Permissions**: Review what permissions were copied
3. **Use Rollback**: Undo the copy operation if necessary
4. **Refine and Retry**: Use filters to copy only appropriate permissions

```bash
# Rollback if necessary
awsideman rollback execute --operation-id copy-20240816-144522-xyz789

# Retry with more restrictive exclusions
awsideman copy --from user:alice.smith --to group:senior-developers \
  --exclude-permission-sets "AdminAccess,PowerUserAccess,BillingAccess" \
  --exclude-accounts "345678901234"
```

## Security Considerations

### Access Amplification

When copying user permissions to a group:
- **All group members** will inherit these permissions
- **Future group members** will automatically get these permissions
- **Consider the principle of least privilege** when selecting template users

### Audit and Compliance

1. **Document Template Selection**: Record why a specific user was chosen as template
2. **Review Group Membership**: Regularly audit who is in the group
3. **Monitor Permission Usage**: Track how group permissions are being used
4. **Maintain Approval Records**: Keep records of who approved the group permissions

### Ongoing Management

1. **Regular Reviews**: Periodically review group permissions and membership
2. **Template Updates**: When template user permissions change, consider updating group
3. **Access Certification**: Include groups in regular access certification processes
4. **Separation of Duties**: Ensure group permissions don't violate separation requirements

## Related Examples

- [Group to Group Copy](../basic-operations/group-to-group-copy.md)
- [Group to User Copy](group-to-user-copy.md)
- [Permission Set Filtering](../filtering-scenarios/permission-set-filtering.md)
- [Rollback Procedures](../rollback-examples/basic-rollback.md)
