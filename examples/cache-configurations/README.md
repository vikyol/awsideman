# Cache Configuration Examples

This directory contains example configuration files for different awsideman deployment scenarios. Each configuration is optimized for specific use cases and environments.

## Available Examples

### 1. Development Environment (`development.yaml`)
**Use Case:** Local development and testing
- **Backend:** File-based cache
- **Encryption:** Disabled (for performance)
- **TTL:** Short (30 minutes default) for rapid iteration
- **Cache Size:** Small (50 MB)

**Best For:**
- Individual developers
- Local testing
- Rapid development cycles
- Environments where security is less critical

### 2. Production Environment (`production.yaml`)
**Use Case:** Enterprise production deployments
- **Backend:** DynamoDB for scalability and reliability
- **Encryption:** Enabled with AES-256
- **TTL:** Balanced (1 hour default) for performance and freshness
- **Cache Size:** Large (500 MB)

**Best For:**
- Production workloads
- Enterprise environments
- Teams requiring shared cache
- High-availability requirements

### 3. Team Hybrid Environment (`team-hybrid.yaml`)
**Use Case:** Team collaboration with local performance
- **Backend:** Hybrid (local + DynamoDB)
- **Encryption:** Enabled for security
- **TTL:** Optimized for team workflows
- **Local Cache:** 5 minutes for frequently accessed data

**Best For:**
- Development teams
- Mixed online/offline work
- Performance-sensitive operations
- Collaborative environments

### 4. CI/CD Environment (`ci-cd.yaml`)
**Use Case:** Automated build and deployment pipelines
- **Backend:** DynamoDB for consistency across builds
- **Encryption:** Enabled for security
- **TTL:** Longer (2 hours default) for build efficiency
- **Cache Size:** Large (1 GB) for complex pipelines

**Best For:**
- Continuous integration
- Automated deployments
- Build pipelines
- Consistent environments

### 5. Multi-Region Environment (`multi-region.yaml`)
**Use Case:** Global teams working across AWS regions
- **Backend:** Hybrid with central DynamoDB
- **Encryption:** Enabled for global security
- **TTL:** Optimized for regional differences
- **Central Cache:** US East 1 for global access

**Best For:**
- Global teams
- Multi-region deployments
- Distributed organizations
- Cross-region consistency needs

### 6. High Security Environment (`high-security.yaml`)
**Use Case:** Maximum security for sensitive environments
- **Backend:** File-based (air-gapped compatible)
- **Encryption:** Maximum security settings
- **TTL:** Very short (15 minutes default) to minimize exposure
- **Cache Size:** Minimal (50 MB)

**Best For:**
- Government environments
- Highly regulated industries
- Air-gapped networks
- Maximum security requirements

## How to Use These Examples

### 1. Copy and Customize
```bash
# Copy an example to your config location
cp examples/cache-configurations/production.yaml ~/.awsideman/config.yaml

# Edit to match your environment
nano ~/.awsideman/config.yaml
```

### 2. Environment-Specific Deployment
```bash
# Use different configs for different environments
cp examples/cache-configurations/development.yaml ~/.awsideman/config-dev.yaml
cp examples/cache-configurations/production.yaml ~/.awsideman/config-prod.yaml

# Switch between environments
export AWSIDEMAN_CONFIG_FILE=~/.awsideman/config-prod.yaml
```

### 3. Validation and Testing
```bash
# Validate your configuration
awsideman config validate

# Test cache functionality
awsideman cache status
awsideman cache health check
```

## Configuration Customization Guide

### Backend Selection

**Choose File Backend When:**
- Single user environment
- No need for shared cache
- Offline or air-gapped environment
- Simple setup requirements

**Choose DynamoDB Backend When:**
- Multiple users need shared cache
- High availability requirements
- Scalability is important
- Team collaboration needed

