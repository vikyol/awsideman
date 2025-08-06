# Requirements Document

## Introduction

Awsideman currently supports managing permission set assignments either by invoking individual CLI commands or through a bulk operations mode. These capabilities are effective for small to medium-scale organizations but become inefficient for large enterprises with many accounts and users.

This feature enhancement aims to improve the scalability of permission set assignment and revocation across large account structures. It introduces the ability to assign or revoke a permission set to/from a user across all or a filtered set of accounts in a single operation.

To increase flexibility, the feature will support an optional account filter parameter. The filter may be specified using:
- A wildcard character (*) to select all accounts
- An account tag (key-value pair) to select a subset of accounts

## Requirements

### Requirement 1

**User Story:** As an identity administrator, I want to assign a permission set to a user across all or a filtered list of AWS accounts so that the user can access multiple accounts with a consistent set of permissions.

#### Acceptance Criteria

1. WHEN an administrator executes a multi-account assignment command THEN the CLI SHALL support assigning a given permission set to a user across multiple accounts
2. WHEN specifying the target user THEN the user SHALL be identified by a principal ID or name
3. WHEN providing account filtering THEN the CLI SHALL accept an account filter parameter that supports wildcard (*) to match all accounts AND tag-based filtering (--filter-tag Key=Environment Value=Dev)
4. WHEN the command is executed THEN the CLI SHALL iterate over all matching accounts and invoke the necessary API calls to create the assignments
5. WHEN the operation completes THEN the CLI output SHALL show a summary of accounts where the permission set was successfully assigned or failed

### Requirement 2

**User Story:** As an identity administrator, I want to revoke a permission set from a user across all or a filtered list of AWS accounts in one command so that I can efficiently remove access across multiple accounts.

#### Acceptance Criteria

1. WHEN an administrator executes a multi-account revocation command THEN the CLI SHALL support revoking a given permission set from a user across multiple accounts
2. WHEN providing account filtering THEN the command SHALL accept the same account filtering options as the assignment operation
3. WHEN the command is executed THEN the CLI SHALL iterate over all matching accounts and revoke the assignments if they exist
4. WHEN the operation completes THEN the output SHALL show a summary of accounts where revocation was successful or skipped (e.g., if assignment was not present)

### Requirement 3

**User Story:** As an administrator, I want to limit the bulk permission set operations to only a subset of accounts, so I can target only development, production, or tagged groups of accounts.

#### Acceptance Criteria

1. WHEN using wildcard filtering THEN the account filter SHALL support matching all accounts using a wildcard *
2. WHEN using tag-based filtering THEN the account filter SHALL support matching a subset of accounts using a tag key-value pair
3. IF no filter is provided THEN the CLI SHALL return an error indicating a filter is required to avoid accidental bulk operations
4. WHEN using tag filtering THEN the system SHALL support multiple values using repeated --filter-tag flags or a comma-separated list

### Requirement 4

**User Story:** As an administrator, I want to preview which accounts would be affected before performing bulk changes to avoid unintended access grants or removals.

#### Acceptance Criteria

1. WHEN the --dry-run flag is provided THEN the CLI SHALL list the accounts and operations it would perform without making any actual changes
2. WHEN in dry-run mode THEN the CLI SHALL simulate assignments or revocations and indicate what would happen per account
3. WHEN --dry-run is enabled THEN the CLI SHALL not modify any assignments

### Requirement 5

**User Story:** As an administrator, I want to see real-time progress when performing multi-account operations so that I can monitor the status of long-running operations across hundreds of accounts.

#### Acceptance Criteria

1. WHEN executing multi-account operations THEN the CLI SHALL display a progress indicator showing current account being processed and total progress
2. WHEN processing accounts THEN the CLI SHALL show the account name/ID currently being processed
3. WHEN an operation completes or fails for an account THEN the CLI SHALL immediately display the result
4. WHEN the operation is complete THEN the CLI SHALL display a final summary with success/failure counts

### Requirement 6

**User Story:** As an administrator, I want to configure the batch size for multi-account operations so that I can optimize performance and avoid API rate limits.

#### Acceptance Criteria

1. WHEN executing multi-account operations THEN the CLI SHALL support a --batch-size parameter to control how many accounts are processed concurrently
2. WHEN no batch size is specified THEN the CLI SHALL use a sensible default batch size (e.g., 10 accounts)
3. WHEN batch size is configured THEN the CLI SHALL process accounts in batches of the specified size
4. WHEN rate limits are encountered THEN the CLI SHALL implement exponential backoff and retry logic



