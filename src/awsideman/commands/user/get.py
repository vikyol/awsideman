"""Get user command for awsideman."""

import re
from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.panel import Panel
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from .helpers import console, validate_profile, validate_sso_instance


def _get_user_group_memberships(identity_store, identity_store_id: str, user_id: str):
    """
    Get all groups that a user is a member of.

    Args:
        identity_store: AWS Identity Store client
        identity_store_id: Identity store ID
        user_id: User ID to find groups for

    Returns:
        List of group dictionaries with GroupId, DisplayName, Description, and MembershipId
    """
    groups = []

    try:
        # List all groups and check if the user is a member of each
        paginator = identity_store.get_paginator("list_groups")
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            for group in page.get("Groups", []):
                group_id = group["GroupId"]

                # Check if user is a member of this group
                try:
                    memberships_response = identity_store.list_group_memberships(
                        IdentityStoreId=identity_store_id, GroupId=group_id
                    )

                    for membership in memberships_response.get("GroupMemberships", []):
                        member_id = membership.get("MemberId", {})
                        if member_id.get("UserId") == user_id:
                            groups.append(
                                {
                                    "GroupId": group_id,
                                    "DisplayName": group.get("DisplayName", ""),
                                    "Description": group.get("Description", ""),
                                    "MembershipId": membership.get("MembershipId", ""),
                                }
                            )
                            break
                except ClientError:
                    # Skip groups we can't access
                    continue
    except ClientError:
        # If we can't list groups, return empty list
        pass

    return groups


