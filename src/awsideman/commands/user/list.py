"""List users command for awsideman."""

import os
from typing import Optional

import typer
from rich.table import Table

from ..common import (
    extract_standard_params,
    handle_aws_error,
    profile_option,
    region_option,
    show_cache_info,
    validate_profile_with_cache,
)
from .helpers import console, get_single_key, validate_sso_instance


def list_users(
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter users by attribute in format 'attribute=value' (e.g., UserName=john)",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of users to return in a single page"
    ),
    next_token: Optional[str] = typer.Option(
        None, "--next-token", "-n", help="Pagination token (for internal use)"
    ),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """List all users in the Identity Store.

    Displays a table of users with their IDs, usernames, emails, and names.
    Results can be filtered and paginated. Press ENTER to see the next page of results.

    Note: For detailed user information including status, use 'awsideman user get <username>'.
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

        # Check if AWS_DEFAULT_REGION environment variable is set
        if os.environ.get("AWS_DEFAULT_REGION") and verbose:
            console.print(
                f"[yellow]Warning: AWS_DEFAULT_REGION environment variable is set to '{os.environ.get('AWS_DEFAULT_REGION')}'. This may override the region in your profile.[/yellow]"
            )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()

        # Prepare the list_users API call parameters
        list_users_params = {"IdentityStoreId": identity_store_id}

        # Add optional parameters if provided
        if filter:
            # Check if filter is in the format "attribute=value"
            if "=" not in filter:
                raise ValueError("Filter must be in the format 'attribute=value'")

            attribute_path, attribute_value = filter.split("=", 1)
            list_users_params["Filters"] = [
                {"AttributePath": attribute_path, "AttributeValue": attribute_value}
            ]

        if limit:
            list_users_params["MaxResults"] = limit

        if next_token:
            list_users_params["NextToken"] = next_token

        # Make the API call to list users
        response = identity_store.list_users(**list_users_params)

        # Extract users and next token from the response
        users = response.get("Users", [])
        next_token = response.get("NextToken")

        # Display the results using a Rich table
        if not users:
            console.print("[yellow]No users found.[/yellow]")
            return [], next_token

        # Display pagination status
        page_info = ""
        if next_token:
            page_info = " (more results available)"
        if limit:
            page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"

        console.print(f"[green]Found {len(users)} users{page_info}.[/green]")

        # Create a table for displaying users
        table = Table(title=f"Users in Identity Store {identity_store_id}")

        # Add columns to the table
        table.add_column("User ID", style="cyan")
        table.add_column("Username", style="green")
        table.add_column("Email", style="blue")
        table.add_column("Name", style="magenta")

        # Add rows to the table
        for user in users:
            user_id = user.get("UserId", "")
            username = user.get("UserName", "")

            # Extract email from user attributes
            email = ""
            for attr in user.get("Emails", []):
                if attr.get("Primary", False):
                    email = attr.get("Value", "")
                    break

            # Extract name components
            given_name = user.get("Name", {}).get("GivenName", "")
            family_name = user.get("Name", {}).get("FamilyName", "")
            display_name = user.get("DisplayName", "")

            # Format the name for display
            if display_name:
                name = display_name
            elif given_name or family_name:
                name = f"{given_name} {family_name}".strip()
            else:
                name = ""

            # Add the row to the table
            table.add_row(user_id, username, email, name)

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
                    # Call list_users recursively with the next token
                    return list_users(
                        filter=filter,
                        limit=limit,
                        next_token=next_token,
                        profile=profile,
                        region=region,
                        verbose=verbose,
                    )
                else:
                    console.print("\n[yellow]Pagination stopped.[/yellow]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Pagination stopped by user.[/yellow]")

        # Return the users and next token for further processing
        return users, next_token

    except ValueError as e:
        # Handle filter format errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("Filter format should be 'attribute=value'.")
        raise typer.Exit(1)
    except Exception as e:
        # Handle all other errors using common error handler
        handle_aws_error(e, "listing users", verbose=verbose)
        raise typer.Exit(1)
