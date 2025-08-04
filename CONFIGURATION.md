# awsideman Configuration Guide

This guide explains how to configure awsideman using the unified YAML configuration system.

## Configuration File Location

awsideman uses a single YAML configuration file located at:
```
~/.awsideman/config.yaml
```


## Configuration Structure

The configuration file has the following main sections:

### 1. Default Profile
```yaml
default_profile: "production"
```

### 2. AWS Profiles
```yaml
profiles:
  production:
    region: "us-east-1"
    sso_instance_arn: "arn:aws:sso:::instance/ssoins-1234567890abcdef"
    sso_display_name: "Production SSO"
  
  development:
    region: "us-west-2"
    sso_instance_arn: "arn:aws:sso:::instance/ssoins-abcdef1234567890"
    sso_display_name: "Development SSO"
```

### 3. Cache Configuration
```yaml
cache:
  # Basic settings
  enabled: true
  default_ttl: 3600
  max_size_mb: 100
  
  # Backend configuration
  backend_type: "file"  # Options: "file", "dynamodb", "hybrid"
  
  # Encryption settings
  encryption_enabled: false
  encryption_type: "aes256"  # Options: "none", "aes256"
  
  # DynamoDB backend settings
  dynamodb_table_name: "awsideman-cache"
  dynamodb_region: "us-east-1"
  dynamodb_profile: "production"
  
  # File backend settings
  file_cache_dir: "~/.awsideman/cache"
  
  # Hybrid backend settings
  hybrid_local_ttl: 300
  
  # Operation-specific TTLs
  operation_ttls:
    list_users: 3600
    list_groups: 3600
    describe_user: 1800
```

## Configuration Management Commands

### View Configuration
```bash
# Show all configuration
awsideman config show

# Show specific section
awsideman config show --section profiles
awsideman config show --section cache

# Show in different formats
awsideman config show --format yaml
awsideman config show --format json
awsideman config show --format table
```

### Validate Configuration
```bash
# Validate current configuration
awsideman config validate
```

### Configuration File Information
```bash
# Show configuration file path and status
awsideman config path
```

## Profile Management

### Add Profile
```bash
# Add a new profile
awsideman profile add production --region us-east-1

# Add and set as default
awsideman profile add production --region us-east-1 --default
```

### List Profiles
```bash
awsideman profile list
```

### Update Profile
```bash
# Update region
awsideman profile update production --region us-west-2

# Set as default
awsideman profile update production --default
```

### Remove Profile
```bash
# Remove profile with confirmation
awsideman profile remove development

# Force remove without confirmation
awsideman profile remove development --force
```

### Set Default Profile
```bash
awsideman profile set-default production
```

## Cache Configuration

### Basic Cache Settings

#### Enable/Disable Cache
```yaml
cache:
  enabled: true  # or false
```

#### Set Default TTL
```yaml
cache:
  default_ttl: 3600  # seconds (1 hour)
```

#### Set Maximum Cache Size
```yaml
cache:
  max_size_mb: 100  # megabytes
```

### Backend Configuration

awsideman supports three cache backend types: file (default), DynamoDB, and hybrid. Each backend has specific configuration options and use cases.

#### File Backend (Default)
The file backend stores cache data as files on the local filesystem. This is the default and simplest option.

```yaml
cache:
  backend_type: "file"
  file_cache_dir: "~/.awsideman/cache"  # optional custom directory
```

**File Backend Options:**
- `file_cache_dir`: Custom directory for cache files (default: `~/.awsideman/cache`)

**Use Cases:**
- Single-user environments
- Development and testing
- When you don't need to share cache across machines
- Offline or air-gapped environments

#### DynamoDB Backend
The DynamoDB backend stores cache data in an AWS DynamoDB table, enabling cache sharing across multiple machines and users.

```yaml
cache:
  backend_type: "dynamodb"
  dynamodb_table_name: "awsideman-cache"
  dynamodb_region: "us-east-1"
  dynamodb_profile: "production"  # optional AWS profile
```

