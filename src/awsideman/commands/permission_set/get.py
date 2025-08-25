"""Get permission set command for awsideman."""

from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.panel import Panel
from rich.table import Table

from ...utils.error_handler import with_retry
from ..common import (
    extract_standard_params,
    handle_aws_error,
    profile_option,
    region_option,
    show_cache_info,
    validate_profile_with_cache,
)
from .helpers import (
    console,
    format_permission_set_for_display,
    resolve_permission_set_identifier,
    validate_sso_instance,
)


def get_permission_set(
    identifier: str = typer.Argument(..., help="Permission set name or ARN"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
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
        # Extract and process standard command parameters
        profile, region, enable_caching = extract_standard_params(profile, region)

        # Show cache information if verbose
        show_cache_info(verbose)

        # Validate profile and get AWS client with cache integration
        profile_name, profile_data, aws_client = validate_profile_with_cache(
            profile=profile, enable_caching=enable_caching, region=region
        )

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Get the SSO admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Resolve the permission set identifier to an ARN
        permission_set_arn = resolve_permission_set_identifier(
            sso_admin_client, instance_arn, identifier, identity_store_id
        )

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

    except typer.Exit:
        # Re-raise typer.Exit without additional error messages
        raise
    except Exception as e:
        # Handle all other errors using common error handler
        handle_aws_error(e, "getting permission set", verbose=verbose)
        raise typer.Exit(1)
