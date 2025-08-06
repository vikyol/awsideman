# Implementation Plan

- [x] 1. Create account filtering infrastructure
  - Implement AccountFilter class to handle wildcard and tag-based filtering
  - Add Organizations API integration for account discovery and metadata retrieval
  - Create validation logic for filter expressions and error handling
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 2. Implement multi-account data models
  - Create AccountInfo dataclass for account metadata and tag matching
  - Implement AccountResult dataclass for individual account operation results
  - Create MultiAccountAssignment model with name resolution capabilities
  - Add MultiAccountResults aggregation class with success rate calculations
  - _Requirements: 1.1, 2.1, 5.5_

- [x] 3. Extend progress tracking for multi-account operations
  - Create MultiAccountProgressTracker extending existing ProgressTracker
  - Add account-level progress display with current account being processed
  - Implement real-time result display for completed accounts
  - Add final summary with success/failure counts
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 4. Create multi-account batch processor
  - Implement MultiAccountBatchProcessor extending existing BatchProcessor
  - Add name resolution integration using existing ResourceResolver
  - Implement account-level error isolation and retry logic
  - Add configurable batch size support with rate limiting
  - _Requirements: 1.4, 2.3, 6.1, 6.2, 6.3, 6.4_

- [x] 5. Implement CLI commands for multi-account operations
  - Add multi-assign command to assignment command group
  - Add multi-revoke command to assignment command group
  - Implement input validation for permission set names and principal names
  - Add account filter parameter validation and parsing
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 3.3_

- [x] 6. Add dry-run functionality for multi-account operations
  - Implement dry-run mode that shows preview without making changes
  - Display list of accounts that would be affected by the operation
  - Show resolved permission set ARN and principal ID in preview
  - Add simulation of assignment/revocation operations per account
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 7. Implement comprehensive error handling and reporting
  - Add name resolution error handling with detailed error messages
  - Implement account filter error handling for invalid expressions
  - Create multi-account specific error reporting with account-level details
  - Add error summary generation for failed operations
  - _Requirements: 1.5, 2.4, 3.3, 5.4_

- [ ] 8. Create unit tests for account filtering
  - Write tests for wildcard account filtering functionality
  - Create tests for tag-based account filtering with various tag combinations
  - Add tests for multiple tag filter support
  - Implement tests for invalid filter expression handling
  - _Requirements: 3.1, 3.2, 3.4_

- [ ] 9. Create unit tests for multi-account batch processing
  - Write tests for multi-account assignment processing with success scenarios
  - Create tests for error isolation between accounts during processing
  - Add tests for progress tracking accuracy across multiple accounts
  - Implement tests for retry logic when individual account operations fail
  - _Requirements: 1.4, 2.3, 5.1, 6.4_

- [ ] 10. Create integration tests for end-to-end workflows
  - Write integration tests for complete multi-assign workflow
  - Create integration tests for complete multi-revoke workflow
  - Add tests for dry-run validation across multiple accounts
  - Implement tests for mixed success/failure scenarios
  - _Requirements: 1.1, 1.4, 1.5, 2.1, 2.3, 2.4, 4.1, 4.2_

- [ ] 11. Add performance tests for scalability
  - Create tests for operations across 100+ accounts
  - Write tests for large batch size processing efficiency
  - Add memory usage tests with large account lists
  - Implement progress tracking performance validation
  - _Requirements: 5.1, 6.1, 6.2, 6.3_

- [ ] 12. Create comprehensive documentation and examples
  - Write command usage documentation with examples for both multi-assign and multi-revoke
  - Create examples showing different account filtering scenarios
  - Add troubleshooting guide for common error scenarios
  - Document performance considerations and best practices
  - _Requirements: 1.1, 2.1, 3.1, 3.2, 4.1, 5.1, 6.1_