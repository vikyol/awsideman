"""
CLI command for cloning permission sets.

This module provides the 'clone' command for cloning permission sets
with an intuitive --name and --to interface.
"""

from typing import Optional

import typer

from ..aws_clients.manager import AWSClientManager
from ..permission_cloning.permission_set_cloner import PermissionSetCloner
from ..permission_cloning.preview_generator import PreviewGenerator
from ..permission_cloning.rollback_integration import PermissionCloningRollbackIntegration
from ..rollback.processor import RollbackProcessor
from ..utils.config import Config

app = typer.Typer(help="Clone permission sets with all their policies and settings")


@app.callback(invoke_without_command=True)
def clone_permission_set(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Source permission set name to clone"),
    to: str = typer.Option(..., "--to", help="Target permission set name"),
    description: Optional[str] = typer.Option(
        None, "--description", help="Description for the new permission set"
    ),
    instance_arn: Optional[str] = typer.Option(
        None, "--instance-arn", help="SSO instance ARN (from config if not provided)"
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
    preview: bool = typer.Option(
        False, "--preview", help="Preview the operation without executing"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without making changes"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Clone a permission set with all its policies and settings."""
    try:
        # Get configuration
        config = Config()

        # Initialize AWS client manager and determine profile to use
        profile_to_use = profile or config.get("default_profile")
        if not profile_to_use:
            typer.echo("❌ Error: No profile specified and no default profile set.")
            typer.echo(
                "Use --profile option or set a default profile with 'awsideman profile set-default'."
            )
            raise typer.Exit(1)

        # If no instance ARN provided, try to discover it from the profile
        if not instance_arn:
            try:
                # CRITICAL FIX: Use profile-specific SSO instance instead of list_instances()
                # This prevents profile mixing and security vulnerabilities

                # Get SSO instance information from profile configuration
                profiles = config.get("profiles", {})
                if profile_to_use not in profiles:
                    typer.echo(f"❌ Error: Profile '{profile_to_use}' not found in configuration.")
                    raise typer.Exit(1)

                profile_data = profiles[profile_to_use]
                instance_arn = profile_data.get("sso_instance_arn")
                identity_store_id = profile_data.get("identity_store_id")

                if not instance_arn or not identity_store_id:
                    typer.echo(
                        f"❌ Error: No SSO instance configured for profile '{profile_to_use}'."
                    )
                    typer.echo(
                        "Use 'awsideman sso set <instance_arn> <identity_store_id>' to configure an SSO instance."
                    )
                    raise typer.Exit(1)

                typer.echo(f"🔍 Using configured SSO instance: {instance_arn}")
                typer.echo(f"🔍 Identity Store ID: {identity_store_id}")

            except Exception as e:
                typer.echo(f"❌ Error discovering SSO information: {e}")
                typer.echo(
                    "Please provide --instance-arn parameter or ensure AWS credentials are properly configured."
                )
                raise typer.Exit(1)

        # Initialize AWS client manager
        client_manager = AWSClientManager(profile=profile_to_use)

        if preview:
            # Generate preview
            preview_generator = PreviewGenerator(client_manager, instance_arn)

            preview_result = preview_generator.preview_permission_set_clone(
                source_permission_set_name=name,
                target_permission_set_name=to,
                target_description=description,
            )

            typer.echo("=== Permission Set Clone Preview ===")
            typer.echo(f"Source: {name}")
            typer.echo(f"Target: {to}")
            if description:
                typer.echo(f"Description: {description}")

            if preview_result["cloned_config"]:
                config = preview_result["cloned_config"]
                typer.echo("\nConfiguration to be cloned:")
                typer.echo(f"  - Session duration: {config.session_duration}")
                typer.echo(f"  - Relay state URL: {config.relay_state_url or 'None'}")
                typer.echo(f"  - AWS managed policies: {len(config.aws_managed_policies)}")
                if config.aws_managed_policies:
                    for policy in config.aws_managed_policies:
                        typer.echo(f"    • {policy}")
                typer.echo(
                    f"  - Customer managed policies: {len(config.customer_managed_policies)}"
                )
                if config.customer_managed_policies:
                    for policy in config.customer_managed_policies:
                        typer.echo(f"    • {policy.name}")
                typer.echo(f"  - Inline policy: {'Yes' if config.inline_policy else 'No'}")

            if preview_result["warnings"]:
                typer.echo("\nWarnings:")
                for warning in preview_result["warnings"]:
                    typer.echo(f"  ⚠️  {warning}")

        else:
            # Execute the clone operation
            permission_set_cloner = PermissionSetCloner(client_manager, instance_arn)

            clone_result = permission_set_cloner.clone_permission_set(
                source_name=name,
                target_name=to,
                target_description=description,
                preview=False,
            )

            if clone_result.success:
                typer.echo(f"✅ Successfully cloned permission set '{name}' to '{to}'")

                if clone_result.cloned_config:
                    config = clone_result.cloned_config
                    typer.echo("\nCloned configuration:")
                    typer.echo(f"  - Session duration: {config.session_duration}")
                    typer.echo(f"  - Relay state URL: {config.relay_state_url or 'None'}")
                    typer.echo(f"  - AWS managed policies: {len(config.aws_managed_policies)}")
                    if config.aws_managed_policies:
                        for policy in config.aws_managed_policies:
                            typer.echo(f"    • {policy}")
                    typer.echo(
                        f"  - Customer managed policies: {len(config.customer_managed_policies)}"
                    )
                    if config.customer_managed_policies:
                        for policy in config.customer_managed_policies:
                            typer.echo(f"    • {policy.name}")
                    typer.echo(f"  - Inline policy: {'Yes' if config.inline_policy else 'No'}")

                # Track operation for rollback if not dry run
                if not dry_run:
                    try:
                        rollback_processor = RollbackProcessor()
                        rollback_integration = PermissionCloningRollbackIntegration(
                            client_manager, rollback_processor
                        )

                        # Get the ARNs from the clone result
                        source_arn = clone_result.source_arn or ""
                        target_arn = clone_result.target_arn or ""

                        operation_id = rollback_integration.track_permission_set_clone_operation(
                            source_permission_set_name=name,
                            source_permission_set_arn=source_arn,
                            target_permission_set_name=to,
                            target_permission_set_arn=target_arn,
                            clone_result=clone_result,
                        )

                        typer.echo(f"\n📝 Operation tracked for rollback: {operation_id}")
                        typer.echo(f"To rollback: awsideman rollback apply {operation_id}")

                    except Exception as e:
                        typer.echo(f"⚠️  Warning: Failed to track operation for rollback: {str(e)}")
            else:
                typer.echo(f"❌ Failed to clone permission set: {clone_result.error_message}")
                raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)
