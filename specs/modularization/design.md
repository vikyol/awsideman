# Design Document

## Overview

The modularization feature will refactor large command files into smaller, focused submodules. This design maintains backward compatibility while improving code organization, maintainability, and testability. The current monolithic command files range from 1,055 to 3,217 lines, making them difficult to navigate and maintain.

**Phase 1 (Completed):** `assignment.py` (2,997 lines), `cache.py` (3,217 lines), `user.py` (1,214 lines)
**Phase 2 (Planned):** `permission_set.py` (1,617 lines), `group.py` (1,370 lines), `status.py` (1,055 lines)

The refactoring will create directory-based module structures where each command type gets its own directory with focused submodules. The CLI interface will remain unchanged through proper import management and module initialization.

## Architecture

### Current Structure
```
src/awsideman/commands/
├── assignment.py (2,997 lines) ❌ REMOVED
├── cache.py (3,217 lines)      ❌ REMOVED
├── user.py (1,214 lines)       ❌ REMOVED
├── permission_set.py (1,617 lines) ⚠️ TARGET FOR PHASE 2
├── group.py (1,370 lines)      ⚠️ TARGET FOR PHASE 2
├── status.py (1,055 lines)     ⚠️ TARGET FOR PHASE 2
└── ...
```

### Target Structure
```
src/awsideman/commands/
├── assignment/ ✅ COMPLETED
│   ├── __init__.py
│   ├── assign.py
│   ├── revoke.py
│   ├── list.py
│   ├── get.py
│   └── helpers.py
├── cache/ ✅ COMPLETED
│   ├── __init__.py
│   ├── clear.py
│   ├── status.py
│   ├── warm.py
│   ├── encryption.py
│   ├── accounts.py
│   ├── inspect.py
│   └── helpers.py
├── user/ ✅ COMPLETED
│   ├── __init__.py
│   ├── list.py
│   ├── get.py
│   ├── create.py
│   ├── update.py
│   ├── delete.py
│   └── helpers.py
├── permission_set/ 🚧 PLANNED FOR PHASE 2
│   ├── __init__.py
│   ├── list.py
│   ├── get.py
│   ├── create.py
│   ├── update.py
│   ├── delete.py
│   └── helpers.py
├── group/ 🚧 PLANNED FOR PHASE 2
│   ├── __init__.py
│   ├── list.py
│   ├── get.py
│   ├── create.py
│   ├── update.py
│   ├── delete.py
│   ├── members.py
│   └── helpers.py
├── status/ 🚧 PLANNED FOR PHASE 2
│   ├── __init__.py
│   ├── check.py
│   ├── inspect.py
│   ├── cleanup.py
│   ├── monitor.py
│   └── helpers.py
└── ...
```

## Components and Interfaces

### Assignment Module Structure

**assignment/__init__.py**
- Exports the main `app` typer instance
- Imports and registers all subcommands
- Maintains backward compatibility for existing imports

**assignment/assign.py**
- Contains the `assign_permission_set` command function
- Handles permission set assignment logic
- Imports shared utilities from helpers.py

**assignment/revoke.py**
- Contains the `revoke_permission_set` command function
- Handles permission set revocation logic
- Shares common validation with helpers.py

**assignment/list.py**
- Contains the `list_assignments` command function
- Handles assignment listing and filtering
- Uses shared formatting utilities

**assignment/get.py**
- Contains the `get_assignment` command function
- Handles detailed assignment retrieval
- Uses shared validation and formatting

**assignment/helpers.py**
- Contains shared utility functions
- Common validation logic
- Shared formatting and display functions
- Error handling utilities

### Cache Module Structure

**cache/__init__.py**
- Exports the main `app` typer instance
- Imports and registers all cache subcommands
- Maintains backward compatibility

**cache/clear.py**
- Contains the `clear_cache` command function
- Handles cache clearing operations
- Uses shared cache management utilities

**cache/status.py**
- Contains the `cache_status` command function
- Displays cache statistics and health information
- Uses shared formatting utilities

**cache/warm.py**
- Contains the `warm_cache` command function
- Handles cache warming operations
- Uses shared performance optimization logic

**cache/encryption.py**
- Contains the `encryption_management` command function
- Handles encryption key management
- Uses shared encryption utilities

**cache/accounts.py**
- Contains the `account_cache_status` command function
- Handles account-specific cache operations
- Uses shared account filtering logic