**DynamoDB Backend Options:**
- `dynamodb_table_name`: Name of the DynamoDB table (default: "awsideman-cache")
- `dynamodb_region`: AWS region for the DynamoDB table (default: uses profile's region)
- `dynamodb_profile`: AWS profile to use for DynamoDB operations (default: uses current profile)

**Features:**
- Automatic table creation with proper schema
- TTL-based automatic expiration using DynamoDB TTL
- Support for large cache entries (>400KB) through automatic chunking
- Compression for large entries to reduce storage costs
- Pay-per-request billing mode for cost efficiency

**Use Cases:**
- Team environments where cache should be shared
- Multi-machine setups (CI/CD, multiple workstations)
- When you need centralized cache management
- Production environments requiring high availability

**Prerequisites:**
- AWS credentials configured for DynamoDB access
- IAM permissions for DynamoDB operations (CreateTable, GetItem, PutItem, DeleteItem, DescribeTable)

#### Hybrid Backend
The hybrid backend combines local file caching with DynamoDB remote storage, providing the best of both worlds.

```yaml
cache:
  backend_type: "hybrid"
  hybrid_local_ttl: 300  # local cache TTL in seconds (5 minutes)
  # DynamoDB settings (required for hybrid mode)
  dynamodb_table_name: "awsideman-cache"
  dynamodb_region: "us-east-1"
  dynamodb_profile: "production"
```

**Hybrid Backend Options:**
- `hybrid_local_ttl`: TTL for local cache entries in seconds (default: 300 = 5 minutes)
- All DynamoDB backend options are also required

**How It Works:**
1. Frequently accessed data is cached locally for fast access
2. Less frequently accessed data is stored in DynamoDB
3. Local cache has a shorter TTL to ensure data freshness
4. Automatic promotion/demotion based on access patterns

**Use Cases:**
- Teams that want shared cache but also fast local access
- Environments with variable network connectivity
- When you need both performance and data sharing
- Distributed teams with some offline work

### Encryption Configuration

awsideman supports AES-256 encryption for cache data at rest. Encryption keys are securely stored in the operating system's keyring.

#### Enable Encryption
```yaml
cache:
  encryption_enabled: true
  encryption_type: "aes256"
```

#### Disable Encryption
```yaml
cache:
  encryption_enabled: false
  encryption_type: "none"
```

**Encryption Options:**
- `encryption_enabled`: Enable/disable encryption (default: false)
- `encryption_type`: Encryption algorithm ("none" or "aes256", default: "aes256")

**Security Features:**
- AES-256-CBC encryption with random initialization vectors
- PKCS7 padding for data integrity
- Secure key generation using cryptographically secure random
- OS keyring integration (Keychain on macOS, Credential Manager on Windows, Secret Service on Linux)
- Protection against timing attacks during decryption
- Secure key rotation with automatic re-encryption

**Key Management:**
- Keys are automatically generated on first use
- Keys are stored securely in the OS keyring, never in plain text
- Supports key rotation with `awsideman cache encryption rotate`
- Fallback to file-based key storage if keyring is unavailable
- Keys are never logged or exposed in configuration files

### Operation-Specific TTLs
```yaml
cache:
  operation_ttls:
    list_users: 3600          # 1 hour
    list_groups: 3600         # 1 hour
    list_permission_sets: 7200 # 2 hours
    describe_user: 1800       # 30 minutes
    describe_group: 1800      # 30 minutes
    describe_permission_set: 1800  # 30 minutes
    list_accounts: 7200       # 2 hours
    describe_account: 3600    # 1 hour
    list_account_assignments: 1800  # 30 minutes
```

## Environment Variable Overrides

You can override any configuration setting using environment variables. Environment variables take precedence over configuration file settings.

### Basic Cache Settings
```bash
# Enable/disable cache
export AWSIDEMAN_CACHE_ENABLED=true

# Set default TTL (in seconds)
export AWSIDEMAN_CACHE_TTL_DEFAULT=3600

# Set maximum cache size (in MB)
export AWSIDEMAN_CACHE_MAX_SIZE_MB=100
```

### Backend Settings
```bash
# Set backend type (file, dynamodb, hybrid)
export AWSIDEMAN_CACHE_BACKEND=dynamodb

# DynamoDB backend settings
export AWSIDEMAN_CACHE_DYNAMODB_TABLE=my-cache-table
export AWSIDEMAN_CACHE_DYNAMODB_REGION=us-west-2
export AWSIDEMAN_CACHE_DYNAMODB_PROFILE=production

# File backend settings
export AWSIDEMAN_CACHE_FILE_DIR=/custom/cache/path

# Hybrid backend settings
export AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL=300
```

### Encryption Settings
```bash
# Enable/disable encryption
export AWSIDEMAN_CACHE_ENCRYPTION=true

# Set encryption type (none, aes256)
export AWSIDEMAN_CACHE_ENCRYPTION_TYPE=aes256
```

### Operation-Specific TTLs
You can set custom TTLs for specific AWS operations:

```bash
# User operations
export AWSIDEMAN_CACHE_TTL_LIST_USERS=7200
export AWSIDEMAN_CACHE_TTL_DESCRIBE_USER=900

# Group operations
export AWSIDEMAN_CACHE_TTL_LIST_GROUPS=7200
export AWSIDEMAN_CACHE_TTL_DESCRIBE_GROUP=1800

# Permission set operations
export AWSIDEMAN_CACHE_TTL_LIST_PERMISSION_SETS=7200
export AWSIDEMAN_CACHE_TTL_DESCRIBE_PERMISSION_SET=1800

# Account operations
export AWSIDEMAN_CACHE_TTL_LIST_ACCOUNTS=14400
export AWSIDEMAN_CACHE_TTL_DESCRIBE_ACCOUNT=3600

# Assignment operations
export AWSIDEMAN_CACHE_TTL_LIST_ACCOUNT_ASSIGNMENTS=1800
```

### Environment Variable Naming Convention
Environment variables follow the pattern: `AWSIDEMAN_CACHE_<SETTING_NAME>`

- Configuration file keys are converted to uppercase
- Underscores replace hyphens and dots
- Nested configuration uses underscore separation

Examples:
- `backend_type` → `AWSIDEMAN_CACHE_BACKEND_TYPE` or `AWSIDEMAN_CACHE_BACKEND`
- `dynamodb_table_name` → `AWSIDEMAN_CACHE_DYNAMODB_TABLE`
- `encryption_enabled` → `AWSIDEMAN_CACHE_ENCRYPTION`

## Cache Management Commands

### Basic Cache Operations

#### View Cache Status
```bash
# Show comprehensive cache status
awsideman cache status
```

This command displays:
- Backend type and configuration
- Encryption status and key information
- Number of cached entries and total cache size
- Backend-specific statistics and health status
- Recent cache entries with expiration times

#### Clear Cache
```bash
# Clear all cache entries (with confirmation)
awsideman cache clear

# Force clear without confirmation
awsideman cache clear --force
```

#### Warm Cache
```bash
# Pre-populate cache for better performance
awsideman cache warm "user list"
awsideman cache warm "group list --limit 50"
awsideman cache warm "org tree" --profile production
```

Cache warming executes commands to populate the cache without displaying output, improving performance for subsequent identical commands.

### Advanced Cache Management

#### Backend Health Monitoring
```bash
# Check backend health and connectivity
awsideman cache health check

# Test backend connectivity
awsideman cache health connectivity

# Benchmark backend performance
awsideman cache health benchmark

# Repair backend issues
awsideman cache health repair
```

#### Configuration Management
```bash
# Validate current cache configuration
awsideman cache config validate

# Show current cache configuration
awsideman cache config show

# Test backend configuration
awsideman cache config test
```

### Encryption Management

#### Encryption Status and Control
```bash
# Check encryption status and key information
awsideman cache encryption status

# Enable encryption on existing cache
awsideman cache encryption enable

# Disable encryption (with data conversion)
awsideman cache encryption disable
```

#### Key Management
```bash
# Rotate encryption keys
awsideman cache encryption rotate

# Generate new encryption key
awsideman cache encryption generate-key

# Backup encryption keys
awsideman cache encryption backup

# Restore encryption keys from backup
awsideman cache encryption restore backup-file.key

# Test encryption functionality
awsideman cache encryption test
```

**Key Rotation Process:**
1. Generates a new encryption key
2. Re-encrypts all existing cache data with the new key
3. Securely deletes the old key
4. Updates the keyring with the new key

### DynamoDB Backend Management

#### Table Management
```bash
# Create DynamoDB table manually
awsideman cache dynamodb create-table

# Check table status and configuration
awsideman cache dynamodb table-info

# Delete DynamoDB table (with confirmation)
awsideman cache dynamodb delete-table

# Configure table settings
awsideman cache dynamodb configure
```

#### Data Management
```bash
# List items in DynamoDB table
awsideman cache dynamodb list-items

# Clean up expired items
awsideman cache dynamodb cleanup

# Export cache data from DynamoDB
awsideman cache dynamodb export

# Import cache data to DynamoDB
awsideman cache dynamodb import
```

### Migration and Maintenance

#### Backend Migration
```bash
# Migrate from file to DynamoDB backend
awsideman cache migrate --from file --to dynamodb

# Migrate from DynamoDB to hybrid backend
awsideman cache migrate --from dynamodb --to hybrid

# Migrate with encryption enabled
awsideman cache migrate --from file --to dynamodb --enable-encryption
```

#### Maintenance Operations
```bash
# Compact cache (remove expired entries)
awsideman cache compact

# Rebuild cache index
awsideman cache rebuild

# Verify cache integrity
awsideman cache verify

# Show cache statistics
awsideman cache stats
```

## Example Configurations

### Development Setup (File Backend)
```yaml
default_profile: "dev"

profiles:
  dev:
    region: "us-west-2"
    sso_instance_arn: "arn:aws:sso:::instance/ssoins-dev123456"
    sso_display_name: "Development"

cache:
  enabled: true
  backend_type: "file"
  default_ttl: 1800  # 30 minutes for faster development
  encryption_enabled: false
```

### Production Setup (DynamoDB Backend with Encryption)
```yaml
default_profile: "production"

profiles:
  production:
    region: "us-east-1"
    sso_instance_arn: "arn:aws:sso:::instance/ssoins-prod789012"
    sso_display_name: "Production"
  
  staging:
    region: "us-east-1"
    sso_instance_arn: "arn:aws:sso:::instance/ssoins-stage345678"
    sso_display_name: "Staging"

cache:
  enabled: true
  backend_type: "dynamodb"
  dynamodb_table_name: "awsideman-cache-prod"
  dynamodb_region: "us-east-1"
  dynamodb_profile: "production"
  encryption_enabled: true
  encryption_type: "aes256"
  default_ttl: 3600
  max_size_mb: 500
```

### Multi-Environment Setup (Hybrid Backend)
```yaml
default_profile: "production"

profiles:
  production:
    region: "us-east-1"
    sso_instance_arn: "arn:aws:sso:::instance/ssoins-prod123"
    sso_display_name: "Production"
  
  development:
    region: "us-west-2"
    sso_instance_arn: "arn:aws:sso:::instance/ssoins-dev456"
    sso_display_name: "Development"

cache:
  enabled: true
  backend_type: "hybrid"
  dynamodb_table_name: "awsideman-cache-shared"
  dynamodb_region: "us-east-1"
  hybrid_local_ttl: 300  # 5 minutes local cache
  encryption_enabled: true
  default_ttl: 3600
  operation_ttls:
    list_users: 7200      # Cache users longer
    describe_user: 1800   # Cache user details shorter
```

## Troubleshooting

### Configuration Issues

#### YAML Syntax Errors
```bash
# Validate configuration syntax
awsideman config validate

# Show configuration file location
awsideman config path

# Show current configuration
awsideman config show
```

**Common YAML Issues:**
- Incorrect indentation (use spaces, not tabs)
- Missing colons after keys
- Unquoted strings containing special characters
- Inconsistent data types (mixing strings and numbers)

#### Migration Problems
```bash
# Check migration status
awsideman config path

# Force migration from JSON to YAML
awsideman config migrate --force

# Migrate with backup
awsideman config migrate --backup
```

#### Missing Dependencies
```bash
# Install required Python packages
pip install PyYAML boto3 keyring cryptography

# Check installed packages
pip list | grep -E "(PyYAML|boto3|keyring|cryptography)"
```

### Cache Backend Issues

#### File Backend Problems

**Permission Issues:**
```bash
# Check cache directory permissions
ls -la ~/.awsideman/cache/

# Fix permissions
chmod 755 ~/.awsideman/cache/
chmod 644 ~/.awsideman/cache/*
```

**Disk Space Issues:**
```bash
# Check available disk space
df -h ~/.awsideman/

# Clean up cache if needed
awsideman cache clear --force
```

**Corrupted Cache Files:**
```bash
# Verify cache integrity
awsideman cache verify

# Repair corrupted files
awsideman cache repair

# Clear and rebuild cache
awsideman cache clear --force
```

#### DynamoDB Backend Problems

**Connectivity Issues:**
```bash
# Test DynamoDB connectivity
awsideman cache health connectivity

# Check AWS credentials
aws sts get-caller-identity

# Test DynamoDB access
aws dynamodb list-tables --region us-east-1
```

**Table Creation Issues:**
```bash
# Check table status
awsideman cache dynamodb table-info

# Manually create table
awsideman cache dynamodb create-table

# Check IAM permissions
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:user/myuser \
  --action-names dynamodb:CreateTable dynamodb:GetItem dynamodb:PutItem \
  --resource-arns "arn:aws:dynamodb:us-east-1:123456789012:table/awsideman-cache"
```

**Required IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:UpdateTimeToLive",
        "dynamodb:DescribeTimeToLive"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/awsideman-cache*"
    }
  ]
}
```

**Region and Profile Issues:**
```bash
# Check current AWS profile
aws configure list

