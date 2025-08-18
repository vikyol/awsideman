# Configuration Templates

Ready-to-use configuration templates for different backup and restore scenarios.

## Basic Configuration

### Minimal Configuration

**File: `~/.awsideman/config-minimal.toml`**
```toml
[backup]
storage_backend = "filesystem"
storage_path = "/var/backups/awsideman"

[backup.encryption]
enabled = true
algorithm = "AES-256"
```

### Standard Configuration

**File: `~/.awsideman/config-standard.toml`**
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

## Environment-Specific Configurations

### Development Environment

**File: `~/.awsideman/config-dev.toml`**
```toml
[backup]
storage_backend = "filesystem"
storage_path = "/tmp/awsideman-dev"

# Development optimizations
compression_enabled = true
compression_algorithm = "gzip"
deduplication_enabled = false
parallel_processing_enabled = true
max_workers = 4

# Shorter retention for dev
retention_daily = 3
retention_weekly = 2
retention_monthly = 3
retention_yearly = 1

[backup.encryption]
enabled = false  # Disable for development

[backup.scheduling]
enabled = false  # Manual backups only

[backup.logging]
level = "DEBUG"
file_path = "/tmp/awsideman-dev.log"
```

### Staging Environment

**File: `~/.awsideman/config-staging.toml`**
```toml
[backup]
storage_backend = "filesystem"
storage_path = "/var/backups/awsideman-staging"

# Balanced performance
compression_enabled = true
compression_algorithm = "lz4"
deduplication_enabled = true
parallel_processing_enabled = true
max_workers = 6

# Medium retention
retention_daily = 5
retention_weekly = 3
retention_monthly = 6
retention_yearly = 2

[backup.encryption]
enabled = true
algorithm = "AES-256"

[backup.scheduling]
enabled = true
default_schedule = "0 3 * * *"  # Daily at 3 AM

[backup.logging]
level = "INFO"
file_path = "/var/log/awsideman/staging.log"
```

### Production Environment

**File: `~/.awsideman/config-prod.toml`**
```toml
[backup]
storage_backend = "s3"
storage_path = "s3://company-backups/awsideman/prod"

# Maximum performance
compression_enabled = true
compression_algorithm = "lz4"
deduplication_enabled = true
parallel_processing_enabled = true
max_workers = 16

# Long retention
retention_daily = 7
retention_weekly = 4
retention_monthly = 12
retention_yearly = 5

[backup.encryption]
enabled = true
algorithm = "AES-256"
key_id = "alias/company-backup-key"

[backup.scheduling]
enabled = true
default_schedule = "0 2 * * *"  # Daily at 2 AM

[backup.logging]
level = "WARNING"
file_path = "/var/log/awsideman/production.log"

[backup.monitoring]
enabled = true
alert_email = "backup-alerts@company.com"
alert_webhook = "https://hooks.slack.com/services/xxx/yyy/zzz"
```

## Storage Backend Configurations

### Local Filesystem Storage

**File: `~/.awsideman/config-filesystem.toml`**
```toml
[backup]
storage_backend = "filesystem"
storage_path = "/var/backups/awsideman"

[backup.filesystem]
# File permissions
file_mode = "0644"
directory_mode = "0755"
owner = "awsideman"
group = "awsideman"

# Storage limits
max_size_gb = 100
max_files = 1000

# Cleanup settings
cleanup_enabled = true
cleanup_interval_hours = 24
```

### S3 Storage

**File: `~/.awsideman/config-s3.toml`**
```toml
[backup]
storage_backend = "s3"
storage_path = "s3://company-backups/awsideman"

[backup.s3]
bucket = "company-backups"
prefix = "awsideman"
region = "us-east-1"

# S3 settings
storage_class = "STANDARD_IA"
encryption = "AES256"
versioning = true

# Transfer settings
multipart_threshold_mb = 100
multipart_chunk_size_mb = 50
max_concurrent_uploads = 10

# Lifecycle policies
lifecycle_enabled = true
transition_to_ia_days = 30
transition_to_glacier_days = 90
expiration_days = 2555  # 7 years
```

