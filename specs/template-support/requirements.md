# Requirements Document

## Introduction

Managing AWS IAM Identity Center permission assignments at scale often involves repetitive tasks — assigning the same permission set to similar user groups across multiple accounts. This enhancement introduces permission assignment templates, allowing users to define reusable templates that describe a set of assignments, which can be applied, reviewed, and versioned as needed.

Templates provide a declarative way to manage user access consistently and efficiently, improving automation and reducing manual errors. Templates should contain placeholders that will be passed in by the user. Each template might have one or more placeholder, e.g. account name, user name, etc.

## Requirements

### Requirement 1

**User Story:** As a user, I want to define reusable templates that describe permission assignments so that I can manage access configurations in a structured way.

#### Acceptance Criteria

1. WHEN a user creates a template THEN the system SHALL support creating templates as YAML or JSON files on disk
2. WHEN a template is created THEN the template SHALL contain template name, list of user or group identifiers, target permission set name or ARN, and account targets (account IDs or tag filters)
3. IF no custom location is specified THEN templates SHALL be stored in a .awsideman/templates/ directory
4. WHEN a template file is provided THEN the CLI SHALL validate the structure and values of the template file
5. WHEN a user runs template create command THEN the CLI SHALL support a template create subcommand to initialize a blank or example template

### Requirement 2

**User Story:** As a user, I want to apply a permission template so that all the assignments are created or updated in bulk.

#### Acceptance Criteria

1. WHEN a user wants to apply a template THEN the CLI SHALL support a template apply <template-file> command
2. WHEN applying a template THEN the system SHALL assign all specified permission sets to the users/groups for each account defined
3. WHEN account selection is specified THEN the system SHALL support wildcard and tag-based filtering, as in the multi-account feature
4. WHEN a template is applied THEN the CLI output SHALL summarize all actions taken, and clearly indicate any skipped or failed assignments
5. WHEN --dry-run option is used THEN the system SHALL simulate and print the changes without making actual API calls

### Requirement 3

**User Story:** As a user, I want to validate and preview what a template would do before applying it, to avoid unintended assignments.

#### Acceptance Criteria

1. WHEN a user runs template validate command THEN the CLI SHALL support template validate <template-file> to check format, required fields, and structure
2. WHEN a user runs template preview command THEN the CLI SHALL support template preview <template-file> to display the resolved assignments in table or JSON format
3. WHEN validation is performed THEN the system SHALL report any missing permission sets, unresolved users, or unknown accounts/tags
4. WHEN preview is performed THEN the system SHALL simulate full account resolution (e.g., tag filtering → matching account list)

### Requirement 4

**User Story:** As a user, I want to list and describe templates so I can reuse and maintain them easily.

#### Acceptance Criteria

1. WHEN a user runs template list command THEN the CLI SHALL support template list to show all available templates with basic metadata (name, users, permission set, # of accounts)
2. WHEN a user runs template show command THEN the CLI SHALL support template show <template-name> to display the full contents of the template
3. IF a template includes metadata THEN templates MAY include an optional description or metadata section to aid documentation
4. IF versioning is needed THEN the system MAY support versioning or backup (e.g., .bak or template-v2.yaml), but this is not required in the initial phase
