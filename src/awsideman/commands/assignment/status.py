"""Assignment status command for awsideman.

This module provides the status command for checking the status of assignment
creation or deletion requests using their request IDs.
"""

from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.panel import Panel

from ...aws_clients.manager import AWSClientManager
from ...utils.config import Config
from ...utils.error_handler import handle_aws_error
from ...utils.validators import validate_profile, validate_sso_instance
from .helpers import console

config = Config()


def check_assignment_status(
    request_id: str = typer.Argument(..., help="Request ID from assignment operation"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
) -> None:
    """Check the status of an assignment creation or deletion request.

    Retrieves and displays the current status of an assignment operation using
    the request ID returned from the assign or revoke command. Shows detailed
    information about the operation including status, failure reason (if any),
    and timing information.

    Examples:
        # Check status of an assignment creation request
        $ awsideman assignment status 7a2a5b5e-cd48-4d2a-9c0c-419506922b05

        # Check status with specific profile
        $ awsideman assignment status 7a2a5b5e-cd48-4d2a-9c0c-419506922b05 --profile production
    """
    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Validate request ID format (basic validation - should not be empty)
    if not request_id.strip():
        console.print("[red]Error: Request ID cannot be empty.[/red]")
        raise typer.Exit(1)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    # Get SSO admin client
    try:
        sso_admin_client = aws_client.get_sso_admin_client()
    except Exception as e:
        console.print(f"[red]Error: Failed to create SSO admin client: {str(e)}[/red]")
        raise typer.Exit(1)

    # Display a message indicating that we're fetching request status
    with console.status("[blue]Fetching request status...[/blue]"):
        try:
            # Try to get creation status first
            try:
                creation_response = sso_admin_client.describe_account_assignment_creation_status(
                    InstanceArn=instance_arn,
                    AccountAssignmentCreationRequestId=request_id,
                )

                status_info = creation_response.get("AccountAssignmentCreationStatus", {})
                operation_type = "creation"

            except ClientError as e:
                # If creation status fails, try deletion status
                error_code = e.response.get("Error", {}).get("Code")
                console.print(
                    f"[dim]DEBUG: Creation status failed with error code: {error_code}[/dim]"
                )

                if error_code == "ResourceNotFoundException":
                    console.print("[dim]DEBUG: Trying deletion status API...[/dim]")
                    try:
                        deletion_response = (
                            sso_admin_client.describe_account_assignment_deletion_status(
                                InstanceArn=instance_arn,
                                AccountAssignmentDeletionRequestId=request_id,
                            )
                        )

                        status_info = deletion_response.get("AccountAssignmentDeletionStatus", {})
                        operation_type = "deletion"
                        console.print("[dim]DEBUG: Deletion status API succeeded[/dim]")

                    except ClientError as deletion_error:
                        deletion_error_code = deletion_error.response.get("Error", {}).get("Code")
                        console.print(
                            f"[dim]DEBUG: Deletion status also failed with error code: {deletion_error_code}[/dim]"
                        )
                        console.print("[red]Error: Request ID not found.[/red]")
                        console.print(
                            f"[yellow]Request ID '{request_id}' was not found for either creation or deletion operations.[/yellow]"
                        )
                        console.print(
                            "[yellow]Please verify the request ID and try again.[/yellow]"
                        )
                        raise typer.Exit(1)
                else:
                    # Re-raise if it's not a ResourceNotFound error
                    console.print(f"[dim]DEBUG: Re-raising error with code: {error_code}[/dim]")
                    raise e

            # Extract status information
            status = status_info.get("Status", "UNKNOWN")
            failure_reason = status_info.get("FailureReason")
            created_date = status_info.get("CreatedDate")
            status_reason = status_info.get("StatusReason")

            # Extract assignment details
            assignment_info = status_info.get("AccountAssignment", {})
            permission_set_arn = assignment_info.get("PermissionSetArn")
            principal_id = assignment_info.get("PrincipalId")
            principal_type = assignment_info.get("PrincipalType")
            account_id = assignment_info.get("AccountId")

            # Create status display
            status_content = []

            # Request Information
            status_content.append("[bold blue]Request Information[/bold blue]")
            status_content.append(f"  Request ID: [dim]{request_id}[/dim]")
            status_content.append(f"  Operation Type: [cyan]{operation_type.title()}[/cyan]")
            status_content.append(f"  Status: {_format_status(status)}")

            if created_date:
                if hasattr(created_date, "strftime"):
                    formatted_date = created_date.strftime("%Y-%m-%d %H:%M:%S UTC")
                else:
                    formatted_date = str(created_date)
                status_content.append(f"  Created Date: [white]{formatted_date}[/white]")

            if status_reason:
                status_content.append(f"  Status Reason: [yellow]{status_reason}[/yellow]")

            if failure_reason:
                status_content.append(f"  Failure Reason: [red]{failure_reason}[/red]")

            status_content.append("")

            # Assignment Details
            if assignment_info:
                status_content.append("[bold green]Assignment Details[/bold green]")
                if permission_set_arn:
                    status_content.append(f"  Permission Set ARN: [dim]{permission_set_arn}[/dim]")
                if principal_id:
                    status_content.append(f"  Principal ID: [dim]{principal_id}[/dim]")
                if principal_type:
                    status_content.append(f"  Principal Type: [magenta]{principal_type}[/magenta]")
                if account_id:
                    status_content.append(f"  Account ID: [yellow]{account_id}[/yellow]")

            # Join all content with newlines
            content_text = "\n".join(status_content)

            # Create and display the panel
            panel = Panel(
                content_text,
                title="[bold]Assignment Request Status[/bold]",
                title_align="left",
                border_style="blue",
                padding=(1, 2),
            )

            console.print(panel)

            # Provide next steps based on status
            if status == "IN_PROGRESS":
                console.print()
                console.print("[yellow]The assignment operation is still in progress.[/yellow]")
                console.print(
                    "[yellow]You can check the status again later using the same request ID.[/yellow]"
                )
            elif status == "SUCCEEDED":
                console.print()
                console.print("[green]✓ The assignment operation completed successfully![/green]")
                if operation_type == "creation":
                    console.print(
                        "[green]The assignment has been created and is now active.[/green]"
                    )
                else:
                    console.print("[green]The assignment has been deleted successfully.[/green]")
            elif status == "FAILED":
                console.print()
                console.print("[red]✗ The assignment operation failed.[/red]")
                if failure_reason:
                    console.print(f"[red]Failure reason: {failure_reason}[/red]")
                console.print(
                    "[yellow]You may need to retry the operation or check your permissions.[/yellow]"
                )

        except ClientError as e:
            # Handle AWS API errors with enhanced error handling
            handle_aws_error(e, "DescribeAccountAssignmentStatus")
        except Exception as e:
            # Handle other unexpected errors
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(1)


def _format_status(status: str) -> str:
    """Format status with appropriate colors."""
    status_colors = {
        "IN_PROGRESS": "[yellow]IN_PROGRESS[/yellow]",
        "SUCCEEDED": "[green]SUCCEEDED[/green]",
        "FAILED": "[red]FAILED[/red]",
        "UNKNOWN": "[dim]UNKNOWN[/dim]",
    }
    return status_colors.get(status, f"[dim]{status}[/dim]")
