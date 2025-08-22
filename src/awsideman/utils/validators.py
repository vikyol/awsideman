"""Input validation utilities for awsideman."""

import re
from typing import Optional

import typer
from rich.console import Console

from ..aws_clients.manager import AWSClientManager
from .config import Config

console = Console()
config = Config()

# Regular expression patterns for validation
UUID_PATTERN = r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{10,})"
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
FILTER_PATTERN = r"^[a-zA-Z0-9_]+=[a-zA-Z0-9_@.-]+"


def validate_uuid(value: str, field_name: str = "identifier") -> bool:
    """
    Validate that a string is a valid UUID.

    Args:
        value: The string to validate
        field_name: The name of the field being validated (for error messages)

    Returns:
        True if the string is a valid UUID, False otherwise

    Raises:
        typer.Exit: If validation fails and exit_on_error is True
    """
    if not value:
        console.print(f"[red]Error: {field_name} cannot be empty.[/red]")
        return False

    if not re.match(UUID_PATTERN, value, re.IGNORECASE):
        console.print(f"[red]Error: {field_name} is not a valid UUID.[/red]")
        return False

    return True


def validate_email(value: str, field_name: str = "email") -> bool:
    """
    Validate that a string is a valid email address.

    Args:
        value: The string to validate
        field_name: The name of the field being validated (for error messages)

    Returns:
        True if the string is a valid email address, False otherwise

    Raises:
        typer.Exit: If validation fails and exit_on_error is True
    """
    if not value:
        console.print(f"[red]Error: {field_name} cannot be empty.[/red]")
        return False

    if not re.match(EMAIL_PATTERN, value):
        console.print(f"[red]Error: {field_name} is not a valid email address.[/red]")
        console.print(
            "[yellow]Email addresses should be in the format 'user@example.com'.[/yellow]"
        )
        return False

    return True


def validate_filter(value: str, field_name: str = "filter") -> bool:
    """
    Validate that a string is a valid filter expression.

    Args:
        value: The string to validate
        field_name: The name of the field being validated (for error messages)

    Returns:
        True if the string is a valid filter expression, False otherwise

    Raises:
        typer.Exit: If validation fails and exit_on_error is True
    """
    if not value:
        console.print(f"[red]Error: {field_name} cannot be empty.[/red]")
        return False

    if "=" not in value:
        console.print(f"[red]Error: {field_name} must be in the format 'attribute=value'.[/red]")
        console.print("[yellow]Example: DisplayName=Administrators[/yellow]")
        return False

    # Check if the filter matches the expected pattern
    if not re.match(FILTER_PATTERN, value):
        console.print(f"[red]Error: {field_name} contains invalid characters.[/red]")
        console.print(
            "[yellow]Filter should only contain letters, numbers, underscores, dots, hyphens, and @ symbols.[/yellow]"
        )
        return False

    return True


def validate_non_empty(value: str, field_name: str = "value") -> bool:
    """
    Validate that a string is not empty.

    Args:
        value: The string to validate
        field_name: The name of the field being validated (for error messages)

    Returns:
        True if the string is not empty, False otherwise

    Raises:
        typer.Exit: If validation fails and exit_on_error is True
    """
    if not value or value.strip() == "":
        console.print(f"[red]Error: {field_name} cannot be empty.[/red]")
        return False

    return True


def validate_limit(value: Optional[int], field_name: str = "limit") -> bool:
    """
    Validate that a limit value is positive.

    Args:
        value: The value to validate
        field_name: The name of the field being validated (for error messages)

    Returns:
        True if the value is valid, False otherwise

    Raises:
        typer.Exit: If validation fails and exit_on_error is True
    """
    if value is None:
        return True

    if value <= 0:
        console.print(f"[red]Error: {field_name} must be a positive integer.[/red]")
        return False

    return True


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
    if not validate_non_empty(name, "Group name"):
        return False

    # Check length
    if len(name) > 128:
        console.print("[red]Error: Group name cannot exceed 128 characters.[/red]")
        return False

    # Check for invalid characters
    if re.search(r"[<>%&\\\^\[\]\{\}]", name):
        console.print("[red]Error: Group name contains invalid characters.[/red]")
        console.print("[yellow]Group names cannot contain: < > % & \\ ^ [ ] { }[/yellow]")
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
        return True

    # Check length
    if len(description) > 1024:
        console.print("[red]Error: Group description cannot exceed 1024 characters.[/red]")
        return False

    return True


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


