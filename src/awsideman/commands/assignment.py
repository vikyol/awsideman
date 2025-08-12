"""Assignment management commands for awsideman.

This module provides commands for managing permission set assignments in AWS Identity Center.
Assignments link permission sets to principals (users or groups) for specific AWS accounts.

Commands:
    list: List all assignments in the Identity Center
    get: Get detailed information about a specific assignment
    assign: Assign a permission set to a principal for a specific account
    revoke: Revoke a permission set assignment from a principal

Examples:
    # List all assignments
    $ awsideman assignment list

    # List assignments for a specific account
    $ awsideman assignment list --account-id 123456789012

    # Get details for a specific assignment
    $ awsideman assignment get arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef user-1234567890abcdef 123456789012

    # Assign a permission set to a user
    $ awsideman assignment assign arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef user-1234567890abcdef 123456789012

    # Revoke a permission set assignment
    $ awsideman assignment revoke arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef user-1234567890abcdef 123456789012
"""
import sys
from typing import List, Optional

import typer
from botocore.exceptions import ClientError
from rich.console import Console
from rich.table import Table

from ..aws_clients.manager import AWSClientManager
from ..commands.permission_set import resolve_permission_set_identifier
from ..utils.account_filter import AccountFilter
from ..utils.bulk.performance_optimizer import (
    create_performance_optimized_processor,
    display_performance_recommendations,
)
from ..utils.bulk.resolver import ResourceResolver
from ..utils.config import Config
from ..utils.error_handler import handle_aws_error, handle_network_error
from ..utils.models import MultiAccountAssignment
from ..utils.rollback.logger import OperationLogger
from ..utils.validators import validate_profile, validate_sso_instance

