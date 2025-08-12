# awsideman Documentation

This directory contains comprehensive documentation for awsideman's features and capabilities.

## Documentation Index

### Core Features
- **[Multi-Account Operations](MULTI_ACCOUNT_OPERATIONS.md)** - Complete guide to managing permissions across multiple AWS accounts
- **[Bulk Operations](BULK_OPERATIONS.md)** - CSV/JSON-based bulk assignment and revocation operations
- **[Security Implementation](SECURITY.md)** - Security features, encryption, and best practices
- **[Security Best Practices](SECURITY_BEST_PRACTICES.md)** - Enterprise security guidelines and recommendations

### Troubleshooting and Support
- **[Multi-Account Troubleshooting](MULTI_ACCOUNT_TROUBLESHOOTING.md)** - Comprehensive troubleshooting guide for multi-account operations
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** - Configuration through environment variables

## Quick Navigation

### Getting Started
1. [Installation and Setup](../README.md#installation)
2. [Basic Configuration](../CONFIGURATION.md)
3. [Profile Management](../README.md#profile-management)

### Common Use Cases
1. **New Employee Onboarding**
   - [Multi-Account Operations Guide](MULTI_ACCOUNT_OPERATIONS.md#example-1-basic-multi-account-assignment)
   - [Automation Scripts](../examples/multi-account-operations/automation-scripts/)

2. **Employee Offboarding**
   - [Multi-Account Revocation](MULTI_ACCOUNT_OPERATIONS.md#example-3-multi-account-revocation)
   - [Offboarding Script](../examples/multi-account-operations/automation-scripts/offboard-employee.sh)

3. **Bulk Permission Management**
   - [Bulk Operations Guide](BULK_OPERATIONS.md)
   - [CSV/JSON Examples](../examples/bulk-operations/)

4. **Enterprise Workflows**
   - [Enterprise Examples](../examples/multi-account-operations/sample-data/enterprise-accounts.json)
   - [Complex Filtering](../examples/multi-account-operations/README.md#filtering-scenarios)

### Advanced Topics
1. **Performance Optimization**
   - [Multi-Account Performance](MULTI_ACCOUNT_OPERATIONS.md#performance-considerations)
   - [Cache Configuration](../examples/cache-configurations/)

2. **Security and Compliance**
   - [Security Features](SECURITY.md)
   - [Best Practices](SECURITY_BEST_PRACTICES.md)
   - [Compliance Examples](../examples/multi-account-operations/sample-data/enterprise-accounts.json#security_and_compliance)

3. **Automation and Integration**
   - [CI/CD Integration](../examples/multi-account-operations/README.md#cicd-integration)
   - [Automation Scripts](../examples/multi-account-operations/automation-scripts/)

## Feature Matrix

| Feature | Single Account | Multi-Account | Bulk Operations | Notes |
|---------|---------------|---------------|-----------------|-------|
| User Assignment | ✅ | ✅ | ✅ | Full support across all modes |
| Group Assignment | ✅ | ✅ | ✅ | Full support across all modes |
| Permission Set Assignment | ✅ | ✅ | ✅ | Full support across all modes |
| Account Filtering | ❌ | ✅ | ✅ | Wildcard and tag-based filtering |
| Dry-Run Mode | ✅ | ✅ | ✅ | Preview changes before execution |
| Progress Tracking | ✅ | ✅ | ✅ | Real-time progress indicators |
| Error Handling | ✅ | ✅ | ✅ | Comprehensive error reporting |
| Name Resolution | ✅ | ✅ | ✅ | Human-readable names to AWS IDs |
| Batch Processing | ❌ | ✅ | ✅ | Configurable batch sizes |
| Rate Limiting | ✅ | ✅ | ✅ | Automatic throttling and retry |

## Command Reference

### Multi-Account Commands
```bash
# Assignment commands
awsideman assignment assign <permission-set> <principal> --filter <filter>
awsideman assignment revoke <permission-set> <principal> --filter <filter>

# Common options
--dry-run              # Preview without making changes
--batch-size N         # Process N accounts concurrently
--filter "expression"  # Account filter (wildcard or tag-based)
--profile <profile>    # AWS profile to use
```

### Bulk Operation Commands
```bash
# Bulk assignment/revocation
awsideman bulk assign <file>
awsideman bulk revoke <file>

# Common options
--dry-run              # Preview without making changes
--batch-size N         # Process N operations concurrently
--stop-on-error        # Stop processing on first error
--force                # Skip confirmation prompts
```

### Cache Management Commands
```bash
# Cache operations
awsideman cache status
awsideman cache clear
awsideman cache health check
awsideman cache warm --resource-type <type>
```

## Examples by Organization Size

### Small Organization (< 50 accounts)
- [Small Org Examples](../examples/multi-account-operations/sample-data/small-org-accounts.json)
- Recommended batch size: 10-15
- Simple filtering patterns
- Basic automation scripts

### Medium Organization (50-200 accounts)
- [Medium Org Examples](../examples/multi-account-operations/sample-data/medium-org-accounts.json)
- Recommended batch size: 8-12
- Department and environment-based filtering
- Workflow automation

### Large Enterprise (200+ accounts)
- [Enterprise Examples](../examples/multi-account-operations/sample-data/enterprise-accounts.json)
- Recommended batch size: 3-8
- Complex compliance and business unit filtering
- Advanced automation and CI/CD integration

## Best Practices Summary

### Security
- Always use `--dry-run` first
- Use specific filters instead of wildcards
- Implement approval workflows for production
- Regular access reviews and auditing

### Performance
- Choose appropriate batch sizes
- Monitor API rate limits
- Use caching effectively
- Schedule large operations during off-peak hours

### Operations
- Maintain detailed logs
- Implement error handling and retry logic
- Use automation for repetitive tasks
- Document your filtering patterns

### Compliance
- Align with data classification requirements
- Implement segregation of duties
- Maintain audit trails
- Regular compliance reporting

## Support and Community

### Getting Help
1. Check the [troubleshooting guide](MULTI_ACCOUNT_TROUBLESHOOTING.md)
2. Review [common error scenarios](MULTI_ACCOUNT_TROUBLESHOOTING.md#common-error-scenarios)
3. Consult the [examples directory](../examples/)
4. Open an issue on GitHub

### Contributing
1. Review the [development setup](../README.md#development)
2. Run tests before submitting changes
3. Follow the existing code style
4. Update documentation for new features

### Resources
- [GitHub Repository](https://github.com/yourusername/awsideman)
- [Issue Tracker](https://github.com/yourusername/awsideman/issues)
- [AWS Identity Center Documentation](https://docs.aws.amazon.com/singlesignon/)
- [AWS Organizations Documentation](https://docs.aws.amazon.com/organizations/)
