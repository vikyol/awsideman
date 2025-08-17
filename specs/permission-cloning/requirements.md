# Requirements Document

## Introduction

This feature enables administrators to efficiently manage AWS Identity Center permissions by copying permission assignments between users or groups and creating new permission sets by cloning existing ones. This capability reduces manual configuration effort, ensures consistency across similar roles, and accelerates permission management workflows.

## Requirements

### Requirement 1

**User Story:** As an AWS Identity Center administrator, I want to use a simple "copy" command to copy permission assignments between users and groups, so that I can quickly replicate access patterns with an intuitive interface.

#### Acceptance Criteria

1. WHEN I use "copy --from user:username --to user:targetuser" THEN the system SHALL copy all permission assignments from the source user to the target user
2. WHEN I use "copy --from group:groupname --to group:targetgroup" THEN the system SHALL copy all permission assignments from the source group to the target group
3. WHEN I use "copy --from user:username --to group:targetgroup" THEN the system SHALL copy all permission assignments from the user to the group
4. WHEN I use "copy --from group:groupname --to user:targetuser" THEN the system SHALL copy all permission assignments from the group to the user
5. WHEN copying permissions THEN the system SHALL preserve the account scope for each permission assignment
6. WHEN copying permissions THEN the system SHALL validate that both source and target entities exist before proceeding
7. IF the target entity already has some of the same permission assignments THEN the system SHALL skip duplicates and report which assignments were skipped
8. WHEN the copy operation completes THEN the system SHALL provide a summary of assignments copied and any skipped duplicates

### Requirement 2

**User Story:** As an AWS Identity Center administrator, I want to use a simple "clone" command to clone permission sets, so that I can create new permission sets based on existing ones with a clear interface.

#### Acceptance Criteria

1. WHEN I use "clone --name sourcepermissionset --to newpermissionset" THEN the system SHALL create a new permission set with identical configuration
2. WHEN cloning a permission set THEN the system SHALL copy all AWS managed policies attached to the source
3. WHEN cloning a permission set THEN the system SHALL copy all customer managed policies attached to the source
4. WHEN cloning a permission set THEN the system SHALL copy all inline policies from the source
5. WHEN cloning a permission set THEN the system SHALL copy the session duration setting from the source
6. WHEN cloning a permission set THEN the system SHALL copy the relay state URL if configured on the source
7. WHEN cloning a permission set THEN the system SHALL allow me to specify a different description for the new permission set using --description
8. IF a permission set with the target name already exists THEN the system SHALL return an error and not proceed

### Requirement 3

**User Story:** As an AWS Identity Center administrator, I want the copy and clone commands to support entity name resolution, so that I can use human-readable names instead of IDs.

#### Acceptance Criteria

1. WHEN I specify "user:username" THEN the system SHALL resolve the username to the corresponding user ID
2. WHEN I specify "group:groupname" THEN the system SHALL resolve the group name to the corresponding group ID
3. WHEN I specify a permission set name THEN the system SHALL resolve it to the corresponding permission set ARN
4. IF an entity name cannot be resolved THEN the system SHALL provide a clear error message indicating which entity was not found
5. WHEN entity resolution fails THEN the system SHALL not proceed with the operation

### Requirement 4

**User Story:** As an AWS Identity Center administrator, I want to preview what will be copied before executing the operation, so that I can verify the changes before they are applied.

#### Acceptance Criteria

1. WHEN I use "--preview" with a copy command THEN the system SHALL show all permission assignments that would be copied
2. WHEN I use "--preview" with a clone command THEN the system SHALL show all policies and settings that would be copied
3. WHEN previewing THEN the system SHALL identify any potential conflicts or duplicates
4. WHEN previewing THEN the system SHALL not make any actual changes to the system
5. WHEN previewing THEN the system SHALL provide clear formatting to distinguish between what will be copied and what will be skipped

### Requirement 5

**User Story:** As an AWS Identity Center administrator, I want to filter which permissions are copied based on specific criteria, so that I can selectively copy only relevant permissions.

#### Acceptance Criteria

1. WHEN copying permissions THEN the system SHALL allow me to filter by specific permission set names
2. WHEN copying permissions THEN the system SHALL allow me to filter by specific AWS account IDs
3. WHEN copying permissions THEN the system SHALL allow me to exclude specific permission sets from the copy operation
4. WHEN copying permissions THEN the system SHALL allow me to exclude specific AWS accounts from the copy operation
5. WHEN using filters THEN the system SHALL apply all specified filters in combination

### Requirement 6

**User Story:** As an AWS Identity Center administrator, I want comprehensive logging and rollback capability for copy and clone operations, so that I can track changes and undo them if necessary.

#### Acceptance Criteria

1. WHEN performing copy or clone operations THEN the system SHALL log all changes made
2. WHEN performing copy or clone operations THEN the system SHALL create rollback information for each change
3. WHEN a copy or clone operation fails partway through THEN the system SHALL provide options to rollback completed changes
4. WHEN I request rollback of a copy operation THEN the system SHALL remove only the assignments that were added during that operation
5. WHEN I request rollback of a clone operation THEN the system SHALL delete the cloned permission set if it was successfully created
