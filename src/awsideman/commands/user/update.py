"""Update user command for awsideman."""

import re
from typing import Optional

import typer
from botocore.exceptions import ClientError
from rich.panel import Panel
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from .helpers import (
    console,
    format_user_for_display,
    validate_email_format,
    validate_profile,
    validate_sso_instance,
    validate_username_format,
)


def update_user(
    identifier: str = typer.Argument(..., help="Username, email, or user ID to update"),
    username: Optional[str] = typer.Option(
        None, "--username", "-u", help="New username for the user"
    ),
    display_name: Optional[str] = typer.Option(
        None, "--display-name", "-n", help="New display name for the user"
    ),
    email: Optional[str] = typer.Option(
        None, "--email", "-e", help="New email address for the user"
    ),
    first_name: Optional[str] = typer.Option(
        None, "--first-name", "-f", help="New first name of the user"
    ),
    last_name: Optional[str] = typer.Option(
        None, "--last-name", "-l", help="New last name of the user"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Update an existing user in AWS Identity Center.

    Updates the specified user with new attribute values.
    Only the attributes you specify will be updated; others will remain unchanged.
    You can update username, display name, email, first name, and last name.

    Examples:
        # Update user display name
        $ awsideman user update john.doe --display-name "John Smith"

        # Update user email
        $ awsideman user update john.doe --email john.smith@example.com

        # Update multiple attributes
        $ awsideman user update john.doe --display-name "John Smith" --email john.smith@example.com --first-name John --last-name Smith

        # Update user using a specific AWS profile
        $ awsideman user update admin --username administrator --profile dev-account
    """
    try:
        # Check if any update parameters were provided
        if not any([username, display_name, email, first_name, last_name]):
            console.print(
                "[yellow]Warning: No update parameters provided. Nothing to update.[/yellow]"
            )
            console.print(
                "[yellow]Use --username, --display-name, --email, --first-name, or --last-name to specify updates.[/yellow]"
            )
            raise typer.Exit(1)

        # Validate inputs if provided
        if username is not None and not validate_username_format(username):
            console.print("[red]Error: Invalid username format.[/red]")
            console.print(
                "[yellow]Username must be 1-128 characters and contain only alphanumeric characters, underscores, and hyphens.[/yellow]"
            )
            raise typer.Exit(1)

        if email is not None and not validate_email_format(email):
            console.print("[red]Error: Invalid email format.[/red]")
            console.print("[yellow]Please provide a valid email address.[/yellow]")
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
                        f"[yellow]Warning: Multiple users found matching '{identifier}'. Updating the first match.[/yellow]"
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

        # Display a message indicating that we're updating the user
        current_username = current_user.get("UserName", "Unknown")
        console.print(f"[blue]Updating user '{current_username}'...[/blue]")

        # Prepare the update_user API call parameters
        update_user_params = {
            "IdentityStoreId": identity_store_id,
            "UserId": user_id,
        }

        # Add optional parameters if provided
        if username is not None:
            update_user_params["UserName"] = username

        if display_name is not None:
            update_user_params["DisplayName"] = display_name

        if email is not None:
            # Update email - replace existing emails
            update_user_params["Emails"] = [{"Value": email, "Primary": True, "Type": "work"}]

        # Handle name updates
        name_updates = {}
        current_name = current_user.get("Name", {})

        if first_name is not None:
            name_updates["GivenName"] = first_name
        elif "GivenName" in current_name:
            name_updates["GivenName"] = current_name["GivenName"]

        if last_name is not None:
            name_updates["FamilyName"] = last_name
        elif "FamilyName" in current_name:
            name_updates["FamilyName"] = current_name["FamilyName"]

        if name_updates:
            update_user_params["Name"] = name_updates

        try:
            # Make the API call to update the user
            identity_store.update_user(**update_user_params)

            # Cache invalidation is handled automatically by CachedIdentityStoreClient

            # Log the successful update
            console.print("[green]User updated successfully.[/green]")

            # Log which attributes were updated
            if username is not None:
                console.print(f"[green]Updated username: {username}[/green]")
            if display_name is not None:
                console.print(f"[green]Updated display name: {display_name}[/green]")
            if email is not None:
                console.print(f"[green]Updated email: {email}[/green]")
            if first_name is not None:
                console.print(f"[green]Updated first name: {first_name}[/green]")
            if last_name is not None:
                console.print(f"[green]Updated last name: {last_name}[/green]")

            # Get the updated user details to display
            try:
                updated_user_response = identity_store.describe_user(
                    IdentityStoreId=identity_store_id,
                    UserId=user_id,
                )
                updated_user = updated_user_response.get("User", {})

                # Format the user data for display (stored for potential future use)
                _ = format_user_for_display(updated_user)

                # Create a table for the user details
                details_table = Table(show_header=False, box=None)
                details_table.add_column("Attribute", style="cyan")
                details_table.add_column("Value")

                # Add rows for each attribute
                for key, value in updated_user.items():
                    if isinstance(value, list):
                        # Handle list attributes like emails
                        if key == "Emails" and value:
                            email_values = [email_obj.get("Value", "N/A") for email_obj in value]
                            details_table.add_row(key, ", ".join(email_values))
                        elif key == "Name" and value:
                            name_values = [f"{k}: {v}" for k, v in value.items()]
                            details_table.add_row(key, ", ".join(name_values))
                        else:
                            details_table.add_row(key, str(value))
                    else:
                        details_table.add_row(key, str(value))

                # Create a panel for the user details
                panel = Panel(
                    details_table,
                    title=f"Updated User: {updated_user.get('UserName', 'Unknown')}",
                    expand=False,
                )

                # Display the panel
                console.print(panel)

            except ClientError:
                # Just log a warning if we can't get the details, but don't fail the command
                console.print(
                    "[yellow]Warning: Could not retrieve full user details after update.[/yellow]"
                )

            return {
                "UserId": user_id,
                "UserName": updated_user.get("UserName", current_username),
                "DisplayName": updated_user.get("DisplayName", current_user.get("DisplayName")),
                "Email": (
                    email if email else current_user.get("Emails", [{}])[0].get("Value", "N/A")
                ),
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ConflictException":
                console.print(f"[red]Error: Username '{username}' is already taken.[/red]")
                console.print(
                    "[yellow]Use a different username or update a different attribute.[/yellow]"
                )
            elif error_code == "ValidationException":
                console.print(f"[red]Error: Validation failed - {error_message}[/red]")
                console.print("[yellow]Please check your input parameters and try again.[/yellow]")
            else:
                console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                console.print(
                    "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                )

            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        console.print(
            f"[red]AWS API Error: {e.response.get('Error', {}).get('Code', 'Unknown')} - {e.response.get('Error', {}).get('Message', str(e))}[/red]"
        )
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)
