# Implementation Plan

- [x] 1. Create permission set command module structure
  - Create `src/awsideman/commands/permission_set.py` with basic Typer app setup
  - Import necessary dependencies (typer, boto3, rich, etc.)
  - Set up console and config instances following existing patterns
  - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 2. Implement helper functions for permission set operations
  - [x] 2.1 Create permission set identifier resolution helper
    - Write function to determine if identifier is ARN or name
    - Implement name-to-ARN lookup functionality using ListPermissionSets API
    - Add error handling for non-existent permission sets
    - _Requirements: 2.2, 2.3, 4.1, 5.1_

  - [x] 2.2 Create permission set validation and formatting helpers
    - Write function to validate permission set names and descriptions
    - Create helper to format permission set data for display
    - Implement AWS-managed policy ARN validation
    - _Requirements: 3.2, 3.4, 4.2, 4.3, 6.2, 6.3_

- [x] 3. Implement permission set list command
  - [x] 3.1 Create list_permission_sets function with basic structure
    - Set up command signature with filter, limit, next_token, and profile parameters
    - Implement profile and SSO instance validation using existing helpers
    - Add AWS client initialization following existing patterns
    - _Requirements: 1.1, 1.5, 1.6_

  - [x] 3.2 Implement ListPermissionSets API integration
    - Call ListPermissionSets API with proper parameters
    - Handle pagination with NextToken support
    - Implement filtering by permission set attributes
    - Add limit parameter support for result count control
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 3.3 Add permission set details retrieval for list display
    - Call DescribePermissionSet for each permission set to get details
    - Format permission set data into table structure
    - Handle API errors and display appropriate messages
    - _Requirements: 1.1, 6.1, 6.4_

  - [x] 3.4 Implement interactive pagination for list command
    - Add Rich table formatting for permission set display
    - Implement interactive pagination similar to user list command
    - Add support for manual pagination with next-token parameter
    - _Requirements: 1.3, 1.4_

- [x] 4. Implement permission set get command
  - [x] 4.1 Create get_permission_set function structure
    - Set up command signature with identifier and profile parameters
    - Implement identifier resolution (name vs ARN)
    - Add profile and SSO instance validation
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 4.2 Implement DescribePermissionSet API integration
    - Call DescribePermissionSet API with resolved permission set ARN
    - Handle ResourceNotFoundException for non-existent permission sets
    - Add comprehensive error handling for API responses
    - _Requirements: 2.1, 2.4, 6.1_

  - [x] 4.3 Add managed policy retrieval for permission set details
    - Call ListManagedPoliciesInPermissionSet API
    - Format managed policy information for display
    - Create Rich panel display for detailed permission set information
    - _Requirements: 2.1, 6.1_

- [x] 5. Implement permission set create command
  - [x] 5.1 Create create_permission_set function structure
    - Set up command signature with name, description, session_duration, relay_state, managed_policy, and profile parameters
    - Implement input validation for required and optional parameters
    - Add profile and SSO instance validation
    - _Requirements: 3.1, 3.2, 3.3, 3.7_

  - [x] 5.2 Implement CreatePermissionSet API integration
    - Call CreatePermissionSet API with validated parameters
    - Handle ConflictException for duplicate permission set names
    - Add comprehensive error handling and validation
    - _Requirements: 3.1, 3.5, 3.6, 6.1, 6.2_

  - [x] 5.3 Add AWS-managed policy attachment during creation
    - Call AttachManagedPolicyToPermissionSet for each provided policy ARN
    - Validate AWS-managed policy ARNs before attachment
    - Handle policy attachment errors appropriately
    - _Requirements: 3.4, 6.3_

  - [x] 5.4 Display created permission set details
    - Retrieve full permission set details after creation
    - Format and display created permission set information
    - Show attached managed policies in the output
    - _Requirements: 3.6_

- [x] 6. Implement permission set update command
  - [x] 6.1 Create update_permission_set function structure
    - Set up command signature with identifier, description, session_duration, relay_state, add_managed_policy, remove_managed_policy, and profile parameters
    - Implement identifier resolution and validation
    - Add profile and SSO instance validation
    - _Requirements: 4.1, 4.6_

  - [x] 6.2 Implement UpdatePermissionSet API integration
    - Call UpdatePermissionSet API for modifiable attributes
    - Handle ResourceNotFoundException for non-existent permission sets
    - Validate and update description, session duration, and relay state
    - _Requirements: 4.1, 4.2, 4.4, 6.1_

  - [x] 6.3 Add managed policy attachment and detachment
    - Call AttachManagedPolicyToPermissionSet for policies to add
    - Call DetachManagedPolicyFromPermissionSet for policies to remove
    - Validate policy ARNs before attachment/detachment operations
    - Handle policy management errors appropriately
    - _Requirements: 4.3, 6.3_

  - [x] 6.4 Display updated permission set details
    - Retrieve full permission set details after update
    - Format and display updated permission set information
    - Show current managed policies in the output
    - _Requirements: 4.5_

