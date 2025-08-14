"""Assignment revocation command for awsideman.

This module provides the revoke command for removing permission set assignments
in AWS Identity Center. It supports both single-account and multi-account revocations
with various filtering options.
"""

from typing import Optional

import typer
from botocore.exceptions import ClientError

from ...aws_clients.manager import AWSClientManager
from ...bulk.resolver import ResourceResolver
from ...commands.permission_set.helpers import resolve_permission_set_identifier
from ...utils.config import Config
from ...utils.validators import validate_profile, validate_sso_instance
from .helpers import (
    console,
    log_individual_operation,
    resolve_permission_set_info,
    resolve_principal_info,
)

config = Config()


def revoke_permission_set(
    permission_set_name: str = typer.Argument(..., help="Permission set name"),
    principal_name: str = typer.Argument(..., help="Principal name (user or group)"),
    account_id: Optional[str] = typer.Argument(
        None, help="AWS account ID (for single account revocation)"
    ),
    account_filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Account filter for multi-account revocation (* for all accounts, or tag:Key=Value for tag-based filtering)",
    ),
    accounts: Optional[str] = typer.Option(
        None, "--accounts", help="Comma-separated list of account IDs for multi-account revocation"
    ),
    ou_filter: Optional[str] = typer.Option(
        None, "--ou-filter", help="Organizational unit path filter (e.g., 'Root/Production')"
    ),
    account_pattern: Optional[str] = typer.Option(
        None, "--account-pattern", help="Regex pattern for account name matching"
    ),
    principal_type: str = typer.Option(
        "USER", "--principal-type", help="Principal type (USER or GROUP)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force revocation without confirmation"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview operations without making changes"
    ),
    batch_size: int = typer.Option(
        10,
        "--batch-size",
        help="Number of accounts to process concurrently (for multi-account operations)",
    ),
    continue_on_error: bool = typer.Option(
        True,
        "--continue-on-error/--stop-on-error",
        help="Continue processing on individual account failures (for multi-account operations)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
) -> None:
    """Revoke a permission set assignment from a principal for one or more AWS accounts.

    This unified command supports both single-account and multi-account revocations:

    Single Account Revocation:
        Provide an account_id as the third argument to revoke from a specific account.

    Multi-Account Revocation:
        Use --filter or --accounts to revoke across multiple accounts.

    Examples:
        # Single account revocation
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com 123456789012

        # Multi-account revocation from all accounts
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com --filter "*"

        # Multi-account revocation with tag filter
        $ awsideman assignment revoke PowerUserAccess developers --filter "tag:Environment=Production" --principal-type GROUP

        # Multi-account revocation from specific accounts
        $ awsideman assignment revoke ViewOnlyAccess jane.doe@company.com --accounts "123456789012,987654321098"

        # Preview multi-account revocation without making changes
        $ awsideman assignment revoke AdminAccess admin@company.com --filter "*" --dry-run

        # Force revocation without confirmation
        $ awsideman assignment revoke TempAccess temp.user@company.com 123456789012 --force
    """
    # Validate mutually exclusive target options
    provided_options = sum(
        [
            bool(account_id),
            bool(account_filter),
            bool(accounts),
            bool(ou_filter),
            bool(account_pattern),
        ]
    )
    if provided_options == 0:
        console.print("[red]Error: Must specify one target option[/red]")
        console.print("[yellow]Examples:[/yellow]")
        console.print(
            "  Single account: awsideman assignment revoke ReadOnlyAccess user@company.com 123456789012"
        )
        console.print(
            "  Multi-account:  awsideman assignment revoke ReadOnlyAccess user@company.com --filter '*'"
        )
        console.print(
            "  OU-based:       awsideman assignment revoke ReadOnlyAccess user@company.com --ou-filter 'Root/Production'"
        )
        console.print(
            "  Pattern-based:  awsideman assignment revoke ReadOnlyAccess user@company.com --account-pattern '^prod-.*'"
        )
        raise typer.Exit(1)
    elif provided_options > 1:
        console.print("[red]Error: Cannot specify multiple target options simultaneously[/red]")
        console.print(
            "[yellow]Choose one of: account_id, --filter, --accounts, --ou-filter, or --account-pattern[/yellow]"
        )
        raise typer.Exit(1)

    # Route to appropriate implementation
    if account_id:
        # Single account revocation
        return revoke_single_account(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            account_id=account_id,
            principal_type=principal_type,
            force=force,
            profile=profile,
        )
    else:
        # Multi-account revocation with explicit accounts
        if accounts:
            # Convert comma-separated account list to list
            account_list = [acc.strip() for acc in accounts.split(",") if acc.strip()]

            if not account_list:
                console.print(
                    "[red]Error: No valid account IDs provided in --accounts parameter.[/red]"
                )
                raise typer.Exit(1)

            # Use explicit account revocation
            return revoke_multi_account_explicit(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_list=account_list,
                principal_type=principal_type,
                force=force,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )

        elif account_filter:
            # Use account filter (existing multi-account revocation logic)
            return _execute_multi_account_revocation(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_filter=account_filter,
                principal_type=principal_type,
                force=force,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )
        else:
            # Use advanced filtering options (OU or pattern)
            return revoke_multi_account_advanced(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                ou_filter=ou_filter,
                account_pattern=account_pattern,
                principal_type=principal_type,
                force=force,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )


def revoke_single_account(
    permission_set_name: str,
    principal_name: str,
    account_id: str,
    principal_type: str = "USER",
    force: bool = False,
    profile: Optional[str] = None,
) -> None:
    """Revoke a permission set assignment from a principal.

    Removes an assignment linking a permission set to a principal (user or group) for a specific AWS account.
    This will remove the principal's access to the specified account through the permission set.

    Examples:
        # Revoke a permission set assignment from a user
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com 123456789012

        # Revoke a permission set assignment from a group
        $ awsideman assignment revoke PowerUserAccess developers 123456789012 --principal-type GROUP

        # Force revocation without confirmation
        $ awsideman assignment revoke ReadOnlyAccess john.doe@company.com 123456789012 --force
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

    # Validate permission set name format (basic validation - should not be empty)
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    # Validate account ID format (basic validation - should be 12 digits)
    if not account_id.isdigit() or len(account_id) != 12:
        console.print("[red]Error: Invalid account ID format.[/red]")
        console.print("[yellow]Account ID should be a 12-digit number.[/yellow]")
        raise typer.Exit(1)

    # Validate principal name format (basic validation - should not be empty)
    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
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

    # Resolve permission set name to ARN
    with console.status("[blue]Resolving permission set name...[/blue]"):
        try:
            permission_set_arn = resolve_permission_set_identifier(
                aws_client, instance_arn, permission_set_name
            )
        except typer.Exit:
            # Error already handled by resolve_permission_set_identifier
            raise

    # Resolve principal name to ID
    with console.status("[blue]Resolving principal name...[/blue]"):
        try:
            resolver = ResourceResolver(
                aws_client_manager=aws_client,
                instance_arn=instance_arn,
                identity_store_id=identity_store_id,
            )

            principal_result = resolver.resolve_principal_name(principal_name, principal_type)
            if not principal_result.success:
                console.print(f"[red]Error: {principal_result.error_message}[/red]")
                console.print(
                    "[yellow]Use 'awsideman user list' or 'awsideman group list' to see available principals.[/yellow]"
                )
                raise typer.Exit(1)

            principal_id = principal_result.resolved_value
            if principal_id is None:
                console.print("[red]Error: Failed to resolve principal ID[/red]")
                raise typer.Exit(1)

        except Exception as e:
            console.print(f"[red]Error resolving principal name: {str(e)}[/red]")
            raise typer.Exit(1)

    # Display a message indicating that we're checking the assignment
    with console.status("[blue]Checking assignment details...[/blue]"):
        try:
            # First, check if the assignment exists
            list_params = {
                "InstanceArn": instance_arn,
                "AccountId": account_id,
                "PermissionSetArn": permission_set_arn,
            }

            # Check for existing assignment
            existing_response = sso_admin_client.list_account_assignments(**list_params)
            all_assignments = existing_response.get("AccountAssignments", [])

            # Filter assignments by principal ID and type locally
            existing_assignments = [
                assignment
                for assignment in all_assignments
                if assignment.get("PrincipalId") == principal_id
                and assignment.get("PrincipalType") == principal_type
            ]

            if not existing_assignments:
                console.print("[red]Error: Assignment not found.[/red]")
                console.print("[yellow]No assignment found for:[/yellow]")
                console.print(f"  Permission Set: {permission_set_name}")
                console.print(f"  Principal: {principal_name} ({principal_type})")
                console.print(f"  Account ID: {account_id}")
                console.print(
                    "[yellow]Use 'awsideman assignment list' to see all available assignments.[/yellow]"
                )
                raise typer.Exit(1)

            # Resolve names for display
            try:
                permission_set_info = resolve_permission_set_info(
                    instance_arn, permission_set_arn, sso_admin_client
                )
                permission_set_display_name = permission_set_info.get("Name", "Unknown")
            except typer.Exit:
                permission_set_display_name = "Unknown"

            try:
                principal_info = resolve_principal_info(
                    identity_store_id, principal_id, principal_type, identity_store_client
                )
                principal_display_name = principal_info.get("DisplayName", "Unknown")
            except typer.Exit:
                principal_display_name = "Unknown"

            # Show confirmation prompt unless force flag is used
            if not force:
                console.print()
                console.print(
                    "[bold red]⚠️  WARNING: You are about to revoke a permission set assignment[/bold red]"
                )
                console.print()
                console.print("[bold]Assignment to be revoked:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                console.print(
                    "[red]This will remove the principal's access to the specified account through this permission set.[/red]"
                )
                console.print()

                # Get user confirmation
                confirm = typer.confirm("Are you sure you want to revoke this assignment?")
                if not confirm:
                    console.print("[yellow]Assignment revocation cancelled.[/yellow]")
                    raise typer.Exit(0)

            # Revoke the assignment
            # Create the revocation parameters
            delete_params = {
                "InstanceArn": instance_arn,
                "TargetId": account_id,
                "TargetType": "AWS_ACCOUNT",
                "PermissionSetArn": permission_set_arn,
                "PrincipalType": principal_type,
                "PrincipalId": principal_id,
            }

            # Make the API call to delete the assignment
            response = sso_admin_client.delete_account_assignment(**delete_params)

            # Extract the request ID for tracking
            request_id = response.get("AccountAssignmentDeletionStatus", {}).get("RequestId")

            # The assignment deletion is asynchronous, so we get a request status
            assignment_status = response.get("AccountAssignmentDeletionStatus", {})
            status = assignment_status.get("Status", "UNKNOWN")

            # Handle the response and display appropriate output
            if status == "IN_PROGRESS":
                console.print("[green]✓ Assignment revocation initiated successfully.[/green]")
                console.print()
                console.print("[bold]Revoked Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Note: Assignment revocation is asynchronous and may take a few moments to complete.[/yellow]"
                )
                console.print(
                    "[yellow]You can verify the revocation using 'awsideman assignment list' command.[/yellow]"
                )

                # Log the successful revocation operation
                log_individual_operation(
                    "revoke",
                    principal_id,
                    principal_type,
                    principal_display_name,
                    permission_set_arn,
                    permission_set_display_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                )

            elif status == "SUCCEEDED":
                console.print("[green]✓ Assignment revoked successfully.[/green]")
                console.print()
                console.print("[bold]Revoked Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                console.print(
                    "[green]The principal no longer has access to the specified account through this permission set.[/green]"
                )

                # Log the successful revocation operation
                log_individual_operation(
                    "revoke",
                    principal_id,
                    principal_type,
                    principal_display_name,
                    permission_set_arn,
                    permission_set_display_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                )
            elif status == "FAILED":
                failure_reason = assignment_status.get("FailureReason", "Unknown error")
                console.print(f"[red]✗ Assignment revocation failed: {failure_reason}[/red]")
                console.print()
                console.print("[bold]Attempted Revocation:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                raise typer.Exit(1)
            else:
                console.print(f"[yellow]Assignment revocation status: {status}[/yellow]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_display_name}[/green]")
                console.print(
                    f"  Principal: [cyan]{principal_display_name}[/cyan] ({principal_type})"
                )
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Please check the assignment status using 'awsideman assignment list' command.[/yellow]"
                )

        except ClientError as e:
            # Handle AWS API errors
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ResourceNotFoundException":
                console.print("[red]✗ Assignment revocation failed: Assignment not found.[/red]")
                console.print()
                console.print("[bold]Attempted Revocation:[/bold]")
                console.print(f"  Permission Set ARN: {permission_set_arn}")
                console.print(f"  Principal ID: {principal_id}")
                console.print(f"  Principal Type: {principal_type}")
                console.print(f"  Account ID: {account_id}")
                console.print()
                console.print("[yellow]Troubleshooting:[/yellow]")
                console.print("• The assignment may have already been revoked")
                console.print("• The assignment may never have existed")
                console.print("• Use 'awsideman assignment list' to see all available assignments")
            else:
                console.print(
                    f"[red]✗ Assignment revocation failed ({error_code}): {error_message}[/red]"
                )
                console.print()
                console.print("[bold]Attempted Revocation:[/bold]")
                console.print(f"  Permission Set ARN: {permission_set_arn}")
                console.print(f"  Principal ID: {principal_id}")
                console.print(f"  Principal Type: {principal_type}")
                console.print(f"  Account ID: {account_id}")
                console.print()

                if error_code == "AccessDeniedException":
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print("• You do not have sufficient permissions to revoke assignments")
                    console.print(
                        "• Ensure your AWS credentials have the necessary SSO Admin permissions"
                    )
                    console.print(
                        "• Required permissions: sso:DeleteAccountAssignment, sso:ListAccountAssignments"
                    )
                elif error_code == "ValidationException":
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print("• Check that the permission set ARN is valid and exists")
                    console.print("• Verify that the principal ID exists in the identity store")
                    console.print("• Ensure the account ID is a valid 12-digit AWS account number")
                    console.print(
                        "• Confirm the principal type matches the actual principal (USER or GROUP)"
                    )
                elif error_code == "ConflictException":
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print("• There may be a conflicting assignment operation in progress")
                    console.print("• Wait a few moments and try again")
                    console.print(
                        "• Check if the assignment is currently being created or modified"
                    )
                else:
                    console.print("[yellow]Troubleshooting:[/yellow]")
                    console.print(
                        "• This could be due to an issue with the AWS Identity Center service"
                    )
                    console.print("• Check AWS service health status")
                    console.print("• Verify your AWS region configuration")

            raise typer.Exit(1)
        except Exception as e:
            # Handle other unexpected errors
            console.print(f"[red]✗ Assignment revocation failed: {str(e)}[/red]")
            console.print()
            console.print("[bold]Attempted Revocation:[/bold]")
            console.print(f"  Permission Set ARN: {permission_set_arn}")
            console.print(f"  Principal ID: {principal_id}")
            console.print(f"  Principal Type: {principal_type}")
            console.print(f"  Account ID: {account_id}")
            console.print()
            console.print(
                "[yellow]This could be due to an unexpected error. Please try again or contact support.[/yellow]"
            )
            raise typer.Exit(1)


# Note: The multi-account revocation functions are complex and would make this file very large.
# For now, we'll implement them as stubs that call back to the original functions.


def revoke_multi_account_explicit(*args, **kwargs):
    """Stub for multi-account explicit revocation - to be implemented."""
    from .. import assignment as original_assignment

    return original_assignment.revoke_multi_account_explicit(*args, **kwargs)


def revoke_multi_account_advanced(*args, **kwargs):
    """Stub for multi-account advanced revocation - to be implemented."""
    from .. import assignment as original_assignment

    return original_assignment.revoke_multi_account_advanced(*args, **kwargs)


def _execute_multi_account_revocation(*args, **kwargs):
    """Stub for multi-account revocation execution - to be implemented."""
    from .. import assignment as original_assignment

    return original_assignment._execute_multi_account_revocation(*args, **kwargs)