# Set specific profile for cache
export AWSIDEMAN_CACHE_DYNAMODB_PROFILE=myprofile

# Set specific region for cache
export AWSIDEMAN_CACHE_DYNAMODB_REGION=us-east-1
```

#### Hybrid Backend Problems

**Local Cache Issues:**
```bash
# Check local cache status
awsideman cache status | grep -A 10 "Local Backend"

# Clear local cache only
rm -rf ~/.awsideman/cache/local/
```

**Synchronization Issues:**
```bash
# Force sync with remote backend
awsideman cache hybrid sync

# Check sync status
awsideman cache hybrid status
```

### Encryption Issues

#### Key Management Problems

**Missing Encryption Key:**
```bash
# Check key status
awsideman cache encryption status

# Generate new key
awsideman cache encryption generate-key

# Test encryption functionality
awsideman cache encryption test
```

**Keyring Unavailable:**
```bash
# Check keyring availability
python -c "import keyring; print(keyring.get_keyring())"

# Install keyring backend (Linux)
sudo apt-get install python3-secretstorage

# Install keyring backend (macOS)
# Keychain is built-in, no additional installation needed

# Install keyring backend (Windows)
# Windows Credential Manager is built-in
```

**Key Corruption:**
```bash
# Backup current key
awsideman cache encryption backup

