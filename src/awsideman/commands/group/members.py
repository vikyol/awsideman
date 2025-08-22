"""Group member management commands for awsideman."""

import re
from typing import Any, Dict, List, Optional, Tuple

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...utils.error_handler import handle_aws_error, handle_network_error
from .get import get_group
from .helpers import (
    _find_user_id,
    console,
    get_single_key,
    validate_limit,
    validate_non_empty,
    validate_profile,
    validate_sso_instance,
)


def _list_members_internal(
    group_identifier: str,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
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

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()

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
                    user_response = identity_store.describe_user(
                        IdentityStoreId=identity_store_id, UserId=user_id
                    )
                    user = user_response.get("User", {})
                    username = user.get("UserName", "N/A")
                    display_name = user.get("DisplayName", "N/A")
                except ClientError:
                    username = "N/A"
                    display_name = "N/A"

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
                            group_identifier, limit, next_token_result, profile
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
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """List all members of a group.

    Displays a table of users who are members of the specified group.
    Results can be paginated. Press ENTER to see the next page of results.

    Examples:
        # List members of a group by name
        $ awsideman group list-members Administrators

        # List members with a limit
        $ awsideman group list-members Developers --limit 50

        # List members using a specific AWS profile
        $ awsideman group list-members Engineers --profile dev-account
    """
    memberships, next_token_result = _list_members_internal(
        group_identifier, limit, next_token, profile
    )
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

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the identity store client
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
                    return None

        except ClientError as e:
            handle_aws_error(e, operation="ListGroupMemberships")
            raise typer.Exit(1)

        # Add the user to the group
        try:
            response = identity_store.create_group_membership(
                IdentityStoreId=identity_store_id, GroupId=group_id, MemberId={"UserId": user_id}
            )

            membership_id = response.get("MembershipId")
            console.print(
                f"[green]Successfully added user '{username}' to group '{group_name}'.[/green]"
            )

            return membership_id

        except ClientError as e:
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

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the identity store client
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
