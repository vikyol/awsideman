"""
Backup manager implementation for orchestrating backup operations.

This module provides the main BackupManager class that coordinates the entire
backup workflow including data collection, validation, and storage.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .interfaces import (
    BackupManagerInterface,
    CollectorInterface,
    ProgressReporterInterface,
    StorageEngineInterface,
)
from .models import (
    BackupData,
    BackupMetadata,
    BackupOptions,
    BackupResult,
    BackupType,
    EncryptionMetadata,
    ResourceType,
    RetentionPolicy,
    ValidationResult,
)
from .monitoring import BackupMonitor, OperationType
from .performance import PerformanceOptimizer
from .validation import BackupValidator

logger = logging.getLogger(__name__)


class BackupManager(BackupManagerInterface):
    """
    Main backup manager that orchestrates backup operations.

    Coordinates between data collection, validation, and storage to provide
    a complete backup solution with error recovery and progress tracking.
    """

    def __init__(
        self,
        collector: CollectorInterface,
        storage_engine: StorageEngineInterface,
        validator: Optional[BackupValidator] = None,
        progress_reporter: Optional[ProgressReporterInterface] = None,
        backup_monitor: Optional[BackupMonitor] = None,
        performance_optimizer: Optional[PerformanceOptimizer] = None,
        instance_arn: str = "",
        source_account: str = "",
        source_region: str = "",
    ):
        """
        Initialize backup manager.

        Args:
            collector: Data collector for Identity Center resources
            storage_engine: Storage engine for backup persistence
            validator: Optional backup validator
            progress_reporter: Optional progress reporter
            instance_arn: Identity Center instance ARN
            source_account: Source AWS account ID
            source_region: Source AWS region
        """
        self.collector = collector
        self.storage_engine = storage_engine
        self.validator = validator or BackupValidator()
        self.progress_reporter = progress_reporter
        self.backup_monitor = backup_monitor
        self.performance_optimizer = performance_optimizer or PerformanceOptimizer()
        self.instance_arn = instance_arn
        self.source_account = source_account
        self.source_region = source_region

        # Operation tracking
        self._active_operations: Dict[str, Dict[str, Any]] = {}

    async def create_backup(self, options: BackupOptions) -> BackupResult:
        """
        Create a new backup with the specified options.

        Args:
            options: Configuration options for the backup operation

        Returns:
            BackupResult containing the outcome of the backup operation
        """
        operation_id = f"backup-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()

        try:
            logger.info(
                f"Starting backup operation {operation_id} with type {options.backup_type.value}"
            )

            # Track operation
            self._active_operations[operation_id] = {
                "type": "backup",
                "start_time": start_time,
                "options": options,
                "status": "initializing",
            }

            # Initialize progress tracking
            total_steps = self._calculate_backup_steps(options)
            if self.progress_reporter:
                await self.progress_reporter.start_operation(
                    operation_id, total_steps, f"Creating {options.backup_type.value} backup"
                )

            # Initialize monitoring
            if self.backup_monitor:
                await self.backup_monitor.start_operation_monitoring(
                    operation_id,
                    OperationType.BACKUP,
                    total_steps,
                    f"Creating {options.backup_type.value} backup",
                )

            # Step 1: Validate connection and permissions
            await self._update_progress(operation_id, 1, "Validating connection")
            validation_result = await self.collector.validate_connection()
            if not validation_result.is_valid:
                return BackupResult(
                    success=False,
                    message="Connection validation failed",
                    errors=validation_result.errors,
                    warnings=validation_result.warnings,
                )

            # Step 2: Validate cross-account configurations if present
            if options.cross_account_configs:
                await self._update_progress(operation_id, 2, "Validating cross-account access")
                cross_account_validation = await self.collector.validate_cross_account_access(
                    options.cross_account_configs
                )
                if not cross_account_validation.is_valid:
                    return BackupResult(
                        success=False,
                        message="Cross-account validation failed",
                        errors=cross_account_validation.errors,
                        warnings=cross_account_validation.warnings,
                    )

            # Step 3: Collect data based on backup type
            await self._update_progress(operation_id, 3, "Collecting data")
            self._active_operations[operation_id]["status"] = "collecting"

            if options.backup_type == BackupType.INCREMENTAL and options.since:
                backup_data = await self.collector.collect_incremental(options.since, options)

                # Early detection: Check if incremental backup contains any actual changes
                # For now, we'll use a simple heuristic: if all resource counts match the previous backup
                # and the since date is recent, we can assume no changes

                # Get the most recent backup to compare against
                try:
                    recent_backups = await self.storage_engine.list_backups()
                    if recent_backups:
                        # Sort by timestamp and get the most recent
                        recent_backups.sort(key=lambda x: x.timestamp, reverse=True)
                        latest_backup = recent_backups[0]

                        if latest_backup:
                            # Compare resource counts
                            current_counts = {
                                "users": len(backup_data.users),
                                "groups": len(backup_data.groups),
                                "permission_sets": len(backup_data.permission_sets),
                                "assignments": len(backup_data.assignments),
                            }

                            previous_counts = latest_backup.resource_counts or {}

                            # Check if counts are identical
                            counts_match = all(
                                current_counts.get(key, 0) == previous_counts.get(key, 0)
                                for key in current_counts.keys()
                            )

                            # If counts match and since date is very recent (within last hour), likely no changes
                            time_since_last = datetime.now() - latest_backup.timestamp
                            very_recent = time_since_last.total_seconds() < 3600  # 1 hour

                            if counts_match and very_recent:
                                logger.info(
                                    "No changes detected since last backup, skipping incremental backup creation"
                                )
                                await self._complete_operation(
                                    operation_id, True, "No changes detected, backup skipped"
                                )

                                return BackupResult(
                                    success=True,
                                    backup_id=None,
                                    message="No changes detected since last backup",
                                    warnings=["Incremental backup skipped - no changes found"],
                                    metadata=None,
                                    duration=datetime.now() - start_time,
                                )
                except Exception as e:
                    logger.warning(
                        f"Could not compare with previous backup for early detection: {e}"
                    )
                    # Continue with backup creation if comparison fails
            else:
                backup_data = await self._collect_full_backup(options, operation_id)

            # Step 4: Collect cross-account data if configured
            cross_account_data = {}
            if options.cross_account_configs:
                await self._update_progress(operation_id, 4, "Collecting cross-account data")
                cross_account_data = await self.collector.collect_cross_account_data(options)

                # Merge cross-account data into main backup (simplified approach)
                if cross_account_data:
                    await self._merge_cross_account_data(backup_data, cross_account_data)

            # Step 5: Detect duplicates before creating metadata (if enabled)
            if not options.skip_duplicate_check:
                await self._update_progress(operation_id, 5, "Checking for duplicates")
                duplicate_backup_id = await self._detect_duplicate_backup(backup_data)

                if duplicate_backup_id:
                    logger.info(f"Duplicate backup detected, identical to {duplicate_backup_id}")

                    # Handle duplicate based on options
                    if options.delete_duplicates:
                        logger.info(f"Deleting duplicate backup {duplicate_backup_id}")
                        try:
                            await self.storage_engine.delete_backup(duplicate_backup_id)
                            logger.info(
                                f"Successfully deleted duplicate backup {duplicate_backup_id}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete duplicate backup {duplicate_backup_id}: {e}"
                            )

                    await self._complete_operation(
                        operation_id,
                        True,
                        f"Duplicate backup detected, identical to {duplicate_backup_id}",
                    )

                    return BackupResult(
                        success=True,
                        backup_id=None,
                        message=f"Duplicate backup detected, identical to {duplicate_backup_id}",
                        warnings=["Backup skipped - no changes detected since last backup"],
                        metadata=None,
                        duration=datetime.now() - start_time,
                    )
            else:
                await self._update_progress(operation_id, 5, "Skipping duplicate check")
                logger.info("Duplicate detection skipped by user request")

            # Step 6: Generate unique backup ID
            backup_id = f"{options.backup_type.value}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}-{uuid.uuid4().hex[:8]}"

            # Step 7: Create and populate metadata
            await self._update_progress(operation_id, 7, "Creating metadata")
            backup_data.metadata = self._create_backup_metadata(backup_id, options, backup_data)

            # Step 8: Validate backup data
            await self._update_progress(operation_id, 8, "Validating backup data")
            self._active_operations[operation_id]["status"] = "validating"

            validation_result = await self.validator.validate_backup_data(backup_data)
            if not validation_result.is_valid:
                logger.warning(
                    f"Backup validation failed for {backup_id}: {validation_result.errors}"
                )
                # Continue with warnings but fail on critical errors
                critical_errors = [e for e in validation_result.errors if "critical" in e.lower()]
                if critical_errors:
                    return BackupResult(
                        success=False,
                        message="Critical validation errors found",
                        errors=critical_errors,
                        warnings=validation_result.warnings,
                    )

            # Step 9: Optimize backup data for storage
            await self._update_progress(operation_id, 9, "Optimizing backup data")
            self._active_operations[operation_id]["status"] = "optimizing"

            try:
                optimized_data, optimization_metadata = (
                    await self.performance_optimizer.optimize_backup_data(backup_data)
                )
                logger.info(
                    f"Backup optimization completed: {optimization_metadata['original_size']} -> "
                    f"{optimization_metadata['final_size']} bytes "
                    f"(ratio: {optimization_metadata['total_reduction_ratio']:.2f}x)"
                )
                # Store optimization metadata in backup metadata
                backup_data.metadata.optimization_info = optimization_metadata
            except Exception as e:
                logger.warning(
                    f"Performance optimization failed, proceeding with unoptimized data: {e}"
                )
                optimization_metadata = {}

            # Step 10: Store backup
            await self._update_progress(operation_id, 10, "Storing backup")
            self._active_operations[operation_id]["status"] = "storing"

            # Store backup data
            stored_backup_id = await self.storage_engine.store_backup(backup_data)
            if not stored_backup_id:
                return BackupResult(
                    success=False,
                    message="Failed to store backup data",
                    errors=["Storage operation failed"],
                )

            # Step 11: Verify stored backup integrity
            await self._update_progress(operation_id, 11, "Verifying integrity")
            integrity_result = await self.storage_engine.verify_integrity(stored_backup_id)
            if not integrity_result.is_valid:
                logger.error(f"Backup integrity verification failed for {stored_backup_id}")
                # Try to clean up failed backup
                await self.storage_engine.delete_backup(stored_backup_id)
                return BackupResult(
                    success=False,
                    message="Backup integrity verification failed",
                    errors=integrity_result.errors,
                    warnings=integrity_result.warnings,
                )

            # Complete operation
            duration = datetime.now() - start_time
            await self._complete_operation(operation_id, True, "Backup completed successfully")

            # Create result
            result = BackupResult(
                success=True,
                backup_id=stored_backup_id,
                message=f"Backup created successfully in {duration.total_seconds():.2f} seconds",
                warnings=validation_result.warnings if validation_result else [],
                metadata=backup_data.metadata,
                duration=duration,
            )

            # Complete monitoring
            if self.backup_monitor:
                await self.backup_monitor.complete_operation_monitoring(operation_id, True, result)

            logger.info(
                f"Backup operation {operation_id} completed successfully: {stored_backup_id}"
            )

            return result

        except Exception as e:
            logger.error(f"Backup operation {operation_id} failed: {e}")
            await self._complete_operation(operation_id, False, f"Backup failed: {e}")

            # Create failure result
            result = BackupResult(
                success=False,
                message=f"Backup operation failed: {e}",
                errors=[str(e)],
                duration=datetime.now() - start_time,
            )

            # Complete monitoring with failure
            if self.backup_monitor:
                await self.backup_monitor.complete_operation_monitoring(operation_id, False, result)

            return result

        finally:
            # Clean up operation tracking
            self._active_operations.pop(operation_id, None)

    async def list_backups(self, filters: Optional[Dict[str, Any]] = None) -> List[BackupMetadata]:
        """
        List available backups with optional filtering.

        Args:
            filters: Optional filters to apply to the backup list

        Returns:
            List of backup metadata objects
        """
        try:
            logger.debug("Listing backups")
            return await self.storage_engine.list_backups(filters)
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []

    async def validate_backup(self, backup_id: str) -> ValidationResult:
        """
        Validate the integrity and completeness of a backup.

        Args:
            backup_id: Unique identifier of the backup to validate

        Returns:
            ValidationResult containing validation status and details
        """
        try:
            logger.info(f"Validating backup {backup_id}")

            # First check storage integrity
            storage_validation = await self.storage_engine.verify_integrity(backup_id)
            if not storage_validation.is_valid:
                return storage_validation

            # Retrieve and validate backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                return ValidationResult(
                    is_valid=False,
                    errors=[f"Backup {backup_id} not found or could not be retrieved"],
                    warnings=[],
                    details={},
                )

            # Validate backup data structure and content
            data_validation = await self.validator.validate_backup_data(backup_data)

            # Combine results
            combined_errors = storage_validation.errors + data_validation.errors
            combined_warnings = storage_validation.warnings + data_validation.warnings
            combined_details = {**storage_validation.details, **data_validation.details}

            is_valid = len(combined_errors) == 0

            logger.info(f"Backup validation for {backup_id}: {'passed' if is_valid else 'failed'}")

            return ValidationResult(
                is_valid=is_valid,
                errors=combined_errors,
                warnings=combined_warnings,
                details=combined_details,
            )

        except Exception as e:
            logger.error(f"Failed to validate backup {backup_id}: {e}")
            return ValidationResult(
                is_valid=False, errors=[f"Validation failed: {e}"], warnings=[], details={}
            )

    async def delete_backup(self, backup_id: str) -> bool:
        """
        Delete a backup and all associated data.

        Args:
            backup_id: Unique identifier of the backup to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            logger.info(f"Deleting backup {backup_id}")
            return await self.storage_engine.delete_backup(backup_id)
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_id}: {e}")
            return False

    async def get_backup_metadata(self, backup_id: str) -> Optional[BackupMetadata]:
        """
        Retrieve metadata for a specific backup.

        Args:
            backup_id: Unique identifier of the backup

        Returns:
            BackupMetadata if found, None otherwise
        """
        try:
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            return backup_data.metadata if backup_data else None
        except Exception as e:
            logger.error(f"Failed to get metadata for backup {backup_id}: {e}")
            return None

    async def get_operation_status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of an active backup operation.

        Args:
            operation_id: Unique identifier of the operation

        Returns:
            Operation status information if found, None otherwise
        """
        operation = self._active_operations.get(operation_id)
        if not operation:
            return None

        status = operation.copy()
        if self.progress_reporter:
            progress = await self.progress_reporter.get_progress(operation_id)
            if progress:
                status["progress"] = progress

        return status

    async def cancel_operation(self, operation_id: str) -> bool:
        """
        Cancel an active backup operation.

        Args:
            operation_id: Unique identifier of the operation to cancel

        Returns:
            True if cancellation was successful, False otherwise
        """
        if operation_id not in self._active_operations:
            return False

        try:
            logger.info(f"Cancelling backup operation {operation_id}")

            # Mark operation as cancelled
            self._active_operations[operation_id]["status"] = "cancelled"

            # Complete progress tracking
            if self.progress_reporter:
                await self.progress_reporter.complete_operation(
                    operation_id, False, "Operation cancelled by user"
                )

            # Clean up
            self._active_operations.pop(operation_id, None)

            return True

        except Exception as e:
            logger.error(f"Failed to cancel operation {operation_id}: {e}")
            return False

    def _calculate_backup_steps(self, options: BackupOptions) -> int:
        """Calculate total number of steps for progress tracking."""
        base_steps = 11  # validate, cross-account-validate, collect, cross-account-collect, duplicate-check, metadata, validate, optimize, store, verify

        # Add steps for cross-account operations
        if options.cross_account_configs:
            base_steps += len(options.cross_account_configs)  # One step per cross-account config

        # Add steps based on resource types
        resource_count = len(options.resource_types)
        if ResourceType.ALL in options.resource_types:
            resource_count = 4  # users, groups, permission_sets, assignments

        return base_steps + resource_count

    async def _collect_full_backup(self, options: BackupOptions, operation_id: str) -> BackupData:
        """Collect data for a full backup."""
        users = []
        groups = []
        permission_sets = []
        assignments = []

        step = 2  # Starting after connection validation

        # Collect based on resource types
        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.USERS in options.resource_types
        ):
            await self._update_progress(operation_id, step, "Collecting users")
            users = await self.collector.collect_users(options)
            step += 1

        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.GROUPS in options.resource_types
        ):
            await self._update_progress(operation_id, step, "Collecting groups")
            groups = await self.collector.collect_groups(options)
            step += 1

        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.PERMISSION_SETS in options.resource_types
        ):
            await self._update_progress(operation_id, step, "Collecting permission sets")
            permission_sets = await self.collector.collect_permission_sets(options)
            step += 1

        if (
            ResourceType.ALL in options.resource_types
            or ResourceType.ASSIGNMENTS in options.resource_types
        ):
            await self._update_progress(operation_id, step, "Collecting assignments")
            assignments = await self.collector.collect_assignments(options)
            step += 1

        # Build relationships
        await self._update_progress(operation_id, step, "Building relationships")
        relationships = self._build_relationships(users, groups, permission_sets, assignments)

        # Create temporary metadata (will be replaced with proper metadata)
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
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
            relationships=relationships,
        )

    def _create_backup_metadata(
        self, backup_id: str, options: BackupOptions, backup_data: BackupData
    ) -> BackupMetadata:
        """Create backup metadata from options and collected data."""
        return BackupMetadata(
            backup_id=backup_id,
            timestamp=datetime.now(),
            instance_arn=self.instance_arn,
            backup_type=options.backup_type,
            version="1.0.0",
            source_account=self.source_account,
            source_region=self.source_region,
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(encrypted=options.encryption_enabled),
            resource_counts={
                "users": len(backup_data.users),
                "groups": len(backup_data.groups),
                "permission_sets": len(backup_data.permission_sets),
                "assignments": len(backup_data.assignments),
            },
        )

    def _build_relationships(self, users, groups, permission_sets, assignments):
        """Build relationship mappings between resources."""
        from .models import RelationshipMap

        relationships = RelationshipMap()

        # Build user-group relationships
        for group in groups:
            for member_id in group.members:
                if member_id not in relationships.user_groups:
                    relationships.user_groups[member_id] = []
                relationships.user_groups[member_id].append(group.group_id)

                if group.group_id not in relationships.group_members:
                    relationships.group_members[group.group_id] = []
                relationships.group_members[group.group_id].append(member_id)

        # Build permission set assignment relationships
        for assignment in assignments:
            ps_arn = assignment.permission_set_arn
            assignment_key = (
                f"{assignment.account_id}:{assignment.principal_type}:{assignment.principal_id}"
            )

            if ps_arn not in relationships.permission_set_assignments:
                relationships.permission_set_assignments[ps_arn] = []
            relationships.permission_set_assignments[ps_arn].append(assignment_key)

        return relationships

    async def _update_progress(self, operation_id: str, step: int, message: str) -> None:
        """Update progress for an operation."""
        if self.progress_reporter:
            await self.progress_reporter.update_progress(operation_id, step, message)

        if self.backup_monitor:
            await self.backup_monitor.update_operation_progress(operation_id, step, message)

    async def _complete_operation(self, operation_id: str, success: bool, message: str) -> None:
        """Complete an operation."""
        if self.progress_reporter:
            await self.progress_reporter.complete_operation(operation_id, success, message)

    async def _merge_cross_account_data(
        self, main_backup: BackupData, cross_account_data: Dict[str, BackupData]
    ) -> None:
        """
        Merge cross-account backup data into the main backup.

        Args:
            main_backup: Main backup data to merge into
            cross_account_data: Dictionary of account ID to backup data
        """
        logger.info(f"Merging data from {len(cross_account_data)} cross-account sources")

        for account_id, account_backup in cross_account_data.items():
            logger.debug(f"Merging data from account {account_id}")

            # Merge users (avoid duplicates by user_name)
            existing_user_names = {user.user_name for user in main_backup.users}
            for user in account_backup.users:
                if user.user_name not in existing_user_names:
                    main_backup.users.append(user)
                    existing_user_names.add(user.user_name)

            # Merge groups (avoid duplicates by display_name)
            existing_group_names = {group.display_name for group in main_backup.groups}
            for group in account_backup.groups:
                if group.display_name not in existing_group_names:
                    main_backup.groups.append(group)
                    existing_group_names.add(group.display_name)

            # Merge permission sets (avoid duplicates by name)
            existing_ps_names = {ps.name for ps in main_backup.permission_sets}
            for ps in account_backup.permission_sets:
                if ps.name not in existing_ps_names:
                    main_backup.permission_sets.append(ps)
                    existing_ps_names.add(ps.name)

            # Merge assignments (assignments are unique by combination of fields)
            existing_assignments = {
                (a.account_id, a.permission_set_arn, a.principal_type, a.principal_id)
                for a in main_backup.assignments
            }
            for assignment in account_backup.assignments:
                assignment_key = (
                    assignment.account_id,
                    assignment.permission_set_arn,
                    assignment.principal_type,
                    assignment.principal_id,
                )
                if assignment_key not in existing_assignments:
                    main_backup.assignments.append(assignment)
                    existing_assignments.add(assignment_key)

            # Merge relationships
            for user_id, group_ids in account_backup.relationships.user_groups.items():
                if user_id not in main_backup.relationships.user_groups:
                    main_backup.relationships.user_groups[user_id] = []
                main_backup.relationships.user_groups[user_id].extend(group_ids)

            for group_id, member_ids in account_backup.relationships.group_members.items():
                if group_id not in main_backup.relationships.group_members:
                    main_backup.relationships.group_members[group_id] = []
                main_backup.relationships.group_members[group_id].extend(member_ids)

            for (
                ps_arn,
                assignment_ids,
            ) in account_backup.relationships.permission_set_assignments.items():
                if ps_arn not in main_backup.relationships.permission_set_assignments:
                    main_backup.relationships.permission_set_assignments[ps_arn] = []
                main_backup.relationships.permission_set_assignments[ps_arn].extend(assignment_ids)

        # Recalculate checksums and resource counts after merging
        main_backup._update_resource_counts()
        main_backup._calculate_checksums()

        logger.info(
            f"Merged cross-account data: {len(main_backup.users)} users, "
            f"{len(main_backup.groups)} groups, {len(main_backup.permission_sets)} permission sets, "
            f"{len(main_backup.assignments)} assignments"
        )

    async def _detect_duplicate_backup(self, current_backup: BackupData) -> Optional[str]:
        """
        Detect if the current backup is a duplicate of the most recent backup.

        This method performs a comprehensive comparison between the current backup data
        and the most recent stored backup to determine if they are identical.

        Args:
            current_backup: The backup data that was just collected

        Returns:
            Backup ID of the duplicate if found, None if no duplicate detected
        """
        try:
            # Get the most recent backup
            recent_backups = await self.storage_engine.list_backups()
            if not recent_backups:
                logger.debug("No recent backups found for duplicate detection")
                return None

            # Sort by timestamp and get the most recent
            recent_backups.sort(key=lambda x: x.timestamp, reverse=True)
            latest_backup_metadata = recent_backups[0]

            logger.debug(
                f"Comparing against most recent backup: {latest_backup_metadata.backup_id} from {latest_backup_metadata.timestamp}"
            )

            if not latest_backup_metadata:
                return None

            # Load the actual backup data for comparison
            latest_backup_data = await self.storage_engine.retrieve_backup(
                latest_backup_metadata.backup_id
            )
            if not latest_backup_data:
                logger.warning(
                    f"Could not load latest backup {latest_backup_metadata.backup_id} for comparison"
                )
                return None

            # Compare resource counts first (quick check)
            current_counts = {
                "users": len(current_backup.users),
                "groups": len(current_backup.groups),
                "permission_sets": len(current_backup.permission_sets),
                "assignments": len(current_backup.assignments),
            }

            latest_counts = latest_backup_data.metadata.resource_counts or {}

            # If resource counts don't match, definitely not a duplicate
            if current_counts != latest_counts:
                logger.debug("Resource counts differ, not a duplicate")
                return None

            # If counts match, perform deeper content comparison
            # This is more expensive but necessary for accurate duplicate detection

            # Compare users (by user_name and attributes)
            if not self._compare_users(current_backup.users, latest_backup_data.users):
                logger.debug("User data differs, not a duplicate")
                return None

            # Compare groups (by display_name and members)
            if not self._compare_groups(current_backup.groups, latest_backup_data.groups):
                logger.debug("Group data differs, not a duplicate")
                return None

            # Compare permission sets (by name and attributes)
            if not self._compare_permission_sets(
                current_backup.permission_sets, latest_backup_data.permission_sets
            ):
                logger.debug("Permission set data differs, not a duplicate")
                return None

            # Compare assignments (by unique combination of fields)
            if not self._compare_assignments(
                current_backup.assignments, latest_backup_data.assignments
            ):
                logger.debug("Assignment data differs, not a duplicate")
                return None

            # If we get here, all data is identical - this is a duplicate
            logger.info(
                f"Duplicate backup detected: identical to {latest_backup_metadata.backup_id}"
            )
            return latest_backup_metadata.backup_id

        except Exception as e:
            logger.warning(f"Error during duplicate detection: {e}")
            return None

    def _compare_users(self, current_users: List, latest_users: List) -> bool:
        """Compare user data for duplicate detection."""
        if len(current_users) != len(latest_users):
            return False

        # Create lookup maps for efficient comparison
        current_user_map = {user.user_name: user for user in current_users}
        latest_user_map = {user.user_name: user for user in latest_users}

        for user_name, current_user in current_user_map.items():
            if user_name not in latest_user_map:
                return False
            latest_user = latest_user_map[user_name]

            # Compare key attributes that would indicate changes
            if (
                current_user.display_name != latest_user.display_name
                or current_user.active != latest_user.active
                or current_user.email != latest_user.email
            ):
                return False

        return True

    def _compare_groups(self, current_groups: List, latest_groups: List) -> bool:
        """Compare group data for duplicate detection."""
        if len(current_groups) != len(latest_groups):
            return False

        # Create lookup maps for efficient comparison
        current_group_map = {group.display_name: group for group in current_groups}
        latest_group_map = {group.display_name: group for group in latest_groups}

        for group_name, current_group in current_group_map.items():
            if group_name not in latest_group_map:
                return False
            latest_group = latest_group_map[group_name]

            # Compare key attributes and members
            if current_group.description != latest_group.description or set(
                current_group.members
            ) != set(latest_group.members):
                return False

        return True

    def _compare_permission_sets(self, current_ps: List, latest_ps: List) -> bool:
        """Compare permission set data for duplicate detection."""
        if len(current_ps) != len(latest_ps):
            return False

        # Create lookup maps for efficient comparison
        current_ps_map = {ps.name: ps for ps in current_ps}
        latest_ps_map = {ps.name: ps for ps in latest_ps}

        for ps_name, current_ps_obj in current_ps_map.items():
            if ps_name not in latest_ps_map:
                return False
            latest_ps_obj = latest_ps_map[ps_name]

            # Compare key attributes
            if (
                current_ps_obj.description != latest_ps_obj.description
                or current_ps_obj.relay_state != latest_ps_obj.relay_state
            ):
                return False

        return True

    def _compare_assignments(self, current_assignments: List, latest_assignments: List) -> bool:
        """Compare assignment data for duplicate detection."""
        if len(current_assignments) != len(latest_assignments):
            return False

        # Create lookup maps for efficient comparison
        current_assignment_map = {
            (a.account_id, a.permission_set_arn, a.principal_type, a.principal_id): a
            for a in current_assignments
        }
        latest_assignment_map = {
            (a.account_id, a.permission_set_arn, a.principal_type, a.principal_id): a
            for a in latest_assignments
        }

        # All assignments should be identical
        return current_assignment_map == latest_assignment_map
