"""Create user command for awsideman."""

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


def create_user(
    username: str = typer.Option(..., "--username", "-u", help="Username for the new user"),
    display_name: str = typer.Option(..., "--display-name", "-n", help="Display name for the user"),
    email: str = typer.Option(..., "--email", "-e", help="Email address for the user"),
    first_name: Optional[str] = typer.Option(
        None, "--first-name", "-f", help="First name of the user"
    ),
    last_name: Optional[str] = typer.Option(
        None, "--last-name", "-l", help="Last name of the user"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Create a new user in AWS Identity Center.

    Creates a new user in the Identity Store with the specified attributes.
    The user will be created with the given username, display name, and email address.
    Additional attributes like first name and last name can be specified if needed.

    Examples:
        # Create a basic user
        $ awsideman user create --username john.doe --display-name "John Doe" --email john.doe@example.com

        # Create a user with full name
        $ awsideman user create --username jane.smith --display-name "Jane Smith" --email jane.smith@example.com --first-name Jane --last-name Smith

        # Create a user using a specific AWS profile
        $ awsideman user create --username admin --display-name "Administrator" --email admin@company.com --profile dev-account
    """
    try:
        # Validate inputs
        if not validate_username_format(username):
            console.print("[red]Error: Invalid username format.[/red]")
            console.print(
                "[yellow]Username must be 1-128 characters and contain only alphanumeric characters, underscores, and hyphens.[/yellow]"
            )
            raise typer.Exit(1)

        if not validate_email_format(email):
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

        # Display a message indicating that we're creating the user
        console.print(f"[blue]Creating user '{username}'...[/blue]")

        # Prepare the create_user API call parameters
        create_user_params = {
            "IdentityStoreId": identity_store_id,
            "UserName": username,
            "DisplayName": display_name,
            "Emails": [{"Value": email, "Primary": True, "Type": "work"}],
        }

        # Add optional name attributes if provided
        if first_name or last_name:
            name_attributes = {}
            if first_name:
                name_attributes["GivenName"] = first_name
            if last_name:
                name_attributes["FamilyName"] = last_name

            if name_attributes:
                create_user_params["Name"] = name_attributes

        try:
            # Make the API call to create the user
            response = identity_store.create_user(**create_user_params)

            # Extract the user ID from the response
            user_id = response.get("UserId")
            if not user_id:
                console.print("[red]Error: Failed to create user. No user ID returned.[/red]")
                raise typer.Exit(1)

            console.print(f"[green]User '{username}' created successfully.[/green]")
            console.print(f"[green]User ID: {user_id}[/green]")

            # Get the full user details to display
            try:
                user_response = identity_store.describe_user(
                    IdentityStoreId=identity_store_id,
                    UserId=user_id,
                )
                user = user_response.get("User", {})

                # Format the user data for display (stored for potential future use)
                _ = format_user_for_display(user)

                # Create a table for the user details
                details_table = Table(show_header=False, box=None)
                details_table.add_column("Attribute", style="cyan")
                details_table.add_column("Value")

                # Add rows for each attribute
                for key, value in user.items():
                    if isinstance(value, list):
                        # Handle list attributes like emails
                        if key == "Emails" and value:
                            email_values = [email.get("Value", "N/A") for email in value]
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
                    title=f"Created User: {username}",
                    expand=False,
                )

                # Display the panel
                console.print(panel)

            except ClientError:
                # Just log a warning if we can't get the details, but don't fail the command
                console.print(
                    "[yellow]Warning: Could not retrieve full user details after creation.[/yellow]"
                )

            return {
                "UserId": user_id,
                "UserName": username,
                "DisplayName": display_name,
                "Email": email,
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ConflictException":
                console.print(f"[red]Error: User '{username}' already exists.[/red]")
                console.print(
                    "[yellow]Use a different username or use 'awsideman user update' to modify an existing user.[/yellow]"
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
