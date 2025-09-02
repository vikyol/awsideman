# AWS Identity Center Backup & Restore System

This directory contains comprehensive documentation for awsideman's backup and restore capabilities for AWS Identity Center.

## Overview

The backup and restore system provides enterprise-grade data protection for AWS Identity Center resources including:
- Users and groups
- Permission sets and assignments
- Account access configurations
- Cross-account relationships
- Security policies and compliance settings

## Quick Start

### Basic Backup
```bash
# Create a full backup
awsideman backup create --type full

# Create an incremental backup
awsideman backup create --type incremental --since 2024-01-01

# List existing backups
awsideman backup list

# Validate backup integrity
awsideman backup validate <backup-id>
```

### Basic Restore
```bash
# Preview restore changes
awsideman restore preview <backup-id>

# Restore with conflict resolution
awsideman restore restore <backup-id> --strategy overwrite

# Validate restore compatibility
awsideman restore validate <backup-id>
```

## Documentation Index

### User Guides
- **[Getting Started](getting-started.md)** - Quick setup and first backup
- **[Backup Operations](backup-operations.md)** - Complete guide to backup creation and management
- **[Restore Operations](restore-operations.md)** - Step-by-step restore procedures
- **[Scheduling and Automation](scheduling.md)** - Automated backup workflows
- **[Performance Optimization](performance.md)** - Tuning backup/restore performance

### Reference Documentation
- **[CLI Reference](cli-reference.md)** - Complete command reference
- **[API Reference](api-reference.md)** - Developer API documentation
- **[Configuration Reference](configuration.md)** - Configuration options and examples
- **[Storage Backends](storage-backends.md)** - Supported storage options

### Advanced Topics
- **[Cross-Account Operations](cross-account.md)** - Multi-account backup/restore
- **[Security and Encryption](security.md)** - Security features and best practices
- **[Monitoring and Alerting](monitoring.md)** - Operational monitoring
- **[Troubleshooting](troubleshooting.md)** - Common issues and solutions

### Examples
- **[Basic Examples](examples/basic-examples.md)** - Common backup/restore scenarios
- **[Enterprise Examples](examples/enterprise-examples.md)** - Complex organizational workflows
- **[Automation Scripts](examples/automation-scripts.md)** - CI/CD and automation examples
- **[Configuration Templates](examples/configuration-templates.md)** - Ready-to-use configs

## Key Features

| Feature | Description | Use Case |
|---------|-------------|----------|
| **Full & Incremental Backups** | Complete or delta-based backups | Regular maintenance vs. quick recovery |
| **Cross-Account Support** | Backup/restore across AWS accounts | Multi-account organizations |
| **Encryption** | AES-256 encryption at rest and in transit | Compliance and security requirements |
| **Compression & Deduplication** | Storage optimization and efficiency | Cost reduction and performance |
| **Parallel Processing** | Multi-threaded operations | Large-scale backup/restore |
| **Scheduling** | Automated backup workflows | Operational continuity |
| **Conflict Resolution** | Smart restore strategies | Safe production restores |
| **Audit Logging** | Complete operation tracking | Compliance and troubleshooting |

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CLI Commands  │    │  Backup Manager  │    │ Storage Engine  │
│                 │◄──►│                  │◄──►│                 │
│  • backup       │    │  • Orchestration │    │  • Local FS     │
│  • restore      │    │  • Validation    │    │  • S3           │
│  • schedule     │    │  • Optimization  │    │  • Encryption   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Data Collectors │    │ Performance      │    │ Export/Import   │
│                 │    │ Optimizers       │    │                 │
│  • Users        │    │  • Compression   │    │  • JSON         │
│  • Groups       │    │  • Deduplication │    │  • YAML         │
│  • Permissions  │    │  • Parallel      │    │  • CSV          │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Getting Help

### Common Issues
- [Backup failures](troubleshooting.md#backup-failures)
- [Restore conflicts](troubleshooting.md#restore-conflicts)
- [Performance issues](troubleshooting.md#performance-issues)
- [Storage errors](troubleshooting.md#storage-errors)

### Support Resources
- [Troubleshooting Guide](troubleshooting.md)
- [Configuration Examples](examples/configuration-templates.md)
- [GitHub Issues](https://github.com/vikyol/awsideman/issues)
- [AWS Identity Center Docs](https://docs.aws.amazon.com/singlesignon/)

## Next Steps

1. **[Getting Started](getting-started.md)** - Set up your first backup
2. **[Configuration](configuration.md)** - Customize backup settings
3. **[Examples](examples/basic-examples.md)** - Learn from practical examples
4. **[Advanced Topics](cross-account.md)** - Explore advanced features
