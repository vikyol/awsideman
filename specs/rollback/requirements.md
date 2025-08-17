# Requirements Document

## Introduction

The awsideman tool manages permission assignments in AWS IAM Identity Center across users, groups, accounts, and permission sets. As the tool expands to support bulk operations and templates, the risk of unintended permission changes increases. A rollback capability is required to make these operations safer and reversible.

This feature introduces operation tracking and rollback commands, allowing users to undo specific permission set assignments or revocations made by previous CLI operations.

## Requirements

### Requirement 1

**User Story:** As a CLI user, I want every permission set assignment or revocation to be logged so that I can review or revert the changes later.

#### Acceptance Criteria

1. WHEN a bulk assignment or revocation operation is executed THEN the system SHALL store a log of the operation in a persistent audit file (e.g., JSON or SQLite DB)
2. WHEN an operation is logged THEN each operation record SHALL include:
   - Timestamp
   - Operation ID
   - Type (assign or revoke)
   - Target principal (user/group ID)
   - Permission set ID or name
   - Affected account IDs
   - Result of each assignment (success/failure)
3. WHEN an operation is created THEN the system SHALL tag each operation with a unique ID (UUID)
4. WHEN storing operation logs THEN the system SHALL support storing logs in a dedicated directory (e.g. .awsideman/operations/)

### Requirement 2

**User Story:** As a user, I want to view a list of recent permission assignment operations so I can understand what has changed and decide what to roll back.

#### Acceptance Criteria

1. WHEN I run `awsideman rollback list` THEN the CLI SHALL show a list of recent operations with:
   - Operation ID
   - Timestamp
   - Type (assign or revoke)
   - Subject (user/group)
   - Permission set
   - Number of accounts affected
2. WHEN displaying operation lists THEN the output SHALL be available in both table and JSON formats
3. WHEN listing operations THEN the list SHALL be filterable by:
   - Operation type
   - Subject
   - Permission set
   - Date range

### Requirement 3

**User Story:** As a user, I want to roll back a specific operation by ID so I can undo a permission assignment or revocation that was incorrect or unintended.

#### Acceptance Criteria

1. WHEN I need to rollback an operation THEN the CLI SHALL support `awsideman rollback apply <operation-id>`
2. IF the original operation was assign THEN the rollback SHALL perform the inverse revoke action for the same accounts and subject
3. IF the original operation was revoke THEN the rollback SHALL re-assign the same permission set to the same subject and accounts
4. WHEN executing a rollback operation THEN the system SHALL:
   - Log a new rollback record with a new operation ID
   - Skip any already-rolled-back or unchanged entries
   - Support --dry-run to simulate the rollback
5. WHEN executing a rollback THEN the system SHALL confirm with the user before executing rollback unless --yes is provided

### Requirement 4

**User Story:** As a user, I want rollback to be reliable and consistent, so that I don't accidentally reapply or remove wrong permissions.

#### Acceptance Criteria

1. WHEN performing a rollback THEN the system SHALL check for conflicting or missing state before executing (e.g., already revoked)
2. WHEN a rollback is executed multiple times THEN rollback SHALL be idempotent — running it multiple times should not cause further change
3. WHEN partial failures occur THEN they SHALL be reported clearly, and retried operations SHALL be supported
4. WHEN executing a rollback THEN it SHALL never remove unrelated permissions

## Future Considerations (Out of Scope for Initial Version)

- Rollback previews in graphical diff format
- Undo chains (e.g., revert N levels back)
- Version control integration for template-backed permissions
- Manual rollback plan authoring