**cache/inspect.py**
- Contains the `inspect_cache` command function
- Provides detailed cache inspection capabilities
- Uses shared diagnostic utilities

**cache/helpers.py**
- Contains shared cache management utilities
- Common validation and error handling
- Shared formatting and display functions
- Performance optimization helpers

### User Module Structure

**user/__init__.py**
- Exports the main `app` typer instance
- Imports and registers all user subcommands
- Maintains backward compatibility

**user/list.py**
- Contains the `list_users` command function
- Handles user listing and pagination
- Uses shared formatting utilities

**user/get.py**
- Contains the `get_user` command function
- Handles user retrieval and display
- Uses shared validation logic

**user/create.py**
- Contains the `create_user` command function
- Handles user creation operations
- Uses shared validation and error handling

**user/update.py**
- Contains the `update_user` command function
- Handles user modification operations
- Uses shared validation logic

**user/delete.py**
- Contains the `delete_user` command function
- Handles user deletion operations
- Uses shared confirmation and error handling

**user/helpers.py**
- Contains shared user management utilities
- Common validation and error handling
- Shared formatting and display functions
- Interactive input utilities (like `get_single_key`)

### Permission Set Module Structure

**permission_set/__init__.py**
- Exports the main `app` typer instance
- Imports and registers all permission set subcommands
- Maintains backward compatibility

**permission_set/list.py**
- Contains the `list_permission_sets` command function
- Handles permission set listing and filtering
- Uses shared validation and formatting utilities

**permission_set/get.py**
- Contains the `get_permission_set` command function
- Handles detailed permission set retrieval
- Uses shared validation and formatting

**permission_set/create.py**
- Contains the `create_permission_set` command function
- Handles permission set creation operations
- Uses shared validation and error handling

**permission_set/update.py**
- Contains the `update_permission_set` command function
- Handles permission set modification operations
- Uses shared validation and conflict resolution

**permission_set/delete.py**
- Contains the `delete_permission_set` command function
- Handles permission set deletion operations
- Uses shared confirmation and error handling

**permission_set/helpers.py**
- Contains shared permission set management utilities
- Common validation and error handling
- Shared formatting and display functions
- Permission set identifier resolution

### Group Module Structure

**group/__init__.py**
- Exports the main `app` typer instance
- Imports and registers all group subcommands
- Maintains backward compatibility

**group/list.py**
- Contains the `list_groups` command function
- Handles group listing and filtering
- Uses shared validation and formatting utilities

**group/get.py**
- Contains the `get_group` command function
- Handles group retrieval and display
- Uses shared validation logic

**group/create.py**
- Contains the `create_group` command function
- Handles group creation operations
- Uses shared validation and error handling

**group/update.py**
- Contains the `update_group` command function
- Handles group modification operations
- Uses shared validation logic

**group/delete.py**
- Contains the `delete_group` command function
- Handles group deletion operations
- Uses shared confirmation and error handling

**group/members.py**
- Contains group member management commands
- Handles adding/removing members from groups
- Uses shared validation and error handling

**group/helpers.py**
- Contains shared group management utilities
- Common validation and error handling
- Shared formatting and display functions
- Member management utilities

### Status Module Structure

**status/__init__.py**
- Exports the main `app` typer instance
- Imports and registers all status subcommands
- Maintains backward compatibility

**status/check.py**
- Contains the `check_status` command function
- Handles comprehensive status checking
- Uses shared monitoring and notification utilities

**status/inspect.py**
- Contains the `inspect_resource` command function
- Handles resource inspection operations
- Uses shared resource inspection utilities

**status/cleanup.py**
- Contains the `cleanup_orphaned` command function
- Handles orphaned resource cleanup
- Uses shared cleanup and validation utilities

**status/monitor.py**
- Contains the `monitor_config` command function
- Handles monitoring configuration and scheduling
- Uses shared monitoring and notification utilities

**status/helpers.py**
- Contains shared status monitoring utilities
- Common validation and error handling
- Shared formatting and display functions
- Monitoring configuration utilities

## Data Models

The modularization will not introduce new data models but will maintain the existing data structures:

- **MultiAccountAssignment**: Used in assignment operations
- **CacheEntry**: Used in cache operations
- **User models**: Used in user operations

All existing model imports and usage patterns will be preserved in the new modular structure.

## Error Handling

