"""Group member management commands for awsideman."""

import csv
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from rich.table import Table

from ...utils.error_handler import handle_aws_error, handle_network_error
from .get import get_group
from .helpers import (
    _find_user_id,
    console,
    get_single_key,
    validate_limit,
    validate_non_empty,
    validate_sso_instance,
)


def _extract_email(user: dict) -> str:
    """Safely extract email from user data."""
    try:
        emails = user.get("Emails", [])
        if emails and len(emails) > 0 and isinstance(emails[0], dict):
            return emails[0].get("Value", "")
        return ""
    except (IndexError, TypeError, AttributeError):
        return ""


def _list_members_internal(
    group_identifier: str,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
    debug: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Internal implementation of list_members that can be called directly from tests.

    Args:
        group_identifier: Group name or ID to list members for
        limit: Maximum number of members to return in a single page
        next_token: Pagination token
        profile: AWS profile to use

    Returns:
        Tuple of (members, next_token)
    """
    try:
        # Validate inputs
        if not validate_non_empty(group_identifier, "Group identifier"):
            raise typer.Exit(1)

        if limit and not validate_limit(limit):
            raise typer.Exit(1)

        # Validate profile and get AWS client with cache integration
        from ..common import validate_profile_with_cache

        profile_name, profile_data, aws_client = validate_profile_with_cache(
            profile=profile, enable_caching=True, region=None
        )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Get the identity store client (now cached)
        identity_store = aws_client.get_identity_store_client()

        # Check permissions in debug mode
        if debug:
            try:
                # Try to list a few users to check permissions
                identity_store.list_users(IdentityStoreId=identity_store_id, MaxResults=1)
                console.print("[green]DEBUG: Permission check passed - can list users[/green]")
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_message = e.response.get("Error", {}).get("Message", str(e))
                console.print("[red]DEBUG: Permission check failed - cannot list users:[/red]")
                console.print(f"[red]  Error Code: {error_code}[/red]")
                console.print(f"[red]  Error Message: {error_message}[/red]")
                console.print("[red]  This may explain why user details are showing as N/A[/red]")

        # Check if group_identifier is a UUID (group ID) or if we need to search
        uuid_pattern = (
            r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{10,})"
        )
        if re.match(uuid_pattern, group_identifier, re.IGNORECASE):
            # Direct lookup by group ID
            group_id = group_identifier
        else:
            # Search for group by display name
            console.print(f"[blue]Searching for group: {group_identifier}[/blue]")

            # Search by display name
            try:
                search_response = identity_store.list_groups(
                    IdentityStoreId=identity_store_id,
                    Filters=[{"AttributePath": "DisplayName", "AttributeValue": group_identifier}],
                )

                groups = search_response.get("Groups", [])

                # Handle search results
                if not groups:
                    console.print(
                        f"[red]Error: No group found with name '{group_identifier}'.[/red]"
                    )
                    console.print("[yellow]Please check the group name and try again.[/yellow]")
                    console.print(
                        "[yellow]You can list available groups with 'awsideman group list'.[/yellow]"
                    )
                    raise typer.Exit(1)
                elif len(groups) > 1:
                    console.print(
                        f"[yellow]Warning: Multiple groups found matching '{group_identifier}'. Using the first match.[/yellow]"
                    )

                # Use the first group found
                group_id = groups[0].get("GroupId")
                console.print(
                    f"[green]Found group: {groups[0].get('DisplayName', 'N/A')} (ID: {group_id})[/green]"
                )

            except ClientError as search_error:
                console.print(
                    f"[red]Error searching for group: {search_error.response.get('Error', {}).get('Message', str(search_error))}[/red]"
                )
                console.print(
                    "[yellow]Try using the group ID instead of the name if this error persists.[/yellow]"
                )
                handle_aws_error(search_error, operation="ListGroups")
                raise typer.Exit(1)

        # Get group memberships
        try:
            list_params = {"IdentityStoreId": identity_store_id, "GroupId": group_id}

            if limit:
                list_params["MaxResults"] = limit

            if next_token:
                list_params["NextToken"] = next_token

            memberships_response = identity_store.list_group_memberships(**list_params)
            memberships = memberships_response.get("GroupMemberships", [])
            next_token_result = memberships_response.get("NextToken")

            # Display the results
            if not memberships:
                console.print("[yellow]No members found in this group.[/yellow]")
                return [], next_token_result

            # Display pagination status
            page_info = ""
            if next_token_result:
                page_info = " (more results available)"
            if limit:
                page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"

            console.print(f"[green]Found {len(memberships)} members{page_info}.[/green]")

            # Create a table for displaying members
            table = Table(title=f"Members of Group {group_identifier}")

            # Add columns to the table
            table.add_column("Membership ID", style="cyan")
            table.add_column("User ID", style="blue")
            table.add_column("Username", style="green")
            table.add_column("Display Name", style="yellow")

            # Get user details for each membership
            for membership in memberships:
                membership_id = membership.get("MembershipId", "")
                user_id = membership.get("MemberId", {}).get("UserId", "")

                # Get user details
                try:
                    if debug:
                        console.print(f"[blue]DEBUG: Getting details for user {user_id}[/blue]")

                    user_response = identity_store.describe_user(
                        IdentityStoreId=identity_store_id, UserId=user_id
                    )

                    # The AWS Identity Store API returns user data at the top level, not nested under "User"
                    user = user_response

                    username = user.get("UserName", "N/A")
                    display_name = user.get("DisplayName", "N/A")

                except ClientError as e:
                    # Log the specific error for debugging
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    if debug:
                        # Show detailed error information in debug mode
                        console.print(f"[red]DEBUG: Error retrieving user {user_id}:[/red]")
                        console.print(f"[red]  Error Code: {error_code}[/red]")
                        console.print(f"[red]  Error Message: {error_message}[/red]")
                        console.print(f"[red]  User ID: {user_id}[/red]")
                        console.print(f"[red]  Identity Store ID: {identity_store_id}[/red]")

                    if error_code == "AccessDenied":
                        console.print(
                            f"[yellow]Warning: Access denied when retrieving details for user {user_id}. Check permissions.[/yellow]"
                        )
                    elif error_code == "ResourceNotFoundException":
                        console.print(
                            f"[yellow]Warning: User {user_id} not found. User may have been deleted.[/yellow]"
                        )
                    else:
                        console.print(
                            f"[yellow]Warning: Error retrieving user {user_id} details: {error_code} - {error_message}[/yellow]"
                        )

                    # Try to get basic user info from the membership data if available
                    username = "N/A (Error)"
                    display_name = "N/A (Error)"

                    # If we have the user ID, we can at least show that
                    if user_id:
                        username = f"User ID: {user_id[:8]}..."
                        display_name = "Details unavailable"

                # Add the row to the table
                table.add_row(membership_id, user_id, username, display_name)

            # Display the table
            console.print(table)

            # Handle pagination - interactive by default
            if next_token_result:
                console.print(
                    "\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]"
                )
                try:
                    # Wait for single key press
                    key = get_single_key()

                    # If the user pressed Enter (or Return), fetch the next page
                    if key in ["\r", "\n", ""]:
                        console.print("\n[blue]Fetching next page...[/blue]\n")
                        # Call _list_members_internal recursively with the next token
                        return _list_members_internal(
                            group_identifier, limit, next_token_result, profile, debug
                        )
                    else:
                        console.print("\n[yellow]Pagination stopped.[/yellow]")
                except KeyboardInterrupt:
                    console.print("\n[yellow]Pagination stopped by user.[/yellow]")

            return memberships, next_token_result

        except ClientError as e:
            handle_aws_error(e, operation="ListGroupMemberships")
            raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="ListGroupMemberships")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def list_members(
    group_identifier: str = typer.Argument(..., help="Group name or ID to list members for"),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of members to return in a single page"
    ),
    next_token: Optional[str] = typer.Option(
        None, "--next-token", "-n", help="Pagination token (for internal use)"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format (json, csv, table)"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
    debug: bool = typer.Option(
        False, "--debug", "-d", help="Enable debug mode for troubleshooting user detail retrieval"
    ),
):
    """List all members of a group.

    Displays a table of users who are members of the specified group.
    Results can be paginated and exported in various formats.

    If user details show as "N/A", use --debug to see detailed error information.

    Examples:
        # List members of a group by name
        $ awsideman group list-members Administrators

        # List members with a limit
        $ awsideman group list-members Developers --limit 50

        # Export to CSV
        $ awsideman group list-members Engineers --format csv --output engineers.csv

        # Export to JSON
        $ awsideman group list-members TestGroup --format json --output testgroup.json

        # List members using a specific AWS profile
        $ awsideman group list-members Engineers --profile dev-account

        # List members with debug information
        $ awsideman group list-members TestGroup --debug
    """
    memberships, next_token_result = _list_members_internal(
        group_identifier, limit, next_token, profile, debug
    )

    # Process memberships data for export formats
    if output_format in ["json", "csv"]:
        # Get AWS clients to enrich the data
        from ..common import validate_profile_with_cache

        profile, region, enable_caching = validate_profile_with_cache(profile, None)

        from ...aws_clients.manager import AWSClientManager

        client_manager = AWSClientManager(profile=profile, region=region)
        identitystore_client = client_manager.get_identity_store_client()

        # Get SSO instance info
        instance_arn, identity_store_id = validate_sso_instance(profile)

        # Process each membership to get user details
        processed_memberships = []
        for membership in memberships:
            membership_id = membership.get("MembershipId", "")
            user_id = membership.get("MemberId", {}).get("UserId", "")

            # Get user details
            try:
                user_response = identitystore_client.describe_user(
                    IdentityStoreId=identity_store_id, UserId=user_id
                )
                user = user_response
                username = user.get("UserName", "N/A")
                display_name = user.get("DisplayName", "N/A")
            except Exception:
                username = "N/A"
                display_name = "N/A"

            processed_membership = {
                "membership_id": membership_id,
                "user_id": user_id,
                "user_name": username,
                "display_name": display_name,
            }
            processed_memberships.append(processed_membership)

    # Handle different output formats
    if output_format == "json":
        output_data = {
            "group_identifier": group_identifier,
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_members": len(processed_memberships),
            "members": processed_memberships,
        }

        if output_file:
            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=2)
            console.print(
                f"[green]Exported {len(processed_memberships)} members to {output_file}[/green]"
            )
        else:
            print(json.dumps(output_data, indent=2))

    elif output_format == "csv":
        if not processed_memberships:
            console.print("[yellow]No members to export.[/yellow]")
            return memberships, next_token_result, group_identifier

        # Define CSV columns
        fieldnames = ["membership_id", "user_id", "user_name", "display_name"]

        if output_file:
            with open(output_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(processed_memberships)
            console.print(
                f"[green]Exported {len(processed_memberships)} members to {output_file}[/green]"
            )
        else:
            import sys

            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(processed_memberships)
    else:
        # Table format (default behavior)
        pass  # The existing table display logic is already in _list_members_internal

    # Return the expected tuple format for tests
    return memberships, next_token_result, group_identifier


def add_member(
    group_identifier: str = typer.Argument(..., help="Group name or ID to add member to"),
    user_identifier: str = typer.Argument(
        ..., help="User ID, username, or email to add to the group"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Add a user to a group.

    Adds the specified user to the specified group.
    Users can be identified by their ID, username, or email.

    Examples:
        # Add a user to a group by username
        $ awsideman group add-member Developers john.doe

        # Add a user by email
        $ awsideman group add-member Administrators admin@example.com

        # Add a user using a specific AWS profile
        $ awsideman group add-member Engineers jane.smith --profile dev-account
    """
    try:
        # Validate inputs
        if not validate_non_empty(group_identifier, "Group identifier"):
            raise typer.Exit(1)

        if not validate_non_empty(user_identifier, "User identifier"):
            raise typer.Exit(1)

        # Validate profile and get AWS client with cache integration
        from ..common import validate_profile_with_cache

        profile_name, profile_data, aws_client = validate_profile_with_cache(
            profile=profile, enable_caching=True, region=None
        )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Get the identity store client (now cached)
        identity_store = aws_client.get_identity_store_client()

        # Get group details
        group_details = get_group(group_identifier, profile)
        group_id = group_details.get("GroupId")
        group_name = group_details.get("DisplayName", group_identifier)

        # Find the user ID
        try:
            user_id = _find_user_id(identity_store, identity_store_id, user_identifier)
        except ValueError as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(1)

        # Get user details for display
        try:
            user_details = identity_store.describe_user(
                IdentityStoreId=identity_store_id, UserId=user_id
            )
            username = user_details.get("UserName", user_identifier)
        except ClientError:
            username = user_identifier

        # Inform user about the operation
        console.print(f"[blue]Adding user '{username}' to group '{group_name}'...[/blue]")

        # Check if user is already a member
        try:
            memberships_response = identity_store.list_group_memberships(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            existing_memberships = memberships_response.get("GroupMemberships", [])
            for membership in existing_memberships:
                if membership.get("MemberId", {}).get("UserId") == user_id:
                    console.print(
                        f"[yellow]User '{username}' is already a member of group '{group_name}'.[/yellow]"
                    )
                    console.print(
                        "[blue]No action needed - the user is already in the group.[/blue]"
                    )
                    return None

        except ClientError:
            # If we can't check existing memberships, continue and let the create operation handle it
            console.print(
                f"[yellow]Warning: Could not check existing memberships for group '{group_name}'. Proceeding with add operation...[/yellow]"
            )
            console.print(
                "[blue]If the user is already a member, you'll see a clear message below.[/blue]"
            )

        # Add the user to the group
        try:
            response = identity_store.create_group_membership(
                IdentityStoreId=identity_store_id, GroupId=group_id, MemberId={"UserId": user_id}
            )

            membership_id = response.get("MembershipId")
            console.print(
                f"[green]Successfully added user '{username}' to group '{group_name}'.[/green]"
            )

            # Cache invalidation is now handled automatically by the cached client

            return membership_id

        except ClientError as e:
            # Handle the specific case where user is already a member
            error_code = e.response.get("Error", {}).get("Code", "")
            error_message = e.response.get("Error", {}).get("Message", "")

            if (
                error_code == "ConflictException"
                and "Member and Group relationship already exists" in error_message
            ):
                console.print(
                    f"[yellow]User '{username}' is already a member of group '{group_name}'.[/yellow]"
                )
                return None
            else:
                # Handle other AWS errors using the standard error handler
                handle_aws_error(e, operation="CreateGroupMembership")
                raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="CreateGroupMembership")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def remove_member(
    group_identifier: str = typer.Argument(..., help="Group name or ID to remove member from"),
    user_identifier: str = typer.Argument(
        ..., help="User ID, username, or email to remove from the group"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Remove a user from a group.

    Removes the specified user from the specified group.
    Users can be identified by their ID, username, or email.
    Requires confirmation unless the --force flag is used.

    Examples:
        # Remove a user from a group with confirmation
        $ awsideman group remove-member Developers john.doe

        # Remove a user by email
        $ awsideman group remove-member Administrators admin@example.com

        # Force remove without confirmation
        $ awsideman group remove-member TestGroup test.user --force

        # Remove using a specific AWS profile
        $ awsideman group remove-member Engineers jane.smith --profile dev-account
    """
    try:
        # Validate inputs
        if not validate_non_empty(group_identifier, "Group identifier"):
            raise typer.Exit(1)

        if not validate_non_empty(user_identifier, "User identifier"):
            raise typer.Exit(1)

        # Validate profile and get AWS client with cache integration
        from ..common import validate_profile_with_cache

        profile_name, profile_data, aws_client = validate_profile_with_cache(
            profile=profile, enable_caching=True, region=None
        )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Get the identity store client (now cached)
        identity_store = aws_client.get_identity_store_client()

        # Get group details
        group_details = get_group(group_identifier, profile)
        group_id = group_details.get("GroupId")
        group_name = group_details.get("DisplayName", group_identifier)

        # Find the user ID
        try:
            user_id = _find_user_id(identity_store, identity_store_id, user_identifier)
        except ValueError as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            raise typer.Exit(1)

        # Get user details for display
        try:
            user_details = identity_store.describe_user(
                IdentityStoreId=identity_store_id, UserId=user_id
            )
            username = user_details.get("UserName", user_identifier)
        except ClientError:
            username = user_identifier

        # Find the membership to remove
        try:
            memberships_response = identity_store.list_group_memberships(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            existing_memberships = memberships_response.get("GroupMemberships", [])
            membership_id = None

            for membership in existing_memberships:
                if membership.get("MemberId", {}).get("UserId") == user_id:
                    membership_id = membership.get("MembershipId")
                    break

            if not membership_id:
                console.print(
                    f"[yellow]User '{username}' is not a member of group '{group_name}'.[/yellow]"
                )
                raise typer.Exit(1)

        except ClientError as e:
            handle_aws_error(e, operation="ListGroupMemberships")
            raise typer.Exit(1)

        # Check if force option is used, otherwise prompt for confirmation
        if not force:
            console.print(
                f"[yellow]Warning: This will remove user '{username}' from group '{group_name}'.[/yellow]"
            )
            console.print("\n[blue]Are you sure you want to continue? (y/N)[/blue]")

            try:
                # Wait for user input
                confirmation = get_single_key().lower()

                # Check if the user confirmed the removal
                if confirmation != "y":
                    console.print("\n[yellow]Member removal cancelled.[/yellow]")
                    raise typer.Exit(0)

                console.print()  # Add a newline for better formatting

            except KeyboardInterrupt:
                console.print("\n[yellow]Member removal cancelled.[/yellow]")
                return

        # Remove the user from the group
        try:
            identity_store.delete_group_membership(
                IdentityStoreId=identity_store_id, MembershipId=membership_id
            )

            console.print(
                f"[green]Successfully removed user '{username}' from group '{group_name}'.[/green]"
            )

            # Cache invalidation is now handled automatically by the cached client

            return True

        except ClientError as e:
            handle_aws_error(e, operation="DeleteGroupMembership")
            raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="DeleteGroupMembership")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def export_members(
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format (json, csv, table)"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path (optional)"
    ),
    group_filter: Optional[str] = typer.Option(
        None,
        "--filter",
        help="Filter groups by attribute in format 'attribute=value' (e.g., DisplayName=engineering)",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    try:
        return _export_members_impl(output_format, output_file, group_filter, profile, verbose)
    except Exception as e:
        console.print(f"[red]Error in export_members: {e}[/red]")
        console.print(f"[red]Error type: {type(e)}[/red]")
        import traceback

        console.print(f"[red]Traceback: {traceback.format_exc()}[/red]")
        raise


def _export_members_impl(
    output_format: str,
    output_file: Optional[str],
    group_filter: Optional[str],
    profile: Optional[str],
    verbose: bool,
):
    """Export all group memberships across all groups.

    Exports a comprehensive list of all users and their group memberships.
    Automatically handles pagination to retrieve all memberships across all pages.
    Results can be filtered by group attributes and exported in various formats.

    Examples:
        # Export all group memberships to CSV
        $ awsideman group export-members --format csv --output group_memberships.csv

        # Export filtered groups to JSON
        $ awsideman group export-members --format json --filter "DisplayName=Prod*" --output prod_groups.json

        # Export to table format (default)
        $ awsideman group export-members --verbose
    """
    try:
        # Validate profile and get AWS client with cache integration
        from ..common import validate_profile_with_cache

        profile, region_data, enable_caching = validate_profile_with_cache(profile, None)

        # Extract region string from the region data
        if isinstance(region_data, dict):
            region = region_data.get("region", "eu-north-1")
        else:
            region = region_data

        # Get AWS clients
        from ...aws_clients.manager import AWSClientManager

        client_manager = AWSClientManager(profile=profile, region=region)
        identitystore_client = client_manager.get_identity_store_client()

        # Get SSO instance info from region data
        try:
            if isinstance(region_data, dict):
                instance_arn = region_data.get("sso_instance_arn")
                identity_store_id = region_data.get("identity_store_id")
                if not instance_arn or not identity_store_id:
                    raise ValueError("SSO instance information not found in profile data")
            else:
                instance_arn, identity_store_id = validate_sso_instance(profile)
        except Exception as e:
            console.print(f"[red]Error validating SSO instance: {e}[/red]")
            console.print(f"[red]Error type: {type(e)}[/red]")
            raise

        console.print("[green]Exporting group memberships...[/green]")

        # Get all groups
        try:
            from .list import _list_groups_internal

            groups, _ = _list_groups_internal(
                filter=group_filter,
                limit=None,
                next_token=None,
                profile=profile,
                region=region,
                enable_caching=enable_caching,
                verbose=verbose,
                interactive=False,
                suppress_display=True,
            )
        except Exception as e:
            console.print(f"[red]Error getting groups: {e}[/red]")
            console.print(f"[red]Error type: {type(e)}[/red]")
            raise

        if not groups:
            console.print("[yellow]No groups found matching the filter criteria.[/yellow]")
            return

        # Collect all group memberships
        all_memberships = []

        for group in groups:
            group_id = group["GroupId"]
            group_name = group["DisplayName"]

            if verbose:
                console.print(f"[blue]Processing group: {group_name}[/blue]")

            # Get members for this group with pagination
            try:
                # Use paginator to get all memberships across all pages
                paginator = identitystore_client.get_paginator("list_group_memberships")
                memberships = []

                for page in paginator.paginate(IdentityStoreId=identity_store_id, GroupId=group_id):
                    memberships.extend(page.get("GroupMemberships", []))

                if verbose and len(memberships) > 0:
                    console.print(
                        f"[blue]Found {len(memberships)} members in group {group_name}[/blue]"
                    )

                # Get user details for each membership
                for membership in memberships:
                    user_id = membership["MemberId"]["UserId"]

                    try:
                        user_response = identitystore_client.describe_user(
                            IdentityStoreId=identity_store_id, UserId=user_id
                        )
                        # The AWS Identity Store API returns user data at the top level, not nested under "User"
                        user = user_response

                        membership_data = {
                            "group_id": group_id,
                            "group_name": group_name,
                            "group_description": group.get("Description", ""),
                            "membership_id": membership["MembershipId"],
                            "user_id": user_id,
                            "user_name": user.get("UserName", ""),
                            "display_name": user.get("DisplayName", ""),
                            "email": _extract_email(user),
                            "export_timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        all_memberships.append(membership_data)

                    except ClientError as user_error:
                        if verbose:
                            console.print(
                                f"[yellow]Warning: Could not get details for user {user_id}: {user_error}[/yellow]"
                            )
                        # Still include the membership with limited data
                        membership_data = {
                            "group_id": group_id,
                            "group_name": group_name,
                            "group_description": group.get("Description", ""),
                            "membership_id": membership["MembershipId"],
                            "user_id": user_id,
                            "user_name": "N/A",
                            "display_name": "N/A",
                            "email": "N/A",
                            "export_timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        all_memberships.append(membership_data)

            except ClientError as e:
                console.print(
                    f"[yellow]Warning: Could not get members for group {group_name}: {e}[/yellow]"
                )
                continue

        # Generate output
        if output_format == "json":
            output_data = {
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "total_memberships": len(all_memberships),
                "total_groups": len(groups),
                "filter_applied": group_filter,
                "memberships": all_memberships,
            }

            if output_file:
                with open(output_file, "w") as f:
                    json.dump(output_data, f, indent=2)
                console.print(
                    f"[green]Exported {len(all_memberships)} memberships to {output_file}[/green]"
                )
            else:
                print(json.dumps(output_data, indent=2))

        elif output_format == "csv":
            if not all_memberships:
                console.print("[yellow]No memberships to export.[/yellow]")
                return

            # Process memberships for CSV output
            processed_memberships = []

            for membership in all_memberships:
                processed_membership = {
                    "group_name": membership.get("group_name", ""),
                    "user_name": membership.get("user_name", ""),
                    "display_name": membership.get("display_name", ""),
                    "group_id": membership.get("group_id", ""),
                    "membership_id": membership.get("membership_id", ""),
                }

                processed_memberships.append(processed_membership)

            # Check if any user has a different email than username
            needs_email_column = False
            for membership in all_memberships:
                user_name = membership.get("user_name", "")
                email = membership.get("email", "")
                if user_name != email and email.strip() != "":
                    needs_email_column = True
                    break

            # Add email column to all memberships if needed
            if needs_email_column:
                for i, membership in enumerate(all_memberships):
                    user_name = membership.get("user_name", "")
                    email = membership.get("email", "")
                    if user_name != email and email.strip() != "":
                        processed_memberships[i]["email"] = email
                    else:
                        processed_memberships[i]["email"] = ""

            # Define CSV columns based on whether email is needed
            base_fieldnames = [
                "group_name",
                "user_name",
                "display_name",
                "group_id",
                "membership_id",
            ]

            if needs_email_column:
                fieldnames = base_fieldnames + ["email"]
            else:
                fieldnames = base_fieldnames

            try:
                if output_file:
                    with open(output_file, "w", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(processed_memberships)
                    console.print(
                        f"[green]Exported {len(processed_memberships)} memberships to {output_file}[/green]"
                    )
                else:
                    import sys

                    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(processed_memberships)
            except Exception as e:
                console.print(f"[red]Error writing CSV: {e}[/red]")
                console.print(f"[red]Error type: {type(e)}[/red]")
                if processed_memberships:
                    console.print(f"[red]First membership: {processed_memberships[0]}[/red]")
                    console.print(
                        f"[red]First membership type: {type(processed_memberships[0])}[/red]"
                    )
                raise
        else:
            # Table format
            if not all_memberships:
                console.print("[yellow]No memberships found.[/yellow]")
                return

            table = Table(title="Group Memberships")
            table.add_column("Group Name", style="cyan")
            table.add_column("User Name", style="green")
            table.add_column("Display Name", style="yellow")
            table.add_column("Email", style="blue")

            for membership in all_memberships:
                table.add_row(
                    membership["group_name"],
                    membership["user_name"],
                    membership["display_name"],
                    membership["email"],
                )

            if output_file:
                # Save table to file
                from rich.console import Console

                file_console = Console(file=open(output_file, "w", encoding="utf-8"))
                file_console.print(table)
                file_console.file.close()
                console.print(
                    f"[green]Exported {len(all_memberships)} memberships to {output_file}[/green]"
                )
            else:
                console.print(table)

        # Summary
        console.print(
            f"[green]Exported {len(all_memberships)} memberships from {len(groups)} groups[/green]"
        )

    except ClientError as e:
        handle_aws_error(e, operation="ExportGroupMembers")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
