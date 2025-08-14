"""Assignment listing command for awsideman.

This module provides the list command for displaying permission set assignments
in AWS Identity Center. It supports filtering by account, permission set, and principal.
"""

from typing import Any, Dict, Optional

import typer
from botocore.exceptions import ClientError
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...utils.config import Config
from ...utils.error_handler import handle_aws_error, handle_network_error
from ...utils.validators import validate_profile, validate_sso_instance
from .helpers import console, resolve_permission_set_info, resolve_principal_info

config = Config()


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
) -> None:
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
            list_params: Dict[str, Any] = {
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
                        permission_set_cache[assignment_info["PermissionSetArn"]] = (
                            permission_set_info
                        )
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
