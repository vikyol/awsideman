# Design Document

## Overview

The rollback feature adds operation tracking and rollback capabilities to awsideman, enabling users to safely undo permission set assignments and revocations. This feature integrates with the existing CLI architecture and leverages established patterns for configuration, logging, and error handling.

The design follows the existing awsideman patterns:
- Typer-based CLI commands with rich console output
- Configuration management through the Config class
- AWS client management through AWSClientManager
- Structured logging and error handling
- Async batch processing for performance

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Layer                                │
├─────────────────────────────────────────────────────────────────┤
│  rollback.py (Typer commands)                                  │
│  ├── list    - List historical operations                      │
│  ├── apply   - Apply rollback for operation                    │
│  └── status  - Show rollback status                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Operation Tracking                          │
├─────────────────────────────────────────────────────────────────┤
│  OperationLogger                                               │
│  ├── log_operation()    - Record operation details             │
│  ├── get_operations()   - Retrieve operation history           │
│  └── mark_rolled_back() - Mark operation as rolled back        │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Rollback Engine                             │
├─────────────────────────────────────────────────────────────────┤
│  RollbackProcessor                                             │
│  ├── validate_rollback()  - Check rollback feasibility        │
│  ├── generate_plan()      - Create rollback execution plan     │
│  ├── execute_rollback()   - Perform rollback operations        │
│  └── verify_rollback()    - Verify rollback completion         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Storage Layer                               │
├─────────────────────────────────────────────────────────────────┤
│  OperationStore (JSON-based)                                  │
│  ├── ~/.awsideman/operations/                                 │
│  ├── operations.json       - Operation records                │
│  └── rollbacks.json        - Rollback records                 │
└─────────────────────────────────────────────────────────────────┘
```

### Integration Points

The rollback feature integrates with existing awsideman components:

1. **Bulk Operations**: Modify `bulk.py` to call `OperationLogger` after successful operations
2. **Assignment Commands**: Modify `assignment.py` to log individual assignment operations
3. **Configuration**: Extend `Config` class to support rollback-specific settings
4. **AWS Clients**: Use existing `AWSClientManager` for AWS API calls
5. **Error Handling**: Leverage existing error handling patterns

## Components and Interfaces

### OperationLogger

Responsible for tracking all permission set operations in a persistent store.

```python
class OperationRecord:
    operation_id: str
    timestamp: datetime
    operation_type: str  # "assign" or "revoke"
    principal_id: str
    principal_type: str  # "USER" or "GROUP"
    principal_name: str
    permission_set_arn: str
    permission_set_name: str
    account_ids: List[str]
    account_names: List[str]
    results: List[OperationResult]
    metadata: Dict[str, Any]
    rolled_back: bool = False
    rollback_operation_id: Optional[str] = None

class OperationLogger:
    def log_operation(self, operation_data: Dict[str, Any]) -> str
    def get_operations(self, filters: Optional[Dict] = None) -> List[OperationRecord]
    def get_operation(self, operation_id: str) -> Optional[OperationRecord]
    def mark_rolled_back(self, operation_id: str, rollback_operation_id: str) -> None
    def cleanup_old_operations(self, days: int = 90) -> None
```

### RollbackProcessor

Handles the rollback logic and execution.

```python
class RollbackPlan:
    operation_id: str
    rollback_type: str  # "assign" or "revoke"
    actions: List[RollbackAction]
    estimated_duration: int
    warnings: List[str]

class RollbackAction:
    principal_id: str
    permission_set_arn: str
    account_id: str
    action_type: str  # "assign" or "revoke"
    current_state: str  # "assigned", "not_assigned", "unknown"

class RollbackProcessor:
    def validate_rollback(self, operation_id: str) -> RollbackValidation
    def generate_plan(self, operation_id: str) -> RollbackPlan
    def execute_rollback(self, plan: RollbackPlan, dry_run: bool = False) -> RollbackResult
    def verify_rollback(self, rollback_operation_id: str) -> RollbackVerification
```

### CLI Commands

Following the existing awsideman CLI patterns with Typer:

```python
# src/awsideman/commands/rollback.py
app = typer.Typer(help="Rollback permission set operations")

@app.command("list")
def list_operations(
    operation_type: Optional[str] = None,
    principal: Optional[str] = None,
    permission_set: Optional[str] = None,
    days: int = 30,
    format: str = "table"
) -> None: ...

