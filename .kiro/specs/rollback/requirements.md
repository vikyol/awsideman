# Requirements Document

Introduction

The awsideman tool manages permission assignments in AWS IAM Identity Center across users, groups, accounts, and permission sets. As the tool expands to support bulk operations and templates, the risk of unintended permission changes increases. A rollback capability is required to make these operations safer and reversible.

This feature introduces operation tracking and rollback commands, allowing users to undo specific permission set assignments or revocations made by previous CLI operations.

⸻

Requirements

Requirement A – Track Permission Set Changes

User Story: As a CLI user, I want every permission set assignment or revocation to be logged so that I can review or revert the changes later.

Acceptance Criteria
	1.	The system SHALL store a log of each bulk assignment or revocation operation in a persistent audit file (e.g., JSON or SQLite DB).
	2.	Each operation record SHALL include:
	•	Timestamp
	•	Operation ID
	•	Type (assign or revoke)
	•	Target principal (user/group ID)
	•	Permission set ID or name
	•	Affected account IDs
	•	Result of each assignment (success/failure)
	3.	The system SHALL tag each operation with a unique ID (UUID).
	4.	The system SHALL support storing logs in a dedicated directory (e.g. .awsideman/operations/).

⸻

Requirement B – List Historical Operations

User Story: As a user, I want to view a list of recent permission assignment operations so I can understand what has changed and decide what to roll back.

Acceptance Criteria
	1.	The CLI SHALL support awsideman rollback list to show a list of recent operations with:
	•	Operation ID
	•	Timestamp
	•	Type (assign or revoke)
	•	Subject (user/group)
	•	Permission set
	•	Number of accounts affected
	2.	The output SHALL be available in both table and JSON formats.
	3.	The list SHALL be filterable by:
	•	Operation type
	•	Subject
	•	Permission set
	•	Date range

⸻

Requirement C – Roll Back a Specific Operation

User Story: As a user, I want to roll back a specific operation by ID so I can undo a permission assignment or revocation that was incorrect or unintended.

Acceptance Criteria
	1.	The CLI SHALL support awsideman rollback apply <operation-id>.
	2.	If the original operation was assign, the rollback SHALL perform the inverse revoke action for the same accounts and subject.
	3.	If the original operation was revoke, the rollback SHALL re-assign the same permission set to the same subject and accounts.
	4.	The rollback operation SHALL:
	•	Log a new rollback record with a new operation ID
	•	Skip any already-rolled-back or unchanged entries
	•	Support --dry-run to simulate the rollback
	5.	The system SHALL confirm with the user before executing rollback unless --yes is provided.

⸻

Requirement D – Safety and Consistency

User Story: As a user, I want rollback to be reliable and consistent, so that I don’t accidentally reapply or remove wrong permissions.

Acceptance Criteria
	1.	The system SHALL check for conflicting or missing state before performing a rollback (e.g., already revoked).
	2.	Rollback SHALL be idempotent — running it multiple times should not cause further change.
	3.	Partial failures SHALL be reported clearly, and retried operations SHALL be supported.
	4.	A rollback SHALL never remove unrelated permissions.

⸻

Future Considerations (Out of Scope for Initial Version)
	•	Rollback previews in graphical diff format
	•	Undo chains (e.g., revert N levels back)
	•	Version control integration for template-backed permissions
	•	Manual rollback plan authoring



