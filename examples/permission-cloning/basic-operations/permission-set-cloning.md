# Permission Set Cloning

## Scenario

You need to create a new permission set based on an existing one. This is common when:
- Creating environment-specific variations (dev, staging, prod)
- Setting up role-based access with slight modifications
- Creating backup or template permission sets
- Establishing permission sets for different teams with similar needs

## Example: Creating Developer Access from Power User Access

### Situation
You have a "PowerUserAccess" permission set that's too broad for new developers. You want to create a "DeveloperAccess" permission set based on it, then modify it to be more restrictive.

### Command

```bash
awsideman clone --name PowerUserAccess --to DeveloperAccess --description "Developer access with limited permissions"
```

### Step-by-Step Process

#### 1. Preview the Operation

```bash
awsideman clone --name PowerUserAccess --to DeveloperAccess --description "Developer access with limited permissions" --preview
```

**Expected Preview Output:**
```
Permission Set Clone Preview
===========================

Source: PowerUserAccess
Target: DeveloperAccess
Description: "Developer access with limited permissions"

Configuration to Clone:
┌─────────────────────────┬─────────────────────────────────────────┐
│ Setting                 │ Value                                   │
├─────────────────────────┼─────────────────────────────────────────┤
│ Session Duration        │ PT8H (8 hours)                         │
│ Relay State URL         │ https://console.aws.amazon.com/         │
└─────────────────────────┴─────────────────────────────────────────┘

AWS Managed Policies to Clone:
┌─────────────────────────────────────────────────────────────────┐
│ Policy ARN                                                      │
├─────────────────────────────────────────────────────────────────┤
│ arn:aws:iam::aws:policy/PowerUserAccess                        │
│ arn:aws:iam::aws:policy/IAMReadOnlyAccess                      │
└─────────────────────────────────────────────────────────────────┘

Customer Managed Policies to Clone:
┌─────────────────────────────────────────────────────────────────┐
│ Policy Name                                                     │
├─────────────────────────────────────────────────────────────────┤
│ CompanyS3Access                                                 │
│ CompanyLoggingAccess                                            │
└─────────────────────────────────────────────────────────────────┘

Inline Policy to Clone:
┌─────────────────────────────────────────────────────────────────┐
│ Policy Document (truncated)                                     │
├─────────────────────────────────────────────────────────────────┤
│ {                                                               │
│   "Version": "2012-10-17",                                     │
│   "Statement": [                                               │
│     {                                                           │
│       "Effect": "Allow",                                       │
│       "Action": [                                              │
│         "cloudformation:Describe*",                            │
│         "cloudformation:List*"                                 │
│       ],                                                        │
│       "Resource": "*"                                          │
│     }                                                           │
│   ]                                                             │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘

Summary:
- New permission set "DeveloperAccess" will be created
- 2 AWS managed policies will be attached
- 2 customer managed policies will be attached
- 1 inline policy will be added
- Session duration: 8 hours
- Relay state URL will be set

This is a preview - no changes will be made.
```

#### 2. Execute the Operation

```bash
awsideman clone --name PowerUserAccess --to DeveloperAccess --description "Developer access with limited permissions"
```

**Expected Execution Output:**
```
Cloning Permission Set
=====================

Source: PowerUserAccess
Target: DeveloperAccess

Progress: [████████████████████] 100%

Steps Completed:
✓ Created permission set "DeveloperAccess"
✓ Set description: "Developer access with limited permissions"
✓ Set session duration: PT8H
✓ Set relay state URL: https://console.aws.amazon.com/
✓ Attached AWS managed policy: PowerUserAccess
✓ Attached AWS managed policy: IAMReadOnlyAccess
✓ Attached customer managed policy: CompanyS3Access
✓ Attached customer managed policy: CompanyLoggingAccess
✓ Added inline policy (156 characters)

Operation completed successfully!

Summary:
- Permission set "DeveloperAccess" created
- All policies and settings copied from "PowerUserAccess"
- Rollback ID: clone-20240816-143522-def456

To undo this operation:
awsideman rollback execute --operation-id clone-20240816-143522-def456

Next steps:
1. Review the cloned permission set in AWS Identity Center console
2. Modify policies as needed for developer-specific access
3. Assign the permission set to developer users/groups
```

### Verification

#### Check the Results

```bash
# Verify the new permission set exists
awsideman status check --permission-sets | grep DeveloperAccess
```

**Expected Output:**
```
DeveloperAccess - Developer access with limited permissions
```

#### Inspect the Cloned Permission Set

You can also verify in the AWS Identity Center console:
1. Go to AWS Identity Center console
2. Navigate to Permission sets
3. Find "DeveloperAccess"
4. Review the policies and settings

