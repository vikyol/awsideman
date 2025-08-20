"""
Optimized assignment copier with performance enhancements.

This module provides an optimized version of the assignment copier that uses:
- Parallel processing for multiple assignment operations
- Rate limiting to respect AWS API constraints
- Optimized caching strategy for entity and permission set lookups
- Streaming processing for large assignment lists
"""

import logging
from typing import List, Optional, Tuple
from uuid import uuid4

from .assignment_retriever import AssignmentRetriever
from .entity_resolver import EntityResolver
from .filter_engine import FilterEngine
from .models import (
    CopyFilters,
    CopyResult,
    EntityReference,
    EntityType,
    PermissionAssignment,
    ValidationResult,
)
from .performance import BatchConfig, PerformanceMetrics, PerformanceOptimizer, RateLimitConfig

logger = logging.getLogger(__name__)


class OptimizedAssignmentCopier:
    """
    Optimized assignment copier with performance enhancements.

    This class provides the same functionality as AssignmentCopier but with:
    - Parallel processing for better throughput
    - Rate limiting to avoid AWS API throttling
    - Optimized caching for reduced API calls
    - Streaming processing for large operations
    - Performance monitoring and metrics
    """

    def __init__(
        self,
        entity_resolver: EntityResolver,
        assignment_retriever: AssignmentRetriever,
        filter_engine: FilterEngine,
        rate_limit_config: Optional[RateLimitConfig] = None,
        batch_config: Optional[BatchConfig] = None,
        cache_size: int = 10000,
    ):
        """
        Initialize the OptimizedAssignmentCopier.

        Args:
            entity_resolver: Entity resolver for validation
            assignment_retriever: Assignment retriever for fetching assignments
            filter_engine: Filter engine for filtering assignments
            rate_limit_config: Rate limiting configuration
            batch_config: Batch processing configuration
            cache_size: Maximum cache size
        """
        self.entity_resolver = entity_resolver
        self.assignment_retriever = assignment_retriever
        self.filter_engine = filter_engine

        # Initialize performance optimizer
        self.performance_optimizer = PerformanceOptimizer(
            rate_limit_config=rate_limit_config, batch_config=batch_config, cache_size=cache_size
        )

    def copy_assignments(
        self,
        source: EntityReference,
        target: EntityReference,
        filters: Optional[CopyFilters] = None,
        preview: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> CopyResult:
        """
        Copy permission assignments from source entity to target entity with optimizations.

        Args:
            source: Source entity (user or group)
            target: Target entity (user or group)
            filters: Optional filters to apply to assignments
            preview: If True, only preview the operation without executing
            progress_callback: Optional callback for progress updates (current, total)

        Returns:
            CopyResult with details of the operation and performance metrics
        """
        # Start performance tracking
        operation_id = self.performance_optimizer.start_operation_metrics()
        metrics = self.performance_optimizer.get_operation_metrics(operation_id)

        logger.info(
            f"Starting optimized assignment copy from {source.entity_type.value} '{source.entity_name}' "
            f"to {target.entity_type.value} '{target.entity_name}' (operation_id: {operation_id})"
        )

        try:
            # Validate entities before proceeding
            validation_result = self.validate_entities(source, target)
            if validation_result.has_errors:
                logger.error(f"Entity validation failed: {validation_result.messages}")
                return self._create_error_result(
                    source, target, "; ".join(validation_result.messages), operation_id
                )

            # Warm cache with entities
            self.performance_optimizer.warm_cache([source, target])

            # Get source assignments with caching
            source_assignments = self._get_source_assignments_optimized(source, metrics)
            if not source_assignments:
                logger.info(
                    f"No assignments found for source {source.entity_type.value} '{source.entity_name}'"
                )
                return self._create_success_result(source, target, [], [], None, operation_id)

            metrics.total_assignments = len(source_assignments)

            # Apply filters if specified
            if filters:
                logger.info(f"Applying filters: {self.filter_engine.get_filter_summary(filters)}")
                source_assignments = self.filter_engine.apply_filters(source_assignments, filters)
                if not source_assignments:
                    logger.info("No assignments match the specified filters")
                    return self._create_success_result(source, target, [], [], None, operation_id)

                metrics.total_assignments = len(source_assignments)

            # Get target assignments for duplicate detection
            target_assignments = self._get_source_assignments_optimized(target, metrics)

            # Identify assignments to copy and skip
            assignments_to_copy, assignments_to_skip = self._identify_assignments_to_copy(
                source_assignments, target_assignments
            )

            if preview:
                logger.info("Preview mode - no assignments will be copied")
                return self._create_success_result(
                    source, target, assignments_to_copy, assignments_to_skip, None, operation_id
                )

            # Generate rollback ID for this operation
            rollback_id = str(uuid4())
            logger.info(f"Generated rollback ID: {rollback_id}")

            # Execute the copy operation with optimizations
            copied_assignments = self._execute_copy_operation_optimized(
                target, assignments_to_copy, rollback_id, metrics, progress_callback
            )

            # Prepare result
            result = self._create_success_result(
                source, target, copied_assignments, assignments_to_skip, rollback_id, operation_id
            )

            logger.info(
                f"Successfully copied {len(copied_assignments)} assignments, "
                f"skipped {len(assignments_to_skip)} duplicates"
            )

            return result

        except Exception as e:
            logger.error(f"Error during optimized assignment copy: {str(e)}", exc_info=True)
            return self._create_error_result(
                source, target, f"Copy operation failed: {str(e)}", operation_id
            )

    def copy_assignments_batch(
        self,
        copy_requests: List[Tuple[EntityReference, EntityReference, Optional[CopyFilters]]],
        preview: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> List[CopyResult]:
        """
        Copy assignments for multiple source-target pairs in an optimized batch.

        Args:
            copy_requests: List of (source, target, filters) tuples
            preview: If True, only preview operations without executing
            progress_callback: Optional callback for progress updates

        Returns:
            List of CopyResult objects for each request
        """
        logger.info(f"Starting batch copy operation for {len(copy_requests)} requests")

        # Start performance tracking
        operation_id = self.performance_optimizer.start_operation_metrics()

        # Warm cache with all entities
        all_entities = []
        for source, target, _ in copy_requests:
            all_entities.extend([source, target])
        self.performance_optimizer.warm_cache(all_entities)

        results = []

        # Process each request
        for i, (source, target, filters) in enumerate(copy_requests):
            try:
                result = self.copy_assignments(
                    source=source, target=target, filters=filters, preview=preview
                )
                results.append(result)

                # Update progress
                if progress_callback:
                    progress_callback(i + 1, len(copy_requests))

            except Exception as e:
                logger.error(f"Error in batch copy request {i}: {str(e)}")
                error_result = self._create_error_result(
                    source, target, f"Batch copy failed: {str(e)}", operation_id
                )
                results.append(error_result)

        # Finish performance tracking
        self.performance_optimizer.finish_operation_metrics(operation_id)

        logger.info(f"Completed batch copy operation: {len(results)} results")
        return results

    def validate_entities(
        self, source: EntityReference, target: EntityReference
    ) -> ValidationResult:
        """
        Validate that both source and target entities exist and are accessible.

        Args:
            source: Source entity to validate
            target: Target entity to validate

        Returns:
            ValidationResult indicating success or failure
        """
        errors = []

        # Validate source entity
        source_validation = self.entity_resolver.validate_entity(source)
        if source_validation.has_errors:
            errors.extend(
                [f"Source {source.entity_type.value}: {msg}" for msg in source_validation.messages]
            )

        # Validate target entity
        target_validation = self.entity_resolver.validate_entity(target)
        if target_validation.has_errors:
            errors.extend(
                [f"Target {target.entity_type.value}: {msg}" for msg in target_validation.messages]
            )

        # Check if source and target are the same entity
        if source.entity_type == target.entity_type and source.entity_id == target.entity_id:
            errors.append("Source and target entities cannot be the same")

        if errors:
            return ValidationResult(result_type="ERROR", messages=errors)

        return ValidationResult(result_type="SUCCESS", messages=[])

    def get_performance_stats(self) -> dict:
        """Get performance statistics."""
        return {
            "cache_stats": self.performance_optimizer.get_cache_stats(),
            "active_operations": len(self.performance_optimizer._active_metrics),
        }

    def clear_cache(self) -> None:
        """Clear performance cache."""
        self.performance_optimizer.clear_cache()

    def _get_source_assignments_optimized(
        self, entity: EntityReference, metrics: PerformanceMetrics
    ) -> List[PermissionAssignment]:
        """
        Get assignments for entity with optimized caching.

        Args:
            entity: Entity to get assignments for
            metrics: Performance metrics tracker

        Returns:
            List of permission assignments
        """
        import time

        # Check cache first
        cached_assignments = self.performance_optimizer.cache.get_assignments(
            entity.entity_id, entity.entity_type
        )
        if cached_assignments is not None:
            metrics.cached_lookups += 1
            logger.debug(
                f"Using cached assignments for {entity.entity_type.value} {entity.entity_name}"
            )
            return cached_assignments

        # Fetch from API with timing
        start_time = time.time()

        if entity.entity_type == EntityType.USER:
            assignments = self.assignment_retriever.get_user_assignments(entity)
        elif entity.entity_type == EntityType.GROUP:
            assignments = self.assignment_retriever.get_group_assignments(entity)
        else:
            logger.error(f"Unsupported entity type: {entity.entity_type}")
            return []

        metrics.assignment_retrieval_time_ms += (time.time() - start_time) * 1000
        metrics.api_calls += 1

        # Cache the result
        self.performance_optimizer.cache.put_assignments(
            entity.entity_id, entity.entity_type, assignments
        )

        return assignments

    def _identify_assignments_to_copy(
        self,
        source_assignments: List[PermissionAssignment],
        target_assignments: List[PermissionAssignment],
    ) -> Tuple[List[PermissionAssignment], List[PermissionAssignment]]:
        """
        Identify which assignments should be copied and which should be skipped.

        Args:
            source_assignments: Source entity assignments
            target_assignments: Target entity assignments

        Returns:
            Tuple of (assignments_to_copy, assignments_to_skip)
        """
        assignments_to_copy = []
        assignments_to_skip = []

        # Create a set of existing target assignments for fast lookup
        existing_assignments = set()
        for assignment in target_assignments:
            key = (assignment.permission_set_arn, assignment.account_id)
            existing_assignments.add(key)

        # Check each source assignment
        for assignment in source_assignments:
            key = (assignment.permission_set_arn, assignment.account_id)

            if key in existing_assignments:
                assignments_to_skip.append(assignment)
                logger.debug(
                    f"Skipping duplicate assignment: {assignment.permission_set_name} "
                    f"on account {assignment.account_id}"
                )
            else:
                assignments_to_copy.append(assignment)
                logger.debug(
                    f"Will copy assignment: {assignment.permission_set_name} "
                    f"on account {assignment.account_id}"
                )

        return assignments_to_copy, assignments_to_skip

    def _execute_copy_operation_optimized(
        self,
        target: EntityReference,
        assignments_to_copy: List[PermissionAssignment],
        rollback_id: str,
        metrics: PerformanceMetrics,
        progress_callback: Optional[callable] = None,
    ) -> List[PermissionAssignment]:
        """
        Execute the copy operation using optimized batch processing.

        Args:
            target: Target entity to copy assignments to
            assignments_to_copy: List of assignments to copy
            rollback_id: Rollback ID for this operation
            metrics: Performance metrics tracker
            progress_callback: Optional callback for progress updates

        Returns:
            List of successfully copied assignments
        """
        if not assignments_to_copy:
            return []

        logger.info(
            f"Executing optimized copy operation for {len(assignments_to_copy)} assignments"
        )

        # Create operation function
        def create_assignment_operation(
            target_entity: EntityReference, assignment: PermissionAssignment
        ):
            if target_entity.entity_type == EntityType.USER:
                self._create_user_assignment(
                    target_entity.entity_id, assignment.permission_set_arn, assignment.account_id
                )
            else:  # GROUP
                self._create_group_assignment(
                    target_entity.entity_id, assignment.permission_set_arn, assignment.account_id
                )

        # Use stream processor for large operations
        stream_processor = self.performance_optimizer.create_stream_processor()

        successful_assignments, error_messages = stream_processor.process_large_assignment_list(
            assignments=assignments_to_copy,
            target_entity=target,
            operation_func=create_assignment_operation,
            metrics=metrics,
            progress_callback=progress_callback,
        )

        # Log any errors
        for error_msg in error_messages:
            logger.warning(error_msg)

        logger.info(
            f"Optimized copy operation completed: {len(successful_assignments)} successful, "
            f"{len(error_messages)} failed"
        )

        return successful_assignments

    def _create_user_assignment(
        self, user_id: str, permission_set_arn: str, account_id: str
    ) -> None:
        """
        Create a permission assignment for a user.

        Args:
            user_id: User ID to assign permissions to
            permission_set_arn: Permission set ARN to assign
            account_id: Account ID to assign permissions on

        Raises:
            Exception: If assignment creation fails
        """
        try:
            # Get the SSO Admin client from the assignment retriever
            sso_admin_client = self.assignment_retriever.sso_admin_client

            # Create the account assignment
            response = sso_admin_client.create_account_assignment(
                InstanceArn=self.assignment_retriever.instance_arn,
                TargetId=account_id,
                TargetType="AWS_ACCOUNT",
                PermissionSetArn=permission_set_arn,
                PrincipalType="USER",
                PrincipalId=user_id,
            )

            logger.debug(f"Created user assignment: {response}")

        except Exception as e:
            logger.error(f"Failed to create user assignment: {str(e)}")
            raise

    def _create_group_assignment(
        self, group_id: str, permission_set_arn: str, account_id: str
    ) -> None:
        """
        Create a permission assignment for a group.

        Args:
            group_id: Group ID to assign permissions to
            permission_set_arn: Permission set ARN to assign
            account_id: Account ID to assign permissions on

        Raises:
            Exception: If assignment creation fails
        """
        try:
            # Get the SSO Admin client from the assignment retriever
            sso_admin_client = self.assignment_retriever.sso_admin_client

            # Create the account assignment
            response = sso_admin_client.create_account_assignment(
                InstanceArn=self.assignment_retriever.instance_arn,
                TargetId=account_id,
                TargetType="AWS_ACCOUNT",
                PermissionSetArn=permission_set_arn,
                PrincipalType="GROUP",
                PrincipalId=group_id,
            )

            logger.debug(f"Created group assignment: {response}")

        except Exception as e:
            logger.error(f"Failed to create group assignment: {str(e)}")
            raise

    def _create_success_result(
        self,
        source: EntityReference,
        target: EntityReference,
        assignments_copied: List[PermissionAssignment],
        assignments_skipped: List[PermissionAssignment],
        rollback_id: Optional[str],
        operation_id: str,
    ) -> CopyResult:
        """Create a successful CopyResult with performance metrics."""
        # Finish performance tracking
        final_metrics = self.performance_optimizer.finish_operation_metrics(operation_id)

        result = CopyResult(
            source=source,
            target=target,
            assignments_copied=assignments_copied,
            assignments_skipped=assignments_skipped,
            rollback_id=rollback_id,
            success=True,
            error_message=None,
        )

        # Add performance metrics to result if available
        if final_metrics:
            result.performance_metrics = {
                "duration_ms": final_metrics.duration_ms,
                "assignments_per_second": final_metrics.assignments_per_second,
                "success_rate": final_metrics.success_rate,
                "api_calls": final_metrics.api_calls,
                "cached_lookups": final_metrics.cached_lookups,
                "rate_limit_delays_ms": final_metrics.rate_limit_delays_ms,
                "retry_attempts": final_metrics.retry_attempts,
            }

        return result

    def _create_error_result(
        self,
        source: EntityReference,
        target: EntityReference,
        error_message: str,
        operation_id: str,
    ) -> CopyResult:
        """Create an error CopyResult with performance metrics."""
        # Finish performance tracking
        final_metrics = self.performance_optimizer.finish_operation_metrics(operation_id)

        result = CopyResult(
            source=source,
            target=target,
            assignments_copied=[],
            assignments_skipped=[],
            rollback_id=None,
            success=False,
            error_message=error_message,
        )

        # Add performance metrics to result if available
        if final_metrics:
            result.performance_metrics = {
                "duration_ms": final_metrics.duration_ms,
                "api_calls": final_metrics.api_calls,
                "cached_lookups": final_metrics.cached_lookups,
            }

        return result
