# Group Management Design Document

## Overview

The Group Management feature extends the awsideman CLI tool to provide comprehensive management capabilities for AWS Identity Center groups. This feature will enable administrators to list, get details, create, update, delete, and manage memberships of groups within the Identity Store. The implementation will follow the same command structure and patterns as the existing user management commands, ensuring a consistent user experience across the CLI tool.

## Architecture

The Group Management feature will be implemented as a new command module within the existing awsideman CLI architecture. It will leverage the existing utilities for AWS client management, configuration handling, and command-line interface components.

### Component Structure

```
src/awsideman/
├── commands/
│   ├── __init__.py
│   ├── profile.py
│   ├── sso.py
│   ├── user.py
│   └── group.py (new)
└── utils/
    ├── __init__.py
    ├── aws_client.py
    └── config.py
```

The new `group.py` module will contain all group-related commands and follow the same structure as the existing `user.py` module. It will be registered in the CLI application through the `__init__.py` file in the commands directory.

## Components and Interfaces

### Command Module

The Group Management feature will be implemented as a Typer command group with the following structure:

```python
app = typer.Typer(help="Manage groups in AWS Identity Center. Create, list, update, and delete groups in the Identity Store.")
```

### Commands

The module will include the following commands:

1. **list_groups**: List all groups in the Identity Store with optional filtering and pagination
2. **get_group**: Get detailed information about a specific group
3. **create_group**: Create a new group in the Identity Store
4. **update_group**: Update an existing group in the Identity Store
5. **delete_group**: Delete a group from the Identity Store
6. **list_members**: List all members of a specific group
7. **add_member**: Add a user to a group
8. **remove_member**: Remove a user from a group

### Shared Utilities

The group commands will use the same utility functions as the user commands:

- `validate_profile`: Validate the AWS profile and return profile data
- `validate_sso_instance`: Validate the SSO instance configuration
- `AWSClientManager`: Manage AWS client connections

### AWS API Integration

The commands will interact with the AWS Identity Store API through the boto3 client. The primary API methods used will be:

- `list_groups`: List groups in the Identity Store
- `describe_group`: Get detailed information about a group
- `create_group`: Create a new group
- `update_group`: Update an existing group
- `delete_group`: Delete a group
- `list_group_memberships`: List members of a group
- `create_group_membership`: Add a user to a group
- `delete_group_membership`: Remove a user from a group

## Data Models

### Group Model

The group data model will follow the AWS Identity Store API structure:

```python
{
    "GroupId": str,
    "DisplayName": str,
    "Description": str,
    "ExternalIds": [
        {
            "Issuer": str,
            "Id": str
        }
    ],
    "CreatedDate": datetime,
    "LastModifiedDate": datetime
}
```

### Group Membership Model

```python
{
    "MembershipId": str,
    "GroupId": str,
    "MemberId": {
        "UserId": str
    }
}
```

## Error Handling

The Group Management feature will implement comprehensive error handling to provide clear feedback to users. Error handling will include:

1. **Input Validation**: Validate command inputs before making API calls
2. **AWS API Error Handling**: Handle AWS API errors with clear error messages
3. **Resource Not Found Handling**: Provide specific error messages when groups or users are not found
4. **Permission Error Handling**: Display clear messages when the user lacks necessary permissions
5. **Network Error Handling**: Handle network issues with appropriate error messages and retry mechanisms

Error messages will be displayed using the Rich console with appropriate formatting and colors to enhance readability.

### Error Handling Examples

```python
try:
    # API call
    response = identity_store.create_group(...)
except ClientError as e:
    error_code = e.response.get("Error", {}).get("Code", "Unknown")
    error_message = e.response.get("Error", {}).get("Message", str(e))

    if error_code == "ResourceNotFoundException":
        console.print("[red]Error: The specified resource was not found.[/red]")
    elif error_code == "AccessDeniedException":
        console.print("[red]Error: You do not have permission to perform this action.[/red]")
    else:
        console.print(f"[red]Error ({error_code}): {error_message}[/red]")
    raise typer.Exit(1)
```

## Testing Strategy

The Group Management feature will be thoroughly tested using pytest with a focus on unit tests and mocking AWS API calls. The testing approach will follow the same pattern as the existing user command tests.

### Test Categories

1. **Unit Tests**: Test individual command functions with mocked AWS clients
2. **Integration Tests**: Test the integration between commands and AWS clients (with mocked responses)
3. **Error Handling Tests**: Test error handling for various error scenarios
4. **Parameter Validation Tests**: Test validation of command parameters

### Test Structure

Tests will be organized in the following structure:

```
tests/commands/
├── test_group_list.py
├── test_group_get.py
├── test_group_create.py
├── test_group_update.py
├── test_group_delete.py
├── test_group_members.py
└── test_group_helpers.py
```

### Test Example

```python
@patch("src.awsideman.commands.group.validate_profile")
@patch("src.awsideman.commands.group.validate_sso_instance")
@patch("src.awsideman.commands.group.AWSClientManager")
@patch("src.awsideman.commands.group.console")
def test_list_groups_successful(
    mock_console,
    mock_aws_client_manager,
    mock_validate_sso_instance,
    mock_validate_profile,
    mock_aws_client,
    sample_groups
):
    """Test successful list_groups operation."""
    # Setup mocks
    mock_client, mock_identity_store = mock_aws_client
    mock_aws_client_manager.return_value = mock_client
    mock_validate_profile.return_value = ("default", {"region": "us-east-1"})
    mock_validate_sso_instance.return_value = ("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")

    # Mock the list_groups API response
    mock_identity_store.list_groups.return_value = {
        "Groups": sample_groups,
        "NextToken": None
    }

    # Call the function
    result, next_token = list_groups()

    # Verify the function called the API correctly
    mock_identity_store.list_groups.assert_called_once_with(
        IdentityStoreId="d-1234567890"
    )

    # Verify the function returned the correct data
    assert result == sample_groups
    assert next_token is None
```

## Design Decisions and Rationales

### Command Structure

The Group Management feature will follow the same command structure as the existing user management commands to ensure consistency across the CLI tool. This approach leverages the existing patterns and utilities, reducing code duplication and ensuring a familiar user experience.

**Rationale**: Consistency in command structure makes the CLI tool easier to learn and use. Users familiar with the user management commands will be able to quickly understand and use the group management commands.

### Group Identification

Groups can be identified by either their display name or group ID. When a display name is provided, the system will search for the group by name. If multiple groups have the same name, the system will display a warning and use the first match.

**Rationale**: This approach provides flexibility for users who may not know the group ID but know the display name. It also handles the edge case where multiple groups have the same name.

### Pagination

The list commands will support pagination to handle large numbers of groups or group members. The pagination will be interactive by default, allowing users to press Enter to see the next page or any other key to exit.

**Rationale**: Interactive pagination provides a better user experience for exploring large datasets while still allowing users to exit when they have found what they need.

### Error Messages

Error messages will be detailed and specific, providing clear guidance on how to resolve issues. They will include AWS error codes and messages when available.

**Rationale**: Clear error messages help users understand and resolve issues quickly, improving the overall user experience.

### Group Membership Management

Group membership management will be implemented as separate commands (add_member, remove_member, list_members) rather than as options to the group command. This approach provides a clearer command structure and better separation of concerns.

**Rationale**: Separate commands for membership management provide a more intuitive interface for users and allow for more specific help text and error messages.

## Conclusion

The Group Management feature will extend the awsideman CLI tool with comprehensive group management capabilities, following the same patterns and structure as the existing user management commands. The implementation will focus on providing a consistent user experience, clear error messages, and comprehensive testing to ensure reliability and usability.
