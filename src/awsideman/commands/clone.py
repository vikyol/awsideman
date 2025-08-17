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
        if not instance_arn:
            instance_arn = config.get_instance_arn()

        if not instance_arn:
            typer.echo("❌ Error: SSO instance ARN is required")
            typer.echo("Provide it via --instance-arn or configure it in your settings")
            raise typer.Exit(1)

        # Initialize AWS client manager
        client_manager = AWSClientManager()

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
                dry_run=dry_run,
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

                        operation_id = rollback_integration.track_permission_set_clone_operation(
                            source_permission_set_name=name,
                            source_permission_set_arn=(
                                clone_result.cloned_config.arn
                                if hasattr(clone_result.cloned_config, "arn")
                                else ""
                            ),
                            target_permission_set_name=to,
                            target_permission_set_arn=(
                                clone_result.cloned_config.arn
                                if hasattr(clone_result.cloned_config, "arn")
                                else ""
                            ),
                            clone_result=clone_result,
                        )

                        typer.echo(f"\n📝 Operation tracked for rollback: {operation_id}")
                        typer.echo(f"To rollback: awsideman rollback {operation_id}")

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