**Choose Hybrid Backend When:**
- Need both local performance and shared cache
- Variable network connectivity
- Want to optimize for frequently accessed data
- Mixed online/offline usage patterns

### TTL Optimization

**Short TTLs (5-15 minutes):**
- Security-sensitive environments
- Rapidly changing data
- Development environments

**Medium TTLs (30 minutes - 2 hours):**
- Balanced performance and freshness
- Most production environments
- Team collaboration

**Long TTLs (4+ hours):**
- Stable data (accounts, permission sets)
- CI/CD environments
- Performance-critical applications

### Encryption Considerations

**Enable Encryption When:**
- Production environments
- Sensitive data
- Compliance requirements
- Shared or remote backends

**Disable Encryption When:**
- Development environments
- Performance is critical
- Local-only usage
- Non-sensitive data

### Cache Size Guidelines

**Small (50-100 MB):**
- Development environments
- Security-sensitive environments
- Limited storage

**Medium (200-500 MB):**
- Team environments
- Balanced usage
- Most production environments

**Large (1+ GB):**
- CI/CD environments
- Heavy usage patterns
- Large organizations

## Environment Variables Override

All configuration options can be overridden with environment variables:

```bash
# Backend configuration
export AWSIDEMAN_CACHE_BACKEND=dynamodb
export AWSIDEMAN_CACHE_DYNAMODB_TABLE=my-custom-table

# Encryption settings
export AWSIDEMAN_CACHE_ENCRYPTION=true

# TTL settings
export AWSIDEMAN_CACHE_TTL_DEFAULT=7200
export AWSIDEMAN_CACHE_TTL_LIST_USERS=3600
```

## Migration Between Configurations

### From File to DynamoDB
```bash
# Backup current cache
awsideman cache backup

# Update configuration
cp examples/cache-configurations/production.yaml ~/.awsideman/config.yaml

# Migrate data
awsideman cache migrate --from file --to dynamodb
```

### From DynamoDB to Hybrid
```bash
# Update configuration
cp examples/cache-configurations/team-hybrid.yaml ~/.awsideman/config.yaml

# Test new configuration
awsideman cache status
awsideman cache health check
```

## Security Best Practices

1. **Always enable encryption in production**
2. **Use appropriate TTLs for your security requirements**
3. **Regularly rotate encryption keys**
4. **Monitor cache access and usage**
5. **Use environment variables for sensitive settings**
6. **Implement proper IAM policies for DynamoDB access**
7. **Regular security audits of cache configuration**

## Performance Optimization

1. **Choose appropriate backend for your use case**
2. **Optimize TTLs based on data change frequency**
3. **Use hybrid backend for mixed access patterns**
4. **Monitor cache hit rates and adjust accordingly**
5. **Consider regional placement for DynamoDB tables**
6. **Regular cache maintenance and cleanup**

## Troubleshooting

If you encounter issues with these configurations:

1. **Validate configuration syntax:**
   ```bash
   awsideman config validate
   ```

2. **Check backend connectivity:**
   ```bash
   awsideman cache health connectivity
   ```

3. **Verify permissions (for DynamoDB):**
   ```bash
   aws sts get-caller-identity
   aws dynamodb list-tables
   ```

4. **Test encryption (if enabled):**
   ```bash
   awsideman cache encryption status
   awsideman cache encryption test
   ```

5. **Enable debug mode for detailed logs:**
   ```bash
   export AWSIDEMAN_DEBUG=true
   awsideman cache status
   ```

For more detailed troubleshooting, see the main [CONFIGURATION.md](../../CONFIGURATION.md) file.

## Additional Resources

- [Environment Variables Reference](../../docs/ENVIRONMENT_VARIABLES.md) - Comprehensive guide to all environment variables
- [Main Configuration Guide](../../CONFIGURATION.md) - Complete configuration documentation
- [Troubleshooting Guide](../../CONFIGURATION.md#troubleshooting) - Detailed troubleshooting steps