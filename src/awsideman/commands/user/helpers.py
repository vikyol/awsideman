"""Shared utilities for user management commands."""

import sys
from typing import Optional, Tuple

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


def format_user_for_display(user_data: dict) -> str:
    """Format user data for display in tables or output."""
    username = user_data.get("UserName", "N/A")
    display_name = user_data.get("DisplayName", "N/A")
    email = (
        user_data.get("Emails", [{}])[0].get("Value", "N/A") if user_data.get("Emails") else "N/A"
    )

    return f"{username} ({display_name}) - {email}"


def validate_email_format(email: str) -> bool:
    """Validate email format using basic regex pattern."""
    import re

    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_username_format(username: str) -> bool:
    """Validate username format for AWS Identity Center."""
    # Username must be 1-128 characters and contain only alphanumeric characters, underscores, and hyphens
    import re

    pattern = r"^[a-zA-Z0-9_-]{1,128}$"
    return re.match(pattern, username) is not None
