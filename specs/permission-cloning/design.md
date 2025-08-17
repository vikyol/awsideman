# Permission Cloning Design Document

## Overview

The Permission Cloning feature provides AWS Identity Center administrators with efficient tools to copy permission assignments between users and groups, and clone permission sets. This feature reduces manual configuration effort, ensures consistency across similar roles, and accelerates permission management workflows through both assignment copying and permission set cloning capabilities.

The system supports flexible copying between different entity types (user-to-user, group-to-group, user-to-group, group-to-user), comprehensive permission set cloning, preview functionality, filtering options, and full rollback capabilities.

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Permission Cloning Module                │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Assignment      │  │ Permission Set  │  │ Preview      │ │
│  │ Copier          │  │ Cloner          │  │ Generator    │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Filter Engine   │  │ Rollback        │  │ Validation   │ │
│  │                 │  │ Manager         │  │ Engine       │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Existing Core Services                   │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ AWS Clients     │  │ Cache Layer     │  │ Rollback     │ │
│  │ Manager         │  │                 │  │ System       │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Design Rationale

**Modular Architecture**: The design separates assignment copying from permission set cloning to maintain clear separation of concerns and enable independent testing and maintenance.

**Filter Engine**: A dedicated filtering component allows for flexible, combinable filters without cluttering the core copying logic.

**Preview System**: Preview functionality is implemented as a separate component that can simulate operations without making changes, providing safety and transparency.

**Rollback Integration**: Leverages the existing rollback system to ensure all cloning operations can be undone, maintaining system reliability.

## Components and Interfaces

### Assignment Copier

**Purpose**: Handles copying permission assignments between users and groups.

**Key Methods**:
```python
class AssignmentCopier:
    def copy_assignments(
        self,
        source: EntityReference,
        target: EntityReference,
        filters: Optional[CopyFilters] = None,
        preview: bool = False
    ) -> CopyResult

    def validate_entities(
        self,
        source: EntityReference,
        target: EntityReference
    ) -> ValidationResult

    def get_source_assignments(
        self,
        entity: EntityReference
    ) -> List[PermissionAssignment]
```

**Design Decisions**:
- Uses a unified `EntityReference` type to handle both users and groups seamlessly
- Returns structured `CopyResult` objects for consistent reporting
- Supports both preview and execution modes in the same interface

### Permission Set Cloner

**Purpose**: Handles cloning of permission sets with all their policies and configurations.

**Key Methods**:
```python
class PermissionSetCloner:
    def clone_permission_set(
        self,
        source_name: str,
        target_name: str,
        target_description: Optional[str] = None,
        preview: bool = False
    ) -> CloneResult

    def get_permission_set_config(
        self,
        permission_set_name: str
    ) -> PermissionSetConfig

    def validate_clone_request(
        self,
        source_name: str,
        target_name: str
    ) -> ValidationResult
```

**Design Decisions**:
- Separates configuration retrieval from cloning logic for better testability
- Allows custom descriptions for cloned permission sets while preserving all other settings
- Validates target name availability before attempting to clone

### Filter Engine

**Purpose**: Provides flexible filtering capabilities for copy operations.

**Key Methods**:
```python
class FilterEngine:
    def apply_filters(
        self,
        assignments: List[PermissionAssignment],
        filters: CopyFilters
    ) -> List[PermissionAssignment]

    def validate_filters(
        self,
        filters: CopyFilters
    ) -> ValidationResult
```

**Filter Types**:
- Permission set name inclusion/exclusion
- AWS account ID inclusion/exclusion
- Combinable filters with AND logic

**Design Decisions**:
- Filters are applied as a separate step to maintain clean separation of concerns
- All filters are combinable, providing maximum flexibility
- Filter validation occurs before processing to fail fast on invalid criteria

### Preview Generator

**Purpose**: Generates detailed previews of operations without executing them.

**Key Methods**:
```python
class PreviewGenerator:
    def generate_copy_preview(
        self,
        source: EntityReference,
        target: EntityReference,
        filters: Optional[CopyFilters] = None
    ) -> CopyPreview

    def generate_clone_preview(
        self,
        source_name: str,
        target_name: str
    ) -> ClonePreview
```

**Design Decisions**:
- Preview generation is separate from execution to ensure no side effects
- Previews include conflict detection and duplicate identification
- Structured preview objects enable consistent formatting across different output formats

## Data Models

### Core Data Types

