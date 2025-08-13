# Implementation Plan

- [x] 1. Create assignment command module structure
  - Create `src/awsideman/commands/assignment.py` with basic Typer app setup
  - Import required dependencies (typer, rich, boto3 utilities)
  - Set up console, config, and basic command group structure
  - _Requirements: 5.1, 5.2_

- [x] 2. Implement helper functions for assignment operations
- [x] 2.1 Create principal resolution helper function
  - Implement `resolve_principal_info()` to get principal name and type from ID
  - Handle both USER and GROUP principal types
  - Add error handling for invalid principal IDs
  - _Requirements: 1.2, 2.3, 3.3, 4.3_

- [x] 2.2 Create permission set resolution helper function
  - Implement `resolve_permission_set_info()` to get permission set name from ARN
  - Add error handling for invalid permission set ARNs
  - _Requirements: 1.2, 2.3, 3.3, 4.3_

- [x] 3. Implement list assignments command
- [x] 3.1 Create list command structure and parameter validation
  - Define `list_assignments()` command with all required parameters
  - Add optional filtering by account ID, permission set ARN, and principal ID
  - Implement pagination support with limit and next_token parameters
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.1, 5.2_

- [x] 3.2 Implement list assignments API integration
  - Call AWS SSO Admin `list_account_assignments` API
  - Handle API responses and pagination
  - Resolve principal and permission set names for display
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 3.3 Create list assignments output formatting
  - Format results in tabular format using Rich
  - Display permission set name, principal name, principal type, and target account
  - Handle empty results with appropriate messaging
  - _Requirements: 1.1, 1.2, 1.3, 5.2_

- [x] 4. Implement get assignment command
- [x] 4.1 Create get command structure and parameter validation
  - Define `get_assignment()` command with required parameters
  - Validate permission set ARN, principal ID, and account ID parameters
  - _Requirements: 2.1, 2.2, 5.1_

- [x] 4.2 Implement get assignment logic and API integration
  - Check if assignment exists by listing assignments with filters
  - Resolve detailed assignment information including creation date
  - Handle assignment not found scenarios
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 4.3 Create get assignment detailed output formatting
  - Display comprehensive assignment information in panel format
  - Show permission set ARN, principal ID, principal type, account ID, and creation date
  - Include resolved names for user-friendly display
  - _Requirements: 2.1, 2.3, 5.2_

- [x] 5. Implement assign permission set command
- [x] 5.1 Create assign command structure and parameter validation
  - Define `assign_permission_set()` command with required parameters
  - Validate permission set ARN, principal ID, account ID, and principal type
  - Default principal type to USER when not specified
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1_

- [x] 5.2 Implement assign permission set API integration
  - Call AWS SSO Admin `create_account_assignment` API
  - Handle successful assignment creation
  - Check for existing assignments and handle appropriately
  - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [x] 5.3 Create assign command output and confirmation
  - Display confirmation message with assignment details
  - Handle and display appropriate error messages for invalid inputs
  - _Requirements: 3.2, 3.3, 3.5, 5.2_

- [x] 6. Implement revoke assignment command
- [x] 6.1 Create revoke command structure and parameter validation
  - Define `revoke_assignment()` command with required parameters
  - Add force flag for bypassing confirmation prompts
  - Validate all required identifiers
  - _Requirements: 4.1, 4.2, 4.3, 5.1_

- [x] 6.2 Implement revoke assignment confirmation and API integration
  - Add confirmation prompt showing assignment details before revocation
  - Call AWS SSO Admin `delete_account_assignment` API
  - Handle assignment not found scenarios
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 6.3 Create revoke command output formatting
  - Display confirmation message after successful revocation
  - Handle and display appropriate error messages
  - _Requirements: 4.2, 4.3, 4.4, 5.2_

- [x] 7. Integrate assignment commands into main CLI
  - Add assignment command group to `src/awsideman/cli.py`
  - Import assignment module and register with main app
  - Test command group integration and help text
  - _Requirements: 5.1, 5.4_

- [x] 8. Implement comprehensive error handling
- [x] 8.1 Add profile and SSO instance validation
  - Use existing `validate_profile()` and `validate_sso_instance()` helper functions
  - Ensure consistent error handling across all assignment commands
  - _Requirements: 5.3, 5.4_

- [x] 8.2 Add AWS API error handling
  - Handle common AWS API errors (AccessDenied, ResourceNotFound, etc.)
  - Provide clear error messages for insufficient permissions
  - Handle invalid principal, permission set, and account scenarios
  - _Requirements: 1.4, 2.4, 3.5, 4.4, 5.3_

- [-] 9. Create comprehensive unit tests for assignment commands
- [x] 9.1 Create test file structure and fixtures
  - Create `tests/commands/test_assignment_list.py`
  - Create `tests/commands/test_assignment_get.py`
  - Create `tests/commands/test_assignment_assign.py`
  - Create `tests/commands/test_assignment_revoke.py`
  - Set up common test fixtures and mock objects
  - _Requirements: All requirements for testing coverage_

- [x] 9.2 Implement list assignments command tests
  - Test successful list operations with various filters
  - Test pagination handling and empty results
  - Test API error scenarios and error handling
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 9.3 Implement get assignment command tests
  - Test successful get operations with valid identifiers
  - Test assignment not found scenarios
  - Test API error handling and invalid inputs
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 9.4 Implement assign permission set command tests
  - Test successful assignment creation
  - Test duplicate assignment handling
  - Test invalid parameter validation and API errors
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 9.5 Implement revoke assignment command tests
  - Test successful assignment revocation with and without force flag
  - Test confirmation prompt handling
  - Test assignment not found and API error scenarios
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 9.6 Create helper function tests
  - Test principal resolution function with various principal types
  - Test permission set resolution function
  - Test error handling in helper functions
  - _Requirements: 1.2, 2.3, 3.3, 4.3_

- [x] 10. Create integration tests for assignment management
  - Test end-to-end assignment workflows (assign -> list -> get -> revoke)
  - Test integration with AWS Identity Center and Identity Store APIs
  - Test real-world error scenarios and edge cases
  - _Requirements: All requirements for integration testing_
