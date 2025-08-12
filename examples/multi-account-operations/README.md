# Multi-Account Operations Examples

This directory contains practical examples for using awsideman's multi-account operations across various scenarios and organizational structures.

## Directory Structure

```
examples/multi-account-operations/
├── README.md                          # This file
├── basic-scenarios.md                 # Simple use cases
├── advanced-filtering.md              # Complex filtering examples
├── enterprise-workflows.md            # Large-scale enterprise examples
├── automation-scripts/                # Automation examples
│   ├── onboard-new-employee.sh
│   ├── offboard-employee.sh
│   └── rotate-permissions.sh
└── sample-data/                       # Sample account structures
    ├── small-org-accounts.json
    ├── medium-org-accounts.json
    └── enterprise-accounts.json
```

## Quick Start Examples

### 1. Assign ReadOnly Access to All Accounts

```bash
# Preview the operation first
awsideman assignment assign ReadOnlyAccess john.doe --filter "*" --dry-run

# Execute after review
awsideman assignment assign ReadOnlyAccess john.doe --filter "*"
```

### 2. Assign Development Access to Dev Accounts

```bash
awsideman assignment assign DeveloperAccess jane.smith \
  --filter "tag:Environment=Development"
```

### 3. Revoke Access from Former Employee

```bash
awsideman assignment revoke PowerUserAccess former.employee \
  --filter "*" \
  --batch-size 5
```

## Filtering Scenarios

### Environment-Based Filtering

```bash
# Production accounts only
--filter "tag:Environment=Production"

# Development and staging accounts
--filter "tag:Environment=Development"
--filter "tag:Environment=Staging"

# Non-production accounts (requires multiple commands)
awsideman assignment assign DevAccess user --filter "tag:Environment=Development"
awsideman assignment assign DevAccess user --filter "tag:Environment=Staging"
awsideman assignment assign DevAccess user --filter "tag:Environment=Testing"
```

### Department-Based Filtering

```bash
# Finance department accounts
--filter "tag:Department=Finance"

# Engineering team accounts
--filter "tag:Team=Engineering"

# Multiple departments (separate commands)
awsideman assignment assign ReadOnly auditor --filter "tag:Department=Finance"
awsideman assignment assign ReadOnly auditor --filter "tag:Department=HR"
```

### Region-Based Filtering

```bash
# US East region accounts
--filter "tag:Region=us-east-1"

# European accounts
--filter "tag:Region=eu-west-1"

# Multi-region deployment accounts
--filter "tag:Deployment=MultiRegion"
```

### Compliance-Based Filtering

```bash
# SOX compliance accounts
--filter "tag:Compliance=SOX"

# HIPAA compliance accounts
--filter "tag:Compliance=HIPAA"

# High security accounts
--filter "tag:SecurityLevel=High"
```

## Performance Optimization Examples

### Small Organization (< 50 accounts)

```bash
# Use larger batch size for faster processing
awsideman assignment assign ReadOnly user --filter "*" --batch-size 15
```

### Medium Organization (50-200 accounts)

```bash
# Balanced batch size
awsideman assignment assign ReadOnly user --filter "*" --batch-size 10
```

### Large Organization (200+ accounts)

```bash
# Smaller batch size to avoid rate limits
awsideman assignment multi-assign ReadOnly user --filter "*" --batch-size 5
```

### Very Large Organization (500+ accounts)

```bash
# Process in chunks by environment
awsideman assignment multi-assign ReadOnly user --filter "tag:Environment=Production" --batch-size 3
awsideman assignment multi-assign ReadOnly user --filter "tag:Environment=Development" --batch-size 3
awsideman assignment multi-assign ReadOnly user --filter "tag:Environment=Staging" --batch-size 3
```

## Common Workflows

### New Employee Onboarding

```bash
#!/bin/bash
# onboard-new-employee.sh

USERNAME=$1
DEPARTMENT=$2
ROLE=$3

echo "Onboarding new employee: $USERNAME"

# Step 1: Assign basic read access to all accounts
echo "Assigning basic read access..."
awsideman assignment multi-assign ReadOnlyAccess "$USERNAME" --filter "*"

# Step 2: Assign department-specific access
echo "Assigning department access..."
awsideman assignment multi-assign DepartmentAccess "$USERNAME" \
  --filter "tag:Department=$DEPARTMENT"

# Step 3: Assign role-specific access to appropriate environments
case $ROLE in
  "Developer")
    awsideman assignment multi-assign DeveloperAccess "$USERNAME" \
      --filter "tag:Environment=Development"
    ;;
  "DevOps")
    awsideman assignment multi-assign PowerUserAccess "$USERNAME" \
      --filter "tag:Environment=Development"
    awsideman assignment multi-assign PowerUserAccess "$USERNAME" \
      --filter "tag:Environment=Staging"
    ;;
  "Manager")
    awsideman assignment multi-assign ManagerAccess "$USERNAME" \
      --filter "tag:Department=$DEPARTMENT"
    ;;
esac

echo "Onboarding completed for $USERNAME"
```

