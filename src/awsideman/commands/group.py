"""Group management commands for awsideman."""

import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from rich.console import Console
from rich.table import Table

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config
from ..utils.error_handler import handle_aws_error, handle_network_error, with_retry
from ..utils.validators import (
    validate_filter,
    validate_group_description,
    validate_group_name,
    validate_limit,
    validate_non_empty,
)

app = typer.Typer(
    help="Manage groups in AWS Identity Center. Create, list, update, and delete groups in the Identity Store."
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


def validate_profile(profile_name: Optional[str] = None) -> tuple[str, dict]:
    """
    Validate the profile and return profile name and data.

    This function checks if the specified profile exists or uses the default profile.
    It handles cases where no profile is specified and no default profile is set,
    or when the specified profile does not exist.

    Args:
        profile_name: AWS profile name to use

    Returns:
        Tuple of (profile_name, profile_data)

    Raises:
        typer.Exit: If profile validation fails with a clear error message
    """
    # Use the provided profile name or fall back to the default profile
    profile_name = profile_name or config.get("default_profile")

    # Check if a profile name is available
    if not profile_name:
        console.print("[red]Error: No profile specified and no default profile set.[/red]")
        console.print(
            "Use --profile option or set a default profile with 'awsideman profile set-default'."
        )
        raise typer.Exit(1)

    # Get all profiles and check if the specified profile exists
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        console.print(f"[red]Error: Profile '{profile_name}' does not exist.[/red]")
        console.print("Use 'awsideman profile add' to create a new profile.")
        raise typer.Exit(1)

    # Get the profile data
    profile_data = profiles[profile_name]

    # Check network connectivity if we have a region
    region = profile_data.get("region")
    if region:
        from ..utils.error_handler import check_network_connectivity

        check_network_connectivity(region)

    # Return the profile name and profile data
    return profile_name, profile_data


def validate_sso_instance(profile_data: dict) -> tuple[str, str]:
    """
    Validate the SSO instance configuration and return instance ARN and identity store ID.

    This function checks if the specified profile has an SSO instance configured.
    It handles cases where no SSO instance is configured for the profile and provides
    helpful guidance on how to configure an SSO instance.

    Args:
        profile_data: Profile data dictionary containing configuration

    Returns:
        Tuple of (instance_arn, identity_store_id)

    Raises:
        typer.Exit: If SSO instance validation fails with a clear error message and guidance
    """
    # Get the SSO instance ARN and identity store ID from the profile data
    instance_arn = profile_data.get("sso_instance_arn")
    identity_store_id = profile_data.get("identity_store_id")

    # Check if both the instance ARN and identity store ID are available
    if not instance_arn or not identity_store_id:
        console.print("[red]Error: No SSO instance configured for this profile.[/red]")
        console.print(
            "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
        )
        console.print("You can find available SSO instances with 'awsideman sso list'.")
        raise typer.Exit(1)

    # Return the instance ARN and identity store ID
    return instance_arn, identity_store_id


def _list_groups_internal(
    filter: Optional[str] = None,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Internal implementation of list_groups that can be called directly from tests.

    Args:
        filter: Filter groups by attribute in format 'attribute=value'
        limit: Maximum number of groups to return in a single page
        next_token: Pagination token
        profile: AWS profile to use

    Returns:
        Tuple of (groups, next_token)
    """
    try:
        # Validate inputs
        if filter and not validate_filter(filter):
            raise typer.Exit(1)

        if not validate_limit(limit):
            raise typer.Exit(1)
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Check if AWS_DEFAULT_REGION environment variable is set
        import os

        if os.environ.get("AWS_DEFAULT_REGION"):
            console.print(
                f"[yellow]Warning: AWS_DEFAULT_REGION environment variable is set to '{os.environ.get('AWS_DEFAULT_REGION')}'. This may override the region in your profile.[/yellow]"
            )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()

        # Prepare the list_groups API call parameters
        list_groups_params = {"IdentityStoreId": identity_store_id}

        # Add optional parameters if provided
        if filter:
            # Check if filter is in the format "attribute=value"
            if "=" not in filter:
                raise ValueError("Filter must be in the format 'attribute=value'")

            attribute_path, attribute_value = filter.split("=", 1)
            list_groups_params["Filters"] = [
                {"AttributePath": attribute_path, "AttributeValue": attribute_value}
            ]

        if limit:
            list_groups_params["MaxResults"] = limit

        if next_token:
            list_groups_params["NextToken"] = next_token

        # Make the API call to list groups
        response = identity_store.list_groups(**list_groups_params)

        # Extract groups and next token from the response
        groups = response.get("Groups", [])
        next_token = response.get("NextToken")

        # Display the results using a Rich table
        if not groups:
            console.print("[yellow]No groups found.[/yellow]")
            return [], next_token

        # Display pagination status
        page_info = ""
        if next_token:
            page_info = " (more results available)"
        if limit:
            page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"

        console.print(f"[green]Found {len(groups)} groups{page_info}.[/green]")

        # Create a table for displaying groups
        table = Table(title=f"Groups in Identity Store {identity_store_id}")

        # Add columns to the table
        table.add_column("Group ID", style="cyan")
        table.add_column("Display Name", style="green")
        table.add_column("Description", style="blue")

        # Add rows to the table
        for group in groups:
            group_id = group.get("GroupId", "")
            display_name = group.get("DisplayName", "")
            description = group.get("Description", "")

            # Add the row to the table
            table.add_row(group_id, display_name, description)

        # Display the table
        console.print(table)

        # Handle pagination - interactive by default
        if next_token:
            console.print(
                "\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]"
            )
            try:
                # Wait for single key press
                key = get_single_key()

                # If the user pressed Enter (or Return), fetch the next page
                if key in ["\r", "\n", ""]:
                    console.print("\n[blue]Fetching next page...[/blue]\n")
                    # Call _list_groups_internal recursively with the next token
                    return _list_groups_internal(
                        filter=filter, limit=limit, next_token=next_token, profile=profile
                    )
                else:
                    console.print("\n[yellow]Pagination stopped.[/yellow]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Pagination stopped by user.[/yellow]")

        # Return the groups and next token for further processing
        return groups, next_token

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="ListGroups")
    except ValueError as e:
        # Handle filter format errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("[yellow]Filter format should be 'attribute=value'.[/yellow]")
        console.print("[yellow]Example: --filter DisplayName=Administrators[/yellow]")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)


@app.command("list")
def list_groups(
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter groups by attribute in format 'attribute=value' (e.g., DisplayName=engineering)",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of groups to return in a single page"
    ),
    next_token: Optional[str] = typer.Option(
        None, "--next-token", "-n", help="Pagination token (for internal use)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """List all groups in the Identity Store.

    Displays a table of groups with their IDs, names, and descriptions.
    Results can be filtered and paginated. Press ENTER to see the next page of results.
    """
    return _list_groups_internal(filter, limit, next_token, profile)


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

        if not validate_limit(limit):
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
                    console.print(
                        "[yellow]Consider using the group ID instead of the name for more precise targeting.[/yellow]"
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

        # Verify the group exists before attempting to list members
        try:
            # Make the API call to describe the group
            group_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            # Get the display name for the output
            display_name = group_details.get("DisplayName", "Unknown")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            # Handle group not found error
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: Group with ID '{group_id}' not found.[/red]")
                console.print("[yellow]Please check the group ID or name and try again.[/yellow]")
                console.print(
                    "[yellow]You can list available groups with 'awsideman group list'.[/yellow]"
                )
                raise typer.Exit(1)
            else:
                # Handle other errors with improved messages
                handle_aws_error(e, operation="DescribeGroup")
                raise typer.Exit(1)

        # Prepare the list_group_memberships API call parameters
        list_members_params = {"IdentityStoreId": identity_store_id, "GroupId": group_id}

        # Add optional parameters if provided
        if limit:
            list_members_params["MaxResults"] = limit

        if next_token:
            list_members_params["NextToken"] = next_token

        # Make the API call to list group memberships
        try:
            # Apply retry decorator for transient errors
            @with_retry(max_retries=3, delay=1.0, backoff=2.0)
            def list_memberships_with_retry():
                return identity_store.list_group_memberships(**list_members_params)

            response = list_memberships_with_retry()

            # Extract memberships and next token from the response
            memberships = response.get("GroupMemberships", [])
            next_token = response.get("NextToken")

            # If no memberships found, return early
            if not memberships:
                console.print(f"[yellow]No members found for group '{display_name}'.[/yellow]")
                return [], next_token

            # Display pagination status
            page_info = ""
            if next_token:
                page_info = " (more results available)"
            if limit:
                page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"

            console.print(
                f"[green]Found {len(memberships)} members in group '{display_name}'{page_info}.[/green]"
            )

            # Create a table for displaying members
            table = Table(title=f"Members of Group '{display_name}' (ID: {group_id})")

            # Add columns to the table
            table.add_column("Username", style="green")
            table.add_column("Full Name", style="cyan")
            table.add_column("Email", style="blue")
            table.add_column("User ID", style="dim")

            # Collect all user IDs to fetch user details
            user_ids = [
                membership.get("MemberId", {}).get("UserId", "") for membership in memberships
            ]
            user_details = {}

            # Fetch user details for each user ID
            for user_id in user_ids:
                if not user_id:
                    continue

                try:
                    # Get user details
                    user_response = identity_store.describe_user(
                        IdentityStoreId=identity_store_id, UserId=user_id
                    )

                    # Store user details for later use
                    user_details[user_id] = user_response
                except ClientError as e:
                    # If we can't get user details, just continue with what we have
                    console.print(
                        f"[yellow]Warning: Could not retrieve details for user {user_id}: {e.response.get('Error', {}).get('Message', str(e))}[/yellow]"
                    )

            # Add rows to the table
            for membership in memberships:
                user_id = membership.get("MemberId", {}).get("UserId", "")

                # Get user details if available
                user = user_details.get(user_id, {})

                # Extract user information
                username = user.get("UserName", "N/A")

                # Extract name components
                given_name = user.get("Name", {}).get("GivenName", "")
                family_name = user.get("Name", {}).get("FamilyName", "")
                display_name = user.get("DisplayName", "")

                # Format the name for display
                if display_name:
                    full_name = display_name
                elif given_name or family_name:
                    full_name = f"{given_name} {family_name}".strip()
                else:
                    full_name = "N/A"

                # Extract email from user attributes
                email = "N/A"
                for email_obj in user.get("Emails", []):
                    if email_obj.get("Primary", False):
                        email = email_obj.get("Value", "N/A")
                        break

                # Add the row to the table
                table.add_row(username, full_name, email, user_id)

            # Display the table
            console.print(table)

            # Handle pagination - interactive by default
            if next_token:
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
                            group_identifier=group_identifier,
                            limit=limit,
                            next_token=next_token,
                            profile=profile,
                        )
                    else:
                        console.print("\n[yellow]Pagination stopped.[/yellow]")
                except KeyboardInterrupt:
                    console.print("\n[yellow]Pagination stopped by user.[/yellow]")

            # Return the memberships and next token for further processing
            return memberships, next_token

        except ClientError as e:
            # Handle AWS API errors with improved error messages and guidance
            handle_aws_error(e, operation="ListGroupMemberships")

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="ListGroupMemberships")
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)

    # Return empty list and None if we get here (should not happen)
    return [], None


@app.command("list-members")
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
    """
    memberships, next_token_result = _list_members_internal(
        group_identifier, limit, next_token, profile
    )
    # Return the expected tuple format for tests
    return memberships, next_token_result, group_identifier


@app.command("add-member")
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


@app.command("remove-member")
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


@app.command("delete")
def delete_group(
    identifier: str = typer.Argument(..., help="Group name or ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Delete a group from the Identity Store.

    Permanently removes a group from the Identity Store.
    Requires confirmation unless the --force flag is used.
    """
    try:
        # Validate inputs
        if not validate_non_empty(identifier, "Group identifier"):
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

        # Check if identifier is a UUID (group ID) or if we need to search
        uuid_pattern = (
            r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{10,})"
        )
        if re.match(uuid_pattern, identifier, re.IGNORECASE):
            # Direct lookup by group ID
            group_id = identifier
        else:
            # Search for group by display name
            console.print(f"[blue]Searching for group: {identifier}[/blue]")

            # Search by display name
            try:
                search_response = identity_store.list_groups(
                    IdentityStoreId=identity_store_id,
                    Filters=[{"AttributePath": "DisplayName", "AttributeValue": identifier}],
                )

                groups = search_response.get("Groups", [])

                # Handle search results
                if not groups:
                    console.print(f"[red]Error: No group found with name '{identifier}'.[/red]")
                    console.print("[yellow]Please check the group name and try again.[/yellow]")
                    console.print(
                        "[yellow]You can list available groups with 'awsideman group list'.[/yellow]"
                    )
                    raise typer.Exit(1)
                elif len(groups) > 1:
                    console.print(
                        f"[yellow]Warning: Multiple groups found matching '{identifier}'. Deleting the first match.[/yellow]"
                    )
                    console.print(
                        "[yellow]Consider using the group ID instead of the name for more precise targeting.[/yellow]"
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

        # Verify the group exists before attempting to delete
        try:
            # Make the API call to describe the group
            group_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            # Get the display name for confirmation message
            display_name = group_details.get("DisplayName", "Unknown")

            # Log the operation
            console.print(
                f"[blue]Preparing to delete group '{display_name}' (ID: {group_id}) from Identity Store {identity_store_id}...[/blue]"
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            # Handle group not found error
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: Group with ID '{group_id}' not found.[/red]")
                console.print("[yellow]Please check the group ID or name and try again.[/yellow]")
                console.print(
                    "[yellow]You can list available groups with 'awsideman group list'.[/yellow]"
                )
                raise typer.Exit(1)
            else:
                # Handle other errors with improved messages
                handle_aws_error(e, operation="DescribeGroup")
                raise typer.Exit(1)

        # Check if force option is used, otherwise prompt for confirmation
        if not force:
            console.print(
                f"[yellow]Warning: This will permanently delete group '{display_name}' (ID: {group_id}).[/yellow]"
            )
            console.print("[yellow]This action cannot be undone.[/yellow]")
            console.print("\n[blue]Are you sure you want to continue? (y/N)[/blue]")

            try:
                # Wait for user input
                confirmation = get_single_key().lower()

                # Check if the user confirmed the deletion
                if confirmation != "y":
                    console.print("\n[yellow]Group deletion cancelled.[/yellow]")
                    raise typer.Exit(0)

                console.print()  # Add a newline for better formatting

            except KeyboardInterrupt:
                console.print("\n[yellow]Group deletion cancelled.[/yellow]")
                return

        # Make the API call to delete the group
        try:
            # Apply retry decorator for transient errors
            @with_retry(max_retries=3, delay=1.0, backoff=2.0)
            def delete_group_with_retry():
                return identity_store.delete_group(
                    IdentityStoreId=identity_store_id, GroupId=group_id
                )

            delete_group_with_retry()

            # Display success message
            console.print(f"[green]Group '{display_name}' deleted successfully.[/green]")

            return True

        except ClientError as delete_error:
            error_code = delete_error.response.get("Error", {}).get("Code", "Unknown")

            # Handle specific error cases
            if error_code == "ResourceNotFoundException":
                console.print(
                    f"[red]Error: Group with ID '{group_id}' not found or already deleted.[/red]"
                )
                console.print(
                    "[yellow]The group may have been deleted by another process or user.[/yellow]"
                )
            else:
                handle_aws_error(delete_error, operation="DeleteGroup")

            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="DeleteGroup")
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)


def create_group(
    name: str,
    description: Optional[str] = None,
    profile: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Create a new group in the Identity Store.

    Args:
        name: Display name for the group
        description: Optional description for the group
        profile: AWS profile to use

    Returns:
        Tuple of (group_id, group_attributes)

    Raises:
        typer.Exit: If group creation fails
    """
    try:
        # Validate inputs
        if not validate_non_empty(name, "Group name"):
            raise typer.Exit(1)

        if not validate_group_name(name):
            raise typer.Exit(1)

        if description and not validate_group_description(description):
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

        # Check if group already exists
        try:
            search_response = identity_store.list_groups(
                IdentityStoreId=identity_store_id,
                Filters=[{"AttributePath": "DisplayName", "AttributeValue": name}],
            )

            existing_groups = search_response.get("Groups", [])
            if existing_groups:
                console.print(f"[red]Error: A group with name '{name}' already exists.[/red]")
                raise typer.Exit(1)

        except ClientError as e:
            handle_aws_error(e, operation="ListGroups")
            raise typer.Exit(1)

        # Create the group
        create_params = {"IdentityStoreId": identity_store_id, "DisplayName": name}

        if description:
            create_params["Description"] = description

        try:
            response = identity_store.create_group(**create_params)
            group_id = response.get("GroupId")

            # Get the created group details
            group_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            console.print("[green]Group created successfully![/green]")

            return group_id, group_details

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
            raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="CreateGroup")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def get_group(
    identifier: str,
    profile: Optional[str] = None,
) -> dict:
    """
    Get detailed information about a group.

    Args:
        identifier: Group name or ID to retrieve
        profile: AWS profile to use

    Returns:
        Dictionary containing group details

    Raises:
        typer.Exit: If group retrieval fails
    """
    try:
        # Validate inputs
        if not validate_non_empty(identifier, "Group identifier"):
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

        # Check if identifier is a UUID (group ID) or if we need to search
        uuid_pattern = (
            r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{10,})"
        )
        if re.match(uuid_pattern, identifier, re.IGNORECASE):
            # Direct lookup by group ID
            group_id = identifier
        else:
            # Search for group by display name
            console.print(f"[blue]Searching for group: {identifier}[/blue]")

            try:
                search_response = identity_store.list_groups(
                    IdentityStoreId=identity_store_id,
                    Filters=[{"AttributePath": "DisplayName", "AttributeValue": identifier}],
                )

                groups = search_response.get("Groups", [])

                if not groups:
                    console.print(f"[red]Error: No group found with name '{identifier}'.[/red]")
                    raise typer.Exit(1)
                elif len(groups) > 1:
                    console.print(
                        f"[yellow]Warning: Multiple groups found matching '{identifier}'. Showing the first match.[/yellow]"
                    )

                group_id = groups[0].get("GroupId")
                console.print(f"[green]Found group: {identifier} (ID: {group_id})[/green]")

            except ClientError as e:
                handle_aws_error(e, operation="ListGroups")
                raise typer.Exit(1)

        # Get group details
        try:
            group_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            return group_details

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: Group '{group_id}' not found.[/red]")
            else:
                handle_aws_error(e, operation="DescribeGroup")
            raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="DescribeGroup")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def update_group(
    identifier: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    profile: Optional[str] = None,
) -> dict:
    """
    Update a group's attributes.

    Args:
        identifier: Group name or ID to update
        name: New display name for the group
        description: New description for the group
        profile: AWS profile to use

    Returns:
        Dictionary containing updated group details

    Raises:
        typer.Exit: If group update fails
    """
    try:
        # Validate inputs
        if not validate_non_empty(identifier, "Group identifier"):
            raise typer.Exit(1)

        if not name and description is None:
            console.print("[red]Error: At least one of name or description must be provided.[/red]")
            raise typer.Exit(1)

        if name and not validate_group_name(name):
            raise typer.Exit(1)

        if description and not validate_group_description(description):
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

        # Get the group first to ensure it exists and get current details
        group_details = get_group(identifier, profile)
        group_id = group_details.get("GroupId")

        # Prepare update operations
        operations = []

        if name:
            operations.append({"AttributePath": "DisplayName", "AttributeValue": name})

        if description is not None:
            operations.append({"AttributePath": "Description", "AttributeValue": description})

        # Update the group
        try:
            identity_store.update_group(
                IdentityStoreId=identity_store_id,
                GroupId=group_id,
                Operations=[
                    {"AttributePath": op["AttributePath"], "AttributeValue": op["AttributeValue"]}
                    for op in operations
                ],
            )

            # Get updated group details
            updated_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            console.print("[green]Group updated successfully![/green]")

            return updated_details

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
            raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="UpdateGroup")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


