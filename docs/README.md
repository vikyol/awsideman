# awsideman Documentation

This directory contains user-focused documentation for awsideman's features and capabilities.

## Documentation Index

### Core Features
- **[Backup & Restore System](backup-restore/README.md)** - Comprehensive backup and restore for AWS Identity Center
- **[Enhanced Progress Reporting](enhanced-progress-reporting/README.md)** - Advanced progress reporting and monitoring features
- **[Security Implementation](SECURITY.md)** - Security features, encryption, and best practices
- **[Security Best Practices](SECURITY_BEST_PRACTICES.md)** - Enterprise security guidelines and recommendations

### Configuration and Reference
- **[Environment Variables](ENVIRONMENT_VARIABLES.md)** - Configuration through environment variables
- **[Template Format](template-format.md)** - YAML template format specification and examples
- **[Template Troubleshooting](template-troubleshooting.md)** - Common template issues and solutions
- **[Release Notes](releases/README.md)** - Detailed release notes for all versions

## Quick Navigation

### Getting Started
1. [Installation and Setup](../README.md#installation)
2. [Basic Configuration](../CONFIGURATION.md)
3. [Profile Management](../README.md#profile-management)

### Common Use Cases
1. **Backup and Restore**
   - [Backup & Restore System](backup-restore/README.md)
   - [Getting Started Guide](backup-restore/getting-started.md)
   - [CLI Reference](backup-restore/cli-reference.md)

2. **Template Management**
   - [Template Format Guide](template-format.md)
   - [Template Examples](backup-restore/examples/configuration-templates.md)
   - [Template Troubleshooting](template-troubleshooting.md)

3. **Security and Compliance**
   - [Security Features](SECURITY.md)
   - [Security Best Practices](SECURITY_BEST_PRACTICES.md)
   - [Environment Variables](ENVIRONMENT_VARIABLES.md)

### Advanced Topics
1. **Progress Reporting**
   - [Enhanced Progress Reporting](enhanced-progress-reporting/README.md)
   - [Monitoring and Analytics](enhanced-progress-reporting/README.md)

2. **Configuration Management**
   - [Environment Variables](ENVIRONMENT_VARIABLES.md)
   - [Template System](template-format.md)
   - [Configuration Examples](../examples/cache-configurations/)

3. **Backup and Restore**
   - [Advanced Backup Features](backup-restore/README.md)
   - [Automation Scripts](backup-restore/examples/automation-scripts.md)
   - [Configuration Templates](backup-restore/examples/configuration-templates.md)

## Quick Reference

### Backup and Restore Commands
```bash
# Create backup
awsideman backup create --type full

# List backups
awsideman backup list

# Restore from backup
awsideman restore <backup-id>

# Schedule backups
awsideman backup schedule --cron "0 2 * * *"
```

### Template Commands
```bash
# Validate template
awsideman templates validate template.yaml

# Execute template
awsideman templates execute template.yaml
```

## Getting Help

For detailed command reference and examples, see:
- [Backup & Restore CLI Reference](backup-restore/cli-reference.md)
- [Template Format Guide](template-format.md)
- [Environment Variables Reference](ENVIRONMENT_VARIABLES.md)

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
1. Check the [template troubleshooting guide](template-troubleshooting.md)
2. Review [environment variables](ENVIRONMENT_VARIABLES.md)
3. Consult [security best practices](SECURITY_BEST_PRACTICES.md)
4. Open an issue on GitHub

### Contributing
1. Review the [development setup](../README.md#development)
2. Run tests before submitting changes
3. Follow the existing code style
4. Update documentation for new features

### Resources
- [GitHub Repository](https://github.com/vikyol/awsideman)
- [Issue Tracker](https://github.com/vikyol/awsideman/issues)
- [AWS Identity Center Documentation](https://docs.aws.amazon.com/singlesignon/)
- [AWS Organizations Documentation](https://docs.aws.amazon.com/organizations/)
