"""Shared utilities for group management commands."""

import sys
from typing import Optional, Tuple

import typer
from botocore.exceptions import ClientError
from rich.console import Console

from ...utils.config import Config

# Shared console and config instances
console = Console()
config = Config()


def get_single_key():
    """
    Get a single key press without requiring Enter.

    Used for interactive pagination in the list command.
    Handles platform-specific keyboard input with fallbacks.
    """
    try:
        # Try to import platform-specific modules
        if sys.platform == "win32":
            import msvcrt

            return msvcrt.getch().decode("utf-8")
        else:
            import termios
            import tty

            # Save the terminal settings
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)

            try:
                # Set terminal to raw mode
                tty.setraw(sys.stdin.fileno())
                # Read a single character
                key = sys.stdin.read(1)
                return key
            finally:
                # Restore terminal settings
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except ImportError:
        # Fallback to input() if platform-specific modules are not available
        return input()
    except Exception:
        # Fallback to input() if anything goes wrong
        return input()


def validate_profile(profile_name: Optional[str] = None) -> Tuple[str, dict]:
    """
    Validate the profile and return profile name and data.

    This function checks if the specified profile exists or uses the default profile.
    It handles cases where no profile is specified and no default profile is set,
    or when the specified profile does not exist.

    Args:
        profile_name: AWS profile name to use

    Returns:
        Tuple of (profile_name, profile_data)

    Raises:
        typer.Exit: If profile validation fails with a clear error message
    """
    # Use the provided profile name or fall back to the default profile
    profile_name = profile_name or config.get("default_profile")

    # Check if a profile name is available
    if not profile_name:
        console.print("[red]Error: No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        raise typer.Exit(1)

    # Get all profiles and check if the specified profile exists
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Error: Profile '{profile_name}' does not exist.[/red]")
        console.print("Use 'awsideman profile add' to create a new profile.")
        raise typer.Exit(1)

    # Return the profile name and profile data
    return profile_name, profiles[profile_name]


def validate_sso_instance(profile_data: dict) -> Tuple[str, str]:
    """
    Validate the SSO instance configuration and return instance ARN and identity store ID.

    This function checks if the specified profile has an SSO instance configured.
    It handles cases where no SSO instance is configured for the profile and provides
    helpful guidance on how to configure an SSO instance.

    Args:
        profile_data: Profile data dictionary containing configuration

    Returns:
        Tuple of (instance_arn, identity_store_id)

    Raises:
        typer.Exit: If SSO instance validation fails with a clear error message and guidance
    """
    # Get the SSO instance ARN and identity store ID from the profile data
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    # Check if both the instance ARN and identity store ID are available
    if not instance_arn or not identity_store_id:
        console.print("[red]Error: No SSO instance configured for this profile.[/red]")
        console.print(
            "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
        )
        console.print("You can find available SSO instances with 'awsideman sso list'.")
        raise typer.Exit(1)

    # Return the instance ARN and identity store ID
    return instance_arn, identity_store_id


def validate_group_name(name: str) -> bool:
    """
    Validate a group name.

    Args:
        name: The group name to validate

    Returns:
        True if the name is valid, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if not name or name.strip() == "":
        console.print("[red]Error: Group name cannot be empty.[/red]")
        return False

    # Check length
    if len(name) > 128:
        console.print("[red]Error: Group name cannot exceed 128 characters.[/red]")
        return False

    # Check for invalid characters
    import re

    if not re.match(r"^[a-zA-Z0-9+=,.@_-]+$", name):
        console.print("[red]Error: Group name contains invalid characters.[/red]")
        console.print(
            "[yellow]Group names can only contain alphanumeric characters and the following special characters: +=,.@_-[/yellow]"
        )
        return False

    return True


def validate_group_description(description: Optional[str]) -> bool:
    """
    Validate a group description.

    Args:
        description: The group description to validate

    Returns:
        True if the description is valid, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if description is None:
        return True  # Description is optional

    if len(description) > 256:
        console.print("[red]Error: Group description cannot exceed 256 characters.[/red]")
        return False

    return True


def validate_filter(filter_str: str) -> bool:
    """
    Validate a filter string.

    Args:
        filter_str: The filter string to validate

    Returns:
        True if the filter is valid, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if not filter_str or filter_str.strip() == "":
        console.print("[red]Error: Filter cannot be empty.[/red]")
        return False

    # Check if filter is in the format "attribute=value"
    if "=" not in filter_str:
        console.print("[red]Error: Filter must be in the format 'attribute=value'.[/red]")
        return False

    attribute_path, attribute_value = filter_str.split("=", 1)
    if not attribute_path.strip() or not attribute_value.strip():
        console.print("[red]Error: Filter attribute and value cannot be empty.[/red]")
        return False

    return True


def validate_limit(limit: int) -> bool:
    """
    Validate a limit value.

    Args:
        limit: The limit value to validate

    Returns:
        True if the limit is valid, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if limit <= 0:
        console.print("[red]Error: Limit must be greater than 0.[/red]")
        return False

    if limit > 100:
        console.print("[red]Error: Limit cannot exceed 100.[/red]")
        return False

    return True


def validate_non_empty(value: str, field_name: str) -> bool:
    """
    Validate that a value is not empty.

    Args:
        value: The value to validate
        field_name: The name of the field for error messages

    Returns:
        True if the value is not empty, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if not value or value.strip() == "":
        console.print(f"[red]Error: {field_name} cannot be empty.[/red]")
        return False

    return True


def _find_user_id(identity_store_client, identity_store_id: str, user_identifier: str) -> str:
    """
    Find a user ID by username, email, or user ID.

    Args:
        identity_store_client: The identity store client
        identity_store_id: The identity store ID
        user_identifier: The user identifier (username, email, or user ID)

    Returns:
        The user ID

    Raises:
        typer.Exit: If user is not found
    """
    import re

    # Check if identifier is a UUID (user ID) or if we need to search
    uuid_pattern = (
        r"^(?:[0-9a-f]{10}-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )

    if re.match(uuid_pattern, user_identifier):
        # Direct lookup by user ID
        try:
            identity_store_client.describe_user(
                IdentityStoreId=identity_store_id,
                UserId=user_identifier,
            )
            return user_identifier
        except ClientError:
            console.print(f"[red]Error: User with ID '{user_identifier}' not found.[/red]")
            raise typer.Exit(1)
    else:
        # Search for user by username or email
        try:
            # Try searching by username first
            search_response = identity_store_client.list_users(
                IdentityStoreId=identity_store_id,
                Filters=[{"AttributePath": "UserName", "AttributeValue": user_identifier}],
            )

            users = search_response.get("Users", [])

            # If no users found by username, search by email
            if not users:
                # Get all users (with pagination if needed)
                all_users = []
                next_token = None

                while True:
                    list_params = {"IdentityStoreId": identity_store_id}
                    if next_token:
                        list_params["NextToken"] = next_token

                    list_response = identity_store_client.list_users(**list_params)
                    batch_users = list_response.get("Users", [])
                    all_users.extend(batch_users)

                    next_token = list_response.get("NextToken")
                    if not next_token:
                        break

                # Filter users by email manually
                for user in all_users:
                    emails = user.get("Emails", [])
                    for email in emails:
                        if email.get("Value", "").lower() == user_identifier.lower():
                            users.append(user)
                            break

            # Handle search results
            if not users:
                console.print(
                    f"[red]Error: No user found with username or email '{user_identifier}'.[/red]"
                )
                raise typer.Exit(1)
            elif len(users) > 1:
                console.print(
                    f"[yellow]Warning: Multiple users found matching '{user_identifier}'. Using the first match.[/yellow]"
                )

            return users[0].get("UserId")

        except ClientError as e:
            console.print(
                f"[red]Error searching for user: {e.response.get('Error', {}).get('Message', str(e))}[/red]"
            )
            raise typer.Exit(1)
