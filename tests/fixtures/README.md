# Test Fixtures

This directory contains organized test fixtures and data for awsideman tests, replacing the generic `conftest.py` approach with a more structured and maintainable system.

## Directory Structure

```
tests/fixtures/
├── __init__.py              # Package initialization and exports
├── common.py                # Shared fixtures and configuration
├── aws_clients.py           # AWS client mocks and fixtures
├── bulk_operations.py       # Bulk operation test data and fixtures
├── rollback_operations.py   # Rollback operation test data and fixtures
├── permission_sets.py       # Permission set test data and fixtures
├── users_groups.py          # User and group test data and fixtures
└── organizations.py         # AWS Organizations test data and fixtures
```

## Usage

### Importing Fixtures

```python
# Import specific fixtures
from tests.fixtures.common import mock_validation_functions
from tests.fixtures.aws_clients import mock_aws_client_manager
from tests.fixtures.bulk_operations import sample_bulk_assignments
from tests.fixtures.rollback_operations import sample_operation_record

# Or import from the package
from tests.fixtures import mock_aws_client_manager, sample_bulk_assignments
```

### Using Fixtures in Tests

```python
import pytest
from tests.fixtures import mock_aws_client_manager, sample_bulk_assignments

def test_bulk_operation(mock_aws_client_manager, sample_bulk_assignments):
    """Test bulk operation with mocked AWS client and sample data."""
    # Use the fixtures
    aws_client = mock_aws_client_manager
    assignments = sample_bulk_assignments

    # Your test logic here
    assert len(assignments) > 0
```

## Available Fixtures

### Common Fixtures (`common.py`)
- `mock_validation_functions`: Mock all validation functions
- `mock_aws_infrastructure`: Mock AWS client infrastructure
- `sample_permission_set_data`: Sample permission set data
- `sample_create_response`: Sample create response
- `sample_managed_policies`: Sample managed policies
- `PermissionSetMockFactory`: Factory for creating permission set mocks

### AWS Client Fixtures (`aws_clients.py`)
- `mock_aws_client_manager`: Mock AWS client manager with all clients
- `mock_sso_admin_client`: Mock SSO Admin client
- `mock_identity_store_client`: Mock Identity Store client
- `mock_organizations_client`: Mock Organizations client
- `mock_iam_client`: Mock IAM client
- `aws_client_factory`: Factory for creating custom AWS client mocks
- `mock_aws_error`: Mock AWS error responses

### Bulk Operation Fixtures (`bulk_operations.py`)
- `sample_bulk_assignments`: Sample bulk assignment data
- `sample_csv_data`: Sample CSV data for bulk operations
- `sample_json_data`: Sample JSON data for bulk operations
- `sample_resolved_assignments`: Sample resolved assignments with AWS identifiers
- `sample_bulk_results`: Sample bulk operation results
- `sample_multi_account_data`: Sample multi-account data
- `bulk_operation_factory`: Factory for creating bulk operation test data

### Rollback Operation Fixtures (`rollback_operations.py`)
- `sample_operation_record`: Sample operation record
- `sample_rollback_plan`: Sample rollback plan
- `sample_rollback_validation`: Sample rollback validation result
- `sample_rollback_actions`: Sample rollback actions
- `sample_operation_results`: Sample operation results
- `sample_rollback_operation_data`: Sample rollback operation data
- `rollback_operation_factory`: Factory for creating rollback operation test data

### Permission Set Fixtures (`permission_sets.py`)
- `sample_permission_set_data`: Sample permission set data
- `sample_create_response`: Sample create response
- `sample_managed_policies`: Sample managed policies
- `sample_permission_sets_list`: Sample list of permission sets
- `sample_permission_set_assignments`: Sample permission set assignments
- `permission_set_factory`: Factory for creating permission set test data

### User and Group Fixtures (`users_groups.py`)
- `sample_user_data`: Sample user data
- `sample_group_data`: Sample group data
- `sample_users_list`: Sample list of users
- `sample_groups_list`: Sample list of groups
- `sample_group_members`: Sample group members
- `sample_user_assignments`: Sample user assignments
- `users_groups_factory`: Factory for creating users and groups test data

### Organization Fixtures (`organizations.py`)
- `sample_account_data`: Sample AWS account data
- `sample_organizational_unit_data`: Sample organizational unit data
- `sample_root_data`: Sample root organizational unit data
- `sample_accounts_list`: Sample list of AWS accounts
- `sample_organizational_units_list`: Sample list of organizational units
- `sample_organization_hierarchy`: Sample organization hierarchy
- `sample_account_tags`: Sample account tags
- `organizations_factory`: Factory for creating AWS Organizations test data

## Factory Pattern

Many fixture modules include factory classes that allow you to create custom test data:

```python
from tests.fixtures import bulk_operation_factory, permission_set_factory

# Create custom test data
custom_assignments = bulk_operation_factory.create_bulk_assignments(count=10)
custom_permission_set = permission_set_factory.create_permission_set(
    name="CustomAccess",
    description="Custom permission set for testing"
)
```

## Migration from conftest.py

If you were previously using fixtures from `conftest.py`, you can now import them from the appropriate fixture module:

```python
# Old way (conftest.py)
# pytest automatically discovered these fixtures

# New way
from tests.fixtures.common import mock_validation_functions
from tests.fixtures.aws_clients import mock_aws_client_manager
```

## Best Practices

1. **Import Specific Fixtures**: Import only the fixtures you need
2. **Use Factories**: Use factory classes for creating custom test data
3. **Group Related Fixtures**: Keep related fixtures in the same module
4. **Document Fixtures**: Add docstrings to explain fixture purpose and usage
5. **Reuse Fixtures**: Import and reuse fixtures across different test modules

## Adding New Fixtures

To add new fixtures:

1. **Identify the appropriate module** based on functionality
2. **Add the fixture** to the relevant module
3. **Update the `__init__.py`** to export the new fixture
4. **Add documentation** explaining the fixture's purpose and usage

Example:

```python
# In tests/fixtures/new_module.py
@pytest.fixture
def new_fixture():
    """Description of what this fixture provides."""
    return {"key": "value"}

# In tests/fixtures/__init__.py
from .new_module import new_fixture

__all__ = [
    # ... existing fixtures ...
    "new_fixture",
]
```