### Hybrid Storage (Local + S3)

**File: `~/.awsideman/config-hybrid.toml`**
```toml
[backup]
storage_backend = "hybrid"
primary_storage = "filesystem"
secondary_storage = "s3"

[backup.filesystem]
storage_path = "/var/backups/awsideman"
max_size_gb = 50

[backup.s3]
bucket = "company-backups"
prefix = "awsideman/archive"
region = "us-east-1"

[backup.hybrid]
# Sync settings
sync_enabled = true
sync_interval_hours = 6
sync_retention_days = 7  # Keep local for 7 days, then S3 only
```

## Performance Configurations

### High Performance

**File: `~/.awsideman/config-high-performance.toml`**
```toml
[backup]
storage_backend = "s3"
storage_path = "s3://company-backups/awsideman"

# Maximum performance settings
compression_enabled = true
compression_algorithm = "lz4"
deduplication_enabled = true
parallel_processing_enabled = true
max_workers = 32

# Advanced optimizations
batch_size = 1000
memory_limit_gb = 8
cache_enabled = true
cache_size_mb = 1024

[backup.performance]
# Compression settings
compression_level = 1  # Fast compression
compression_threads = 4

# Deduplication settings
chunk_size_kb = 64
hash_algorithm = "blake2b"

# Parallel processing
process_pool_size = 8
thread_pool_size = 16
```

### Balanced Performance

**File: `~/.awsideman/config-balanced.toml`**
```toml
[backup]
storage_backend = "filesystem"
storage_path = "/var/backups/awsideman"

# Balanced settings
compression_enabled = true
compression_algorithm = "gzip"
deduplication_enabled = true
parallel_processing_enabled = true
max_workers = 8

# Moderate optimizations
batch_size = 500
memory_limit_gb = 4
cache_enabled = true
cache_size_mb = 512

[backup.performance]
# Compression settings
compression_level = 6  # Balanced compression
compression_threads = 2

# Deduplication settings
chunk_size_kb = 128
hash_algorithm = "sha256"

# Parallel processing
process_pool_size = 4
thread_pool_size = 8
```

### Resource Constrained

**File: `~/.awsideman/config-low-resource.toml`**
```toml
[backup]
storage_backend = "filesystem"
storage_path = "/var/backups/awsideman"

# Minimal resource usage
compression_enabled = true
compression_algorithm = "zlib"
deduplication_enabled = false
parallel_processing_enabled = true
max_workers = 2

# Conservative settings
batch_size = 100
memory_limit_gb = 1
cache_enabled = false

[backup.performance]
# Compression settings
compression_level = 1  # Fast, low CPU
compression_threads = 1

# Parallel processing
process_pool_size = 1
thread_pool_size = 2
```

## Security Configurations

### High Security

**File: `~/.awsideman/config-high-security.toml`**
```toml
[backup]
storage_backend = "s3"
storage_path = "s3://company-backups/awsideman"

# Encryption settings
encryption_enabled = true
algorithm = "AES-256"
key_id = "alias/company-backup-key"
key_rotation_days = 90

# Access control
require_mfa = true
allowed_ips = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
allowed_roles = ["arn:aws:iam::123456789012:role/BackupAdmin"]

# Audit logging
audit_logging_enabled = true
audit_retention_days = 2555
audit_encryption = true

[backup.security]
# Data protection
data_classification = "confidential"
retention_compliance = true
secure_deletion = true

# Network security
vpc_only = true
endpoint_policy = "strict"
```

### Compliance Focused

**File: `~/.awsideman/config-compliance.toml`**
```toml
[backup]
storage_backend = "s3"
storage_path = "s3://company-backups/awsideman"

# Compliance settings
compliance_standard = "SOC2"
data_retention_years = 7
audit_trail_enabled = true

# Encryption
encryption_enabled = true
algorithm = "AES-256"
key_management = "AWS_KMS"
key_rotation_enabled = true

[backup.compliance]
# Data handling
data_classification = "regulated"
pii_handling = "encrypted"
gdpr_compliance = true

# Retention policies
legal_hold_enabled = true
discovery_enabled = true
retention_locks = true

# Monitoring
access_monitoring = true
change_detection = true
compliance_reporting = true
```

