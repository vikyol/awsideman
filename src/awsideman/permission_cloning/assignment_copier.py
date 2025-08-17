"""
Assignment copier for permission assignments in AWS Identity Center.

This module provides functionality to copy permission assignments between users and groups,
including duplicate detection, support for different entity types, and comprehensive error handling.
"""

import logging
import time
from typing import Callable, List, Optional, Tuple
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
    ValidationResultType,
)
from .progress_reporter import ProgressReporter, get_progress_reporter

logger = logging.getLogger(__name__)


class AssignmentCopier:
    """
    Handles copying permission assignments between users and groups.

    This class supports:
    - Copying between users (user-to-user)
    - Copying between groups (group-to-group)
    - Copying from user to group (user-to-group)
    - Copying from group to user (group-to-user)
    - Duplicate detection and skipping
    - Filtering of assignments to copy
    - Comprehensive error handling and reporting
    """

    def __init__(
        self,
        entity_resolver: EntityResolver,
        assignment_retriever: AssignmentRetriever,
        filter_engine: FilterEngine,
        progress_reporter: Optional[ProgressReporter] = None,
    ):
        """
        Initialize the AssignmentCopier.

        Args:
            entity_resolver: Entity resolver for validation
            assignment_retriever: Assignment retriever for fetching assignments
            filter_engine: Filter engine for filtering assignments
            progress_reporter: Optional progress reporter for logging and progress tracking
        """
        self.entity_resolver = entity_resolver
        self.assignment_retriever = assignment_retriever
        self.filter_engine = filter_engine
        self.progress_reporter = progress_reporter or get_progress_reporter()

    def copy_assignments(
        self,
        source: EntityReference,
        target: EntityReference,
        filters: Optional[CopyFilters] = None,
        preview: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> CopyResult:
        """
        Copy permission assignments from source entity to target entity.

        Args:
            source: Source entity (user or group)
            target: Target entity (user or group)
            filters: Optional filters to apply to assignments
            preview: If True, only preview the operation without executing
            progress_callback: Optional callback for progress updates (current, total, message)

        Returns:
            CopyResult with details of the operation
        """
        # Start operation tracking
        operation_id = self.progress_reporter.start_operation(
            operation_type="copy_assignments",
            source_entity_type=source.entity_type.value,
            source_entity_name=source.entity_name,
            target_entity_type=target.entity_type.value,
            target_entity_name=target.entity_name,
            preview_mode=preview,
            filters_applied=self.filter_engine.get_filter_summary(filters) if filters else None,
        )

        start_time = time.time()

        logger.info(
            f"Starting assignment copy from {source.entity_type.value} '{source.entity_name}' "
            f"to {target.entity_type.value} '{target.entity_name}' (operation_id: {operation_id})"
        )

        try:
            # Update progress: Starting validation
            self.progress_reporter.update_progress(operation_id, 0, 100, "Validating entities")
            if progress_callback:
                progress_callback(0, 100, "Validating entities")

            # Validate entities before proceeding
            validation_result = self.validate_entities(source, target)
            if validation_result.has_errors:
                error_message = "; ".join(validation_result.messages)
                logger.error(f"Entity validation failed: {error_message}")

                # Finish operation with error
                self.progress_reporter.finish_operation(
                    operation_id, success=False, error_message=error_message
                )

                return CopyResult(
                    source=source,
                    target=target,
                    assignments_copied=[],
                    assignments_skipped=[],
                    rollback_id=None,
                    success=False,
                    error_message=error_message,
                )

            # Update progress: Retrieving source assignments
            self.progress_reporter.update_progress(
                operation_id, 10, 100, "Retrieving source assignments"
            )
            if progress_callback:
                progress_callback(10, 100, "Retrieving source assignments")

            # Get source assignments
            source_assignments = self.get_source_assignments(source)
            if not source_assignments:
                logger.info(
                    f"No assignments found for source {source.entity_type.value} '{source.entity_name}'"
                )

                # Log audit event and finish operation
                self.progress_reporter.log_assignment_copy_start(
                    operation_id,
                    source,
                    target,
                    0,
                    self.filter_engine.get_filter_summary(filters) if filters else None,
                )

                duration_ms = (time.time() - start_time) * 1000
                result = CopyResult(
                    source=source,
                    target=target,
                    assignments_copied=[],
                    assignments_skipped=[],
                    rollback_id=None,
                    success=True,
                    error_message=None,
                )

                self.progress_reporter.log_assignment_copy_result(operation_id, result, duration_ms)
                self.progress_reporter.finish_operation(operation_id, success=True)

                return result

            # Update progress: Applying filters
            self.progress_reporter.update_progress(operation_id, 20, 100, "Applying filters")
            if progress_callback:
                progress_callback(20, 100, "Applying filters")

            # Apply filters if specified
            if filters:
                logger.info(f"Applying filters: {self.filter_engine.get_filter_summary(filters)}")
                source_assignments = self.filter_engine.apply_filters(source_assignments, filters)
                if not source_assignments:
                    logger.info("No assignments match the specified filters")

                    # Log audit event and finish operation
                    self.progress_reporter.log_assignment_copy_start(
                        operation_id,
                        source,
                        target,
                        0,
                        self.filter_engine.get_filter_summary(filters),
                    )

                    duration_ms = (time.time() - start_time) * 1000
                    result = CopyResult(
                        source=source,
                        target=target,
                        assignments_copied=[],
                        assignments_skipped=[],
                        rollback_id=None,
                        success=True,
                        error_message=None,
                    )

                    self.progress_reporter.log_assignment_copy_result(
                        operation_id, result, duration_ms
                    )
                    self.progress_reporter.finish_operation(operation_id, success=True)

                    return result

            # Log the start of the copy operation
            self.progress_reporter.log_assignment_copy_start(
                operation_id,
                source,
                target,
                len(source_assignments),
                self.filter_engine.get_filter_summary(filters) if filters else None,
            )

            # Update progress: Getting target assignments
            self.progress_reporter.update_progress(
                operation_id, 30, 100, "Retrieving target assignments for duplicate detection"
            )
            if progress_callback:
                progress_callback(30, 100, "Retrieving target assignments for duplicate detection")

            # Get target assignments for duplicate detection
            target_assignments = self.get_source_assignments(target)

            # Update progress: Analyzing assignments
            self.progress_reporter.update_progress(
                operation_id, 40, 100, "Analyzing assignments for duplicates"
            )
            if progress_callback:
                progress_callback(40, 100, "Analyzing assignments for duplicates")

            # Identify assignments to copy and skip
            assignments_to_copy, assignments_to_skip = self._identify_assignments_to_copy(
                source_assignments, target_assignments
            )

            if preview:
                logger.info("Preview mode - no assignments will be copied")

                # Update progress: Preview complete
                self.progress_reporter.update_progress(operation_id, 100, 100, "Preview completed")
                if progress_callback:
                    progress_callback(100, 100, "Preview completed")

                duration_ms = (time.time() - start_time) * 1000
                result = CopyResult(
                    source=source,
                    target=target,
                    assignments_copied=assignments_to_copy,
                    assignments_skipped=assignments_to_skip,
                    rollback_id=None,
                    success=True,
                    error_message=None,
                )

                self.progress_reporter.log_assignment_copy_result(operation_id, result, duration_ms)
                self.progress_reporter.finish_operation(operation_id, success=True)

                return result

            # Generate rollback ID for this operation
            rollback_id = str(uuid4())
            logger.info(f"Generated rollback ID: {rollback_id}")

            # Update progress: Starting copy operation
            self.progress_reporter.update_progress(
                operation_id, 50, 100, f"Copying {len(assignments_to_copy)} assignments"
            )
            if progress_callback:
                progress_callback(50, 100, f"Copying {len(assignments_to_copy)} assignments")

            # Execute the copy operation with progress tracking
            copied_assignments = self._execute_copy_operation(
                target, assignments_to_copy, rollback_id, operation_id, progress_callback
            )

            # Update progress: Operation complete
            self.progress_reporter.update_progress(
                operation_id, 100, 100, "Copy operation completed"
            )
            if progress_callback:
                progress_callback(100, 100, "Copy operation completed")

            # Prepare result
            result = CopyResult(
                source=source,
                target=target,
                assignments_copied=copied_assignments,
                assignments_skipped=assignments_to_skip,
                rollback_id=rollback_id,
                success=True,
                error_message=None,
            )

            # Log performance metrics
            duration_ms = (time.time() - start_time) * 1000
            self.progress_reporter.log_performance_metric(
                operation_id, "copy_assignments", "duration_ms", duration_ms, "milliseconds"
            )
            self.progress_reporter.log_performance_metric(
                operation_id,
                "copy_assignments",
                "assignments_copied",
                len(copied_assignments),
                "count",
            )
            self.progress_reporter.log_performance_metric(
                operation_id,
                "copy_assignments",
                "assignments_skipped",
                len(assignments_to_skip),
                "count",
            )
            if duration_ms > 0:
                throughput = (
                    len(copied_assignments) / duration_ms
                ) * 1000  # assignments per second
                self.progress_reporter.log_performance_metric(
                    operation_id, "copy_assignments", "throughput", throughput, "assignments/second"
                )

            # Log audit result and finish operation
            self.progress_reporter.log_assignment_copy_result(operation_id, result, duration_ms)
            self.progress_reporter.finish_operation(operation_id, success=True)

            logger.info(
                f"Successfully copied {len(copied_assignments)} assignments, "
                f"skipped {len(assignments_to_skip)} duplicates"
            )

            return result

        except Exception as e:
            error_message = f"Copy operation failed: {str(e)}"
            logger.error(f"Error during assignment copy: {str(e)}", exc_info=True)

            # Log performance metrics for failed operation
            duration_ms = (time.time() - start_time) * 1000
            self.progress_reporter.log_performance_metric(
                operation_id, "copy_assignments", "duration_ms", duration_ms, "milliseconds"
            )

            # Finish operation with error
            self.progress_reporter.finish_operation(
                operation_id, success=False, error_message=error_message
            )

            return CopyResult(
                source=source,
                target=target,
                assignments_copied=[],
                assignments_skipped=[],
                rollback_id=None,
                success=False,
                error_message=error_message,
            )

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
            return ValidationResult(result_type=ValidationResultType.ERROR, messages=errors)

        return ValidationResult(result_type=ValidationResultType.SUCCESS, messages=[])

    def get_source_assignments(self, entity: EntityReference) -> List[PermissionAssignment]:
        """
        Get all permission assignments for a given entity.

        Args:
            entity: Entity to get assignments for

        Returns:
            List of permission assignments
        """
        if entity.entity_type == EntityType.USER:
            return self.assignment_retriever.get_user_assignments(entity)
        elif entity.entity_type == EntityType.GROUP:
            return self.assignment_retriever.get_group_assignments(entity)
        else:
            logger.error(f"Unsupported entity type: {entity.entity_type}")
            return []

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

    def _execute_copy_operation(
        self,
        target: EntityReference,
        assignments_to_copy: List[PermissionAssignment],
        rollback_id: str,
        operation_id: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[PermissionAssignment]:
        """
        Execute the actual copy operation by creating assignments on the target entity.

        Args:
            target: Target entity to copy assignments to
            assignments_to_copy: List of assignments to copy
            rollback_id: Rollback ID for this operation
            operation_id: Operation ID for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            List of successfully copied assignments
        """
        copied_assignments = []
        total_assignments = len(assignments_to_copy)

        for i, assignment in enumerate(assignments_to_copy):
            try:
                # Update progress for this assignment
                progress_message = f"Creating assignment {i+1}/{total_assignments}: {assignment.permission_set_name}"
                progress_percentage = 50 + int((i / total_assignments) * 50)  # 50-100% range

                self.progress_reporter.update_progress(
                    operation_id, progress_percentage, 100, progress_message
                )
                if progress_callback:
                    progress_callback(progress_percentage, 100, progress_message)

                logger.info(
                    f"Creating assignment: {assignment.permission_set_name} "
                    f"on account {assignment.account_id} for {target.entity_type.value} "
                    f"'{target.entity_name}'"
                )

                # Create the assignment using the assignment retriever's client
                if target.entity_type == EntityType.USER:
                    self._create_user_assignment(
                        target.entity_id, assignment.permission_set_arn, assignment.account_id
                    )
                else:  # GROUP
                    self._create_group_assignment(
                        target.entity_id, assignment.permission_set_arn, assignment.account_id
                    )

                copied_assignments.append(assignment)
                logger.info(
                    f"Successfully created assignment: {assignment.permission_set_name} "
                    f"on account {assignment.account_id}"
                )

                # Log performance metric for individual assignment
                self.progress_reporter.log_performance_metric(
                    operation_id,
                    "copy_assignments",
                    "assignment_created",
                    1,
                    "count",
                    permission_set_name=assignment.permission_set_name,
                    account_id=assignment.account_id,
                )

            except Exception as e:
                logger.error(
                    f"Failed to create assignment {assignment.permission_set_name} "
                    f"on account {assignment.account_id}: {str(e)}"
                )

                # Log performance metric for failed assignment
                self.progress_reporter.log_performance_metric(
                    operation_id,
                    "copy_assignments",
                    "assignment_failed",
                    1,
                    "count",
                    permission_set_name=assignment.permission_set_name,
                    account_id=assignment.account_id,
                    error=str(e),
                )

                # Continue with other assignments instead of failing completely
                continue

        return copied_assignments

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
                TargetId=user_id,
                TargetType="AWS_ACCOUNT",
                PermissionSetArn=permission_set_arn,
                PrincipalType="USER",
                AccountId=account_id,
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
                TargetId=group_id,
                TargetType="AWS_ACCOUNT",
                PermissionSetArn=permission_set_arn,
                PrincipalType="GROUP",
                AccountId=account_id,
            )

            logger.debug(f"Created group assignment: {response}")

        except Exception as e:
            logger.error(f"Failed to create group assignment: {str(e)}")
            raise

    def copy_assignments_by_name(
        self,
        source_entity_type: str,
        source_entity_name: str,
        target_entity_type: str,
        target_entity_name: str,
        filters: Optional[CopyFilters] = None,
        dry_run: bool = False,
    ) -> CopyResult:
        """
        Copy permission assignments between entities using their names.

        Args:
            source_entity_type: Source entity type ('user' or 'group')
            source_entity_name: Source entity name
            target_entity_type: Target entity type ('user' or 'group')
            target_entity_name: Target entity name
            filters: Optional filters to apply to assignments
            dry_run: If True, only preview the operation without executing

        Returns:
            CopyResult with details of the operation
        """
        try:
            # Resolve source entity
            source_type = (
                EntityType.USER if source_entity_type.lower() == "user" else EntityType.GROUP
            )
            source_entity = self.entity_resolver.resolve_entity_by_name(
                source_type, source_entity_name
            )

            # Resolve target entity
            target_type = (
                EntityType.USER if target_entity_type.lower() == "user" else EntityType.GROUP
            )
            target_entity = self.entity_resolver.resolve_entity_by_name(
                target_type, target_entity_name
            )

            # Perform the copy operation
            return self.copy_assignments(
                source=source_entity, target=target_entity, filters=filters, preview=dry_run
            )

        except Exception as e:
            logger.error(f"Failed to copy assignments by name: {str(e)}")
            # Create dummy entities for error reporting
            source_entity = EntityReference(
                entity_type=(
                    EntityType.USER if source_entity_type.lower() == "user" else EntityType.GROUP
                ),
                entity_id="unknown",
                entity_name=source_entity_name,
            )
            target_entity = EntityReference(
                entity_type=(
                    EntityType.USER if target_entity_type.lower() == "user" else EntityType.GROUP
                ),
                entity_id="unknown",
                entity_name=target_entity_name,
            )

            return CopyResult(
                source=source_entity,
                target=target_entity,
                assignments_copied=[],
                assignments_skipped=[],
                rollback_id=None,
                success=False,
                error_message=str(e),
            )

    def get_copy_summary(self, result: CopyResult) -> str:
        """
        Get a human-readable summary of the copy operation.

        Args:
            result: CopyResult from a copy operation

        Returns:
            String summary of the copy operation
        """
        if not result.success:
            return f"Copy operation failed: {result.error_message}"

        summary_parts = []

        if result.assignments_copied:
            summary_parts.append(
                f"Successfully copied {len(result.assignments_copied)} assignments"
            )
        else:
            summary_parts.append("No assignments were copied")

        if result.assignments_skipped:
            summary_parts.append(f"Skipped {len(result.assignments_skipped)} duplicate assignments")

        if result.rollback_id:
            summary_parts.append(f"Rollback ID: {result.rollback_id}")

        return "; ".join(summary_parts)
