# Requirements Document

## Introduction

The AWS Identity Center CLI tool currently supports managing permission set assignments manually. This feature will enable bulk operations for assigning permission sets to users and groups using input files, supporting both CSV and JSON formats to improve efficiency when managing multiple assignments.
Before applying changes, provide a report to visually present what changes will be applied. This will help users to review the changes before applying them.

## Requirements

### Requirement 1

**User Story:** As an AWS administrator, I want to bulk assign permission sets to multiple users using a CSV file, so that I can efficiently manage large numbers of user permissions without manual individual assignments.

#### Acceptance Criteria

1. WHEN a user provides a CSV file with user names and permission set data THEN the system SHALL validate the CSV format and structure
2. WHEN the CSV file is valid THEN the system SHALL resolve user names to principal IDs and assign the specified permission sets to the corresponding users
3. IF a user name in the CSV cannot be resolved to a principal ID THEN the system SHALL log an error and continue processing remaining entries
4. IF a permission set in the CSV does not exist THEN the system SHALL log an error and continue processing remaining entries
5. WHEN bulk assignment is complete THEN the system SHALL provide a summary report of successful and failed assignments

### Requirement 2

**User Story:** As an AWS administrator, I want to bulk assign permission sets to multiple groups using a CSV file, so that I can efficiently manage group-based permissions at scale.

#### Acceptance Criteria

1. WHEN a user provides a CSV file with group names and permission set data THEN the system SHALL validate the CSV format and structure
2. WHEN the CSV file is valid THEN the system SHALL resolve group names to principal IDs and assign the specified permission sets to the corresponding groups
3. IF a group name in the CSV cannot be resolved to a principal ID THEN the system SHALL log an error and continue processing remaining entries
4. WHEN bulk group assignment is complete THEN the system SHALL provide a summary report of successful and failed assignments

### Requirement 3

**User Story:** As an AWS administrator, I want to bulk assign permission sets using a JSON file format, so that I can use structured data with more complex assignment configurations.

#### Acceptance Criteria

1. WHEN a user provides a JSON file with assignment data containing principal names THEN the system SHALL validate the JSON format and schema
2. WHEN the JSON file is valid THEN the system SHALL resolve principal names to principal IDs and process each assignment entry for both users and groups
3. IF the JSON structure is invalid THEN the system SHALL provide clear error messages indicating the specific validation failures
4. WHEN bulk assignment from JSON is complete THEN the system SHALL provide a detailed summary report with assignment results

### Requirement 4

**User Story:** As an AWS administrator, I want to see detailed progress and error reporting during bulk operations, so that I can monitor the process and troubleshoot any issues.

#### Acceptance Criteria

1. WHEN bulk operations are running THEN the system SHALL display progress indicators showing current status
2. IF any assignment fails THEN the system SHALL log the specific error with user/group and permission set details
3. WHEN bulk operations complete THEN the system SHALL generate a comprehensive report showing successful and failed assignments
4. IF there are validation errors THEN the system SHALL provide clear, actionable error messages to help resolve issues

### Requirement 5

**User Story:** As an AWS administrator, I want to preview the changes that will be applied before executing bulk operations, so that I can review and confirm the assignments before they are processed.

#### Acceptance Criteria

1. WHEN a user provides an input file THEN the system SHALL generate a preview report showing all assignments to be processed
2. WHEN the preview report is displayed THEN the system SHALL show principal names, permission set names, and account details for each assignment
3. IF the user chooses to proceed after preview THEN the system SHALL execute the bulk operation
4. IF the user chooses not to proceed after preview THEN the system SHALL exit without making any changes



