# Basic Examples

Common backup and restore scenarios with practical examples.

## Quick Start Examples

### 1. First Backup

Create your first backup of all AWS Identity Center resources:

```bash
# Simple full backup
awsideman backup create --type full

# With description
awsideman backup create \
    --type full \
    --description "Initial backup of all resources"
```

**Expected Output:**
```
🔄 Creating backup...
✅ Step 1/8: Validating configuration
✅ Step 2/8: Collecting users (25 found)
✅ Step 3/8: Collecting groups (12 found)
✅ Step 4/8: Collecting permission sets (18 found)
✅ Step 5/8: Collecting assignments (67 found)
✅ Step 6/8: Building relationships
✅ Step 7/8: Optimizing data (compression: 2.1x, deduplication: 1.5x)
✅ Step 8/8: Storing backup
🎉 Backup completed successfully: backup-20241201-143022-abc123
```

### 2. List and Validate

Check your backups and validate their integrity:

```bash
# List recent backups
awsideman backup list --recent

# Validate specific backup
awsideman backup validate backup-20241201-143022-abc123

# Get backup details
awsideman backup status backup-20241201-143022-abc123
```

**Expected Output:**
```
┌─────────────────────────────────────┬──────────┬─────────────┬─────────────┬─────────┐
│ Backup ID                          │ Type     │ Created     │ Size        │ Status  │
├─────────────────────────────────────┼──────────┼─────────────┼─────────────┼─────────┤
│ backup-20241201-143022-abc123     │ Full     │ 2024-12-01  │ 2.3 MB     │ ✅      │
│ backup-20241130-143022-def456     │ Full     │ 2024-11-30  │ 2.1 MB     │ ✅      │
└─────────────────────────────────────┴──────────┴─────────────┴─────────────┴─────────┘
```

### 3. Preview Restore

See what would be restored without making changes:

```bash
# Preview restore with overwrite strategy
awsideman restore preview backup-20241201-143022-abc123 --strategy overwrite

# Preview specific resources
awsideman restore preview backup-20241201-143022-abc123 \
    --resource-types users,groups \
    --strategy merge
```

**Expected Output:**
```
🔍 Previewing restore operation...
📊 Resource Summary:
   • Users: 25 (25 new, 0 existing, 0 conflicts)
   • Groups: 12 (12 new, 0 existing, 0 conflicts)
   • Permission Sets: 18 (18 new, 0 existing, 0 conflicts)
   • Assignments: 67 (67 new, 0 existing, 0 conflicts)

⚠️  Conflicts: None detected
✅ Ready to restore with 'overwrite' strategy
```

## Resource-Specific Examples

### 1. User and Group Backup

Backup only user and group resources:

```bash
# Backup users and groups only
awsideman backup create \
    --type full \
    --resource-types users,groups \
    --description "User and group backup for HR department"

# Verify backup contents
awsideman backup validate backup-20241201-143022-abc123
```

### 2. Permission Set Backup

Backup permission sets and assignments:

```bash
# Backup permission-related resources
awsideman backup create \
    --type full \
    --resource-types permission-sets,assignments \
    --description "Permission sets and assignments backup"

# Check assignment mappings
awsideman backup export backup-20241201-143022-abc123 \
    --format json \
    --resource-types assignments
```

### 3. Incremental Backup

Create incremental backups since a specific date:

```bash
# Incremental backup since last week
awsideman backup create \
    --type incremental \
    --since 2024-11-25 \
    --description "Weekly incremental backup"

# Compare with previous backup
awsideman backup list --since 2024-11-20
```

## Conflict Resolution Examples

### 1. Overwrite Strategy

Restore with complete replacement:

```bash
# Restore overwriting all existing resources
awsideman restore restore backup-20241201-143022-abc123 \
    --strategy overwrite \
    --dry-run

# If preview looks good, execute
awsideman restore restore backup-20241201-143022-abc123 \
    --strategy overwrite
```

### 2. Skip Strategy

Restore skipping conflicting resources:

```bash
# Restore skipping conflicts
awsideman restore restore backup-20241201-143022-abc123 \
    --strategy skip \
    --resource-types users,groups

# Check what was skipped
awsideman restore status
```

### 3. Merge Strategy

Restore merging with existing resources:

```bash
# Restore with merge strategy
awsideman restore restore backup-20241201-143022-abc123 \
    --strategy merge \
    --resource-types users,groups

# Review merge results
awsideman restore status
```

## Performance Examples

### 1. Enable Optimizations

Configure performance features:

```bash
# Enable all optimizations
awsideman backup performance enable \
    --compression \
    --deduplication \
    --parallel-processing \
    --resource-monitoring \
    --max-workers 16

# Check status
awsideman backup performance status
```

### 2. Performance Benchmarking

Test system performance:

```bash
# Run standard benchmark
awsideman backup performance benchmark

# Custom benchmark
awsideman backup performance benchmark \
    --iterations 5 \
    --data-size large

# View performance stats
awsideman backup performance stats
```

### 3. Monitor Performance

Track optimization effectiveness:

```bash
# View recent performance
awsideman backup performance stats --since 2024-12-01

# Check resource usage
awsideman backup performance status

# Clear caches if needed
awsideman backup performance clear
```

## Scheduling Examples

### 1. Daily Backup Schedule

Create automated daily backups:

```bash
# Daily backup at 2 AM
awsideman backup schedule create \
    --name "daily-backup" \
    --cron "0 2 * * *" \
    --type full \
    --description "Daily automated backup"

# Verify schedule
awsideman backup schedule list

# Test schedule manually
awsideman backup schedule run daily-backup --dry-run
```

