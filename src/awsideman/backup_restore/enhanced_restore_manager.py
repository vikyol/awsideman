"""
Enhanced restore manager with comprehensive error handling and rollback capabilities.

This module extends the base restore manager with advanced error handling,
retry logic, rollback capabilities, and detailed error reporting.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..aws_clients import CachedIdentityCenterClient, CachedIdentityStoreClient
from .error_handling import (
    OperationState,
    RetryConfig,
    RollbackManager,
    create_error_handling_system,
)
from .interfaces import ProgressReporterInterface, RestoreManagerInterface, StorageEngineInterface
from .models import (
    BackupData,
    ConflictInfo,
    ResourceType,
    RestoreOptions,
    RestorePreview,
    RestoreResult,
    ValidationResult,
)
from .restore_manager import CompatibilityValidator, ConflictResolver, RestoreProcessor

logger = logging.getLogger(__name__)


class EnhancedRestoreManager(RestoreManagerInterface):
    """
    Enhanced restore manager with comprehensive error handling and rollback capabilities.

    Provides:
    - Retry logic with exponential backoff
    - Automatic rollback on failure
    - Detailed error reporting with remediation suggestions
    - Operation state tracking for recovery
    - Partial restore recovery
    """

    def __init__(
        self,
        storage_engine: StorageEngineInterface,
        identity_center_client: CachedIdentityCenterClient,
        identity_store_client: CachedIdentityStoreClient,
        progress_reporter: Optional[ProgressReporterInterface] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize enhanced restore manager.

        Args:
            storage_engine: Storage engine for backup retrieval
            identity_center_client: Identity Center client
            identity_store_client: Identity Store client
            progress_reporter: Optional progress reporter
            retry_config: Optional retry configuration
        """
        self.storage_engine = storage_engine
        self.identity_center_client = identity_center_client
        self.identity_store_client = identity_store_client
        self.progress_reporter = progress_reporter

        # Initialize error handling system
        self.error_handling = create_error_handling_system(retry_config)
        self.retry_handler = self.error_handling["retry_handler"]
        self.error_analyzer = self.error_handling["error_analyzer"]
        self.rollback_manager = self.error_handling["rollback_manager"]
        self.error_reporter = self.error_handling["error_reporter"]

        # Initialize restore components
        self.compatibility_validator = CompatibilityValidator(
            identity_center_client, identity_store_client
        )

        # Operation state tracking
        self._operation_states: Dict[str, OperationState] = {}

    async def restore_backup(self, backup_id: str, options: RestoreOptions) -> RestoreResult:
        """
        Restore a backup with enhanced error handling and rollback capabilities.

        Args:
            backup_id: Unique identifier of the backup to restore
            options: Configuration options for the restore operation

        Returns:
            RestoreResult containing the outcome of the restore operation
        """
        operation_id = f"restore-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        # Initialize operation state for tracking and rollback
        operation_state = OperationState(
            operation_id=operation_id, operation_type="restore", start_time=start_time
        )
        self._operation_states[operation_id] = operation_state

        try:
            logger.info(
                f"Starting enhanced restore operation {operation_id} for backup {backup_id}"
            )

            # Add initial checkpoint
            operation_state.add_checkpoint(
                "operation_start", {"backup_id": backup_id, "options": options.to_dict()}
            )

            # Execute restore with retry logic and rollback capability
            result = await self.retry_handler.execute_with_retry(
                self._execute_restore_with_rollback,
                backup_id,
                options,
                operation_state,
                context={"operation_id": operation_id, "operation_type": "restore"},
            )

            operation_state.completed = True
            operation_state.success = result.success

            return result

        except Exception as e:
            logger.error(f"Enhanced restore operation {operation_id} failed: {e}")

            # Analyze the error
            error_info = self.error_analyzer.analyze_error(
                e,
                {
                    "operation_id": operation_id,
                    "operation_type": "restore",
                    "backup_id": backup_id,
                    "options": options.to_dict(),
                },
            )

            # Attempt rollback if changes were applied
            rollback_result = None
            if operation_state.applied_changes and not options.dry_run:
                logger.info(f"Attempting rollback for operation {operation_id}")
                rollback_result = await self.rollback_manager.execute_rollback(operation_state)

            # Generate detailed error report
            error_report = self.error_reporter.generate_error_report(
                [error_info],
                {
                    "operation_id": operation_id,
                    "operation_type": "restore",
                    "backup_id": backup_id,
                    "options": options.to_dict(),
                    "rollback_attempted": rollback_result is not None,
                },
            )

            # Create enhanced failure result
            result = RestoreResult(
                success=False,
                message=f"Restore operation failed: {error_info.message}",
                errors=[error_info.message] + error_info.suggested_actions,
                duration=datetime.now() - start_time,
            )

            # Add rollback information if available
            if rollback_result:
                if rollback_result.get("success"):
                    result.message += f" (Rollback successful: {rollback_result['message']})"
                    result.warnings = [
                        f"Changes rolled back: {rollback_result['applied_changes_reverted']} actions"
                    ]
                else:
                    result.message += (
                        f" (Rollback failed: {rollback_result.get('message', 'Unknown error')})"
                    )
                    result.errors.append(
                        f"Rollback failed: {rollback_result.get('message', 'Unknown error')}"
                    )

            # Add error report to result
            result.errors.extend(
                [
                    f"Error Report ID: {error_report['report_id']}",
                    f"Next Steps: {'; '.join(error_report['next_steps'][:3])}",
                ]
            )

            operation_state.completed = True
            operation_state.success = False

            return result

        finally:
            # Clean up operation state after a delay to allow for inspection
            asyncio.create_task(self._cleanup_operation_state(operation_id, delay=300))  # 5 minutes

    async def _execute_restore_with_rollback(
        self, backup_id: str, options: RestoreOptions, operation_state: OperationState
    ) -> RestoreResult:
        """
        Execute restore operation with rollback capability.

        Args:
            backup_id: Backup ID to restore
            options: Restore options
            operation_state: Operation state for tracking

        Returns:
            RestoreResult
        """
        operation_id = operation_state.operation_id

        # Step 1: Retrieve backup data with retry
        backup_data = await self.retry_handler.execute_with_retry(
            self.storage_engine.retrieve_backup,
            backup_id,
            context={"step": "backup_retrieval", "operation_id": operation_id},
        )

        if not backup_data:
            raise ValueError(f"Backup {backup_id} not found or could not be retrieved")

        operation_state.add_checkpoint(
            "backup_retrieved",
            {"backup_id": backup_id, "resource_counts": backup_data.metadata.resource_counts},
        )

        # Step 2: Validate compatibility with retry
        if not options.skip_validation:
            target_instance_arn = options.target_instance_arn or backup_data.metadata.instance_arn
            compatibility_result = await self.retry_handler.execute_with_retry(
                self.compatibility_validator.validate_compatibility,
                backup_data,
                target_instance_arn,
                context={"step": "compatibility_validation", "operation_id": operation_id},
            )

            if not compatibility_result.is_valid:
                raise ValueError(
                    f"Compatibility validation failed: {'; '.join(compatibility_result.errors)}"
                )

            operation_state.add_checkpoint(
                "compatibility_validated", {"validation_result": compatibility_result.to_dict()}
            )

        # Step 3: Initialize restore processor with rollback tracking
        conflict_resolver = ConflictResolver(options.conflict_strategy)
        restore_processor = EnhancedRestoreProcessor(
            self.identity_center_client,
            self.identity_store_client,
            conflict_resolver,
            operation_state,
            self.rollback_manager,
        )

        # Step 4: Execute restore with rollback tracking
        if self.progress_reporter:
            total_steps = self._calculate_total_steps(backup_data, options)
            await self.progress_reporter.start_operation(
                operation_id, total_steps, "Restoring backup with rollback capability"
            )

        result = await restore_processor.process_restore_with_rollback(
            backup_data, options, self.progress_reporter, operation_id
        )

        # Complete operation
        if self.progress_reporter:
            await self.progress_reporter.complete_operation(
                operation_id, result.success, result.message
            )

        return result

    async def preview_restore(self, backup_id: str, options: RestoreOptions) -> RestorePreview:
        """
        Preview the changes that would be made by a restore operation.

        Args:
            backup_id: Unique identifier of the backup to preview
            options: Configuration options for the restore operation

        Returns:
            RestorePreview containing details of planned changes
        """
        try:
            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                raise ValueError(f"Backup {backup_id} not found")

            # Create dry-run options
            preview_options = RestoreOptions(
                target_resources=options.target_resources,
                conflict_strategy=options.conflict_strategy,
                dry_run=True,
                target_account=options.target_account,
                target_region=options.target_region,
                target_instance_arn=options.target_instance_arn,
                resource_mappings=options.resource_mappings,
                skip_validation=options.skip_validation,
            )

            # Execute dry-run restore
            conflict_resolver = ConflictResolver(preview_options.conflict_strategy)
            restore_processor = RestoreProcessor(
                self.identity_center_client, self.identity_store_client, conflict_resolver
            )

            # Get preview by running dry-run
            dry_run_result = await restore_processor.process_restore(backup_data, preview_options)

            # Convert result to preview
            changes_summary = dry_run_result.changes_applied
            estimated_duration = timedelta(
                seconds=len(
                    backup_data.users
                    + backup_data.groups
                    + backup_data.permission_sets
                    + backup_data.assignments
                )
                * 0.5
            )

            return RestorePreview(
                changes_summary=changes_summary,
                conflicts=[],  # Would be populated by actual conflict detection
                warnings=dry_run_result.warnings,
                estimated_duration=estimated_duration,
            )

        except Exception as e:
            logger.error(f"Failed to preview restore for backup {backup_id}: {e}")
            return RestorePreview(
                changes_summary={},
                conflicts=[],
                warnings=[f"Preview failed: {str(e)}"],
                estimated_duration=None,
            )

    async def validate_compatibility(
        self, backup_id: str, target_instance_arn: str
    ) -> ValidationResult:
        """
        Validate compatibility between a backup and target environment.

        Args:
            backup_id: Unique identifier of the backup
            target_instance_arn: ARN of the target Identity Center instance

        Returns:
            ValidationResult containing compatibility status and details
        """
        try:
            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Backup {backup_id} not found"],
                    warnings=[],
                    details={},
                )

            # Validate compatibility
            return await self.compatibility_validator.validate_compatibility(
                backup_data, target_instance_arn
            )

        except Exception as e:
            logger.error(f"Failed to validate compatibility for backup {backup_id}: {e}")
            return ValidationResult(
                is_valid=False,
                errors=[f"Compatibility validation failed: {str(e)}"],
                warnings=[],
                details={},
            )

    def _calculate_total_steps(self, backup_data: BackupData, options: RestoreOptions) -> int:
        """Calculate total steps for progress reporting."""
        total = 0
        if (
            ResourceType.USERS in options.target_resources
            or ResourceType.ALL in options.target_resources
        ):
            total += len(backup_data.users)
        if (
            ResourceType.GROUPS in options.target_resources
            or ResourceType.ALL in options.target_resources
        ):
            total += len(backup_data.groups)
        if (
            ResourceType.PERMISSION_SETS in options.target_resources
            or ResourceType.ALL in options.target_resources
        ):
            total += len(backup_data.permission_sets)
        if (
            ResourceType.ASSIGNMENTS in options.target_resources
            or ResourceType.ALL in options.target_resources
        ):
            total += len(backup_data.assignments)
        return total

    async def get_operation_state(self, operation_id: str) -> Optional[OperationState]:
        """
        Get the current state of an operation.

        Args:
            operation_id: ID of the operation

        Returns:
            OperationState if found, None otherwise
        """
        return self._operation_states.get(operation_id)

    async def list_operation_states(self) -> List[Dict[str, Any]]:
        """
        List all tracked operation states.

        Returns:
            List of operation state summaries
        """
        states = []
        for operation_id, state in self._operation_states.items():
            states.append(
                {
                    "operation_id": operation_id,
                    "operation_type": state.operation_type,
                    "start_time": state.start_time.isoformat(),
                    "completed": state.completed,
                    "success": state.success,
                    "checkpoints_count": len(state.checkpoints),
                    "changes_count": len(state.applied_changes),
                    "rollback_actions_count": len(state.rollback_actions),
                }
            )
        return states

    async def execute_rollback(self, operation_id: str) -> Dict[str, Any]:
        """
        Execute rollback for a specific operation.

        Args:
            operation_id: ID of the operation to rollback

        Returns:
            Rollback result
        """
        operation_state = self._operation_states.get(operation_id)
        if not operation_state:
            return {
                "success": False,
                "message": f"Operation {operation_id} not found or already cleaned up",
            }

        return await self.rollback_manager.execute_rollback(operation_state)

    async def _cleanup_operation_state(self, operation_id: str, delay: int = 300):
        """
        Clean up operation state after a delay.

        Args:
            operation_id: ID of the operation to clean up
            delay: Delay in seconds before cleanup
        """
        await asyncio.sleep(delay)
        self._operation_states.pop(operation_id, None)
        logger.debug(f"Cleaned up operation state for {operation_id}")


