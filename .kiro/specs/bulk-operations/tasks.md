# Implementation Plan

- [ ] 1. Create bulk command module structure
  - Create the bulk.py command module with basic Typer app setup
  - Add command group integration to main CLI
  - Implement basic command structure following existing patterns
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [ ] 2. Implement file processing components
- [ ] 2.1 Create CSV processor class
  - Implement CSVProcessor class with file validation and parsing
  - Add support for required columns (principal_id, permission_set_arn, account_id)
  - Add support for optional columns (principal_type, principal_name, permission_set_name)
  - Write unit tests for CSV parsing and validation
  - _Requirements: 1.1, 2.1_

- [ ] 2.2 Create JSON processor class
  - Implement JSONProcessor class with schema validation
  - Add JSON schema definition for assignment structure
  - Implement JSON parsing with comprehensive error handling
  - Write unit tests for JSON parsing and validation
  - _Requirements: 3.1, 3.3_

- [ ] 2.3 Create file format detection utility
  - Implement automatic file format detection based on extension
  - Add support for both .csv and .json file extensions
  - Handle format detection errors with clear messages
  - _Requirements: 1.1, 3.1_

- [ ] 3. Implement assignment validation components
- [ ] 3.1 Create assignment validator class
  - Implement AssignmentValidator class for validating individual assignments
  - Add principal validation against Identity Store API
  - Add permission set validation against SSO Admin API
  - Add account ID validation
  - Write unit tests for validation logic
  - _Requirements: 1.3, 1.4, 2.3, 3.3_

- [ ] 3.2 Implement validation caching
  - Add caching for repeated principal and permission set validations
  - Implement cache invalidation strategies
  - Optimize validation performance for large files
  - _Requirements: 1.1, 2.1, 3.1_

- [ ] 4. Implement batch processing engine
- [ ] 4.1 Create batch processor class
  - Implement BatchProcessor class for handling bulk operations
  - Add support for configurable batch sizes
  - Implement parallel processing with proper error isolation
  - Add support for continue-on-error vs stop-on-error modes
  - Write unit tests for batch processing logic
  - _Requirements: 1.2, 1.5, 2.2, 2.4, 3.2, 4.1, 4.2_

- [ ] 4.2 Implement progress tracking
  - Create ProgressTracker class using Rich progress bars
  - Add real-time progress updates during batch processing
  - Implement progress display for different batch sizes
  - Add estimated completion time calculations
  - _Requirements: 4.1_

- [ ] 4.3 Add error handling and retry logic
  - Implement exponential backoff for API rate limiting
  - Add retry logic for transient AWS API errors
  - Handle network errors with appropriate user feedback
  - Implement proper error isolation between batch items
  - _Requirements: 4.2_

- [ ] 5. Implement reporting components
- [ ] 5.1 Create report generator class
  - Implement ReportGenerator class for summary and detailed reports
  - Add support for console output formatting using Rich
  - Create summary report with success/failure counts
  - Implement detailed report with individual assignment results
  - Write unit tests for report generation
  - _Requirements: 1.5, 2.4, 3.4, 4.3_

- [ ] 5.2 Add result tracking data structures
  - Implement AssignmentResult and BulkOperationResults dataclasses
  - Add proper result categorization (successful, failed, skipped)
  - Include error messages and timing information
  - _Requirements: 1.5, 2.4, 3.4, 4.3_

- [ ] 6. Implement bulk assign command
- [ ] 6.1 Create bulk assign command implementation
  - Implement bulk_assign command with all required options
  - Add support for dry-run mode for validation without changes
  - Integrate file processing, validation, and batch processing
  - Add proper error handling and user feedback
  - Write integration tests for assign command
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

- [ ] 6.2 Add assignment operation logic
  - Implement AWS Identity Center assignment API calls
  - Add proper handling of existing assignments
  - Implement assignment creation with error handling
  - Add support for both user and group assignments
  - _Requirements: 1.2, 2.2_

- [ ] 7. Implement bulk revoke command
- [ ] 7.1 Create bulk revoke command implementation
  - Implement bulk_revoke command with all required options
  - Add confirmation prompts with force option override
  - Integrate with existing validation and batch processing
  - Add proper error handling for revoke operations
  - Write integration tests for revoke command
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

- [ ] 7.2 Add revoke operation logic
  - Implement AWS Identity Center revoke API calls
  - Add proper handling of non-existent assignments
  - Implement assignment deletion with error handling
  - Add support for both user and group assignment revocation
  - _Requirements: 1.2, 2.2_

- [ ] 8. Add CLI integration and testing
- [ ] 8.1 Integrate bulk commands into main CLI
  - Add bulk command group to main CLI application
  - Update CLI imports and command registration
  - Ensure consistent help text and parameter naming
  - Test CLI integration with existing commands
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [ ] 8.2 Create comprehensive test suite
  - Write unit tests for all components (file processors, validators, batch processor)
  - Create integration tests for end-to-end workflows
  - Add test fixtures for CSV and JSON input files
  - Test error scenarios and edge cases
  - Add performance tests for large file processing
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3_

- [ ] 9. Add documentation and examples
- [ ] 9.1 Create example input files
  - Create sample CSV files with various assignment scenarios
  - Create sample JSON files with complex assignment structures
  - Add examples for both user and group assignments
  - Include examples with validation errors for testing
  - _Requirements: 1.1, 2.1, 3.1_

- [ ] 9.2 Update help documentation
  - Add comprehensive help text for all bulk commands
  - Include usage examples in command help
  - Document file format requirements and examples
  - Add troubleshooting guidance for common errors
  - _Requirements: 4.4_