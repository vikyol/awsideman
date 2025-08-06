# Requirements Document

Introduction

Managing AWS IAM Identity Center permission assignments at scale often involves repetitive tasks — assigning the same permission set to similar user groups across multiple accounts. This enhancement introduces permission assignment templates, allowing users to define reusable templates that describe a set of assignments, which can be applied, reviewed, and versioned as needed.

Templates provide a declarative way to manage user access consistently and efficiently, improving automation and reducing manual errors.

⸻

Requirement A – Define and Create Templates

User Story: As a user, I want to define reusable templates that describe permission assignments so that I can manage access configurations in a structured way.

Acceptance Criteria
	1.	The system SHALL support creating templates as YAML or JSON files on disk.
	2.	A template SHALL contain:
	•	Template name
	•	List of user or group identifiers
	•	Target permission set name or ARN
	•	Account targets (account IDs or tag filters)
	3.	Templates MAY be stored in a .awsideman/templates/ directory or user-defined location.
	4.	The CLI SHALL validate the structure and values of a template file.
	5.	The CLI SHALL support a template create subcommand to initialize a blank or example template.

⸻

Requirement B – Apply a Template

User Story: As a user, I want to apply a permission template so that all the assignments are created or updated in bulk.

Acceptance Criteria
	1.	The CLI SHALL support a template apply <template-file> command.
	2.	Applying a template SHALL assign all specified permission sets to the users/groups for each account defined.
	3.	Account selection SHALL support wildcard and tag-based filtering, as in the bulk assignment feature.
	4.	The CLI output SHALL summarize all actions taken, and clearly indicate any skipped or failed assignments.
	5.	A --dry-run option SHALL simulate and print the changes without making actual API calls.

⸻

Requirement C – Validate and Preview Templates

User Story: As a user, I want to validate and preview what a template would do before applying it, to avoid unintended assignments.

Acceptance Criteria
	1.	The CLI SHALL support template validate <template-file> to check format, required fields, and structure.
	2.	The CLI SHALL support template preview <template-file> to display the resolved assignments in table or JSON format.
	3.	Validation SHALL report any missing permission sets, unresolved users, or unknown accounts/tags.
	4.	Preview SHALL simulate full account resolution (e.g., tag filtering → matching account list).

⸻

Requirement D – Manage Templates

User Story: As a user, I want to list and describe templates so I can reuse and maintain them easily.

Acceptance Criteria
	1.	The CLI SHALL support template list to show all available templates with basic metadata (name, users, permission set, # of accounts).
	2.	The CLI SHALL support template show <template-name> to display the full contents of the template.
	3.	Templates MAY include an optional description or metadata section to aid documentation.
	4.	The system MAY support versioning or backup (e.g., .bak or template-v2.yaml), but this is not required in the initial phase.
