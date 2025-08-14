"""Get permission set command for awsideman."""

from typing import Optional

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from rich.panel import Panel
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...utils.error_handler import handle_aws_error, handle_network_error, with_retry
from .helpers import (
    console,
    format_permission_set_for_display,
    resolve_permission_set_identifier,
    validate_profile,
    validate_sso_instance,
)


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