# Rotate to new key
awsideman cache encryption rotate

# If rotation fails, disable and re-enable encryption
awsideman cache encryption disable
awsideman cache encryption enable
```

#### Decryption Failures

**Corrupted Encrypted Data:**
```bash
# Check for corrupted entries
awsideman cache verify

# Clear corrupted entries
awsideman cache repair

# If all else fails, clear cache and disable encryption
awsideman cache clear --force
awsideman cache encryption disable
```

**Version Compatibility:**
```bash
# Check encryption format version
awsideman cache encryption version

# Migrate old encryption format
awsideman cache encryption migrate
```

### Performance Issues

#### Slow Cache Operations

**File Backend Performance:**
```bash
# Check disk I/O performance
iostat -x 1 5

# Check cache directory for too many files
find ~/.awsideman/cache/ -type f | wc -l

# Compact cache if needed
awsideman cache compact
```

**DynamoDB Performance:**
```bash
# Check DynamoDB metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedReadCapacityUnits \
  --dimensions Name=TableName,Value=awsideman-cache \
  --start-time 2023-01-01T00:00:00Z \
  --end-time 2023-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum

# Benchmark cache performance
awsideman cache health benchmark
```

**Encryption Overhead:**
```bash
# Benchmark encryption performance
awsideman cache encryption benchmark

