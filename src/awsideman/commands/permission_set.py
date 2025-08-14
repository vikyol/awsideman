"""Permission set management commands for awsideman.

This module provides commands for managing permission sets in AWS Identity Center.
Permission sets define the level of access that users and groups have to AWS accounts.

Commands:
    list: List all permission sets in the Identity Center
    get: Get detailed information about a specific permission set
    create: Create a new permission set
    update: Update an existing permission set
    delete: Delete a permission set

Examples:
    # List all permission sets
    $ awsideman permission-set list

    # Get details for a specific permission set
    $ awsideman permission-set get AdminAccess

    # Create a new permission set with AWS managed policy
    $ awsideman permission-set create --name ReadOnlyAccess --description "Read-only access to all resources" --managed-policy arn:aws:iam::aws:policy/ReadOnlyAccess

    # Update a permission set
    $ awsideman permission-set update AdminAccess --description "Updated description" --add-managed-policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

    # Delete a permission set
    $ awsideman permission-set delete AdminAccess
"""

import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from rich.console import Console
from rich.table import Table

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config
from ..utils.error_handler import handle_aws_error, handle_network_error, with_retry
from ..utils.validators import validate_filter, validate_limit

app = typer.Typer(
    help="Manage permission sets in AWS Identity Center. Create, list, get, update, and delete permission sets."
)
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

    # Get the profile data
    profile_data = profiles[profile_name]

    # Check network connectivity if we have a region
    region = profile_data.get("region")
    if region:
        from ..utils.error_handler import check_network_connectivity

        check_network_connectivity(region)

    # Return the profile name and profile data
    return profile_name, profile_data


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


