# Requirements Document

Introduction

This document outlines the requirements for enhancing the AWS Identity Center CLI tool with support for listing and inspecting AWS Organizations-related information. The functionality includes querying organizations, organizational units (OUs), accounts, and service control policies (SCPs) and resource control policies (RCPs).

The primary goals are:
	•	Provide visibility into the structure and metadata of an AWS Organization
	•	Enable account lookup and filtering capabilities
	•	Trace the effective SCPs and RCPs applied to specific accounts

Requirements

Requirement 1: List AWS Organization Structure

User Story: As a CLI user, I want to list my AWS Organization structure including roots, organizational units, and accounts.

Acceptance Criteria
	1.	The CLI SHALL provide a command to display the full hierarchy of roots, OUs, and accounts.
	2.	The output SHALL include OU names, IDs, and parent relationships.
	3.	Accounts SHALL be listed under their corresponding OUs.
	4.	The output SHALL support both tree and flat formats.

Requirement 2: Display Detailed Account Information

User Story: As a CLI user, I want to inspect an account’s metadata, including tags and its OU path.

Acceptance Criteria
	1.	The CLI SHALL provide a command to show full metadata for a given AWS account ID.
	2.	The output SHALL include the account name, ID, email, status, joined timestamp, and tags.
	3.	The output SHALL show the full OU path from the root to the account.
	4.	The CLI SHALL support output in JSON and table formats.

Requirement 3: Filter and Search Accounts

User Story: As a CLI user, I want to search accounts by name or substring to quickly locate them.

Acceptance Criteria
	1.	The CLI SHALL provide a command to search accounts by full or partial match on the account name.
	2.	The CLI SHALL return a list of matching accounts including their name, ID, email, and OU path.
	3.	The command SHALL support optional filters (e.g. by OU, by tag).
	4.	The search SHALL be case-insensitive by default.

Requirement 4: Trace SCPs and RCPs for an Account

User Story: As a CLI user, I want to see all SCPs and RCPs affecting a given account, including those inherited from parent OUs and root.

Acceptance Criteria
	1.	The CLI SHALL provide a command to trace SCPs and RCPs for a given account ID.
	2.	The command SHALL resolve the full OU path and collect all attached policies from each level.
	3.	The output SHALL include the policy names, IDs, attachment points, and effective status.
	4.	If a policy is conditionally enabled/disabled, the output SHALL reflect that status.
	5.	The CLI SHALL distinguish between SCPs and RCPs in the output.
