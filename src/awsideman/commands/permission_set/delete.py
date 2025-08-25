"""Delete permission set command for awsideman."""

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


def delete_permission_set(
    identifier: str = typer.Argument(..., help="Permission set name or ARN"),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Delete a permission set from AWS Identity Center.

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

        # Force delete without confirmation
        $ awsideman permission-set delete TestAccess --force
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the SSO admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Resolve the permission set identifier to an ARN
        permission_set_arn = resolve_permission_set_identifier(
            sso_admin_client, instance_arn, identifier, identity_store_id
        )

        # Get the permission set details for confirmation

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

        # Ask for confirmation before deletion (unless force flag is used)
        if not force:
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

            # Invalidate cache to ensure permission set data is fresh
            try:
                # Use the AWS client manager's cache manager to ensure we invalidate
                # the same cache that the cached client uses
                if aws_client.is_caching_enabled():
                    # Clear internal data storage to ensure fresh data
                    aws_client.clear_cache()

            except Exception as cache_error:
                # Don't fail the command if cache invalidation fails
                console.print(
                    f"[yellow]Warning: Failed to invalidate cache: {cache_error}[/yellow]"
                )

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
    except typer.Exit:
        # Re-raise typer.Exit without additional error messages
        raise
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)
    return None
