# Implementation Plan

- [x] 1. Create AWS Organizations client wrapper
  - Create `OrganizationsClient` class in `utils/aws_client.py` to wrap boto3 organizations client
  - Add methods for `list_roots()`, `list_organizational_units_for_parent()`, `list_accounts_for_parent()`, `describe_account()`, `list_tags_for_resource()`, `list_policies_for_target()`
  - Include proper error handling and session management
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [x] 2. Create data models for organization structure
  - Define `OrgNode` class with id, name, type, and children attributes
  - Define `AccountDetails` class with comprehensive account metadata
  - Create type definitions for policy information and hierarchy paths
  - _Requirements: 1.2, 2.2, 2.3, 4.3_

- [x] 3. Implement organization hierarchy builder
  - Create function to recursively build organization tree structure
  - Handle root, OU, and account relationships correctly
  - Include error handling for incomplete or malformed organization data
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 4. Create organization command module
  - Create `src/awsideman/commands/org.py` with typer app structure
  - Set up basic command structure following existing patterns from other command modules
  - Add proper imports and console setup
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [x] 5. Implement `org tree` command
  - Create command to display full organization hierarchy
  - Support both tree and flat output formats using `--flat` flag
  - Include JSON output support with `--json` flag
  - Display OU names, IDs, parent relationships, and accounts under OUs
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 6. Implement account metadata retrieval
  - Create helper function to get comprehensive account details
  - Retrieve account name, ID, email, status, joined timestamp, and tags
  - Calculate and include full OU path from root to account
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 7. Implement `org account` command
  - Create command to display detailed account information for given account ID
  - Support both table and JSON output formats
  - Include comprehensive error handling for invalid account IDs
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 8. Implement account search functionality
  - Create helper function for case-insensitive account name searching
  - Support partial string matching on account names
  - Include optional filtering by OU and tags
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 9. Implement `org search` command
  - Create command to search accounts by name or substring
  - Return matching accounts with name, ID, email, and OU path
  - Support optional `--ou` and `--tag` filters
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 10. Create policy resolver for SCP/RCP tracing
  - Implement `PolicyResolver` class to traverse OU hierarchy from account to root
  - Aggregate all attached SCPs and RCPs at each level
  - Handle conditional/inherited policies and effective status
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 11. Implement `org trace-policies` command
  - Create command to trace all SCPs and RCPs affecting a given account
  - Display policy names, IDs, attachment points, and effective status
  - Distinguish between SCPs and RCPs in output
  - Include full OU path resolution
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 12. Add organization commands to main CLI
  - Register the org command module in `src/awsideman/cli.py`
  - Follow existing pattern for adding subcommands
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [x] 13. Create comprehensive unit tests for OrganizationsClient
  - Test all client wrapper methods with mocked boto3 responses
  - Test error handling scenarios
  - Use `botocore.stub.Stubber` for mocking AWS API calls
  - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [x] 14. Create unit tests for data models and hierarchy builder
  - Test `OrgNode` and `AccountDetails` classes
  - Test organization tree construction logic
  - Test edge cases and malformed data handling
  - _Requirements: 1.2, 2.2, 4.3_

- [x] 15. Create unit tests for policy resolver
  - Test policy aggregation logic across OU hierarchy
  - Test handling of conditional and inherited policies
  - Test SCP vs RCP distinction
  - _Requirements: 4.2, 4.3, 4.4, 4.5_

- [x] 16. Create CLI integration tests for all org commands
  - Test `org tree` command with various output formats
  - Test `org account` command with valid and invalid account IDs
  - Test `org search` command with different search patterns and filters
  - Test `org trace-policies` command with policy inheritance scenarios
  - Use `click.testing.CliRunner` for CLI testing
  - _Requirements: 1.1, 1.4, 2.1, 2.4, 3.1, 3.2, 4.1_