class EnhancedRestoreProcessor(RestoreProcessor):
    """
    Enhanced restore processor with rollback capability.

    Extends the base RestoreProcessor to track changes and create rollback actions.
    """

    def __init__(
        self,
        identity_center_client: CachedIdentityCenterClient,
        identity_store_client: CachedIdentityStoreClient,
        conflict_resolver: ConflictResolver,
        operation_state: OperationState,
        rollback_manager: RollbackManager,
    ):
        """
        Initialize enhanced restore processor.

        Args:
            identity_center_client: Identity Center client
            identity_store_client: Identity Store client
            conflict_resolver: Conflict resolver
            operation_state: Operation state for tracking changes
            rollback_manager: Rollback manager for creating rollback actions
        """
        super().__init__(identity_center_client, identity_store_client, conflict_resolver)
        self.operation_state = operation_state
        self.rollback_manager = rollback_manager

    async def process_restore_with_rollback(
        self,
        backup_data: BackupData,
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface] = None,
        operation_id: str = None,
    ) -> RestoreResult:
        """
        Process restore operation with rollback tracking.

        Args:
            backup_data: Data to restore
            options: Restore options
            progress_reporter: Optional progress reporter
            operation_id: Operation ID for progress tracking

        Returns:
            RestoreResult with operation outcome
        """
        start_time = datetime.now()
        errors = []
        warnings = []
        changes_applied = {}

        try:
            current_step = 0

            # Restore in dependency order with rollback tracking
            if (
                ResourceType.USERS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                result = await self._restore_users_with_rollback(
                    backup_data.users, options, progress_reporter, operation_id, current_step
                )
                changes_applied["users"] = result["applied"]
                errors.extend(result["errors"])
                warnings.extend(result["warnings"])
                current_step += result["steps"]

            if (
                ResourceType.GROUPS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                result = await self._restore_groups_with_rollback(
                    backup_data.groups, options, progress_reporter, operation_id, current_step
                )
                changes_applied["groups"] = result["applied"]
                errors.extend(result["errors"])
                warnings.extend(result["warnings"])
                current_step += result["steps"]

            if (
                ResourceType.PERMISSION_SETS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                result = await self._restore_permission_sets_with_rollback(
                    backup_data.permission_sets,
                    options,
                    progress_reporter,
                    operation_id,
                    current_step,
                )
                changes_applied["permission_sets"] = result["applied"]
                errors.extend(result["errors"])
                warnings.extend(result["warnings"])
                current_step += result["steps"]

            if (
                ResourceType.ASSIGNMENTS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                result = await self._restore_assignments_with_rollback(
                    backup_data.assignments, options, progress_reporter, operation_id, current_step
                )
                changes_applied["assignments"] = result["applied"]
                errors.extend(result["errors"])
                warnings.extend(result["warnings"])
                current_step += result["steps"]

        except Exception as e:
            logger.error(f"Error during restore processing with rollback: {e}")
            errors.append(f"Restore processing error: {str(e)}")

        duration = datetime.now() - start_time
        success = len(errors) == 0

        return RestoreResult(
            success=success,
            message=(
                "Restore completed successfully" if success else "Restore completed with errors"
            ),
            errors=errors,
            warnings=warnings,
            changes_applied=changes_applied,
            duration=duration,
        )

    async def _restore_users_with_rollback(
        self,
        users: List,
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore users with rollback tracking."""
        errors = []
        warnings = []
        applied = 0

        for i, user in enumerate(users):
            try:
                if progress_reporter:
                    await progress_reporter.update_progress(
                        operation_id, start_step + i, f"Restoring user: {user.user_name}"
                    )

                if not options.dry_run:
                    # Check if user exists
                    existing_user = await self._get_existing_user(user.user_name)

                    if existing_user:
                        # Handle conflict with rollback tracking
                        conflict = ConflictInfo(
                            resource_type=ResourceType.USERS,
                            resource_id=user.user_name,
                            conflict_type="user_exists",
                            existing_value=existing_user,
                            new_value=user.to_dict(),
                            suggested_action="overwrite",
                        )

                        action = await self.conflict_resolver.resolve_conflict(conflict)

                        if action == "overwrite":
                            # Create rollback action before updating
                            rollback_action = await self.rollback_manager.create_rollback_action(
                                "user", user.user_name, "update", {"previous_values": existing_user}
                            )
                            self.operation_state.add_rollback_action(rollback_action)

                            # Update user
                            await self._update_user(user, existing_user["UserId"])

                            # Track the change
                            self.operation_state.add_change(
                                "user", user.user_name, "update", existing_user, user.to_dict()
                            )

                            applied += 1
                        elif action == "skip":
                            warnings.append(f"Skipped existing user: {user.user_name}")
                    else:
                        # Create rollback action before creating
                        rollback_action = await self.rollback_manager.create_rollback_action(
                            "user", user.user_name, "create", {}
                        )
                        self.operation_state.add_rollback_action(rollback_action)

                        # Create new user
                        await self._create_user(user)

                        # Track the change
                        self.operation_state.add_change(
                            "user", user.user_name, "create", None, user.to_dict()
                        )

                        applied += 1
                else:
                    # Dry run - just count what would be applied
                    applied += 1

            except Exception as e:
                logger.error(f"Error restoring user {user.user_name}: {e}")
                errors.append(f"Failed to restore user {user.user_name}: {str(e)}")

        return {"applied": applied, "errors": errors, "warnings": warnings, "steps": len(users)}

    async def _restore_groups_with_rollback(
        self,
        groups: List,
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore groups with rollback tracking."""
        errors = []
        warnings = []
        applied = 0

        for i, group in enumerate(groups):
            try:
                if progress_reporter:
                    await progress_reporter.update_progress(
                        operation_id, start_step + i, f"Restoring group: {group.display_name}"
                    )

                if not options.dry_run:
                    # Check if group exists
                    existing_group = await self._get_existing_group(group.display_name)

                    if existing_group:
                        # Handle conflict with rollback tracking
                        conflict = ConflictInfo(
                            resource_type=ResourceType.GROUPS,
                            resource_id=group.display_name,
                            conflict_type="group_exists",
                            existing_value=existing_group,
                            new_value=group.to_dict(),
                            suggested_action="merge",
                        )

                        action = await self.conflict_resolver.resolve_conflict(conflict)

                        if action in ["overwrite", "merge"]:
                            # Create rollback action before updating
                            rollback_action = await self.rollback_manager.create_rollback_action(
                                "group",
                                group.display_name,
                                "update",
                                {"previous_values": existing_group},
                            )
                            self.operation_state.add_rollback_action(rollback_action)

                            # Update group
                            await self._update_group(group, existing_group["GroupId"])

                            # Track the change
                            self.operation_state.add_change(
                                "group",
                                group.display_name,
                                "update",
                                existing_group,
                                group.to_dict(),
                            )

                            applied += 1
                        elif action == "skip":
                            warnings.append(f"Skipped existing group: {group.display_name}")
                    else:
                        # Create rollback action before creating
                        rollback_action = await self.rollback_manager.create_rollback_action(
                            "group", group.display_name, "create", {}
                        )
                        self.operation_state.add_rollback_action(rollback_action)

                        # Create new group
                        await self._create_group(group)

                        # Track the change
                        self.operation_state.add_change(
                            "group", group.display_name, "create", None, group.to_dict()
                        )

                        applied += 1
                else:
                    applied += 1

            except Exception as e:
                logger.error(f"Error restoring group {group.display_name}: {e}")
                errors.append(f"Failed to restore group {group.display_name}: {str(e)}")

        return {"applied": applied, "errors": errors, "warnings": warnings, "steps": len(groups)}

    async def _restore_permission_sets_with_rollback(
        self,
        permission_sets: List,
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore permission sets with rollback tracking."""
        errors = []
        warnings = []
        applied = 0

        # Skip if no permission sets to restore
        if not permission_sets:
            return {"applied": 0, "errors": errors, "warnings": warnings, "steps": 0}

        # Get target instance ARN
        instance_arn = options.target_instance_arn
        if not instance_arn:
            warnings.append(
                "Target instance ARN not specified for permission set restore, skipping"
            )
            return {
                "applied": 0,
                "errors": errors,
                "warnings": warnings,
                "steps": len(permission_sets),
            }

        for i, ps in enumerate(permission_sets):
            try:
                if progress_reporter:
                    await progress_reporter.update_progress(
                        operation_id, start_step + i, f"Restoring permission set: {ps.name}"
                    )

                if not options.dry_run:
                    # Check if permission set exists
                    existing_ps = await self._get_existing_permission_set(ps.name, instance_arn)

                    if existing_ps:
                        # Handle conflict with rollback tracking
                        conflict = ConflictInfo(
                            resource_type=ResourceType.PERMISSION_SETS,
                            resource_id=ps.name,
                            conflict_type="permission_set_exists",
                            existing_value=existing_ps,
                            new_value=ps.to_dict(),
                            suggested_action="overwrite",
                        )

                        action = await self.conflict_resolver.resolve_conflict(conflict)

                        if action == "overwrite":
                            # Create rollback action before updating
                            rollback_action = await self.rollback_manager.create_rollback_action(
                                "permission_set",
                                ps.name,
                                "update",
                                {"previous_values": existing_ps, "instance_arn": instance_arn},
                            )
                            self.operation_state.add_rollback_action(rollback_action)

                            # Update permission set
                            await self._update_permission_set(
                                ps, existing_ps["PermissionSetArn"], instance_arn
                            )

                            # Track the change
                            self.operation_state.add_change(
                                "permission_set", ps.name, "update", existing_ps, ps.to_dict()
                            )

                            applied += 1
                        elif action == "skip":
                            warnings.append(f"Skipped existing permission set: {ps.name}")
                    else:
                        # Create rollback action before creating
                        rollback_action = await self.rollback_manager.create_rollback_action(
                            "permission_set", ps.name, "create", {"instance_arn": instance_arn}
                        )
                        self.operation_state.add_rollback_action(rollback_action)

                        # Create new permission set
                        await self._create_permission_set(ps, instance_arn)

                        # Track the change
                        self.operation_state.add_change(
                            "permission_set", ps.name, "create", None, ps.to_dict()
                        )

                        applied += 1
                else:
                    applied += 1

            except Exception as e:
                logger.error(f"Error restoring permission set {ps.name}: {e}")
                errors.append(f"Failed to restore permission set {ps.name}: {str(e)}")

        return {
            "applied": applied,
            "errors": errors,
            "warnings": warnings,
            "steps": len(permission_sets),
        }

    async def _restore_assignments_with_rollback(
        self,
        assignments: List,
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore assignments with rollback tracking."""
        errors = []
        warnings = []
        applied = 0

        # Skip if no assignments to restore
        if not assignments:
            return {"applied": 0, "errors": errors, "warnings": warnings, "steps": 0}

        # Get target instance ARN
        instance_arn = options.target_instance_arn
        if not instance_arn:
            warnings.append("Target instance ARN not specified for assignment restore, skipping")
            return {"applied": 0, "errors": errors, "warnings": warnings, "steps": len(assignments)}

        for i, assignment in enumerate(assignments):
            try:
                if progress_reporter:
                    await progress_reporter.update_progress(
                        operation_id,
                        start_step + i,
                        f"Restoring assignment for {assignment.principal_id}",
                    )

                if not options.dry_run:
                    # Check if assignment exists
                    existing_assignment = await self._get_existing_assignment(
                        assignment, instance_arn
                    )

                    if existing_assignment:
                        warnings.append(f"Assignment already exists for {assignment.principal_id}")
                    else:
                        # Create rollback action before creating
                        assignment_key = f"{assignment.account_id}:{assignment.permission_set_arn}:{assignment.principal_id}"
                        rollback_action = await self.rollback_manager.create_rollback_action(
                            "assignment",
                            assignment_key,
                            "create",
                            {"instance_arn": instance_arn, "assignment_data": assignment.to_dict()},
                        )
                        self.operation_state.add_rollback_action(rollback_action)

                        # Create new assignment
                        await self._create_assignment(assignment, instance_arn)

                        # Track the change
                        self.operation_state.add_change(
                            "assignment", assignment_key, "create", None, assignment.to_dict()
                        )

                        applied += 1
                else:
                    applied += 1

            except Exception as e:
                logger.error(f"Error restoring assignment for {assignment.principal_id}: {e}")
                errors.append(
                    f"Failed to restore assignment for {assignment.principal_id}: {str(e)}"
                )

        return {
            "applied": applied,
            "errors": errors,
            "warnings": warnings,
            "steps": len(assignments),
        }
