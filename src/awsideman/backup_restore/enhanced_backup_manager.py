"""
Enhanced backup manager with comprehensive error handling and recovery.

This module extends the base backup manager with advanced error handling,
retry logic, partial recovery, and detailed error reporting.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .error_handling import ErrorCategory, OperationState, RetryConfig, create_error_handling_system
from .interfaces import CollectorInterface, ProgressReporterInterface, StorageEngineInterface
from .manager import BackupManager
from .models import BackupData, BackupOptions, BackupResult, ResourceType

logger = logging.getLogger(__name__)


class EnhancedBackupManager(BackupManager):
    """
    Enhanced backup manager with comprehensive error handling and recovery capabilities.

    Extends the base BackupManager with:
    - Retry logic with exponential backoff
    - Partial backup recovery
    - Detailed error reporting with remediation suggestions
    - Operation state tracking for recovery
    """

    def __init__(
        self,
        collector: CollectorInterface,
        storage_engine: StorageEngineInterface,
        validator=None,
        progress_reporter: Optional[ProgressReporterInterface] = None,
        backup_monitor=None,
        instance_arn: str = "",
        source_account: str = "",
        source_region: str = "",
        retry_config: Optional[RetryConfig] = None,
    ):
        """
        Initialize enhanced backup manager.

        Args:
            collector: Data collector for Identity Center resources
            storage_engine: Storage engine for backup persistence
            validator: Optional backup validator
            progress_reporter: Optional progress reporter
            backup_monitor: Optional backup monitor
            instance_arn: Identity Center instance ARN
            source_account: Source AWS account ID
            source_region: Source AWS region
            retry_config: Optional retry configuration
        """
        super().__init__(
            collector=collector,
            storage_engine=storage_engine,
            validator=validator,
            progress_reporter=progress_reporter,
            backup_monitor=backup_monitor,
            instance_arn=instance_arn,
            source_account=source_account,
            source_region=source_region,
        )

        # Initialize error handling system
        self.error_handling = create_error_handling_system(retry_config)
        self.retry_handler = self.error_handling["retry_handler"]
        self.error_analyzer = self.error_handling["error_analyzer"]
        self.partial_recovery_manager = self.error_handling["partial_recovery_manager"]
        self.error_reporter = self.error_handling["error_reporter"]

        # Operation state tracking
        self._operation_states: Dict[str, OperationState] = {}

    async def create_backup(self, options: BackupOptions) -> BackupResult:
        """
        Create a new backup with enhanced error handling and recovery.

        Args:
            options: Configuration options for the backup operation

        Returns:
            BackupResult containing the outcome of the backup operation
        """
        operation_id = f"backup-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        # Initialize operation state for tracking and recovery
        operation_state = OperationState(
            operation_id=operation_id, operation_type="backup", start_time=start_time
        )
        self._operation_states[operation_id] = operation_state

        try:
            logger.info(
                f"Starting enhanced backup operation {operation_id} with type {options.backup_type.value}"
            )

            # Add initial checkpoint
            operation_state.add_checkpoint(
                "operation_start",
                {
                    "options": options.to_dict(),
                    "instance_arn": self.instance_arn,
                    "source_account": self.source_account,
                    "source_region": self.source_region,
                },
            )

            # Execute backup with retry logic
            result = await self.retry_handler.execute_with_retry(
                self._execute_backup_with_recovery,
                options,
                operation_state,
                context={"operation_id": operation_id, "operation_type": "backup"},
            )

            operation_state.completed = True
            operation_state.success = result.success

            return result

        except Exception as e:
            logger.error(f"Enhanced backup operation {operation_id} failed: {e}")

            # Analyze the error
            error_info = self.error_analyzer.analyze_error(
                e,
                {
                    "operation_id": operation_id,
                    "operation_type": "backup",
                    "options": options.to_dict(),
                },
            )

            # Attempt partial recovery if possible
            recovery_result = None
            if error_info.recoverable and error_info.category != ErrorCategory.VALIDATION:
                logger.info(f"Attempting partial recovery for operation {operation_id}")
                recovery_result = await self.partial_recovery_manager.attempt_partial_recovery(
                    "backup", operation_state, error_info
                )

            # Generate detailed error report
            error_report = self.error_reporter.generate_error_report(
                [error_info],
                {
                    "operation_id": operation_id,
                    "operation_type": "backup",
                    "options": options.to_dict(),
                    "recovery_attempted": recovery_result is not None,
                },
            )

            # Create enhanced failure result
            result = BackupResult(
                success=False,
                message=f"Backup operation failed: {error_info.message}",
                errors=[error_info.message] + error_info.suggested_actions,
                duration=datetime.now() - start_time,
            )

            # Add recovery information if available
            if recovery_result and recovery_result.get("success"):
                result.message += f" (Partial recovery: {recovery_result['message']})"
                result.warnings = [f"Partial backup available: {recovery_result['message']}"]

                # If we have recovered data, try to store it as a partial backup
                if recovery_result.get("recovered_data"):
                    try:
                        partial_backup_id = await self._store_partial_backup(
                            recovery_result["recovered_data"], operation_id
                        )
                        result.backup_id = partial_backup_id
                        result.warnings.append(f"Partial backup stored as: {partial_backup_id}")
                    except Exception as store_error:
                        logger.error(f"Failed to store partial backup: {store_error}")
                        result.errors.append(f"Failed to store partial backup: {store_error}")

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

    async def _execute_backup_with_recovery(
        self, options: BackupOptions, operation_state: OperationState
    ) -> BackupResult:
        """
        Execute backup operation with recovery checkpoints.

        Args:
            options: Backup options
            operation_state: Operation state for tracking

        Returns:
            BackupResult
        """
        operation_id = operation_state.operation_id
        start_time = operation_state.start_time

        # Initialize progress tracking
        total_steps = self._calculate_backup_steps(options)
        if self.progress_reporter:
            await self.progress_reporter.start_operation(
                operation_id,
                total_steps,
                f"Creating {options.backup_type.value} backup with error recovery",
            )

        # Step 1: Validate connection with retry
        await self._update_progress(operation_id, 1, "Validating connection")
        validation_result = await self.retry_handler.execute_with_retry(
            self.collector.validate_connection,
            context={"step": "connection_validation", "operation_id": operation_id},
        )

        if not validation_result.is_valid:
            raise ValueError(f"Connection validation failed: {'; '.join(validation_result.errors)}")

        operation_state.add_checkpoint(
            "connection_validated", {"validation_result": validation_result.to_dict()}
        )

        # Step 2: Collect data with recovery checkpoints
        await self._update_progress(operation_id, 2, "Collecting data with recovery points")
        backup_data = await self._collect_data_with_checkpoints(options, operation_state)

        # Step 3: Create metadata
        backup_id = f"{options.backup_type.value}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        backup_data.metadata = self._create_backup_metadata(backup_id, options, backup_data)

        operation_state.add_checkpoint(
            "metadata_created", {"backup_id": backup_id, "metadata": backup_data.metadata.to_dict()}
        )

        # Step 4: Validate backup data with retry
        await self._update_progress(operation_id, 4, "Validating backup data")
        validation_result = await self.retry_handler.execute_with_retry(
            self.validator.validate_backup_data,
            backup_data,
            context={"step": "data_validation", "operation_id": operation_id},
        )

        if not validation_result.is_valid:
            # Check for critical errors
            critical_errors = [e for e in validation_result.errors if "critical" in e.lower()]
            if critical_errors:
                raise ValueError(f"Critical validation errors: {'; '.join(critical_errors)}")

        operation_state.add_checkpoint(
            "data_validated", {"validation_result": validation_result.to_dict()}
        )

        # Step 5: Store backup with retry
        await self._update_progress(operation_id, 5, "Storing backup")
        stored_backup_id = await self.retry_handler.execute_with_retry(
            self.storage_engine.store_backup,
            backup_data,
            context={"step": "storage", "operation_id": operation_id},
        )

        if not stored_backup_id:
            raise RuntimeError("Failed to store backup data")

        operation_state.add_checkpoint("backup_stored", {"stored_backup_id": stored_backup_id})

        # Step 6: Verify integrity with retry
        await self._update_progress(operation_id, 6, "Verifying integrity")
        integrity_result = await self.retry_handler.execute_with_retry(
            self.storage_engine.verify_integrity,
            stored_backup_id,
            context={"step": "integrity_verification", "operation_id": operation_id},
        )

        if not integrity_result.is_valid:
            # Try to clean up failed backup
            try:
                await self.storage_engine.delete_backup(stored_backup_id)
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup invalid backup {stored_backup_id}: {cleanup_error}"
                )

            raise RuntimeError(
                f"Backup integrity verification failed: {'; '.join(integrity_result.errors)}"
            )

        # Complete operation
        duration = datetime.now() - start_time
        await self._complete_operation(operation_id, True, "Backup completed successfully")

        return BackupResult(
            success=True,
            backup_id=stored_backup_id,
            message=f"Enhanced backup created successfully in {duration.total_seconds():.2f} seconds",
            warnings=validation_result.warnings if validation_result else [],
            metadata=backup_data.metadata,
            duration=duration,
        )

    async def _collect_data_with_checkpoints(
        self, options: BackupOptions, operation_state: OperationState
    ) -> BackupData:
        """
        Collect backup data with recovery checkpoints.

        Args:
            options: Backup options
            operation_state: Operation state for checkpoints

        Returns:
            BackupData with collected resources
        """
        operation_id = operation_state.operation_id
        collected_data = {}

        # Collect users with checkpoint
        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.USERS in options.resource_types
        ):
            await self._update_progress(operation_id, 3, "Collecting users")
            try:
                users = await self.retry_handler.execute_with_retry(
                    self.collector.collect_users,
                    options,
                    context={"resource_type": "users", "operation_id": operation_id},
                )
                collected_data["users"] = users
                operation_state.add_checkpoint("collected_users", users)
                logger.info(f"Successfully collected {len(users)} users")
            except Exception as e:
                logger.error(f"Failed to collect users: {e}")
                # Continue with other resources
                collected_data["users"] = []

        # Collect groups with checkpoint
        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.GROUPS in options.resource_types
        ):
            await self._update_progress(operation_id, 3, "Collecting groups")
            try:
                groups = await self.retry_handler.execute_with_retry(
                    self.collector.collect_groups,
                    options,
                    context={"resource_type": "groups", "operation_id": operation_id},
                )
                collected_data["groups"] = groups
                operation_state.add_checkpoint("collected_groups", groups)
                logger.info(f"Successfully collected {len(groups)} groups")
            except Exception as e:
                logger.error(f"Failed to collect groups: {e}")
                collected_data["groups"] = []

        # Collect permission sets with checkpoint
        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.PERMISSION_SETS in options.resource_types
        ):
            await self._update_progress(operation_id, 3, "Collecting permission sets")
            try:
                permission_sets = await self.retry_handler.execute_with_retry(
                    self.collector.collect_permission_sets,
                    options,
                    context={"resource_type": "permission_sets", "operation_id": operation_id},
                )
                collected_data["permission_sets"] = permission_sets
                operation_state.add_checkpoint("collected_permission_sets", permission_sets)
                logger.info(f"Successfully collected {len(permission_sets)} permission sets")
            except Exception as e:
                logger.error(f"Failed to collect permission sets: {e}")
                collected_data["permission_sets"] = []

        # Collect assignments with checkpoint
        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.ASSIGNMENTS in options.resource_types
        ):
            await self._update_progress(operation_id, 3, "Collecting assignments")
            try:
                assignments = await self.retry_handler.execute_with_retry(
                    self.collector.collect_assignments,
                    options,
                    context={"resource_type": "assignments", "operation_id": operation_id},
                )
                collected_data["assignments"] = assignments
                operation_state.add_checkpoint("collected_assignments", assignments)
                logger.info(f"Successfully collected {len(assignments)} assignments")
            except Exception as e:
                logger.error(f"Failed to collect assignments: {e}")
                collected_data["assignments"] = []

        # Build relationships
        relationships = self._build_relationships(
            collected_data.get("users", []),
            collected_data.get("groups", []),
            collected_data.get("permission_sets", []),
            collected_data.get("assignments", []),
        )

        # Create temporary metadata (will be replaced)
        from .models import BackupMetadata, EncryptionMetadata, RetentionPolicy

        temp_metadata = BackupMetadata(
            backup_id="temp",
            timestamp=datetime.now(),
            instance_arn=self.instance_arn,
            backup_type=options.backup_type,
            version="1.0.0",
            source_account=self.source_account,
            source_region=self.source_region,
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        return BackupData(
            metadata=temp_metadata,
            users=collected_data.get("users", []),
            groups=collected_data.get("groups", []),
            permission_sets=collected_data.get("permission_sets", []),
            assignments=collected_data.get("assignments", []),
            relationships=relationships,
        )

    async def _store_partial_backup(self, recovered_data: Dict[str, Any], operation_id: str) -> str:
        """
        Store partial backup data from recovery.

        Args:
            recovered_data: Recovered backup data
            operation_id: Original operation ID

        Returns:
            Backup ID of stored partial backup
        """
        try:
            # Convert dict back to BackupData if needed
            if isinstance(recovered_data, dict) and "metadata" in recovered_data:
                from .models import BackupData

                backup_data = BackupData.from_dict(recovered_data)
            else:
                # Create BackupData from recovered resources
                backup_data = self._create_backup_data_from_recovery(recovered_data, operation_id)

            # Store the partial backup
            partial_backup_id = await self.storage_engine.store_backup(backup_data)
            logger.info(f"Stored partial backup as {partial_backup_id}")

            return partial_backup_id

        except Exception as e:
            logger.error(f"Failed to store partial backup: {e}")
            raise

    def _create_backup_data_from_recovery(
        self, recovered_data: Dict[str, Any], operation_id: str
    ) -> BackupData:
        """Create BackupData from recovered resources."""
        from .models import (
            BackupData,
            BackupMetadata,
            BackupType,
            EncryptionMetadata,
            RetentionPolicy,
        )

        # Create metadata for partial backup
        backup_id = f"partial-{operation_id}"
        metadata = BackupMetadata(
            backup_id=backup_id,
            timestamp=datetime.now(),
            instance_arn=self.instance_arn,
            backup_type=BackupType.FULL,  # Mark as full even though partial
            version="1.0.0-partial",
            source_account=self.source_account,
            source_region=self.source_region,
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        # Create backup data with recovered resources
        return BackupData(
            metadata=metadata,
            users=recovered_data.get("users", []),
            groups=recovered_data.get("groups", []),
            permission_sets=recovered_data.get("permission_sets", []),
            assignments=recovered_data.get("assignments", []),
        )

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
                }
            )
        return states

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