def _list_permission_sets_internal(
    filter: Optional[str] = None,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Internal implementation of list_permission_sets that can be called directly from tests.

    Args:
        filter: Filter permission sets by attribute in format 'attribute=value'
        limit: Maximum number of permission sets to return in a single page
        next_token: Pagination token
        profile: AWS profile to use

    Returns:
        Tuple of (permission_sets, next_token)
    """
    try:
        # Validate inputs
        if filter and not validate_filter(filter):
            raise typer.Exit(1)

        if not validate_limit(limit):
            raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Check if AWS_DEFAULT_REGION environment variable is set
        import os

        if os.environ.get("AWS_DEFAULT_REGION"):
            console.print(
                f"[yellow]Warning: AWS_DEFAULT_REGION environment variable is set to '{os.environ.get('AWS_DEFAULT_REGION')}'. This may override the region in your profile.[/yellow]"
            )

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, _ = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the SSO Admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Prepare the list_permission_sets API call parameters
        list_permission_sets_params = {"InstanceArn": instance_arn}

        # Add optional parameters if provided
        if limit:
            list_permission_sets_params["MaxResults"] = limit

        if next_token:
            list_permission_sets_params["NextToken"] = next_token

        # Make the API call to list permission sets
        response = sso_admin_client.list_permission_sets(**list_permission_sets_params)

        # Extract permission sets and next token from the response
        permission_set_arns = response.get("PermissionSets", [])
        next_token = response.get("NextToken")

        # If no permission sets found, return empty list
        if not permission_set_arns:
            console.print("[yellow]No permission sets found.[/yellow]")
            return [], next_token

        # Display pagination status
        page_info = ""
        if next_token:
            page_info = " (more results available)"
        if limit:
            page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"

        console.print(
            f"[green]Found {len(permission_set_arns)} permission sets{page_info}.[/green]"
        )

        # Create a table for displaying permission sets
        table = Table(title=f"Permission Sets in Identity Center Instance {instance_arn}")

        # Add columns to the table
        table.add_column("Name", style="green")
        table.add_column("ARN", style="cyan", no_wrap=False)
        table.add_column("Description", style="blue")
        table.add_column("Session Duration", style="magenta")

        # We need to get details for each permission set
        permission_sets = []
        filtered_permission_sets = []

        # Use with_retry decorator to handle transient errors
        @with_retry(max_retries=3, delay=1.0)
        def get_permission_set_details(instance_arn, permission_set_arn):
            return sso_admin_client.describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
            )

        for permission_set_arn in permission_set_arns:
            try:
                # Get permission set details with retry logic
                permission_set_response = get_permission_set_details(
                    instance_arn, permission_set_arn
                )
                permission_set = permission_set_response.get("PermissionSet", {})

                # Store the ARN in the permission set object for reference
                permission_set["PermissionSetArn"] = permission_set_arn
                permission_sets.append(permission_set)

                # Extract fields for display and filtering
                name = permission_set.get("Name", "")
                description = permission_set.get("Description", "")
                session_duration = permission_set.get("SessionDuration", "PT1H")
                relay_state = permission_set.get("RelayState", "")

                # Format session duration for display
                formatted_duration = session_duration
                if session_duration.startswith("PT"):
                    duration = session_duration[2:]
                    if "H" in duration:
                        hours = duration.split("H")[0]
                        formatted_duration = f"{hours} hour(s)"
                    elif "M" in duration:
                        minutes = duration.split("M")[0]
                        formatted_duration = f"{minutes} minute(s)"

                # Apply filtering if specified
                if filter:
                    # Check if filter is in the format "attribute=value"
                    if "=" not in filter:
                        raise ValueError("Filter must be in the format 'attribute=value'")

                    attribute_path, attribute_value = filter.split("=", 1)
                    attribute_value = attribute_value.lower()

                    # Skip this permission set if it doesn't match the filter
                    if attribute_path.lower() == "name" and attribute_value not in name.lower():
                        continue
                    elif (
                        attribute_path.lower() == "description"
                        and attribute_value not in description.lower()
                    ):
                        continue
                    elif (
                        attribute_path.lower() == "sessionduration"
                        and attribute_value not in session_duration.lower()
                    ):
                        continue
                    elif (
                        attribute_path.lower() == "relaystate"
                        and attribute_value not in relay_state.lower()
                    ):
                        continue
                    elif (
                        attribute_path.lower() == "arn"
                        and attribute_value not in permission_set_arn.lower()
                    ):
                        continue

                # Add the permission set to the filtered list
                filtered_permission_sets.append(permission_set)

                # Add the row to the table
                table.add_row(name, permission_set_arn, description or "N/A", formatted_duration)

            except ClientError as e:
                # Handle errors for individual permission sets
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_message = e.response.get("Error", {}).get("Message", str(e))
                console.print(
                    f"[yellow]Warning: Could not retrieve details for permission set {permission_set_arn}: {error_code} - {error_message}[/yellow]"
                )

                # Add a placeholder row with just the ARN
                table.add_row("Unknown", permission_set_arn, "Error retrieving details", "Unknown")

        # Display filtered results count if filtering was applied
        if filter and len(filtered_permission_sets) != len(permission_sets):
            console.print(
                f"[green]Filtered to {len(filtered_permission_sets)} permission sets matching '{filter}'.[/green]"
            )

        # Display the table
        console.print(table)

        # Handle pagination - interactive by default
        if next_token:
            # If next_token was explicitly provided as a parameter, return the results without interactive pagination
            if next_token != list_permission_sets_params.get("NextToken"):
                console.print(f"\n[blue]Next token for additional results: {next_token}[/blue]")
                console.print("[blue]Use --next-token parameter to retrieve the next page.[/blue]")
            else:
                console.print(
                    "\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]"
                )
                try:
                    # Wait for single key press
                    key = get_single_key()

                    # If the user pressed Enter (or Return), fetch the next page
                    if key in ["\r", "\n", ""]:
                        console.print("\n[blue]Fetching next page...[/blue]\n")
                        # Call _list_permission_sets_internal recursively with the next token
                        return _list_permission_sets_internal(
                            filter=filter, limit=limit, next_token=next_token, profile=profile
                        )
                    else:
                        console.print("\n[yellow]Pagination stopped.[/yellow]")
                        console.print(
                            f"[blue]To continue pagination later, use: --next-token {next_token}[/blue]"
                        )
                except KeyboardInterrupt:
                    console.print("\n[yellow]Pagination stopped by user.[/yellow]")
                    console.print(
                        f"[blue]To continue pagination later, use: --next-token {next_token}[/blue]"
                    )

        # Return the filtered permission sets and next token for further processing
        return filtered_permission_sets, next_token

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="ListPermissionSets")
        raise typer.Exit(1)
    except ValueError as e:
        # Handle filter format errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("[yellow]Filter format should be 'attribute=value'.[/yellow]")
        console.print("[yellow]Example: --filter Name=AdminAccess[/yellow]")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)


@app.command("list")
def list_permission_sets(
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter permission sets by attribute in format 'attribute=value' (e.g., Name=AdminAccess)",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of permission sets to return"
    ),
    next_token: Optional[str] = typer.Option(None, "--next-token", "-n", help="Pagination token"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """List all permission sets in the Identity Center.

    Displays a table of permission sets with their names, ARNs, descriptions, and session durations.
    Results can be filtered and paginated. Press ENTER to see the next page of results.

    Examples:
        # List all permission sets
        $ awsideman permission-set list

        # List permission sets with a name containing "Admin"
        $ awsideman permission-set list --filter Name=Admin

        # List up to 5 permission sets
        $ awsideman permission-set list --limit 5

        # List permission sets using a specific AWS profile
        $ awsideman permission-set list --profile dev-account

        # Continue pagination from a previous request
        $ awsideman permission-set list --next-token ABCDEF123456
    """
    return _list_permission_sets_internal(filter, limit, next_token, profile)


@app.command("get")
def get_permission_set(
    identifier: str = typer.Argument(..., help="Permission set name or ARN"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Get detailed information about a specific permission set.

    Retrieves and displays comprehensive information about a permission set by its name or ARN.
    Shows all available permission set attributes including name, ARN, description, session duration,
    relay state, creation date, last modified date, and attached AWS managed policies.

    Examples:
        # Get permission set by name
        $ awsideman permission-set get AdminAccess

        # Get permission set by ARN
        $ awsideman permission-set get arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef

        # Get permission set using a specific AWS profile
        $ awsideman permission-set get AdminAccess --profile dev-account
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, _ = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Resolve the permission set identifier to an ARN
        permission_set_arn = resolve_permission_set_identifier(aws_client, instance_arn, identifier)

        # Get the SSO Admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Use with_retry decorator to handle transient errors
        @with_retry(max_retries=3, delay=1.0)
        def get_permission_set_details(instance_arn, permission_set_arn):
            return sso_admin_client.describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
            )

        @with_retry(max_retries=3, delay=1.0)
        def get_managed_policies(instance_arn, permission_set_arn):
            return sso_admin_client.list_managed_policies_in_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
            )

        try:
            # Get permission set details with retry logic
            permission_set_response = get_permission_set_details(instance_arn, permission_set_arn)
            permission_set = permission_set_response.get("PermissionSet", {})

            # Store the ARN in the permission set object for reference
            permission_set["PermissionSetArn"] = permission_set_arn

            # Format the permission set data for display
            formatted_permission_set = format_permission_set_for_display(permission_set)

            # Get managed policies attached to the permission set
            managed_policies_response = get_managed_policies(instance_arn, permission_set_arn)
            managed_policies = managed_policies_response.get("AttachedManagedPolicies", [])

            # Create a Rich panel for displaying the permission set details
            from rich.panel import Panel
            from rich.table import Table

            # Create a table for the permission set details
            details_table = Table(show_header=False, box=None)
            details_table.add_column("Attribute", style="cyan")
            details_table.add_column("Value")

            # Add rows for each attribute
            for key, value in formatted_permission_set.items():
                details_table.add_row(key, str(value))

            # Create a table for the managed policies
            policies_table = Table(title="Attached AWS Managed Policies", show_header=True)
            policies_table.add_column("Name", style="green")
            policies_table.add_column("ARN", style="cyan")

            # Add rows for each policy
            if managed_policies:
                for policy in managed_policies:
                    policy_name = policy.get("Name", "N/A")
                    policy_arn = policy.get("Arn", "N/A")
                    policies_table.add_row(policy_name, policy_arn)
            else:
                policies_table.add_row("No managed policies attached", "")

            # Create a panel for the permission set details
            panel = Panel(
                details_table,
                title=f"Permission Set: {permission_set.get('Name', 'Unknown')}",
                expand=False,
            )

            # Display the panel and policies table
            console.print(panel)
            console.print(policies_table)

            return permission_set

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: Permission set '{identifier}' not found.[/red]")
                console.print(
                    "[yellow]Check the permission set name or ARN and try again.[/yellow]"
                )
                console.print(
                    "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
                )
            else:
                console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                console.print(
                    "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                )

            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="GetPermissionSet")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)


@app.command("create")
def create_permission_set(
    name: str = typer.Option(..., "--name", help="Name for the permission set"),
    description: Optional[str] = typer.Option(
        None, "--description", help="Description for the permission set"
    ),
    session_duration: Optional[str] = typer.Option(
        "PT1H",
        "--session-duration",
        help="Session duration (ISO-8601 format, e.g., PT1H for 1 hour, PT30M for 30 minutes)",
    ),
    relay_state: Optional[str] = typer.Option(
        None,
        "--relay-state",
        help="Relay state URL (the URL users are redirected to after federation)",
    ),
    managed_policy: Optional[List[str]] = typer.Option(
        None,
        "--managed-policy",
        help="AWS-managed policy ARN to attach (can be specified multiple times)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Create a new permission set in the Identity Center.

    Creates a new permission set with the specified attributes and optionally attaches AWS-managed policies.
    Displays the created permission set details upon successful creation.

    The permission set name must be unique within the Identity Center instance and can contain
    alphanumeric characters and the following special characters: +=,.@_-

    Session duration must be in ISO-8601 format (e.g., PT1H for 1 hour, PT8H for 8 hours, PT30M for 30 minutes).

    Examples:
        # Create a basic permission set
        $ awsideman permission-set create --name BasicAccess --description "Basic access to AWS resources"

        # Create a permission set with custom session duration
        $ awsideman permission-set create --name LongSession --description "Extended session" --session-duration PT8H

        # Create a permission set with AWS managed policy
        $ awsideman permission-set create --name AdminAccess --managed-policy arn:aws:iam::aws:policy/AdministratorAccess

        # Create a permission set with multiple AWS managed policies
        $ awsideman permission-set create --name PowerUser --managed-policy arn:aws:iam::aws:policy/PowerUserAccess --managed-policy arn:aws:iam::aws:policy/AmazonS3FullAccess

        # Create a permission set with relay state URL
        $ awsideman permission-set create --name S3Access --relay-state https://console.aws.amazon.com/s3/
    """
    try:
        # Validate inputs
        if not validate_permission_set_name(name):
            raise typer.Exit(1)

        if description is not None and not validate_permission_set_description(description):
            raise typer.Exit(1)

        # Validate managed policy ARNs if provided
        if managed_policy:
            for policy_arn in managed_policy:
                if not validate_aws_managed_policy_arn(policy_arn):
                    raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, _ = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the SSO Admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Prepare the create_permission_set API call parameters
        create_permission_set_params = {"InstanceArn": instance_arn, "Name": name}

        # Add optional parameters if provided
        if description:
            create_permission_set_params["Description"] = description

        if session_duration:
            create_permission_set_params["SessionDuration"] = session_duration

        if relay_state:
            create_permission_set_params["RelayState"] = relay_state

        # Display a message indicating that we're creating the permission set
        console.print(f"[blue]Creating permission set '{name}'...[/blue]")

        # Use with_retry decorator to handle transient errors
        @with_retry(max_retries=3, delay=1.0)
        def create_permission_set_with_retry(params):
            return sso_admin_client.create_permission_set(**params)

        try:
            # Make the API call to create the permission set
            response = create_permission_set_with_retry(create_permission_set_params)

            # Extract the permission set ARN from the response
            permission_set_arn = None
            if "PermissionSet" in response and "PermissionSetArn" in response["PermissionSet"]:
                permission_set_arn = response["PermissionSet"]["PermissionSetArn"]
            else:
                permission_set_arn = response.get("PermissionSetArn")

            if not permission_set_arn:
                console.print("[red]Error: Failed to create permission set. No ARN returned.[/red]")
                raise typer.Exit(1)

            console.print(f"[green]Permission set '{name}' created successfully.[/green]")
            console.print(f"[green]Permission Set ARN: {permission_set_arn}[/green]")

            # Attach managed policies if provided
            attached_policies = []
            if managed_policy:
                console.print(f"[blue]Attaching {len(managed_policy)} managed policies...[/blue]")

                # Use with_retry decorator to handle transient errors
                @with_retry(max_retries=3, delay=1.0)
                def attach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn):
                    return sso_admin_client.attach_managed_policy_to_permission_set(
                        InstanceArn=instance_arn,
                        PermissionSetArn=permission_set_arn,
                        ManagedPolicyArn=policy_arn,
                    )

                for policy_arn in managed_policy:
                    try:
                        # Validate the policy ARN again (redundant but safe)
                        if not validate_aws_managed_policy_arn(policy_arn):
                            console.print(
                                f"[yellow]Skipping invalid policy ARN: {policy_arn}[/yellow]"
                            )
                            continue

                        # Make the API call to attach the managed policy
                        attach_managed_policy_with_retry(
                            instance_arn, permission_set_arn, policy_arn
                        )

                        # Extract the policy name from the ARN for display
                        policy_name = policy_arn.split("/")[-1]
                        console.print(f"[green]Attached policy: {policy_name}[/green]")

                        # Add the policy to the list of attached policies
                        attached_policies.append({"Name": policy_name, "Arn": policy_arn})

                    except ClientError as e:
                        error_code = e.response.get("Error", {}).get("Code", "Unknown")
                        error_message = e.response.get("Error", {}).get("Message", str(e))

                        console.print(
                            f"[yellow]Warning: Failed to attach policy {policy_arn}: {error_code} - {error_message}[/yellow]"
                        )
                        console.print(
                            "[yellow]The permission set was created but not all policies were attached.[/yellow]"
                        )

            # Get the full permission set details to display
            try:
                # Use with_retry decorator to handle transient errors
                @with_retry(max_retries=3, delay=1.0)
                def get_permission_set_details(instance_arn, permission_set_arn):
                    return sso_admin_client.describe_permission_set(
                        InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                    )

                # Get permission set details with retry logic
                permission_set_response = get_permission_set_details(
                    instance_arn, permission_set_arn
                )
                permission_set = permission_set_response.get("PermissionSet", {})

                # Store the ARN in the permission set object for reference
                permission_set["PermissionSetArn"] = permission_set_arn

                # Format the permission set data for display
                formatted_permission_set = format_permission_set_for_display(permission_set)

                # Create a Rich panel for displaying the permission set details
                from rich.panel import Panel
                from rich.table import Table

                # Create a table for the permission set details
                details_table = Table(show_header=False, box=None)
                details_table.add_column("Attribute", style="cyan")
                details_table.add_column("Value")

                # Add rows for each attribute
                for key, value in formatted_permission_set.items():
                    details_table.add_row(key, str(value))

                # Create a table for the managed policies
                policies_table = Table(title="Attached AWS Managed Policies", show_header=True)
                policies_table.add_column("Name", style="green")
                policies_table.add_column("ARN", style="cyan")

                # Add rows for each policy
                if attached_policies:
                    for policy in attached_policies:
                        policy_name = policy.get("Name", "N/A")
                        policy_arn = policy.get("Arn", "N/A")
                        policies_table.add_row(policy_name, policy_arn)
                else:
                    policies_table.add_row("No managed policies attached", "")

                # Create a panel for the permission set details
                panel = Panel(
                    details_table,
                    title=f"Permission Set: {permission_set.get('Name', 'Unknown')}",
                    expand=False,
                )

                # Display the panel and policies table
                console.print(panel)
                console.print(policies_table)

            except ClientError:
                # Just log a warning if we can't get the details, but don't fail the command
                console.print(
                    "[yellow]Warning: Could not retrieve full permission set details after creation.[/yellow]"
                )

            return {
                "PermissionSetArn": permission_set_arn,
                "Name": name,
                "Description": description,
                "SessionDuration": session_duration,
                "RelayState": relay_state,
                "AttachedManagedPolicies": attached_policies,
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ConflictException":
                console.print(f"[red]Error: Permission set '{name}' already exists.[/red]")
                console.print(
                    "[yellow]Use a different name or use 'awsideman permission-set update' to modify an existing permission set.[/yellow]"
                )
            else:
                console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                console.print(
                    "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                )

            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="CreatePermissionSet")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)


