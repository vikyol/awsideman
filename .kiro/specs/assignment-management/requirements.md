# Requirements Document

## Introduction

The Permission Set assignment management feature for awsideman CLI will enable administrators to assign or revoke permission sets to principals within AWS Identity Center. This feature will provide commands to list, get, assign and revoke permissions sets assignments in the Identity Store. It will follow the same command structure and user experience as the existing profile and SSO commands, providing a consistent interface for managing AWS Identity Center resources.

## Requirements

### Requirement 1

**User Story:** As an AWS administrator, I want to list all permission set assignments, so that I can see which permission sets are assigned to which principals and accounts.

#### Acceptance Criteria

1. WHEN the user runs the list assignments command THEN the system SHALL display all permission set assignments in a tabular format
2. WHEN displaying assignments THEN the system SHALL show permission set name, principal name, principal type, and target account
3. WHEN no assignments exist THEN the system SHALL display an appropriate message indicating no assignments found
4. WHEN the API call fails THEN the system SHALL display a clear error message

### Requirement 2

**User Story:** As an AWS administrator, I want to get details of a specific permission set assignment, so that I can view comprehensive information about a particular assignment.

#### Acceptance Criteria

1. WHEN the user provides a valid assignment identifier THEN the system SHALL display detailed assignment information
2. WHEN the assignment identifier is invalid THEN the system SHALL display an error message indicating the assignment was not found
3. WHEN displaying assignment details THEN the system SHALL show permission set ARN, principal ID, principal type, account ID, and creation date
4. WHEN the API call fails THEN the system SHALL display a clear error message

### Requirement 3

**User Story:** As an AWS administrator, I want to assign a permission set to a principal for a specific account, so that I can grant the necessary permissions for that principal to access AWS resources.

#### Acceptance Criteria

1. WHEN the user provides valid permission set, principal, and account identifiers THEN the system SHALL create the assignment
2. WHEN the assignment is successful THEN the system SHALL display a confirmation message
3. WHEN the permission set, principal, or account is invalid THEN the system SHALL display an appropriate error message
4. WHEN the assignment already exists THEN the system SHALL display a message indicating the assignment already exists
5. WHEN the API call fails THEN the system SHALL display a clear error message

### Requirement 4

**User Story:** As an AWS administrator, I want to revoke a permission set assignment from a principal, so that I can remove access when it's no longer needed.

#### Acceptance Criteria

1. WHEN the user provides valid assignment identifiers THEN the system SHALL remove the assignment
2. WHEN the revocation is successful THEN the system SHALL display a confirmation message
3. WHEN the assignment does not exist THEN the system SHALL display an error message indicating the assignment was not found
4. WHEN the API call fails THEN the system SHALL display a clear error message

### Requirement 5

**User Story:** As an AWS administrator, I want the assignment commands to follow the same CLI patterns as other awsideman commands, so that I have a consistent user experience.

#### Acceptance Criteria

1. WHEN using assignment commands THEN the system SHALL follow the same command structure as existing commands (list, get, assign, revoke)
2. WHEN displaying output THEN the system SHALL use consistent formatting and styling with other commands
3. WHEN handling errors THEN the system SHALL use the same error handling patterns as existing commands
4. WHEN providing help THEN the system SHALL display usage information in the same format as other commands
