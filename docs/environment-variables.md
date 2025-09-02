# Environment Variables Reference

This document provides a comprehensive reference for all environment variables supported by awsideman's advanced cache features.

## Overview

Environment variables provide a way to override configuration file settings and are particularly useful for:
- CI/CD environments
- Docker containers
- Temporary configuration changes
- Sensitive settings that shouldn't be in config files
- Environment-specific overrides

Environment variables take precedence over configuration file settings.

## Basic Cache Settings

### Cache Enable/Disable
```bash
# Enable or disable cache entirely
export AWSIDEMAN_CACHE_ENABLED=true          # Default: true
export AWSIDEMAN_CACHE_ENABLED=false
```

### Default TTL
```bash
# Set default TTL for all cache entries (in seconds)
export AWSIDEMAN_CACHE_TTL_DEFAULT=3600      # Default: 3600 (1 hour)
export AWSIDEMAN_CACHE_TTL_DEFAULT=7200      # 2 hours
export AWSIDEMAN_CACHE_TTL_DEFAULT=1800      # 30 minutes
```

### Cache Size Limits
```bash
# Set maximum cache size in megabytes
export AWSIDEMAN_CACHE_MAX_SIZE_MB=100       # Default: 100 MB
export AWSIDEMAN_CACHE_MAX_SIZE_MB=500       # 500 MB for larger environments
export AWSIDEMAN_CACHE_MAX_SIZE_MB=50        # 50 MB for constrained environments
```

## Backend Configuration

### Backend Type Selection
```bash
# Choose cache backend type
export AWSIDEMAN_CACHE_BACKEND=file          # Default: file
export AWSIDEMAN_CACHE_BACKEND=dynamodb      # DynamoDB backend
export AWSIDEMAN_CACHE_BACKEND=hybrid        # Hybrid backend

# Alternative naming (for compatibility)
export AWSIDEMAN_CACHE_BACKEND_TYPE=dynamodb
```

### File Backend Settings
```bash
# Custom cache directory for file backend
export AWSIDEMAN_CACHE_FILE_DIR=/custom/cache/path
export AWSIDEMAN_CACHE_FILE_DIR=/tmp/awsideman-cache
export AWSIDEMAN_CACHE_FILE_DIR=$HOME/.cache/awsideman

# Alternative naming
export AWSIDEMAN_CACHE_FILE_CACHE_DIR=/custom/path
```

### DynamoDB Backend Settings
```bash
# DynamoDB table name
export AWSIDEMAN_CACHE_DYNAMODB_TABLE=awsideman-cache        # Default
export AWSIDEMAN_CACHE_DYNAMODB_TABLE=my-custom-cache-table
export AWSIDEMAN_CACHE_DYNAMODB_TABLE=team-cache-prod

# Alternative naming
export AWSIDEMAN_CACHE_DYNAMODB_TABLE_NAME=awsideman-cache

# DynamoDB region
export AWSIDEMAN_CACHE_DYNAMODB_REGION=us-east-1
export AWSIDEMAN_CACHE_DYNAMODB_REGION=us-west-2
export AWSIDEMAN_CACHE_DYNAMODB_REGION=eu-west-1

# AWS profile for DynamoDB operations
export AWSIDEMAN_CACHE_DYNAMODB_PROFILE=production
export AWSIDEMAN_CACHE_DYNAMODB_PROFILE=development
export AWSIDEMAN_CACHE_DYNAMODB_PROFILE=team
```

### Hybrid Backend Settings
```bash
# Local cache TTL for hybrid backend (in seconds)
export AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL=300     # Default: 300 (5 minutes)
export AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL=600     # 10 minutes
export AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL=120     # 2 minutes

# Note: Hybrid backend also requires DynamoDB settings above
```

## Encryption Configuration