@app.command("update")
def update_permission_set(
    identifier: str = typer.Argument(..., help="Permission set name or ARN"),
    description: Optional[str] = typer.Option(
        None, "--description", help="Description for the permission set"
    ),
    session_duration: Optional[str] = typer.Option(
        None,
        "--session-duration",
        help="Session duration (ISO-8601 format, e.g., PT1H for 1 hour, PT30M for 30 minutes)",
    ),
    relay_state: Optional[str] = typer.Option(
        None,
        "--relay-state",
        help="Relay state URL (the URL users are redirected to after federation)",
    ),
    add_managed_policy: Optional[List[str]] = typer.Option(
        None,
        "--add-managed-policy",
        help="AWS-managed policy ARN to attach (can be specified multiple times)",
    ),
    remove_managed_policy: Optional[List[str]] = typer.Option(
        None,
        "--remove-managed-policy",
        help="AWS-managed policy ARN to detach (can be specified multiple times)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Update an existing permission set in the Identity Center.

    Updates the specified permission set with new attribute values and/or modifies attached policies.
    Displays the updated permission set details upon successful update.

    You can update the description, session duration, relay state, and attached AWS managed policies.
    Only the attributes you specify will be updated; others will remain unchanged.

    Examples:
        # Update permission set description
        $ awsideman permission-set update AdminAccess --description "Updated administrator access"

        # Update session duration
        $ awsideman permission-set update AdminAccess --session-duration PT4H

        # Update relay state URL
        $ awsideman permission-set update AdminAccess --relay-state https://console.aws.amazon.com/ec2/

        # Add an AWS managed policy
        $ awsideman permission-set update AdminAccess --add-managed-policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

        # Remove an AWS managed policy
        $ awsideman permission-set update AdminAccess --remove-managed-policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

        # Update multiple attributes at once
        $ awsideman permission-set update AdminAccess --description "Updated access" --session-duration PT2H --add-managed-policy arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess
    """
    try:
        # Validate inputs
        if description is not None and not validate_permission_set_description(description):
            raise typer.Exit(1)

        # Validate managed policy ARNs if provided
        if add_managed_policy:
            for policy_arn in add_managed_policy:
                if not validate_aws_managed_policy_arn(policy_arn):
                    raise typer.Exit(1)

        if remove_managed_policy:
            for policy_arn in remove_managed_policy:
                if not validate_aws_managed_policy_arn(policy_arn):
                    raise typer.Exit(1)

        # Check if any update parameters were provided
        if not any(
            [
                description is not None,
                session_duration is not None,
                relay_state is not None,
                add_managed_policy is not None,
                remove_managed_policy is not None,
            ]
        ):
            console.print(
                "[yellow]Warning: No update parameters provided. Nothing to update.[/yellow]"
            )
            console.print(
                "[yellow]Use --description, --session-duration, --relay-state, --add-managed-policy, or --remove-managed-policy to specify updates.[/yellow]"
            )
            raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, _ = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the SSO Admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Resolve the permission set identifier to an ARN
        permission_set_arn = resolve_permission_set_identifier(aws_client, instance_arn, identifier)

        # Display a message indicating that we're updating the permission set
        console.print(f"[blue]Updating permission set '{identifier}'...[/blue]")

        # Check if we need to update the permission set attributes
        if any([description is not None, session_duration is not None, relay_state is not None]):
            # Prepare the update_permission_set API call parameters
            update_permission_set_params = {
                "InstanceArn": instance_arn,
                "PermissionSetArn": permission_set_arn,
            }

            # Add optional parameters if provided
            if description is not None:
                update_permission_set_params["Description"] = description

            if session_duration is not None:
                update_permission_set_params["SessionDuration"] = session_duration

            if relay_state is not None:
                update_permission_set_params["RelayState"] = relay_state

            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def update_permission_set_with_retry(params):
                return sso_admin_client.update_permission_set(**params)

            try:
                # Make the API call to update the permission set
                update_permission_set_with_retry(update_permission_set_params)

                # Log the successful update
                console.print("[green]Permission set attributes updated successfully.[/green]")

                # Log which attributes were updated
                if description is not None:
                    console.print(f"[green]Updated description: {description}[/green]")
                if session_duration is not None:
                    console.print(f"[green]Updated session duration: {session_duration}[/green]")
                if relay_state is not None:
                    console.print(f"[green]Updated relay state: {relay_state}[/green]")

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_message = e.response.get("Error", {}).get("Message", str(e))

                if error_code == "ResourceNotFoundException":
                    console.print(f"[red]Error: Permission set '{identifier}' not found.[/red]")
                    console.print(
                        "[yellow]Check the permission set name or ARN and try again.[/yellow]"
                    )
                    console.print(
                        "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
                    )
                else:
                    console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                    console.print(
                        "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                    )

                raise typer.Exit(1)

        # Handle managed policy attachment and detachment
        attached_policies = []
        detached_policies = []

        # Attach managed policies if provided
        if add_managed_policy:
            console.print(f"[blue]Attaching {len(add_managed_policy)} managed policies...[/blue]")

            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def attach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn):
                return sso_admin_client.attach_managed_policy_to_permission_set(
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy_arn,
                )

            for policy_arn in add_managed_policy:
                try:
                    # Validate the policy ARN again (redundant but safe)
                    if not validate_aws_managed_policy_arn(policy_arn):
                        console.print(f"[yellow]Skipping invalid policy ARN: {policy_arn}[/yellow]")
                        continue

                    # Make the API call to attach the managed policy
                    attach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn)

                    # Extract the policy name from the ARN for display
                    policy_name = policy_arn.split("/")[-1]
                    console.print(f"[green]Attached policy: {policy_name}[/green]")

                    # Add the policy to the list of attached policies
                    attached_policies.append({"Name": policy_name, "Arn": policy_arn})

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    if error_code == "ConflictException":
                        console.print(
                            f"[yellow]Policy {policy_arn} is already attached to this permission set.[/yellow]"
                        )
                    else:
                        console.print(
                            f"[yellow]Warning: Failed to attach policy {policy_arn}: {error_code} - {error_message}[/yellow]"
                        )
                        console.print(
                            "[yellow]The permission set was updated but not all policies were attached.[/yellow]"
                        )

        # Detach managed policies if provided
        if remove_managed_policy:
            console.print(
                f"[blue]Detaching {len(remove_managed_policy)} managed policies...[/blue]"
            )

            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def detach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn):
                return sso_admin_client.detach_managed_policy_from_permission_set(
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy_arn,
                )

            for policy_arn in remove_managed_policy:
                try:
                    # Validate the policy ARN again (redundant but safe)
                    if not validate_aws_managed_policy_arn(policy_arn):
                        console.print(f"[yellow]Skipping invalid policy ARN: {policy_arn}[/yellow]")
                        continue

                    # Make the API call to detach the managed policy
                    detach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn)

                    # Extract the policy name from the ARN for display
                    policy_name = policy_arn.split("/")[-1]
                    console.print(f"[green]Detached policy: {policy_name}[/green]")

                    # Add the policy to the list of detached policies
                    detached_policies.append({"Name": policy_name, "Arn": policy_arn})

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    if error_code == "ResourceNotFoundException":
                        console.print(
                            f"[yellow]Policy {policy_arn} is not attached to this permission set.[/yellow]"
                        )
                    else:
                        console.print(
                            f"[yellow]Warning: Failed to detach policy {policy_arn}: {error_code} - {error_message}[/yellow]"
                        )
                        console.print(
                            "[yellow]The permission set was updated but not all policies were detached.[/yellow]"
                        )

        # Get the updated permission set details to display
        try:
            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def get_permission_set_details(instance_arn, permission_set_arn):
                return sso_admin_client.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                )

            @with_retry(max_retries=3, delay=1.0)
            def get_managed_policies(instance_arn, permission_set_arn):
                return sso_admin_client.list_managed_policies_in_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                )

            # Get permission set details with retry logic
            permission_set_response = get_permission_set_details(instance_arn, permission_set_arn)
            permission_set = permission_set_response.get("PermissionSet", {})

            # Store the ARN in the permission set object for reference
            permission_set["PermissionSetArn"] = permission_set_arn

            # Format the permission set data for display
            formatted_permission_set = format_permission_set_for_display(permission_set)

            # Get managed policies attached to the permission set
            managed_policies_response = get_managed_policies(instance_arn, permission_set_arn)
            managed_policies = managed_policies_response.get("AttachedManagedPolicies", [])

            # Create a Rich panel for displaying the permission set details
            from rich.panel import Panel
            from rich.table import Table

            # Create a table for the permission set details
            details_table = Table(show_header=False, box=None)
            details_table.add_column("Attribute", style="cyan")
            details_table.add_column("Value")

            # Add rows for each attribute
            for key, value in formatted_permission_set.items():
                details_table.add_row(key, str(value))

            # Create a table for the managed policies
            policies_table = Table(title="Attached AWS Managed Policies", show_header=True)
            policies_table.add_column("Name", style="green")
            policies_table.add_column("ARN", style="cyan")

            # Add rows for each policy
            if managed_policies:
                for policy in managed_policies:
                    policy_name = policy.get("Name", "N/A")
                    policy_arn = policy.get("Arn", "N/A")
                    policies_table.add_row(policy_name, policy_arn)
            else:
                policies_table.add_row("No managed policies attached", "")

            # Create a panel for the permission set details
            panel = Panel(
                details_table,
                title=f"Updated Permission Set: {permission_set.get('Name', 'Unknown')}",
                expand=False,
            )

            # Display the panel and policies table
            console.print("\n[green]Permission set updated successfully.[/green]")
            console.print(panel)
            console.print(policies_table)

            # Display a summary of changes
            if attached_policies or detached_policies:
                changes_table = Table(title="Policy Changes Summary", show_header=True)
                changes_table.add_column("Action", style="cyan")
                changes_table.add_column("Policy Name", style="green")
                changes_table.add_column("Policy ARN", style="blue")

                for policy in attached_policies:
                    changes_table.add_row(
                        "Attached", policy.get("Name", "N/A"), policy.get("Arn", "N/A")
                    )

                for policy in detached_policies:
                    changes_table.add_row(
                        "Detached", policy.get("Name", "N/A"), policy.get("Arn", "N/A")
                    )

                console.print(changes_table)

            return {
                "PermissionSet": permission_set,
                "AttachedManagedPolicies": managed_policies,
                "AttachedPolicies": attached_policies,
                "DetachedPolicies": detached_policies,
            }

        except ClientError as e:
            # Just log a warning if we can't get the details, but don't fail the command
            console.print(
                "[yellow]Warning: Could not retrieve full permission set details after update.[/yellow]"
            )
            console.print(
                f"[yellow]Error: {e.response.get('Error', {}).get('Code', 'Unknown')} - {e.response.get('Error', {}).get('Message', str(e))}[/yellow]"
            )
            console.print(
                "[yellow]The permission set was updated but the updated details could not be displayed.[/yellow]"
            )

            return {
                "PermissionSetArn": permission_set_arn,
                "AttachedPolicies": attached_policies,
                "DetachedPolicies": detached_policies,
            }

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="UpdatePermissionSet")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)


def validate_permission_set_name(name: str) -> bool:
    """
    Validate a permission set name.

    Args:
        name: The permission set name to validate

    Returns:
        True if the name is valid, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if not name or name.strip() == "":
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        return False

    # Check length
    if len(name) > 32:
        console.print("[red]Error: Permission set name cannot exceed 32 characters.[/red]")
        return False

    # Check for invalid characters
    if not re.match(r"^[a-zA-Z0-9+=,.@_-]+$$", name):
        console.print("[red]Error: Permission set name contains invalid characters.[/red]")
        console.print(
            "[yellow]Permission set names can only contain alphanumeric characters and the following special characters: +=,.@_-[/yellow]"
        )
        return False

    return True


def validate_permission_set_description(description: Optional[str]) -> bool:
    """
    Validate a permission set description.

    Args:
        description: The permission set description to validate

    Returns:
        True if the description is valid, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if description is None:
        return True

    # Check length
    if len(description) > 700:
        console.print("[red]Error: Permission set description cannot exceed 700 characters.[/red]")
        return False

    return True


def validate_aws_managed_policy_arn(policy_arn: str) -> bool:
    """
    Validate an AWS managed policy ARN.

    Args:
        policy_arn: The policy ARN to validate

    Returns:
        True if the ARN is valid, False otherwise

    Raises:
        typer.Exit: If validation fails
    """
    if not policy_arn or policy_arn.strip() == "":
        console.print("[red]Error: Policy ARN cannot be empty.[/red]")
        return False

    # Check if it's an ARN
    if not policy_arn.startswith("arn:aws:iam::aws:policy/"):
        console.print("[red]Error: Invalid AWS managed policy ARN.[/red]")
        console.print(
            "[yellow]AWS managed policy ARNs should start with 'arn:aws:iam::aws:policy/'.[/yellow]"
        )
        console.print("[yellow]Example: arn:aws:iam::aws:policy/AdministratorAccess[/yellow]")
        return False

    return True


def format_permission_set_for_display(permission_set: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format permission set data for display.

    Args:
        permission_set: Permission set data from AWS API

    Returns:
        Formatted permission set data
    """
    formatted = {}

    # Extract and format basic fields
    formatted["Name"] = permission_set.get("Name", "N/A")
    formatted["ARN"] = permission_set.get("PermissionSetArn", "N/A")
    formatted["Description"] = permission_set.get("Description", "N/A")

    # Format session duration
    session_duration = permission_set.get("SessionDuration", "PT1H")
    # Convert ISO-8601 duration to a more readable format if possible
    if session_duration.startswith("PT"):
        duration = session_duration[2:]
        if "H" in duration:
            hours = duration.split("H")[0]
            formatted["Session Duration"] = f"{hours} hour(s)"
        elif "M" in duration:
            minutes = duration.split("M")[0]
            formatted["Session Duration"] = f"{minutes} minute(s)"
        else:
            formatted["Session Duration"] = session_duration
    else:
        formatted["Session Duration"] = session_duration

    # Format relay state
    formatted["Relay State"] = permission_set.get("RelayState", "N/A")

    # Format creation and last modified dates
    created_date = permission_set.get("CreatedDate")
    if created_date:
        formatted["Created"] = created_date.strftime("%Y-%m-%d %H:%M:%S")

    last_modified = permission_set.get("LastModifiedDate")
    if last_modified:
        formatted["Last Modified"] = last_modified.strftime("%Y-%m-%d %H:%M:%S")

    return formatted


def resolve_permission_set_identifier(
    aws_client: AWSClientManager, instance_arn: str, identifier: str
) -> str:
    """
    Resolve a permission set identifier (name or ARN) to its ARN.

    This function determines if the identifier is an ARN or a name.
    If it's a name, it looks up the ARN using the ListPermissionSets API.

    Args:
        aws_client: AWSClientManager instance for making AWS API calls
        instance_arn: SSO instance ARN
        identifier: Permission set name or ARN

    Returns:
        Permission set ARN

    Raises:
        typer.Exit: If the permission set cannot be found
    """
    # Check if the identifier is already an ARN
    if identifier.startswith("arn:aws:"):
        return identifier

    # If not an ARN, treat as a name and look up the ARN
    try:
        # Get the SSO Admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # List all permission sets
        paginator = sso_admin_client.get_paginator("list_permission_sets")
        found_permission_set_arn = None

        # Iterate through pages of permission sets
        for page in paginator.paginate(InstanceArn=instance_arn):
            permission_set_arns = page.get("PermissionSets", [])

            # For each permission set ARN, get details to check the name
            for permission_set_arn in permission_set_arns:
                response = sso_admin_client.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                )

                permission_set = response.get("PermissionSet", {})
                if permission_set.get("Name") == identifier:
                    found_permission_set_arn = permission_set_arn
                    break

            # If we found the permission set, no need to check more pages
            if found_permission_set_arn:
                break

        # If we found the permission set, return its ARN
        if found_permission_set_arn:
            return found_permission_set_arn

        # If we didn't find the permission set, raise an error
        console.print(f"[red]Error: Permission set with name '{identifier}' not found.[/red]")
        console.print("[yellow]Check the permission set name and try again.[/yellow]")
        console.print(
            "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
        )
        raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, "ListPermissionSets")
        raise  # Re-raise the exception after handling it
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise  # Re-raise the exception after handling it