def get_user(
    identifier: str = typer.Argument(..., help="Username, email, or user ID to search for"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Get detailed information about a specific user.

    Retrieves and displays comprehensive information about a user by their username, email, or user ID.
    Shows all available user attributes including contact information, status, and timestamps.
    """
    try:
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()

        # Check if identifier is a UUID (user ID) or if we need to search
        uuid_pattern = (
            r"^(?:[0-9a-f]{10}-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )

        if re.match(uuid_pattern, identifier):
            # Direct lookup by user ID
            user_id = identifier
        else:
            # Search for user by username or email
            console.print(f"[blue]Searching for user: {identifier}[/blue]")

            # Try searching by username first
            try:
                search_response = identity_store.list_users(
                    IdentityStoreId=identity_store_id,
                    Filters=[{"AttributePath": "UserName", "AttributeValue": identifier}],
                )

                users = search_response.get("Users", [])

                # If no users found by username, we need to list all users and filter by email manually
                # since the AWS API doesn't support filtering by email directly
                if not users:
                    # Get all users (with pagination if needed)
                    all_users = []
                    next_token = None

                    while True:
                        list_params = {"IdentityStoreId": identity_store_id}
                        if next_token:
                            list_params["NextToken"] = next_token

                        list_response = identity_store.list_users(**list_params)
                        batch_users = list_response.get("Users", [])
                        all_users.extend(batch_users)

                        next_token = list_response.get("NextToken")
                        if not next_token:
                            break

                    # Filter users by email manually
                    users = []
                    for user in all_users:
                        emails = user.get("Emails", [])
                        for email in emails:
                            if email.get("Value", "").lower() == identifier.lower():
                                users.append(user)
                                break

                # Handle search results
                if not users:
                    console.print(
                        f"[red]Error: No user found with username or email '{identifier}'.[/red]"
                    )
                    raise typer.Exit(1)
                elif len(users) > 1:
                    console.print(
                        f"[yellow]Warning: Multiple users found matching '{identifier}'. Showing the first match.[/yellow]"
                    )

                # Use the first user found
                user_id = users[0].get("UserId")
                console.print(
                    f"[green]Found user: {users[0].get('UserName', 'N/A')} (ID: {user_id})[/green]"
                )

            except ClientError as search_error:
                console.print(f"[red]Error searching for user: {search_error}[/red]")
                raise typer.Exit(1)

        # Make the API call to describe the user
        response = identity_store.describe_user(IdentityStoreId=identity_store_id, UserId=user_id)

        # Format and display the user details
        user = response

        # Create a table for displaying user details
        table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        table.add_column("Field", style="cyan", width=20)
        table.add_column("Value", style="white")

        # Add basic user information
        table.add_row("User ID", user.get("UserId", ""))
        table.add_row("Username", user.get("UserName", ""))

        # Add name information
        name_info = user.get("Name", {})
        if name_info.get("GivenName"):
            table.add_row("Given Name", name_info.get("GivenName", ""))
        if name_info.get("FamilyName"):
            table.add_row("Family Name", name_info.get("FamilyName", ""))
        if user.get("DisplayName"):
            table.add_row("Display Name", user.get("DisplayName", ""))

        # Add email information
        emails = user.get("Emails", [])
        if emails:
            for i, email in enumerate(emails):
                email_label = "Email"
                if len(emails) > 1:
                    email_label = f"Email {i+1}"
                if email.get("Primary", False):
                    email_label += " (Primary)"
                table.add_row(email_label, email.get("Value", ""))

        # Add phone numbers if available
        phone_numbers = user.get("PhoneNumbers", [])
        if phone_numbers:
            for i, phone in enumerate(phone_numbers):
                phone_label = "Phone"
                if len(phone_numbers) > 1:
                    phone_label = f"Phone {i+1}"
                if phone.get("Primary", False):
                    phone_label += " (Primary)"
                table.add_row(phone_label, phone.get("Value", ""))

        # Add addresses if available
        addresses = user.get("Addresses", [])
        if addresses:
            for i, address in enumerate(addresses):
                address_label = "Address"
                if len(addresses) > 1:
                    address_label = f"Address {i+1}"
                if address.get("Primary", False):
                    address_label += " (Primary)"

                # Format address components
                address_parts = []
                if address.get("StreetAddress"):
                    address_parts.append(address.get("StreetAddress"))
                if address.get("Locality"):
                    address_parts.append(address.get("Locality"))
                if address.get("Region"):
                    address_parts.append(address.get("Region"))
                if address.get("PostalCode"):
                    address_parts.append(address.get("PostalCode"))
                if address.get("Country"):
                    address_parts.append(address.get("Country"))

                formatted_address = ", ".join(address_parts)
                table.add_row(address_label, formatted_address)

        # Add status information
        if user.get("Status"):
            status = user.get("Status", "")
            status_style = "green" if status == "ENABLED" else "yellow"
            table.add_row("Status", f"[{status_style}]{status}[/{status_style}]")

        # Add creation and modification timestamps if available
        if user.get("CreatedDate"):
            from datetime import datetime

            created_date = user.get("CreatedDate")
            if isinstance(created_date, datetime):
                table.add_row("Created", created_date.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                table.add_row("Created", str(created_date))

        if user.get("LastModifiedDate"):
            from datetime import datetime

            modified_date = user.get("LastModifiedDate")
            if isinstance(modified_date, datetime):
                table.add_row("Last Modified", modified_date.strftime("%Y-%m-%d %H:%M:%S"))
            else:
                table.add_row("Last Modified", str(modified_date))

        # Add external IDs if available
        external_ids = user.get("ExternalIds", [])
        if external_ids:
            for i, ext_id in enumerate(external_ids):
                ext_id_label = "External ID"
                if len(external_ids) > 1:
                    ext_id_label = f"External ID {i+1}"
                if ext_id.get("Issuer"):
                    ext_id_label += f" ({ext_id.get('Issuer')})"
                table.add_row(ext_id_label, ext_id.get("Id", ""))

        # Add user type if available
        if user.get("UserType"):
            table.add_row("User Type", user.get("UserType", ""))

        # Add any custom attributes if available
        custom_attributes = user.get("CustomAttributes", {})
        if custom_attributes:
            for key, value in custom_attributes.items():
                table.add_row(f"Custom: {key}", str(value))

        # Create a title for the panel
        display_name = user.get("DisplayName", "")
        username = user.get("UserName", "")
        user_id_short = user.get("UserId", "")[:8] + "..." if user.get("UserId") else ""

        if display_name:
            title = f"{display_name} ({username})"
        else:
            title = username or user_id_short

        # Create a panel with the table
        panel = Panel(
            table,
            title=f"[bold green]User Details: {title}[/bold green]",
            border_style="blue",
            expand=False,
        )

        # Display the panel
        console.print(panel)

        # Add group memberships information
        console.print("\n[bold blue]Group Memberships:[/bold blue]")

        try:
            # Get all groups that the user is a member of
            user_groups = _get_user_group_memberships(identity_store, identity_store_id, user_id)

            if not user_groups:
                console.print("[yellow]User is not a member of any groups.[/yellow]")
            else:
                # Create a table for displaying group memberships
                groups_table = Table(title=f"Groups for {username or user_id_short}")
                groups_table.add_column("Group ID", style="cyan")
                groups_table.add_column("Group Name", style="green")
                groups_table.add_column("Description", style="yellow")
                groups_table.add_column("Membership ID", style="blue")

                # Add rows to the table
                for group in user_groups:
                    groups_table.add_row(
                        group.get("GroupId", ""),
                        group.get("DisplayName", "N/A"),
                        group.get("Description", "N/A"),
                        group.get("MembershipId", ""),
                    )

                # Display the groups table
                console.print(groups_table)
                console.print(f"[green]User is a member of {len(user_groups)} group(s).[/green]")

        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not retrieve group memberships: {str(e)}[/yellow]"
            )

        # Return the user data for further processing if needed
        return user

    except ClientError as e:
        # Handle AWS API errors
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))

        # Handle specific error cases
        if error_code == "ResourceNotFoundException":
            console.print(f"[red]Error: User '{identifier}' not found.[/red]")
            console.print("Please check the user ID and try again.")
        else:
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