### 2. Weekly Incremental Schedule

Weekly incremental backup schedule:

```bash
# Weekly incremental on Sunday at 3 AM
awsideman backup schedule create \
    --name "weekly-incremental" \
    --cron "0 3 * * 0" \
    --type incremental \
    --description "Weekly incremental backup"

# Check schedule status
awsideman backup schedule status weekly-incremental
```

### 3. Business Hours Schedule

Backup during business hours:

```bash
# Backup at 6 PM on weekdays
awsideman backup schedule create \
    --name "business-hours-backup" \
    --cron "0 18 * * 1-5" \
    --type full \
    --description "End-of-day backup on weekdays"

# List all schedules
awsideman backup schedule list
```

## Export and Import Examples

### 1. Export to Different Formats

Export backup data in various formats:

```bash
# Export to JSON
awsideman backup export backup-20241201-143022-abc123 \
    --format json \
    --output backup-data.json

# Export to YAML
awsideman backup export backup-20241201-143022-abc123 \
    --format yaml \
    --output backup-data.yaml

# Export specific resources to CSV
awsideman backup export backup-20241201-143022-abc123 \
    --format csv \
    --output users.csv \
    --resource-types users
```

### 2. Import External Data

Import data from external sources:

```bash
# Import from JSON file
awsideman backup import backup-data.json

# Import with validation only
awsideman backup import users.yaml --validate-only

# Preview import
awsideman backup import backup-data.json --dry-run
```

## Troubleshooting Examples

### 1. Backup Failures

Handle backup failures:

```bash
# Check backup status
awsideman backup status

# Validate configuration
awsideman backup create --type full --dry-run

# Check storage space
df -h /var/backups/awsideman

# Review error logs
awsideman backup status --operation-id op-123456
```

### 2. Restore Issues

Resolve restore problems:

```bash
# Preview with different strategies
awsideman restore preview backup-20241201-143022-abc123 --strategy skip
awsideman restore preview backup-20241201-143022-abc123 --strategy merge

# Validate compatibility
awsideman restore validate backup-20241201-143022-abc123

# Check permissions
awsideman restore restore backup-20241201-143022-abc123 --dry-run
```

### 3. Performance Problems

Optimize performance:

```bash
# Check current settings
awsideman backup performance status

# Adjust worker count
awsideman backup performance enable --max-workers 4

# Monitor resource usage
awsideman backup performance stats

# Run diagnostics
awsideman backup performance benchmark
```

## Complete Workflow Examples

### 1. Daily Backup Workflow

Complete daily backup process:

```bash
# 1. Check system status
awsideman backup performance status
awsideman backup schedule list

# 2. Create daily backup
awsideman backup create \
    --type full \
    --description "Daily backup $(date +%Y-%m-%d)"

# 3. Validate backup
awsideman backup validate backup-$(date +%Y%m%d)-*

# 4. Check storage usage
awsideman backup list --recent

# 5. Clean up old backups
awsideman backup delete --older-than 30d --dry-run
```

### 2. Disaster Recovery Workflow

Complete disaster recovery process:

```bash
# 1. List available backups
awsideman backup list --recent

# 2. Validate backup integrity
awsideman backup validate backup-20241201-143022-abc123

# 3. Check restore compatibility
awsideman restore validate backup-20241201-143022-abc123

# 4. Preview restore
awsideman restore preview backup-20241201-143022-abc123 --strategy overwrite

# 5. Execute restore
awsideman restore restore backup-20241201-143022-abc123 --strategy overwrite

# 6. Verify restore
awsideman restore status
```

### 3. Migration Workflow

Migrate between environments:

```bash
# 1. Backup source environment
awsideman backup create \
    --type full \
    --description "Migration backup from production"

# 2. Export to portable format
awsideman backup export backup-20241201-143022-abc123 \
    --format json \
    --output migration-backup.json

# 3. Transfer to target environment
scp migration-backup.json target-server:/tmp/

# 4. Import to target environment
awsideman backup import /tmp/migration-backup.json

# 5. Validate import
awsideman backup validate backup-import-*

# 6. Restore to target
awsideman restore restore backup-import-* --strategy overwrite
```

## Best Practices

### 1. Always Use Dry-Run First
```bash
# Preview before execution
awsideman backup create --type full --dry-run
awsideman restore restore backup-id --dry-run
awsideman backup delete --older-than 30d --dry-run
```

### 2. Validate After Operations
```bash
# Validate backups after creation
awsideman backup validate backup-id

# Validate before restore
awsideman restore validate backup-id
```

### 3. Monitor Performance
```bash
# Regular performance checks
awsideman backup performance stats
awsideman backup performance status

# Benchmark periodically
awsideman backup performance benchmark
```

### 4. Use Descriptive Names
```bash
# Meaningful descriptions
awsideman backup create \
    --description "Monthly full backup - December 2024"

# Named schedules
awsideman backup schedule create \
    --name "monthly-full-backup" \
    --cron "0 2 1 * *"
```

## Next Steps

1. **[Enterprise Examples](enterprise-examples.md)** - Complex organizational workflows
2. **[Automation Scripts](automation-scripts.md)** - CI/CD and automation examples
3. **[Configuration Templates](configuration-templates.md)** - Ready-to-use configs
4. **[Troubleshooting](../troubleshooting.md)** - Solve common problems
