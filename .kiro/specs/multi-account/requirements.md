# Requirements Document

Introduction

Awsideman currently supports managing permission set assignments either by invoking individual CLI commands or through a bulk operations mode. These capabilities are effective for small to medium-scale organizations but become inefficient for large enterprises with many accounts and users.

This feature enhancement aims to improve the scalability of permission set assignment and revocation across large account structures. It introduces the ability to assign or revoke a permission set to/from a user across all or a filtered set of accounts in a single operation.

To increase flexibility, the feature will support an optional account filter parameter. The filter may be specified using:
	•	A wildcard character (*) to select all accounts
	•	An account tag (key-value pair) to select a subset of accounts

⸻

Requirements

Requirement A – Assign Permission Set to User Across Accounts

User Story: As an identity administrator, I want to assign a permission set to a user across all or a filtered list of AWS accounts so that the user can access multiple accounts with a consistent set of permissions.

Acceptance Criteria
	1.	The CLI SHALL support a command to assign a given permission set to a user across multiple accounts.
	2.	The user SHALL be identified by a principal ID or name.
	3.	The CLI SHALL accept an account filter parameter that supports:
	•	Wildcard (*) to match all accounts
	•	Tag-based filtering (--filter-tag Key=Environment Value=Dev)
	4.	The command SHALL iterate over all matching accounts and invoke the necessary API calls to create the assignments.
	5.	The CLI output SHALL show a summary of accounts where the permission set was successfully assigned or failed.

⸻

Requirement B – Revoke Permission Set from User Across Accounts

User Story: As an identity administrator, I want to revoke a permission set from a user across all or a filtered list of AWS accounts in one command.

Acceptance Criteria
	1.	The CLI SHALL support a command to revoke a given permission set from a user across multiple accounts.
	2.	The command SHALL accept the same account filtering options as the assignment operation.
	3.	The CLI SHALL iterate over all matching accounts and revoke the assignments if they exist.
	4.	The output SHALL show a summary of accounts where revocation was successful or skipped (e.g., if assignment was not present).

⸻

Requirement C – Account Filter Support

User Story: As an administrator, I want to limit the bulk permission set operations to only a subset of accounts, so I can target only development, production, or tagged groups of accounts.

Acceptance Criteria
	1.	The account filter SHALL support matching all accounts using a wildcard *.
	2.	The account filter SHALL support matching a subset of accounts using a tag key-value pair.
	3.	If no filter is provided, the CLI SHALL return an error indicating a filter is required to avoid accidental bulk operations.
	4.	Tag filtering SHALL support multiple values using repeated --filter-tag flags or a comma-separated list.

⸻

Requirement D – Safety and Dry-Run Mode

User Story: As an administrator, I want to preview which accounts would be affected before performing bulk changes to avoid unintended access grants or removals.

Acceptance Criteria
	1.	The CLI SHALL support a --dry-run flag that lists the accounts and operations it would perform without making any actual changes.
	2.	In dry-run mode, the CLI SHALL simulate assignments or revocations and indicate what would happen per account.
	3.	The CLI SHALL not modify any assignments when --dry-run is enabled.



