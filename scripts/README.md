# Scripts

This directory contains utility scripts for the awsideman project.

## Import Validation Scripts

These scripts were created during the project packaging reorganization to validate that all import statements resolve correctly after moving files between packages.

### `validate_internal_imports.py`

Validates internal project imports without trying to actually import modules that depend on external libraries. This script:

- Scans all Python files in the project
- Extracts internal import statements (awsideman package imports)
- Validates that import paths exist in the file system
- Reports any broken internal import references

**Usage:**
```bash
python3 scripts/validate_internal_imports.py
```

**Features:**
- Path-based validation (doesn't require external dependencies)
- Handles relative imports correctly
- Provides detailed error reporting
- Focuses only on internal project imports

### `validate_imports.py`

Comprehensive import validation script that attempts to actually import modules. This script:

- Validates both internal and external imports
- Uses actual Python import mechanism
- Skips known external dependencies
- Provides detailed import statistics

**Usage:**
```bash
python3 scripts/validate_imports.py
```

**Features:**
- Comprehensive import testing
- External dependency detection
- Detailed error reporting with context
- Import statistics and categorization

## When to Use These Scripts

- **During refactoring**: When moving files or reorganizing package structure
- **Before releases**: To ensure all imports are working correctly
- **Debugging import issues**: To identify broken import paths
- **Code quality checks**: As part of CI/CD validation

## Requirements

These scripts only require Python standard library modules and don't need external dependencies to run the validation logic.