# Consider disabling encryption for development
export AWSIDEMAN_CACHE_ENCRYPTION=false
```

### Network and Connectivity Issues

#### AWS API Rate Limiting
```bash
# Check for rate limiting errors in logs
awsideman --debug cache status 2>&1 | grep -i "rate\|throttl"

# Increase cache TTL to reduce API calls
export AWSIDEMAN_CACHE_TTL_DEFAULT=7200
```

#### Network Timeouts
```bash
# Test network connectivity to AWS
ping dynamodb.us-east-1.amazonaws.com

# Check for proxy issues
echo $HTTP_PROXY $HTTPS_PROXY

# Configure AWS CLI with longer timeouts
aws configure set max_attempts 10
aws configure set retry_mode adaptive
```

### Common Error Messages

#### "Backend not available"
- Check backend configuration in `~/.awsideman/config.yaml`
- Verify AWS credentials for DynamoDB backend
- Test connectivity with `awsideman cache health connectivity`

#### "Encryption key not found"
- Check keyring availability
- Generate new key with `awsideman cache encryption generate-key`
- Check OS keyring permissions

#### "Table does not exist"
- Create table with `awsideman cache dynamodb create-table`
- Check IAM permissions for table creation
- Verify region and profile configuration

#### "Cache directory not writable"
- Check directory permissions: `ls -la ~/.awsideman/`
- Fix permissions: `chmod 755 ~/.awsideman/cache/`
- Check disk space: `df -h ~/.awsideman/`

#### "Invalid configuration"
- Validate configuration: `awsideman config validate`
- Check YAML syntax
- Verify all required fields are present

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
# Enable debug mode
export AWSIDEMAN_DEBUG=true

# Run commands with debug output
awsideman --debug cache status

# Check log files
tail -f ~/.awsideman/logs/awsideman.log
```

