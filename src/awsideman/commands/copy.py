"""
CLI command for copying permission assignments between entities.

This module provides the 'copy' command for copying permission assignments
between users and groups with an intuitive --from and --to interface.
"""

from typing import Optional

import typer

from ..aws_clients.manager import AWSClientManager
from ..permission_cloning.assignment_copier import AssignmentCopier
from ..permission_cloning.models import CopyFilters, EntityType
from ..permission_cloning.optimized_assignment_copier import OptimizedAssignmentCopier
from ..permission_cloning.performance import BatchConfig, RateLimitConfig
from ..permission_cloning.preview_generator import PreviewGenerator
from ..permission_cloning.rollback_integration import PermissionCloningRollbackIntegration
from ..rollback.processor import RollbackProcessor
from ..utils.config import Config

app = typer.Typer(help="Copy permission assignments between users and groups")


def parse_entity_reference(entity_ref: str) -> tuple[str, str]:
    """Parse entity reference in format 'type:name' into type and name."""
    if ":" not in entity_ref:
        raise typer.BadParameter(
            f"Entity reference must be in format 'user:name' or 'group:name', got: {entity_ref}"
        )

    entity_type, entity_name = entity_ref.split(":", 1)

    if entity_type.lower() not in ["user", "group"]:
        raise typer.BadParameter(f"Entity type must be 'user' or 'group', got: {entity_type}")

    return entity_type.lower(), entity_name


