# Rollback Operations Examples

This directory contains examples and scripts for using the rollback operations feature in awsideman.

## Files Overview

- **[emergency-rollback.sh](emergency-rollback.sh)** - Emergency rollback script with safety checks
- **[rollback-monitor.sh](rollback-monitor.sh)** - Monitoring script for rollback system health
- **[compliance-report.sh](compliance-report.sh)** - Generate compliance reports from operation history
- **[bulk-rollback.sh](bulk-rollback.sh)** - Script for rolling back multiple operations
- **[sample-operation-log.json](sample-operation-log.json)** - Example operation log structure
- **[rollback-config.yaml](rollback-config.yaml)** - Example rollback configuration

## Quick Start

### 1. Basic Rollback Workflow

```bash
# List recent operations
awsideman rollback list --days 7

# Preview a rollback
awsideman rollback apply --dry-run abc123-def456-ghi789

# Apply the rollback
awsideman rollback apply abc123-def456-ghi789
```

### 2. Emergency Rollback

Use the emergency rollback script for quick rollbacks with safety checks:

```bash
./emergency-rollback.sh abc123-def456-ghi789
```

### 3. System Monitoring

Monitor rollback system health:

```bash
./rollback-monitor.sh
```

## Common Scenarios

### Scenario 1: Incorrect Bulk Assignment

You accidentally assigned the wrong permission set to multiple users:

```bash
# Find the bulk operation
awsideman rollback list --operation-type assign --days 1

# Preview the rollback
awsideman rollback apply --dry-run <operation-id>

# Apply the rollback
awsideman rollback apply <operation-id>
```

### Scenario 2: Overprivileged Assignment

You assigned admin access when you meant to assign read-only:

```bash
# Find admin assignments
awsideman rollback list --permission-set AdminAccess --days 7

# Roll back the incorrect assignment
awsideman rollback apply <operation-id>

# Apply the correct assignment
awsideman assignment assign ReadOnlyAccess john.doe --account Production
```

### Scenario 3: Compliance Audit

Generate a report for compliance auditing:

```bash
# Generate quarterly report
./compliance-report.sh

# Review specific user's operations
awsideman rollback list --principal john.doe --days 90 --format json
```

## Best Practices

### 1. Always Preview First

```bash
# Always use --dry-run first
awsideman rollback apply --dry-run <operation-id>
```

### 2. Monitor System Health

```bash
# Check system status regularly
awsideman rollback status

# Monitor for high rollback frequency
./rollback-monitor.sh
```

### 3. Document Rollbacks

```bash
# Keep a log of why rollbacks were performed
echo "$(date): Rolled back operation <operation-id> - Reason: Incorrect permission set" >> rollback-log.txt
```

### 4. Use Appropriate Batch Sizes

```bash
# For large rollbacks, use smaller batch sizes to avoid rate limits
awsideman rollback apply --batch-size 5 <operation-id>
```

## Configuration Examples

### Development Environment

```yaml
rollback:
  enabled: true
  retention_days: 30
  confirmation_required: false
  dry_run_default: true
```

### Production Environment

```yaml
rollback:
  enabled: true
  retention_days: 365
  confirmation_required: true
  dry_run_default: false
  auto_cleanup: true
```

## Troubleshooting

### Common Issues

1. **Operation Not Found**
   - Check if operation ID is correct
   - Verify retention period hasn't expired
   - Check storage directory permissions

2. **State Mismatch**
   - Manual changes may have been made outside awsideman
   - Use dry-run to see current state
   - Verify with AWS console

3. **Rate Limiting**
   - Reduce batch size
   - Add delays between operations
   - Check AWS service limits

### Diagnostic Commands

```bash
# Check system health
awsideman rollback status

# Validate operation logs
python -m json.tool ~/.awsideman/operations/operations.json

# Test AWS connectivity
aws sts get-caller-identity
```

## Integration Examples

### CI/CD Pipeline

```bash
# Pre-deployment check
if [ "$(awsideman rollback list --days 1 --format json | jq '.operations | length')" -gt 0 ]; then
    echo "Recent operations detected. Review before deployment."
    exit 1
fi
```

### Automated Monitoring

```bash
# Add to cron for regular monitoring
0 */6 * * * /path/to/rollback-monitor.sh
```

### Slack Integration

```bash
# Send rollback notifications to Slack
ROLLBACKS=$(awsideman rollback list --days 1 --format json | jq '[.operations[] | select(.operation_type == "rollback")] | length')
if [ "$ROLLBACKS" -gt 0 ]; then
    curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"$ROLLBACKS rollback operations performed today\"}" \
        $SLACK_WEBHOOK_URL
fi
```

## Security Considerations

### 1. Access Control

- Limit rollback permissions to authorized users
- Use separate AWS profiles for rollback operations
- Implement approval workflows for production rollbacks

### 2. Audit Trail

- All rollback operations are automatically logged
- Preserve operation logs for compliance requirements
- Regular backup of operation logs

### 3. Data Protection

- Operation logs contain sensitive permission information
- Ensure proper file permissions (600/700)
- Consider encryption for highly sensitive environments

## Performance Tips

### 1. Batch Size Optimization

- Start with default batch size (10)
- Reduce for rate-limited environments
- Increase for faster processing when possible

### 2. Filtering Efficiency

- Use specific filters to reduce processing time
- Avoid broad date ranges when possible
- Use JSON format only when detailed data is needed

### 3. Storage Management

- Enable auto-cleanup to prevent storage bloat
- Set appropriate retention periods
- Monitor storage usage regularly

---

For more detailed information, see the [Rollback Operations Documentation](../../docs/ROLLBACK_OPERATIONS.md).
