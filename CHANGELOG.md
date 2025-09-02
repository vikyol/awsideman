# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1-alpha] - 2025-09-02

### Added
- Profile-specific cache configuration support
- Enhanced cache management with file and DynamoDB backends
- Advanced permission cloning capabilities
- Bulk operations for user and group management
- Template-based configuration system
- Rollback system for operations
- Multi-account support with AWS Organizations integration
- Comprehensive backup and restore functionality
- Encryption support for cache files (AES-256)
- Performance optimization features

### Changed
- Improved CLI command structure and user experience
- Enhanced error handling and user feedback
- Better integration with AWS Identity Center APIs
- Optimized cache performance and storage

### Fixed
- Profile-specific cache configuration issues
- Cache entry display problems with file backend
- Various test failures and integration issues

## [0.1.0-alpha.3] - 2025-08-24

### Added
- **Profile-Aware Cache System**: Support for profile-specific cache configurations
  - Separate cache backends per profile (file, DynamoDB)
  - Profile-specific cache settings via `awsideman config set cache.*`
  - Enhanced cache management commands with `--profile` support

- **Enhanced CLI Commands**:
  - `awsideman config show` - Display current profile's cache settings
  - `awsideman config set cache.backend_type=file` - Simplified profile cache configuration
  - `awsideman cache status --profile <profile>` - Profile-aware cache status
  - `awsideman cache clear --profile <profile>` - Profile-aware cache clearing
  - `awsideman cache warm --profile <profile>` - Profile-aware cache warming

- **Advanced Cache Backends**:
  - File-based caching with encryption support
  - DynamoDB backend for scalable caching
  - Automatic cache path management
  - Cache statistics and monitoring

- **Permission Management**:
  - User and group creation/deletion
  - Permission set management
  - Assignment operations
  - Bulk permission operations

- **Backup and Restore**:
  - Full and incremental backup support
  - Multiple storage backends (filesystem, S3)
  - Backup scheduling and monitoring
  - Restore preview and execution

- **Template System**:
  - YAML-based configuration templates
  - Template validation and execution
  - Predefined templates for common use cases

- **Rollback System**:
  - Operation tracking and logging
  - Automatic rollback capabilities
  - Rollback monitoring and cleanup

### Changed
- **Configuration Management**: Simplified profile-specific cache configuration
- **Cache Operations**: All cache commands now support `--profile` flag
- **Error Handling**: Improved error messages and user feedback
- **Performance**: Enhanced caching performance and storage optimization

### Fixed
- Profile-specific cache configuration integration issues
- Cache entry display problems with file backend
- Test failures in profile cache integration
- Cache warm command test issues
- DynamoDB backend statistics display

### Technical Details
- **Python Version**: 3.9+
- **Dependencies**: Modern Python ecosystem (Poetry, Pydantic, Rich, Typer)
- **Testing**: Comprehensive test suite with 3180+ tests
- **Code Quality**: Linting and type checking compliance
- **Documentation**: Extensive documentation and examples

### Known Limitations (Alpha Release)
- This is an alpha release and may contain bugs
- Breaking changes may occur in future releases
- Not recommended for production use
- Some advanced features may be incomplete

### Installation
```bash
# Install alpha version
pip install awsideman==0.1.0-alpha.1

# Or with Poetry
poetry add awsideman@0.1.0-alpha.1
```

### Configuration
```bash
# Set profile-specific cache backend
awsideman config set cache.backend_type=file --profile myprofile

# View current profile's cache settings
awsideman config show --profile myprofile

# Check cache status
awsideman cache status --profile myprofile
```

---

## [0.0.1] - Initial Development

### Added
- Basic project structure and CLI framework
- Initial AWS Identity Center integration
- Basic user and group management commands
- Foundation for backup and restore functionality