### Encryption Enable/Disable
```bash
# Enable or disable encryption
export AWSIDEMAN_CACHE_ENCRYPTION=true          # Enable encryption
export AWSIDEMAN_CACHE_ENCRYPTION=false         # Disable encryption (default)

# Alternative naming
export AWSIDEMAN_CACHE_ENCRYPTION_ENABLED=true
```

### Encryption Type
```bash
# Set encryption algorithm
export AWSIDEMAN_CACHE_ENCRYPTION_TYPE=aes256   # Default when encryption enabled
export AWSIDEMAN_CACHE_ENCRYPTION_TYPE=none     # Disable encryption
```

## Operation-Specific TTLs

You can set custom TTLs for specific AWS operations using the pattern:
`AWSIDEMAN_CACHE_TTL_<OPERATION_NAME>`

### User Operations
```bash
# User listing operations
export AWSIDEMAN_CACHE_TTL_LIST_USERS=7200              # 2 hours
export AWSIDEMAN_CACHE_TTL_DESCRIBE_USER=1800           # 30 minutes
export AWSIDEMAN_CACHE_TTL_GET_USER=1800                # 30 minutes
export AWSIDEMAN_CACHE_TTL_LIST_USER_GROUPS=3600        # 1 hour
```

### Group Operations
```bash
# Group listing operations
export AWSIDEMAN_CACHE_TTL_LIST_GROUPS=7200             # 2 hours
export AWSIDEMAN_CACHE_TTL_DESCRIBE_GROUP=1800          # 30 minutes
export AWSIDEMAN_CACHE_TTL_GET_GROUP=1800               # 30 minutes
export AWSIDEMAN_CACHE_TTL_LIST_GROUP_MEMBERS=3600      # 1 hour
export AWSIDEMAN_CACHE_TTL_LIST_GROUP_MEMBERSHIPS=3600  # 1 hour
```

### Permission Set Operations
```bash
# Permission set operations
export AWSIDEMAN_CACHE_TTL_LIST_PERMISSION_SETS=14400           # 4 hours
export AWSIDEMAN_CACHE_TTL_DESCRIBE_PERMISSION_SET=7200         # 2 hours
export AWSIDEMAN_CACHE_TTL_GET_PERMISSION_SET=7200              # 2 hours
export AWSIDEMAN_CACHE_TTL_LIST_MANAGED_POLICIES_IN_PERMISSION_SET=7200  # 2 hours
export AWSIDEMAN_CACHE_TTL_GET_INLINE_POLICY_FOR_PERMISSION_SET=7200     # 2 hours
```

### Account Operations
```bash
# Account operations (typically stable data)
export AWSIDEMAN_CACHE_TTL_LIST_ACCOUNTS=28800          # 8 hours
export AWSIDEMAN_CACHE_TTL_DESCRIBE_ACCOUNT=14400       # 4 hours
export AWSIDEMAN_CACHE_TTL_LIST_ROOTS=86400             # 24 hours
export AWSIDEMAN_CACHE_TTL_LIST_ORGANIZATIONAL_UNITS=43200  # 12 hours
```

### Assignment Operations
```bash
# Assignment operations (frequently changing)
export AWSIDEMAN_CACHE_TTL_LIST_ACCOUNT_ASSIGNMENTS=1800        # 30 minutes
export AWSIDEMAN_CACHE_TTL_LIST_ACCOUNT_ASSIGNMENTS_FOR_PRINCIPAL=1800  # 30 minutes
export AWSIDEMAN_CACHE_TTL_LIST_PERMISSION_SETS_PROVISIONED_TO_ACCOUNT=3600  # 1 hour
```

### SSO Operations
```bash
# SSO instance operations
export AWSIDEMAN_CACHE_TTL_LIST_INSTANCES=86400         # 24 hours (very stable)
export AWSIDEMAN_CACHE_TTL_DESCRIBE_INSTANCE=43200      # 12 hours
```

## Advanced Configuration

