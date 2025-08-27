"""Get group command for awsideman."""

import re
from typing import Optional

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError

from ...utils.error_handler import handle_aws_error, handle_network_error
from .helpers import console, validate_non_empty, validate_sso_instance


def get_group(
    identifier: str = typer.Argument(..., help="Group name or ID to retrieve"),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
) -> dict:
    """
    Get detailed information about a group.

    Retrieves and displays comprehensive information about a group by their name or ID.
    Shows all available group attributes including description, creation date, and member count.

    Examples:
        # Get group by name
        $ awsideman group get Administrators

        # Get group by ID
        $ awsideman group get 12345678-1234-1234-1234-123456789012

        # Get group using a specific AWS profile
        $ awsideman group get Developers --profile dev-account
    """
    try:
        # Validate inputs
        if not validate_non_empty(identifier, "Group identifier"):
            raise typer.Exit(1)

        # Validate profile and get AWS client with cache integration
        from ..common import validate_profile_with_cache

        profile_name, profile_data, aws_client = validate_profile_with_cache(
            profile=profile, enable_caching=True, region=None
        )

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Get the identity store client (now cached)
        identity_store = aws_client.get_identity_store_client()

        # Check if identifier is a UUID (group ID) or if we need to search
        uuid_pattern = (
            r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{10,})"
        )
        if re.match(uuid_pattern, identifier, re.IGNORECASE):
            # Direct lookup by group ID
            group_id = identifier
        else:
            # Search for group by display name
            console.print(f"[blue]Searching for group: {identifier}[/blue]")

            try:
                search_response = identity_store.list_groups(
                    IdentityStoreId=identity_store_id,
                    Filters=[{"AttributePath": "DisplayName", "AttributeValue": identifier}],
                )

                groups = search_response.get("Groups", [])

                if not groups:
                    console.print(f"[red]Error: No group found with name '{identifier}'.[/red]")
                    console.print(
                        "[yellow]You can list available groups with 'awsideman group list'.[/yellow]"
                    )
                    return  # Exit cleanly for "not found" scenario
                elif len(groups) > 1:
                    console.print(
                        f"[yellow]Warning: Multiple groups found matching '{identifier}'. Showing the first match.[/yellow]"
                    )

                group_id = groups[0].get("GroupId")
                console.print(f"[green]Found group: {identifier} (ID: {group_id})[/green]")

            except ClientError as e:
                handle_aws_error(e, operation="ListGroups")
                raise typer.Exit(1)

        # Get group details
        try:
            group_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            return group_details

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: Group '{group_id}' not found.[/red]")
                console.print("[yellow]Please check the group ID or name and try again.[/yellow]")
                return  # Exit cleanly for "not found" scenario
            else:
                handle_aws_error(e, operation="DescribeGroup")
                raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="DescribeGroup")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