def _find_user_id(identity_store_client, identity_store_id: str, user_identifier: str) -> str:
    """
    Find a user ID by username or email.

    Args:
        identity_store_client: Identity Store client
        identity_store_id: Identity Store ID
        user_identifier: User ID, username, or email

    Returns:
        User ID string

    Raises:
        ValueError: If user is not found or multiple users match
    """
    # Check if user_identifier is already a UUID (user ID)
    uuid_pattern = (
        r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{10,})"
    )
    if re.match(uuid_pattern, user_identifier, re.IGNORECASE):
        return user_identifier

    # Search by username first
    try:
        response = identity_store_client.list_users(
            IdentityStoreId=identity_store_id,
            Filters=[{"AttributePath": "UserName", "AttributeValue": user_identifier}],
        )

        users = response.get("Users", [])
        if len(users) == 1:
            return users[0].get("UserId")
        elif len(users) > 1:
            raise ValueError(f"Multiple users found with username '{user_identifier}'")

    except ClientError:
        pass  # Continue to email search

    # Search by email if username search didn't work
    try:
        response = identity_store_client.list_users(
            IdentityStoreId=identity_store_id,
            Filters=[{"AttributePath": "Emails.Value", "AttributeValue": user_identifier}],
        )

        users = response.get("Users", [])
        if len(users) == 1:
            return users[0].get("UserId")
        elif len(users) > 1:
            raise ValueError(f"Multiple users found with email '{user_identifier}'")

    except ClientError:
        pass  # Continue to raise not found error

    raise ValueError(f"User '{user_identifier}' not found")