@app.callback(invoke_without_command=True)
def copy_assignments(
    ctx: typer.Context,
    from_entity: str = typer.Option(
        ..., "--from", help="Source entity in format 'user:name' or 'group:name'"
    ),
    to_entity: str = typer.Option(
        ..., "--to", help="Target entity in format 'user:name' or 'group:name'"
    ),
    instance_arn: Optional[str] = typer.Option(
        None, "--instance-arn", help="SSO instance ARN (from config if not provided)"
    ),
    identity_store_id: Optional[str] = typer.Option(
        None, "--identity-store-id", help="Identity store ID (from config if not provided)"
    ),
    exclude_permission_sets: Optional[str] = typer.Option(
        None,
        "--exclude-permission-sets",
        help="Comma-separated list of permission set names to exclude (e.g., AdminAccess,BillingAccess)",
    ),
    include_accounts: Optional[str] = typer.Option(
        None, "--include-accounts", help="Comma-separated list of account IDs to include"
    ),
    exclude_accounts: Optional[str] = typer.Option(
        None, "--exclude-accounts", help="Comma-separated list of account IDs to exclude"
    ),
    preview: bool = typer.Option(
        False, "--preview", help="Preview the operation without executing"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without making changes"
    ),
    optimized: bool = typer.Option(
        True,
        "--optimized/--no-optimized",
        help="Use performance optimizations (parallel processing, caching, rate limiting)",
    ),
    batch_size: int = typer.Option(10, "--batch-size", help="Batch size for parallel processing"),
    max_workers: int = typer.Option(5, "--max-workers", help="Maximum number of parallel workers"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: Optional[str] = typer.Option(None, "--profile", help="AWS profile to use"),
):
    """Copy permission assignments from source entity to target entity."""
    try:
        # Parse entity references
        source_type, source_name = parse_entity_reference(from_entity)
        target_type, target_name = parse_entity_reference(to_entity)

        # Get configuration
        config = Config()

        # Discover SSO instance ARN and identity store ID if not provided
        if not instance_arn or not identity_store_id:
            try:
                # Initialize AWS client manager to discover SSO information
                # Use provided profile or awsideman default profile
                profile_to_use = profile or config.get("default_profile")
                if not profile_to_use:
                    typer.echo("❌ Error: No profile specified and no default profile set.")
                    typer.echo(
                        "Use --profile option or set a default profile with 'awsideman profile set-default'."
                    )
                    raise typer.Exit(1)

                aws_client = AWSClientManager(profile=profile_to_use)
                sso_client = aws_client.get_identity_center_client()

                # Get SSO instance information
                instances = sso_client.list_instances()
                if not instances.get("Instances"):
                    typer.echo(
                        "❌ Error: No SSO instances found. Cannot proceed with copy operation."
                    )
                    raise typer.Exit(1)

                if not instance_arn:
                    instance_arn = instances["Instances"][0]["InstanceArn"]
                    typer.echo(f"🔍 Discovered SSO instance: {instance_arn}")

                if not identity_store_id:
                    identity_store_id = instances["Instances"][0]["IdentityStoreId"]
                    typer.echo(f"🔍 Discovered identity store ID: {identity_store_id}")

            except Exception as e:
                typer.echo(f"❌ Error discovering SSO information: {e}")
                typer.echo(
                    "Please provide --instance-arn and --identity-store-id parameters or ensure AWS credentials are properly configured."
                )
                raise typer.Exit(1)

        # Initialize AWS client manager
        # Use provided profile or awsideman default profile
        profile_to_use = profile or config.get("default_profile")
        if not profile_to_use:
            typer.echo("❌ Error: No profile specified and no default profile set.")
            typer.echo(
                "Use --profile option or set a default profile with 'awsideman profile set-default'."
            )
            raise typer.Exit(1)

        client_manager = AWSClientManager(profile=profile_to_use)

        # Parse filters
        copy_filters = CopyFilters(
            exclude_permission_sets=(
                exclude_permission_sets.split(",") if exclude_permission_sets else None
            ),
            include_accounts=include_accounts.split(",") if include_accounts else None,
            exclude_accounts=exclude_accounts.split(",") if exclude_accounts else None,
        )

        # Debug: Print filter information
        if verbose:
            typer.echo(f"🔍 Filters: {copy_filters}")
            typer.echo(f"🔍 Filter type: {type(copy_filters)}")

        if preview:
            # Generate preview
            preview_generator = PreviewGenerator(client_manager, instance_arn, identity_store_id)

            preview_result = preview_generator.preview_assignment_copy_by_name(
                source_entity_type=source_type,
                source_entity_name=source_name,
                target_entity_type=target_type,
                target_entity_name=target_name,
                filters=copy_filters,
            )

            typer.echo("=== Assignment Copy Preview ===")
            typer.echo(f"Source: {source_type} '{source_name}'")
            typer.echo(f"Target: {target_type} '{target_name}'")
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
                for assignment in preview_result["assignments"]["new"]:
                    typer.echo(
                        f"  - {assignment.permission_set_name} in account {assignment.account_name}"
                    )

            if preview_result["warnings"]:
                typer.echo("\nWarnings:")
                for warning in preview_result["warnings"]:
                    typer.echo(f"  ⚠️  {warning}")

        else:
            # Initialize dependencies
            from ..permission_cloning.assignment_retriever import AssignmentRetriever
            from ..permission_cloning.entity_resolver import EntityResolver
            from ..permission_cloning.filter_engine import FilterEngine

            entity_resolver = EntityResolver(client_manager, identity_store_id)
            assignment_retriever = AssignmentRetriever(
                client_manager, instance_arn, identity_store_id
            )
            filter_engine = FilterEngine()

            # Execute the copy operation
            if optimized:
                # Use optimized assignment copier with performance enhancements
                rate_limit_config = RateLimitConfig()
                batch_config = BatchConfig(
                    assignment_copy_batch_size=batch_size, max_workers=max_workers
                )

                assignment_copier = OptimizedAssignmentCopier(
                    entity_resolver=entity_resolver,
                    assignment_retriever=assignment_retriever,
                    filter_engine=filter_engine,
                    rate_limit_config=rate_limit_config,
                    batch_config=batch_config,
                )

                # Resolve entities first
                source_entity = entity_resolver.resolve_entity_by_name(
                    EntityType.USER if source_type == "user" else EntityType.GROUP, source_name
                )
                target_entity = entity_resolver.resolve_entity_by_name(
                    EntityType.USER if target_type == "user" else EntityType.GROUP, target_name
                )

                if not source_entity:
                    typer.echo(f"❌ Error: Source {source_type} '{source_name}' not found")
                    raise typer.Exit(1)

                if not target_entity:
                    typer.echo(f"❌ Error: Target {target_type} '{target_name}' not found")
                    raise typer.Exit(1)

                copy_result = assignment_copier.copy_assignments(
                    source=source_entity,
                    target=target_entity,
                    filters=copy_filters,
                    preview=dry_run,
                )
            else:
                # Use standard assignment copier
                assignment_copier = AssignmentCopier(
                    entity_resolver, assignment_retriever, filter_engine
                )

                copy_result = assignment_copier.copy_assignments_by_name(
                    source_entity_type=source_type,
                    source_entity_name=source_name,
                    target_entity_type=target_type,
                    target_entity_name=target_name,
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
                    typer.echo(
                        f"\nSkipped {len(copy_result.assignments_skipped)} assignments (already exist):"
                    )
                    for assignment in copy_result.assignments_skipped:
                        typer.echo(
                            f"  - {assignment.permission_set_name} in account {assignment.account_name}"
                        )

                # Display performance metrics if available
                if (
                    optimized
                    and hasattr(copy_result, "performance_metrics")
                    and copy_result.performance_metrics
                ):
                    metrics = copy_result.performance_metrics
                    typer.echo("\n📊 Performance Metrics:")

                    if metrics.get("duration_ms"):
                        duration_sec = metrics["duration_ms"] / 1000
                        typer.echo(f"  Duration: {duration_sec:.2f} seconds")

                    if metrics.get("assignments_per_second"):
                        typer.echo(
                            f"  Throughput: {metrics['assignments_per_second']:.2f} assignments/second"
                        )

                    if metrics.get("success_rate"):
                        typer.echo(f"  Success Rate: {metrics['success_rate']:.1f}%")

                    if metrics.get("api_calls") and metrics.get("cached_lookups"):
                        total_lookups = metrics["api_calls"] + metrics["cached_lookups"]
                        cache_hit_rate = (
                            (metrics["cached_lookups"] / total_lookups) * 100
                            if total_lookups > 0
                            else 0
                        )
                        typer.echo(
                            f"  Cache Hit Rate: {cache_hit_rate:.1f}% ({metrics['cached_lookups']}/{total_lookups})"
                        )

                    if metrics.get("rate_limit_delays_ms") and metrics.get("duration_ms"):
                        delay_percentage = (
                            metrics["rate_limit_delays_ms"] / metrics["duration_ms"]
                        ) * 100
                        typer.echo(f"  Rate Limit Impact: {delay_percentage:.1f}% of total time")

                    if metrics.get("retry_attempts"):
                        typer.echo(f"  Retry Attempts: {metrics['retry_attempts']}")

                    if verbose and optimized:
                        # Show optimization recommendations
                        from ..permission_cloning.performance import PerformanceMetrics

                        perf_metrics = PerformanceMetrics(
                            operation_id="display",
                            start_time=0,
                            total_assignments=len(copy_result.assignments_copied)
                            + len(copy_result.assignments_skipped),
                            processed_assignments=len(copy_result.assignments_copied),
                            api_calls=metrics.get("api_calls", 0),
                            cached_lookups=metrics.get("cached_lookups", 0),
                            retry_attempts=metrics.get("retry_attempts", 0),
                        )
                        perf_metrics.end_time = perf_metrics.start_time + (
                            metrics.get("duration_ms", 0) / 1000
                        )

                        optimizer = assignment_copier.performance_optimizer
                        recommendations = optimizer.get_optimization_recommendations(perf_metrics)

                        if recommendations:
                            typer.echo("\n💡 Optimization Recommendations:")
                            for rec in recommendations:
                                typer.echo(f"  - {rec}")

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
                        typer.echo(f"To rollback: awsideman rollback apply {operation_id}")

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
