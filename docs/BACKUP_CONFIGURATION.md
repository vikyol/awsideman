# Backup Configuration Guide

This guide explains how to configure backup settings in awsideman to avoid having to specify the same options repeatedly on every backup command.

## Overview

The backup configuration system allows you to set default values for backup operations in your `~/.awsideman/config.yaml` file. This eliminates the need to remember and type storage backend, bucket names, and other options for every backup command.

## Configuration Location

Backup configuration is stored in the main awsideman configuration file:
```
~/.awsideman/config.yaml
```

## Configuration Structure

```yaml
backup:
  # Storage configuration
  storage:
    default_backend: "filesystem"    # Options: "filesystem", "s3"
    filesystem:
      path: "~/.awsideman/backups"  # Local backup directory
    s3:
      bucket: "my-backup-bucket"     # S3 bucket name
      prefix: "backups"              # S3 key prefix
      region: "us-east-1"            # S3 region (optional)

  # Encryption settings
  encryption:
    enabled: true                    # Enable backup encryption
    type: "aes256"                  # Encryption type: "none", "aes256"

  # Compression settings
  compression:
    enabled: true                    # Enable backup compression
    type: "gzip"                    # Compression type: "none", "gzip", "lz4", "zstd"

  # Default backup settings
  defaults:
    backup_type: "full"             # Default backup type: "full", "incremental"
    include_inactive_users: false   # Include inactive users by default
    resource_types: "all"           # Default resources to backup

  # Retention policy
  retention:
    keep_daily: 7                   # Keep daily backups for 7 days
    keep_weekly: 4                  # Keep weekly backups for 4 weeks
    keep_monthly: 12                # Keep monthly backups for 12 months
    auto_cleanup: true              # Automatically clean up old backups

  # Performance settings
  performance:
    deduplication_enabled: true     # Enable deduplication to reduce storage
    parallel_processing_enabled: true  # Enable parallel processing
    resource_monitoring_enabled: true  # Enable resource monitoring
    max_workers: 8                  # Maximum number of worker threads
```

## Configuration Commands

### View Configuration

```bash
# Show all backup configuration
awsideman backup config show

# Show in different formats
awsideman backup config show --format yaml
awsideman backup config show --format json
```

### Set Configuration Values

```bash
# Set storage backend
awsideman backup config set storage.default_backend s3

# Set S3 bucket
awsideman backup config set storage.s3.bucket my-backup-bucket

# Set S3 prefix
awsideman backup config set storage.s3.prefix production-backups

# Set default backup type
awsideman backup config set defaults.backup_type incremental

# Set encryption settings
awsideman backup config set encryption.enabled true
awsideman backup config set encryption.type aes256

# Set compression settings
awsideman backup config set compression.enabled true
awsideman backup config set compression.type lz4

# Set performance settings
awsideman backup config set performance.deduplication_enabled true
awsideman backup config set performance.max_workers 16
```

### Get Configuration Values

```bash
# Get specific configuration values
awsideman backup config get storage.default_backend
awsideman backup config get storage.s3.bucket
awsideman backup config get defaults.backup_type
```

### Reset Configuration

```bash
# Reset specific section
awsideman backup config reset --section storage

# Reset all backup configuration to defaults
awsideman backup config reset

# Force reset without confirmation
awsideman backup config reset --force
```

### Validate Configuration

```bash
# Test configuration validity
awsideman backup config test
```

### List Valid Configuration Keys

```bash
# List all valid configuration keys
awsideman backup config list-keys

# List keys for specific section
awsideman backup config list-keys --section storage
```

## Configuration Validation

The backup configuration system includes comprehensive validation to prevent configuration errors:

### Key Validation
- **Valid Key Paths**: Only valid configuration keys are accepted (e.g., `storage.default_backend`)
- **Invalid Keys Rejected**: Invalid keys like `storage.s3_bucket` (should be `storage.s3.bucket`) are rejected
- **Helpful Error Messages**: Clear error messages show valid alternatives

### Value Validation
- **Type Checking**: Values are validated against expected types (string, boolean, integer)
- **Enum Values**: Predefined values are enforced (e.g., `filesystem` or `s3` for storage backend)
- **Range Validation**: Integer values are validated for appropriate ranges
- **Boolean Conversion**: `true`/`false` strings are automatically converted to boolean values

### Examples of Validation

