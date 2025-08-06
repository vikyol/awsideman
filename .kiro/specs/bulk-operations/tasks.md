# Implementation Plan

- [x] 1. Create bulk command module structure
  - Create the bulk.py command module with basic Typer app setup
  - Add command group integration to main CLI
  - Implement basic command structure following existing patterns
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [x] 2. Implement file processing components
- [x] 2.1 Create CSV processor class
  - Implement CSVProcessor class with file validation and parsing
  - Add support for required columns (principal_name, permission_set_name, account_name)
  - Add support for optional columns (principal_type, account_id, permission_set_arn, principal_id)
  - Write unit tests for CSV parsing and validation
  - _Requirements: 1.1, 2.1_

- [x] 2.2 Create JSON processor class
  - Implement JSONProcessor class with schema validation
  - Add JSON schema definition for assignment structure with name-based fields
  - Implement JSON parsing with comprehensive error handling
  - Write unit tests for JSON parsing and validation
  - _Requirements: 3.1, 3.3_

- [x] 2.3 Create file format detection utility
  - Implement automatic file format detection based on extension
  - Add support for both .csv and .json file extensions
  - Handle format detection errors with clear messages
  - _Requirements: 1.1, 3.1_

- [x] 3. Implement resource resolution components
- [x] 3.1 Create resource resolver class
  - Implement ResourceResolver class for converting names to IDs/ARNs
  - Add principal name to ID resolution using Identity Store API
  - Add permission set name to ARN resolution using SSO Admin API
  - Add account name to ID resolution using Organizations API
  - Write unit tests for resolution logic
  - _Requirements: 1.2, 2.2, 3.2_

- [x] 3.2 Implement resolution caching
  - Add caching for repeated principal, permission set, and account name resolutions
  - Implement cache invalidation strategies
  - Optimize resolution performance for large files
  - _Requirements: 1.1, 2.1, 3.1_

- [x] 3.3 Create assignment validator class
  - Implement AssignmentValidator class for validating resolved assignments
  - Add validation for resolved principal IDs, permission set ARNs, and account IDs
  - Add validation for assignment existence checks
  - Write unit tests for validation logic
  - _Requirements: 1.3, 1.4, 2.3, 3.3_

- [x] 4. Implement preview functionality
- [x] 4.1 Create preview generator class
  - Implement PreviewGenerator class for displaying assignment previews
  - Add preview report generation showing resolved names and IDs
  - Implement user confirmation prompts after preview display
  - Add support for proceeding or canceling after preview
  - Write unit tests for preview generation
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 5. Implement batch processing engine
- [x] 5.1 Create batch processor class
  - Implement BatchProcessor class for handling bulk operations
  - Add support for configurable batch sizes
  - Implement parallel processing with proper error isolation
  - Add support for continue-on-error vs stop-on-error modes
  - Write unit tests for batch processing logic
  - _Requirements: 1.2, 1.5, 2.2, 2.4, 3.2, 4.1, 4.2_

- [x] 5.2 Implement progress tracking
  - Create ProgressTracker class using Rich progress bars
  - Add real-time progress updates during batch processing
  - Implement progress display for different batch sizes
  - Add estimated completion time calculations
  - _Requirements: 4.1_

- [x] 5.3 Add error handling and retry logic
  - Implement exponential backoff for API rate limiting
  - Add retry logic for transient AWS API errors
  - Handle network errors with appropriate user feedback
  - Implement proper error isolation between batch items
  - _Requirements: 4.2_

- [x] 6. Implement reporting components
- [x] 6.1 Create report generator class
  - Implement ReportGenerator class for summary and detailed reports
  - Add support for console output formatting using Rich
  - Create summary report with success/failure counts showing human-readable names
  - Implement detailed report with individual assignment results
  - Write unit tests for report generation
  - _Requirements: 1.5, 2.4, 3.4, 4.3_

- [x] 6.2 Add result tracking data structures
  - Implement AssignmentResult and BulkOperationResults dataclasses
  - Add proper result categorization (successful, failed, skipped)
  - Include error messages, timing information, and both names and resolved IDs
  - _Requirements: 1.5, 2.4, 3.4, 4.3_

- [x] 7. Implement bulk assign command
- [x] 7.1 Create bulk assign command implementation
  - Implement bulk_assign command with all required options
  - Add support for dry-run mode for validation without changes
  - Integrate file processing, name resolution, preview, and batch processing
  - Add proper error handling and user feedback
  - Write integration tests for assign command
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4_

- [x] 7.2 Add assignment operation logic
  - Implement AWS Identity Center assignment API calls using resolved IDs/ARNs
  - Add proper handling of existing assignments
  - Implement assignment creation with error handling
  - Add support for both user and group assignments
  - _Requirements: 1.2, 2.2_

- [x] 8. Implement bulk revoke command
- [x] 8.1 Create bulk revoke command implementation
  - Implement bulk_revoke command with all required options
  - Add confirmation prompts with force option override
  - Integrate with name resolution, preview, and batch processing
  - Add proper error handling for revoke operations
  - Write integration tests for revoke command
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4_

- [x] 8.2 Add revoke operation logic
  - Implement AWS Identity Center revoke API calls using resolved IDs/ARNs
  - Add proper handling of non-existent assignments
  - Implement assignment deletion with error handling
  - Add support for both user and group assignment revocation
  - _Requirements: 1.2, 2.2_

- [x] 9. Add CLI integration and testing
- [x] 9.1 Integrate bulk commands into main CLI
  - Add bulk command group to main CLI application
  - Update CLI imports and command registration
  - Ensure consistent help text and parameter naming
  - Test CLI integration with existing commands
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [x] 9.2 Create comprehensive test suite
  - Write unit tests for all components (file processors, resource resolver, validators, batch processor)
  - Create integration tests for end-to-end workflows including name resolution
  - Add test fixtures for CSV and JSON input files with human-readable names
  - Test error scenarios and edge cases including name resolution failures
  - Add performance tests for large file processing with caching
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_

- [x] 10. Add documentation and examples
- [x] 10.1 Create example input files
  - Create sample CSV files with human-readable names for various assignment scenarios
  - Create sample JSON files with name-based assignment structures
  - Add examples for both user and group assignments using names
  - Include examples with validation errors for testing name resolution
  - _Requirements: 1.1, 2.1, 3.1_

- [x] 10.2 Update help documentation
  - Add comprehensive help text for all bulk commands
  - Include usage examples showing name-based input format
  - Document file format requirements with human-readable examples
  - Add troubleshooting guidance for name resolution errors
  - _Requirements: 4.4_