### Centralized Error Handling
- Each helpers.py module will contain common error handling patterns
- Shared exception handling for AWS API errors
- Consistent error message formatting across submodules

### Error Propagation
- Submodules will use shared error handling utilities
- Maintain existing error codes and messages
- Preserve current logging and error reporting behavior

### Validation
- Common validation logic will be centralized in helpers.py files
- Input validation will be consistent across related commands
- Shared validation for AWS resource identifiers

## Testing Strategy

### Test Structure Migration
```
tests/unit/commands/
├── assignment/ ✅ COMPLETED
│   ├── test_assign.py
│   ├── test_revoke.py
│   ├── test_list.py
│   ├── test_get.py
│   └── test_helpers.py
├── cache/ ✅ COMPLETED
│   ├── test_clear.py
│   ├── test_status.py
│   ├── test_warm.py
│   ├── test_encryption.py
│   ├── test_accounts.py
│   ├── test_inspect.py
│   └── test_helpers.py
├── user/ ✅ COMPLETED
│   ├── test_list.py
│   ├── test_get.py
│   ├── test_create.py
│   ├── test_update.py
│   ├── test_delete.py
│   └── test_helpers.py
├── permission_set/ 🚧 PLANNED FOR PHASE 2
│   ├── test_list.py
│   ├── test_get.py
│   ├── test_create.py
│   ├── test_update.py
│   ├── test_delete.py
│   └── test_helpers.py
├── group/ 🚧 PLANNED FOR PHASE 2
│   ├── test_list.py
│   ├── test_get.py
│   ├── test_create.py
│   ├── test_update.py
│   ├── test_delete.py
│   ├── test_members.py
│   └── test_helpers.py
├── status/ 🚧 PLANNED FOR PHASE 2
│   ├── test_check.py
│   ├── test_inspect.py
│   ├── test_cleanup.py
│   ├── test_monitor.py
│   └── test_helpers.py
└── ...
```

### Test Migration Strategy
1. **Import Updates**: Update all test imports to reference new module paths
2. **Test Splitting**: Split existing monolithic test files into focused test modules
3. **Shared Test Utilities**: Create test helpers for common test patterns
4. **Coverage Maintenance**: Ensure test coverage is maintained or improved
5. **Integration Testing**: Verify CLI interface remains unchanged

### Test Validation
- All existing tests must pass after refactoring
- New modular tests should provide better isolation
- Test execution time should remain similar or improve
- Mock and fixture usage should be optimized for the new structure

## Implementation Phases

### Phase 1: Core Modules (COMPLETED ✅)
1. **Assignment Module** - ✅ COMPLETED
   - Create assignment directory structure
   - Split assignment.py into focused submodules
   - Update imports and maintain CLI compatibility
   - Update related tests

2. **Cache Module** - ✅ COMPLETED
   - Create cache directory structure
   - Split cache.py into focused submodules
   - Update imports and maintain CLI compatibility
   - Update related tests

3. **User Module** - ✅ COMPLETED
   - Create user directory structure
   - Split user.py into focused submodules
   - Update imports and maintain CLI compatibility
   - Update related tests

### Phase 2: Extended Modules (PLANNED 🚧)
4. **Permission Set Module** - 🚧 PLANNED
   - Create permission_set directory structure
   - Split permission_set.py into focused submodules
   - Update imports and maintain CLI compatibility
   - Update related tests

5. **Group Module** - 🚧 PLANNED
   - Create group directory structure
   - Split group.py into focused submodules
   - Update imports and maintain CLI compatibility
   - Update related tests

6. **Status Module** - 🚧 PLANNED
   - Create status directory structure
   - Split status.py into focused submodules
   - Update imports and maintain CLI compatibility
   - Update related tests

### Phase 3: Integration and Validation
1. Run full test suite to ensure no regressions
2. Validate CLI interface remains unchanged
3. Performance testing to ensure no degradation
4. Documentation updates if needed

## Backward Compatibility

### Import Compatibility
- The `__init__.py` files will re-export all necessary functions and classes
- Existing imports like `from awsideman.commands.assignment import app` will continue to work
- Internal imports within the codebase will be updated to use the new structure

### CLI Interface
- All command signatures will remain identical
- Command help text and behavior will be preserved
- Exit codes and error messages will remain consistent

### API Compatibility
- All public functions and classes will maintain their signatures
- Internal refactoring will not affect external usage
- Configuration and environment variable handling will remain unchanged
