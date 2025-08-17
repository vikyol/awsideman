# Requirements Document

## Introduction

The Permission Set Management feature for awsideman CLI will enable administrators to manage permission sets within AWS Identity Center. This feature will provide commands to list, get, create, update, and delete permissions sets in the Identity Store. It will follow the same command structure and user experience as the existing profile and SSO commands, providing a consistent interface for managing AWS Identity Center resources.

The first phase of the project only involves assigning AWS-managed roles to the permission sets during creation or update.

## Requirements

### Requirement 1: Permission Set Listing

**User Story:** As an AWS administrator, I want to list all permission sets in the Identity Center, so that I can view and manage the permission sets in my organization.

#### Acceptance Criteria

1. WHEN the user runs the 'permission-set list' command THEN the system SHALL display a table of all permission sets with their names, ARNs, and descriptions.
2. WHEN the user provides a filter parameter THEN the system SHALL filter permission sets based on the specified attribute.
3. WHEN there are more permission sets than can fit in a single page THEN the system SHALL support pagination.
4. WHEN the user specifies a limit parameter THEN the system SHALL limit the number of permission sets returned.
5. WHEN the user specifies a profile THEN the system SHALL use that profile's credentials and Identity Center instance ARN.
6. WHEN no profile is specified THEN the system SHALL use the default profile if available.

### Requirement 2: Permission Set Details

**User Story:** As an AWS administrator, I want to get detailed information about a specific permission set, so that I can understand its configuration and assigned policies.

#### Acceptance Criteria

1. WHEN the user runs the 'permission-set get' command with a permission set identifier THEN the system SHALL display detailed information about that permission set.
2. WHEN the user provides a permission set name THEN the system SHALL search for the permission set by name.
3. WHEN the user provides a permission set ARN THEN the system SHALL look up the permission set directly by ARN.
4. WHEN the specified permission set does not exist THEN the system SHALL display an appropriate error message.
5. WHEN the user specifies a profile THEN the system SHALL use that profile's credentials and Identity Center instance ARN.

### Requirement 3: Permission Set Creation

**User Story:** As an AWS administrator, I want to create new permission sets in the Identity Center, so that I can define access levels for users and groups.

#### Acceptance Criteria

1. WHEN the user runs the 'permission-set create' command with required parameters THEN the system SHALL create a new permission set in the Identity Center.
2. WHEN creating a permission set THEN the system SHALL require a permission set name.
3. WHEN creating a permission set THEN the system SHALL allow an optional description.
4. WHEN creating a permission set THEN the system SHALL allow specifying an AWS-managed policy ARN.
5. WHEN a permission set with the same name already exists THEN the system SHALL display an appropriate error message.
6. WHEN the permission set is created successfully THEN the system SHALL display the details of the new permission set.
7. WHEN the user specifies a profile THEN the system SHALL use that profile's credentials and Identity Center instance ARN.

### Requirement 4: Permission Set Update

**User Story:** As an AWS administrator, I want to update existing permission sets in the Identity Center, so that I can modify their properties and assigned policies as needed.

#### Acceptance Criteria

1. WHEN the user runs the 'permission-set update' command with a permission set identifier THEN the system SHALL update the specified permission set.
2. WHEN updating a permission set THEN the system SHALL allow modifying the permission set's description.
3. WHEN updating a permission set THEN the system SHALL allow adding or removing AWS-managed policies.
4. WHEN the specified permission set does not exist THEN the system SHALL display an appropriate error message.
5. WHEN the permission set is updated successfully THEN the system SHALL display the updated permission set details.
6. WHEN the user specifies a profile THEN the system SHALL use that profile's credentials and Identity Center instance ARN.

### Requirement 5: Permission Set Deletion

**User Story:** As an AWS administrator, I want to delete permission sets from the Identity Center, so that I can remove permission sets that are no longer needed.

#### Acceptance Criteria

1. WHEN the user runs the 'permission-set delete' command with a permission set identifier THEN the system SHALL delete the specified permission set.
2. WHEN the specified permission set does not exist THEN the system SHALL display an appropriate error message.
3. WHEN the permission set is deleted successfully THEN the system SHALL display a confirmation message.
4. WHEN the user specifies a profile THEN the system SHALL use that profile's credentials and Identity Center instance ARN.

### Requirement 6: Error Handling and Validation

**User Story:** As an AWS administrator, I want clear error messages and input validation, so that I can troubleshoot issues and provide correct inputs.

#### Acceptance Criteria

1. WHEN any command fails due to AWS API errors THEN the system SHALL display the error code and message.
2. WHEN required parameters are missing THEN the system SHALL prompt the user or display a helpful error message.
3. WHEN input validation fails THEN the system SHALL explain why the input is invalid.
4. WHEN the user lacks necessary permissions THEN the system SHALL display a clear permissions-related error message.
5. WHEN the system encounters network issues THEN the system SHALL provide appropriate error handling and retry mechanisms.