```python
@dataclass
class EntityReference:
    entity_type: EntityType  # USER or GROUP
    entity_id: str
    entity_name: str

@dataclass
class PermissionAssignment:
    permission_set_arn: str
    permission_set_name: str
    account_id: str
    account_name: Optional[str]

@dataclass
class PermissionSetConfig:
    name: str
    description: str
    session_duration: str
    relay_state_url: Optional[str]
    aws_managed_policies: List[str]
    customer_managed_policies: List[CustomerManagedPolicy]
    inline_policy: Optional[str]

@dataclass
class CopyFilters:
    include_permission_sets: Optional[List[str]] = None
    exclude_permission_sets: Optional[List[str]] = None
    include_accounts: Optional[List[str]] = None
    exclude_accounts: Optional[List[str]] = None

@dataclass
class CopyResult:
    source: EntityReference
    target: EntityReference
    assignments_copied: List[PermissionAssignment]
    assignments_skipped: List[PermissionAssignment]
    rollback_id: Optional[str]
    success: bool
    error_message: Optional[str]

@dataclass
class CloneResult:
    source_name: str
    target_name: str
    cloned_config: Optional[PermissionSetConfig]
    rollback_id: Optional[str]
    success: bool
    error_message: Optional[str]
```

**Design Decisions**:
- Dataclasses provide immutable, well-structured data with automatic equality and string representations
- Optional fields accommodate varying AWS configurations
- Rollback IDs are included in all result types to support undo operations
- Separate result types for copy and clone operations maintain type safety

## Error Handling

### Validation Errors
- **Entity Not Found**: Clear error messages when source or target entities don't exist
- **Permission Set Not Found**: Specific error for missing permission sets in clone operations
- **Duplicate Target**: Error when attempting to clone to an existing permission set name
- **Invalid Filters**: Validation errors for malformed filter criteria

### Operation Errors
- **Partial Failures**: Continue processing remaining assignments when individual assignments fail
- **AWS API Errors**: Proper handling and reporting of AWS service errors
- **Permission Errors**: Clear messaging when insufficient permissions prevent operations

### Rollback Errors
- **Rollback Failures**: Detailed logging when rollback operations encounter issues
- **Orphaned Resources**: Detection and reporting of resources that couldn't be cleaned up

**Design Decisions**:
- Fail-fast validation prevents partial operations where possible
- Partial failure handling allows maximum completion of batch operations
- Comprehensive error categorization enables appropriate user messaging and troubleshooting

## Testing Strategy

### Unit Testing
- **Component Isolation**: Each component (AssignmentCopier, PermissionSetCloner, FilterEngine) tested independently
- **Mock AWS Services**: Use mocked AWS clients to test business logic without AWS dependencies
- **Edge Cases**: Test boundary conditions, empty results, and error scenarios
- **Filter Combinations**: Comprehensive testing of all filter combinations and edge cases

### Integration Testing
- **End-to-End Workflows**: Test complete copy and clone operations with real AWS service interactions
- **Rollback Verification**: Verify rollback operations correctly undo changes
- **Cross-Entity Operations**: Test copying between different entity types (user-to-group, etc.)
- **Large Dataset Handling**: Test performance and reliability with large numbers of assignments

### Preview Testing
- **Preview Accuracy**: Verify preview results match actual operation outcomes
- **No Side Effects**: Ensure preview operations don't modify any resources
- **Conflict Detection**: Test preview's ability to identify duplicates and conflicts

**Design Decisions**:
- Separate unit and integration test suites allow for fast feedback during development
- Mock-heavy unit tests enable testing of error conditions that are difficult to reproduce with real AWS services
- Integration tests focus on real-world scenarios and AWS service interactions

## Performance Considerations

### Batch Operations
- **Parallel Processing**: Process multiple assignments concurrently where AWS API limits allow
- **Rate Limiting**: Implement proper rate limiting to avoid AWS API throttling
- **Progress Reporting**: Provide progress updates for long-running operations

### Caching Strategy
- **Entity Resolution**: Cache user and group lookups to avoid repeated API calls
- **Permission Set Details**: Cache permission set configurations during clone operations
- **Account Information**: Cache account names and IDs for better user experience

### Memory Management
- **Streaming Processing**: Process large assignment lists in chunks to manage memory usage
- **Result Pagination**: Handle paginated AWS API responses efficiently

**Design Decisions**:
- Parallel processing improves performance while respecting AWS API constraints
- Caching reduces API calls and improves response times for repeated operations
- Streaming processing ensures the system can handle large-scale operations without memory issues

## Security Considerations

### Permission Validation
- **Source Access**: Verify user has permission to read assignments from source entities
- **Target Access**: Verify user has permission to modify assignments on target entities
- **Permission Set Access**: Verify user has permission to read and create permission sets

### Audit Logging
- **Operation Logging**: Log all copy and clone operations with source, target, and user information
- **Change Tracking**: Integrate with existing rollback system for comprehensive change tracking
- **Sensitive Data**: Avoid logging sensitive policy content while maintaining audit trail

### Data Protection
- **In-Memory Security**: Ensure sensitive configuration data is not persisted unnecessarily
- **API Security**: Use secure AWS API practices and proper credential management

**Design Decisions**:
- Permission validation occurs before any operations to prevent unauthorized access
- Comprehensive audit logging supports compliance and troubleshooting requirements
- Integration with existing security infrastructure maintains consistent security posture
