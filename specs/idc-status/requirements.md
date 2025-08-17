# Requirements Document

## Introduction

The IDC Status feature provides comprehensive status monitoring and health checking capabilities for AWS Identity Center (IDC) resources and operations. This feature enables administrators to quickly assess the current state of their Identity Center deployment, including user provisioning status, permission set assignments, group memberships, and overall system health.

## Requirements

### Requirement 1

**User Story:** As an AWS Identity Center administrator, I want to check the overall health status of my Identity Center instance, so that I can quickly identify any issues or operational problems.

#### Acceptance Criteria

1. WHEN the user runs the status command THEN the system SHALL display the overall health status of the Identity Center instance
2. WHEN the Identity Center instance is healthy THEN the system SHALL display a "Healthy" status with green indicator
3. WHEN there are warnings or issues THEN the system SHALL display appropriate status levels (Warning, Critical) with colored indicators
4. WHEN the system cannot connect to Identity Center THEN the system SHALL display a "Connection Failed" status with error details

### Requirement 2

**User Story:** As an administrator, I want to see the status of user provisioning operations, so that I can monitor ongoing synchronization processes and identify stuck or failed operations.

#### Acceptance Criteria

1. WHEN the user requests provisioning status THEN the system SHALL display the current state of all active provisioning operations
2. WHEN there are pending provisioning operations THEN the system SHALL show the count and estimated completion time
3. WHEN provisioning operations have failed THEN the system SHALL display error details and affected users
4. WHEN no provisioning operations are active THEN the system SHALL display "No active operations"

### Requirement 3

**User Story:** As an administrator, I want to see orphaned permission set assignments, so that I can identify and clean up assignments for principals that no longer exist in the identity provider.

#### Acceptance Criteria

1. WHEN the user requests orphaned assignment status THEN the system SHALL identify and display permission set assignments where the principal has been deleted from the identity provider
2. WHEN orphaned assignments are found THEN the system SHALL display the assignment details including permission set name, account, and the orphaned principal identifier
3. WHEN displaying orphaned assignments THEN the system SHALL show error messages that AWS Identity Center displays for missing user names
4. WHEN orphaned assignments are displayed THEN the system SHALL prompt the user with an option to clean up the orphaned assignments
5. WHEN the user confirms cleanup THEN the system SHALL remove the orphaned assignments and display a summary of cleaned up items
6. WHEN no orphaned assignments exist THEN the system SHALL display "No orphaned assignments found"

### Requirement 4

**User Story:** As an administrator, I want to see the synchronization status with external identity providers, so that I can ensure user and group data is properly synchronized.

#### Acceptance Criteria

1. WHEN the user requests sync status THEN the system SHALL display the last synchronization time and status for each configured identity provider
2. WHEN synchronization is overdue THEN the system SHALL display a warning with the time since last sync
3. WHEN synchronization has failed THEN the system SHALL display error details and suggested remediation steps
4. WHEN no external identity providers are configured THEN the system SHALL display "No external providers configured"

### Requirement 5

**User Story:** As an administrator, I want to check the status of specific resources (users, groups, permission sets), so that I can troubleshoot issues with individual components.

#### Acceptance Criteria

1. WHEN the user specifies a resource type and identifier THEN the system SHALL display detailed status information for that resource
2. WHEN the resource exists and is healthy THEN the system SHALL display current configuration and last update time
3. WHEN the resource has issues THEN the system SHALL display specific error conditions and suggested actions
4. WHEN the resource does not exist THEN the system SHALL display "Resource not found" with suggestions for similar resources

### Requirement 6

**User Story:** As an administrator, I want to export status information in different formats, so that I can integrate status data with monitoring systems or generate reports.

#### Acceptance Criteria

1. WHEN the user specifies an output format THEN the system SHALL support JSON, CSV, and table formats
2. WHEN exporting to JSON THEN the system SHALL include all status data in a structured format suitable for API consumption
3. WHEN exporting to CSV THEN the system SHALL format data for spreadsheet analysis
4. WHEN no format is specified THEN the system SHALL default to human-readable table format

### Requirement 7

**User Story:** As an administrator, I want to see summary statistics of my Identity Center deployment, so that I can quickly understand the scale and scope of my current configuration.

#### Acceptance Criteria

1. WHEN the user requests status information THEN the system SHALL display total counts of users, groups, and permission sets
2. WHEN displaying assignment statistics THEN the system SHALL show total number of active assignments across all accounts
3. WHEN showing account information THEN the system SHALL display the number of accounts with active assignments
4. WHEN presenting summary data THEN the system SHALL include creation dates and last modification times for key metrics

### Requirement 8

**User Story:** As an administrator, I want to set up automated status monitoring, so that I can receive alerts when issues are detected without manual checking.

#### Acceptance Criteria

1. WHEN the user configures monitoring thresholds THEN the system SHALL support configurable warning and critical levels
2. WHEN status checks are automated THEN the system SHALL support scheduled execution via cron or similar mechanisms
3. WHEN issues are detected THEN the system SHALL support notification via email, webhook, or log output
4. WHEN monitoring is disabled THEN the system SHALL only perform on-demand status checks