def validate_sso_instance(profile_data: dict, profile_name: str = None) -> tuple[str, str]:
    """
    Validate the SSO instance configuration and return instance ARN and identity store ID.

    This function checks if the specified profile has an SSO instance configured.
    If no SSO instance is configured, it attempts to auto-detect one when there's only
    one available in the AWS account. This implements the "lazy human" approach where
    awsideman automatically configures itself when possible.

    Args:
        profile_data: Profile data dictionary containing configuration
        profile_name: Profile name for auto-detection (optional)

    Returns:
        Tuple of (instance_arn, identity_store_id)

    Raises:
        typer.Exit: If SSO instance validation fails with a clear error message and guidance
    """
    # Get the SSO instance ARN and identity store ID from the profile data
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    # If both are configured, return them immediately
    if instance_arn and identity_store_id:
        return instance_arn, identity_store_id

    # If not configured, try to auto-detect
    if profile_name:
        try:
            console.print("[blue]No SSO instance configured. Attempting auto-detection...[/blue]")

            # Create AWS client manager to discover SSO instances
            region = profile_data.get("region")
            aws_client = AWSClientManager(profile=profile_name, region=region)

            # List available SSO instances
            sso_client = aws_client.get_identity_center_client()
            response = sso_client.list_instances()
            instances = response.get("Instances", [])

            if not instances:
                console.print("[red]Error: No SSO instances found in AWS account.[/red]")
                console.print(
                    "[yellow]Make sure your AWS profile has access to AWS Identity Center.[/yellow]"
                )
                raise typer.Exit(1)

            if len(instances) == 1:
                # Auto-configure the single instance
                instance = instances[0]
                auto_instance_arn = instance["InstanceArn"]
                auto_identity_store_id = instance["IdentityStoreId"]

                console.print(
                    f"[green]Auto-detected single SSO instance: {auto_instance_arn}[/green]"
                )
                console.print(f"[green]Identity Store ID: {auto_identity_store_id}[/green]")

                # Auto-save the configuration for future use
                try:
                    profiles = config.get("profiles", {})
                    if profile_name in profiles:
                        profiles[profile_name]["sso_instance_arn"] = auto_instance_arn
                        profiles[profile_name]["identity_store_id"] = auto_identity_store_id
                        config.set("profiles", profiles)
                        console.print(
                            f"[green]Auto-configured SSO instance for profile '{profile_name}'[/green]"
                        )
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not save auto-configuration: {str(e)}[/yellow]"
                    )
                    console.print("[yellow]Configuration will be lost after this session.[/yellow]")

                return auto_instance_arn, auto_identity_store_id

            else:
                # Multiple instances found - user must choose
                console.print(
                    f"[red]Error: Found {len(instances)} SSO instances. Auto-detection not possible.[/red]"
                )
                console.print("[yellow]Available instances:[/yellow]")
                for i, instance in enumerate(instances, 1):
                    instance_id = instance["InstanceArn"].split("/")[-1]
                    console.print(f"[yellow]  {i}. Instance ID: {instance_id}[/yellow]")
                console.print(
                    "\n[yellow]Please use 'awsideman sso set <instance_arn> <identity_store_id>' to configure one.[/yellow]"
                )
                console.print("[yellow]You can find full ARNs with 'awsideman sso list'.[/yellow]")
                raise typer.Exit(1)

        except Exception as e:
            console.print(f"[red]Error during SSO instance auto-detection: {str(e)}[/red]")
            console.print("[yellow]Falling back to manual configuration.[/yellow]")

    # If auto-detection failed or profile_name not provided, show manual configuration message
    console.print("[red]Error: No SSO instance configured for this profile.[/red]")
    console.print(
        "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
    )
    console.print("You can find available SSO instances with 'awsideman sso list'.")
    raise typer.Exit(1)
