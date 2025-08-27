"""Find groups command for awsideman."""

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


def find_groups(
    pattern: str = typer.Argument(
        ..., help="Regex pattern to search for in group names, descriptions, or display names"
    ),
    case_sensitive: bool = typer.Option(
        False, "--case-sensitive", "-c", help="Make the search case sensitive"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of groups to return"
    ),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> List[dict]:
    """Find groups in the Identity Store based on a regex pattern.

    Searches through all groups in the Identity Store and returns those whose names,
    descriptions, or display names match the specified regex pattern. The search is performed
    locally after retrieving all groups from AWS.

    Examples:
        # Find groups with 'admin' in their name (case insensitive)
        $ awsideman group find 'admin'

        # Find groups with 'dev' in their name (case sensitive)
        $ awsideman group find 'dev' --case-sensitive

        # Find groups with descriptions containing 'temporary'
        $ awsideman group find 'temporary'

        # Find groups with names starting with 'A' and ending with 'n'
        $ awsideman group find '^A.*n$'

        # Limit results to 5 groups
        $ awsideman group find 'team' --limit 5

        # Use a specific AWS profile
        $ awsideman group find 'test' --profile dev-account
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
            f"[blue]Searching for groups matching pattern '{pattern}' ({case_info})...[/blue]"
        )

        # Get all groups from the Identity Store
        all_groups = []
        next_token = None

        while True:
            list_params = {"IdentityStoreId": identity_store_id}
            if next_token:
                list_params["NextToken"] = next_token

            response = identity_store.list_groups(**list_params)
            batch_groups = response.get("Groups", [])
            all_groups.extend(batch_groups)

            next_token = response.get("NextToken")
            if not next_token:
                break

        if verbose:
            console.print(
                f"[blue]Retrieved {len(all_groups)} total groups from Identity Store[/blue]"
            )

        # Filter groups based on the regex pattern
        matching_groups = []
        for group in all_groups:
            # Check display name
            display_name = group.get("DisplayName", "")
            if compiled_pattern.search(display_name):
                matching_groups.append(group)
                continue

            # Check description
            description = group.get("Description", "")
            if compiled_pattern.search(description):
                matching_groups.append(group)
                continue

            # Check external IDs (if any)
            external_ids = group.get("ExternalIds", [])
            for external_id in external_ids:
                external_id_value = external_id.get("Id", "")
                if compiled_pattern.search(external_id_value):
                    matching_groups.append(group)
                    break

        # Apply limit if specified
        if limit and len(matching_groups) > limit:
            matching_groups = matching_groups[:limit]
            limit_info = f" (limited to {limit})"
        else:
            limit_info = ""

        # Display results
        if not matching_groups:
            console.print(f"[yellow]No groups found matching pattern '{pattern}'.[/yellow]")
            return []

        # Display search results summary
        console.print(
            f"[green]Found {len(matching_groups)} groups matching pattern '{pattern}'{limit_info}.[/green]"
        )

        # Create a table for displaying matching groups
        table = Table(title=f"Groups matching '{pattern}' in Identity Store {identity_store_id}")

        # Add columns to the table
        table.add_column("Group ID", style="cyan")
        table.add_column("Display Name", style="green")
        table.add_column("Description", style="blue")
        table.add_column("External ID", style="magenta")

        # Add rows to the table
        for group in matching_groups:
            group_id = group.get("GroupId", "")
            display_name = group.get("DisplayName", "")
            description = group.get("Description", "")

            # Extract external ID if available
            external_id = ""
            external_ids = group.get("ExternalIds", [])
            if external_ids:
                external_id = external_ids[0].get("Id", "")

            # Add the row to the table
            table.add_row(group_id, display_name, description, external_id)

        # Display the table
        console.print(table)

        # Return the matching groups for further processing
        return matching_groups

    except Exception as e:
        # Handle all errors using common error handler
        handle_aws_error(e, "finding groups", verbose=verbose)
        raise typer.Exit(1)