### Rollback (if needed)

If you need to undo the cloning operation:

```bash
awsideman rollback execute --operation-id clone-20240816-143522-def456
```

**Expected Rollback Output:**
```
Rolling Back Operation
=====================

Operation ID: clone-20240816-143522-def456
Type: Permission Set Clone
Date: 2024-08-16 14:35:22

Removing cloned permission set...

Progress: [████████████████████] 100%

Results:
✓ Detached AWS managed policy: PowerUserAccess
✓ Detached AWS managed policy: IAMReadOnlyAccess
✓ Detached customer managed policy: CompanyS3Access
✓ Detached customer managed policy: CompanyLoggingAccess
✓ Removed inline policy
✓ Deleted permission set "DeveloperAccess"

Rollback completed successfully!
Permission set "DeveloperAccess" has been completely removed.
```

## Variations

### Clone with Different Description Only

```bash
# Clone with just a different description
awsideman clone --name PowerUserAccess --to PowerUserAccess-Backup
```

### Clone for Different Environment

```bash
# Create environment-specific permission sets
awsideman clone --name ProductionReadOnly --to StagingReadOnly --description "Read-only access for staging environment"
awsideman clone --name ProductionReadOnly --to DevelopmentReadOnly --description "Read-only access for development environment"
```

### Clone for Team Variations

```bash
# Create team-specific variations
awsideman clone --name BaseDevAccess --to FrontendDevAccess --description "Frontend developer access"
awsideman clone --name BaseDevAccess --to BackendDevAccess --description "Backend developer access"
awsideman clone --name BaseDevAccess --to FullStackDevAccess --description "Full-stack developer access"
```

## Common Issues

### Permission Set Not Found

**Error:** `Permission set 'PowerUserAccess' not found`

**Solution:** Verify the permission set name:
```bash
# List available permission sets
awsideman status check --permission-sets

# Use exact name from the list
awsideman clone --name "Power User Access" --to DeveloperAccess --preview
```

### Target Already Exists

**Error:** `Permission set 'DeveloperAccess' already exists`

**Solutions:**
```bash
# Use a different target name
awsideman clone --name PowerUserAccess --to DeveloperAccess-v2

# Or delete the existing one first (if safe to do so)
# Note: Only do this if you're sure it's not in use
```

### Permission Denied

**Error:** `Access denied: insufficient permissions to create permission set`

**Solution:** Ensure you have the necessary AWS permissions:
- `sso:CreatePermissionSet`
- `sso:DescribePermissionSet`
- `sso:ListManagedPoliciesInPermissionSet`
- `sso:GetInlinePolicyForPermissionSet`
- `sso:AttachManagedPolicyToPermissionSet`
- `sso:PutInlinePolicyToPermissionSet`

### Policy Attachment Failures

**Error:** `Failed to attach customer managed policy 'CompanyS3Access'`

**Solution:** Verify the policy exists and you have access:
```bash
# Check if the policy exists in the target account
aws iam list-policies --scope Local | grep CompanyS3Access

# Clone without the problematic policy, then add it manually
```

## Best Practices

1. **Always preview first** to see what will be cloned
2. **Use descriptive names** for cloned permission sets
3. **Provide clear descriptions** explaining the purpose
4. **Save rollback IDs** for important clones
5. **Review and modify** cloned permission sets as needed
6. **Test the permission set** before assigning to users
7. **Document the relationship** between source and cloned permission sets

## Post-Clone Modifications

After cloning, you typically want to modify the permission set:

### Remove Unnecessary Policies

```bash
# Use AWS CLI or console to remove policies that aren't needed
aws sso-admin detach-managed-policy-from-permission-set \
  --instance-arn arn:aws:sso:::instance/ssoins-1234567890abcdef \
  --permission-set-arn arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef \
  --managed-policy-arn arn:aws:iam::aws:policy/PowerUserAccess
```

### Add Specific Policies

```bash
# Add more restrictive policies
aws sso-admin attach-managed-policy-to-permission-set \
  --instance-arn arn:aws:sso:::instance/ssoins-1234567890abcdef \
  --permission-set-arn arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef \
  --managed-policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
```

### Modify Session Duration

```bash
# Change session duration to 4 hours for developers
aws sso-admin put-permission-set-session-duration \
  --instance-arn arn:aws:sso:::instance/ssoins-1234567890abcdef \
  --permission-set-arn arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef \
  --session-duration PT4H
```

## Related Examples

- [User to User Copy](user-to-user-copy.md)
- [Group to Group Copy](group-to-group-copy.md)
- [Permission Set Management](../filtering-scenarios/permission-set-filtering.md)
- [Rollback Procedures](../rollback-examples/permission-set-rollback.md)
