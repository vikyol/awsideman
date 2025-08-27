"""Find permission sets command for awsideman."""

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


def find_permission_sets(
    pattern: str = typer.Argument(
        ...,
        help="Regex pattern to search for in permission set names, descriptions, or display names",
    ),
    case_sensitive: bool = typer.Option(
        False, "--case-sensitive", "-c", help="Make the search case sensitive"
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of permission sets to return"
    ),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> List[dict]:
    """Find permission sets in AWS Identity Center based on a regex pattern.

    Searches through all permission sets in the Identity Center and returns those whose names,
    descriptions, or display names match the specified regex pattern. The search is performed
    locally after retrieving all permission sets from AWS.

    Examples:
        # Find permission sets with 'admin' in their name (case insensitive)
        $ awsideman permission-set find 'admin'

        # Find permission sets with 'readonly' in their name (case sensitive)
        $ awsideman permission-set find 'readonly' --case-sensitive

        # Find permission sets with descriptions containing 'temporary'
        $ awsideman permission-set find 'temporary'

        # Find permission sets with names starting with 'A' and ending with 'n'
        $ awsideman permission-set find '^A.*n$'

        # Limit results to 5 permission sets
        $ awsideman permission-set find 'team' --limit 5

        # Use a specific AWS profile
        $ awsideman permission-set find 'test' --profile dev-account
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
        instance_arn, _ = validate_sso_instance(profile_data)

        # Get the SSO admin client
        sso_admin = aws_client.get_identity_center_client()

        # Display search information
        case_info = "case sensitive" if case_sensitive else "case insensitive"
        console.print(
            f"[blue]Searching for permission sets matching pattern '{pattern}' ({case_info})...[/blue]"
        )

        # Get all permission sets from the Identity Center
        all_permission_sets = []
        next_token = None

        while True:
            list_params = {"InstanceArn": instance_arn}
            if next_token:
                list_params["NextToken"] = next_token

            response = sso_admin.list_permission_sets(**list_params)
            batch_permission_sets = response.get("PermissionSets", [])
            all_permission_sets.extend(batch_permission_sets)

            next_token = response.get("NextToken")
            if not next_token:
                break

        if verbose:
            console.print(
                f"[blue]Retrieved {len(all_permission_sets)} total permission sets from Identity Center[/blue]"
            )

        # Get detailed information for each permission set
        matching_permission_sets = []
        for permission_set_arn in all_permission_sets:
            try:
                # Get permission set details
                describe_response = sso_admin.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                )

                permission_set = describe_response.get("PermissionSet", {})

                # Check name
                name = permission_set.get("Name", "")
                if compiled_pattern.search(name):
                    matching_permission_sets.append(
                        {
                            "PermissionSetArn": permission_set_arn,
                            "Name": name,
                            "Description": permission_set.get("Description", ""),
                            "SessionDuration": permission_set.get("SessionDuration", ""),
                            "RelayState": permission_set.get("RelayState", ""),
                        }
                    )
                    continue

                # Check description
                description = permission_set.get("Description", "")
                if compiled_pattern.search(description):
                    matching_permission_sets.append(
                        {
                            "PermissionSetArn": permission_set_arn,
                            "Name": name,
                            "Description": description,
                            "SessionDuration": permission_set.get("SessionDuration", ""),
                            "RelayState": permission_set.get("RelayState", ""),
                        }
                    )
                    continue

            except Exception as e:
                if verbose:
                    console.print(
                        f"[yellow]Warning: Could not retrieve details for permission set {permission_set_arn}: {e}[/yellow]"
                    )
                continue

        # Apply limit if specified
        if limit and len(matching_permission_sets) > limit:
            matching_permission_sets = matching_permission_sets[:limit]
            limit_info = f" (limited to {limit})"
        else:
            limit_info = ""

        # Display results
        if not matching_permission_sets:
            console.print(
                f"[yellow]No permission sets found matching pattern '{pattern}'.[/yellow]"
            )
            return []

        # Display search results summary
        console.print(
            f"[green]Found {len(matching_permission_sets)} permission sets matching pattern '{pattern}'{limit_info}.[/green]"
        )

        # Create a table for displaying matching permission sets
        table = Table(title=f"Permission Sets matching '{pattern}' in Identity Center")

        # Add columns to the table
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="green")
        table.add_column("Session Duration", style="blue")
        table.add_column("Relay State", style="magenta")
        table.add_column("ARN", style="yellow")

        # Add rows to the table
        for permission_set in matching_permission_sets:
            name = permission_set.get("Name", "")
            description = permission_set.get("Description", "")
            session_duration = permission_set.get("SessionDuration", "")
            relay_state = permission_set.get("RelayState", "")
            arn = permission_set.get("PermissionSetArn", "")

            # Format session duration for display
            if session_duration:
                session_duration = f"{session_duration} seconds"
            else:
                session_duration = "Default"

            # Format relay state for display
            if not relay_state:
                relay_state = "None"

            # Truncate long ARNs for display
            display_arn = arn
            if len(arn) > 50:
                display_arn = f"{arn[:47]}..."

            # Add the row to the table
            table.add_row(name, description, session_duration, relay_state, display_arn)

        # Display the table
        console.print(table)

        # Return the matching permission sets for further processing
        return matching_permission_sets

    except Exception as e:
        # Handle all errors using common error handler
        handle_aws_error(e, "finding permission sets", verbose=verbose)
        raise typer.Exit(1)