```bash
# ✅ Valid configuration
awsideman backup config set storage.default_backend s3
awsideman backup config set storage.s3.bucket my-bucket
awsideman backup config set encryption.enabled true
awsideman backup config set retention.keep_daily 30

# ❌ Invalid keys (rejected)
awsideman backup config set storage.s3_bucket my-bucket  # Invalid key
awsideman backup config set invalid.section.key value   # Invalid section

# ❌ Invalid values (rejected)
awsideman backup config set storage.default_backend invalid  # Invalid value
awsideman backup config set encryption.enabled invalid       # Invalid boolean
awsideman backup config set retention.keep_daily abc        # Invalid integer

# ❌ Missing values (rejected)
awsideman backup config set storage.s3.bucket              # Missing value
```

## Common Configuration Scenarios

### S3 Storage Configuration

```bash
# Configure S3 as default storage backend
awsideman backup config set storage.default_backend s3

# Set S3 bucket
awsideman backup config set storage.s3.bucket my-company-backups

# Set S3 prefix for organization
awsideman backup config set storage.s3.prefix awsideman/backups

# Set S3 region (optional, uses profile region if not specified)
awsideman backup config set storage.s3.region us-west-2
```

### Production Backup Settings

```bash
# Enable encryption and compression
awsideman backup config set encryption.enabled true
awsideman backup config set compression.enabled true

# Set daily incremental backups
awsideman backup config set defaults.backup_type incremental

# Include inactive users for compliance
awsideman backup config set defaults.include_inactive_users true

# Set retention policy
awsideman backup config set retention.keep_daily 30
awsideman backup config set retention.keep_weekly 12
awsideman backup config set retention.keep_monthly 24
```

### Development Backup Settings

```bash
# Use local filesystem for development
awsideman backup config set storage.default_backend filesystem
awsideman backup config set storage.filesystem.path ./dev-backups

# Disable encryption for faster development (not recommended for production)
awsideman backup config set encryption.enabled false

# Keep fewer backups for development
awsideman backup config set retention.keep_daily 3
awsideman backup config set retention.keep_weekly 2
```

## Using Configuration with Backup Commands

Once configured, you can use simplified backup commands:

### Before Configuration
```bash
# Had to specify everything every time
awsideman backup create --storage s3 --storage-path my-bucket/backups --type full
awsideman backup create --storage s3 --storage-path my-bucket/backups --type incremental --since 2024-01-01
```

### After Configuration
```bash
# Uses configuration defaults
awsideman backup create
awsideman backup create --type incremental --since 2024-01-01

# Override specific settings when needed
awsideman backup create --storage filesystem --storage-path ./temp-backup
```

## Configuration Precedence

Command line options always override configuration defaults:

1. **Command line options** (highest priority)
2. **Configuration file values**
3. **Built-in defaults** (lowest priority)

## Migration from Manual Commands

If you're currently using manual backup commands, you can migrate to configuration-based backups:

1. **Extract common options** from your backup commands
2. **Set configuration defaults** using `awsideman backup config set`
3. **Test configuration** with `awsideman backup config test`
4. **Simplify your backup commands** to use defaults
5. **Override specific settings** only when needed

## Troubleshooting

### Configuration Not Applied

```bash
# Check if configuration is loaded
awsideman backup config show

# Verify configuration file location
awsideman config path

# Reload configuration
awsideman config reload
```

### S3 Configuration Issues

```bash
# Test S3 configuration
awsideman backup config test

# Verify bucket permissions
awsideman backup config get storage.s3.bucket

# Check region configuration
awsideman backup config get storage.s3.region
```

### Validation Errors

```bash
# Run configuration test
awsideman backup config test

# Fix identified issues
awsideman backup config set <key> <value>

# Reset problematic sections
awsideman backup config reset --section <section-name>
```

## Best Practices

1. **Use S3 for production** backups with proper bucket policies
2. **Enable encryption** for all production backups
3. **Set appropriate retention policies** based on compliance requirements
4. **Test configuration** before relying on it for production
5. **Document your configuration** for team members
6. **Use different configurations** for different environments (dev/staging/prod)

## Example Complete Configuration

```yaml
# ~/.awsideman/config.yaml
backup:
  storage:
    default_backend: "s3"
    filesystem:
      path: "~/.awsideman/backups"
    s3:
      bucket: "my-company-backups"
      prefix: "awsideman/production"
      region: "us-east-1"

  encryption:
    enabled: true
    type: "aes256"

  compression:
    enabled: true
    type: "gzip"

  defaults:
    backup_type: "full"
    include_inactive_users: true
    resource_types: "all"

  retention:
    keep_daily: 30
    keep_weekly: 12
    keep_monthly: 24
    auto_cleanup: true
```

With this configuration, you can simply run:
```bash
awsideman backup create
```

And it will automatically use S3 storage, encryption, compression, and all your configured defaults.