### Employee Offboarding

```bash
#!/bin/bash
# offboard-employee.sh

USERNAME=$1

echo "Offboarding employee: $USERNAME"

# Remove all access across all accounts
awsideman assignment multi-revoke ReadOnlyAccess "$USERNAME" --filter "*"
awsideman assignment multi-revoke DeveloperAccess "$USERNAME" --filter "*"
awsideman assignment multi-revoke PowerUserAccess "$USERNAME" --filter "*"
awsideman assignment multi-revoke ManagerAccess "$USERNAME" --filter "*"

echo "Offboarding completed for $USERNAME"
```

### Quarterly Access Review

```bash
#!/bin/bash
# quarterly-access-review.sh

echo "Starting quarterly access review..."

# Generate reports for each environment
for env in Production Staging Development; do
  echo "Reviewing $env environment..."

  # This would typically integrate with reporting tools
  awsideman assignment list --filter "tag:Environment=$env" > "access-report-$env.csv"
done

echo "Access review reports generated"
```

## Error Handling Examples

### Robust Assignment with Error Handling

```bash
#!/bin/bash
# robust-assignment.sh

USERNAME=$1
PERMISSION_SET=$2
FILTER=$3

echo "Assigning $PERMISSION_SET to $USERNAME with filter: $FILTER"

# Step 1: Validate inputs
if [[ -z "$USERNAME" || -z "$PERMISSION_SET" || -z "$FILTER" ]]; then
  echo "Error: Missing required parameters"
  echo "Usage: $0 <username> <permission-set> <filter>"
  exit 1
fi

# Step 2: Test with dry-run first
echo "Testing with dry-run..."
if ! awsideman assignment multi-assign "$PERMISSION_SET" "$USERNAME" \
  --filter "$FILTER" --dry-run; then
  echo "Error: Dry-run failed. Please check your parameters."
  exit 1
fi

# Step 3: Confirm with user
read -p "Proceed with actual assignment? (y/N): " confirm
if [[ $confirm != [yY] ]]; then
  echo "Operation cancelled."
  exit 0
fi

# Step 4: Execute with error handling
echo "Executing assignment..."
if awsideman assignment multi-assign "$PERMISSION_SET" "$USERNAME" \
  --filter "$FILTER" --batch-size 5; then
  echo "Assignment completed successfully!"
else
  echo "Assignment failed. Check the output above for details."
  exit 1
fi
```

### Retry Failed Operations

```bash
#!/bin/bash
# retry-failed-operations.sh

# List of accounts that failed in previous operation
FAILED_ACCOUNTS=(
  "123456789012"
  "123456789013"
  "123456789014"
)

USERNAME=$1
PERMISSION_SET=$2

echo "Retrying failed operations for $USERNAME"

for account in "${FAILED_ACCOUNTS[@]}"; do
  echo "Processing account: $account"

  if awsideman assignment assign "$PERMISSION_SET" "$USERNAME" \
    --account "$account"; then
    echo "✅ Success: $account"
  else
    echo "❌ Failed: $account"
  fi

  # Small delay to avoid rate limiting
  sleep 2
done

echo "Retry operations completed"
```

## Integration Examples

### CI/CD Pipeline Integration

```yaml
# .github/workflows/permission-management.yml
name: Permission Management

on:
  workflow_dispatch:
    inputs:
      action:
        description: 'Action to perform'
        required: true
        type: choice
        options:
          - assign
          - revoke
      username:
        description: 'Username'
        required: true
        type: string
      permission_set:
        description: 'Permission Set'
        required: true
        type: string
      environment:
        description: 'Target Environment'
        required: true
        type: choice
        options:
          - Development
          - Staging
          - Production

jobs:
  manage-permissions:
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Install awsideman
        run: pip install awsideman

      - name: Dry run operation
        run: |
          awsideman assignment multi-${{ github.event.inputs.action }} \
            "${{ github.event.inputs.permission_set }}" \
            "${{ github.event.inputs.username }}" \
            --filter "tag:Environment=${{ github.event.inputs.environment }}" \
            --dry-run

      - name: Execute operation
        if: github.event.inputs.action == 'assign' || github.event.inputs.action == 'revoke'
        run: |
          awsideman assignment multi-${{ github.event.inputs.action }} \
            "${{ github.event.inputs.permission_set }}" \
            "${{ github.event.inputs.username }}" \
            --filter "tag:Environment=${{ github.event.inputs.environment }}" \
            --batch-size 5
```

