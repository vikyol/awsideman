"""Update group command for awsideman."""

from typing import Optional

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError

from ...utils.error_handler import handle_aws_error, handle_network_error
from .get import get_group
from .helpers import (
    console,
    validate_group_description,
    validate_group_name,
    validate_non_empty,
    validate_sso_instance,
)


def update_group(
    identifier: str = typer.Argument(..., help="Group name or ID to update"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New display name for the group"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="New description for the group"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
) -> dict:
    """
    Update a group's attributes in AWS Identity Center.

    Updates the specified group with new attribute values.
    Only the attributes you specify will be updated; others will remain unchanged.

    Examples:
        # Update group name
        $ awsideman group update Developers --name Engineers

        # Update group description
        $ awsideman group update Administrators --description "System administrators with elevated privileges"

        # Update multiple attributes
        $ awsideman group update TestGroup --name ProductionGroup --description "Production environment access"

        # Update using a specific AWS profile
        $ awsideman group update DevTeam --name EngineeringTeam --profile dev-account
    """
    try:
        # Validate inputs
        if not validate_non_empty(identifier, "Group identifier"):
            raise typer.Exit(1)

        if not name and description is None:
            console.print("[red]Error: At least one of name or description must be provided.[/red]")
            raise typer.Exit(1)

        if name and not validate_group_name(name):
            raise typer.Exit(1)

        if description and not validate_group_description(description):
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

        # Get the group first to ensure it exists and get current details
        group_details = get_group(identifier, profile)
        group_id = group_details.get("GroupId")

        # Prepare update operations
        operations = []

        if name:
            operations.append({"AttributePath": "DisplayName", "AttributeValue": name})

        if description is not None:
            operations.append({"AttributePath": "Description", "AttributeValue": description})

        # Update the group
        try:
            identity_store.update_group(
                IdentityStoreId=identity_store_id,
                GroupId=group_id,
                Operations=[
                    {"AttributePath": op["AttributePath"], "AttributeValue": op["AttributeValue"]}
                    for op in operations
                ],
            )

            # Get updated group details
            updated_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            console.print("[green]Group updated successfully![/green]")

            # Cache invalidation is now handled automatically by the cached client

            return updated_details

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
            raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="UpdateGroup")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