@app.command("apply")
def apply_rollback(
    operation_id: str,
    dry_run: bool = False,
    yes: bool = False,
    batch_size: int = 10
) -> None: ...
```

## Data Models

### Operation Storage Schema

Operations are stored in JSON format in `~/.awsideman/operations/operations.json`:

```json
{
  "operations": [
    {
      "operation_id": "uuid-string",
      "timestamp": "2024-01-15T10:30:00Z",
      "operation_type": "assign",
      "principal_id": "user-id",
      "principal_type": "USER",
      "principal_name": "john.doe",
      "permission_set_arn": "arn:aws:sso:::permissionSet/...",
      "permission_set_name": "ReadOnlyAccess",
      "account_ids": ["123456789012"],
      "account_names": ["Production"],
      "results": [
        {
          "account_id": "123456789012",
          "success": true,
          "error": null,
          "duration_ms": 1500
        }
      ],
      "metadata": {
        "source": "bulk_assign",
        "input_file": "assignments.csv",
        "batch_size": 10,
        "profile": "default"
      },
      "rolled_back": false,
      "rollback_operation_id": null
    }
  ]
}
```

### Configuration Extensions

Extend the existing Config class to support rollback settings:

```yaml
# ~/.awsideman/config.yaml
rollback:
  enabled: true
  storage_directory: "~/.awsideman/operations"
  retention_days: 90
  auto_cleanup: true
  max_operations: 10000
  confirmation_required: true
  dry_run_default: false
```

## Error Handling

### Rollback Validation Errors

- **Operation Not Found**: Operation ID doesn't exist in the log
- **Already Rolled Back**: Operation has already been rolled back
- **Partial Rollback**: Some assignments in the operation cannot be rolled back
- **State Mismatch**: Current AWS state doesn't match expected state for rollback

### Rollback Execution Errors

- **AWS API Errors**: Rate limiting, permission errors, service unavailability
- **Concurrent Modifications**: Another process modified assignments during rollback
- **Partial Failures**: Some rollback actions succeed while others fail

### Error Recovery

- **Retry Logic**: Automatic retry for transient AWS API errors
- **Partial Rollback Handling**: Continue with remaining actions when some fail
- **State Verification**: Verify actual AWS state before and after rollback
- **Rollback Logging**: Log all rollback attempts and results

## Testing Strategy

### Unit Tests

- **OperationLogger**: Test operation logging, retrieval, and filtering
- **RollbackProcessor**: Test rollback validation, planning, and execution
- **CLI Commands**: Test command parsing, validation, and output formatting
- **Data Models**: Test serialization, deserialization, and validation

### Integration Tests

- **End-to-End Rollback**: Test complete assign → rollback → verify cycle
- **Bulk Operation Integration**: Test rollback of bulk operations
- **AWS API Integration**: Test with real AWS Identity Center (using test accounts)
- **Error Scenarios**: Test handling of various error conditions

### Performance Tests

- **Large Operation Rollback**: Test rollback of operations with many assignments
- **Operation History Performance**: Test performance with large operation history
- **Concurrent Rollback**: Test handling of concurrent rollback operations

## Security Considerations

### Operation Log Security

- **Sensitive Data**: Avoid logging sensitive information (tokens, credentials)
- **Access Control**: Ensure operation logs are only accessible to the user
- **Data Retention**: Implement automatic cleanup of old operation logs

### Rollback Authorization

- **AWS Permissions**: Verify user has necessary permissions for rollback operations
- **Operation Ownership**: Ensure users can only rollback their own operations
- **Confirmation Requirements**: Require explicit confirmation for destructive operations

### Audit Trail

- **Rollback Logging**: Log all rollback operations for audit purposes
- **Change Tracking**: Track who performed rollbacks and when
- **Compliance**: Support compliance requirements for permission change tracking

## Performance Considerations

### Operation Logging Performance

- **Async Logging**: Log operations asynchronously to avoid blocking main operations
- **Batch Logging**: Log multiple operations in batches for better performance
- **Storage Optimization**: Use efficient JSON storage with compression

### Rollback Execution Performance

- **Parallel Processing**: Execute rollback actions in parallel where possible
- **Batch Operations**: Use AWS batch APIs for better performance
- **Progress Tracking**: Provide real-time progress updates for long-running rollbacks

### Storage Management

- **Log Rotation**: Automatically rotate and compress old operation logs
- **Storage Limits**: Implement configurable limits on operation log storage
- **Cleanup Scheduling**: Schedule automatic cleanup of old operations

## Migration and Deployment

### Backward Compatibility

- **Existing Operations**: Don't break existing awsideman functionality
- **Configuration Migration**: Automatically migrate existing configurations
- **CLI Compatibility**: Maintain compatibility with existing CLI usage patterns

### Rollout Strategy

1. **Phase 1**: Implement operation logging without rollback functionality
2. **Phase 2**: Add rollback commands and basic rollback functionality
3. **Phase 3**: Add advanced features (filtering, bulk rollback, etc.)
4. **Phase 4**: Add performance optimizations and advanced error handling

### Configuration Management

- **Default Settings**: Provide sensible defaults for all rollback settings
- **Environment Variables**: Support environment variable overrides
- **Profile-Specific Settings**: Allow different rollback settings per AWS profile
