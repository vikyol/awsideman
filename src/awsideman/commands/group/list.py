"""List groups command for awsideman."""

import os
from typing import Any, Dict, List, Optional, Tuple

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...utils.error_handler import handle_aws_error, handle_network_error
from .helpers import (
    console,
    get_single_key,
    validate_filter,
    validate_limit,
    validate_profile,
    validate_sso_instance,
)


def _list_groups_internal(
    filter: Optional[str] = None,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Internal implementation of list_groups that can be called directly from tests.

    Args:
        filter: Filter groups by attribute in format 'attribute=value'
        limit: Maximum number of groups to return in a single page
        next_token: Pagination token
        profile: AWS profile to use

    Returns:
        Tuple of (groups, next_token)
    """
    try:
        # Validate inputs
        if filter and not validate_filter(filter):
            raise typer.Exit(1)

        if not validate_limit(limit):
            raise typer.Exit(1)
        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Check if AWS_DEFAULT_REGION environment variable is set
        if os.environ.get("AWS_DEFAULT_REGION"):
            console.print(
                f"[yellow]Warning: AWS_DEFAULT_REGION environment variable is set to '{os.environ.get('AWS_DEFAULT_REGION')}'. This may override the region in your profile.[/yellow]"
            )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()

        # Prepare the list_groups API call parameters
        list_groups_params = {"IdentityStoreId": identity_store_id}

        # Add optional parameters if provided
        if filter:
            # Check if filter is in the format "attribute=value"
            if "=" not in filter:
                raise ValueError("Filter must be in the format 'attribute=value'")

            attribute_path, attribute_value = filter.split("=", 1)
            list_groups_params["Filters"] = [
                {"AttributePath": attribute_path, "AttributeValue": attribute_value}
            ]

        if limit:
            list_groups_params["MaxResults"] = limit

        if next_token:
            list_groups_params["NextToken"] = next_token

        # Make the API call to list groups
        response = identity_store.list_groups(**list_groups_params)

        # Extract groups and next token from the response
        groups = response.get("Groups", [])
        next_token = response.get("NextToken")

        # Display the results using a Rich table
        if not groups:
            console.print("[yellow]No groups found.[/yellow]")
            return [], next_token

        # Display pagination status
        page_info = ""
        if next_token:
            page_info = " (more results available)"
        if limit:
            page_info = f" (showing up to {limit} results{page_info.replace(' (', ', ') if page_info else ''})"

        console.print(f"[green]Found {len(groups)} groups{page_info}.[/green]")

        # Create a table for displaying groups
        table = Table(title=f"Groups in Identity Store {identity_store_id}")

        # Add columns to the table
        table.add_column("Group ID", style="cyan")
        table.add_column("Display Name", style="green")
        table.add_column("Description", style="blue")

        # Add rows to the table
        for group in groups:
            group_id = group.get("GroupId", "")
            display_name = group.get("DisplayName", "")
            description = group.get("Description", "")

            # Add the row to the table
            table.add_row(group_id, display_name, description)

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
                    # Call _list_groups_internal recursively with the next token
                    return _list_groups_internal(
                        filter=filter, limit=limit, next_token=next_token, profile=profile
                    )
                else:
                    console.print("\n[yellow]Pagination stopped.[/yellow]")
            except KeyboardInterrupt:
                console.print("\n[yellow]Pagination stopped by user.[/yellow]")

        # Return the groups and next token for further processing
        return groups, next_token

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="ListGroups")
    except ValueError as e:
        # Handle filter format errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print("[yellow]Filter format should be 'attribute=value'.[/yellow]")
        console.print("[yellow]Example: --filter DisplayName=Administrators[/yellow]")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)


def list_groups(
    filter: Optional[str] = typer.Option(
        None,
        "--filter",
        "-f",
        help="Filter groups by attribute in format 'attribute=value' (e.g., DisplayName=engineering)",
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum number of groups to return in a single page"
    ),
    next_token: Optional[str] = typer.Option(
        None, "--next-token", "-n", help="Pagination token (for internal use)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """List all groups in the Identity Store.

    Displays a table of groups with their IDs, names, and descriptions.
    Results can be filtered and paginated. Press ENTER to see the next page of results.
    """
    return _list_groups_internal(filter, limit, next_token, profile)
