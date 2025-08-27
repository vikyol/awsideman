"""Delete group command for awsideman."""

import re
from typing import Optional

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError

from ...utils.error_handler import handle_aws_error, handle_network_error, with_retry
from .helpers import console, get_single_key, validate_non_empty, validate_sso_instance


def delete_group(
    identifier: str = typer.Argument(..., help="Group name or ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    ),
):
    """Delete a group from AWS Identity Center.

    Permanently removes a group from the Identity Store.
    Requires confirmation unless the --force flag is used.

    Examples:
        # Delete a group with confirmation
        $ awsideman group delete TestGroup

        # Delete a group by ID
        $ awsideman group delete 12345678-1234-1234-1234-123456789012

        # Force delete without confirmation
        $ awsideman group delete OldGroup --force

        # Delete using a specific AWS profile
        $ awsideman group delete DevGroup --profile dev-account
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

            # Search by display name
            try:
                search_response = identity_store.list_groups(
                    IdentityStoreId=identity_store_id,
                    Filters=[{"AttributePath": "DisplayName", "AttributeValue": identifier}],
                )

                groups = search_response.get("Groups", [])

                # Handle search results
                if not groups:
                    console.print(f"[red]Error: No group found with name '{identifier}'.[/red]")
                    console.print("[yellow]Please check the group name and try again.[/yellow]")
                    console.print(
                        "[yellow]You can list available groups with 'awsideman group list'.[/yellow]"
                    )
                    return  # Exit cleanly for "not found" scenario
                elif len(groups) > 1:
                    console.print(
                        f"[yellow]Warning: Multiple groups found matching '{identifier}'. Deleting the first match.[/yellow]"
                    )
                    console.print(
                        "[yellow]Consider using the group ID instead of the name for more precise targeting.[/yellow]"
                    )

                # Use the first group found
                group_id = groups[0].get("GroupId")
                console.print(
                    f"[green]Found group: {groups[0].get('DisplayName', 'N/A')} (ID: {group_id})[/green]"
                )

            except ClientError as search_error:
                console.print(
                    f"[red]Error searching for group: {search_error.response.get('Error', {}).get('Message', str(search_error))}[/red]"
                )
                console.print(
                    "[yellow]Try using the group ID instead of the name if this error persists.[/yellow]"
                )
                handle_aws_error(search_error, operation="ListGroups")
                raise typer.Exit(1)

        # Verify the group exists before attempting to delete
        try:
            # Make the API call to describe the group
            group_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            # Get the display name for confirmation message
            display_name = group_details.get("DisplayName", "Unknown")

            # Log the operation
            console.print(
                f"[blue]Preparing to delete group '{display_name}' (ID: {group_id}) from Identity Store {identity_store_id}...[/blue]"
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            # Handle group not found error
            if error_code == "ResourceNotFoundException":
                console.print(f"[red]Error: Group with ID '{group_id}' not found.[/red]")
                console.print("[yellow]Please check the group ID or name and try again.[/yellow]")
                console.print(
                    "[yellow]You can list available groups with 'awsideman group list'.[/yellow]"
                )
                return  # Exit cleanly for "not found" scenario
            else:
                # Handle other errors with improved messages
                handle_aws_error(e, operation="DescribeGroup")
                raise typer.Exit(1)

        # Check if force option is used, otherwise prompt for confirmation
        if not force:
            console.print(
                f"[yellow]Warning: This will permanently delete group '{display_name}' (ID: {group_id}).[/yellow]"
            )
            console.print("[yellow]This action cannot be undone.[/yellow]")
            console.print("\n[blue]Are you sure you want to continue? (y/N)[/blue]")

            try:
                # Wait for user input
                confirmation = get_single_key().lower()

                # Check if the user confirmed the deletion
                if confirmation != "y":
                    console.print("\n[yellow]Group deletion cancelled.[/yellow]")
                    raise typer.Exit(0)

                console.print()  # Add a newline for better formatting

            except KeyboardInterrupt:
                console.print("\n[yellow]Group deletion cancelled.[/yellow]")
                return

        # Make the API call to delete the group
        try:
            # Apply retry decorator for transient errors
            @with_retry(max_retries=3, delay=1.0, backoff=2.0)
            def delete_group_with_retry():
                return identity_store.delete_group(
                    IdentityStoreId=identity_store_id, GroupId=group_id
                )

            delete_group_with_retry()

            # Display success message
            console.print(f"[green]Group '{display_name}' deleted successfully.[/green]")

            return True

        except ClientError as delete_error:
            error_code = delete_error.response.get("Error", {}).get("Code", "Unknown")

            # Handle specific error cases
            if error_code == "ResourceNotFoundException":
                console.print(
                    f"[red]Error: Group with ID '{group_id}' not found or already deleted.[/red]"
                )
                console.print(
                    "[yellow]The group may have been deleted by another process or user.[/yellow]"
                )
                return  # Exit cleanly for "not found" scenario
            else:
                handle_aws_error(delete_error, operation="DeleteGroup")
                raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="DeleteGroup")
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