### Debug and Logging
```bash
# Enable debug mode for cache operations
export AWSIDEMAN_DEBUG=true
export AWSIDEMAN_CACHE_DEBUG=true

# Set log level specifically for cache
export AWSIDEMAN_CACHE_LOG_LEVEL=DEBUG
export AWSIDEMAN_CACHE_LOG_LEVEL=INFO
export AWSIDEMAN_CACHE_LOG_LEVEL=WARNING
```

### Performance Tuning
```bash
# Connection timeout for DynamoDB (in seconds)
export AWSIDEMAN_CACHE_DYNAMODB_TIMEOUT=30

# Maximum retry attempts for DynamoDB operations
export AWSIDEMAN_CACHE_DYNAMODB_MAX_RETRIES=3

# Enable/disable compression for large cache entries
export AWSIDEMAN_CACHE_COMPRESSION=true

# Compression threshold (bytes)
export AWSIDEMAN_CACHE_COMPRESSION_THRESHOLD=1024
```

### Security Settings
```bash
# Key rotation interval (in days)
export AWSIDEMAN_CACHE_KEY_ROTATION_DAYS=90

# Enable audit logging for cache operations
export AWSIDEMAN_CACHE_AUDIT_LOG=true

# Secure memory handling for encryption keys
export AWSIDEMAN_CACHE_SECURE_MEMORY=true
```

## Environment-Specific Examples

### Development Environment
```bash
#!/bin/bash
# Development environment settings
export AWSIDEMAN_CACHE_ENABLED=true
export AWSIDEMAN_CACHE_BACKEND=file
export AWSIDEMAN_CACHE_TTL_DEFAULT=1800
export AWSIDEMAN_CACHE_MAX_SIZE_MB=50
export AWSIDEMAN_CACHE_ENCRYPTION=false
export AWSIDEMAN_DEBUG=true
```

### Production Environment
```bash
#!/bin/bash
# Production environment settings
export AWSIDEMAN_CACHE_ENABLED=true
export AWSIDEMAN_CACHE_BACKEND=dynamodb
export AWSIDEMAN_CACHE_DYNAMODB_TABLE=awsideman-cache-prod
export AWSIDEMAN_CACHE_DYNAMODB_REGION=us-east-1
export AWSIDEMAN_CACHE_DYNAMODB_PROFILE=production
export AWSIDEMAN_CACHE_TTL_DEFAULT=3600
export AWSIDEMAN_CACHE_MAX_SIZE_MB=500
export AWSIDEMAN_CACHE_ENCRYPTION=true
export AWSIDEMAN_CACHE_AUDIT_LOG=true
```

### CI/CD Environment
```bash
#!/bin/bash
# CI/CD environment settings
export AWSIDEMAN_CACHE_ENABLED=true
export AWSIDEMAN_CACHE_BACKEND=dynamodb
export AWSIDEMAN_CACHE_DYNAMODB_TABLE=awsideman-cache-cicd
export AWSIDEMAN_CACHE_DYNAMODB_REGION=us-east-1
export AWSIDEMAN_CACHE_TTL_DEFAULT=7200
export AWSIDEMAN_CACHE_MAX_SIZE_MB=1000
export AWSIDEMAN_CACHE_ENCRYPTION=true

# Longer TTLs for stable CI/CD data
export AWSIDEMAN_CACHE_TTL_LIST_ACCOUNTS=86400
export AWSIDEMAN_CACHE_TTL_LIST_PERMISSION_SETS=28800
export AWSIDEMAN_CACHE_TTL_LIST_USERS=14400
```

