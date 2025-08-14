"""Assignment details command for awsideman.

This module provides the get command for retrieving detailed information about
a specific permission set assignment in AWS Identity Center.
"""

from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.panel import Panel

from ...aws_clients.manager import AWSClientManager
from ...utils.config import Config
from ...utils.error_handler import handle_aws_error
from ...utils.validators import validate_profile, validate_sso_instance
from .helpers import console, resolve_permission_set_info, resolve_principal_info

config = Config()


def get_assignment(
    permission_set_arn: str = typer.Argument(..., help="Permission set ARN"),
    principal_id: str = typer.Argument(..., help="Principal ID (user or group)"),
    account_id: str = typer.Argument(..., help="AWS account ID"),
    principal_type: str = typer.Option(
        "USER", "--principal-type", help="Principal type (USER or GROUP)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
) -> None:
    """Get details about a specific permission set assignment.

    Retrieves and displays comprehensive information about an assignment by its permission set ARN,
    principal ID, and account ID. Shows detailed assignment information including creation date
    and resolved names for user-friendly display.

    Examples:
        # Get assignment details for a user
        $ awsideman assignment get arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef user-1234567890abcdef 123456789012

        # Get assignment details for a group
        $ awsideman assignment get arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef group-1234567890abcdef 123456789012 --principal-type GROUP
    """
    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    # Convert principal type to uppercase
    principal_type = principal_type.upper()

    # Validate permission set ARN format (basic validation)
    if not permission_set_arn.startswith("arn:aws:sso:::permissionSet/"):
        console.print("[red]Error: Invalid permission set ARN format.[/red]")
        console.print(
            "[yellow]Permission set ARN should start with 'arn:aws:sso:::permissionSet/'.[/yellow]"
        )
        raise typer.Exit(1)

    # Validate account ID format (basic validation - should be 12 digits)
    if not account_id.isdigit() or len(account_id) != 12:
        console.print("[red]Error: Invalid account ID format.[/red]")
        console.print("[yellow]Account ID should be a 12-digit number.[/yellow]")
        raise typer.Exit(1)

    # Validate principal ID format (basic validation - should not be empty)
    if not principal_id.strip():
        console.print("[red]Error: Principal ID cannot be empty.[/red]")
        raise typer.Exit(1)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    # Get SSO admin client
    try:
        sso_admin_client = aws_client.get_sso_admin_client()
    except Exception as e:
        console.print(f"[red]Error: Failed to create SSO admin client: {str(e)}[/red]")
        raise typer.Exit(1)

    # Get identity store client
    try:
        identity_store_client = aws_client.get_identity_store_client()
    except Exception as e:
        console.print(f"[red]Error: Failed to create identity store client: {str(e)}[/red]")
        raise typer.Exit(1)

    # Display a message indicating that we're fetching assignment details
    with console.status("[blue]Fetching assignment details...[/blue]"):
        try:
            # Check if assignment exists by listing assignments for the permission set and account
            list_params = {
                "InstanceArn": instance_arn,
                "AccountId": account_id,
                "PermissionSetArn": permission_set_arn,
            }

            # Make the API call to list account assignments
            response = sso_admin_client.list_account_assignments(**list_params)

            # Extract assignments from the response
            all_assignments = response.get("AccountAssignments", [])

            # Filter assignments by principal ID and type locally
            assignments = [
                assignment
                for assignment in all_assignments
                if assignment.get("PrincipalId") == principal_id
                and assignment.get("PrincipalType") == principal_type
            ]

            # Check if the assignment exists
            if not assignments:
                console.print("[red]Error: Assignment not found.[/red]")
                console.print("[yellow]No assignment found for:[/yellow]")
                console.print(f"  Permission Set ARN: {permission_set_arn}")
                console.print(f"  Principal ID: {principal_id}")
                console.print(f"  Principal Type: {principal_type}")
                console.print(f"  Account ID: {account_id}")
                console.print(
                    "[yellow]Use 'awsideman assignment list' to see all available assignments.[/yellow]"
                )
                raise typer.Exit(1)

            # Get the first (and should be only) assignment
            assignment = assignments[0]

            # Extract assignment information
            assignment_info = {
                "PermissionSetArn": assignment.get("PermissionSetArn"),
                "PrincipalId": assignment.get("PrincipalId"),
                "PrincipalType": assignment.get("PrincipalType"),
                "AccountId": assignment.get("AccountId"),
                "CreatedDate": assignment.get("CreatedDate"),
            }

            # Resolve permission set information
            try:
                permission_set_info = resolve_permission_set_info(
                    instance_arn, assignment_info["PermissionSetArn"], sso_admin_client
                )
                assignment_info["PermissionSetName"] = permission_set_info.get("Name")
                assignment_info["PermissionSetDescription"] = permission_set_info.get("Description")
                assignment_info["SessionDuration"] = permission_set_info.get("SessionDuration")
            except typer.Exit:
                # If we can't resolve the permission set, use placeholder values
                assignment_info["PermissionSetName"] = "Unknown Permission Set"
                assignment_info["PermissionSetDescription"] = None
                assignment_info["SessionDuration"] = None

            # Resolve principal information
            try:
                principal_info = resolve_principal_info(
                    identity_store_id,
                    assignment_info["PrincipalId"],
                    assignment_info["PrincipalType"],
                    identity_store_client,
                )
                assignment_info["PrincipalName"] = principal_info.get("PrincipalName")
                assignment_info["PrincipalDisplayName"] = principal_info.get("DisplayName")
            except typer.Exit:
                # If we can't resolve the principal, use placeholder values
                assignment_info["PrincipalName"] = "Unknown Principal"
                assignment_info["PrincipalDisplayName"] = "Unknown Principal"

            # Display comprehensive assignment information in panel format
            # Create the assignment details content
            details_content = []

            # Permission Set Information
            details_content.append("[bold blue]Permission Set Information[/bold blue]")
            details_content.append(
                f"  Name: [green]{assignment_info.get('PermissionSetName', 'Unknown')}[/green]"
            )
            details_content.append(f"  ARN: [dim]{assignment_info['PermissionSetArn']}[/dim]")
            if assignment_info.get("PermissionSetDescription"):
                details_content.append(
                    f"  Description: {assignment_info['PermissionSetDescription']}"
                )
            if assignment_info.get("SessionDuration"):
                details_content.append(f"  Session Duration: {assignment_info['SessionDuration']}")
            details_content.append("")

            # Principal Information
            details_content.append("[bold cyan]Principal Information[/bold cyan]")
            details_content.append(
                f"  Display Name: [cyan]{assignment_info.get('PrincipalDisplayName', 'Unknown')}[/cyan]"
            )
            details_content.append(
                f"  Principal Name: {assignment_info.get('PrincipalName', 'Unknown')}"
            )
            details_content.append(f"  Principal ID: [dim]{assignment_info['PrincipalId']}[/dim]")
            details_content.append(
                f"  Principal Type: [magenta]{assignment_info['PrincipalType']}[/magenta]"
            )
            details_content.append("")

            # Account Information
            details_content.append("[bold yellow]Account Information[/bold yellow]")
            details_content.append(f"  Account ID: [yellow]{assignment_info['AccountId']}[/yellow]")
            details_content.append("")

            # Assignment Metadata
            details_content.append("[bold white]Assignment Metadata[/bold white]")
            if assignment_info.get("CreatedDate"):
                # Format the creation date for better readability
                created_date = assignment_info["CreatedDate"]
                if hasattr(created_date, "strftime"):
                    formatted_date = created_date.strftime("%Y-%m-%d %H:%M:%S UTC")
                else:
                    formatted_date = str(created_date)
                details_content.append(f"  Created Date: [white]{formatted_date}[/white]")
            else:
                details_content.append("  Created Date: [dim]Not available[/dim]")

            # Join all content with newlines
            content_text = "\n".join(details_content)

            # Create and display the panel
            panel = Panel(
                content_text,
                title="[bold]Assignment Details[/bold]",
                title_align="left",
                border_style="blue",
                padding=(1, 2),
            )

            console.print(panel)

        except ClientError as e:
            # Handle AWS API errors with enhanced error handling
            handle_aws_error(e, "ListAccountAssignments")
        except Exception as e:
            # Handle other unexpected errors
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(1)
