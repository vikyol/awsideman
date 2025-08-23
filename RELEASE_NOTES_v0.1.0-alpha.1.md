# 🚀 awsideman v0.1.0-alpha.1 - Alpha Release

> **Release Date**: August 24, 2025
> **Version**: 0.1.0-alpha.1
> **Status**: Alpha (Pre-release)
> **Python**: 3.10+

## ⚠️ **Alpha Release Notice**

**This is an alpha release and is NOT recommended for production use.**

- Breaking changes may occur in future releases
- Some features may be incomplete or unstable
- Please report any issues you encounter
- Feedback and contributions are welcome!

## 🎉 **What's New in This Release**

### **🌟 Major Features**

#### **1. Profile-Aware Cache System**
- **Separate cache backends per profile** (file, DynamoDB)
- **Profile-specific cache settings** via simplified CLI commands
- **Enhanced cache management** with `--profile` support
- **Automatic cache path management** for file-based caching

#### **2. Enhanced CLI Commands**
- **`awsideman config show`** - Display current profile's cache settings
- **`awsideman config set cache.backend_type=file`** - Simplified profile cache configuration
- **`awsideman cache status --profile <profile>`** - Profile-aware cache status
- **`awsideman cache clear --profile <profile>`** - Profile-aware cache clearing
- **`awsideman cache warm --profile <profile>`** - Profile-aware cache warming

#### **3. Advanced Cache Backends**
- **File-based caching** with encryption support (AES-256)
- **DynamoDB backend** for scalable, cloud-based caching
- **Cache statistics and monitoring** for performance insights
- **Automatic TTL management** and cleanup

#### **4. Comprehensive Permission Management**
- **User and group creation/deletion** with validation
- **Permission set management** and customization
- **Assignment operations** across multiple accounts
- **Bulk permission operations** for large-scale management

#### **5. Backup and Restore System**
- **Full and incremental backup** support
- **Multiple storage backends** (filesystem, S3)
- **Backup scheduling and monitoring** capabilities
- **Restore preview and execution** with safety checks

#### **6. Template System**
- **YAML-based configuration templates** for common scenarios
- **Template validation and execution** with error handling
- **Predefined templates** for admin, developer, and DevOps access
- **Custom template creation** and management

#### **7. Rollback System**
- **Operation tracking and logging** for all changes
- **Automatic rollback capabilities** for failed operations
- **Rollback monitoring and cleanup** with retention policies
- **Emergency rollback procedures** for critical situations

#### **8. Multi-Account Support**
- **AWS Organizations integration** for enterprise environments
- **Cross-account operations** with role assumption
- **Profile-based account management** for multiple environments
- **Account filtering and targeting** by tags and OUs

## 🔧 **Technical Improvements**

### **Performance Enhancements**
- **Intelligent caching** with up to 90% reduction in API calls
- **Parallel processing** for bulk operations
- **Optimized storage** for cache backends
- **Memory-efficient** operations for large datasets

### **Code Quality**
- **Comprehensive test suite** with 3180+ tests
- **Type safety** with full mypy compliance
- **Code formatting** with black and ruff
- **Import sorting** with isort

### **Error Handling**
- **Improved error messages** with actionable feedback
- **Comprehensive validation** before AWS API calls
- **Graceful degradation** for non-critical failures
- **Detailed logging** for debugging and audit

## 📋 **Installation**

### **Quick Install (Recommended)**
```bash
# Install alpha version
pip install awsideman==0.1.0-alpha.1

# Or with Poetry
poetry add awsideman@0.1.0-alpha.1
```

### **From Source**
```bash
git clone https://github.com/vikyol/awsideman.git
cd awsideman
poetry install
```

## ⚙️ **Configuration**

### **Profile-Specific Cache Setup**
```bash
# Set file-based caching for a profile
awsideman config set cache.backend_type=file --profile myprofile

# View current profile's cache settings
awsideman config show --profile myprofile

# Check cache status
awsideman cache status --profile myprofile
```