- [x] 7. Implement permission set delete command
  - [x] 7.1 Create delete_permission_set function structure
    - Set up command signature with identifier and profile parameters
    - Implement identifier resolution and validation
    - Add profile and SSO instance validation
    - _Requirements: 5.1, 5.4_

  - [x] 7.2 Implement DeletePermissionSet API integration
    - Call DeletePermissionSet API with resolved permission set ARN
    - Handle ResourceNotFoundException for non-existent permission sets
    - Add comprehensive error handling for deletion failures
    - _Requirements: 5.1, 5.2, 6.1_

  - [x] 7.3 Add deletion confirmation and success messaging
    - Display confirmation message upon successful deletion
    - Handle and display appropriate error messages for failures
    - _Requirements: 5.3_

- [x] 8. Integrate permission set commands into CLI
  - Add permission_set import to cli.py
  - Register permission-set command group with main Typer app
  - Test command registration and help text display
  - _Requirements: All requirements - CLI integration_

- [x] 9. Create comprehensive test suite for permission set list command
  - [x] 9.1 Create test_permission_set_list.py with basic test structure
    - Set up test fixtures for mock AWS clients and sample data
    - Create tests for successful list operations with various parameters
    - Add tests for pagination handling and filtering
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 9.2 Add error handling tests for list command
    - Test API error handling and display
    - Test profile and SSO instance validation failures
    - Test network error scenarios
    - _Requirements: 6.1, 6.4, 6.5_

- [x] 10. Create comprehensive test suite for permission set get command
  - [x] 10.1 Create test_permission_set_get.py with basic test structure
    - Set up test fixtures for mock AWS clients and sample permission set data
    - Create tests for successful get operations by name and ARN
    - Add tests for identifier resolution functionality
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 10.2 Add error handling tests for get command
    - Test ResourceNotFoundException handling
    - Test invalid identifier scenarios
    - Test API error handling and display
    - _Requirements: 2.4, 6.1_

- [x] 11. Create comprehensive test suite for permission set create command
  - [x] 11.1 Create test_permission_set_create.py with basic test structure
    - Set up test fixtures for mock AWS clients and sample data
    - Create tests for successful create operations with various parameters
    - Add tests for managed policy attachment during creation
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 11.2 Add validation and error handling tests for create command
    - Test duplicate name handling
    - Test input validation for required and optional parameters
    - Test API error handling and display
    - _Requirements: 3.5, 6.1, 6.2, 6.3_

- [x] 12. Create comprehensive test suite for permission set update command
  - [x] 12.1 Create test_permission_set_update.py with basic test structure
    - Set up test fixtures for mock AWS clients and sample data
    - Create tests for successful update operations with various parameters
    - Add tests for managed policy addition and removal
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 12.2 Add error handling tests for update command
    - Test ResourceNotFoundException handling
    - Test invalid parameter scenarios
    - Test policy attachment/detachment error handling
    - _Requirements: 4.4, 6.1, 6.3_

- [x] 13. Create comprehensive test suite for permission set delete command
  - [x] 13.1 Create test_permission_set_delete.py with basic test structure
    - Set up test fixtures for mock AWS clients
    - Create tests for successful delete operations
    - Add tests for identifier resolution in delete context
    - _Requirements: 5.1_

  - [x] 13.2 Add error handling tests for delete command
    - Test ResourceNotFoundException handling
    - Test API error scenarios for deletion failures
    - Test confirmation message display
    - _Requirements: 5.2, 5.3, 6.1_

- [x] 14. Create helper function tests
  - Create test_permission_set_helpers.py for shared utility functions
  - Test identifier resolution helper functions
  - Test validation and formatting helper functions
  - Test error handling in helper functions
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 15. Add integration testing and documentation
  - [x] 15.1 Create integration tests for end-to-end workflows
    - Test complete permission set lifecycle (create, get, update, delete)
    - Test command chaining and data consistency
    - Test error recovery scenarios
    - _Requirements: All requirements - integration testing_

  - [x] 15.2 Update CLI help documentation and examples
    - Add comprehensive help text for all commands
    - Include usage examples in command descriptions
    - Update main CLI help to include permission-set commands
    - _Requirements: All requirements - user experience_