@app.command("delete")
def delete_permission_set(
    identifier: str = typer.Argument(..., help="Permission set name or ARN"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Delete a permission set from the Identity Center.

    Permanently removes a permission set from the Identity Center.
    Requires confirmation before deletion to prevent accidental removal.

    Warning: This action cannot be undone. If the permission set is assigned to users or groups,
    those assignments will also be removed. The permission set must not be in use by any account
    assignments, or the deletion will fail.

    Examples:
        # Delete a permission set by name
        $ awsideman permission-set delete AdminAccess

        # Delete a permission set by ARN
        $ awsideman permission-set delete arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef

        # Delete a permission set using a specific AWS profile
        $ awsideman permission-set delete AdminAccess --profile dev-account
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, _ = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Resolve the permission set identifier to an ARN
        permission_set_arn = resolve_permission_set_identifier(aws_client, instance_arn, identifier)

        # Get the permission set details for confirmation
        sso_admin_client = aws_client.get_client("sso-admin")

        # Use with_retry decorator to handle transient errors
        @with_retry(max_retries=3, delay=1.0)
        def get_permission_set_details(instance_arn, permission_set_arn):
            return sso_admin_client.describe_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
            )

        # Get permission set details with retry logic
        permission_set_response = get_permission_set_details(instance_arn, permission_set_arn)
        permission_set = permission_set_response.get("PermissionSet", {})
        permission_set_name = permission_set.get("Name", "Unknown")

        # Format the permission set data for display
        formatted_permission_set = format_permission_set_for_display(permission_set)

        # Create a Rich panel for displaying the permission set details
        from rich.panel import Panel
        from rich.table import Table

        # Create a table for the permission set details
        details_table = Table(show_header=False, box=None)
        details_table.add_column("Attribute", style="cyan")
        details_table.add_column("Value")

        # Add rows for each attribute
        for key, value in formatted_permission_set.items():
            details_table.add_row(key, str(value))

        # Create a panel for the permission set details
        panel = Panel(
            details_table, title=f"Permission Set to Delete: {permission_set_name}", expand=False
        )

        # Display the panel
        console.print(panel)

        # Display warning about deletion
        console.print(
            "[yellow]Warning: This action cannot be undone. The permission set will be permanently deleted.[/yellow]"
        )
        console.print(
            "[yellow]If this permission set is assigned to users or groups, those assignments will also be removed.[/yellow]"
        )

        # Ask for confirmation before deletion
        confirmation = typer.confirm("Are you sure you want to delete this permission set?")
        if not confirmation:
            console.print("[yellow]Deletion cancelled.[/yellow]")
            return

        # Display a message indicating that we're deleting the permission set
        console.print(f"[blue]Deleting permission set '{permission_set_name}'...[/blue]")

        # Use with_retry decorator to handle transient errors
        @with_retry(max_retries=3, delay=1.0)
        def delete_permission_set_with_retry(instance_arn, permission_set_arn):
            return sso_admin_client.delete_permission_set(
                InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
            )

        try:
            # Make the API call to delete the permission set
            delete_permission_set_with_retry(instance_arn, permission_set_arn)

            # Display success message with checkmark emoji
            console.print(
                f"[green]✓ Permission set '{permission_set_name}' deleted successfully.[/green]"
            )
            console.print(f"[green]Permission Set ARN: {permission_set_arn}[/green]")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: Permission set '{identifier}' not found.[/red]")
                console.print("[yellow]The permission set may have been deleted already.[/yellow]")
            elif error_code == "ConflictException":
                console.print(
                    f"[red]Error: Cannot delete permission set '{permission_set_name}'.[/red]"
                )
                console.print(
                    "[yellow]The permission set may be in use by account assignments.[/yellow]"
                )
                console.print(
                    "[yellow]Remove all account assignments for this permission set before deletion.[/yellow]"
                )
            else:
                console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                console.print(
                    "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                )

            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="DeletePermissionSet")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)
    return None