### High Security Environment
```bash
#!/bin/bash
# High security environment settings
export AWSIDEMAN_CACHE_ENABLED=true
export AWSIDEMAN_CACHE_BACKEND=file
export AWSIDEMAN_CACHE_FILE_DIR=/secure/cache/awsideman
export AWSIDEMAN_CACHE_TTL_DEFAULT=900
export AWSIDEMAN_CACHE_MAX_SIZE_MB=50
export AWSIDEMAN_CACHE_ENCRYPTION=true
export AWSIDEMAN_CACHE_SECURE_MEMORY=true
export AWSIDEMAN_CACHE_AUDIT_LOG=true

# Very short TTLs for security
export AWSIDEMAN_CACHE_TTL_LIST_USERS=600
export AWSIDEMAN_CACHE_TTL_DESCRIBE_USER=300
export AWSIDEMAN_CACHE_TTL_LIST_ACCOUNT_ASSIGNMENTS=300
```

## Docker and Container Environments

### Docker Compose Example
```yaml
version: '3.8'
services:
  awsideman:
    image: awsideman:latest
    environment:
      - AWSIDEMAN_CACHE_ENABLED=true
      - AWSIDEMAN_CACHE_BACKEND=dynamodb
      - AWSIDEMAN_CACHE_DYNAMODB_TABLE=awsideman-cache-docker
      - AWSIDEMAN_CACHE_DYNAMODB_REGION=us-east-1
      - AWSIDEMAN_CACHE_ENCRYPTION=true
      - AWSIDEMAN_CACHE_TTL_DEFAULT=3600
```

### Kubernetes ConfigMap Example
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: awsideman-cache-config
data:
  AWSIDEMAN_CACHE_ENABLED: "true"
  AWSIDEMAN_CACHE_BACKEND: "dynamodb"
  AWSIDEMAN_CACHE_DYNAMODB_TABLE: "awsideman-cache-k8s"
  AWSIDEMAN_CACHE_DYNAMODB_REGION: "us-east-1"
  AWSIDEMAN_CACHE_ENCRYPTION: "true"
  AWSIDEMAN_CACHE_TTL_DEFAULT: "3600"
```

## Validation and Testing

### Validate Environment Variables
```bash
# Check current environment variable settings
env | grep AWSIDEMAN_CACHE | sort

# Test configuration with environment variables
awsideman config show

# Validate the resulting configuration
awsideman config validate
```

### Test Cache Functionality
```bash
# Test cache with current environment settings
awsideman cache status
awsideman cache health check

# Test specific backend connectivity
awsideman cache health connectivity
```

## Troubleshooting Environment Variables

### Common Issues

1. **Variable Not Taking Effect**
   ```bash
   # Check if variable is set
   echo $AWSIDEMAN_CACHE_BACKEND

   # Check all cache-related variables
   env | grep AWSIDEMAN_CACHE
   ```

2. **Invalid Values**
   ```bash
   # Validate configuration
   awsideman config validate

   # Check specific setting
   awsideman config show --section cache
   ```

3. **Type Conversion Issues**
   ```bash
   # Boolean values: use "true" or "false" (case-insensitive)
   export AWSIDEMAN_CACHE_ENABLED=true

   # Integer values: use numeric strings
   export AWSIDEMAN_CACHE_TTL_DEFAULT=3600
   ```

### Debug Environment Variable Loading
```bash
# Enable debug mode to see configuration loading
export AWSIDEMAN_DEBUG=true
awsideman config show

# Check configuration precedence
awsideman config show --format json | jq '.cache'
```

## Security Considerations

1. **Sensitive Variables**: Use secure methods to set sensitive environment variables
2. **Container Security**: Be careful with environment variables in container logs
3. **CI/CD Security**: Use secure variable storage in CI/CD systems
4. **Audit Trail**: Monitor environment variable changes in production
5. **Least Privilege**: Only set necessary environment variables

## Best Practices

1. **Use Consistent Naming**: Follow the `AWSIDEMAN_CACHE_*` pattern
2. **Document Variables**: Document custom environment variables in your deployment
3. **Validate Settings**: Always validate configuration after setting environment variables
4. **Environment Separation**: Use different variables for different environments
5. **Version Control**: Don't commit sensitive environment variables to version control
6. **Testing**: Test environment variable configurations in non-production first
