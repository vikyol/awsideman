# AI Agent Guide for AWS Identity Manager (awsideman)

This document provides AI agents with essential information about the project structure, execution environment, testing procedures, and development workflow.

## Project Overview

**awsideman** is a Python-based AWS Identity Center (SSO) management tool that provides comprehensive backup, restore, and management capabilities for AWS SSO resources including users, groups, permission sets, and assignments.

## Execution Environment

### Prerequisites
- **Python**: 3.10+ (project uses Poetry for dependency management)
- **Poetry**: Required for package management and virtual environment
- **AWS CLI**: Configured with appropriate credentials/profiles
- **Operating System**: macOS, Linux, or Windows (tested on macOS)

### Setup Commands
```bash
# Install Poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install

# Activate virtual environment
poetry shell

# Or run commands directly with poetry run
poetry run awsideman --help
```

### Environment Variables
```bash
# AWS Profile (optional, can be specified via --profile flag)
export AWS_PROFILE=your-profile-name

# AWS Region (optional, can be specified via --region flag)
export AWS_DEFAULT_REGION=eu-west-1

# Debug logging (optional)
export LOG_LEVEL=DEBUG
```

## Project Structure

```
awsideman/
├── src/awsideman/           # Main source code
│   ├── backup_restore/      # Backup and restore functionality
│   ├── commands/            # CLI command implementations
│   ├── permission_cloning/  # Permission cloning features
│   ├── rollback/           # Rollback operations
│   ├── templates/          # Template system
│   └── utils/              # Utility functions
├── tests/                  # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── performance/       # Performance tests
├── examples/              # Usage examples and templates
├── docs/                  # Documentation
└── pyproject.toml        # Project configuration
```

## Testing

### Running Tests
```bash
# Run all tests
poetry run pytest

# Run specific test categories
poetry run pytest tests/unit/
poetry run pytest tests/integration/
poetry run pytest tests/performance/

# Run with coverage
poetry run pytest --cov=src/awsideman

# Run specific test file
poetry run pytest tests/unit/backup_restore/test_manager.py

# Run with verbose output
poetry run pytest -v

# Run tests in parallel
poetry run pytest -n auto
```

### Test Fixtures
- **Location**: `tests/fixtures/`
- **Purpose**: Provides mock data and test utilities
- **Key Files**:
  - `aws_clients.py`: Mock AWS client configurations
  - `bulk_operations.py`: Bulk operation test data
  - `common.py`: Common test utilities
  - `organizations.py`: AWS Organizations mock data

### Test Data
- **Sample Data**: `examples/` directory contains sample configurations
- **Mock Responses**: Tests use mocked AWS API responses
- **Validation**: Tests validate both success and error scenarios

## Code Quality & Linting

### Linters and Formatters
```bash
# Run black (code formatter)
poetry run black src/ tests/

# Run isort (import sorter)
poetry run isort src/ tests/

# Run ruff (linter), auto-fix the issues where possible
poetry run ruff check --fix

# Run mypy (type checker)
poetry run mypy src/

# Run all quality checks
poetry run pre-commit run --all-files
```

### Pre-commit Hooks
```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run all hooks on staged files
poetry run pre-commit run

# Run specific hook
poetry run pre-commit run black
```

## Development Workflow

### Running the Tool
```bash
# Basic help
poetry run awsideman --help

# Backup operations
poetry run awsideman backup create --type full
poetry run awsideman backup list
poetry run awsideman backup delete <backup-id>

# User management
poetry run awsideman user create --username testuser
poetry run awsideman user list

# Group management
poetry run awsideman group create --name testgroup
poetry run awsideman group list

# Permission set operations
poetry run awsideman permission-set create --name testps
poetry run awsideman permission-set list
```

### Common Development Commands
```bash
# Run specific command with debug output
poetry run awsideman backup create --type incremental --since 2024-01-01 --verbose

# Test with specific AWS profile
poetry run awsideman backup list --profile development

# Run with custom storage backend
poetry run awsideman backup create --storage s3 --storage-path my-bucket/backups

# Validate configuration
poetry run awsideman templates validate example-config.yaml
```

## Key Components for AI Agents

### 1. Backup System
- **Storage Backends**: Filesystem and S3 support
- **Backup Types**: Full and incremental backups
- **Encryption**: AES encryption support
- **Compression**: Optional compression for storage efficiency

### 2. Permission Cloning
- **Cross-entity**: User-to-user, user-to-group copying
- **Filtering**: Advanced filtering for permission sets
- **Rollback**: Comprehensive rollback system

### 3. Template System
- **YAML-based**: Human-readable configuration templates
- **Validation**: Built-in template validation
- **Execution**: Template-based operations

### 4. Multi-account Support
- **Cross-account**: Operations across multiple AWS accounts
- **Organizations**: AWS Organizations integration
- **Role assumption**: Cross-account role management

## Error Handling

### Common Error Scenarios
1. **AWS Credentials**: Invalid or expired credentials
2. **Permissions**: Insufficient IAM permissions
3. **Network**: Connectivity issues to AWS services
4. **Storage**: S3 bucket access or filesystem permissions
5. **Validation**: Invalid input data or configuration

### Debug Mode
```bash
# Enable debug logging
poetry run awsideman --log-level DEBUG backup create

# Or set environment variable
export LOG_LEVEL=DEBUG
poetry run awsideman backup create
```

## Performance Considerations

### Backup Performance
- **Parallel Collection**: Configurable parallel resource collection
- **Batch Operations**: Bulk operations for large datasets
- **Caching**: Local metadata index for faster operations
- **Optimization**: Performance optimization for storage

### Memory Management
- **Streaming**: Large file handling without memory issues
- **Pagination**: AWS API pagination support
- **Resource Limits**: Configurable resource limits

## Integration Points

### AWS Services
- **Identity Center (SSO)**: Primary service for user/group management
- **S3**: Backup storage backend
- **IAM**: Permission management
- **Organizations**: Multi-account management

### External Tools
- **AWS CLI**: Profile and credential management
- **Docker**: Containerized testing (if needed)
- **CI/CD**: GitHub Actions integration

## Troubleshooting

### Common Issues
1. **Import Errors**: Check Poetry environment and dependencies
2. **AWS Errors**: Verify credentials and permissions
3. **Storage Errors**: Check S3 bucket access or filesystem permissions
4. **Performance Issues**: Review parallel collection settings

### Debug Commands
```bash
# Check AWS configuration
poetry run awsideman status check

# Validate storage backend
poetry run awsideman backup health

# Test connectivity
poetry run awsideman status check --verbose
```

## Best Practices for AI Agents

### Code Changes
1. **Always run tests** after making changes
2. **Use type hints** for all new functions
3. **Follow existing patterns** for consistency
4. **Update documentation** when adding features
5. **Handle errors gracefully** with user-friendly messages

### Testing Strategy
1. **Unit tests** for individual functions
2. **Integration tests** for component interactions
3. **Performance tests** for critical operations
4. **Mock external dependencies** for reliable testing

### Error Handling
1. **Provide clear error messages** to users
2. **Log detailed information** for debugging
3. **Implement proper rollback** for failed operations
4. **Validate inputs** before processing

This guide should help AI agents understand the project structure and contribute effectively to the awsideman project.