### Terraform Integration

```hcl
# terraform/permission-management.tf

resource "null_resource" "assign_permissions" {
  count = length(var.new_users)

  provisioner "local-exec" {
    command = <<-EOT
      awsideman assignment multi-assign ReadOnlyAccess ${var.new_users[count.index]} \
        --filter "tag:Environment=${var.environment}" \
        --batch-size 5
    EOT
  }

  triggers = {
    users = join(",", var.new_users)
    environment = var.environment
  }
}

variable "new_users" {
  description = "List of new users to assign permissions"
  type        = list(string)
  default     = []
}

variable "environment" {
  description = "Target environment"
  type        = string
  default     = "Development"
}
```

## Monitoring and Alerting Examples

### CloudWatch Integration

```bash
#!/bin/bash
# monitor-multi-account-operations.sh

# Function to send CloudWatch metrics
send_metric() {
  local metric_name=$1
  local value=$2
  local unit=$3

  aws cloudwatch put-metric-data \
    --namespace "AwsIdeman/MultiAccount" \
    --metric-data MetricName="$metric_name",Value="$value",Unit="$unit"
}

# Execute operation and capture metrics
start_time=$(date +%s)

if awsideman assignment multi-assign ReadOnlyAccess "$USERNAME" \
  --filter "$FILTER" --batch-size 5; then

  end_time=$(date +%s)
  duration=$((end_time - start_time))

  # Send success metrics
  send_metric "OperationSuccess" 1 "Count"
  send_metric "OperationDuration" "$duration" "Seconds"
else
  # Send failure metrics
  send_metric "OperationFailure" 1 "Count"
fi
```

### Slack Integration

```bash
#!/bin/bash
# slack-notification.sh

SLACK_WEBHOOK_URL="your-webhook-url"

send_slack_notification() {
  local message=$1
  local color=$2

  curl -X POST -H 'Content-type: application/json' \
    --data "{\"attachments\":[{\"color\":\"$color\",\"text\":\"$message\"}]}" \
    "$SLACK_WEBHOOK_URL"
}

# Execute operation with notification
if awsideman assignment multi-assign ReadOnlyAccess "$USERNAME" \
  --filter "$FILTER"; then

  send_slack_notification \
    "✅ Successfully assigned ReadOnlyAccess to $USERNAME across filtered accounts" \
    "good"
else
  send_slack_notification \
    "❌ Failed to assign ReadOnlyAccess to $USERNAME" \
    "danger"
fi
```

## Testing Examples

### Unit Test for Automation Scripts

```bash
#!/bin/bash
# test-automation-scripts.sh

# Test onboarding script
test_onboarding() {
  echo "Testing onboarding script..."

  # Test with dry-run
  if ./onboard-new-employee.sh "test.user" "Engineering" "Developer" --dry-run; then
    echo "✅ Onboarding test passed"
  else
    echo "❌ Onboarding test failed"
    return 1
  fi
}

# Test offboarding script
test_offboarding() {
  echo "Testing offboarding script..."

  # Test with dry-run
  if ./offboard-employee.sh "test.user" --dry-run; then
    echo "✅ Offboarding test passed"
  else
    echo "❌ Offboarding test failed"
    return 1
  fi
}

# Run tests
test_onboarding
test_offboarding

echo "All tests completed"
```

## Best Practices Summary

1. **Always use dry-run first** for any multi-account operation
2. **Use specific filters** instead of wildcards when possible
3. **Start with small batch sizes** and increase based on performance
4. **Implement error handling** in automation scripts
5. **Monitor and log** all multi-account operations
6. **Test scripts** in non-production environments first
7. **Document your filters** and their intended use cases
8. **Regular access reviews** using automated reporting
9. **Implement approval workflows** for production changes
10. **Maintain audit trails** for compliance requirements

## Next Steps

- Review the [troubleshooting guide](../docs/MULTI_ACCOUNT_TROUBLESHOOTING.md) for common issues
- Explore [performance optimization](../docs/MULTI_ACCOUNT_OPERATIONS.md#performance-considerations) techniques
- Set up [monitoring and alerting](../docs/MONITORING.md) for your operations
- Integrate with your [CI/CD pipelines](../docs/CICD_INTEGRATION.md)
