# Design Document

## Overview

The IDC Status feature provides comprehensive monitoring and health checking capabilities for AWS Identity Center deployments. The system will implement a modular architecture that can check various aspects of Identity Center health, detect orphaned assignments, monitor provisioning operations, and provide flexible output formats for integration with monitoring systems.

## Architecture

The IDC Status feature follows a layered architecture pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Interface Layer                      │
├─────────────────────────────────────────────────────────────┤
│                  Status Command Handler                     │
├─────────────────────────────────────────────────────────────┤
│                    Status Orchestrator                      │
├─────────────────────────────────────────────────────────────┤
│  Health    │ Provisioning │ Orphaned   │ Sync     │ Resource │
│  Checker   │ Monitor      │ Assignment │ Monitor  │ Inspector│
│            │              │ Detector   │          │          │
├─────────────────────────────────────────────────────────────┤
│                    AWS IDC Client Layer                     │
├─────────────────────────────────────────────────────────────┤
│                    Output Formatters                        │
└─────────────────────────────────────────────────────────────┘
```

The architecture separates concerns into distinct layers:
- **CLI Interface**: Handles command parsing and user interaction
- **Command Handler**: Processes status command requests and coordinates responses
- **Status Orchestrator**: Coordinates multiple status checks and aggregates results
- **Status Modules**: Specialized components for different types of status checks
- **AWS Client Layer**: Handles all AWS Identity Center API interactions
- **Output Formatters**: Transform status data into various output formats

## Components and Interfaces

### Status Orchestrator

The central component that coordinates all status checking operations:

```python
class StatusOrchestrator:
    def __init__(self, idc_client: IDCClient):
        self.idc_client = idc_client
        self.health_checker = HealthChecker(idc_client)
        self.provisioning_monitor = ProvisioningMonitor(idc_client)
        self.orphaned_detector = OrphanedAssignmentDetector(idc_client)
        self.sync_monitor = SyncMonitor(idc_client)
        self.resource_inspector = ResourceInspector(idc_client)

    async def get_comprehensive_status(self) -> StatusReport
    async def get_specific_status(self, check_type: str) -> StatusResult
```

### Health Checker

Monitors overall Identity Center instance health:

```python
class HealthChecker:
    async def check_instance_health(self) -> HealthStatus
    async def check_connectivity(self) -> ConnectionStatus
    async def get_service_status(self) -> ServiceStatus
```

### Provisioning Monitor

Tracks user provisioning operations:

```python
class ProvisioningMonitor:
    async def get_active_operations(self) -> List[ProvisioningOperation]
    async def get_failed_operations(self) -> List[FailedOperation]
    async def estimate_completion_times(self) -> Dict[str, datetime]
```

### Orphaned Assignment Detector

Identifies and manages orphaned permission set assignments:

```python
class OrphanedAssignmentDetector:
    async def detect_orphaned_assignments(self) -> List[OrphanedAssignment]
    async def get_assignment_errors(self) -> List[AssignmentError]
    async def cleanup_orphaned_assignments(self, assignments: List[OrphanedAssignment]) -> CleanupResult

    def prompt_for_cleanup(self, orphaned_assignments: List[OrphanedAssignment]) -> bool
```

### Sync Monitor

Monitors synchronization with external identity providers:

```python
class SyncMonitor:
    async def get_sync_status(self) -> List[SyncStatus]
    async def check_sync_health(self) -> SyncHealthReport
    async def get_last_sync_times(self) -> Dict[str, datetime]
```

### Resource Inspector

Provides detailed status for specific resources:

```python
class ResourceInspector:
    async def inspect_user(self, user_id: str) -> UserStatus
    async def inspect_group(self, group_id: str) -> GroupStatus
    async def inspect_permission_set(self, ps_arn: str) -> PermissionSetStatus
    async def get_resource_suggestions(self, resource_name: str) -> List[str]
```

## Data Models

### Core Status Models

```python
@dataclass
class StatusReport:
    timestamp: datetime
    overall_health: HealthStatus
    provisioning_status: ProvisioningStatus
    orphaned_assignments: List[OrphanedAssignment]
    sync_status: List[SyncStatus]
    summary_statistics: SummaryStats

