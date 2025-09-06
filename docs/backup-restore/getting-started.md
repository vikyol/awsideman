# Getting Started with Backup & Restore

This guide will walk you through setting up and using the AWS Identity Center backup and restore system.

## Prerequisites

### AWS Permissions
Your AWS credentials must have the following permissions:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "sso:ListUsers",
                "sso:ListGroups",
                "sso:ListPermissionSets",
                "sso:ListAccountAssignments",
                "sso:DescribePermissionSet",
                "sso:DescribeUser",
                "sso:DescribeGroup",
                "sso:GetPermissionSet",
                "organizations:ListAccounts",
                "organizations:DescribeAccount",
                "organizations:DescribeOrganization"
            ],
            "Resource": "*"
        }
    ]
}
```

### System Requirements
- Python 3.11 or higher
- 2GB RAM minimum (4GB recommended)
- 10GB free disk space for local storage
- Network access to AWS APIs

## Installation

### 1. Install awsideman
```bash
# Using pip
pip install awsideman

# Using Poetry
poetry add awsideman

# From source
git clone https://github.com/vikyol/awsideman.git
cd awsideman
poetry install
```

### 2. Configure AWS Credentials
```bash
# Set up AWS CLI profile
aws configure --profile backup-admin

# Or use environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

### 3. Verify Installation
```bash
# Check awsideman version
awsideman --version

# Verify backup commands are available
awsideman backup --help
```

## First Backup

### 1. Create Your First Backup
```bash
# Simple full backup
awsideman backup create --type full

# Backup with specific resources
awsideman backup create \
    --type full \
    --resource-types users,groups,permission-sets \
    --description "Initial backup of core resources"
```

### 2. Monitor Progress
The backup process will show real-time progress:
```
🔄 Creating backup...
✅ Step 1/8: Validating configuration
✅ Step 2/8: Collecting users (15 found)
✅ Step 3/8: Collecting groups (8 found)
✅ Step 4/8: Collecting permission sets (12 found)
✅ Step 5/8: Collecting assignments (45 found)
✅ Step 6/8: Building relationships
✅ Step 7/8: Optimizing data (compression: 2.3x, deduplication: 1.8x)
✅ Step 8/8: Storing backup
🎉 Backup completed successfully: backup-20241201-143022-abc123
```

### 3. Verify Backup
```bash
# List all backups
awsideman backup list

# Get backup details
awsideman backup status backup-20241201-143022-abc123

# Validate backup integrity
awsideman backup validate backup-20241201-143022-abc123
```

## Basic Configuration

### 1. Create Configuration File
Create `~/.awsideman/config.toml`:
```toml
[backup]
# Storage configuration
storage_backend = "filesystem"
storage_path = "/var/backups/awsideman"

# Performance settings
compression_enabled = true
compression_algorithm = "lz4"
deduplication_enabled = true
parallel_processing_enabled = true
max_workers = 8

# Retention policy
retention_daily = 7
retention_weekly = 4
retention_monthly = 12
retention_yearly = 3

[backup.encryption]
enabled = true
algorithm = "AES-256"
key_id = "alias/awsideman-backup-key"

[backup.scheduling]
enabled = true
default_schedule = "0 2 * * *"  # Daily at 2 AM
```

### 2. Environment-Specific Configs
```bash
# Development environment
export AWSIDEMAN_CONFIG=~/.awsideman/config-dev.toml

# Production environment
export AWSIDEMAN_CONFIG=~/.awsideman/config-prod.toml
```

## First Restore

### 1. Preview Restore
```bash
# See what would be restored
awsideman restore preview backup-20241201-143022-abc123

# Preview with specific resources
awsideman restore preview backup-20241201-143022-abc123 \
    --resource-types users,groups
```

### 2. Execute Restore
```bash
# Restore with conflict resolution
awsideman restore restore backup-20241201-143022-abc123 \
    --strategy overwrite \
    --dry-run

# If preview looks good, remove --dry-run
awsideman restore restore backup-20241201-143022-abc123 \
    --strategy overwrite
```

## Scheduling Automated Backups

### 1. Create Backup Schedule
```bash
# Daily backup at 2 AM
awsideman backup schedule create \
    --name "daily-backup" \
    --cron "0 2 * * *" \
    --type full \
    --description "Daily automated backup"

# Weekly incremental backup
awsideman backup schedule create \
    --name "weekly-incremental" \
    --cron "0 3 * * 0" \
    --type incremental \
    --description "Weekly incremental backup"
```

### 2. Monitor Schedules
```bash
# List all schedules
awsideman backup schedule list

# Check schedule status
awsideman backup schedule status daily-backup

# Run schedule manually
awsideman backup schedule run daily-backup
```

## Performance Optimization

### 1. Enable Performance Features
```bash
# Enable all optimizations
awsideman backup performance enable \
    --compression \
    --deduplication \
    --parallel-processing \
    --resource-monitoring \
    --max-workers 16

# Check optimization status
awsideman backup performance status

# Run performance benchmark
awsideman backup performance benchmark
```

### 2. Monitor Performance
```bash
# View performance statistics
awsideman backup performance stats

# Clear optimization caches
awsideman backup performance clear
```

## Common Workflows

### Daily Operations
```bash
# Check backup status
awsideman backup list --recent

# Monitor scheduled backups
awsideman backup schedule list

# Check storage usage
awsideman backup status
```

### Weekly Operations
```bash
# Validate all recent backups
awsideman backup list --recent | xargs -I {} awsideman backup validate {}

# Clean up old backups
awsideman backup delete --older-than 30d

# Performance review
awsideman backup performance stats
```

### Monthly Operations
```bash
# Full system backup
awsideman backup create --type full --description "Monthly full backup"

# Test restore procedure
awsideman restore preview <latest-backup-id>

# Review retention policies
awsideman backup list --all
```

## Troubleshooting

### Common Issues

#### Backup Fails
```bash
# Check error details
awsideman backup status <operation-id>

# Verify permissions
awsideman backup create --type full --dry-run

# Check storage space
df -h /var/backups/awsideman
```

#### Restore Conflicts
```bash
# Preview with different strategies
awsideman restore preview <backup-id> --strategy skip
awsideman restore preview <backup-id> --strategy merge

# Validate compatibility
awsideman restore validate <backup-id>
```

#### Performance Issues
```bash
# Check resource usage
awsideman backup performance stats

# Adjust worker count
awsideman backup performance enable --max-workers 4

# Monitor system resources
awsideman backup performance status
```

## Next Steps

1. **[Backup Operations](backup-operations.md)** - Learn advanced backup techniques
2. **[Restore Operations](restore-operations.md)** - Master restore procedures
3. **[Configuration](configuration.md)** - Customize your setup
4. **[Examples](examples/basic-examples.md)** - See practical examples
5. **[Troubleshooting](troubleshooting.md)** - Solve common problems

## Support

- **Documentation**: [Complete Guide](../README.md)
- **Examples**: [Practical Examples](examples/basic-examples.md)
- **Issues**: [GitHub Issues](https://github.com/vikyol/awsideman/issues)
- **Discussions**: [GitHub Discussions](https://github.com/vikyol/awsideman/discussions)