### Getting Help

If you continue to experience issues:

1. Check the GitHub issues: https://github.com/your-repo/awsideman/issues
2. Run `awsideman cache status` and include the output
3. Include your configuration (with sensitive data removed)
4. Provide debug logs when reporting issues

## Additional Documentation

- **[Environment Variables Reference](docs/ENVIRONMENT_VARIABLES.md)** - Comprehensive guide to all environment variables
- **[Configuration Examples](examples/cache-configurations/)** - Ready-to-use configuration files for different scenarios
- **[Example Configurations README](examples/cache-configurations/README.md)** - Detailed guide to configuration examples

## Best Practices

1. **Use version control** for your configuration file (excluding sensitive data)
2. **Set appropriate TTLs** based on how frequently your data changes
3. **Enable encryption** for production environments
4. **Use DynamoDB backend** for shared team environments
5. **Regular backup** of encryption keys
6. **Monitor cache performance** with health checks
7. **Validate configuration** after changes

## Security Considerations

1. **Encryption keys** are stored in the OS keyring (Keychain on macOS, Credential Manager on Windows)
2. **Configuration file** may contain AWS profile names and regions (not credentials)
3. **DynamoDB tables** should use appropriate IAM policies
4. **Backup files** should be stored securely
5. **Environment variables** take precedence over file configuration