"""Assignment listing command for awsideman.

This module provides the list command for displaying permission set assignments
in AWS Identity Center. It supports filtering by account, permission set, and principal.
"""

from typing import Any, Dict, Optional

import typer
from botocore.exceptions import ClientError
from rich.table import Table

from ...bulk.resolver import ResourceResolver
from ...utils.config import Config
from ...utils.error_handler import handle_network_error
from ...utils.validators import validate_sso_instance
from ..common import (
    advanced_cache_option,
    extract_standard_params,
    handle_aws_error,
    profile_option,
    region_option,
    show_cache_info,
    validate_profile_with_cache,
)
from .helpers import console, resolve_permission_set_info, resolve_principal_info

config = Config()


def list_assignments(
    account_id: Optional[str] = typer.Option(
        None, "--account-id", "-a", help="Filter by AWS account ID or name"
    ),
    permission_set: Optional[str] = typer.Option(
        None, "--permission-set", "-p", help="Filter by permission set name or ARN"
    ),
    principal: Optional[str] = typer.Option(
        None, "--principal", help="Filter by principal name or ID"
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
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    no_cache: bool = advanced_cache_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """List all permission set assignments.

    Displays a table of assignments with permission set name, principal name, principal type, and target account.
    Results can be filtered by account, permission set, and principal. All filters accept both names and IDs/ARNs.

    Examples:
        # List all assignments
        $ awsideman assignment list

        # List assignments for a specific account (by ID or name)
        $ awsideman assignment list --account-id 123456789012
        $ awsideman assignment list --account-id "Production Account"

        # List assignments for a specific permission set (by name or ARN)
        $ awsideman assignment list --permission-set "AdministratorAccess"
        $ awsideman assignment list --permission-set arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef

        # List assignments for a specific principal (by name or ID)
        $ awsideman assignment list --principal "john.doe@company.com"
        $ awsideman assignment list --principal "Admins"
        $ awsideman assignment list --principal user-1234567890abcdef

        # List assignments with a specific limit
        $ awsideman assignment list --limit 10
    """
    # Extract and process standard command parameters
    profile, region, enable_caching = extract_standard_params(profile, region, no_cache)

    # Show cache information if verbose
    show_cache_info(verbose)

    # Validate profile and get AWS client with cache integration
    profile_name, profile_data, aws_client = validate_profile_with_cache(
        profile=profile, enable_caching=enable_caching, region=region
    )

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

    # Get SSO admin client
    try:
        sso_admin_client = aws_client.get_sso_admin_client()
    except Exception as e:
        handle_aws_error(e, "creating SSO admin client", verbose=verbose)
        raise typer.Exit(1)

    # Get identity store client
    try:
        identity_store_client = aws_client.get_identity_store_client()
    except ClientError as e:
        handle_aws_error(e, "CreateIdentityStoreClient")
    except Exception as e:
        handle_network_error(e)

    # Resolve names to IDs/ARNs if provided
    resolved_account_id = account_id
    resolved_permission_set_arn = permission_set
    resolved_principal_id = principal

    if account_id or permission_set or principal:
        with console.status("[blue]Resolving resource names...[/blue]"):
            try:
                resolver = ResourceResolver(
                    aws_client_manager=aws_client,
                    instance_arn=instance_arn,
                    identity_store_id=identity_store_id,
                )

                # Resolve account name to ID if it's not already an ID
                if account_id and not account_id.isdigit():
                    account_result = resolver.resolve_account_name(account_id)
                    if account_result.success:
                        resolved_account_id = account_result.resolved_value
                        console.print(
                            f"[green]Resolved account '{account_id}' to ID: {resolved_account_id}[/green]"
                        )
                    else:
                        console.print(f"[red]Error: {account_result.error_message}[/red]")
                        raise typer.Exit(1)

                # Resolve permission set name to ARN if it's not already an ARN
                if permission_set and not permission_set.startswith("arn:aws:sso:::"):
                    ps_result = resolver.resolve_permission_set_name(permission_set)
                    if ps_result.success:
                        resolved_permission_set_arn = ps_result.resolved_value
                        console.print(
                            f"[green]Resolved permission set '{permission_set}' to ARN: {resolved_permission_set_arn}[/green]"
                        )
                    else:
                        console.print(f"[red]Error: {ps_result.error_message}[/red]")
                        raise typer.Exit(1)

                # Resolve principal name to ID if it's not already an ID
                if principal and not principal.startswith(("user-", "group-")):
                    if not principal_type:
                        console.print(
                            "[red]Error: Principal type must be specified when using principal names.[/red]"
                        )
                        console.print(
                            "[yellow]Use --principal-type USER or --principal-type GROUP[/yellow]"
                        )
                        raise typer.Exit(1)

                    principal_result = resolver.resolve_principal_name(principal, principal_type)
                    if principal_result.success:
                        resolved_principal_id = principal_result.resolved_value
                        console.print(
                            f"[green]Resolved principal '{principal}' to ID: {resolved_principal_id}[/green]"
                        )
                    else:
                        console.print(f"[red]Error: {principal_result.error_message}[/red]")
                        raise typer.Exit(1)

            except Exception as e:
                console.print(f"[red]Error resolving resource names: {str(e)}[/red]")
                raise typer.Exit(1)

    # Initialize pagination variables
    current_token = next_token

    # Display a message indicating that we're fetching assignments
    with console.status("[blue]Fetching permission set assignments...[/blue]"):
        try:
            # Initialize variables for pagination
            all_assignments = []

            # Handle different filtering scenarios
            if (
                (resolved_permission_set_arn and not resolved_account_id)
                or (resolved_principal_id and not resolved_account_id)
                or (resolved_account_id and not resolved_permission_set_arn)
                or (
                    not resolved_account_id
                    and not resolved_permission_set_arn
                    and not resolved_principal_id
                )
            ):
                # If only permission set, principal, or account is specified, we need to iterate through all accounts
                if resolved_permission_set_arn:
                    console.print(
                        "[blue]Searching across all accounts for permission set assignments...[/blue]"
                    )
                elif resolved_principal_id:
                    console.print(
                        "[blue]Searching across all accounts for principal assignments...[/blue]"
                    )
                elif resolved_account_id:
                    console.print(
                        "[blue]Searching across all permission sets for account assignments...[/blue]"
                    )
                else:
                    console.print(
                        "[blue]Searching across all accounts and permission sets for all assignments...[/blue]"
                    )

                # Get all accounts first
                try:
                    org_client = aws_client.get_raw_organizations_client()
                    paginator = org_client.get_paginator("list_accounts")
                    accounts = []
                    for page in paginator.paginate():
                        accounts.extend(page.get("Accounts", []))

                    # Get all permission sets if we need to search by principal, account only, or no filters
                    permission_sets = []
                    if (
                        resolved_principal_id
                        or (resolved_account_id and not resolved_permission_set_arn)
                        or (
                            not resolved_account_id
                            and not resolved_permission_set_arn
                            and not resolved_principal_id
                        )
                    ):
                        ps_paginator = sso_admin_client.get_paginator("list_permission_sets")
                        for page in ps_paginator.paginate(InstanceArn=instance_arn):
                            permission_sets.extend(page.get("PermissionSets", []))

                    # Check each account for assignments
                    for account in accounts:
                        account_id = account["Id"]

                        # If we have a specific account filter, only check that account
                        if resolved_account_id and account_id != resolved_account_id:
                            continue

                        try:
                            if resolved_permission_set_arn:
                                # Search by permission set
                                response = sso_admin_client.list_account_assignments(
                                    InstanceArn=instance_arn,
                                    AccountId=account_id,
                                    PermissionSetArn=resolved_permission_set_arn,
                                )
                                all_assignments.extend(response.get("AccountAssignments", []))
                            elif resolved_principal_id:
                                # Search by principal across all permission sets
                                for permission_set_arn in permission_sets:
                                    try:
                                        response = sso_admin_client.list_account_assignments(
                                            InstanceArn=instance_arn,
                                            AccountId=account_id,
                                            PermissionSetArn=permission_set_arn,
                                        )
                                        for assignment in response.get("AccountAssignments", []):
                                            if (
                                                assignment.get("PrincipalId")
                                                == resolved_principal_id
                                            ):
                                                all_assignments.append(assignment)
                                    except Exception:
                                        continue
                            elif resolved_account_id:
                                # Search by account across all permission sets
                                for permission_set_arn in permission_sets:
                                    try:
                                        response = sso_admin_client.list_account_assignments(
                                            InstanceArn=instance_arn,
                                            AccountId=account_id,
                                            PermissionSetArn=permission_set_arn,
                                        )
                                        all_assignments.extend(
                                            response.get("AccountAssignments", [])
                                        )
                                    except Exception:
                                        continue
                            else:
                                # Search for all assignments (no filters)
                                for permission_set_arn in permission_sets:
                                    try:
                                        response = sso_admin_client.list_account_assignments(
                                            InstanceArn=instance_arn,
                                            AccountId=account_id,
                                            PermissionSetArn=permission_set_arn,
                                        )
                                        all_assignments.extend(
                                            response.get("AccountAssignments", [])
                                        )
                                    except Exception:
                                        continue
                        except Exception:
                            # Skip accounts we can't access
                            continue
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Unable to access AWS Organizations. Cannot search across all accounts. Error: {str(e)}[/yellow]"
                    )
                    console.print(
                        "[yellow]Try specifying an account ID to search within a specific account.[/yellow]"
                    )
                    raise typer.Exit(1)
            else:
                # Standard filtering with account ID and/or permission set
                list_params: Dict[str, Any] = {
                    "InstanceArn": instance_arn,
                }

                # Add filters if provided
                if resolved_account_id:
                    list_params["AccountId"] = resolved_account_id

                if resolved_permission_set_arn:
                    list_params["PermissionSetArn"] = resolved_permission_set_arn

                # Note: Principal filtering will be done locally after fetching results
                # as the AWS API doesn't support PrincipalId/PrincipalType parameters
                if resolved_principal_id and not principal_type:
                    console.print(
                        "[yellow]Warning: Principal ID provided without principal type. Using default type 'USER' for filtering.[/yellow]"
                    )
                    principal_type = "USER"

                # Set the maximum number of results to return if limit is provided
                if limit:
                    list_params["MaxResults"] = min(
                        limit, 100
                    )  # AWS API typically limits to 100 items per page

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
            if resolved_principal_id:
                filtered_assignments = []
                for assignment in all_assignments:
                    if assignment.get("PrincipalId") == resolved_principal_id:
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

            # Create a dictionary to cache permission set, principal, and account information
            permission_set_cache = {}
            principal_cache = {}
            account_cache = {}

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
                        principal_cache[principal_cache_key] = {
                            "PrincipalName": "Unknown Principal"
                        }

                # Add principal name to assignment info
                assignment_info["PrincipalName"] = principal_cache[principal_cache_key].get(
                    "PrincipalName"
                )

                # Resolve account name if not already in cache
                if assignment_info["TargetId"] not in account_cache:
                    try:
                        # Get account name from Organizations
                        org_client = aws_client.get_raw_organizations_client()
                        paginator = org_client.get_paginator("list_accounts")
                        account_name = None
                        for page in paginator.paginate():
                            for account in page.get("Accounts", []):
                                if account["Id"] == assignment_info["TargetId"]:
                                    account_name = account.get("Name")
                                    break
                            if account_name:
                                break
                        account_cache[assignment_info["TargetId"]] = (
                            account_name or assignment_info["TargetId"]
                        )
                    except Exception:
                        account_cache[assignment_info["TargetId"]] = assignment_info["TargetId"]

                # Add account name to assignment info
                account_name = account_cache[assignment_info["TargetId"]]
                if account_name and account_name != assignment_info["TargetId"]:
                    assignment_info["AccountDisplay"] = (
                        f"{account_name} ({assignment_info['TargetId']})"
                    )
                else:
                    assignment_info["AccountDisplay"] = assignment_info["TargetId"]

                # Add the processed assignment to the list
                processed_assignments.append(assignment_info)

            # Check if there are any assignments to display
            if not processed_assignments:
                console.print("[yellow]No assignments found.[/yellow]")
                if account_id or permission_set or principal:
                    console.print("[yellow]Try removing filters to see more results.[/yellow]")
                raise typer.Exit(0)

            # Create a table for displaying assignments
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Permission Set", style="green")
            table.add_column("Principal Name", style="cyan")
            table.add_column("Principal Type", style="magenta")
            table.add_column("Account", style="yellow")

            # Add rows to the table
            for assignment in processed_assignments:
                table.add_row(
                    assignment.get("PermissionSetName", "Unknown"),
                    assignment.get("PrincipalName", "Unknown"),
                    assignment.get("PrincipalType", "Unknown"),
                    assignment.get("AccountDisplay", "Unknown"),
                )

            # Display filter information if any filters are applied
            filters_applied = []
            if account_id:
                filters_applied.append(f"Account: {account_id}")
            if permission_set:
                filters_applied.append(f"Permission Set: {permission_set}")
            if principal:
                filters_applied.append(f"Principal: {principal}")
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
