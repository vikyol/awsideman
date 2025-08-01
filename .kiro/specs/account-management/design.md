
# 📐 Design Document – AWS Organizations Support

## Overview

This document describes the design for extending the `awsideman` CLI tool with comprehensive AWS Organizations support. The design enables users to query and inspect organizational structure, account metadata, and policy inheritance. Key capabilities include hierarchical organization display, detailed account inspection, flexible account search, and complete policy tracing for SCPs and RCPs.

The design follows the existing CLI patterns and integrates seamlessly with the current `awsideman` architecture while providing robust error handling and multiple output formats.

---

## 🧱 Architecture Components

### 1. OrganizationsClient
- A wrapper around `boto3` clients for `organizations`, encapsulating:
  - `list_roots()`
  - `list_organizational_units_for_parent()`
  - `list_accounts_for_parent()`
  - `describe_account()`
  - `list_tags_for_resource()`
  - `list_policies_for_target()`

### 2. PolicyResolver
- Given an account ID:
  - Traverses the OU hierarchy from account to root
  - Aggregates all attached SCPs and RCPs at each level
  - Handles conditional/inherited policies

### 3. Cache Layer (optional, later phase)
- Caches account metadata and hierarchy results to avoid redundant calls
- TTL-based invalidation (e.g., 15 minutes for hierarchy)

### 4. Presentation Layer
- CLI output handler supporting:
  - Tree view
  - Flat view
  - JSON
  - Table output
- Modular rendering functions per command

---

## 🖥️ CLI Commands

### `awsideman org tree`
**Purpose**: Display the complete AWS Organization hierarchy including roots, OUs, and accounts.
- Shows OU names, IDs, and parent relationships
- Lists accounts under their corresponding OUs
- Supports `--flat` for linear output and `--json` for structured data
- **Design Rationale**: Tree view provides intuitive visualization of organizational structure, while flat view enables easier parsing and filtering

### `awsideman org account <account-id>`
**Purpose**: Display comprehensive metadata for a specific AWS account.
- Outputs account name, ID, email, status, joined timestamp, and tags
- Shows the complete OU path from root to account
- Supports both table and JSON output formats
- **Design Rationale**: Centralized account inspection reduces need for multiple API calls and provides complete context

### `awsideman org search <query>`
**Purpose**: Enable flexible account discovery through name-based searching.
- Performs case-insensitive partial string matching on account names
- Returns matching accounts with name, ID, email, and OU path
- Optional filtering by OU (`--ou <ou-id>`) and tags (`--tag Key=Value`)
- **Design Rationale**: Case-insensitive search improves usability; optional filters enable targeted discovery in large organizations

### `awsideman org trace-policies <account-id>`
**Purpose**: Provide complete visibility into policy inheritance for compliance and troubleshooting.
- Resolves full OU path and collects all attached SCPs and RCPs from each level
- Displays policy names, IDs, attachment points, and effective status
- Distinguishes between SCPs and RCPs in output
- Handles conditional policy status (enabled/disabled)
- **Design Rationale**: Policy tracing is essential for understanding effective permissions and compliance requirements

---

## 🔗 AWS API Calls

| Feature                | API Calls Used                                                                 |
|------------------------|--------------------------------------------------------------------------------|
| Org tree               | `list_roots`, `list_organizational_units_for_parent`, `list_accounts_for_parent` |
| Account metadata       | `describe_account`, `list_tags_for_resource`                                   |
| Account search         | `list_accounts`, filter in-memory or post-fetch                                |
| Trace policies         | `list_parents`, `list_policies_for_target`, `describe_policy` (for metadata)   |

---

## 🔄 Internal Data Models

### OrgNode
```python
class OrgNode:
    id: str
    name: str
    type: Literal["ROOT", "OU", "ACCOUNT"]
    children: list["OrgNode"]
```

### AccountDetails
```python
class AccountDetails:
    id: str
    name: str
    email: str
    status: str
    joined_timestamp: datetime
    tags: dict[str, str]
    ou_path: list[str]  # IDs or names
```

---

## 📊 Output Examples

### Tree View
```
Root: r-1234
└── OU: Engineering
    ├── Account: dev-001 (111111111111)
    └── Account: qa-001 (222222222222)
```

### Account Details
```json
{
  "id": "111111111111",
  "name": "dev-001",
  "email": "dev@example.com",
  "status": "ACTIVE",
  "joined_timestamp": "2021-01-01T00:00:00Z",
  "tags": {
    "Environment": "Development"
  },
  "ou_path": ["r-1234", "ou-4567"]
}
```

### Policy Trace
```
Account: 111111111111
OU Path: ROOT → OU: Engineering

Policies:
- SCP: FullAccess (p-1234), Attached to ROOT, Status: Enabled
- SCP: ReadOnly (p-5678), Attached to OU: Engineering, Status: Enabled
```

---

## 🧪 Testing Strategy

- Unit tests for:
  - Tree construction
  - Account metadata parsing
  - Policy aggregation logic
- Mock `boto3` clients using `botocore.stub.Stubber`
- CLI-level tests using `click.testing.CliRunner`

---

## 🚧 Future Considerations

- Add support for delegated administrators
- Include SCP evaluation simulator (dry-run mode)
- Cache organization structure with configurable TTL
- Add `awsideman org export --format graphviz/json`