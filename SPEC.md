# awsideman CLI Specification

## Overview

awsideman is a CLI tool for managing AWS Identity Center operations. It provides an intuitive interface for managing profiles, SSO instances, users, groups, permission sets, and assignments.

## Command Structure

```
awsideman
├── profile
│   ├── list
│   ├── add
│   ├── update
│   ├── remove
│   └── set-default
├── sso
│   ├── list
│   ├── set
│   └── info
├── user
│   ├── list
│   ├── get
│   ├── create
│   ├── update
│   └── delete
├── group
│   ├── list
│   ├── get
│   ├── create
│   ├── update
│   ├── delete
│   ├── add-user
│   └── remove-user
├── permission
│   ├── list
│   ├── get
│   ├── create
│   ├── update
│   └── delete
└── assignment
    ├── list
    ├── create
    ├── delete
    └── bulk
```

## Phase 1: Core Infrastructure (Current)

### Profile Management

- `profile list`: List all configured AWS profiles
- `profile add`: Add a new AWS profile
- `profile update`: Update an existing AWS profile
- `profile remove`: Remove an AWS profile
- `profile set-default`: Set the default AWS profile

### SSO Instance Configuration

- `sso list`: List all SSO instances in the AWS account
- `sso set`: Set the SSO instance to use for operations
- `sso info`: Show information about the configured SSO instance

## Phase 2: Identity Management

### User Management

- `user list`: List all users in the Identity Store
  - Options: `--filter`, `--limit`, `--next-token`
- `user get`: Get details about a specific user
  - Arguments: `user-id`
- `user create`: Create a new user
  - Options: `--username`, `--name`, `--email`, `--display-name`
- `user update`: Update an existing user
  - Arguments: `user-id`
  - Options: `--username`, `--name`, `--email`, `--display-name`
- `user delete`: Delete a user
  - Arguments: `user-id`
  - Options: `--force`

### Group Management

- `group list`: List all groups in the Identity Store
  - Options: `--filter`, `--limit`, `--next-token`
- `group get`: Get details about a specific group
  - Arguments: `group-id`
- `group create`: Create a new group
  - Options: `--display-name`, `--description`
- `group update`: Update an existing group
  - Arguments: `group-id`
  - Options: `--display-name`, `--description`
- `group delete`: Delete a group
  - Arguments: `group-id`
  - Options: `--force`
- `group add-user`: Add a user to a group
  - Arguments: `group-id`, `user-id`
- `group remove-user`: Remove a user from a group
  - Arguments: `group-id`, `user-id`

## Phase 3: Access Management

### Permission Set Management

- `permission list`: List all permission sets
  - Options: `--filter`, `--limit`, `--next-token`
- `permission get`: Get details about a specific permission set
  - Arguments: `permission-set-arn`
- `permission create`: Create a new permission set
  - Options: `--name`, `--description`, `--session-duration`, `--relay-state`, `--managed-policies`, `--inline-policy`, `--customer-managed-policies`
- `permission update`: Update an existing permission set
  - Arguments: `permission-set-arn`
  - Options: `--name`, `--description`, `--session-duration`, `--relay-state`
- `permission delete`: Delete a permission set
  - Arguments: `permission-set-arn`
  - Options: `--force`

### Assignment Management

- `assignment list`: List all account assignments
  - Options: `--account-id`, `--permission-set-arn`, `--principal-type`, `--principal-id`
- `assignment create`: Create a new account assignment
  - Options: `--account-id`, `--permission-set-arn`, `--principal-type`, `--principal-id`
- `assignment delete`: Delete an account assignment
  - Options: `--account-id`, `--permission-set-arn`, `--principal-type`, `--principal-id`
- `assignment bulk`: Perform bulk assignment operations
  - Options: `--input-file`, `--operation`

## Phase 4: Advanced Features

### Caching

- Implement caching for improved performance
- Cache user and group information
- Cache permission set information
- Cache assignment information

### Bulk Operations

- Implement bulk user operations
- Implement bulk group operations
- Implement bulk permission set operations
- Implement bulk assignment operations

### Reporting and Auditing

- Generate reports on users, groups, permission sets, and assignments
- Audit access and changes to Identity Center resources

## Implementation Details

### Configuration

- Configuration is stored in `~/.awsideman/config.json`
- Profiles are stored with region and SSO instance information
- Default profile is used if no profile is specified

### AWS SDK Integration

- Use boto3 for AWS API interactions
- Handle pagination for list operations
- Handle error handling and retries

### User Experience

- Use rich for beautiful terminal output
- Provide clear error messages
- Show progress for long-running operations
- Confirm destructive operations
