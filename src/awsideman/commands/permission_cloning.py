"""
CLI commands for permission cloning operations.

This module provides command-line interface for:
- Copying permission assignments between entities
- Cloning permission sets
- Rolling back cloning operations
"""

from typing import Optional

import typer

from ..aws_clients.manager import AWSClientManager
from ..permission_cloning.assignment_copier import AssignmentCopier
from ..permission_cloning.models import CopyFilters, EntityType
from ..permission_cloning.permission_set_cloner import PermissionSetCloner
from ..permission_cloning.preview_generator import PreviewGenerator
from ..permission_cloning.rollback_integration import PermissionCloningRollbackIntegration
from ..rollback.processor import RollbackProcessor

app = typer.Typer(
    help="Permission cloning operations. Copy assignments between entities and clone permission sets."
)


@app.command("copy-assignments")
def copy_assignments(
    source_entity_id: str = typer.Option(
        ..., "--source-entity-id", help="Source entity ID (user or group)"
    ),
    source_entity_type: str = typer.Option(
        ..., "--source-entity-type", help="Source entity type", case_sensitive=False
    ),
    target_entity_id: str = typer.Option(
        ..., "--target-entity-id", help="Target entity ID (user or group)"
    ),
    target_entity_type: str = typer.Option(
        ..., "--target-entity-type", help="Target entity type", case_sensitive=False
    ),
    instance_arn: str = typer.Option(..., "--instance-arn", help="SSO instance ARN"),
    identity_store_id: str = typer.Option(..., "--identity-store-id", help="Identity store ID"),
    account_filter: Optional[str] = typer.Option(
        None, "--account-filter", help="Comma-separated list of account IDs to filter"
    ),
    permission_set_filter: Optional[str] = typer.Option(
        None,
        "--permission-set-filter",
        help="Comma-separated list of permission set names to filter",
    ),
    preview: bool = typer.Option(
        False, "--preview", help="Preview the operation without executing"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without making changes"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Copy permission assignments from source entity to target entity."""
    try:
        # Initialize AWS client manager
        client_manager = AWSClientManager()

        # Parse filters
        copy_filters = None
        if account_filter or permission_set_filter:
            copy_filters = CopyFilters(
                account_ids=account_filter.split(",") if account_filter else None,
                permission_set_names=(
                    permission_set_filter.split(",") if permission_set_filter else None
                ),
            )

        if preview:
            # Generate preview
            preview_generator = PreviewGenerator(client_manager, instance_arn, identity_store_id)

            preview_result = preview_generator.preview_assignment_copy(
                source_entity_id=source_entity_id,
                source_entity_type=source_entity_type,
                target_entity_id=target_entity_id,
                target_entity_type=target_entity_type,
                filters=copy_filters,
            )

            typer.echo("=== Assignment Copy Preview ===")
            typer.echo(f"Source: {source_entity_type} {source_entity_id}")
            typer.echo(f"Target: {target_entity_type} {target_entity_id}")
            typer.echo(
                f"Total source assignments: {preview_result['copy_summary']['total_source_assignments']}"
            )
            typer.echo(
                f"Assignments to copy: {preview_result['copy_summary']['assignments_to_copy']}"
            )
            typer.echo(
                f"Duplicate assignments: {preview_result['copy_summary']['duplicate_assignments']}"
            )
            typer.echo(
                f"Conflicting assignments: {preview_result['copy_summary']['conflicting_assignments']}"
            )

            if preview_result["copy_summary"]["assignments_to_copy"] > 0:
                typer.echo("\nAssignments to be copied:")
                for assignment in preview_result["assignments_to_copy"]:
                    typer.echo(
                        f"  - {assignment['permission_set_name']} in account {assignment['account_name']}"
                    )

            if preview_result["warnings"]:
                typer.echo("\nWarnings:")
                for warning in preview_result["warnings"]:
                    typer.echo(f"  ⚠️  {warning}")

        else:
            # Execute the copy operation
            assignment_copier = AssignmentCopier(client_manager, instance_arn, identity_store_id)

            copy_result = assignment_copier.copy_assignments(
                source_entity_id=source_entity_id,
                source_entity_type=EntityType(source_entity_type),
                target_entity_id=target_entity_id,
                target_entity_type=EntityType(target_entity_type),
                filters=copy_filters,
                dry_run=dry_run,
            )

            if copy_result.success:
                typer.echo(
                    f"✅ Successfully copied {len(copy_result.assignments_copied)} assignments"
                )

                if copy_result.assignments_copied:
                    typer.echo("\nCopied assignments:")
                    for assignment in copy_result.assignments_copied:
                        typer.echo(
                            f"  - {assignment.permission_set_name} in account {assignment.account_name}"
                        )

                if copy_result.assignments_skipped:
                    typer.echo(f"\nSkipped {len(copy_result.assignments_skipped)} assignments")
                    for assignment in copy_result.assignments_skipped:
                        typer.echo(
                            f"  - {assignment.permission_set_name} in account {assignment.account_name}"
                        )

                # Track operation for rollback if not dry run
                if not dry_run:
                    try:
                        rollback_processor = RollbackProcessor()
                        rollback_integration = PermissionCloningRollbackIntegration(
                            client_manager, rollback_processor
                        )

                        operation_id = rollback_integration.track_assignment_copy_operation(
                            source_entity=copy_result.source,
                            target_entity=copy_result.target,
                            assignments_copied=copy_result.assignments_copied,
                            copy_result=copy_result,
                        )

                        typer.echo(f"\n📝 Operation tracked for rollback: {operation_id}")
                        typer.echo(
                            f"To rollback: awsideman permission-cloning rollback-assignment-copy {operation_id}"
                        )

                    except Exception as e:
                        typer.echo(f"⚠️  Warning: Failed to track operation for rollback: {str(e)}")
            else:
                typer.echo(f"❌ Failed to copy assignments: {copy_result.error_message}")
                raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)


@app.command("clone-permission-set")
def clone_permission_set(
    source_name: str = typer.Option(..., "--source-name", help="Source permission set name"),
    target_name: str = typer.Option(..., "--target-name", help="Target permission set name"),
    target_description: Optional[str] = typer.Option(
        None, "--target-description", help="Description for the target permission set"
    ),
    instance_arn: str = typer.Option(..., "--instance-arn", help="SSO instance ARN"),
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
        # Initialize AWS client manager
        client_manager = AWSClientManager()

        if preview:
            # Generate preview
            preview_generator = PreviewGenerator(client_manager, instance_arn)

            preview_result = preview_generator.preview_permission_set_clone(
                source_permission_set_name=source_name,
                target_permission_set_name=target_name,
                target_description=target_description,
            )

            typer.echo("=== Permission Set Clone Preview ===")
            typer.echo(f"Source: {source_name}")
            typer.echo(f"Target: {target_name}")
            if target_description:
                typer.echo(f"Description: {target_description}")

            if preview_result["cloned_config"]:
                config = preview_result["cloned_config"]
                typer.echo("\nConfiguration to be cloned:")
                typer.echo(f"  - Session duration: {config.session_duration}")
                typer.echo(f"  - Relay state URL: {config.relay_state_url or 'None'}")
                typer.echo(f"  - AWS managed policies: {len(config.aws_managed_policies)}")
                typer.echo(
                    f"  - Customer managed policies: {len(config.customer_managed_policies)}"
                )
                typer.echo(f"  - Inline policy: {'Yes' if config.inline_policy else 'No'}")

            if preview_result["warnings"]:
                typer.echo("\nWarnings:")
                for warning in preview_result["warnings"]:
                    typer.echo(f"  ⚠️  {warning}")

        else:
            # Execute the clone operation
            permission_set_cloner = PermissionSetCloner(client_manager, instance_arn)

            clone_result = permission_set_cloner.clone_permission_set(
                source_name=source_name,
                target_name=target_name,
                target_description=target_description,
                preview=False,
                dry_run=dry_run,
            )

            if clone_result.success:
                typer.echo(
                    f"✅ Successfully cloned permission set '{source_name}' to '{target_name}'"
                )

                if clone_result.cloned_config:
                    config = clone_result.cloned_config
                    typer.echo("\nCloned configuration:")
                    typer.echo(f"  - Session duration: {config.session_duration}")
                    typer.echo(f"  - Relay state URL: {config.relay_state_url or 'None'}")
                    typer.echo(f"  - AWS managed policies: {len(config.aws_managed_policies)}")
                    typer.echo(
                        f"  - Customer managed policies: {len(config.customer_managed_policies)}"
                    )
                    typer.echo(f"  - Inline policy: {'Yes' if config.inline_policy else 'No'}")

                # Track operation for rollback if not dry run
                if not dry_run:
                    try:
                        rollback_processor = RollbackProcessor()
                        rollback_integration = PermissionCloningRollbackIntegration(
                            client_manager, rollback_processor
                        )

                        operation_id = rollback_integration.track_permission_set_clone_operation(
                            source_permission_set_name=source_name,
                            source_permission_set_arn=(
                                clone_result.cloned_config.arn
                                if hasattr(clone_result.cloned_config, "arn")
                                else ""
                            ),
                            target_permission_set_name=target_name,
                            target_permission_set_arn=(
                                clone_result.cloned_config.arn
                                if hasattr(clone_result.cloned_config, "arn")
                                else ""
                            ),
                            clone_result=clone_result,
                        )

                        typer.echo(f"\n📝 Operation tracked for rollback: {operation_id}")
                        typer.echo(
                            f"To rollback: awsideman permission-cloning rollback-permission-set-clone {operation_id}"
                        )

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


@app.command("rollback-assignment-copy")
def rollback_assignment_copy(
    operation_id: str = typer.Option(..., "--operation-id", help="Operation ID to rollback"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Rollback an assignment copy operation."""
    try:
        # Initialize AWS client manager and rollback processor
        client_manager = AWSClientManager()
        rollback_processor = RollbackProcessor()
        rollback_integration = PermissionCloningRollbackIntegration(
            client_manager, rollback_processor
        )

        typer.echo(f"🔄 Rolling back assignment copy operation: {operation_id}")

        result = rollback_integration.rollback_assignment_copy_operation(operation_id)

        if result["success"]:
            typer.echo(f"✅ Successfully rolled back operation {operation_id}")
            typer.echo(f"  - Successful actions: {result['success_count']}")
            typer.echo(f"  - Failed actions: {result['failure_count']}")
            typer.echo(f"  - Total actions: {result['total_actions']}")

            if result["errors"]:
                typer.echo("\nErrors encountered:")
                for error in result["errors"]:
                    typer.echo(f"  ❌ {error}")
        else:
            typer.echo(f"❌ Failed to rollback operation {operation_id}")
            if result["errors"]:
                for error in result["errors"]:
                    typer.echo(f"  ❌ {error}")
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)


@app.command("rollback-permission-set-clone")
def rollback_permission_set_clone(
    operation_id: str = typer.Option(..., "--operation-id", help="Operation ID to rollback"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Rollback a permission set clone operation."""
    try:
        # Initialize AWS client manager and rollback processor
        client_manager = AWSClientManager()
        rollback_processor = RollbackProcessor()
        rollback_integration = PermissionCloningRollbackIntegration(
            client_manager, rollback_processor
        )

        typer.echo(f"🔄 Rolling back permission set clone operation: {operation_id}")

        result = rollback_integration.rollback_permission_set_clone_operation(operation_id)

        if result["success"]:
            typer.echo(f"✅ Successfully rolled back operation {operation_id}")
            typer.echo(f"  - Deleted permission set: {result['permission_set_deleted']}")
            typer.echo(f"  - Permission set ARN: {result['permission_set_arn']}")
        else:
            typer.echo(f"❌ Failed to rollback operation {operation_id}")
            typer.echo(f"  - Error: {result['error']}")
            raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)


@app.command("list-rollbackable")
def list_rollbackable_operations(
    operation_type: Optional[str] = typer.Option(
        None,
        "--operation-type",
        help="Filter by operation type (copy_assignments or clone_permission_set)",
    ),
    entity_id: Optional[str] = typer.Option(
        None, "--entity-id", help="Filter by entity ID (source or target)"
    ),
    days: Optional[int] = typer.Option(
        None, "--days", help="Filter by operations within last N days"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """List operations that can be rolled back."""
    try:
        # Initialize AWS client manager and rollback processor
        client_manager = AWSClientManager()
        rollback_processor = RollbackProcessor()
        rollback_integration = PermissionCloningRollbackIntegration(
            client_manager, rollback_processor
        )

        # Convert operation type string to enum if provided
        op_type_enum = None
        if operation_type:
            if operation_type == "copy_assignments":
                from ..rollback.models import OperationType

                op_type_enum = OperationType.COPY_ASSIGNMENTS
            elif operation_type == "clone_permission_set":
                from ..rollback.models import OperationType

                op_type_enum = OperationType.CLONE_PERMISSION_SET

        operations = rollback_integration.get_rollbackable_operations(
            operation_type=op_type_enum, entity_id=entity_id, days=days
        )

        if not operations:
            typer.echo("No rollbackable operations found.")
            return

        typer.echo(f"Found {len(operations)} rollbackable operations:")
        typer.echo()

        for i, op in enumerate(operations, 1):
            typer.echo(f"{i}. Operation ID: {op['operation_id']}")

            if "source_entity_id" in op:
                # Permission cloning operation
                typer.echo("   Type: Assignment Copy")
                typer.echo(
                    f"   Source: {op['source_entity_type']} {op['source_entity_name']} ({op['source_entity_id']})"
                )
                typer.echo(
                    f"   Target: {op['target_entity_type']} {op['target_entity_name']} ({op['target_entity_id']})"
                )
                typer.echo(f"   Assignments: {len(op['assignments_copied'])}")
                typer.echo(f"   Accounts: {len(op['accounts_affected'])}")
                typer.echo(
                    f"   Rollback: awsideman permission-cloning rollback-assignment-copy {op['operation_id']}"
                )
            elif "source_permission_set_name" in op:
                # Permission set cloning operation
                typer.echo("   Type: Permission Set Clone")
                typer.echo(f"   Source: {op['source_permission_set_name']}")
                typer.echo(f"   Target: {op['target_permission_set_name']}")
                typer.echo(
                    f"   Rollback: awsideman permission-cloning rollback-permission-set-clone {op['operation_id']}"
                )

            typer.echo(f"   Timestamp: {op['timestamp']}")
            typer.echo()

    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise typer.Exit(1)
