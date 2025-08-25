"""Delete user command for awsideman."""

import re
from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.panel import Panel
from rich.table import Table

from ..common import (
    extract_standard_params,
    handle_aws_error,
    profile_option,
    region_option,
    show_cache_info,
    validate_profile_with_cache,
)
from .helpers import console, format_user_for_display, validate_sso_instance


def delete_user(
    identifier: str = typer.Argument(..., help="Username, email, or user ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force deletion without confirmation"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """Delete a user from AWS Identity Center.

    Permanently removes a user from the Identity Store.
    Requires confirmation before deletion to prevent accidental removal.

    Warning: This action cannot be undone. If the user is assigned to groups or has
    permission set assignments, those will need to be removed separately.

    Examples:
        # Delete a user by username with confirmation
        $ awsideman user delete john.doe

        # Delete a user by email
        $ awsideman user delete john.doe@example.com

        # Delete a user by user ID
        $ awsideman user delete 12345678-1234-1234-1234-123456789012

        # Force delete without confirmation
        $ awsideman user delete test.user --force

        # Delete using a specific AWS profile
        $ awsideman user delete admin --profile dev-account
    """
    try:
        # Extract and process standard command parameters
        profile, region, enable_caching = extract_standard_params(profile, region)

        # Show cache information if verbose
        show_cache_info(verbose)

        # Validate profile and get AWS client with cache integration
        profile_name, profile_data, aws_client = validate_profile_with_cache(
            profile=profile, enable_caching=enable_caching, region=region
        )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()

        # Find the user by identifier
        user_id = None
        current_user = None

        # Check if identifier is a UUID (user ID) or if we need to search
        uuid_pattern = (
            r"^(?:[0-9a-f]{10}-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )

        if re.match(uuid_pattern, identifier):
            # Direct lookup by user ID
            user_id = identifier
            try:
                user_response = identity_store.describe_user(
                    IdentityStoreId=identity_store_id,
                    UserId=user_id,
                )
                current_user = user_response.get("User", {})
            except ClientError:
                console.print(f"[red]Error: User with ID '{identifier}' not found.[/red]")
                raise typer.Exit(1)
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

                # If no users found by username, search by email
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
                    for user in all_users:
                        emails = user.get("Emails", [])
                        for email_obj in emails:
                            if email_obj.get("Value", "").lower() == identifier.lower():
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
                        f"[yellow]Warning: Multiple users found matching '{identifier}'. Deleting the first match.[/yellow]"
                    )

                current_user = users[0]
                user_id = current_user.get("UserId")

            except ClientError as e:
                console.print(
                    f"[red]Error searching for user: {e.response.get('Error', {}).get('Message', str(e))}[/red]"
                )
                raise typer.Exit(1)

        if not user_id or not current_user:
            console.print(f"[red]Error: Could not find user '{identifier}'.[/red]")
            raise typer.Exit(1)

        # Get the user details for confirmation
        username = current_user.get("UserName", "Unknown")
        display_name = current_user.get("DisplayName", "Unknown")
        email = (
            current_user.get("Emails", [{}])[0].get("Value", "N/A")
            if current_user.get("Emails")
            else "N/A"
        )

        # Format the user data for display (stored for potential future use)
        _ = format_user_for_display(current_user)

        # Create a table for the user details
        details_table = Table(show_header=False, box=None)
        details_table.add_column("Attribute", style="cyan")
        details_table.add_column("Value")

        # Add rows for each attribute
        for key, value in current_user.items():
            if isinstance(value, list):
                # Handle list attributes like emails
                if key == "Emails" and value:
                    email_values = [email_obj.get("Value", "N/A") for email_obj in value]
                    details_table.add_row(key, ", ".join(email_values))
                else:
                    details_table.add_row(key, str(value))
            elif isinstance(value, dict) and key == "Name":
                # Handle Name field specially to format as "GivenName FamilyName"
                given_name = value.get("GivenName", "")
                family_name = value.get("FamilyName", "")
                formatted_name = f"{given_name} {family_name}".strip()
                details_table.add_row(key, formatted_name if formatted_name else "N/A")
            else:
                details_table.add_row(key, str(value))

        # Create a panel for the user details
        panel = Panel(
            details_table,
            title=f"User to Delete: {username}",
            expand=False,
        )

        # Display the panel
        console.print(panel)

        # Display warning about deletion
        console.print(
            "[yellow]Warning: This action cannot be undone. The user will be permanently deleted.[/yellow]"
        )
        console.print(
            "[yellow]If this user is assigned to groups or has permission set assignments, those will need to be removed separately.[/yellow]"
        )

        # Ask for confirmation before deletion (unless force flag is used)
        if not force:
            confirmation = typer.confirm("Are you sure you want to delete this user?")
            if not confirmation:
                console.print("[yellow]Deletion cancelled.[/yellow]")
                return

        # Display a message indicating that we're deleting the user
        console.print(f"[blue]Deleting user '{username}'...[/blue]")

        try:
            # Make the API call to delete the user
            identity_store.delete_user(
                IdentityStoreId=identity_store_id,
                UserId=user_id,
            )

            # Invalidate user-related cache entries to ensure consistency
            # Cache invalidation is handled automatically by CachedIdentityStoreClient

            # Display success message with checkmark emoji
            console.print(f"[green]✓ User '{username}' deleted successfully.[/green]")
            console.print(f"[green]User ID: {user_id}[/green]")

            return {
                "UserId": user_id,
                "UserName": username,
                "DisplayName": display_name,
                "Email": email,
                "Status": "Deleted",
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: User '{identifier}' not found.[/red]")
                console.print("[yellow]The user may have been deleted already.[/yellow]")
            elif error_code == "ConflictException":
                console.print(f"[red]Error: Cannot delete user '{username}'.[/red]")
                console.print(
                    "[yellow]The user may be in use by groups or permission set assignments.[/yellow]"
                )
                console.print(
                    "[yellow]Remove all assignments for this user before deletion.[/yellow]"
                )
            else:
                console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                console.print(
                    "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                )

            raise typer.Exit(1)

    except Exception as e:
        # Handle all errors using common error handler
        handle_aws_error(e, "deleting user", verbose=verbose)
        raise typer.Exit(1)
    return None
