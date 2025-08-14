"""Create group command for awsideman."""

from typing import Optional

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError

from ...aws_clients.manager import AWSClientManager
from ...utils.error_handler import handle_aws_error, handle_network_error
from .helpers import (
    console,
    validate_group_description,
    validate_group_name,
    validate_non_empty,
    validate_profile,
    validate_sso_instance,
)


def create_group(
    name: str = typer.Option(..., "--name", "-n", help="Display name for the group"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Optional description for the group"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
) -> tuple[str, dict]:
    """
    Create a new group in AWS Identity Center.

    Creates a new group in the Identity Store with the specified name and optional description.
    The group name must be unique within the Identity Center instance.

    Examples:
        # Create a basic group
        $ awsideman group create --name Developers

        # Create a group with description
        $ awsideman group create --name Administrators --description "System administrators with full access"

        # Create a group using a specific AWS profile
        $ awsideman group create --name Engineers --description "Engineering team members" --profile dev-account
    """
    try:
        # Validate inputs
        if not validate_non_empty(name, "Group name"):
            raise typer.Exit(1)

        if not validate_group_name(name):
            raise typer.Exit(1)

        if description and not validate_group_description(description):
            raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        _, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the identity store client
        identity_store = aws_client.get_identity_store_client()

        # Check if group already exists
        try:
            search_response = identity_store.list_groups(
                IdentityStoreId=identity_store_id,
                Filters=[{"AttributePath": "DisplayName", "AttributeValue": name}],
            )

            existing_groups = search_response.get("Groups", [])
            if existing_groups:
                console.print(f"[red]Error: A group with name '{name}' already exists.[/red]")
                raise typer.Exit(1)

        except ClientError as e:
            handle_aws_error(e, operation="ListGroups")
            raise typer.Exit(1)

        # Create the group
        create_params = {"IdentityStoreId": identity_store_id, "DisplayName": name}

        if description:
            create_params["Description"] = description

        try:
            response = identity_store.create_group(**create_params)
            group_id = response.get("GroupId")

            # Get the created group details
            group_details = identity_store.describe_group(
                IdentityStoreId=identity_store_id, GroupId=group_id
            )

            console.print("[green]Group created successfully![/green]")

            return group_id, group_details

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            console.print(f"[red]Error ({error_code}): {error_message}[/red]")
            raise typer.Exit(1)

    except ClientError as e:
        handle_aws_error(e, operation="CreateGroup")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)