@dataclass
class HealthStatus:
    status: Literal["Healthy", "Warning", "Critical", "Connection Failed"]
    message: str
    details: Dict[str, Any]

@dataclass
class OrphanedAssignment:
    assignment_id: str
    permission_set_arn: str
    permission_set_name: str
    account_id: str
    principal_id: str
    principal_type: str
    error_message: str
    created_date: datetime

@dataclass
class ProvisioningStatus:
    active_operations: List[ProvisioningOperation]
    failed_operations: List[FailedOperation]
    pending_count: int
    estimated_completion: Optional[datetime]

@dataclass
class SummaryStats:
    total_users: int
    total_groups: int
    total_permission_sets: int
    total_assignments: int
    active_accounts: int
    last_updated: datetime
```

### Output Format Models

```python
@dataclass
class FormattedOutput:
    format_type: Literal["table", "json", "csv"]
    content: str
    metadata: Dict[str, Any]
```

## Error Handling

The system implements comprehensive error handling across multiple layers:

### API Error Handling
- **Connection Errors**: Graceful handling of network connectivity issues
- **Authentication Errors**: Clear messaging for credential problems
- **Rate Limiting**: Automatic retry with exponential backoff
- **Service Errors**: Proper interpretation of AWS service error codes

### Data Validation
- **Input Validation**: Validate resource identifiers and command parameters
- **Response Validation**: Ensure API responses contain expected data structures
- **Type Safety**: Use type hints and runtime validation for data integrity

### User Experience
- **Graceful Degradation**: Continue with partial results when some checks fail
- **Clear Error Messages**: Provide actionable error messages with suggested remediation
- **Progress Indication**: Show progress for long-running operations
- **Timeout Handling**: Implement reasonable timeouts with user feedback

## Testing Strategy

### Unit Testing
- **Component Isolation**: Test each status checker component independently
- **Mock AWS APIs**: Use mocked AWS responses for predictable testing
- **Edge Case Coverage**: Test error conditions, empty results, and boundary conditions
- **Data Model Validation**: Verify data structure integrity and transformations

### Integration Testing
- **AWS API Integration**: Test against real AWS Identity Center instances in test environments
- **End-to-End Workflows**: Validate complete status checking workflows
- **Output Format Testing**: Verify all output formats produce correct results
- **Error Scenario Testing**: Test behavior under various error conditions

### Performance Testing
- **Large Dataset Handling**: Test with organizations having thousands of users and assignments
- **Concurrent Operations**: Verify behavior when multiple status checks run simultaneously
- **Memory Usage**: Monitor memory consumption during large data processing
- **Response Time**: Ensure status checks complete within reasonable timeframes

### User Acceptance Testing
- **CLI Interface Testing**: Validate command-line interface usability
- **Output Readability**: Ensure status information is clear and actionable
- **Workflow Testing**: Test common administrator workflows and use cases
- **Documentation Validation**: Verify help text and documentation accuracy

## Implementation Considerations

### Performance Optimization
- **Parallel Processing**: Execute independent status checks concurrently
- **Caching Strategy**: Cache frequently accessed data with appropriate TTL
- **Pagination Handling**: Efficiently process large result sets from AWS APIs
- **Resource Pooling**: Reuse AWS client connections where possible

### Security Considerations
- **Credential Management**: Secure handling of AWS credentials and session tokens
- **Data Sensitivity**: Avoid logging sensitive information in status outputs
- **Access Control**: Respect AWS IAM permissions for status checking operations
- **Audit Trail**: Log status checking activities for security auditing

### Monitoring and Observability
- **Structured Logging**: Implement consistent logging across all components
- **Metrics Collection**: Track status check performance and success rates
- **Health Endpoints**: Provide health check endpoints for the status system itself
- **Alerting Integration**: Support integration with external monitoring systems

### Configuration Management
- **Flexible Configuration**: Support configuration files and environment variables
- **Profile Support**: Integrate with AWS CLI profiles and credential chains
- **Customizable Thresholds**: Allow administrators to configure warning and critical thresholds
- **Output Preferences**: Support user preferences for default output formats
