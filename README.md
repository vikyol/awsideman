# awsideman - AWS Identity Center Manager

> **"Because humans shouldn't have to think like machines"**

> ⚠️ **ALPHA RELEASE WARNING** ⚠️
>
> **This is an alpha release (v0.1.0-alpha.1) and is not recommended for production use.**
> - Breaking changes may occur in future releases
> - Some features may be incomplete or unstable
> - Please report any issues you encounter
> - Feedback and contributions are welcome!

A powerful, open-source CLI tool that transforms AWS Identity Center (SSO) management from complex, error-prone tasks into intuitive, human-friendly operations. Built for teams who value **simplicity**, **safety**, and **scalability**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/dependency%20management-poetry-blue.svg)](https://python-poetry.org/)

## 🎯 **Why awsideman?**

Managing AWS Identity Center at scale is complex. awsideman makes it simple.

**Traditional AWS CLI approach:**
```bash
# ❌ Complex, error-prone
aws sso-admin create-account-assignment \
  --instance-arn "arn:aws:sso:::instance/ssoins-xxxxxxxxxxxxxxxxx" \
  --target-id "xxxxxxxxxxxx" \
  --target-type "AWS_ACCOUNT" \
  --permission-set-arn "arn:aws:sso:::permissionSet/ps-xxxxxxxxxxxxxxxxx" \
  --principal-type "USER" \
  --principal-id "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

**awsideman approach:**
```bash
# ✅ Simple, intuitive
awsideman assignment assign ReadOnlyAccess john.doe 123456789012
```

## 🌟 **Key Features**

### **🎭 Human-Friendly Interface**
- **Use names, not IDs**: Work with `john.doe` instead of UUIDs
- **Intuitive commands**: Natural language-style operations
- **Auto-discovery**: Automatically detects and configures your SSO environment
- **Smart suggestions**: Context-aware command completion and hints

### **🔒 Enterprise-Grade Safety**
- **Dry-run mode**: Preview all changes before execution
- **Confirmation prompts**: Built-in safeguards for destructive operations
- **Comprehensive validation**: Catch errors before they reach AWS
- **Full audit logging**: Complete operation history for compliance

### **⚡ Performance & Scale**
- **Intelligent caching**: Up to 90% reduction in API calls
- **Bulk operations**: Process hundreds of assignments efficiently
- **Parallel processing**: Configurable concurrency for optimal performance
- **Progress tracking**: Real-time feedback for long-running operations

### **🛠️ Powerful Management**
- **Multi-account operations**: Manage access across your entire AWS organization
- **Advanced filtering**: Target resources by tags, OUs, patterns, and more
- **Permission cloning**: Copy access patterns between users and groups
- **Backup & restore**: Complete SSO configuration backup and recovery
- **Multiple profile/SSO support**: Manage multiple AWS organizations and Identity Centers from a single tool

## 🚀 **Major Use Cases**

### **1. User Lifecycle Management**
```bash
# Onboard new employee
awsideman assignment assign DeveloperAccess new.employee --filter "tag:Environment=Development"

# Offboard departing employee
awsideman assignment revoke ReadOnlyAccess former.employee --filter "*"
awsideman assignment revoke DeveloperAccess former.employee --filter "*"
```

### **2. Bulk Operations**
```bash
# Bulk assign from CSV
awsideman bulk assign assignments.csv --dry-run

# Bulk operations with filtering
awsideman assignment assign ReadOnlyAccess AuditorsGroup --filter "tag:Compliance=Required"
```

### **3. Access Reviews & Compliance**
```bash
# Generate access reports
awsideman access-review principal john.doe --format csv --output user_access.csv
awsideman access-review account 123456789012

# Permission set analysis
awsideman access-review permission-set AdminAccess
```

### **4. Backup & Disaster Recovery**
```bash
# Create comprehensive backups
awsideman backup create --type full
awsideman backup create --type incremental --since 2024-01-01

# Restore from backup
awsideman restore apply backup-20240101 --dry-run
```

### **5. Permission Copying**
```bash
# Copy permissions between users
awsideman copy --from user:john.doe --to user:jane.smith

# Copy permissions between groups
awsideman copy --from group:developers --to group:qa-team

# Copy permissions from user to group
awsideman copy --from user:senior.dev --to group:junior-developers

# Copy with filtering (exclude admin access)
awsideman copy --from user:admin.user --to user:new.employee \
  --exclude-permission-sets "AdminAccess,BillingAccess"

# Copy with account filtering
awsideman copy --from group:production-team --to group:staging-team \
  --include-accounts "123456789012,987654321098"
```

### **6. Permission Set Cloning**
```bash
# Clone a permission set with a new name
awsideman clone --name PowerUserAccess --to DeveloperAccess

# Clone with custom description
awsideman clone --name PowerUserAccess --to DeveloperAccess \
  --description "Developer access with limited permissions"

# Preview clone operation before executing
awsideman clone --name PowerUserAccess --to DeveloperAccess --preview
```

### **7. Multi-Organization Management**
```bash
# Synchronize user access across environments
awsideman assignment assign DeveloperAccess john.doe \
  --profile dev-org --filter "tag:Environment=Development"
awsideman assignment assign DeveloperAccess john.doe \
  --profile prod-org --filter "tag:Environment=Production"

# Cross-organization backup and restore
awsideman backup create --profile production --type full
awsideman backup create --profile development --type full

# Manage multiple client environments
awsideman user create --username client1.admin --display-name "Client1 Admin" --email client1.admin@company.com --profile client1-production
awsideman assignment assign AdminAccess client1.admin \
  --profile client1-production --filter "tag:Client=Client1"
```

## 🛠️ **Installation & Setup**

### **Prerequisites**
- Python 3.10 or higher
- Poetry (for dependency management)
- AWS CLI configured with appropriate credentials

### **Installation**

#### **Option 1: Install Alpha Release (Recommended for Testing)**
```bash
# Install the latest alpha version
pip install awsideman==0.1.0-alpha.1

# Or with Poetry
poetry add awsideman@0.1.0-alpha.1

# Verify installation
awsideman --help
```

#### **Option 2: Install from Source (Development)**
```bash
# Clone the repository
git clone https://github.com/vikyol/awsideman.git
cd awsideman

# Install dependencies
poetry install

# Activate the environment
poetry shell

# Verify installation
awsideman --help
```

### **Quick Configuration**
```bash
# Auto-detect your SSO environment
awsideman info

# Configure AWS profile (if needed)
awsideman profile add my-profile --region us-east-1

# Test connectivity
awsideman user list --limit 5
```

## 📖 **Configuration Options**

awsideman is highly configurable to fit your organization's needs:

### **Cache Configuration**
```yaml
# ~/.awsideman/config.yaml
cache:
  backend: filesystem  # or redis, s3
  ttl: 3600           # Cache TTL in seconds
  encryption: true    # Encrypt cached data
  max_size: 1000      # Maximum cache entries
```

### **Performance Tuning**
```yaml
performance:
  batch_size: 50      # Bulk operation batch size
  max_workers: 10     # Parallel processing workers
  retry_attempts: 3   # API retry attempts
  backoff_factor: 2   # Exponential backoff multiplier
```

### **Security Settings**
```yaml
security:
  require_confirmation: true  # Require confirmation for destructive ops
  audit_logging: true        # Enable comprehensive audit logs
  keyring_integration: true  # Use OS keyring for credentials
```

### **Profile Management**
```yaml
profiles:
  default: production        # Default profile to use
  aliases:
    prod: production         # Short aliases for profiles
    dev: development
    stage: staging
  cross_org_operations: true  # Enable cross-organization features
  profile_switching: true     # Allow runtime profile switching
```

## 🎯 **Advanced Features**

### **Template System**
Create reusable access templates:
```yaml
# templates/developer-access.yaml
name: "Developer Access Template"
assignments:
  - permission_set: "DeveloperAccess"
    accounts:
      - filter: "tag:Environment=Development"
      - filter: "tag:Environment=Staging"
  - permission_set: "ReadOnlyAccess"
    accounts:
      - filter: "tag:Environment=Production"
```

```bash
awsideman templates apply developer-access.yaml
```

### **Multi-Account Operations**
```bash
# Cross-account permission management
awsideman assignment assign ReadOnlyAccess auditor \
  --ou-filter "Root/Production" \
  --batch-size 20 \
  --continue-on-error

# Organization-wide access reviews
awsideman access-review account 123456789012 --format json
```

### **Multiple Profile/SSO Support**
Manage multiple AWS organizations and Identity Centers from a single tool:

```bash
# Work with different AWS profiles
awsideman user list --profile production
awsideman user list --profile development
awsideman user list --profile staging

# Cross-organization operations
awsideman assignment assign ReadOnlyAccess john.doe \
  --profile production \
  --filter "tag:Environment=Production"

# Bulk operations across multiple organizations
awsideman bulk assign cross-org-assignments.csv \
  --profile production \
  --continue-on-error
```

**Perfect for:**
- **Multi-tenant environments**: Manage separate AWS organizations for different clients
- **DevOps teams**: Handle development, staging, and production environments
- **Consultants**: Manage multiple client AWS environments from one tool
- **Enterprise**: Centralized management of subsidiary or regional AWS organizations

### **Rollback System**
```bash
# All operations are tracked for rollback
awsideman rollback list
awsideman rollback apply operation-12345 --dry-run
```

## 🧪 **Development & Testing**

### **Running Tests**
```bash
# Run all tests
poetry run pytest

# Run specific test categories
poetry run pytest tests/unit/
poetry run pytest tests/integration/

# Run with coverage
poetry run pytest --cov=src/awsideman
```

### **Code Quality**
```bash
# Format code
poetry run black src/ tests/

# Lint code
poetry run ruff check --fix

# Type checking
poetry run mypy src/

# Run all quality checks
poetry run pre-commit run --all-files
```

## 🏗️ **Architecture & Design**

awsideman is built with modern software engineering principles:

- **Modular Architecture**: Clean separation of concerns for maintainability
- **Plugin System**: Extensible cache backends and storage systems
- **Type Safety**: Full mypy compliance for robust development
- **Comprehensive Testing**: 1000+ tests ensuring reliability
- **Performance Optimized**: Intelligent caching and parallel processing

## 📊 **Performance**

- **Single Assignment**: ~2 seconds (vs 5-10 seconds with AWS CLI)
- **Bulk Operations**: 100 assignments in ~30 seconds
- **Cache Hit Rate**: 90%+ for repeated operations
- **Memory Usage**: <100MB for typical operations

## 🤝 **Contributing**

We welcome contributions from the community! Whether you're fixing bugs, adding features, or improving documentation, your help is appreciated.

### **Getting Started**
```bash
# Fork the repository and clone your fork
git clone https://github.com/your-username/awsideman.git
cd awsideman

# Set up development environment
poetry install
poetry run pre-commit install

# Run tests to ensure everything works
poetry run pytest
```

### **Development Guidelines**
- **Focus on one change per PR**: Keep changes small and focused
- **Write tests**: All new features should include comprehensive tests
- **Follow code style**: Use `black`, `ruff`, and `mypy` for code quality
- **Update documentation**: Help others understand your changes

### **Submitting Changes**
1. Create a feature branch: `git checkout -b feature/amazing-feature`
2. Make your changes and add tests
3. Run quality checks: `poetry run pre-commit run --all-files`
4. Commit your changes: `git commit -m 'Add amazing feature'`
5. Push to your fork: `git push origin feature/amazing-feature`
6. Open a Pull Request

## 📚 **Documentation**

Comprehensive documentation is available:

- **[Getting Started Guide](docs/backup-restore/getting-started.md)** - Step-by-step setup
- **[Configuration Reference](CONFIGURATION.md)** - All configuration options
- **[Command Reference](docs/)** - Complete CLI documentation
- **[Examples](examples/)** - Real-world usage patterns
- **[API Documentation](docs/api/)** - Internal API reference
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute

## 🐛 **Support & Issues**

- **Bug Reports**: [GitHub Issues](https://github.com/your-org/awsideman/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/your-org/awsideman/discussions)
- **Documentation**: Check the `docs/` directory
- **Examples**: Browse the `examples/` directory

## 🔒 **Security**

Security is a top priority:

- **Credential Security**: Uses AWS credential chain, never stores credentials
- **Encryption**: AES-256 encryption for cached data
- **Audit Logging**: Comprehensive operation logging
- **Validation**: Input validation and sanitization
- **Least Privilege**: Follows AWS security best practices

Report security issues privately to the maintainers.

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 **Acknowledgments**

- Built with ❤️ for the AWS community
- Inspired by the need for human-friendly AWS tooling
- Thanks to all contributors and users who make this project better

---

**Ready to simplify your AWS Identity Center management?**

```bash
# Quick start with alpha release
pip install awsideman==0.1.0-alpha.1
awsideman info

# Or from source
git clone https://github.com/vikyol/awsideman.git
cd awsideman
poetry install
awsideman info
```

**Star ⭐ this repository if awsideman helps you manage AWS Identity Center more effectively!**
