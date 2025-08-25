"""Create user command for awsideman."""

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
from .helpers import (
    console,
    format_user_for_display,
    validate_email_format,
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
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
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

        # Display a message indicating that we're creating the user
        console.print(f"[blue]Creating user '{username}'...[/blue]")

        # Prepare the create_user API call parameters
        create_user_params = {
            "IdentityStoreId": identity_store_id,
            "UserName": username,
            "DisplayName": display_name,
            "Emails": [{"Value": email, "Primary": True, "Type": "work"}],
        }

        # Add name attributes - AWS Identity Center requires a Name attribute
        name_attributes = {}
        if first_name:
            name_attributes["GivenName"] = first_name
        else:
            # Use display_name as GivenName if no first_name provided
            name_attributes["GivenName"] = display_name

        if last_name:
            name_attributes["FamilyName"] = last_name
        else:
            # Use a default last name if none provided
            name_attributes["FamilyName"] = "User"

        create_user_params["Name"] = name_attributes

        try:
            # Make the API call to create the user
            response = identity_store.create_user(**create_user_params)

            # Extract the user ID from the response
            user_id = response.get("UserId")
            if not user_id:
                console.print("[red]Error: Failed to create user. No user ID returned.[/red]")
                raise typer.Exit(1)

            # Cache invalidation is handled automatically by CachedIdentityStoreClient

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

                # Debug: Check if table has rows
                if len(details_table.rows) == 0:
                    # If no rows, add some basic information
                    details_table.add_row("User ID", user_id)
                    details_table.add_row("Username", username)
                    if display_name:
                        details_table.add_row("Display Name", display_name)
                    if email:
                        details_table.add_row("Email", email)

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

    except Exception as e:
        # Handle all errors using common error handler
        handle_aws_error(e, "creating user", verbose=verbose)
        raise typer.Exit(1)
