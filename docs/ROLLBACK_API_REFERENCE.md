# Rollback API Reference

This document provides detailed API reference for the rollback system components in awsideman.

## Table of Contents

1. [OperationLogger](#operationlogger)
2. [RollbackProcessor](#rollbackprocessor)
3. [Data Models](#data-models)
4. [Storage Classes](#storage-classes)
5. [Exception Classes](#exception-classes)
6. [Utility Functions](#utility-functions)

## OperationLogger

The `OperationLogger` class provides the primary interface for tracking permission set operations.

### Class Definition

```python
class OperationLogger:
    """Logger for tracking permission set operations for rollback purposes."""

    def __init__(self, config: Optional[Config] = None) -> None:
        """Initialize the operation logger."""
```

### Methods

#### `log_operation(operation_data: Dict[str, Any]) -> str`

Logs a new operation and returns the generated operation ID.

**Parameters:**
- `operation_data` (Dict[str, Any]): Dictionary containing operation details

**Required Fields in operation_data:**
- `operation_type` (str): "assign" or "revoke"
- `principal_id` (str): AWS principal identifier
- `principal_type` (str): "USER" or "GROUP"
- `principal_name` (str): Human-readable principal name
- `permission_set_arn` (str): AWS permission set ARN
- `permission_set_name` (str): Human-readable permission set name
- `account_ids` (List[str]): List of affected account IDs
- `account_names` (List[str]): List of affected account names
- `results` (List[Dict]): List of operation results per account
- `metadata` (Dict[str, Any]): Additional operation metadata

**Returns:**
- `str`: Generated operation ID (UUID format)

**Raises:**
- `ValueError`: If required fields are missing or invalid
- `StorageError`: If operation cannot be saved to storage

**Example:**
```python
from awsideman.rollback import OperationLogger

logger = OperationLogger()
operation_data = {
    "operation_type": "assign",
    "principal_id": "user-123456789",
    "principal_type": "USER",
    "principal_name": "john.doe",
    "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
    "permission_set_name": "ReadOnlyAccess",
    "account_ids": ["123456789012"],
    "account_names": ["Production"],
    "results": [{"account_id": "123456789012", "success": True, "error": None}],
    "metadata": {"source": "cli", "user": "admin@company.com"}
}

operation_id = logger.log_operation(operation_data)
print(f"Operation logged with ID: {operation_id}")
```

#### `get_operations(filters: Optional[Dict[str, Any]] = None) -> List[OperationRecord]`

Retrieves operations with optional filtering.

**Parameters:**
- `filters` (Optional[Dict[str, Any]]): Filter criteria

**Supported Filter Keys:**
- `operation_type` (str): Filter by operation type ("assign", "revoke", "rollback")
- `principal_name` (str): Filter by principal name (partial match)
- `permission_set_name` (str): Filter by permission set name (partial match)
- `days` (int): Filter operations from last N days
- `rolled_back` (bool): Filter by rollback status
- `account_id` (str): Filter by account ID

**Returns:**
- `List[OperationRecord]`: List of matching operation records

**Example:**
```python
# Get all operations from last 7 days
recent_ops = logger.get_operations({"days": 7})

# Get assign operations for specific user
user_assigns = logger.get_operations({
    "operation_type": "assign",
    "principal_name": "john.doe"
})

# Get operations for specific permission set
ps_ops = logger.get_operations({
    "permission_set_name": "AdminAccess"
})
```

#### `get_operation(operation_id: str) -> Optional[OperationRecord]`

Retrieves a specific operation by ID.

**Parameters:**
- `operation_id` (str): The operation ID to retrieve

**Returns:**
- `Optional[OperationRecord]`: The operation record if found, None otherwise

**Example:**
```python
operation = logger.get_operation("abc123-def456-ghi789")
if operation:
    print(f"Found operation: {operation.operation_type} for {operation.principal_name}")
else:
    print("Operation not found")
```

#### `mark_rolled_back(operation_id: str, rollback_operation_id: str) -> None`

Marks an operation as rolled back.

**Parameters:**
- `operation_id` (str): ID of the operation that was rolled back
- `rollback_operation_id` (str): ID of the rollback operation

**Raises:**
- `OperationNotFoundError`: If the operation ID doesn't exist
- `StorageError`: If the update cannot be saved

**Example:**
```python
logger.mark_rolled_back("abc123-def456-ghi789", "def456-ghi789-jkl012")
```

#### `cleanup_old_operations(days: int = 90) -> int`

Removes operations older than the specified number of days.

**Parameters:**
- `days` (int): Number of days to retain (default: 90)

**Returns:**
- `int`: Number of operations removed

**Example:**
```python
removed_count = logger.cleanup_old_operations(30)
print(f"Removed {removed_count} old operations")
```

## RollbackProcessor

The `RollbackProcessor` class handles rollback validation, planning, and execution.

### Class Definition

```python
class RollbackProcessor:
    """Processor for validating and executing rollback operations."""

    def __init__(self, config: Optional[Config] = None) -> None:
        """Initialize the rollback processor."""
```

### Methods

#### `validate_rollback(operation_id: str) -> RollbackValidation`

Validates whether a rollback is possible for the specified operation.

**Parameters:**
- `operation_id` (str): ID of the operation to validate

**Returns:**
- `RollbackValidation`: Validation results object

**Validation Checks:**
- Operation exists and is not already rolled back
- Current AWS state matches expected state for rollback
- User has necessary AWS permissions
- No conflicting operations exist

**Example:**
```python
from awsideman.rollback import RollbackProcessor

processor = RollbackProcessor()
validation = processor.validate_rollback("abc123-def456-ghi789")

if validation.is_valid:
    print("Rollback is possible")
else:
    print("Validation errors:")
    for error in validation.errors:
        print(f"  - {error}")

    print("Warnings:")
    for warning in validation.warnings:
        print(f"  - {warning}")
```

#### `generate_plan(operation_id: str) -> RollbackPlan`

Generates a detailed execution plan for rolling back an operation.

**Parameters:**
- `operation_id` (str): ID of the operation to roll back

**Returns:**
- `RollbackPlan`: Detailed rollback execution plan

**Raises:**
- `OperationNotFoundError`: If the operation doesn't exist
- `AlreadyRolledBackError`: If the operation is already rolled back
- `RollbackError`: If plan generation fails

**Example:**
```python
plan = processor.generate_plan("abc123-def456-ghi789")

print(f"Rollback plan for operation {plan.operation_id}")
print(f"Rollback type: {plan.rollback_type}")
print(f"Actions to perform: {len(plan.actions)}")
print(f"Estimated duration: {plan.estimated_duration} seconds")

for action in plan.actions:
    print(f"  {action.action_type} {action.permission_set_arn} "
          f"for {action.principal_id} on {action.account_id}")

if plan.warnings:
    print("Warnings:")
    for warning in plan.warnings:
        print(f"  - {warning}")
```

#### `execute_rollback(plan: RollbackPlan, dry_run: bool = False, batch_size: int = 10) -> RollbackResult`

Executes a rollback plan.

**Parameters:**
- `plan` (RollbackPlan): The rollback plan to execute
- `dry_run` (bool): If True, simulate execution without making changes (default: False)
- `batch_size` (int): Number of actions to process in parallel (default: 10)

**Returns:**
- `RollbackResult`: Results of the rollback execution

**Execution Process:**
1. Pre-execution state verification
2. Parallel execution of rollback actions in batches
3. Post-execution verification
4. Result compilation and logging

**Example:**
```python
# Generate plan
plan = processor.generate_plan("abc123-def456-ghi789")

# Dry run first
dry_result = processor.execute_rollback(plan, dry_run=True)
if dry_result.success:
    print("Dry run successful, proceeding with actual rollback")

    # Execute for real
    result = processor.execute_rollback(plan, dry_run=False, batch_size=5)

    if result.success:
        print(f"Rollback completed successfully")
        print(f"Rollback operation ID: {result.rollback_operation_id}")
        print(f"Duration: {result.duration} seconds")
    else:
        print(f"Rollback failed: {result.error_message}")
        print(f"Successful actions: {result.successful_actions}")
        print(f"Failed actions: {result.failed_actions}")
else:
    print(f"Dry run failed: {dry_result.error_message}")
```

#### `verify_rollback(rollback_operation_id: str) -> RollbackVerification`

Verifies that a rollback operation completed successfully.

**Parameters:**
- `rollback_operation_id` (str): ID of the rollback operation to verify

**Returns:**
- `RollbackVerification`: Verification results

**Example:**
```python
verification = processor.verify_rollback("def456-ghi789-jkl012")

if verification.is_verified:
    print("Rollback verification successful")
    print(f"All {verification.verified_actions} actions completed correctly")
else:
    print("Rollback verification failed")
    for issue in verification.issues:
        print(f"  - {issue}")
```

## Data Models

### OperationRecord

Represents a complete record of a permission set operation.

```python
@dataclass
class OperationRecord:
    operation_id: str
    timestamp: datetime
    operation_type: OperationType
    principal_id: str
    principal_type: PrincipalType
    principal_name: str
    permission_set_arn: str
    permission_set_name: str
    account_ids: List[str]
    account_names: List[str]
    results: List[OperationResult]
    metadata: Dict[str, Any]
    rolled_back: bool = False
    rollback_operation_id: Optional[str] = None
```

**Methods:**
- `to_dict(include_sensitive: bool = False) -> Dict[str, Any]`: Convert to dictionary
- `from_dict(data: Dict[str, Any]) -> OperationRecord`: Create from dictionary
- `is_successful() -> bool`: Check if all results were successful
- `get_failed_accounts() -> List[str]`: Get list of accounts where operation failed

### OperationResult

Represents the result of an operation on a single account.

```python
@dataclass
class OperationResult:
    account_id: str
    success: bool
    error: Optional[str] = None
    duration_ms: Optional[int] = None
```

### RollbackPlan

Represents a plan for executing a rollback operation.

```python
@dataclass
class RollbackPlan:
    operation_id: str
    rollback_type: RollbackActionType
    actions: List[RollbackAction]
    estimated_duration: int
    warnings: List[str] = field(default_factory=list)
```

**Methods:**
- `get_actions_by_account(account_id: str) -> List[RollbackAction]`: Get actions for specific account
- `get_total_actions() -> int`: Get total number of actions
- `has_warnings() -> bool`: Check if plan has warnings

### RollbackAction

Represents a single action within a rollback plan.

```python
@dataclass
class RollbackAction:
    principal_id: str
    permission_set_arn: str
    account_id: str
    action_type: RollbackActionType
    current_state: AssignmentState
```

### RollbackValidation

Represents the results of rollback validation.

```python
@dataclass
class RollbackValidation:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
```

**Methods:**
- `add_error(error: str) -> None`: Add validation error
- `add_warning(warning: str) -> None`: Add validation warning
- `has_errors() -> bool`: Check if validation has errors
- `has_warnings() -> bool`: Check if validation has warnings

### RollbackResult

Represents the results of rollback execution.

```python
@dataclass
class RollbackResult:
    success: bool
    rollback_operation_id: Optional[str] = None
    successful_actions: int = 0
    failed_actions: int = 0
    duration: float = 0.0
    error_message: Optional[str] = None
    action_results: List[Dict[str, Any]] = field(default_factory=list)
```

**Methods:**
- `get_success_rate() -> float`: Calculate success rate percentage
- `get_failed_action_details() -> List[Dict[str, Any]]`: Get details of failed actions
- `is_partial_success() -> bool`: Check if some actions succeeded

### RollbackVerification

Represents the results of rollback verification.

```python
@dataclass
class RollbackVerification:
    is_verified: bool
    verified_actions: int = 0
    failed_verifications: int = 0
    issues: List[str] = field(default_factory=list)
```

## Storage Classes

### OperationStore

Base storage interface for operation records.

```python
class OperationStore:
    """Base class for operation storage backends."""

    def save_operation(self, operation: OperationRecord) -> None:
        """Save an operation record."""

    def load_operations(self, filters: Optional[Dict] = None) -> List[OperationRecord]:
        """Load operations with optional filtering."""

    def update_operation(self, operation_id: str, updates: Dict[str, Any]) -> None:
        """Update an existing operation record."""

    def delete_operation(self, operation_id: str) -> None:
        """Delete an operation record."""
```

### JSONOperationStore

JSON file-based storage implementation.

```python
class JSONOperationStore(OperationStore):
    """JSON file-based storage for operation records."""

    def __init__(self, storage_dir: str) -> None:
        """Initialize with storage directory path."""
```

**Methods:**
- `get_storage_size() -> int`: Get storage size in bytes
- `get_operation_count() -> int`: Get total number of stored operations
- `backup_storage(backup_path: str) -> None`: Create backup of storage
- `restore_storage(backup_path: str) -> None`: Restore from backup

## Exception Classes

### RollbackError

Base exception for rollback-related errors.

```python
class RollbackError(Exception):
    """Base exception for rollback operations."""

    def __init__(self, message: str, operation_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.operation_id = operation_id
```

### OperationNotFoundError

Raised when an operation ID is not found.

```python
class OperationNotFoundError(RollbackError):
    """Raised when an operation is not found."""
```

### AlreadyRolledBackError

Raised when attempting to rollback an already rolled back operation.

```python
class AlreadyRolledBackError(RollbackError):
    """Raised when operation is already rolled back."""
```

### StateMismatchError

Raised when current AWS state doesn't match expected state.

```python
class StateMismatchError(RollbackError):
    """Raised when AWS state doesn't match expected state."""

    def __init__(self, message: str, expected_state: str, actual_state: str) -> None:
        super().__init__(message)
        self.expected_state = expected_state
        self.actual_state = actual_state
```

### StorageError

Raised when storage operations fail.

```python
class StorageError(RollbackError):
    """Raised when storage operations fail."""
```

### ValidationError

Raised when rollback validation fails.

```python
class ValidationError(RollbackError):
    """Raised when rollback validation fails."""

    def __init__(self, message: str, validation_errors: List[str]) -> None:
        super().__init__(message)
        self.validation_errors = validation_errors
```

## Utility Functions

### `generate_operation_id() -> str`

Generates a unique operation ID.

**Returns:**
- `str`: UUID-based operation ID

**Example:**
```python
from awsideman.rollback.utils import generate_operation_id

operation_id = generate_operation_id()
print(f"Generated ID: {operation_id}")
```

### `validate_operation_data(operation_data: Dict[str, Any]) -> List[str]`

Validates operation data structure.

**Parameters:**
- `operation_data` (Dict[str, Any]): Operation data to validate

**Returns:**
- `List[str]`: List of validation errors (empty if valid)

**Example:**
```python
from awsideman.rollback.utils import validate_operation_data

errors = validate_operation_data(operation_data)
if errors:
    print("Validation errors:")
    for error in errors:
        print(f"  - {error}")
```

### `format_duration(seconds: float) -> str`

Formats duration in human-readable format.

**Parameters:**
- `seconds` (float): Duration in seconds

**Returns:**
- `str`: Formatted duration string

**Example:**
```python
from awsideman.rollback.utils import format_duration

duration_str = format_duration(125.5)
print(duration_str)  # "2m 5.5s"
```

### `mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]`

Masks sensitive information in operation data.

**Parameters:**
- `data` (Dict[str, Any]): Data to mask

**Returns:**
- `Dict[str, Any]`: Data with sensitive fields masked

**Example:**
```python
from awsideman.rollback.utils import mask_sensitive_data

masked_data = mask_sensitive_data(operation_data)
# Sensitive fields like user emails are masked
```

## Configuration

### RollbackConfig

Configuration class for rollback settings.

```python
@dataclass
class RollbackConfig:
    enabled: bool = True
    storage_directory: str = "~/.awsideman/operations"
    retention_days: int = 90
    auto_cleanup: bool = True
    max_operations: int = 10000
    confirmation_required: bool = True
    dry_run_default: bool = False
    default_batch_size: int = 10
    compress_logs: bool = False
    log_level: str = "INFO"
```

**Environment Variable Overrides:**
- `AWSIDEMAN_ROLLBACK_ENABLED`
- `AWSIDEMAN_ROLLBACK_STORAGE_DIR`
- `AWSIDEMAN_ROLLBACK_RETENTION_DAYS`
- `AWSIDEMAN_ROLLBACK_CONFIRMATION_REQUIRED`
- `AWSIDEMAN_ROLLBACK_DRY_RUN_DEFAULT`
- `AWSIDEMAN_ROLLBACK_DEFAULT_BATCH_SIZE`
- `AWSIDEMAN_ROLLBACK_AUTO_CLEANUP`
- `AWSIDEMAN_ROLLBACK_COMPRESS_LOGS`
- `AWSIDEMAN_ROLLBACK_LOG_LEVEL`

## Usage Examples

### Complete Rollback Workflow

```python
from awsideman.rollback import OperationLogger, RollbackProcessor
from awsideman.utils.config import Config

# Initialize components
config = Config()
logger = OperationLogger(config)
processor = RollbackProcessor(config)

# 1. Log an operation (typically done automatically by commands)
operation_data = {
    "operation_type": "assign",
    "principal_id": "user-123456789",
    "principal_type": "USER",
    "principal_name": "john.doe",
    "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
    "permission_set_name": "ReadOnlyAccess",
    "account_ids": ["123456789012", "234567890123"],
    "account_names": ["Production", "Staging"],
    "results": [
        {"account_id": "123456789012", "success": True},
        {"account_id": "234567890123", "success": True}
    ],
    "metadata": {"source": "cli", "user": "admin@company.com"}
}

operation_id = logger.log_operation(operation_data)
print(f"Operation logged: {operation_id}")

# 2. Later, rollback the operation
validation = processor.validate_rollback(operation_id)
if not validation.is_valid:
    print(f"Rollback not possible: {validation.errors}")
    exit(1)

# 3. Generate rollback plan
plan = processor.generate_plan(operation_id)
print(f"Rollback plan: {len(plan.actions)} actions")

# 4. Execute rollback
result = processor.execute_rollback(plan, dry_run=False)
if result.success:
    print(f"Rollback successful: {result.rollback_operation_id}")

    # 5. Verify rollback
    verification = processor.verify_rollback(result.rollback_operation_id)
    if verification.is_verified:
        print("Rollback verification successful")
    else:
        print(f"Verification issues: {verification.issues}")
else:
    print(f"Rollback failed: {result.error_message}")
```

### Custom Storage Backend

```python
from awsideman.rollback.storage import OperationStore
import boto3

class DynamoDBOperationStore(OperationStore):
    """DynamoDB-based storage backend."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)

    def save_operation(self, operation: OperationRecord) -> None:
        item = operation.to_dict(include_sensitive=False)
        self.table.put_item(Item=item)

    def load_operations(self, filters: Optional[Dict] = None) -> List[OperationRecord]:
        # Implementation for loading from DynamoDB
        response = self.table.scan()
        operations = []
        for item in response['Items']:
            operations.append(OperationRecord.from_dict(item))
        return operations

# Use custom storage backend
custom_store = DynamoDBOperationStore("awsideman-operations")
logger = OperationLogger()
logger.storage = custom_store
```

### Error Handling Example

```python
from awsideman.rollback.exceptions import *

try:
    result = processor.execute_rollback(plan)
except OperationNotFoundError as e:
    print(f"Operation not found: {e.operation_id}")
except AlreadyRolledBackError as e:
    print(f"Operation already rolled back: {e.operation_id}")
except StateMismatchError as e:
    print(f"State mismatch - Expected: {e.expected_state}, Actual: {e.actual_state}")
except ValidationError as e:
    print(f"Validation failed: {e.validation_errors}")
except StorageError as e:
    print(f"Storage error: {e}")
except RollbackError as e:
    print(f"General rollback error: {e}")
```

---

This API reference provides comprehensive documentation for all rollback system components. For usage examples and integration guides, see the [Rollback Developer Guide](ROLLBACK_DEVELOPER_GUIDE.md).