## Multi-Environment Configurations

### Development to Production

**File: `~/.awsideman/config-multi-env.toml`**
```toml
[environments.dev]
storage_backend = "filesystem"
storage_path = "/tmp/awsideman-dev"
compression_enabled = true
max_workers = 2
retention_daily = 3
encryption_enabled = false

[environments.staging]
storage_backend = "filesystem"
storage_path = "/var/backups/awsideman-staging"
compression_enabled = true
max_workers = 4
retention_daily = 5
encryption_enabled = true

[environments.production]
storage_backend = "s3"
storage_path = "s3://company-backups/awsideman/prod"
compression_enabled = true
max_workers = 16
retention_daily = 7
encryption_enabled = true
key_id = "alias/company-backup-key"

[environments.production.scheduling]
enabled = true
daily_schedule = "0 2 * * *"
weekly_schedule = "0 3 * * 0"
monthly_schedule = "0 4 1 * *"
```

## Specialized Configurations

### Disaster Recovery

**File: `~/.awsideman/config-dr.toml`**
```toml
[backup]
storage_backend = "hybrid"
primary_storage = "s3"
secondary_storage = "s3"
secondary_region = "us-west-2"

# DR-specific settings
replication_enabled = true
replication_interval_minutes = 15
cross_region_backup = true
failover_enabled = true

[backup.dr]
# Recovery settings
rto_minutes = 60
rpo_minutes = 15
automated_failover = true
failover_testing = true

# Backup verification
verification_enabled = true
verification_interval_hours = 1
restore_testing = true
restore_test_interval_days = 7
```

### High Availability

**File: `~/.awsideman/config-ha.toml`**
```toml
[backup]
storage_backend = "distributed"
primary_storage = "s3"
secondary_storage = "s3"
tertiary_storage = "filesystem"

# HA settings
redundancy_factor = 3
health_check_interval_seconds = 30
auto_failover = true
load_balancing = true

[backup.ha]
# Cluster settings
cluster_mode = true
cluster_size = 3
leader_election = true
consensus_required = 2

# Monitoring
health_monitoring = true
performance_monitoring = true
alerting_enabled = true
```

## Usage Examples

### Load Configuration

```bash
# Use specific configuration
export AWSIDEMAN_CONFIG=~/.awsideman/config-prod.toml
awsideman backup create --type full

# Or specify on command line
awsideman backup create --type full --config ~/.awsideman/config-prod.toml
```

### Switch Environments

```bash
# Development
export AWSIDEMAN_CONFIG=~/.awsideman/config-dev.toml
awsideman backup create --type full

# Staging
export AWSIDEMAN_CONFIG=~/.awsideman/config-staging.toml
awsideman backup create --type full

# Production
export AWSIDEMAN_CONFIG=~/.awsideman/config-prod.toml
awsideman backup create --type full
```

### Validate Configuration

```bash
# Check configuration syntax
awsideman backup create --type full --dry-run

# Validate specific sections
awsideman backup performance status
awsideman backup schedule list
```

## Configuration Best Practices

### 1. Environment Separation
- Use separate configs for dev/staging/prod
- Never use production config in development
- Use environment variables for sensitive values

### 2. Security First
- Always enable encryption in production
- Use IAM roles instead of access keys
- Implement least privilege access

### 3. Performance Tuning
- Start with balanced settings
- Monitor and adjust based on usage
- Consider resource constraints

### 4. Monitoring and Alerting
- Enable comprehensive logging
- Set up performance monitoring
- Configure alerting for critical issues

### 5. Backup and Version Control
- Keep configs in version control
- Document configuration changes
- Test configurations before production use

## Next Steps

1. **[Basic Examples](basic-examples.md)** - Common backup/restore scenarios
2. **[Automation Scripts](automation-scripts.md)** - CI/CD and automation
3. **[Troubleshooting](../troubleshooting.md)** - Solve configuration issues
4. **[CLI Reference](../cli-reference.md)** - Configuration options