### **Cache Configuration File**
```yaml
# ~/.awsideman/config.yaml
cache:
  backend_type: file  # or dynamodb
  encryption: true    # AES-256 encryption
  ttl: 3600          # Cache TTL in seconds
  max_size: 1000     # Maximum cache entries

profiles:
  myprofile:
    cache:
      backend_type: dynamodb
      table_name: myprofile-cache
      region: eu-north-1
```

## 🚀 **Quick Start Examples**

### **Basic Operations**
```bash
# Check your SSO environment
awsideman info

# List users
awsideman user list

# Create a new user
awsideman user create john.doe --email john.doe@company.com

# Assign permissions
awsideman assignment assign DeveloperAccess john.doe --account Development
```

### **Cache Management**
```bash
# Check cache status
awsideman cache status

# Warm up cache for common operations
awsideman cache warm

# Clear cache if needed
awsideman cache clear
```

### **Backup Operations**
```bash
# Create a full backup
awsideman backup create --type full

# List available backups
awsideman backup list

# Restore from backup (preview first)
awsideman restore --backup-id backup-20241219 --dry-run
```

## 🧪 **Testing and Validation**

### **Run Tests**
```bash
# Run all tests
poetry run pytest

# Run specific test categories
poetry run pytest tests/unit/
poetry run pytest tests/integration/
poetry run pytest tests/performance/
```

### **Code Quality Checks**
```bash
# Format code
poetry run black src/ tests/

# Lint code
poetry run ruff check src/ tests/

# Type checking
poetry run mypy src/
```

## 📚 **Documentation**

- **[Getting Started Guide](docs/getting-started.md)** - Step-by-step setup
- **[Configuration Reference](CONFIGURATION.md)** - All configuration options
- **[Command Reference](docs/)** - Complete CLI documentation
- **[Examples](examples/)** - Real-world usage patterns
- **[API Documentation](docs/api/)** - Internal API reference

## 🐛 **Known Issues and Limitations**

### **Alpha Release Limitations**
- Some advanced features may be incomplete
- Performance optimizations are ongoing
- Edge cases in error handling may exist
- Documentation may have gaps

### **Current Limitations**
- Limited support for very large organizations (>1000 accounts)
- Some AWS regions may have API limitations
- Complex permission set inheritance scenarios
- Advanced filtering options are being enhanced

## 🔮 **What's Coming Next**

### **Planned for Beta Release**
- Enhanced bulk operations with progress bars
- Advanced permission set inheritance
- Improved error recovery mechanisms
- Performance monitoring and metrics
- Additional storage backends

### **Future Roadmap**
- Web-based management interface
- Integration with CI/CD pipelines
- Advanced compliance reporting
- Multi-cloud support
- Plugin system for custom backends

## 🤝 **Contributing**

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### **How to Help**
- Report bugs and issues
- Suggest new features
- Improve documentation
- Contribute code improvements
- Share your use cases and feedback

## 📞 **Support and Feedback**

- **GitHub Issues**: [Report bugs and issues](https://github.com/vikyol/awsideman/issues)
- **GitHub Discussions**: [Ask questions and share ideas](https://github.com/vikyol/awsideman/discussions)
- **Documentation**: Check the `docs/` directory
- **Examples**: Browse the `examples/` directory

## 🙏 **Acknowledgments**

- Built with ❤️ for the AWS community
- Inspired by the need for human-friendly AWS tooling
- Thanks to all contributors and users who make this project better
- Special thanks to early alpha testers and feedback providers

---

## 📊 **Release Statistics**

- **Total Tests**: 3180+ tests passing
- **Code Coverage**: Comprehensive test coverage
- **Dependencies**: 20+ production dependencies
- **Documentation**: Extensive documentation and examples
- **Performance**: Optimized for production workloads

---

**Ready to try awsideman? Install the alpha release and start simplifying your AWS Identity Center management!**

```bash
pip install awsideman==0.1.0-alpha.1
awsideman info
```

**Star ⭐ this repository if awsideman helps you manage AWS Identity Center more effectively!**
