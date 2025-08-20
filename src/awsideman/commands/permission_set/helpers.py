"""Shared utilities for permission set management commands."""

import re
import sys
from typing import Any, Dict, Optional

import typer
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


def validate_profile(profile_name: Optional[str] = None) -> tuple[str, dict]:
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


def validate_sso_instance(profile_data: dict) -> tuple[str, str]:
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


def validate_permission_set_name(name: str) -> bool:
    """
    Validate permission set name format.

    Args:
        name: Permission set name to validate

    Returns:
        True if valid, False otherwise
    """
    if not name or len(name.strip()) == 0:
        return False

    # Permission set names should be alphanumeric with hyphens and underscores
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return False

    # Length should be reasonable (1-128 characters)
    if len(name) > 128:
        return False

    return True


def validate_permission_set_description(description: Optional[str]) -> bool:
    """
    Validate permission set description format.

    Args:
        description: Permission set description to validate

    Returns:
        True if valid, False otherwise
    """
    if description is None:
        return True  # Description is optional

    # Description should not be empty if provided
    if len(description.strip()) == 0:
        return False

    # Length should be reasonable (max 700 characters)
    if len(description) > 700:
        return False

    return True


def validate_aws_managed_policy_arn(policy_arn: str) -> bool:
    """
    Validate AWS managed policy ARN format.

    Args:
        policy_arn: Policy ARN to validate

    Returns:
        True if valid, False otherwise
    """
    if not policy_arn:
        return False

    # Check if it's a valid AWS managed policy ARN
    if not policy_arn.startswith("arn:aws:iam::aws:policy/"):
        return False

    # Extract policy name and validate format
    policy_name = policy_arn.split("/")[-1]
    if not policy_name or len(policy_name) == 0:
        return False

    return True


def format_permission_set_for_display(permission_set: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format permission set data for display in tables or output.

    Args:
        permission_set: Raw permission set data from AWS

    Returns:
        Formatted permission set data
    """
    formatted = permission_set.copy()

    # Format timestamps if present
    if "createdDate" in formatted:
        formatted["createdDate"] = str(formatted["createdDate"])

    if "lastModifiedDate" in formatted:
        formatted["lastModifiedDate"] = str(formatted["lastModifiedDate"])

    # Ensure required fields are present
    if "name" not in formatted:
        formatted["name"] = "N/A"

    if "description" not in formatted:
        formatted["description"] = "N/A"

    return formatted


def resolve_permission_set_identifier(
    sso_admin_client, instance_arn: str, identifier: str, identity_store_id: str
) -> str:
    """
    Resolve a permission set identifier to its ARN.

    Args:
        sso_admin_client: SSO Admin client
        instance_arn: SSO instance ARN
        identifier: Permission set identifier (name or ARN)
        identity_store_id: Identity store ID

    Returns:
        Permission set ARN

    Raises:
        typer.Exit: If permission set is not found
    """
    # If it's already an ARN, return it
    if identifier.startswith("arn:aws:sso:::permissionSet/"):
        return identifier

    # Search for permission sets by name
    try:
        response = sso_admin_client.list_permission_sets(InstanceArn=instance_arn)
    except Exception as e:
        console.print(f"[red]Error resolving permission set identifier: {str(e)}[/red]")
        raise typer.Exit(1)

    for permission_set_arn in response.get("PermissionSets", []):
        try:
            ps_response = sso_admin_client.describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
            )

            if ps_response["PermissionSet"]["Name"] == identifier:
                return permission_set_arn
        except Exception:
            continue

    # If not found, show error and exit
    console.print(f"[red]Error: Permission set '{identifier}' not found.[/red]")
    console.print("Use 'awsideman permission-set list' to see available permission sets.")
    raise typer.Exit(1)