app = typer.Typer(
    help="Manage permission set assignments in AWS Identity Center. List, get, assign, and revoke permission set assignments."
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


@app.command("list")
def list_assignments(
    account_id: Optional[str] = typer.Option(
        None, "--account-id", "-a", help="Filter by AWS account ID"
    ),
    permission_set_arn: Optional[str] = typer.Option(
        None, "--permission-set-arn", "-p", help="Filter by permission set ARN"
    ),
    principal_id: Optional[str] = typer.Option(
        None, "--principal-id", help="Filter by principal ID"
    ),
    principal_type: Optional[str] = typer.Option(
        None, "--principal-type", help="Filter by principal type (USER or GROUP)"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of assignments to return"
    ),
    next_token: Optional[str] = typer.Option(None, "--next-token", "-n", help="Pagination token"),
    interactive: bool = typer.Option(
        True, "--interactive/--no-interactive", help="Enable/disable interactive pagination"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """List all permission set assignments.

    Displays a table of assignments with permission set name, principal name, principal type, and target account.
    Results can be filtered by account ID, permission set ARN, and principal ID.

    Examples:
        # List all assignments
        $ awsideman assignment list

        # List assignments for a specific account
        $ awsideman assignment list --account-id 123456789012

        # List assignments for a specific permission set
        $ awsideman assignment list --permission-set-arn arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef

        # List assignments for a specific principal
        $ awsideman assignment list --principal-id user-1234567890abcdef

        # List assignments with a specific limit
        $ awsideman assignment list --limit 10
    """
    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Validate principal type if provided
    if principal_type and principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    # Convert principal type to uppercase if provided
    if principal_type:
        principal_type = principal_type.upper()

    # Validate limit if provided
    if limit is not None and limit <= 0:
        console.print("[red]Error: Limit must be a positive integer.[/red]")
        raise typer.Exit(1)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    # Get SSO admin client
    try:
        sso_admin_client = aws_client.get_sso_admin_client()
    except ClientError as e:
        handle_aws_error(e, "CreateSSOAdminClient")
    except Exception as e:
        handle_network_error(e)

    # Get identity store client
    try:
        identity_store_client = aws_client.get_identity_store_client()
    except ClientError as e:
        handle_aws_error(e, "CreateIdentityStoreClient")
    except Exception as e:
        handle_network_error(e)

    # Initialize pagination variables
    current_token = next_token

    # Display a message indicating that we're fetching assignments
    with console.status("[blue]Fetching permission set assignments...[/blue]"):
        try:
            # Set up the base parameters for the list_account_assignments API call
            list_params = {
                "InstanceArn": instance_arn,
            }

            # Add filters if provided
            if account_id:
                list_params["AccountId"] = account_id

            if permission_set_arn:
                list_params["PermissionSetArn"] = permission_set_arn

            # Note: Principal filtering will be done locally after fetching results
            # as the AWS API doesn't support PrincipalId/PrincipalType parameters
            if principal_id and not principal_type:
                console.print(
                    "[yellow]Warning: Principal ID provided without principal type. Using default type 'USER' for filtering.[/yellow]"
                )
                principal_type = "USER"

            # Set the maximum number of results to return if limit is provided
            if limit:
                list_params["MaxResults"] = min(
                    limit, 100
                )  # AWS API typically limits to 100 items per page

            # Initialize variables for pagination
            all_assignments = []

            # Fetch assignments with pagination
            while True:
                # Add the pagination token if available
                if current_token:
                    list_params["NextToken"] = current_token

                # Make the API call to list account assignments
                response = sso_admin_client.list_account_assignments(**list_params)

                # Extract assignments from the response
                assignments = response.get("AccountAssignments", [])

                # Add assignments to the list
                all_assignments.extend(assignments)

                # Check if there are more assignments to fetch
                current_token = response.get("NextToken")

                # If there's no next token or we've reached the limit, break the loop
                if not current_token or (limit and len(all_assignments) >= limit):
                    break

            # Apply local filtering for principal ID and type if specified
            if principal_id:
                filtered_assignments = []
                for assignment in all_assignments:
                    if assignment.get("PrincipalId") == principal_id:
                        # If principal_type is specified, also check that
                        if principal_type and assignment.get("PrincipalType") != principal_type:
                            continue
                        filtered_assignments.append(assignment)
                all_assignments = filtered_assignments

            # Apply limit after filtering if specified
            if limit and len(all_assignments) > limit:
                all_assignments = all_assignments[:limit]

            # Process assignments to resolve names
            processed_assignments = []

            # Create a dictionary to cache permission set and principal information
            permission_set_cache = {}
            principal_cache = {}

            # Process each assignment
            for assignment in all_assignments:
                # Extract assignment information
                assignment_info = {
                    "PermissionSetArn": assignment.get("PermissionSetArn"),
                    "PrincipalId": assignment.get("PrincipalId"),
                    "PrincipalType": assignment.get("PrincipalType"),
                    "TargetId": assignment.get("AccountId"),
                    "TargetType": "AWS_ACCOUNT",
                }

                # Resolve permission set name if not already in cache
                if assignment_info["PermissionSetArn"] not in permission_set_cache:
                    try:
                        permission_set_info = resolve_permission_set_info(
                            instance_arn, assignment_info["PermissionSetArn"], sso_admin_client
                        )
                        permission_set_cache[
                            assignment_info["PermissionSetArn"]
                        ] = permission_set_info
                    except typer.Exit:
                        # If we can't resolve the permission set, use a placeholder
                        permission_set_cache[assignment_info["PermissionSetArn"]] = {
                            "Name": "Unknown Permission Set"
                        }

                # Add permission set name to assignment info
                assignment_info["PermissionSetName"] = permission_set_cache[
                    assignment_info["PermissionSetArn"]
                ].get("Name")

                # Create a cache key for the principal
                principal_cache_key = (
                    f"{assignment_info['PrincipalType']}:{assignment_info['PrincipalId']}"
                )

                # Resolve principal name if not already in cache
                if principal_cache_key not in principal_cache:
                    try:
                        principal_info = resolve_principal_info(
                            identity_store_id,
                            assignment_info["PrincipalId"],
                            assignment_info["PrincipalType"],
                            identity_store_client,
                        )
                        principal_cache[principal_cache_key] = principal_info
                    except typer.Exit:
                        # If we can't resolve the principal, use a placeholder
                        principal_cache[principal_cache_key] = {"DisplayName": "Unknown Principal"}

                # Add principal name to assignment info
                assignment_info["PrincipalName"] = principal_cache[principal_cache_key].get(
                    "DisplayName"
                )

                # Add the processed assignment to the list
                processed_assignments.append(assignment_info)

            # Check if there are any assignments to display
            if not processed_assignments:
                console.print("[yellow]No assignments found.[/yellow]")
                if account_id or permission_set_arn or principal_id:
                    console.print("[yellow]Try removing filters to see more results.[/yellow]")
                raise typer.Exit(0)

            # Create a table for displaying assignments
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Permission Set", style="green")
            table.add_column("Principal Name", style="cyan")
            table.add_column("Principal Type", style="magenta")
            table.add_column("Account ID", style="yellow")

            # Add rows to the table
            for assignment in processed_assignments:
                table.add_row(
                    assignment.get("PermissionSetName", "Unknown"),
                    assignment.get("PrincipalName", "Unknown"),
                    assignment.get("PrincipalType", "Unknown"),
                    assignment.get("TargetId", "Unknown"),
                )

            # Display filter information if any filters are applied
            filters_applied = []
            if account_id:
                filters_applied.append(f"Account ID: {account_id}")
            if permission_set_arn:
                filters_applied.append(f"Permission Set ARN: {permission_set_arn}")
            if principal_id:
                filters_applied.append(f"Principal ID: {principal_id}")
            if principal_type:
                filters_applied.append(f"Principal Type: {principal_type}")

            if filters_applied:
                console.print("Filters applied:", ", ".join(filters_applied), style="dim")

            # Display the table
            console.print(table)

            # Display pagination information if there's a next token and interactive mode is enabled
            if current_token and interactive:
                console.print(
                    f"More results available. Use --next-token {current_token} to fetch the next page.",
                    style="dim",
                )

        except ClientError as e:
            # Handle AWS API errors with enhanced error handling
            handle_aws_error(e, "ListAccountAssignments")
        except Exception as e:
            # Handle other unexpected errors
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(1)


@app.command("get")
def get_assignment(
    permission_set_arn: str = typer.Argument(..., help="Permission set ARN"),
    principal_id: str = typer.Argument(..., help="Principal ID (user or group)"),
    account_id: str = typer.Argument(..., help="AWS account ID"),
    principal_type: str = typer.Option(
        "USER", "--principal-type", help="Principal type (USER or GROUP)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
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
            # Check if assignment exists by listing assignments with specific filters
            list_params = {
                "InstanceArn": instance_arn,
                "AccountId": account_id,
                "PermissionSetArn": permission_set_arn,
                "PrincipalId": principal_id,
                "PrincipalType": principal_type,
            }

            # Make the API call to list account assignments with filters
            response = sso_admin_client.list_account_assignments(**list_params)

            # Extract assignments from the response
            assignments = response.get("AccountAssignments", [])

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
            from rich.panel import Panel

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


@app.command("assign")
def assign_permission_set(
    permission_set_name: str = typer.Argument(..., help="Permission set name"),
    principal_name: str = typer.Argument(..., help="Principal name (user or group)"),
    account_id: Optional[str] = typer.Argument(
        None, help="AWS account ID (for single account assignment)"
    ),
    account_filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Account filter for multi-account assignment (* for all accounts, or tag:Key=Value for tag-based filtering)",
    ),
    accounts: Optional[str] = typer.Option(
        None, "--accounts", help="Comma-separated list of account IDs for multi-account assignment"
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
):
    """Assign a permission set to a principal for one or more AWS accounts.

    This unified command supports both single-account and multi-account assignments:

    Single Account Assignment:
        Provide an account_id as the third argument to assign to a specific account.

    Multi-Account Assignment:
        Use --filter or --accounts to assign across multiple accounts.

    Examples:
        # Single account assignment
        $ awsideman assignment assign ReadOnlyAccess john.doe@company.com 123456789012

        # Multi-account assignment to all accounts
        $ awsideman assignment assign ReadOnlyAccess john.doe@company.com --filter "*"

        # Multi-account assignment with tag filter
        $ awsideman assignment assign PowerUserAccess developers --filter "tag:Environment=Production" --principal-type GROUP

        # Multi-account assignment to specific accounts
        $ awsideman assignment assign ViewOnlyAccess jane.doe@company.com --accounts "123456789012,987654321098"

        # Preview multi-account assignment without making changes
        $ awsideman assignment assign AdminAccess admin@company.com --filter "*" --dry-run
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
            "  Single account: awsideman assignment assign ReadOnlyAccess user@company.com 123456789012"
        )
        console.print(
            "  Multi-account:  awsideman assignment assign ReadOnlyAccess user@company.com --filter '*'"
        )
        console.print(
            "  OU-based:       awsideman assignment assign ReadOnlyAccess user@company.com --ou-filter 'Root/Production'"
        )
        console.print(
            "  Pattern-based:  awsideman assignment assign ReadOnlyAccess user@company.com --account-pattern '^prod-.*'"
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
        # Single account assignment
        return assign_single_account(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            account_id=account_id,
            principal_type=principal_type,
            profile=profile,
        )
    else:
        # Multi-account assignment with various filter options
        if accounts:
            # Convert comma-separated account list to list
            account_list = [acc.strip() for acc in accounts.split(",") if acc.strip()]

            if not account_list:
                console.print(
                    "[red]Error: No valid account IDs provided in --accounts parameter.[/red]"
                )
                raise typer.Exit(1)

            # Use explicit account assignment
            return assign_multi_account_explicit(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_list=account_list,
                principal_type=principal_type,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )
        elif account_filter:
            # Use account filter (existing multi-account assignment logic)
            return _execute_multi_account_assignment(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                account_filter=account_filter,
                principal_type=principal_type,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )
        else:
            # Use advanced filtering options (OU or pattern)
            return assign_multi_account_advanced(
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                ou_filter=ou_filter,
                account_pattern=account_pattern,
                principal_type=principal_type,
                dry_run=dry_run,
                batch_size=batch_size,
                continue_on_error=continue_on_error,
                profile=profile,
            )


def assign_single_account(
    permission_set_name: str,
    principal_name: str,
    account_id: str,
    principal_type: str = "USER",
    profile: Optional[str] = None,
):
    """Assign a permission set to a principal for a specific account.

    Creates an assignment linking a permission set to a principal (user or group) for a specific AWS account.
    This allows the principal to assume the permission set's role in the specified account.

    Examples:
        # Assign a permission set to a user
        $ awsideman assignment assign ReadOnlyAccess john.doe@company.com 123456789012

        # Assign a permission set to a group
        $ awsideman assignment assign PowerUserAccess developers 123456789012 --principal-type GROUP
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

        except Exception as e:
            console.print(f"[red]Error resolving principal name: {str(e)}[/red]")
            raise typer.Exit(1)

    # Display a message indicating that we're creating the assignment
    with console.status("[blue]Creating permission set assignment...[/blue]"):
        try:
            # First, check if the assignment already exists
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

            if existing_assignments:
                console.print("[yellow]Assignment already exists.[/yellow]")
                console.print(
                    "Permission set is already assigned to this principal for the specified account."
                )
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                return

            # Create the assignment
            create_params = {
                "InstanceArn": instance_arn,
                "TargetId": account_id,
                "TargetType": "AWS_ACCOUNT",
                "PermissionSetArn": permission_set_arn,
                "PrincipalType": principal_type,
                "PrincipalId": principal_id,
            }

            # Make the API call to create the assignment
            response = sso_admin_client.create_account_assignment(**create_params)

            # Extract the request ID for tracking
            request_id = response.get("AccountAssignmentCreationStatus", {}).get("RequestId")

            # The assignment creation is asynchronous, so we get a request status
            assignment_status = response.get("AccountAssignmentCreationStatus", {})
            status = assignment_status.get("Status", "UNKNOWN")

            if status == "IN_PROGRESS":
                console.print("[green]✓ Assignment creation initiated successfully.[/green]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Note: Assignment creation is asynchronous and may take a few moments to complete.[/yellow]"
                )
                console.print(
                    "[yellow]You can verify the assignment using 'awsideman assignment get' command.[/yellow]"
                )

                # Log the successful assignment operation
                _log_individual_operation(
                    "assign",
                    principal_id,
                    principal_type,
                    principal_name,
                    permission_set_arn,
                    permission_set_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                )

            elif status == "SUCCEEDED":
                console.print("[green]✓ Assignment created successfully.[/green]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                console.print(
                    "[green]The principal can now access the specified account with the assigned permission set.[/green]"
                )

                # Log the successful assignment operation
                _log_individual_operation(
                    "assign",
                    principal_id,
                    principal_type,
                    principal_name,
                    permission_set_arn,
                    permission_set_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                )
            elif status == "FAILED":
                failure_reason = assignment_status.get("FailureReason", "Unknown error")
                console.print(f"[red]✗ Assignment creation failed: {failure_reason}[/red]")
                console.print()
                console.print("[bold]Attempted Assignment:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                raise typer.Exit(1)
            else:
                console.print(f"[yellow]Assignment creation status: {status}[/yellow]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                if request_id:
                    console.print(f"Request ID: [dim]{request_id}[/dim]")
                console.print(
                    "[yellow]Please check the assignment status using 'awsideman assignment get' command.[/yellow]"
                )

        except ClientError as e:
            # Handle AWS API errors with enhanced error handling
            handle_aws_error(e, "CreateAccountAssignment")
        except Exception as e:
            # Handle other unexpected errors
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(1)


@app.command("revoke")
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
):
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
):
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
                console.print(f"  Account ID: {account_id}")
                console.print(
                    "[yellow]Use 'awsideman assignment list' to see all available assignments.[/yellow]"
                )
                raise typer.Exit(1)

            # Get the assignment details

            # Resolve names for display
            try:
                permission_set_info = resolve_permission_set_info(
                    instance_arn, permission_set_arn, sso_admin_client
                )
                permission_set_name = permission_set_info.get("Name", "Unknown")
            except typer.Exit:
                permission_set_name = "Unknown"

            try:
                principal_info = resolve_principal_info(
                    identity_store_id, principal_id, principal_type, identity_store_client
                )
                principal_name = principal_info.get("DisplayName", "Unknown")
            except typer.Exit:
                principal_name = "Unknown"

            # Show confirmation prompt unless force flag is used
            if not force:
                console.print()
                console.print(
                    "[bold red]⚠️  WARNING: You are about to revoke a permission set assignment[/bold red]"
                )
                console.print()
                console.print("[bold]Assignment to be revoked:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
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
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
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
                _log_individual_operation(
                    "revoke",
                    principal_id,
                    principal_type,
                    principal_name,
                    permission_set_arn,
                    permission_set_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                )

            elif status == "SUCCEEDED":
                console.print("[green]✓ Assignment revoked successfully.[/green]")
                console.print()
                console.print("[bold]Revoked Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                console.print()
                console.print(
                    "[green]The principal no longer has access to the specified account through this permission set.[/green]"
                )

                # Log the successful revocation operation
                _log_individual_operation(
                    "revoke",
                    principal_id,
                    principal_type,
                    principal_name,
                    permission_set_arn,
                    permission_set_name,
                    account_id,
                    success=True,
                    request_id=request_id,
                )
            elif status == "FAILED":
                failure_reason = assignment_status.get("FailureReason", "Unknown error")
                console.print(f"[red]✗ Assignment revocation failed: {failure_reason}[/red]")
                console.print()
                console.print("[bold]Attempted Revocation:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
                console.print(f"  Account ID: [yellow]{account_id}[/yellow]")
                raise typer.Exit(1)
            else:
                console.print(f"[yellow]Assignment revocation status: {status}[/yellow]")
                console.print()
                console.print("[bold]Assignment Details:[/bold]")
                console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
                console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
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


def resolve_permission_set_info(
    instance_arn: str, permission_set_arn: str, sso_admin_client
) -> dict:
    """
    Resolve permission set information from ARN.

    This function retrieves detailed information about a permission set based on its ARN.
    It provides error handling for invalid permission set ARNs.

    Args:
        instance_arn: SSO instance ARN
        permission_set_arn: Permission set ARN
        sso_admin_client: SSO admin client

    Returns:
        Dictionary containing permission set information including:
        - PermissionSetArn: The ARN of the permission set
        - Name: The name of the permission set
        - Description: The description of the permission set (if available)
        - SessionDuration: The session duration of the permission set

    Raises:
        typer.Exit: If the permission set cannot be found or an error occurs
    """
    try:
        # Make the API call to describe the permission set
        response = sso_admin_client.describe_permission_set(
            InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
        )

        # Extract permission set information
        permission_set = response.get("PermissionSet", {})

        # Create a dictionary with the permission set information
        permission_set_info = {
            "PermissionSetArn": permission_set_arn,
            "Name": permission_set.get("Name", "Unknown"),
            "Description": permission_set.get("Description", None),
            "SessionDuration": permission_set.get("SessionDuration", "PT1H"),
        }

        return permission_set_info

    except sso_admin_client.exceptions.ResourceNotFoundException:
        console.print(
            f"[red]Error: Permission set with ARN '{permission_set_arn}' not found.[/red]"
        )
        console.print("[yellow]Check the permission set ARN and try again.[/yellow]")
        console.print(
            "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
        )
        raise typer.Exit(1)
    except ClientError as e:
        # Handle AWS API errors with centralized error handling
        handle_aws_error(e, "DescribePermissionSet")
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def resolve_principal_info(
    identity_store_id: str, principal_id: str, principal_type: str, identity_store_client
) -> dict:
    """
    Resolve principal information (name, type) from principal ID.

    This function retrieves detailed information about a principal (user or group)
    based on its ID and type. It handles both USER and GROUP principal types and
    provides error handling for invalid principal IDs.

    Args:
        identity_store_id: Identity store ID
        principal_id: Principal ID to resolve
        principal_type: Type of principal (USER or GROUP)
        identity_store_client: Identity store client

    Returns:
        Dictionary containing principal information including:
        - PrincipalId: The ID of the principal
        - PrincipalType: The type of principal (USER or GROUP)
        - PrincipalName: The name of the principal (username for users, display name for groups)
        - DisplayName: The display name of the principal (if available)

    Raises:
        typer.Exit: If the principal cannot be found or an error occurs
    """
    try:
        principal_info = {
            "PrincipalId": principal_id,
            "PrincipalType": principal_type,
            "PrincipalName": None,
            "DisplayName": None,
        }

        # Handle USER principal type
        if principal_type.upper() == "USER":
            try:
                # Get user details
                user_response = identity_store_client.describe_user(
                    IdentityStoreId=identity_store_id, UserId=principal_id
                )

                # Extract user information
                principal_info["PrincipalName"] = user_response.get("UserName", "Unknown")
                principal_info["DisplayName"] = user_response.get("DisplayName", None)

                # If no display name is available, try to construct one from name components
                if not principal_info["DisplayName"]:
                    name_info = user_response.get("Name", {})
                    given_name = name_info.get("GivenName", "")
                    family_name = name_info.get("FamilyName", "")

                    if given_name or family_name:
                        principal_info["DisplayName"] = f"{given_name} {family_name}".strip()

                # If we still don't have a display name, use the username
                if not principal_info["DisplayName"]:
                    principal_info["DisplayName"] = principal_info["PrincipalName"]

                return principal_info

            except identity_store_client.exceptions.ResourceNotFoundException:
                console.print(f"[red]Error: User with ID '{principal_id}' not found.[/red]")
                console.print("[yellow]Check the user ID and try again.[/yellow]")
                raise typer.Exit(1)

        # Handle GROUP principal type
        elif principal_type.upper() == "GROUP":
            try:
                # Get group details
                group_response = identity_store_client.describe_group(
                    IdentityStoreId=identity_store_id, GroupId=principal_id
                )

                # Extract group information
                principal_info["PrincipalName"] = group_response.get("DisplayName", "Unknown")
                principal_info["DisplayName"] = group_response.get("DisplayName", "Unknown")

                return principal_info

            except identity_store_client.exceptions.ResourceNotFoundException:
                console.print(f"[red]Error: Group with ID '{principal_id}' not found.[/red]")
                console.print("[yellow]Check the group ID and try again.[/yellow]")
                raise typer.Exit(1)

        # Handle invalid principal type
        else:
            console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
            console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with centralized error handling
        operation = "DescribeUser" if principal_type.upper() == "USER" else "DescribeGroup"
        handle_aws_error(e, operation)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _log_individual_operation(
    operation_type: str,
    principal_id: str,
    principal_type: str,
    principal_name: str,
    permission_set_arn: str,
    permission_set_name: str,
    account_id: str,
    success: bool = True,
    error: str = None,
    request_id: str = None,
) -> None:
    """Log an individual assignment operation for rollback tracking.

    Args:
        operation_type: Type of operation ('assign' or 'revoke')
        principal_id: Principal ID
        principal_type: Principal type ('USER' or 'GROUP')
        principal_name: Principal display name
        permission_set_arn: Permission set ARN
        permission_set_name: Permission set name
        account_id: Account ID
        success: Whether the operation was successful
        error: Error message if operation failed
        request_id: AWS request ID for tracking
    """
    try:
        # Initialize operation logger
        operation_logger = OperationLogger()

        # Create operation result
        result = {
            "account_id": account_id,
            "success": success,
            "error": error,
            "duration_ms": None,  # Individual operations don't track duration
        }

        # Create metadata
        metadata = {"source": "individual_assignment", "request_id": request_id}

        # Log the operation
        operation_id = operation_logger.log_operation(
            operation_type=operation_type,
            principal_id=principal_id,
            principal_type=principal_type,
            principal_name=principal_name,
            permission_set_arn=permission_set_arn,
            permission_set_name=permission_set_name,
            account_ids=[account_id],
            account_names=[account_id],  # We don't have account name in individual operations
            results=[result],
            metadata=metadata,
        )

        console.print(f"[dim]Logged {operation_type} operation: {operation_id}[/dim]")

    except Exception as e:
        # Don't fail the entire operation if logging fails
        console.print(f"[yellow]Warning: Failed to log operation: {str(e)}[/yellow]")


def assign_multi_account_explicit(
    permission_set_name: str,
    principal_name: str,
    account_list: List[str],
    principal_type: str = "USER",
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Assign a permission set to a principal across explicit list of AWS accounts.

    Args:
        permission_set_name: Name of the permission set to assign
        principal_name: Name of the principal (user or group)
        account_list: List of explicit account IDs
        principal_type: Type of principal (USER or GROUP)
        dry_run: Whether to preview operations without making changes
        batch_size: Number of accounts to process concurrently
        continue_on_error: Whether to continue processing on individual account failures
        profile: AWS profile to use
    """
    # Validate inputs
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not account_list:
        console.print("[red]Error: Account list cannot be empty.[/red]")
        raise typer.Exit(1)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    principal_type = principal_type.upper()

    # Validate batch size
    if batch_size <= 0:
        console.print("[red]Error: Batch size must be a positive integer.[/red]")
        raise typer.Exit(1)

    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account validation
        organizations_client = aws_client.get_organizations_client()

        # Create account filter with explicit accounts
        account_filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=organizations_client,
            explicit_accounts=account_list,
        )

        # Validate account filter
        validation_errors = account_filter_obj.validate_filter()
        if validation_errors:
            console.print("[red]Error: Invalid account list.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on explicit list
        with console.status("[blue]Validating explicit account list...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error validating accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No valid accounts found in the provided list.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]Validated {len(accounts)} account(s) from explicit list.[/green]")

        # Show preview of accounts
        console.print("\n[bold]Accounts to be processed:[/bold]")
        for i, account in enumerate(accounts):
            console.print(f"  {i+1}. {account.get_display_name()}")

        # Create multi-account assignment
        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="assign",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run
        if not dry_run:
            console.print(
                f"\n[bold yellow]⚠️  You are about to assign a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [blue]ASSIGN[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account assignment cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="assign"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.2:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account assignment...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="assign",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Assignment'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(f"  Skipped: [yellow]{stats['skipped_count']}[/yellow]")

        console.print(f"  Duration: {stats['duration']:.1f} seconds")

        # Show failed accounts if any
        if results.failed_accounts:
            console.print(
                f"\n[bold red]Failed Accounts ({len(results.failed_accounts)}):[/bold red]"
            )
            for failed_account in results.failed_accounts:
                console.print(
                    f"  • {failed_account.account_name} ({failed_account.account_id}): {failed_account.error_message}"
                )

        # Show performance recommendations if applicable
        if len(accounts) > 50:
            display_performance_recommendations(len(accounts), stats["duration"])

    except ClientError as e:
        handle_aws_error(e, "MultiAccountAssign")
    except Exception as e:
        handle_network_error(e)


def assign_multi_account_advanced(
    permission_set_name: str,
    principal_name: str,
    ou_filter: Optional[str] = None,
    account_pattern: Optional[str] = None,
    principal_type: str = "USER",
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Assign a permission set to a principal using advanced filtering options.

    Args:
        permission_set_name: Name of the permission set to assign
        principal_name: Name of the principal (user or group)
        ou_filter: Organizational unit path filter
        account_pattern: Regex pattern for account name matching
        principal_type: Type of principal (USER or GROUP)
        dry_run: Whether to preview operations without making changes
        batch_size: Number of accounts to process concurrently
        continue_on_error: Whether to continue processing on individual account failures
        profile: AWS profile to use
    """
    # Validate inputs
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not ou_filter and not account_pattern:
        console.print("[red]Error: Must specify either --ou-filter or --account-pattern.[/red]")
        raise typer.Exit(1)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    principal_type = principal_type.upper()

    # Validate batch size
    if batch_size <= 0:
        console.print("[red]Error: Batch size must be a positive integer.[/red]")
        raise typer.Exit(1)

    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account filtering
        organizations_client = aws_client.get_organizations_client()

        # Create account filter with advanced options
        account_filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=organizations_client,
            explicit_accounts=None,
            ou_filter=ou_filter,
            account_name_pattern=account_pattern,
        )

        # Validate account filter
        validation_errors = account_filter_obj.validate_filter()
        if validation_errors:
            console.print("[red]Error: Invalid filter options.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on filter
        with console.status("[blue]Resolving accounts based on filter...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error resolving accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No accounts found matching the filter criteria.[/yellow]")
            console.print("[yellow]Please check your filter options and try again.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]Found {len(accounts)} account(s) matching filter criteria.[/green]")

        # Show preview of accounts if requested or if there are many accounts
        if dry_run or len(accounts) > 5:
            console.print("\n[bold]Accounts to be processed:[/bold]")
            for i, account in enumerate(accounts[:10]):  # Show first 10
                console.print(f"  {i+1}. {account.get_display_name()}")

            if len(accounts) > 10:
                console.print(f"  ... and {len(accounts) - 10} more accounts")

        # Create multi-account assignment
        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="assign",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run
        if not dry_run:
            console.print(
                f"\n[bold yellow]⚠️  You are about to assign a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [blue]ASSIGN[/blue]")
            console.print(f"  Filter Type: [blue]{'OU' if ou_filter else 'Pattern'}[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account assignment cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="assign"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.2:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account assignment...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="assign",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Assignment'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(f"  Skipped: [yellow]{stats['skipped_count']}[/yellow]")

        console.print(f"  Duration: {stats['duration']:.1f} seconds")

        # Show failed accounts if any
        if results.failed_accounts:
            console.print(
                f"\n[bold red]Failed Accounts ({len(results.failed_accounts)}):[/bold red]"
            )
            for failed_account in results.failed_accounts:
                console.print(
                    f"  • {failed_account.account_name} ({failed_account.account_id}): {failed_account.error_message}"
                )

        # Show performance recommendations if applicable
        if len(accounts) > 50:
            display_performance_recommendations(len(accounts), stats["duration"])

    except ClientError as e:
        handle_aws_error(e, "MultiAccountAssign")
    except Exception as e:
        handle_network_error(e)


def revoke_multi_account_explicit(
    permission_set_name: str,
    principal_name: str,
    account_list: List[str],
    principal_type: str = "USER",
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Revoke a permission set from a principal across explicit list of AWS accounts.

    Args:
        permission_set_name: Name of the permission set to revoke
        principal_name: Name of the principal (user or group)
        account_list: List of explicit account IDs
        principal_type: Type of principal (USER or GROUP)
        force: Whether to skip confirmation prompt
        dry_run: Whether to preview operations without making changes
        batch_size: Number of accounts to process concurrently
        continue_on_error: Whether to continue processing on individual account failures
        profile: AWS profile to use
    """
    # Validate inputs
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not account_list:
        console.print("[red]Error: Account list cannot be empty.[/red]")
        raise typer.Exit(1)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    principal_type = principal_type.upper()

    # Validate batch size
    if batch_size <= 0:
        console.print("[red]Error: Batch size must be a positive integer.[/red]")
        raise typer.Exit(1)

    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account validation
        organizations_client = aws_client.get_organizations_client()

        # Create account filter with explicit accounts
        account_filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=organizations_client,
            explicit_accounts=account_list,
        )

        # Validate account filter
        validation_errors = account_filter_obj.validate_filter()
        if validation_errors:
            console.print("[red]Error: Invalid account list.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on explicit list
        with console.status("[blue]Validating explicit account list...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error validating accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No valid accounts found in the provided list.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]Validated {len(accounts)} account(s) from explicit list.[/green]")

        # Show preview of accounts
        console.print("\n[bold]Accounts to be processed:[/bold]")
        for i, account in enumerate(accounts):
            console.print(f"  {i+1}. {account.get_display_name()}")

        # Create multi-account assignment
        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="revoke",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run or force
        if not dry_run and not force:
            console.print(
                f"\n[bold yellow]⚠️  You are about to revoke a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [red]REVOKE[/red]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account revocation cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="revoke"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.2:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account revocation...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="revoke",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Revocation'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(f"  Skipped: [yellow]{stats['skipped_count']}[/yellow]")

        console.print(f"  Duration: {stats['duration']:.1f} seconds")

        # Show failed accounts if any
        if results.failed_accounts:
            console.print(
                f"\n[bold red]Failed Accounts ({len(results.failed_accounts)}):[/bold red]"
            )
            for failed_account in results.failed_accounts:
                console.print(
                    f"  • {failed_account.account_name} ({failed_account.account_id}): {failed_account.error_message}"
                )

        # Show performance recommendations if applicable
        if len(accounts) > 50:
            display_performance_recommendations(len(accounts), stats["duration"])

    except ClientError as e:
        handle_aws_error(e, "MultiAccountRevoke")
    except Exception as e:
        handle_network_error(e)


def revoke_multi_account_advanced(
    permission_set_name: str,
    principal_name: str,
    ou_filter: Optional[str] = None,
    account_pattern: Optional[str] = None,
    principal_type: str = "USER",
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Revoke a permission set from a principal using advanced filtering options.

    Args:
        permission_set_name: Name of the permission set to revoke
        principal_name: Name of the principal (user or group)
        ou_filter: Organizational unit path filter
        account_pattern: Regex pattern for account name matching
        principal_type: Type of principal (USER or GROUP)
        force: Whether to skip confirmation prompt
        dry_run: Whether to preview operations without making changes
        batch_size: Number of accounts to process concurrently
        continue_on_error: Whether to continue processing on individual account failures
        profile: AWS profile to use
    """
    # Validate inputs
    if not permission_set_name.strip():
        console.print("[red]Error: Permission set name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not principal_name.strip():
        console.print("[red]Error: Principal name cannot be empty.[/red]")
        raise typer.Exit(1)

    if not ou_filter and not account_pattern:
        console.print("[red]Error: Must specify either --ou-filter or --account-pattern.[/red]")
        raise typer.Exit(1)

    # Validate principal type
    if principal_type.upper() not in ["USER", "GROUP"]:
        console.print(f"[red]Error: Invalid principal type '{principal_type}'.[/red]")
        console.print("[yellow]Principal type must be either 'USER' or 'GROUP'.[/yellow]")
        raise typer.Exit(1)

    principal_type = principal_type.upper()

    # Validate batch size
    if batch_size <= 0:
        console.print("[red]Error: Batch size must be a positive integer.[/red]")
        raise typer.Exit(1)

    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account filtering
        organizations_client = aws_client.get_organizations_client()

        # Create account filter with advanced options
        account_filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=organizations_client,
            explicit_accounts=None,
            ou_filter=ou_filter,
            account_name_pattern=account_pattern,
        )

        # Validate account filter
        validation_errors = account_filter_obj.validate_filter()
        if validation_errors:
            console.print("[red]Error: Invalid filter options.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on filter
        with console.status("[blue]Resolving accounts based on filter...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error resolving accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No accounts found matching the filter criteria.[/yellow]")
            console.print("[yellow]Please check your filter options and try again.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]Found {len(accounts)} account(s) matching filter criteria.[/green]")

        # Show preview of accounts if requested or if there are many accounts
        if dry_run or len(accounts) > 5:
            console.print("\n[bold]Accounts to be processed:[/bold]")
            for i, account in enumerate(accounts[:10]):  # Show first 10
                console.print(f"  {i+1}. {account.get_display_name()}")

            if len(accounts) > 10:
                console.print(f"  ... and {len(accounts) - 10} more accounts")

        # Create multi-account assignment
        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="revoke",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run or force
        if not dry_run and not force:
            console.print(
                f"\n[bold yellow]⚠️  You are about to revoke a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [red]REVOKE[/red]")
            console.print(f"  Filter Type: [blue]{'OU' if ou_filter else 'Pattern'}[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account revocation cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="revoke"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.0:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account revocation...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="revoke",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Revocation'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(
                f"  Skipped: [yellow]{stats['skipped_count']}[/yellow] ({stats['skip_rate']:.1f}%)"
            )

        console.print(f"  Duration: {stats['duration_seconds']:.2f} seconds")
        console.print(f"  Average Time per Account: {stats['average_processing_time']:.3f} seconds")

        # Show failed accounts if any
        if results.has_failures():
            console.print(f"\n[red]Failed Accounts ({len(results.failed_accounts)}):[/red]")
            for result in results.failed_accounts[:5]:  # Show first 5 failures
                console.print(f"  • {result.get_display_name()}: {result.get_error_summary()}")

            if len(results.failed_accounts) > 5:
                console.print(f"  ... and {len(results.failed_accounts) - 5} more failures")

        # Exit with appropriate code
        if dry_run:
            console.print(
                "\n[blue]Preview completed. Use --dry-run=false to execute the revocation.[/blue]"
            )
            return  # Successful completion, no need to raise Exit
        elif results.is_complete_success():
            console.print("\n[green]✓ Multi-account revocation completed successfully![/green]")
            return  # Successful completion, no need to raise Exit
        elif results.has_failures():
            console.print(
                "\n[yellow]⚠️  Multi-account revocation completed with some failures.[/yellow]"
            )
            raise typer.Exit(1)
        else:
            return  # Successful completion, no need to raise Exit

    except ClientError as e:
        handle_aws_error(e, "MultiAccountRevoke")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _execute_multi_account_assignment(
    permission_set_name: str,
    principal_name: str,
    account_filter: str,
    principal_type: str = "USER",
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Execute multi-account assignment using account filter.

    This is a helper function that implements the multi-account assignment logic
    that was previously in the multi-assign command.
    """
    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account filtering
        organizations_client = aws_client.get_organizations_client()

        # Create and validate account filter
        account_filter_obj = AccountFilter(account_filter, organizations_client)
        validation_errors = account_filter_obj.validate_filter()

        if validation_errors:
            console.print("[red]Error: Invalid account filter.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on filter
        with console.status("[blue]Resolving accounts based on filter...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error resolving accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No accounts found matching the filter criteria.[/yellow]")
            console.print("[yellow]Please check your filter expression and try again.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]Found {len(accounts)} account(s) matching filter criteria.[/green]")

        # Show preview of accounts if requested or if there are many accounts
        if dry_run or len(accounts) > 5:
            console.print("\n[bold]Accounts to be processed:[/bold]")
            for i, account in enumerate(accounts[:10]):  # Show first 10
                console.print(f"  {i+1}. {account.get_display_name()}")

            if len(accounts) > 10:
                console.print(f"  ... and {len(accounts) - 10} more accounts")

        # Create multi-account assignment
        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="assign",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run
        if not dry_run:
            console.print(
                f"\n[bold yellow]⚠️  You are about to assign a permission set across {len(accounts)} account(s)[/bold yellow]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [blue]ASSIGN[/blue]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account assignment cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="assign"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.2:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account assignment...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="assign",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Assignment'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(
                f"  Skipped: [yellow]{stats['skipped_count']}[/yellow] ({stats['skip_rate']:.1f}%)"
            )

        console.print(f"  Duration: {stats['duration_seconds']:.2f} seconds")
        console.print(f"  Average Time per Account: {stats['average_processing_time']:.3f} seconds")

        # Show failed accounts if any
        if results.has_failures():
            console.print(f"\n[red]Failed Accounts ({len(results.failed_accounts)}):[/red]")
            for result in results.failed_accounts[:5]:  # Show first 5 failures
                console.print(f"  • {result.get_display_name()}: {result.get_error_summary()}")

            if len(results.failed_accounts) > 5:
                console.print(f"  ... and {len(results.failed_accounts) - 5} more failures")

        # Exit with appropriate code
        if dry_run:
            console.print(
                "\n[blue]Preview completed. Use --dry-run=false to execute the assignment.[/blue]"
            )
            return  # Successful completion, no need to raise Exit
        elif results.is_complete_success():
            console.print("\n[green]✓ Multi-account assignment completed successfully![/green]")
            return  # Successful completion, no need to raise Exit
        elif results.has_failures():
            console.print(
                "\n[yellow]⚠️  Multi-account assignment completed with some failures.[/yellow]"
            )
            raise typer.Exit(1)
        else:
            return  # Successful completion, no need to raise Exit

    except ClientError as e:
        handle_aws_error(e, "MultiAccountAssign")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _execute_multi_account_revocation(
    permission_set_name: str,
    principal_name: str,
    account_filter: str,
    principal_type: str = "USER",
    force: bool = False,
    dry_run: bool = False,
    batch_size: int = 10,
    continue_on_error: bool = True,
    profile: Optional[str] = None,
):
    """Execute multi-account revocation using account filter.

    This is a helper function that implements the multi-account revocation logic
    that was previously in the multi-revoke command.
    """
    # Validate profile and get profile data
    profile_name, profile_data = validate_profile(profile)

    # Validate SSO instance and get instance ARN and identity store ID
    instance_arn, identity_store_id = validate_sso_instance(profile_data)

    # Create AWS client manager
    aws_client = AWSClientManager(profile_name)

    try:
        # Get Organizations client for account filtering
        organizations_client = aws_client.get_organizations_client()

        # Create and validate account filter
        account_filter_obj = AccountFilter(account_filter, organizations_client)
        validation_errors = account_filter_obj.validate_filter()

        if validation_errors:
            console.print("[red]Error: Invalid account filter.[/red]")
            for error in validation_errors:
                console.print(f"  • {error.message}")
            raise typer.Exit(1)

        # Display filter information
        console.print(f"[blue]Account Filter:[/blue] {account_filter_obj.get_filter_description()}")

        # Resolve accounts based on filter
        with console.status("[blue]Resolving accounts based on filter...[/blue]"):
            try:
                accounts = account_filter_obj.resolve_accounts()
            except Exception as e:
                console.print(f"[red]Error resolving accounts: {str(e)}[/red]")
                raise typer.Exit(1)

        if not accounts:
            console.print("[yellow]No accounts found matching the filter criteria.[/yellow]")
            console.print("[yellow]Please check your filter expression and try again.[/yellow]")
            raise typer.Exit(0)

        console.print(f"[green]Found {len(accounts)} account(s) matching filter criteria.[/green]")

        # Show preview of accounts if requested or if there are many accounts
        if dry_run or len(accounts) > 5:
            console.print("\n[bold]Accounts to be processed:[/bold]")
            for i, account in enumerate(accounts[:10]):  # Show first 10
                console.print(f"  {i+1}. {account.get_display_name()}")

            if len(accounts) > 10:
                console.print(f"  ... and {len(accounts) - 10} more accounts")

        # Create multi-account assignment
        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation="revoke",
        )

        # Validate assignment
        validation_errors = multi_assignment.validate()
        if validation_errors:
            console.print("[red]Error: Assignment validation failed.[/red]")
            for error in validation_errors:
                console.print(f"  • {error}")
            raise typer.Exit(1)

        # Show confirmation unless dry run or force
        if not dry_run and not force:
            console.print(
                f"\n[bold red]⚠️  You are about to revoke a permission set across {len(accounts)} account(s)[/bold red]"
            )
            console.print(f"  Permission Set: [green]{permission_set_name}[/green]")
            console.print(f"  Principal: [cyan]{principal_name}[/cyan] ({principal_type})")
            console.print("  Operation: [red]REVOKE[/red]")
            console.print(f"  Batch Size: {batch_size}")
            console.print(f"  Continue on Error: {'Yes' if continue_on_error else 'No'}")
            console.print(
                "\n[red]This will remove the principal's access to the specified accounts through this permission set.[/red]"
            )

            confirm = typer.confirm("\nAre you sure you want to proceed?")
            if not confirm:
                console.print("[yellow]Multi-account revocation cancelled.[/yellow]")
                return

        # Create performance-optimized batch processor
        batch_processor, perf_config = create_performance_optimized_processor(
            aws_client_manager=aws_client, account_count=len(accounts), operation_type="revoke"
        )
        batch_processor.set_resource_resolver(instance_arn, identity_store_id)

        # Show performance info for large operations
        if len(accounts) > 10:
            console.print(f"[dim]Using optimized settings for {len(accounts)} accounts:[/dim]")
            console.print(
                f"[dim]  • Processing {perf_config.max_concurrent_accounts} accounts concurrently[/dim]"
            )
            console.print(f"[dim]  • Batch size: {perf_config.batch_size}[/dim]")
            console.print(
                f"[dim]  • Expected time: ~{len(accounts) * 1.0:.0f} seconds (vs ~{len(accounts) * 2.7:.0f}s unoptimized)[/dim]"
            )

        # Process multi-account operation
        console.print(
            f"\n[blue]{'Previewing' if dry_run else 'Processing'} multi-account revocation...[/blue]"
        )

        import asyncio

        results = asyncio.run(
            batch_processor.process_multi_account_operation(
                accounts=accounts,
                permission_set_name=permission_set_name,
                principal_name=principal_name,
                principal_type=principal_type,
                operation="revoke",
                instance_arn=instance_arn,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
        )

        # Display final results summary
        console.print(f"\n[bold]{'Preview' if dry_run else 'Revocation'} Summary:[/bold]")
        stats = results.get_summary_stats()

        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(
            f"  Successful: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)"
        )

        if stats["failed_count"] > 0:
            console.print(
                f"  Failed: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)"
            )

        if stats["skipped_count"] > 0:
            console.print(
                f"  Skipped: [yellow]{stats['skipped_count']}[/yellow] ({stats['skip_rate']:.1f}%)"
            )

        console.print(f"  Duration: {stats['duration_seconds']:.2f} seconds")
        console.print(f"  Average Time per Account: {stats['average_processing_time']:.3f} seconds")

        # Show failed accounts if any
        if results.has_failures():
            console.print(f"\n[red]Failed Accounts ({len(results.failed_accounts)}):[/red]")
            for result in results.failed_accounts[:5]:  # Show first 5 failures
                console.print(f"  • {result.get_display_name()}: {result.get_error_summary()}")

            if len(results.failed_accounts) > 5:
                console.print(f"  ... and {len(results.failed_accounts) - 5} more failures")

        # Exit with appropriate code
        if dry_run:
            console.print(
                "\n[blue]Preview completed. Use --dry-run=false to execute the revocation.[/blue]"
            )
            return  # Successful completion, no need to raise Exit
        elif results.is_complete_success():
            console.print("\n[green]✓ Multi-account revocation completed successfully![/green]")
            return  # Successful completion, no need to raise Exit
        elif results.has_failures():
            console.print(
                "\n[yellow]⚠️  Multi-account revocation completed with some failures.[/yellow]"
            )
            raise typer.Exit(1)
        else:
            return  # Successful completion, no need to raise Exit

    except ClientError as e:
        handle_aws_error(e, "MultiAccountRevoke")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
