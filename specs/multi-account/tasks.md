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

- [x] 7. Implement comprehensive error handling and reporting
  - Add name resolution error handling with detailed error messages
  - Implement account filter error handling for invalid expressions
  - Create multi-account specific error reporting with account-level details
  - Add error summary generation for failed operations
  - _Requirements: 1.5, 2.4, 3.3, 5.4_

- [x] 8. Create unit tests for account filtering
  - Write tests for wildcard account filtering functionality
  - Create tests for tag-based account filtering with various tag combinations
  - Add tests for multiple tag filter support
  - Implement tests for invalid filter expression handling
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 9. Create unit tests for multi-account batch processing
  - Write tests for multi-account assignment processing with success scenarios
  - Create tests for error isolation between accounts during processing
  - Add tests for progress tracking accuracy across multiple accounts
  - Implement tests for retry logic when individual account operations fail
  - _Requirements: 1.4, 2.3, 5.1, 6.4_

- [x] 10. Create integration tests for end-to-end workflows
  - Write integration tests for complete multi-assign workflow
  - Create integration tests for complete multi-revoke workflow
  - Add tests for dry-run validation across multiple accounts
  - Implement tests for mixed success/failure scenarios
  - _Requirements: 1.1, 1.4, 1.5, 2.1, 2.3, 2.4, 4.1, 4.2_

- [x] 11. Add performance tests for scalability
  - Create tests for operations across 100+ accounts
  - Write tests for large batch size processing efficiency
  - Add memory usage tests with large account lists
  - Implement progress tracking performance validation
  - _Requirements: 5.1, 6.1, 6.2, 6.3_

- [x] 12. Create comprehensive documentation and examples
  - Write command usage documentation with examples for both multi-assign and multi-revoke
  - Create examples showing different account filtering scenarios
  - Add troubleshooting guide for common error scenarios
  - Document performance considerations and best practices
  - _Requirements: 1.1, 2.1, 3.1, 3.2, 4.1, 5.1, 6.1_

- [x] 13. Implement explicit account list support
  - Add explicit_accounts parameter to AccountFilter class constructor
  - Implement _resolve_explicit_accounts method for direct account ID processing
  - Add validation for explicit account IDs to ensure they exist and are accessible
  - Update CLI commands to properly handle --accounts parameter instead of showing placeholder message
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 14. Add streaming account resolution for large-scale operations
  - Implement resolve_accounts_streaming method using Python generators
  - Add memory-efficient account processing for thousands of accounts
  - Create streaming account resolution with lazy evaluation
  - Implement chunked processing for very large account sets
  - _Requirements: 9.1, 9.2_

- [x] 15. Enhance CLI commands with advanced filtering options
  - Add --ou-filter parameter for organizational unit filtering
  - Add --account-pattern parameter for regex-based account name matching
  - Implement OU-based filtering with organizational unit path matching
  - Add regex-based account name pattern filtering
  - Create parameter validation for mutually exclusive filter options
  - _Requirements: 7.4, 8.1, 8.2_

- [x] 16. Implement intelligent backoff strategies for rate limiting
  - Add adaptive backoff strategies based on error type analysis
  - Implement per-service rate limit tracking for different AWS APIs
  - Create circuit breaker pattern for persistent failures
  - Add jitter to exponential backoff to avoid thundering herd problems
  - _Requirements: 6.4, 9.3_

- [x] 17. Add enhanced progress reporting for large operations
  - Implement detailed progress information for extended time operations
  - Create progress persistence for resumable operations
  - Add estimated time remaining calculations for large account sets
  - _Requirements: 9.4_

- [X] 18. Create comprehensive tests for enhanced filtering; keep test cases simple.
  - Write unit tests for explicit account list filtering
  - Create tests for OU-based filtering with various organizational structures
  - Add tests for regex-based account name pattern matching
  - Implement tests for boolean combination logic with complex criteria
  - _Requirements: 7.1, 7.2, 8.1, 8.2, 8.3_

- [X] 19. Update documentation for enhanced features
  - Document explicit account list usage patterns and examples
  - Add OU-based filtering examples with organizational structure scenarios
  - Create regex pattern examples for account name filtering
  - Document performance considerations for large-scale operations
  - _Requirements: 7.1, 8.1, 8.2, 9.1, 9.2, 9.4_
