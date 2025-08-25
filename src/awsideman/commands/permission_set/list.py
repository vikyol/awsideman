"""List permission sets command for awsideman."""

import os
from typing import Any, Dict, List, Optional, Tuple

import typer
from botocore.exceptions import ClientError
from rich.table import Table

from ...utils.validators import validate_filter, validate_limit
from ..common import (
    extract_standard_params,
    handle_aws_error,
    profile_option,
    region_option,
    show_cache_info,
    validate_profile_with_cache,
)
from .helpers import console, get_single_key, validate_sso_instance


def _list_permission_sets_internal(
    filter: Optional[str] = None,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
    region: Optional[str] = None,
    enable_caching: bool = True,
    verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Internal implementation of list_permission_sets that can be called directly from tests.

    Args:
        filter: Filter permission sets by attribute in format 'attribute=value'
        limit: Maximum number of permission sets to return in a single page
        next_token: Pagination token
        profile: AWS profile to use

    Returns:
        Tuple of (permission_sets, next_token)
    """
    try:
        # Validate inputs
        if filter and not validate_filter(filter):
            raise typer.Exit(1)

        if not validate_limit(limit):
            raise typer.Exit(1)

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
        instance_arn, _ = validate_sso_instance(profile_data)

        # Get the SSO Admin client with caching support
        sso_admin_client = aws_client.get_identity_center_client()

        # Prepare the list_permission_sets API call parameters
        list_permission_sets_params = {"InstanceArn": instance_arn}

        # Add optional parameters if provided
        if limit:
            list_permission_sets_params["MaxResults"] = limit

        if next_token:
            list_permission_sets_params["NextToken"] = next_token

        # Make the API call to list permission sets
        response = sso_admin_client.list_permission_sets(**list_permission_sets_params)

        # Extract permission sets and next token from the response
        permission_set_arns = response.get("PermissionSets", [])
        next_token = response.get("NextToken")

        # If no permission sets found, return empty list
        if not permission_set_arns:
            console.print("[yellow]No permission sets found.[/yellow]")
            return [], next_token

        # Display pagination status
        page_info = ""
        if next_token:
            page_info = " (more results available)"
        if limit:
            page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"

        console.print(
            f"[green]Found {len(permission_set_arns)} permission sets{page_info}.[/green]"
        )

        # Create a table for displaying permission sets
        table = Table(title=f"Permission Sets in Identity Center Instance {instance_arn}")

        # Add columns to the table
        table.add_column("Name", style="green")
        table.add_column("ARN", style="cyan", no_wrap=False)
        table.add_column("Description", style="blue")
        table.add_column("Session Duration", style="magenta")

        # We need to get details for each permission set
        permission_sets = []
        filtered_permission_sets = []

        for permission_set_arn in permission_set_arns:
            try:
                # Get permission set details
                permission_set_response = sso_admin_client.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                )
                permission_set = permission_set_response.get("PermissionSet", {})

                # Store the ARN in the permission set object for reference
                permission_set["PermissionSetArn"] = permission_set_arn
                permission_sets.append(permission_set)

                # Extract fields for display and filtering
                name = permission_set.get("Name", "")
                description = permission_set.get("Description", "")
                session_duration = permission_set.get("SessionDuration", "PT1H")
                relay_state = permission_set.get("RelayState", "")

                # Format session duration for display
                formatted_duration = session_duration
                if session_duration.startswith("PT"):
                    duration = session_duration[2:]
                    if "H" in duration:
                        hours = duration.split("H")[0]
                        formatted_duration = f"{hours} hour(s)"
                    elif "M" in duration:
                        minutes = duration.split("M")[0]
                        formatted_duration = f"{minutes} minute(s)"

                # Apply filtering if specified
                if filter:
                    # Check if filter is in the format "attribute=value"
                    if "=" not in filter:
                        raise ValueError("Filter must be in the format 'attribute=value'")

                    attribute_path, attribute_value = filter.split("=", 1)
                    attribute_value = attribute_value.lower()

                    # Skip this permission set if it doesn't match the filter
                    if attribute_path.lower() == "name" and attribute_value not in name.lower():
                        continue
                    elif (
                        attribute_path.lower() == "description"
                        and attribute_value not in description.lower()
                    ):
                        continue
                    elif (
                        attribute_path.lower() == "sessionduration"
                        and attribute_value not in session_duration.lower()
                    ):
                        continue
                    elif (
                        attribute_path.lower() == "relaystate"
                        and attribute_value not in relay_state.lower()
                    ):
                        continue
                    elif (
                        attribute_path.lower() == "arn"
                        and attribute_value not in permission_set_arn.lower()
                    ):
                        continue

                # Add the permission set to the filtered list
                filtered_permission_sets.append(permission_set)

                # Add the row to the table
                table.add_row(name, permission_set_arn, description or "N/A", formatted_duration)

            except ClientError as e:
                # Handle errors for individual permission sets
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_message = e.response.get("Error", {}).get("Message", str(e))
                console.print(
                    f"[yellow]Warning: Could not retrieve details for permission set {permission_set_arn}: {error_code} - {error_message}[/yellow]"
                )

                # Add a placeholder row with just the ARN
                table.add_row("Unknown", permission_set_arn, "Error retrieving details", "Unknown")

        # Display filtered results count if filtering was applied
        if filter and len(filtered_permission_sets) != len(permission_sets):
            console.print(
                f"[green]Filtered to {len(filtered_permission_sets)} permission sets matching '{filter}'.[/green]"
            )

        # Display the table
        console.print(table)

        # Handle pagination - interactive by default
        final_next_token = None  # Initialize final next token

        if next_token:
            # Check if this is a recursive call (next_token from API response) vs. explicit user parameter
            # We can determine this by checking if the next_token parameter matches the original function call
            # For the first call, next_token parameter will be None, so we show interactive prompt
            # For recursive calls, next_token will be the API response token, so we show interactive prompt

            # Always show interactive prompt for permission set list
            console.print(
                "\n[blue]Press ENTER to see the next page, or any other key to exit...[/blue]"
            )
            try:
                # Wait for single key press
                key = get_single_key()

                # If the user pressed Enter (or Return), fetch the next page
                if key in ["\r", "\n", ""]:
                    console.print("\n[blue]Fetching next page...[/blue]\n")
                    # Call _list_permission_sets_internal recursively with the next token
                    return _list_permission_sets_internal(
                        filter=filter,
                        limit=limit,
                        next_token=next_token,
                        profile=profile,
                        region=region,
                        enable_caching=enable_caching,
                        verbose=verbose,
                    )
                else:
                    console.print("\n[yellow]Pagination stopped.[/yellow]")
                    # Set final next token to None to indicate pagination has stopped
                    final_next_token = None
            except KeyboardInterrupt:
                console.print("\n[yellow]Pagination stopped by user.[/yellow]")
                # Set final next token to None to indicate pagination has stopped
                final_next_token = None
        else:
            # No next token, so no pagination
            final_next_token = None

        # Return the filtered permission sets and final next token
        return filtered_permission_sets, final_next_token

    except ValueError as e:
        # Handle filter format errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("[yellow]Filter format should be 'attribute=value'.[/yellow]")
        console.print("[yellow]Example: --filter Name=AdminAccess[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        # Handle all other errors using common error handler
        handle_aws_error(e, "listing permission sets", verbose=verbose)
        raise typer.Exit(1)


def list_permission_sets(
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter permission sets by attribute in format 'attribute=value' (e.g., Name=AdminAccess)",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of permission sets to return"
    ),
    next_token: Optional[str] = typer.Option(None, "--next-token", "-n", help="Pagination token"),
    profile: Optional[str] = profile_option(),
    region: Optional[str] = region_option(),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """List all permission sets in the Identity Center.

    Displays a table of permission sets with their names, ARNs, descriptions, and session durations.
    Results can be filtered and paginated. Press ENTER to see the next page of results.

    Examples:
        # List all permission sets
        $ awsideman permission-set list

        # List permission sets with a name containing "Admin"
        $ awsideman permission-set list --filter Name=Admin

        # List up to 5 permission sets
        $ awsideman permission-set list --limit 5

        # List permission sets using a specific AWS profile
        $ awsideman permission-set list --profile dev-account

        # Continue pagination from a previous request
        $ awsideman permission-set list --next-token ABCDEF123456
    """
    # Extract and process standard command parameters
    profile, region, enable_caching = extract_standard_params(profile, region)

    # Show cache information if verbose
    show_cache_info(verbose)

    return _list_permission_sets_internal(
        filter, limit, next_token, profile, region, enable_caching, verbose
    )
