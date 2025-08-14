# Rollback System Developer Guide

This document provides comprehensive technical documentation for the rollback system in awsideman, including architecture, APIs, and extension guidelines.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Data Models](#data-models)
4. [API Reference](#api-reference)
5. [Integration Points](#integration-points)
6. [Extension Guidelines](#extension-guidelines)
7. [Testing Framework](#testing-framework)
8. [Performance Considerations](#performance-considerations)
9. [Security Implementation](#security-implementation)
10. [Troubleshooting](#troubleshooting)

## Architecture Overview

The rollback system is designed as a modular, extensible component that integrates seamlessly with the existing awsideman architecture. It follows the established patterns for configuration, logging, error handling, and AWS client management.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Layer                                │
├─────────────────────────────────────────────────────────────────┤
│  rollback.py (Typer commands)                                   │
│  ├── list    - List historical operations                       │
│  ├── apply   - Apply rollback for operation                     │
│  └── status  - Show rollback status                             │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Operation Tracking                           │
├─────────────────────────────────────────────────────────────────┤
│  OperationLogger                                                │
│  ├── log_operation()    - Record operation details              │
│  ├── get_operations()   - Retrieve operation history            │
│  └── mark_rolled_back() - Mark operation as rolled back         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Rollback Engine                              │
├─────────────────────────────────────────────────────────────────┤
│  RollbackProcessor                                              │
│  ├── validate_rollback()  - Check rollback feasibility          │
│  ├── generate_plan()      - Create rollback execution plan      │
│  ├── execute_rollback()   - Perform rollback operations         │
│  └── verify_rollback()    - Verify rollback completion          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Storage Layer                                │
├─────────────────────────────────────────────────────────────────┤
│  OperationStore (JSON-based)                                    │
│  ├── ~/.awsideman/operations/                                   │
│  ├── operations.json       - Operation records                  │
│  └── rollbacks.json        - Rollback records                   │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Modularity**: Each component has a single responsibility and clear interfaces
2. **Extensibility**: New operation types and storage backends can be added easily
3. **Safety**: Multiple validation layers prevent accidental data loss
4. **Performance**: Async operations and batch processing for scalability
5. **Observability**: Comprehensive logging and monitoring capabilities
6. **Consistency**: Follows existing awsideman patterns and conventions

## Core Components

### 1. OperationLogger

The `OperationLogger` class is responsible for tracking all permission set operations.

**Location**: `src/awsideman/utils/rollback/logger.py`

**Key Methods**:
```python
class OperationLogger:
    def log_operation(self, operation_data: Dict[str, Any]) -> str:
        """Log a new operation and return operation ID."""

    def get_operations(self, filters: Optional[Dict] = None) -> List[OperationRecord]:
        """Retrieve operations with optional filtering."""

    def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        """Get a specific operation by ID."""

    def mark_rolled_back(self, operation_id: str, rollback_operation_id: str) -> None:
        """Mark an operation as rolled back."""

    def cleanup_old_operations(self, days: int = 90) -> None:
        """Remove operations older than specified days."""
```

**Usage Example**:
```python
from awsideman.rollback import OperationLogger

logger = OperationLogger()

# Log a new operation
operation_data = {
    "operation_type": "assign",
    "principal_id": "user-123",
    "principal_type": "USER",
    "principal_name": "john.doe",
    "permission_set_arn": "arn:aws:sso:::permissionSet/...",
    "permission_set_name": "ReadOnlyAccess",
    "account_ids": ["123456789012"],
    "account_names": ["Production"],
    "results": [{"account_id": "123456789012", "success": True}],
    "metadata": {"source": "individual_assign"}
}

operation_id = logger.log_operation(operation_data)
```

### 2. RollbackProcessor

The `RollbackProcessor` class handles rollback validation, planning, and execution.

**Location**: `src/awsideman/utils/rollback/processor.py`

**Key Methods**:
```python
class RollbackProcessor:
    def validate_rollback(self, operation_id: str) -> RollbackValidation:
        """Validate if rollback is possible for the operation."""

    def generate_plan(self, operation_id: str) -> RollbackPlan:
        """Generate detailed rollback execution plan."""

    def execute_rollback(self, plan: RollbackPlan, dry_run: bool = False) -> RollbackResult:
        """Execute the rollback plan."""

    def verify_rollback(self, rollback_operation_id: str) -> RollbackVerification:
        """Verify rollback was completed successfully."""
```

**Usage Example**:
```python
from awsideman.rollback import RollbackProcessor

processor = RollbackProcessor()

# Validate rollback
validation = processor.validate_rollback("abc123-def456-ghi789")
if not validation.is_valid:
    print(f"Rollback not possible: {validation.errors}")
    return

# Generate plan
plan = processor.generate_plan("abc123-def456-ghi789")
print(f"Rollback will perform {len(plan.actions)} actions")

# Execute rollback
result = processor.execute_rollback(plan, dry_run=False)
if result.success:
    print(f"Rollback completed: {result.rollback_operation_id}")
```

### 3. Data Models

**Location**: `src/awsideman/utils/rollback/models.py`

The rollback system uses strongly-typed data models for consistency and validation:

```python
@dataclass
class OperationRecord:
    """Complete record of a permission set operation."""
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

@dataclass
class RollbackPlan:
    """Plan for executing a rollback operation."""
    operation_id: str
    rollback_type: RollbackActionType
    actions: List[RollbackAction]
    estimated_duration: int
    warnings: List[str]

@dataclass
class RollbackAction:
    """Individual action within a rollback plan."""
    principal_id: str
    permission_set_arn: str
    account_id: str
    action_type: RollbackActionType
    current_state: AssignmentState
```

### 4. Storage System

**Location**: `src/awsideman/utils/rollback/storage.py`

The storage system provides persistent operation tracking:

```python
class OperationStore:
    """JSON-based storage for operation records."""

    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.operations_file = self.storage_dir / "operations.json"

    def save_operation(self, operation: OperationRecord) -> None:
        """Save an operation record."""

    def load_operations(self, filters: Optional[Dict] = None) -> List[OperationRecord]:
        """Load operations with optional filtering."""

    def update_operation(self, operation_id: str, updates: Dict[str, Any]) -> None:
        """Update an existing operation record."""
```

## API Reference

### OperationLogger API

#### `log_operation(operation_data: Dict[str, Any]) -> str`

Logs a new operation and returns the generated operation ID.

**Parameters**:
- `operation_data`: Dictionary containing operation details

**Required Fields**:
- `operation_type`: "assign" or "revoke"
- `principal_id`: AWS principal identifier
- `principal_type`: "USER" or "GROUP"
- `principal_name`: Human-readable principal name
- `permission_set_arn`: AWS permission set ARN
- `permission_set_name`: Human-readable permission set name
- `account_ids`: List of affected account IDs
- `account_names`: List of affected account names
- `results`: List of OperationResult objects
- `metadata`: Additional operation metadata

**Returns**: Generated operation ID (UUID)

**Example**:
```python
operation_id = logger.log_operation({
    "operation_type": "assign",
    "principal_id": "user-123456789",
    "principal_type": "USER",
    "principal_name": "john.doe",
    "permission_set_arn": "arn:aws:sso:::permissionSet/ins-123/ps-456",
    "permission_set_name": "ReadOnlyAccess",
    "account_ids": ["123456789012"],
    "account_names": ["Production"],
    "results": [{"account_id": "123456789012", "success": True}],
    "metadata": {"source": "cli", "user": "admin@company.com"}
})
```

#### `get_operations(filters: Optional[Dict] = None) -> List[OperationRecord]`

Retrieves operations with optional filtering.

**Parameters**:
- `filters`: Optional dictionary of filter criteria

**Supported Filters**:
- `operation_type`: Filter by operation type
- `principal_name`: Filter by principal name
- `permission_set_name`: Filter by permission set name
- `days`: Filter by number of days back
- `rolled_back`: Filter by rollback status

**Returns**: List of OperationRecord objects

**Example**:
```python
# Get all operations from last 7 days
recent_ops = logger.get_operations({"days": 7})

# Get assign operations for specific user
user_assigns = logger.get_operations({
    "operation_type": "assign",
    "principal_name": "john.doe"
})
```

### RollbackProcessor API

#### `validate_rollback(operation_id: str) -> RollbackValidation`

Validates whether a rollback is possible for the specified operation.

**Parameters**:
- `operation_id`: ID of the operation to validate

**Returns**: RollbackValidation object with validation results

**Validation Checks**:
- Operation exists
- Operation not already rolled back
- Current AWS state matches expected state
- User has necessary permissions

**Example**:
```python
validation = processor.validate_rollback("abc123-def456-ghi789")
if validation.is_valid:
    print("Rollback is possible")
else:
    print(f"Validation errors: {validation.errors}")
```

#### `generate_plan(operation_id: str) -> RollbackPlan`

Generates a detailed execution plan for rolling back an operation.

**Parameters**:
- `operation_id`: ID of the operation to roll back

**Returns**: RollbackPlan object with execution details

**Plan Contents**:
- List of rollback actions
- Estimated execution time
- Warnings and considerations
- Current state verification

**Example**:
```python
plan = processor.generate_plan("abc123-def456-ghi789")
print(f"Plan contains {len(plan.actions)} actions")
print(f"Estimated duration: {plan.estimated_duration} seconds")
for warning in plan.warnings:
    print(f"Warning: {warning}")
```

#### `execute_rollback(plan: RollbackPlan, dry_run: bool = False) -> RollbackResult`

Executes a rollback plan.

**Parameters**:
- `plan`: RollbackPlan object to execute
- `dry_run`: If True, simulate execution without making changes

**Returns**: RollbackResult object with execution results

**Execution Process**:
1. Pre-execution state verification
2. Parallel execution of rollback actions
3. Post-execution verification
4. Result logging and reporting

**Example**:
```python
# Dry run first
dry_result = processor.execute_rollback(plan, dry_run=True)
if dry_result.success:
    # Execute for real
    result = processor.execute_rollback(plan, dry_run=False)
    print(f"Rollback operation ID: {result.rollback_operation_id}")
```

## Integration Points

### 1. Command Integration

To integrate rollback logging into existing commands:

```python
# In assignment commands
from awsideman.rollback import OperationLogger

def assign_permission_set(principal, permission_set, accounts):
    # Perform assignment
    results = perform_assignment(principal, permission_set, accounts)

    # Log operation for rollback
    logger = OperationLogger()
    operation_data = {
        "operation_type": "assign",
        "principal_id": principal.id,
        "principal_type": principal.type,
        "principal_name": principal.name,
        "permission_set_arn": permission_set.arn,
        "permission_set_name": permission_set.name,
        "account_ids": [acc.id for acc in accounts],
        "account_names": [acc.name for acc in accounts],
        "results": results,
        "metadata": {
            "source": "individual_assign",
            "user": get_current_user()
        }
    }
    operation_id = logger.log_operation(operation_data)

    return operation_id, results
```

### 2. Configuration Integration

Rollback settings are integrated with the main configuration system:

```python
# In config.py
@dataclass
class RollbackConfig:
    enabled: bool = True
    storage_directory: str = "~/.awsideman/operations"
    retention_days: int = 90
    auto_cleanup: bool = True
    max_operations: int = 10000
    confirmation_required: bool = True
    dry_run_default: bool = False

@dataclass
class Config:
    # ... existing config fields
    rollback: RollbackConfig = field(default_factory=RollbackConfig)
```

### 3. Error Handling Integration

Rollback operations use the existing error handling framework:

```python
from awsideman.rollback.exceptions import (
    RollbackError,
    OperationNotFoundError,
    AlreadyRolledBackError,
    StateMismatchError
)

try:
    result = processor.execute_rollback(plan)
except OperationNotFoundError:
    console.print("[red]Operation not found[/red]")
except AlreadyRolledBackError:
    console.print("[yellow]Operation already rolled back[/yellow]")
except StateMismatchError as e:
    console.print(f"[red]State mismatch: {e.message}[/red]")
```

## Extension Guidelines

### Adding New Operation Types

To add support for new operation types:

1. **Extend the OperationType enum**:
```python
class OperationType(str, Enum):
    ASSIGN = "assign"
    REVOKE = "revoke"
    BULK_ASSIGN = "bulk_assign"  # New type
```

2. **Update the RollbackProcessor**:
```python
def _determine_rollback_type(self, operation_type: OperationType) -> RollbackActionType:
    mapping = {
        OperationType.ASSIGN: RollbackActionType.REVOKE,
        OperationType.REVOKE: RollbackActionType.ASSIGN,
        OperationType.BULK_ASSIGN: RollbackActionType.REVOKE,  # New mapping
    }
    return mapping[operation_type]
```

3. **Add validation logic**:
```python
def _validate_operation_type(self, operation: OperationRecord) -> List[str]:
    errors = []
    if operation.operation_type == OperationType.BULK_ASSIGN:
        # Add specific validation for bulk operations
        if len(operation.account_ids) > 50:
            errors.append("Bulk operations with >50 accounts require manual review")
    return errors
```

### Adding New Storage Backends

To add support for new storage backends:

1. **Create a storage backend interface**:
```python
from abc import ABC, abstractmethod

class StorageBackend(ABC):
    @abstractmethod
    def save_operation(self, operation: OperationRecord) -> None:
        pass

    @abstractmethod
    def load_operations(self, filters: Optional[Dict] = None) -> List[OperationRecord]:
        pass
```

2. **Implement the new backend**:
```python
class DynamoDBStorageBackend(StorageBackend):
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)

    def save_operation(self, operation: OperationRecord) -> None:
        # Implementation for DynamoDB storage
        pass
```

3. **Update the OperationLogger**:
```python
class OperationLogger:
    def __init__(self, storage_backend: Optional[StorageBackend] = None):
        if storage_backend is None:
            storage_backend = JSONStorageBackend()
        self.storage = storage_backend
```

### Adding Custom Validation Rules

To add custom validation rules for rollback operations:

1. **Create a validation rule interface**:
```python
class ValidationRule(ABC):
    @abstractmethod
    def validate(self, operation: OperationRecord) -> List[str]:
        """Return list of validation errors."""
        pass
```

2. **Implement custom rules**:
```python
class HighPrivilegeValidationRule(ValidationRule):
    def validate(self, operation: OperationRecord) -> List[str]:
        errors = []
        if "Admin" in operation.permission_set_name:
            if not self._has_admin_approval(operation):
                errors.append("Admin permission rollbacks require approval")
        return errors
```

3. **Register rules with the processor**:
```python
processor = RollbackProcessor()
processor.add_validation_rule(HighPrivilegeValidationRule())
processor.add_validation_rule(BusinessHoursValidationRule())
```

## Testing Framework

### Unit Testing

The rollback system includes comprehensive unit tests:

```python
# tests/utils/rollback/test_operation_logger.py
import pytest
from awsideman.rollback import OperationLogger, OperationRecord

class TestOperationLogger:
    def test_log_operation_creates_record(self):
        logger = OperationLogger()
        operation_data = {
            "operation_type": "assign",
            "principal_id": "user-123",
            # ... other required fields
        }

        operation_id = logger.log_operation(operation_data)

        assert operation_id is not None
        operation = logger.get_operation(operation_id)
        assert operation.operation_type == "assign"
        assert operation.principal_id == "user-123"

    def test_get_operations_with_filters(self):
        logger = OperationLogger()
        # Create test operations

        filtered_ops = logger.get_operations({"operation_type": "assign"})

        assert all(op.operation_type == "assign" for op in filtered_ops)
```

### Integration Testing

Integration tests verify end-to-end rollback workflows:

```python
# tests/integration/test_rollback_workflow.py
class TestRollbackWorkflow:
    def test_assign_and_rollback_cycle(self):
        # Perform assignment
        assignment_result = assign_permission_set(user, permission_set, accounts)

        # Verify assignment was logged
        logger = OperationLogger()
        operations = logger.get_operations({"days": 1})
        assert len(operations) == 1

        # Perform rollback
        processor = RollbackProcessor()
        plan = processor.generate_plan(operations[0].operation_id)
        result = processor.execute_rollback(plan)

        # Verify rollback completed
        assert result.success
        assert result.rollback_operation_id is not None

        # Verify original operation marked as rolled back
        updated_operation = logger.get_operation(operations[0].operation_id)
        assert updated_operation.rolled_back is True
```

### Performance Testing

Performance tests ensure the system scales appropriately:

```python
# tests/performance/test_rollback_performance.py
class TestRollbackPerformance:
    def test_large_operation_rollback(self):
        # Create operation with 100 accounts
        large_operation = create_large_operation(account_count=100)

        processor = RollbackProcessor()

        start_time = time.time()
        plan = processor.generate_plan(large_operation.operation_id)
        plan_time = time.time() - start_time

        start_time = time.time()
        result = processor.execute_rollback(plan, dry_run=True)
        execution_time = time.time() - start_time

        # Assert performance requirements
        assert plan_time < 5.0  # Plan generation under 5 seconds
        assert execution_time < 30.0  # Execution under 30 seconds
```

## Performance Considerations

### 1. Batch Processing

The rollback system uses batch processing for better performance:

```python
class RollbackProcessor:
    def execute_rollback(self, plan: RollbackPlan, batch_size: int = 10) -> RollbackResult:
        """Execute rollback actions in batches."""
        batches = self._create_batches(plan.actions, batch_size)

        for batch in batches:
            # Process batch in parallel
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = [executor.submit(self._execute_action, action) for action in batch]
                results = [future.result() for future in futures]
```

### 2. Caching

Frequently accessed data is cached to improve performance:

```python
from functools import lru_cache

class OperationLogger:
    @lru_cache(maxsize=1000)
    def _get_cached_operation(self, operation_id: str) -> Optional[OperationRecord]:
        """Cache frequently accessed operations."""
        return self._load_operation_from_storage(operation_id)
```

### 3. Async Operations

Long-running operations use async patterns:

```python
import asyncio

class RollbackProcessor:
    async def execute_rollback_async(self, plan: RollbackPlan) -> RollbackResult:
        """Execute rollback asynchronously."""
        tasks = [self._execute_action_async(action) for action in plan.actions]
        results = await asyncio.gather(*tasks)
        return self._compile_results(results)
```

### 4. Storage Optimization

Storage operations are optimized for performance:

```python
class OptimizedStorage:
    def __init__(self):
        self._write_buffer = []
        self._buffer_size = 100

    def save_operation(self, operation: OperationRecord) -> None:
        """Buffer writes for better performance."""
        self._write_buffer.append(operation)
        if len(self._write_buffer) >= self._buffer_size:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Write buffered operations to storage."""
        # Batch write operations
        pass
```

## Security Implementation

### 1. Access Control

Rollback operations respect AWS permissions:

```python
class RollbackProcessor:
    def _verify_permissions(self, action: RollbackAction) -> bool:
        """Verify user has permissions for rollback action."""
        try:
            # Check if user can perform the inverse operation
            if action.action_type == RollbackActionType.REVOKE:
                return self._can_revoke_assignment(action)
            else:
                return self._can_create_assignment(action)
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDenied':
                return False
            raise
```

### 2. Data Protection

Sensitive data is handled securely:

```python
class OperationRecord:
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert to dictionary, optionally excluding sensitive data."""
        data = {
            "operation_id": self.operation_id,
            "timestamp": self.timestamp.isoformat(),
            "operation_type": self.operation_type,
            # ... other fields
        }

        if not include_sensitive:
            # Remove or mask sensitive information
            data["metadata"] = self._mask_sensitive_metadata(self.metadata)

        return data
```

### 3. Audit Trail

All rollback operations are audited:

```python
class AuditLogger:
    def log_rollback_attempt(self, operation_id: str, user: str, success: bool) -> None:
        """Log rollback attempt for audit purposes."""
        audit_entry = {
            "timestamp": datetime.now(timezone.utc),
            "action": "rollback_attempt",
            "operation_id": operation_id,
            "user": user,
            "success": success,
            "source_ip": self._get_source_ip(),
        }
        self._write_audit_log(audit_entry)
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Operation Not Found

**Symptoms**: `OperationNotFoundError` when trying to rollback

**Causes**:
- Incorrect operation ID
- Operation older than retention period
- Storage corruption

**Debugging**:
```python
# Check if operation exists in storage
logger = OperationLogger()
all_ops = logger.get_operations()
matching_ops = [op for op in all_ops if operation_id in op.operation_id]

# Check storage file integrity
import json
with open("~/.awsideman/operations/operations.json") as f:
    data = json.load(f)
    print(f"Total operations in storage: {len(data['operations'])}")
```

#### 2. State Mismatch

**Symptoms**: `StateMismatchError` during rollback validation

**Causes**:
- Manual changes made outside awsideman
- Concurrent operations
- AWS synchronization delays

**Debugging**:
```python
# Compare expected vs actual state
processor = RollbackProcessor()
validation = processor.validate_rollback(operation_id)
for error in validation.errors:
    if "state mismatch" in error.lower():
        print(f"State mismatch detected: {error}")

# Check current AWS state
current_assignments = get_current_assignments(principal_id, account_id)
print(f"Current assignments: {current_assignments}")
```

#### 3. Performance Issues

**Symptoms**: Slow rollback operations

**Causes**:
- Large number of accounts
- AWS API throttling
- Network latency

**Debugging**:
```python
# Enable performance monitoring
import time

class PerformanceMonitor:
    def __init__(self):
        self.metrics = {}

    def time_operation(self, operation_name: str):
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                self.metrics[operation_name] = duration
                return result
            return wrapper
        return decorator

# Use with rollback operations
monitor = PerformanceMonitor()
processor = RollbackProcessor()
processor.execute_rollback = monitor.time_operation("rollback_execution")(processor.execute_rollback)
```

### Diagnostic Tools

#### 1. Storage Validator

```python
def validate_storage_integrity():
    """Validate operation storage integrity."""
    storage_file = Path("~/.awsideman/operations/operations.json")

    if not storage_file.exists():
        print("Storage file does not exist")
        return False

    try:
        with open(storage_file) as f:
            data = json.load(f)

        operations = data.get("operations", [])
        print(f"Found {len(operations)} operations")

        # Validate each operation
        for i, op in enumerate(operations):
            required_fields = ["operation_id", "timestamp", "operation_type"]
            missing_fields = [field for field in required_fields if field not in op]
            if missing_fields:
                print(f"Operation {i} missing fields: {missing_fields}")

        return True
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return False
```

#### 2. System Health Check

```python
def check_rollback_system_health():
    """Comprehensive health check for rollback system."""
    health_status = {
        "storage_accessible": False,
        "aws_connectivity": False,
        "permissions_valid": False,
        "configuration_valid": False
    }

    # Check storage
    try:
        logger = OperationLogger()
        logger.get_operations({"days": 1})
        health_status["storage_accessible"] = True
    except Exception as e:
        print(f"Storage check failed: {e}")

    # Check AWS connectivity
    try:
        import boto3
        client = boto3.client('sso-admin')
        client.list_instances()
        health_status["aws_connectivity"] = True
    except Exception as e:
        print(f"AWS connectivity check failed: {e}")

    # Check configuration
    try:
        config = Config()
        if config.rollback.enabled:
            health_status["configuration_valid"] = True
    except Exception as e:
        print(f"Configuration check failed: {e}")

    return health_status
```

### Logging and Monitoring

#### 1. Structured Logging

```python
import structlog

logger = structlog.get_logger("rollback")

class RollbackProcessor:
    def execute_rollback(self, plan: RollbackPlan) -> RollbackResult:
        logger.info(
            "rollback_started",
            operation_id=plan.operation_id,
            action_count=len(plan.actions),
            estimated_duration=plan.estimated_duration
        )

        try:
            result = self._perform_rollback(plan)
            logger.info(
                "rollback_completed",
                operation_id=plan.operation_id,
                rollback_operation_id=result.rollback_operation_id,
                success=result.success,
                duration=result.duration
            )
            return result
        except Exception as e:
            logger.error(
                "rollback_failed",
                operation_id=plan.operation_id,
                error=str(e),
                error_type=type(e).__name__
            )
            raise
```

#### 2. Metrics Collection

```python
class RollbackMetrics:
    def __init__(self):
        self.metrics = {
            "rollbacks_attempted": 0,
            "rollbacks_successful": 0,
            "rollbacks_failed": 0,
            "average_rollback_duration": 0.0,
            "operations_logged": 0
        }

    def record_rollback_attempt(self, success: bool, duration: float):
        self.metrics["rollbacks_attempted"] += 1
        if success:
            self.metrics["rollbacks_successful"] += 1
        else:
            self.metrics["rollbacks_failed"] += 1

        # Update average duration
        current_avg = self.metrics["average_rollback_duration"]
        total_attempts = self.metrics["rollbacks_attempted"]
        self.metrics["average_rollback_duration"] = (
            (current_avg * (total_attempts - 1) + duration) / total_attempts
        )

    def get_success_rate(self) -> float:
        if self.metrics["rollbacks_attempted"] == 0:
            return 0.0
        return self.metrics["rollbacks_successful"] / self.metrics["rollbacks_attempted"]
```

## Best Practices for Developers

### 1. Error Handling

Always use specific exception types and provide meaningful error messages:

```python
try:
    result = processor.execute_rollback(plan)
except OperationNotFoundError:
    console.print("[red]Operation not found. Check the operation ID.[/red]")
except AlreadyRolledBackError:
    console.print("[yellow]Operation has already been rolled back.[/yellow]")
except StateMismatchError as e:
    console.print(f"[red]Current AWS state doesn't match expected state: {e.details}[/red]")
except RollbackError as e:
    console.print(f"[red]Rollback failed: {e.message}[/red]")
    logger.error("rollback_error", error=str(e), operation_id=plan.operation_id)
```

### 2. Validation

Always validate inputs and state before performing operations:

```python
def execute_rollback(self, operation_id: str) -> RollbackResult:
    # Validate operation ID format
    if not self._is_valid_uuid(operation_id):
        raise ValueError("Invalid operation ID format")

    # Validate operation exists
    operation = self.logger.get_operation(operation_id)
    if not operation:
        raise OperationNotFoundError(f"Operation {operation_id} not found")

    # Validate rollback is possible
    validation = self.validate_rollback(operation_id)
    if not validation.is_valid:
        raise RollbackError(f"Rollback validation failed: {validation.errors}")

    # Proceed with rollback
    plan = self.generate_plan(operation_id)
    return self._execute_plan(plan)
```

### 3. Testing

Write comprehensive tests for all rollback functionality:

```python
class TestRollbackIntegration:
    @pytest.fixture
    def mock_aws_client(self):
        with patch('boto3.client') as mock:
            yield mock

    def test_rollback_with_aws_errors(self, mock_aws_client):
        # Setup mock to simulate AWS errors
        mock_aws_client.return_value.delete_account_assignment.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException'}}, 'DeleteAccountAssignment'
        )

        processor = RollbackProcessor()
        plan = RollbackPlan(...)

        # Should handle throttling gracefully
        result = processor.execute_rollback(plan)
        assert result.success is False
        assert "throttling" in result.error_message.lower()
```

### 4. Documentation

Document all public APIs and provide usage examples:

```python
class RollbackProcessor:
    def validate_rollback(self, operation_id: str) -> RollbackValidation:
        """Validate if a rollback operation is possible.

        This method performs comprehensive validation to ensure that a rollback
        can be safely executed for the specified operation.

        Args:
            operation_id: The UUID of the operation to validate for rollback

        Returns:
            RollbackValidation object containing validation results

        Raises:
            OperationNotFoundError: If the operation ID doesn't exist
            ValueError: If the operation ID format is invalid

        Example:
            >>> processor = RollbackProcessor()
            >>> validation = processor.validate_rollback("abc123-def456-ghi789")
            >>> if validation.is_valid:
            ...     print("Rollback is possible")
            >>> else:
            ...     print(f"Validation errors: {validation.errors}")
        """
```

---

This developer guide provides comprehensive technical documentation for the rollback system. For user-facing documentation, see the [Rollback Operations Guide](ROLLBACK_OPERATIONS.md). For implementation examples, check the [rollback examples directory](../examples/rollback-operations/).
