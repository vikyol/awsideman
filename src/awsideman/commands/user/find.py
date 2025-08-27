"""Find users command for awsideman."""

import re
from typing import List, Optional

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
from .helpers import console, validate_sso_instance


def find_users(
    pattern: str = typer.Argument(
        ..., help="Regex pattern to search for in user names, emails, or usernames"
    ),
    case_sensitive: bool = typer.Option(
        False, "--case-sensitive", "-c", help="Make the search case sensitive"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of users to return"
    ),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> List[dict]:
    """Find users in the Identity Store based on a regex pattern.

    Searches through all users in the Identity Store and returns those whose names,
    emails, or usernames match the specified regex pattern. The search is performed
    locally after retrieving all users from AWS.

    Examples:
        # Find users with 'han' in their name (case insensitive)
        $ awsideman user find 'han'

        # Find users with 'john' in their username (case sensitive)
        $ awsideman user find 'john' --case-sensitive

        # Find users with email addresses ending in '@company.com'
        $ awsideman user find '@company\\.com$'

        # Find users with names starting with 'A' and ending with 'n'
        $ awsideman user find '^A.*n$'

        # Limit results to 10 users
        $ awsideman user find 'admin' --limit 10

        # Use a specific AWS profile
        $ awsideman user find 'test' --profile dev-account
    """
    try:
        # Validate the regex pattern
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled_pattern = re.compile(pattern, flags)
        except re.error as e:
            console.print(f"[red]Error: Invalid regex pattern '{pattern}': {str(e)}[/red]")
            console.print("[yellow]Please provide a valid regular expression pattern.[/yellow]")
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

        # Display search information
        case_info = "case sensitive" if case_sensitive else "case insensitive"
        console.print(
            f"[blue]Searching for users matching pattern '{pattern}' ({case_info})...[/blue]"
        )

        # Get all users from the Identity Store
        all_users = []
        next_token = None

        while True:
            list_params = {"IdentityStoreId": identity_store_id}
            if next_token:
                list_params["NextToken"] = next_token

            response = identity_store.list_users(**list_params)
            batch_users = response.get("Users", [])
            all_users.extend(batch_users)

            next_token = response.get("NextToken")
            if not next_token:
                break

        if verbose:
            console.print(
                f"[blue]Retrieved {len(all_users)} total users from Identity Store[/blue]"
            )

        # Filter users based on the regex pattern
        matching_users = []
        for user in all_users:
            # Check username
            username = user.get("UserName", "")
            if compiled_pattern.search(username):
                matching_users.append(user)
                continue

            # Check display name
            display_name = user.get("DisplayName", "")
            if compiled_pattern.search(display_name):
                matching_users.append(user)
                continue

            # Check email addresses
            emails = user.get("Emails", [])
            for email in emails:
                email_value = email.get("Value", "")
                if compiled_pattern.search(email_value):
                    matching_users.append(user)
                    break

            # Check name components
            name = user.get("Name", {})
            given_name = name.get("GivenName", "")
            family_name = name.get("FamilyName", "")

            if compiled_pattern.search(given_name) or compiled_pattern.search(family_name):
                matching_users.append(user)
                continue

            # Check full name combination
            full_name = f"{given_name} {family_name}".strip()
            if full_name and compiled_pattern.search(full_name):
                matching_users.append(user)
                continue

        # Apply limit if specified
        if limit and len(matching_users) > limit:
            matching_users = matching_users[:limit]
            limit_info = f" (limited to {limit})"
        else:
            limit_info = ""

        # Display results
        if not matching_users:
            console.print(f"[yellow]No users found matching pattern '{pattern}'.[/yellow]")
            return []

        # Display search results summary
        console.print(
            f"[green]Found {len(matching_users)} users matching pattern '{pattern}'{limit_info}.[/green]"
        )

        # Create a table for displaying matching users
        table = Table(title=f"Users matching '{pattern}' in Identity Store {identity_store_id}")

        # Add columns to the table
        table.add_column("User ID", style="cyan")
        table.add_column("Username", style="green")
        table.add_column("Email", style="blue")
        table.add_column("Display Name", style="magenta")
        table.add_column("Full Name", style="yellow")

        # Add rows to the table
        for user in matching_users:
            user_id = user.get("UserId", "")
            username = user.get("UserName", "")

            # Extract email from user attributes
            email = ""
            for attr in user.get("Emails", []):
                if attr.get("Primary", False):
                    email = attr.get("Value", "")
                    break

            # Extract name components
            name = user.get("Name", {})
            given_name = name.get("GivenName", "")
            family_name = name.get("FamilyName", "")
            display_name = user.get("DisplayName", "")

            # Format the full name for display
            if given_name or family_name:
                full_name = f"{given_name} {family_name}".strip()
            else:
                full_name = ""

            # Add the row to the table
            table.add_row(user_id, username, email, display_name, full_name)

        # Display the table
        console.print(table)

        # Return the matching users for further processing
        return matching_users

    except Exception as e:
        # Handle all errors using common error handler
        handle_aws_error(e, "finding users", verbose=verbose)
        raise typer.Exit(1)
