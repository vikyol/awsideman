"""Update permission set command for awsideman."""

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
    resolve_permission_set_identifier,
    validate_aws_managed_policy_arn,
    validate_permission_set_description,
    validate_profile,
    validate_sso_instance,
)


def update_permission_set(
    identifier: str = typer.Argument(..., help="Permission set name or ARN"),
    description: Optional[str] = typer.Option(
        None, "--description", help="Description for the permission set"
    ),
    session_duration: Optional[str] = typer.Option(
        None,
        "--session-duration",
        help="Session duration (ISO-8601 format, e.g., PT1H for 1 hour, PT30M for 30 minutes)",
    ),
    relay_state: Optional[str] = typer.Option(
        None,
        "--relay-state",
        help="Relay state URL (the URL users are redirected to after federation)",
    ),
    add_managed_policy: Optional[List[str]] = typer.Option(
        None,
        "--add-managed-policy",
        help="AWS-managed policy ARN to attach (can be specified multiple times)",
    ),
    remove_managed_policy: Optional[List[str]] = typer.Option(
        None,
        "--remove-managed-policy",
        help="AWS-managed policy ARN to detach (can be specified multiple times)",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="AWS profile to use"),
):
    """Update an existing permission set in AWS Identity Center.

    Updates the specified permission set with new attribute values and/or modifies attached policies.
    Displays the updated permission set details upon successful update.

    You can update the description, session duration, relay state, and attached AWS managed policies.
    Only the attributes you specify will be updated; others will remain unchanged.

    Examples:
        # Update permission set description
        $ awsideman permission-set update AdminAccess --description "Updated administrator access"

        # Update session duration
        $ awsideman permission-set update AdminAccess --session-duration PT4H

        # Update relay state URL
        $ awsideman permission-set update AdminAccess --relay-state https://console.aws.amazon.com/ec2/

        # Add an AWS managed policy
        $ awsideman permission-set update AdminAccess --add-managed-policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

        # Remove an AWS managed policy
        $ awsideman permission-set update AdminAccess --remove-managed-policy arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess

        # Update multiple attributes at once
        $ awsideman permission-set update AdminAccess --description "Updated access" --session-duration PT2H --add-managed-policy arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess
    """
    try:
        # Validate inputs
        if description is not None and not validate_permission_set_description(description):
            raise typer.Exit(1)

        # Validate managed policy ARNs if provided
        if add_managed_policy:
            for policy_arn in add_managed_policy:
                if not validate_aws_managed_policy_arn(policy_arn):
                    raise typer.Exit(1)

        if remove_managed_policy:
            for policy_arn in remove_managed_policy:
                if not validate_aws_managed_policy_arn(policy_arn):
                    raise typer.Exit(1)

        # Check if any update parameters were provided
        if not any(
            [
                description is not None,
                session_duration is not None,
                relay_state is not None,
                add_managed_policy is not None,
                remove_managed_policy is not None,
            ]
        ):
            console.print(
                "[yellow]Warning: No update parameters provided. Nothing to update.[/yellow]"
            )
            console.print(
                "[yellow]Use --description, --session-duration, --relay-state, --add-managed-policy, or --remove-managed-policy to specify updates.[/yellow]"
            )
            raise typer.Exit(1)

        # Validate the profile and get profile data
        profile_name, profile_data = validate_profile(profile)

        # Validate the SSO instance and get instance ARN and identity store ID
        instance_arn, identity_store_id = validate_sso_instance(profile_data)

        # Initialize the AWS client manager with the profile and region
        region = profile_data.get("region")
        aws_client = AWSClientManager(profile=profile_name, region=region)

        # Get the SSO admin client
        sso_admin_client = aws_client.get_client("sso-admin")

        # Resolve the permission set identifier to an ARN
        permission_set_arn = resolve_permission_set_identifier(
            sso_admin_client, instance_arn, identifier, identity_store_id
        )

        # Display a message indicating that we're updating the permission set
        console.print(f"[blue]Updating permission set '{identifier}'...[/blue]")

        # Check if we need to update the permission set attributes
        if any([description is not None, session_duration is not None, relay_state is not None]):
            # Prepare the update_permission_set API call parameters
            update_permission_set_params = {
                "InstanceArn": instance_arn,
                "PermissionSetArn": permission_set_arn,
            }

            # Add optional parameters if provided
            if description is not None:
                update_permission_set_params["Description"] = description

            if session_duration is not None:
                update_permission_set_params["SessionDuration"] = session_duration

            if relay_state is not None:
                update_permission_set_params["RelayState"] = relay_state

            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def update_permission_set_with_retry(params):
                return sso_admin_client.update_permission_set(**params)

            try:
                # Make the API call to update the permission set
                update_permission_set_with_retry(update_permission_set_params)

                # Log the successful update
                console.print("[green]Permission set attributes updated successfully.[/green]")

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

                # Log which attributes were updated
                if description is not None:
                    console.print(f"[green]Updated description: {description}[/green]")
                if session_duration is not None:
                    console.print(f"[green]Updated session duration: {session_duration}[/green]")
                if relay_state is not None:
                    console.print(f"[green]Updated relay state: {relay_state}[/green]")

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_message = e.response.get("Error", {}).get("Message", str(e))

                if error_code == "ResourceNotFoundException":
                    console.print(f"[red]Error: Permission set '{identifier}' not found.[/red]")
                    console.print(
                        "[yellow]Check the permission set name or ARN and try again.[/yellow]"
                    )
                    console.print(
                        "[yellow]Use 'awsideman permission-set list' to see all available permission sets.[/yellow]"
                    )
                else:
                    console.print(f"[red]Error: {error_code} - {error_message}[/red]")
                    console.print(
                        "[yellow]This could be due to insufficient permissions or an issue with the AWS Identity Center service.[/yellow]"
                    )

                raise typer.Exit(1)

        # Handle managed policy attachment and detachment
        attached_policies = []
        detached_policies = []

        # Attach managed policies if provided
        if add_managed_policy:
            console.print(f"[blue]Attaching {len(add_managed_policy)} managed policies...[/blue]")

            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def attach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn):
                return sso_admin_client.attach_managed_policy_to_permission_set(
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy_arn,
                )

            for policy_arn in add_managed_policy:
                try:
                    # Validate the policy ARN again (redundant but safe)
                    if not validate_aws_managed_policy_arn(policy_arn):
                        console.print(f"[yellow]Skipping invalid policy ARN: {policy_arn}[/yellow]")
                        continue

                    # Make the API call to attach the managed policy
                    attach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn)

                    # Extract the policy name from the ARN for display
                    policy_name = policy_arn.split("/")[-1]
                    console.print(f"[green]Attached policy: {policy_name}[/green]")

                    # Add the policy to the list of attached policies
                    attached_policies.append({"Name": policy_name, "Arn": policy_arn})

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    if error_code == "ConflictException":
                        console.print(
                            f"[yellow]Policy {policy_arn} is already attached to this permission set.[/yellow]"
                        )
                    else:
                        console.print(
                            f"[yellow]Warning: Failed to attach policy {policy_arn}: {error_code} - {error_message}[/yellow]"
                        )
                        console.print(
                            "[yellow]The permission set was updated but not all policies were attached.[/yellow]"
                        )

        # Detach managed policies if provided
        if remove_managed_policy:
            console.print(
                f"[blue]Detaching {len(remove_managed_policy)} managed policies...[/blue]"
            )

            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def detach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn):
                return sso_admin_client.detach_managed_policy_from_permission_set(
                    InstanceArn=instance_arn,
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy_arn,
                )

            for policy_arn in remove_managed_policy:
                try:
                    # Validate the policy ARN again (redundant but safe)
                    if not validate_aws_managed_policy_arn(policy_arn):
                        console.print(f"[yellow]Skipping invalid policy ARN: {policy_arn}[/yellow]")
                        continue

                    # Make the API call to detach the managed policy
                    detach_managed_policy_with_retry(instance_arn, permission_set_arn, policy_arn)

                    # Extract the policy name from the ARN for display
                    policy_name = policy_arn.split("/")[-1]
                    console.print(f"[green]Detached policy: {policy_name}[/green]")

                    # Add the policy to the list of detached policies
                    detached_policies.append({"Name": policy_name, "Arn": policy_arn})

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    if error_code == "ResourceNotFoundException":
                        console.print(
                            f"[yellow]Policy {policy_arn} is not attached to this permission set.[/yellow]"
                        )
                    else:
                        console.print(
                            f"[yellow]Warning: Failed to detach policy {policy_arn}: {error_code} - {error_message}[/yellow]"
                        )
                        console.print(
                            "[yellow]The permission set was updated but not all policies were detached.[/yellow]"
                        )

        # Get the updated permission set details to display
        try:
            # Use with_retry decorator to handle transient errors
            @with_retry(max_retries=3, delay=1.0)
            def get_permission_set_details(instance_arn, permission_set_arn):
                return sso_admin_client.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                )

            @with_retry(max_retries=3, delay=1.0)
            def get_managed_policies(instance_arn, permission_set_arn):
                return sso_admin_client.list_managed_policies_in_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=permission_set_arn
                )

            # Get permission set details with retry logic
            permission_set_response = get_permission_set_details(instance_arn, permission_set_arn)
            permission_set = permission_set_response.get("PermissionSet", {})

            # Store the ARN in the permission set object for reference
            permission_set["PermissionSetArn"] = permission_set_arn

            # Format the permission set data for display
            formatted_permission_set = format_permission_set_for_display(permission_set)

            # Get managed policies attached to the permission set
            managed_policies_response = get_managed_policies(instance_arn, permission_set_arn)
            managed_policies = managed_policies_response.get("AttachedManagedPolicies", [])

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
            if managed_policies:
                for policy in managed_policies:
                    policy_name = policy.get("Name", "N/A")
                    policy_arn = policy.get("Arn", "N/A")
                    policies_table.add_row(policy_name, policy_arn)
            else:
                policies_table.add_row("No managed policies attached", "")

            # Create a panel for the permission set details
            panel = Panel(
                details_table,
                title=f"Updated Permission Set: {permission_set.get('Name', 'Unknown')}",
                expand=False,
            )

            # Display the panel and policies table
            console.print("\n[green]Permission set updated successfully.[/green]")
            console.print(panel)
            console.print(policies_table)

            # Display a summary of changes
            if attached_policies or detached_policies:
                changes_table = Table(title="Policy Changes Summary", show_header=True)
                changes_table.add_column("Action", style="cyan")
                changes_table.add_column("Policy Name", style="green")
                changes_table.add_column("Policy ARN", style="blue")

                for policy in attached_policies:
                    changes_table.add_row(
                        "Attached", policy.get("Name", "N/A"), policy.get("Arn", "N/A")
                    )

                for policy in detached_policies:
                    changes_table.add_row(
                        "Detached", policy.get("Name", "N/A"), policy.get("Arn", "N/A")
                    )

                console.print(changes_table)

            return {
                "PermissionSet": permission_set,
                "AttachedManagedPolicies": managed_policies,
                "AttachedPolicies": attached_policies,
                "DetachedPolicies": detached_policies,
            }

        except ClientError as e:
            # Just log a warning if we can't get the details, but don't fail the command
            console.print(
                "[yellow]Warning: Could not retrieve full permission set details after update.[/yellow]"
            )
            console.print(
                f"[yellow]Error: {e.response.get('Error', {}).get('Code', 'Unknown')} - {e.response.get('Error', {}).get('Message', str(e))}[/yellow]"
            )
            console.print(
                "[yellow]The permission set was updated but the updated details could not be displayed.[/yellow]"
            )

            return {
                "PermissionSetArn": permission_set_arn,
                "AttachedPolicies": attached_policies,
                "DetachedPolicies": detached_policies,
            }

    except ClientError as e:
        # Handle AWS API errors with improved error messages and guidance
        handle_aws_error(e, operation="UpdatePermissionSet")
        raise typer.Exit(1)
    except (ConnectionError, EndpointConnectionError) as e:
        # Handle network-related errors
        handle_network_error(e)
        raise typer.Exit(1)
    except typer.Exit:
        # Re-raise typer.Exit without additional error messages
        raise
    except Exception as e:
        # Handle other unexpected errors
        console.print(f"[red]Error: {str(e)}[/red]")
        console.print(
            "[yellow]This is an unexpected error. Please report this issue if it persists.[/yellow]"
        )
        raise typer.Exit(1)
