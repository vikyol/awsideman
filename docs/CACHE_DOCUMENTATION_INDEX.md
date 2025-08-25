# Cache System Documentation Index

This document provides an overview and navigation guide for the awsideman cache system documentation.

## Documentation Overview

The awsideman cache system documentation is organized into four main documents, each serving a specific purpose:

### 1. [Cache Architecture Documentation](CACHE_ARCHITECTURE.md)
**Purpose**: Comprehensive architectural overview and design principles

**Contents**:
- System architecture and core components
- Cache manager singleton pattern
- Storage backends (memory and disk)
- AWS client integration
- Error handling and resilience
- Performance characteristics
- Configuration options
- Migration strategy

**Target Audience**: Architects, senior developers, system administrators

### 2. [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md)
**Purpose**: Practical implementation examples and code samples

**Contents**:
- Basic cache manager usage
- AWS client integration patterns
- Command implementation examples
- Advanced usage patterns
- Testing strategies
- Best practices and anti-patterns

**Target Audience**: Developers implementing new commands or features

### 3. [Cache Troubleshooting Guide](CACHE_TROUBLESHOOTING.md)
**Purpose**: Diagnostic procedures and problem resolution

**Contents**:
- Quick diagnostic commands
- Common issues and solutions
- Advanced troubleshooting techniques
- Performance optimization
- Monitoring and alerting
- Recovery procedures

**Target Audience**: Operations teams, support engineers, system administrators

### 4. [Cache Key Patterns and Invalidation Rules](CACHE_KEY_PATTERNS.md)
**Purpose**: Detailed specification of cache key structure and invalidation logic

**Contents**:
- Cache key structure and hierarchy
- Resource-specific key patterns
- Parameter hashing strategies
- Invalidation rules and patterns
- Cross-resource relationships
- Implementation examples

**Target Audience**: Developers, cache system maintainers

## Quick Reference

### For New Developers

**Start Here**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md)
- Learn basic cache manager usage
- See practical implementation examples
- Understand integration patterns

**Then Read**: [Cache Key Patterns](CACHE_KEY_PATTERNS.md)
- Understand key structure
- Learn invalidation rules
- See pattern examples

### For System Administrators

**Start Here**: [Cache Architecture](CACHE_ARCHITECTURE.md)
- Understand system design
- Learn configuration options
- Review performance characteristics

**Then Read**: [Cache Troubleshooting](CACHE_TROUBLESHOOTING.md)
- Learn diagnostic procedures
- Understand monitoring setup
- Review recovery procedures

### For Troubleshooting Issues

**Start Here**: [Cache Troubleshooting Guide](CACHE_TROUBLESHOOTING.md)
- Quick diagnostic commands
- Common issue solutions
- Performance optimization

**Reference**: [Cache Key Patterns](CACHE_KEY_PATTERNS.md)
- Debug key generation issues
- Verify invalidation patterns
- Understand cache relationships

### For Architecture Reviews

**Start Here**: [Cache Architecture](CACHE_ARCHITECTURE.md)
- System design overview
- Component interactions
- Performance characteristics

**Reference**: [Cache Key Patterns](CACHE_KEY_PATTERNS.md)
- Key structure specification
- Invalidation rule definitions
- Cross-resource relationships

## Common Use Cases

### Implementing a New Command

1. **Read**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md) - Basic integration patterns
2. **Reference**: [Cache Key Patterns](CACHE_KEY_PATTERNS.md) - Key structure for your resource type
3. **Test**: Use examples from troubleshooting guide to verify behavior

### Debugging Cache Issues

1. **Start**: [Cache Troubleshooting Guide](CACHE_TROUBLESHOOTING.md) - Diagnostic commands
2. **Debug**: [Cache Key Patterns](CACHE_KEY_PATTERNS.md) - Verify key generation
3. **Understand**: [Cache Architecture](CACHE_ARCHITECTURE.md) - System behavior

### Setting Up Monitoring

1. **Plan**: [Cache Architecture](CACHE_ARCHITECTURE.md) - Performance characteristics
2. **Implement**: [Cache Troubleshooting Guide](CACHE_TROUBLESHOOTING.md) - Monitoring scripts
3. **Optimize**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md) - Performance patterns

### Performance Optimization

1. **Baseline**: [Cache Troubleshooting Guide](CACHE_TROUBLESHOOTING.md) - Performance diagnostics
2. **Optimize**: [Cache Architecture](CACHE_ARCHITECTURE.md) - Configuration tuning
3. **Validate**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md) - Efficient patterns

## Key Concepts Cross-Reference

