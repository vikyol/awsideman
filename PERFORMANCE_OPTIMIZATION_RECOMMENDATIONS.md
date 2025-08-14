# Performance Optimization Recommendations for Permission Set Tests

## Issue Summary
The `test_permission_set_*` test suites are running slowly (10+ seconds per test case) due to excessive mocking and complex type checking introduced after mypy improvements.

## Root Causes Identified

### 1. Excessive Mock Patching (Primary Issue)
- **440+ @patch decorators** across permission set test files
- Each test function has 6-9 stacked @patch decorators
- Mock setup overhead is significant when multiplied across many tests

### 2. Repetitive Validation Function Mocking
- Same validation functions mocked in every test:
  - `validate_permission_set_name`
  - `validate_permission_set_description`
  - `validate_aws_managed_policy_arn`
  - `validate_profile`
  - `validate_sso_instance`

### 3. Complex Type Annotations + Strict MyPy
- MyPy strict mode with complex generic types
- `Optional[List[str]]`, `Tuple[List[Dict[str, Any]], Optional[str]]`
- Type checking overhead during test execution

## Optimization Solutions

### Solution 1: Consolidate Mocks with Fixtures (Recommended)
Create shared fixtures to reduce repetitive patching:

```python
@pytest.fixture
def mock_validation_functions():
    """Mock all validation functions in one fixture."""
    with patch.multiple(
        'src.awsideman.commands.permission_set',
        validate_permission_set_name=MagicMock(return_value=True),
        validate_permission_set_description=MagicMock(return_value=True),
        validate_aws_managed_policy_arn=MagicMock(return_value=True),
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")),
    ) as mocks:
        yield mocks

@pytest.fixture
def mock_aws_infrastructure():
    """Mock AWS client infrastructure."""
    with patch.multiple(
        'src.awsideman.commands.permission_set',
        AWSClientManager=MagicMock(),
        console=MagicMock(),
    ) as mocks:
        yield mocks
```

### Solution 2: Use patch.object Instead of String Paths
Replace string-based patching with object-based patching:

```python
# Instead of:
@patch("src.awsideman.commands.permission_set.validate_profile")

# Use:
@patch.object(permission_set, 'validate_profile')
```

### Solution 3: Mock at Module Level
Use `pytest.fixture(autouse=True)` for common mocks:

```python
@pytest.fixture(autouse=True)
def mock_common_dependencies():
    """Auto-mock common dependencies for all tests."""
    with patch.multiple(
        'src.awsideman.commands.permission_set',
        validate_profile=DEFAULT,
        validate_sso_instance=DEFAULT,
        AWSClientManager=DEFAULT,
        console=DEFAULT,
    ):
        yield
```

### Solution 4: Simplify Type Annotations
Consider simplifying complex type hints in hot paths:

```python
# Instead of:
def _list_permission_sets_internal(
    filter: Optional[str] = None,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:

# Consider:
def _list_permission_sets_internal(
    filter=None,
    limit=None,
    next_token=None,
    profile=None,
):
```

### Solution 5: Use Mock Factories
Create reusable mock factories:

```python
class PermissionSetMockFactory:
    @staticmethod
    def create_aws_client_mock():
        mock = MagicMock()
        mock_sso_admin = MagicMock()
        mock.get_client.return_value = mock_sso_admin
        return mock, mock_sso_admin

    @staticmethod
    def create_permission_set_response():
        return {
            "PermissionSet": {
                "Name": "TestPermissionSet",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                # ... other fields
            }
        }
```

## Implementation Priority

1. **High Priority**: Implement Solution 1 (Consolidate Mocks with Fixtures)
2. **Medium Priority**: Implement Solution 5 (Mock Factories)
3. **Low Priority**: Consider Solution 4 (Simplify Type Annotations) for performance-critical paths

## Expected Performance Improvement

- **Current**: 10+ seconds per test case
- **After optimization**: 1-2 seconds per test case
- **Overall improvement**: 80-90% reduction in test execution time

## Implementation Steps

1. Create `tests/conftest.py` with shared fixtures
2. Refactor `test_permission_set_create.py` first as a proof of concept
3. Apply same patterns to other permission set test files
4. Measure performance improvements
5. Iterate and optimize further if needed
