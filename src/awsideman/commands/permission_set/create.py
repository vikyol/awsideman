"""Create permission set command for awsideman."""

from typing import List, Optional

import typer
from botocore.exceptions import ClientError, ConnectionError, EndpointConnectionError
from rich.panel import Panel
from rich.table import Table

from ...aws_clients.manager import AWSClientManager
from ...utils.error_handler import handle_aws_error, handle_network_error, with_retry
from .helpers import (
    console,
    format_permission_set_for_display,
    validate_aws_managed_policy_arn,
    validate_permission_set_description,
    validate_permission_set_name,
    validate_profile,
    validate_sso_instance,
)


def create_permission_set(
    name: str = typer.Option(..., "--name", help="Name for the permission set"),
    description: Optional[str] = typer.Option(
        None, "--description", help="Description for the permission set"
    ),
    session_duration: Optional[str] = typer.Option(
        "PT1H",
        "--session-duration",
        help="Session duration (ISO-8601 format, e.g., PT1H for 1 hour, PT30M for 30 minutes)",
    ),
    relay_state: Optional[str] = typer.Option(
        None,
        "--relay-state",
        help="Relay state URL (the URL users are redirected to after federation)",
    ),
    managed_policy: Optional[List[str]] = typer.Option(
        None,
        "--managed-policy",
        help="AWS-managed policy ARN to attach (can be specified multiple times)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Create a new permission set in AWS Identity Center.

    Creates a new permission set with the specified attributes and optionally attaches AWS-managed policies.
    Displays the created permission set details upon successful creation.

    The permission set name must be unique within the Identity Center instance and can contain
    alphanumeric characters and the following special characters: +=,.@_-

    Session duration must be in ISO-8601 format (e.g., PT1H for 1 hour, PT8H for 8 hours, PT30M for 30 minutes).

    Examples:
        # Create a basic permission set
        $ awsideman permission-set create --name BasicAccess --description "Basic access to AWS resources"

        # Create a permission set with custom session duration
        $ awsideman permission-set create --name LongSession --description "Extended session" --session-duration PT8H

        # Create a permission set with AWS managed policy
        $ awsideman permission-set create --name AdminAccess --managed-policy arn:aws:iam::aws:policy/AdministratorAccess

        # Create a permission set with multiple AWS managed policies
        $ awsideman permission-set create --name PowerUser --managed-policy arn:aws:iam::aws:policy/PowerUserAccess --managed-policy arn:aws:iam::aws:policy/AmazonS3FullAccess

        # Create a permission set with relay state URL
        $ awsideman permission-set create --name S3Access --relay-state https://console.aws.amazon.com/s3/
    """
    try:
        # Validate inputs
        if not validate_permission_set_name(name):
            raise typer.Exit(1)

        if description is not None and not validate_permission_set_description(description):
            raise typer.Exit(1)

        # Validate managed policy ARNs if provided
        if managed_policy:
            for policy_arn in managed_policy:
                if not validate_aws_managed_policy_arn(policy_arn):
                    raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, _ = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the SSO Admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Prepare the create_permission_set API call parameters
        create_permission_set_params = {"InstanceArn": instance_arn, "Name": name}

        # Add optional parameters if provided
        if description:
            create_permission_set_params["Description"] = description

        if session_duration:
            create_permission_set_params["SessionDuration"] = session_duration

        if relay_state:
            create_permission_set_params["RelayState"] = relay_state

        # Display a message indicating that we're creating the permission set
        console.print(f"[blue]Creating permission set '{name}'...[/blue]")

        # Use with_retry decorator to handle transient errors
        @with_retry(max_retries=3, delay=1.0)
        def create_permission_set_with_retry(params):
            return sso_admin_client.create_permission_set(**params)

        try:
            # Make the API call to create the permission set
            response = create_permission_set_with_retry(create_permission_set_params)

            # Extract the permission set ARN from the response
            permission_set_arn = None
            if "PermissionSet" in response and "PermissionSetArn" in response["PermissionSet"]:
                permission_set_arn = response["PermissionSet"]["PermissionSetArn"]
            else:
                permission_set_arn = response.get("PermissionSetArn")

            if not permission_set_arn:
                console.print("[red]Error: Failed to create permission set. No ARN returned.[/red]")
                raise typer.Exit(1)

            console.print(f"[green]Permission set '{name}' created successfully.[/green]")
            console.print(f"[green]Permission Set ARN: {permission_set_arn}[/green]")

            # Invalidate cache to ensure permission set data is fresh
            try:
                # Use the AWS client manager's cache manager to ensure we invalidate
                # Clear internal data storage to ensure fresh data
                if aws_client.is_caching_enabled():
                    # Clear the cache directly through the AWS client manager
                    aws_client.clear_cache()

            except Exception as cache_error:
                # Don't fail the command if cache invalidation fails
                console.print(
                    f"[yellow]Warning: Failed to invalidate cache: {cache_error}[/yellow]"
                )

            # Attach managed policies if provided
            attached_policies = []
            if managed_policy:
                console.print(f"[blue]Attaching {len(managed_policy)} managed policies...[/blue]")

                # Use with_retry decorator to handle transient errors
                @with_retry(max_retries=3, delay=1.0)
                def attach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn):
                    return sso_admin_client.attach_managed_policy_to_permission_set(
                        InstanceArn=instance_arn,
                        PermissionSetArn=permission_set_arn,
                        ManagedPolicyArn=policy_arn,
                    )

                for policy_arn in managed_policy:
                    try:
                        # Validate the policy ARN again (redundant but safe)
                        if not validate_aws_managed_policy_arn(policy_arn):
                            console.print(
                                f"[yellow]Skipping invalid policy ARN: {policy_arn}[/yellow]"
                            )
                            continue

                        # Make the API call to attach the managed policy
                        attach_managed_policy_with_retry(
                            instance_arn, permission_set_arn, policy_arn
                        )

                        # Extract the policy name from the ARN for display
                        policy_name = policy_arn.split("/")[-1]
                        console.print(f"[green]Attached policy: {policy_name}[/green]")

                        # Add the policy to the list of attached policies
                        attached_policies.append({"Name": policy_name, "Arn": policy_arn})

                    except ClientError as e:
                        error_code = e.response.get("Error", {}).get("Code", "Unknown")
                        error_message = e.response.get("Error", {}).get("Message", str(e))

                        console.print(
                            f"[yellow]Warning: Failed to attach policy {policy_arn}: {error_code} - {error_message}[/yellow]"
                        )
                        console.print(
                            "[yellow]The permission set was created but not all policies were attached.[/yellow]"
                        )

            # Get the full permission set details to display
            try:
                # Use with_retry decorator to handle transient errors
                @with_retry(max_retries=3, delay=1.0)
                def get_permission_set_details(instance_arn, permission_set_arn):
                    return sso_admin_client.describe_permission_set(
                        InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                    )

                # Get permission set details with retry logic
                permission_set_response = get_permission_set_details(
                    instance_arn, permission_set_arn
                )
                permission_set = permission_set_response.get("PermissionSet", {})

                # Store the ARN in the permission set object for reference
                permission_set["PermissionSetArn"] = permission_set_arn

                # Format the permission set data for display
                formatted_permission_set = format_permission_set_for_display(permission_set)

                # Create a table for the permission set details
                details_table = Table(show_header=False, box=None)
                details_table.add_column("Attribute", style="cyan")
                details_table.add_column("Value")

                # Add rows for each attribute
                for key, value in formatted_permission_set.items():
                    details_table.add_row(key, str(value))

                # Create a table for the managed policies
                policies_table = Table(title="Attached AWS Managed Policies", show_header=True)
                policies_table.add_column("Name", style="green")
                policies_table.add_column("ARN", style="cyan")

                # Add rows for each policy
                if attached_policies:
                    for policy in attached_policies:
                        policy_name = policy.get("Name", "N/A")
                        policy_arn = policy.get("Arn", "N/A")
                        policies_table.add_row(policy_name, policy_arn)
                else:
                    policies_table.add_row("No managed policies attached", "")

                # Create a panel for the permission set details
                panel = Panel(
                    details_table,
                    title=f"Permission Set: {permission_set.get('Name', 'Unknown')}",
                    expand=False,
                )

                # Display the panel and policies table
                console.print(panel)
                console.print(policies_table)

            except ClientError:
                # Just log a warning if we can't get the details, but don't fail the command
                console.print(
                    "[yellow]Warning: Could not retrieve full permission set details after creation.[/yellow]"
                )

            return {
                "PermissionSetArn": permission_set_arn,
                "Name": name,
                "Description": description,
                "SessionDuration": session_duration,
                "RelayState": relay_state,
                "AttachedManagedPolicies": attached_policies,
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ConflictException":
                console.print(f"[red]Error: Permission set '{name}' already exists.[/red]")
                console.print(
                    "[yellow]Use a different name or use 'awsideman permission-set update' to modify an existing permission set.[/yellow]"
                )
            else:
                console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                console.print(
                    "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                )

            raise typer.Exit(1)

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="CreatePermissionSet")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
        raise typer.Exit(1)
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)