### Cache Manager Singleton
- **Architecture**: [Cache Architecture](CACHE_ARCHITECTURE.md#cache-manager-singleton)
- **Usage**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md#getting-the-cache-manager-instance)
- **Troubleshooting**: [Cache Troubleshooting](CACHE_TROUBLESHOOTING.md#thread-safety-issues)

### Cache Key Structure
- **Specification**: [Cache Key Patterns](CACHE_KEY_PATTERNS.md#cache-key-structure)
- **Usage**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md#example-2-command-with-manual-cache-key)
- **Debugging**: [Cache Troubleshooting](CACHE_TROUBLESHOOTING.md#debug-cache-key-generation)

### Invalidation Rules
- **Rules**: [Cache Key Patterns](CACHE_KEY_PATTERNS.md#invalidation-rules)
- **Implementation**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md#example-3-write-operation-with-invalidation)
- **Debugging**: [Cache Troubleshooting](CACHE_TROUBLESHOOTING.md#debug-invalidation-patterns)

### Storage Backends
- **Architecture**: [Cache Architecture](CACHE_ARCHITECTURE.md#cache-storage-backends)
- **Configuration**: [Cache Architecture](CACHE_ARCHITECTURE.md#configuration-options)
- **Troubleshooting**: [Cache Troubleshooting](CACHE_TROUBLESHOOTING.md#cache-backend-errors)

### Error Handling
- **Design**: [Cache Architecture](CACHE_ARCHITECTURE.md#error-handling-and-resilience)
- **Implementation**: [Cache Usage Examples](CACHE_USAGE_EXAMPLES.md#example-3-error-handling-with-cache-fallback)
- **Recovery**: [Cache Troubleshooting](CACHE_TROUBLESHOOTING.md#recovery-procedures)

## CLI Commands Reference

### Status and Monitoring
```bash
# Basic cache status
awsideman cache status

# Detailed statistics
awsideman cache status --detailed

# Recent activity
awsideman cache status --recent-entries 20
```

### Cache Management
```bash
# Clear entire cache
awsideman cache clear

# Clear specific patterns
awsideman cache clear --pattern "user:*"

# Test cache functionality
awsideman cache test
```

### Debugging
```bash
# Bypass cache for debugging
awsideman user list --no-cache

# Enable debug logging
awsideman --log-level DEBUG user list

# Check cache health
awsideman cache health
```

## Environment Variables Reference

### Cache Configuration
```bash
# Backend type
export AWSIDEMAN_CACHE_BACKEND=memory  # or 'disk'

# Cache directory (disk backend)
export AWSIDEMAN_CACHE_DIR=/var/cache/awsideman

# Size limits
export AWSIDEMAN_CACHE_MAX_SIZE_MB=100

# TTL settings
export AWSIDEMAN_CACHE_DEFAULT_TTL=900  # seconds

# Emergency disable
export AWSIDEMAN_CACHE_DISABLED=true
```

### Debug Settings
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Cache debug mode
export AWSIDEMAN_CACHE_DEBUG=true

# Circuit breaker settings
export AWSIDEMAN_CACHE_CIRCUIT_BREAKER_THRESHOLD=5
```

## Code Examples Quick Reference

### Basic Cache Operations
```python
from awsideman.cache.manager import CacheManager

cache_manager = CacheManager()
cache_manager.set("key", "value", ttl=timedelta(minutes=15))
data = cache_manager.get("key")
cache_manager.invalidate("pattern:*")
```

### AWS Client Integration
```python
from awsideman.cache.aws_client import CachedAWSClient

cached_client = CachedAWSClient(boto3_client, CacheManager())
result = cached_client.list_users(IdentityStoreId=store_id)
```

### Cache Key Building
```python
from awsideman.cache.key_builder import CacheKeyBuilder

key_builder = CacheKeyBuilder()
key = key_builder.build_key("user", "list", "all")
```

### Invalidation
```python
from awsideman.cache.invalidation import CacheInvalidationEngine

invalidation_engine = CacheInvalidationEngine(CacheManager())
count = invalidation_engine.invalidate_for_operation("update", "user", "user-123")
```

## Related Documentation

### Internal Documentation
- [Project README](../README.md) - General project overview
- [Configuration Guide](../CONFIGURATION.md) - System configuration
- [Developer Guide](../docs/README.md) - Development guidelines

### AWS Documentation
- [AWS Identity Center API Reference](https://docs.aws.amazon.com/singlesignon/latest/APIReference/)
- [AWS SDK for Python (Boto3)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)

### External Resources
- [Python Threading Documentation](https://docs.python.org/3/library/threading.html)
- [Design Patterns: Singleton](https://refactoring.guru/design-patterns/singleton)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)

## Maintenance and Updates

### Documentation Maintenance

This documentation should be updated when:
- Cache system architecture changes
- New cache key patterns are added
- Invalidation rules are modified
- New configuration options are introduced
- Performance characteristics change

### Version History

- **v1.0**: Initial cache refactoring documentation
- **v1.1**: Added troubleshooting procedures
- **v1.2**: Enhanced key pattern specifications
- **v1.3**: Added monitoring and alerting guidance

### Contributing to Documentation

When updating cache documentation:
1. Update the relevant specific document
2. Update this index if new sections are added
3. Update cross-references between documents
4. Test all code examples
5. Verify CLI commands work as documented

This index serves as the central navigation point for all cache-related documentation, ensuring developers and administrators can quickly find the information they need.
