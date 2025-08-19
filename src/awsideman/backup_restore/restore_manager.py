"""
Restore manager for AWS Identity Center backup restoration.

This module provides comprehensive restore functionality including conflict resolution,
compatibility validation, and dry-run capabilities for Identity Center configurations.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..aws_clients import AWSClientManager, CachedIdentityCenterClient, CachedIdentityStoreClient
from .cross_account import (
    CrossAccountClientManager,
    CrossAccountPermissionValidator,
    ResourceMapper,
)
from .interfaces import ProgressReporterInterface, RestoreManagerInterface, StorageEngineInterface
from .models import (
    AssignmentData,
    BackupData,
    ConflictInfo,
    ConflictStrategy,
    GroupData,
    PermissionSetData,
    ResourceMapping,
    ResourceType,
    RestoreOptions,
    RestorePreview,
    RestoreResult,
    UserData,
    ValidationResult,
)
from .monitoring import BackupMonitor
from .performance import PerformanceOptimizer

logger = logging.getLogger(__name__)


class ConflictResolver:
    """Handles conflict resolution during restore operations."""

    def __init__(self, strategy: ConflictStrategy):
        self.strategy = strategy
        self._user_responses: Dict[str, str] = {}

    async def resolve_conflict(self, conflict: ConflictInfo) -> str:
        """
        Resolve a conflict based on the configured strategy.

        Args:
            conflict: Information about the conflict

        Returns:
            Action to take: 'overwrite', 'skip', or 'merge'
        """
        if self.strategy == ConflictStrategy.OVERWRITE:
            return "overwrite"
        elif self.strategy == ConflictStrategy.SKIP:
            return "skip"
        elif self.strategy == ConflictStrategy.MERGE:
            return await self._attempt_merge(conflict)
        elif self.strategy == ConflictStrategy.PROMPT:
            return await self._prompt_user(conflict)
        else:
            logger.warning(f"Unknown conflict strategy: {self.strategy}, defaulting to skip")
            return "skip"

    async def _attempt_merge(self, conflict: ConflictInfo) -> str:
        """Attempt to merge conflicting resources."""
        # For now, implement basic merge logic
        # In a real implementation, this would be more sophisticated
        if conflict.resource_type == ResourceType.USERS:
            return await self._merge_user_data(conflict)
        elif conflict.resource_type == ResourceType.GROUPS:
            return await self._merge_group_data(conflict)
        else:
            # For permission sets and assignments, merging is complex
            # Default to overwrite for now
            return "overwrite"

    async def _merge_user_data(self, conflict: ConflictInfo) -> str:
        """Merge user data conflicts."""
        # Simple merge: keep existing core data, update optional fields
        existing = conflict.existing_value
        new = conflict.new_value

        # If email or names are different, prefer new values
        if (new.get("email") and new["email"] != existing.get("email")) or (
            new.get("display_name") and new["display_name"] != existing.get("display_name")
        ):
            return "overwrite"

        return "skip"

    async def _merge_group_data(self, conflict: ConflictInfo) -> str:
        """Merge group data conflicts."""
        # For groups, merge member lists
        existing = conflict.existing_value
        new = conflict.new_value

        # If descriptions are different, prefer new
        if new.get("description") != existing.get("description"):
            return "overwrite"

        return "skip"

    async def _prompt_user(self, conflict: ConflictInfo) -> str:
        """Prompt user for conflict resolution (simulated for now)."""
        # In a real implementation, this would prompt the user
        # For now, we'll use a simple heuristic
        conflict_key = f"{conflict.resource_type.value}:{conflict.resource_id}"

        if conflict_key in self._user_responses:
            return self._user_responses[conflict_key]

        # Default behavior for automated testing
        if conflict.suggested_action:
            action = conflict.suggested_action.lower()
            if action in ["overwrite", "skip", "merge"]:
                self._user_responses[conflict_key] = action
                return action

        # Default to skip if no clear suggestion
        self._user_responses[conflict_key] = "skip"
        return "skip"


class CompatibilityValidator:
    """Validates compatibility between backup and target environment."""

    def __init__(
        self,
        identity_center_client: CachedIdentityCenterClient,
        identity_store_client: CachedIdentityStoreClient,
    ):
        self.identity_center_client = identity_center_client
        self.identity_store_client = identity_store_client

    async def validate_compatibility(
        self, backup_data: BackupData, target_instance_arn: str
    ) -> ValidationResult:
        """
        Validate compatibility between backup and target environment.

        Args:
            backup_data: Backup data to validate
            target_instance_arn: Target Identity Center instance ARN

        Returns:
            ValidationResult with compatibility status
        """
        errors = []
        warnings = []
        details = {}

        try:
            # Validate instance accessibility
            instance_validation = await self._validate_instance_access(target_instance_arn)
            if not instance_validation["accessible"]:
                errors.append(f"Cannot access target instance: {target_instance_arn}")
                return ValidationResult(is_valid=False, errors=errors)

            # Validate permission set compatibility
            ps_validation = await self._validate_permission_sets(
                backup_data.permission_sets, target_instance_arn
            )
            errors.extend(ps_validation["errors"])
            warnings.extend(ps_validation["warnings"])
            details["permission_sets"] = ps_validation["details"]

            # Validate account access for assignments
            account_validation = await self._validate_account_access(backup_data.assignments)
            errors.extend(account_validation["errors"])
            warnings.extend(account_validation["warnings"])
            details["accounts"] = account_validation["details"]

            # Validate user/group limits
            limits_validation = await self._validate_limits(backup_data, target_instance_arn)
            warnings.extend(limits_validation["warnings"])
            details["limits"] = limits_validation["details"]

        except Exception as e:
            logger.error(f"Error during compatibility validation: {e}")
            errors.append(f"Validation error: {str(e)}")

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid, errors=errors, warnings=warnings, details=details
        )

    async def _validate_instance_access(self, instance_arn: str) -> Dict[str, Any]:
        """Validate access to the target Identity Center instance."""
        try:
            # Try to describe the instance
            response = await self.identity_center_client.describe_instance(InstanceArn=instance_arn)
            return {"accessible": True, "instance_metadata": response}
        except Exception as e:
            logger.error(f"Cannot access instance {instance_arn}: {e}")
            return {"accessible": False, "error": str(e)}

    async def _validate_permission_sets(
        self, permission_sets: List[PermissionSetData], instance_arn: str
    ) -> Dict[str, Any]:
        """Validate permission set compatibility."""
        errors = []
        warnings = []
        details = {"total": len(permission_sets), "conflicts": []}

        try:
            # Get existing permission sets
            existing_ps = await self._get_existing_permission_sets(instance_arn)
            existing_names = {ps["Name"] for ps in existing_ps}

            for ps in permission_sets:
                if ps.name in existing_names:
                    warnings.append(
                        f"Permission set '{ps.name}' already exists and may be overwritten"
                    )
                    details["conflicts"].append(ps.name)

                # Validate managed policies exist
                for policy_arn in ps.managed_policies:
                    if not await self._validate_managed_policy(policy_arn):
                        errors.append(f"Managed policy not found: {policy_arn}")

        except Exception as e:
            logger.error(f"Error validating permission sets: {e}")
            errors.append(f"Permission set validation error: {str(e)}")

        return {"errors": errors, "warnings": warnings, "details": details}

    async def _validate_account_access(self, assignments: List[AssignmentData]) -> Dict[str, Any]:
        """Validate access to accounts referenced in assignments."""
        errors = []
        warnings = []
        account_ids = {assignment.account_id for assignment in assignments}
        details = {"total_accounts": len(account_ids), "accessible": [], "inaccessible": []}

        for account_id in account_ids:
            try:
                # In a real implementation, we'd validate account access
                # For now, assume all accounts are accessible
                details["accessible"].append(account_id)
            except Exception as e:
                logger.warning(f"Cannot validate access to account {account_id}: {e}")
                warnings.append(f"Cannot validate access to account {account_id}")
                details["inaccessible"].append(account_id)

        return {"errors": errors, "warnings": warnings, "details": details}

    async def _validate_limits(self, backup_data: BackupData, instance_arn: str) -> Dict[str, Any]:
        """Validate that backup data doesn't exceed service limits."""
        warnings = []
        details = {}

        # Check user limits (typical limit is 50,000 users)
        user_count = len(backup_data.users)
        if user_count > 40000:  # Warning at 80% of typical limit
            warnings.append(f"Large number of users ({user_count}) may approach service limits")

        # Check group limits (typical limit is 10,000 groups)
        group_count = len(backup_data.groups)
        if group_count > 8000:  # Warning at 80% of typical limit
            warnings.append(f"Large number of groups ({group_count}) may approach service limits")

        # Check permission set limits (typical limit is 500 permission sets)
        ps_count = len(backup_data.permission_sets)
        if ps_count > 400:  # Warning at 80% of typical limit
            warnings.append(
                f"Large number of permission sets ({ps_count}) may approach service limits"
            )

        details = {
            "user_count": user_count,
            "group_count": group_count,
            "permission_set_count": ps_count,
        }

        return {"warnings": warnings, "details": details}

    async def _get_existing_permission_sets(self, instance_arn: str) -> List[Dict[str, Any]]:
        """Get existing permission sets from the target instance."""
        try:
            response = await self.identity_center_client.list_permission_sets(
                InstanceArn=instance_arn
            )

            permission_sets = []
            for ps_arn in response.get("PermissionSets", []):
                ps_details = await self.identity_center_client.describe_permission_set(
                    InstanceArn=instance_arn, PermissionSetArn=ps_arn
                )
                permission_sets.append(ps_details["PermissionSet"])

            return permission_sets
        except Exception as e:
            logger.error(f"Error getting existing permission sets: {e}")
            return []

    async def _validate_managed_policy(self, policy_arn: str) -> bool:
        """Validate that a managed policy exists and is accessible."""
        # In a real implementation, we'd check with IAM
        # For now, assume AWS managed policies exist
        return policy_arn.startswith("arn:aws:iam::aws:policy/")


class RestoreProcessor:
    """Processes restore operations for different resource types."""

    def __init__(
        self,
        identity_center_client: CachedIdentityCenterClient,
        identity_store_client: CachedIdentityStoreClient,
        conflict_resolver: ConflictResolver,
    ):
        self.identity_center_client = identity_center_client
        self.identity_store_client = identity_store_client
        self.conflict_resolver = conflict_resolver
        self._identity_store_id = None

    async def process_restore(
        self,
        backup_data: BackupData,
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface] = None,
    ) -> RestoreResult:
        """
        Process the restore operation.

        Args:
            backup_data: Data to restore
            options: Restore options
            progress_reporter: Optional progress reporter

        Returns:
            RestoreResult with operation outcome
        """
        start_time = datetime.now()
        errors = []
        warnings = []
        changes_applied = {}

        try:
            operation_id = str(uuid4())
            total_steps = self._calculate_total_steps(backup_data, options)

            if progress_reporter:
                await progress_reporter.start_operation(
                    operation_id, total_steps, "Restoring backup data"
                )

            current_step = 0

            # Restore in dependency order: users, groups, permission sets, assignments
            if (
                ResourceType.USERS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                result = await self._restore_users(
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
                result = await self._restore_groups(
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
                result = await self._restore_permission_sets(
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
                result = await self._restore_assignments(
                    backup_data.assignments, options, progress_reporter, operation_id, current_step
                )
                changes_applied["assignments"] = result["applied"]
                errors.extend(result["errors"])
                warnings.extend(result["warnings"])
                current_step += result["steps"]

            if progress_reporter:
                await progress_reporter.complete_operation(
                    operation_id, len(errors) == 0, "Restore operation completed"
                )

        except Exception as e:
            logger.error(f"Error during restore processing: {e}")
            errors.append(f"Restore processing error: {str(e)}")
            if progress_reporter:
                await progress_reporter.complete_operation(
                    operation_id, False, f"Restore failed: {str(e)}"
                )

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

    async def _get_identity_store_id(self, instance_arn: str) -> str:
        """Get the identity store ID for the given instance."""
        if self._identity_store_id is None:
            try:
                # Use list_instances instead of describe_instance to avoid resource-based policy issues
                response = await self.identity_center_client.list_instances()
                instances = response.get("Instances", [])

                logger.info(
                    f"Available instances: {[instance.get('InstanceArn') for instance in instances]}"
                )
                logger.info(f"Looking for instance: {instance_arn}")

                # Find the matching instance
                for instance in instances:
                    if instance.get("InstanceArn") == instance_arn:
                        self._identity_store_id = instance.get("IdentityStoreId")
                        logger.info(f"Found identity store ID: {self._identity_store_id}")
                        break

                if not self._identity_store_id:
                    raise ValueError(
                        f"Could not find identity store ID for instance {instance_arn}. Available instances: {[instance.get('InstanceArn') for instance in instances]}"
                    )

            except Exception as e:
                logger.error(f"Failed to get identity store ID for instance {instance_arn}: {e}")
                raise
        return self._identity_store_id

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

    async def _restore_users(
        self,
        users: List[UserData],
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore user data."""
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
                        # Handle conflict
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
                            await self._update_user(user, existing_user["UserId"])
                            applied += 1
                        elif action == "skip":
                            warnings.append(f"Skipped existing user: {user.user_name}")
                        # Merge would be handled in conflict resolver
                    else:
                        # Create new user
                        await self._create_user(user, options.target_instance_arn)
                        applied += 1
                else:
                    # Dry run - just count what would be applied
                    applied += 1

            except Exception as e:
                logger.error(f"Error restoring user {user.user_name}: {e}")
                errors.append(f"Failed to restore user {user.user_name}: {str(e)}")

        return {"applied": applied, "errors": errors, "warnings": warnings, "steps": len(users)}

    async def _restore_groups(
        self,
        groups: List[GroupData],
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore group data."""
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
                        # Handle conflict
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
                            await self._update_group(group, existing_group["GroupId"])
                            applied += 1
                        elif action == "skip":
                            warnings.append(f"Skipped existing group: {group.display_name}")
                    else:
                        # Create new group
                        await self._create_group(group, options.target_instance_arn)
                        applied += 1
                else:
                    applied += 1

            except Exception as e:
                logger.error(f"Error restoring group {group.display_name}: {e}")
                errors.append(f"Failed to restore group {group.display_name}: {str(e)}")

        return {"applied": applied, "errors": errors, "warnings": warnings, "steps": len(groups)}

    async def _restore_permission_sets(
        self,
        permission_sets: List[PermissionSetData],
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore permission set data."""
        errors = []
        warnings = []
        applied = 0

        # Skip permission sets if none to restore
        if not permission_sets:
            return {"applied": 0, "errors": errors, "warnings": warnings, "steps": 0}

        # Get target instance ARN from options
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
                        # Handle conflict
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
                            await self._update_permission_set(
                                ps, existing_ps["PermissionSetArn"], instance_arn
                            )
                            applied += 1
                        elif action == "skip":
                            warnings.append(f"Skipped existing permission set: {ps.name}")
                    else:
                        # Create new permission set
                        await self._create_permission_set(ps, instance_arn)
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

    async def _restore_assignments(
        self,
        assignments: List[AssignmentData],
        options: RestoreOptions,
        progress_reporter: Optional[ProgressReporterInterface],
        operation_id: str,
        start_step: int,
    ) -> Dict[str, Any]:
        """Restore assignment data."""
        errors = []
        warnings = []
        applied = 0

        # Skip assignments if none to restore
        if not assignments:
            return {"applied": 0, "errors": errors, "warnings": warnings, "steps": 0}

        # Get target instance ARN from options
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
                        # Create new assignment
                        await self._create_assignment(assignment, instance_arn)
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

    # Helper methods for AWS API operations (simplified for now)
    async def _get_existing_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get existing user by username."""
        # Simplified implementation
        return None

    async def _create_user(self, user: UserData, instance_arn: str) -> str:
        """Create a new user."""
        try:
            # Get identity store ID
            identity_store_id = await self._get_identity_store_id(instance_arn)

            # Create user via Identity Store API
            response = await self.identity_store_client.create_user(
                IdentityStoreId=identity_store_id,
                UserName=user.user_name,
                DisplayName=user.display_name or user.user_name,
                Emails=[{"Value": user.email, "Primary": True}] if user.email else [],
                Name=(
                    {"GivenName": user.given_name, "FamilyName": user.family_name}
                    if user.given_name and user.family_name
                    else None
                ),
            )
            return response["UserId"]
        except Exception as e:
            logger.error(f"Failed to create user {user.user_name}: {e}")
            raise

    async def _update_user(self, user: UserData, user_id: str) -> None:
        """Update an existing user."""
        # Simplified implementation
        pass

    async def _get_existing_group(self, display_name: str) -> Optional[Dict[str, Any]]:
        """Get existing group by display name."""
        # Simplified implementation
        return None

    async def _create_group(self, group: GroupData, instance_arn: str) -> str:
        """Create a new group."""
        try:
            # Get identity store ID
            identity_store_id = await self._get_identity_store_id(instance_arn)

            # Create group via Identity Store API
            response = await self.identity_store_client.create_group(
                IdentityStoreId=identity_store_id,
                DisplayName=group.display_name,
                Description=group.description
                or "Restored from backup",  # Use default description if None
            )
            return response["GroupId"]
        except Exception as e:
            logger.error(f"Failed to create group {group.display_name}: {e}")
            raise

    async def _update_group(self, group: GroupData, group_id: str) -> None:
        """Update an existing group."""
        # Simplified implementation
        pass

    async def _get_existing_permission_set(
        self, name: str, instance_arn: str
    ) -> Optional[Dict[str, Any]]:
        """Get existing permission set by name."""
        # Simplified implementation
        return None

    async def _create_permission_set(self, ps: PermissionSetData, instance_arn: str) -> str:
        """Create a new permission set."""
        try:
            # Create permission set via Identity Center API
            response = await self.identity_center_client.create_permission_set(
                InstanceArn=instance_arn,
                Name=ps.name,
                Description=ps.description
                or "Restored from backup",  # Use default description if None
                SessionDuration=ps.session_duration or "PT1H",  # Default to 1 hour if not specified
            )
            return response["PermissionSet"]["PermissionSetArn"]
        except Exception as e:
            logger.error(f"Failed to create permission set {ps.name}: {e}")
            raise

    async def _update_permission_set(
        self, ps: PermissionSetData, ps_arn: str, instance_arn: str
    ) -> None:
        """Update an existing permission set."""
        # Simplified implementation
        pass

    async def _get_existing_assignment(
        self, assignment: AssignmentData, instance_arn: str
    ) -> Optional[Dict[str, Any]]:
        """Get existing assignment."""
        # Simplified implementation
        return None

    async def _create_assignment(self, assignment: AssignmentData, instance_arn: str) -> None:
        """Create a new assignment."""
        try:
            # Create assignment via Identity Center API
            await self.identity_center_client.create_account_assignment(
                InstanceArn=instance_arn,
                TargetId=assignment.account_id,
                TargetType="AWS_ACCOUNT",
                PermissionSetArn=assignment.permission_set_arn,
                PrincipalType=assignment.principal_type,
                PrincipalId=assignment.principal_id,
            )
        except Exception as e:
            logger.error(f"Failed to create assignment for {assignment.principal_id}: {e}")
            raise


class CrossAccountRestoreManager(RestoreManagerInterface):
    """
    Enhanced restore manager with cross-account and cross-region support.
    """

    def __init__(self, client_manager: AWSClientManager, storage_engine: StorageEngineInterface):
        """
        Initialize cross-account restore manager.

        Args:
            client_manager: Base AWS client manager
            storage_engine: Storage engine for backup data
        """
        self.client_manager = client_manager
        self.storage_engine = storage_engine
        self.cross_account_manager = CrossAccountClientManager(client_manager)
        self.resource_mapper = ResourceMapper()
        self.permission_validator = CrossAccountPermissionValidator(self.cross_account_manager)

    async def restore_backup(self, backup_id: str, options: RestoreOptions) -> RestoreResult:
        """
        Restore a backup with cross-account and cross-region support.

        Args:
            backup_id: Unique identifier of the backup to restore
            options: Configuration options for the restore operation

        Returns:
            RestoreResult containing the outcome of the restore operation
        """
        start_time = datetime.now()
        warnings = []

        try:
            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                return RestoreResult(
                    success=False,
                    message=f"Backup {backup_id} not found",
                    errors=[f"Backup {backup_id} not found"],
                )

            # Validate cross-account configuration if specified
            if options.cross_account_config:
                # For now, skip cross-account validation since we need the clients first
                # This will be handled during the actual restore operation
                warnings.append(
                    "Cross-account validation will be performed during restore operation"
                )

            # Apply resource mappings if configured
            if options.resource_mapping_configs:
                backup_data = await self._apply_resource_mappings(
                    backup_data, options.resource_mapping_configs
                )

            # Get appropriate client manager (cross-account or local)
            target_client_manager = await self._get_target_client_manager(options)

            # Create restore processor with target client manager
            identity_center_client = target_client_manager.get_identity_center_client()
            identity_store_client = target_client_manager.get_identity_store_client()
            conflict_resolver = ConflictResolver(options.conflict_strategy)

            restore_processor = RestoreProcessor(
                identity_center_client, identity_store_client, conflict_resolver
            )

            # Process the restore
            restore_result = await restore_processor.process_restore(backup_data, options)

            return restore_result

        except Exception as e:
            logger.error(f"Error during cross-account restore: {e}")
            return RestoreResult(
                success=False,
                message=f"Restore failed: {str(e)}",
                errors=[str(e)],
                duration=datetime.now() - start_time,
            )

    async def preview_restore(self, backup_id: str, options: RestoreOptions) -> RestorePreview:
        """
        Preview the changes that would be made by a cross-account restore operation.

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
                return RestorePreview(
                    changes_summary={}, conflicts=[], warnings=[f"Backup {backup_id} not found"]
                )

            # Apply resource mappings for preview
            if options.resource_mapping_configs:
                backup_data = await self._apply_resource_mappings(
                    backup_data, options.resource_mapping_configs
                )

            # Calculate changes summary
            changes_summary = {
                "users": len(backup_data.users),
                "groups": len(backup_data.groups),
                "permission_sets": len(backup_data.permission_sets),
                "assignments": len(backup_data.assignments),
            }

            # Identify potential conflicts (simplified for now)
            conflicts = []
            warnings = []

            # Add cross-account warnings
            if options.cross_account_config:
                warnings.append(
                    f"Cross-account restore to account {options.cross_account_config.target_account_id}"
                )

            # Add resource mapping warnings
            if options.resource_mapping_configs:
                for mapping in options.resource_mapping_configs:
                    warnings.append(
                        f"Resource mapping: {mapping.source_account_id} -> {mapping.target_account_id}"
                    )

            return RestorePreview(
                changes_summary=changes_summary,
                conflicts=conflicts,
                warnings=warnings,
                estimated_duration=timedelta(minutes=5),  # Rough estimate
            )

        except Exception as e:
            logger.error(f"Error during restore preview: {e}")
            return RestorePreview(
                changes_summary={}, conflicts=[], warnings=[f"Preview failed: {str(e)}"]
            )

    async def validate_compatibility(
        self, backup_id: str, target_instance_arn: str
    ) -> ValidationResult:
        """
        Validate compatibility between a backup and target environment with cross-account support.

        Args:
            backup_id: Unique identifier of the backup
            target_instance_arn: ARN of the target Identity Center instance

        Returns:
            ValidationResult containing compatibility status and details
        """
        errors = []
        warnings = []
        details = {}

        try:
            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                return ValidationResult(is_valid=False, errors=[f"Backup {backup_id} not found"])

            # Extract target account and region from instance ARN
            # ARN format: arn:aws:sso:::instance/instance_id
            arn_parts = target_instance_arn.split(":")
            if len(arn_parts) >= 5:
                target_region = arn_parts[3]
                target_account = arn_parts[4]

                details["target_account"] = target_account
                details["target_region"] = target_region
                details["source_account"] = backup_data.metadata.source_account
                details["source_region"] = backup_data.metadata.source_region

                # Check for cross-account operation
                if target_account != backup_data.metadata.source_account:
                    warnings.append(
                        "Cross-account restore detected - ensure proper IAM permissions"
                    )
                    details["cross_account"] = True

                # Check for cross-region operation
                if target_region != backup_data.metadata.source_region:
                    warnings.append(
                        "Cross-region restore detected - verify region-specific resources"
                    )
                    details["cross_region"] = True

            # Validate backup integrity
            if not backup_data.verify_integrity():
                errors.append("Backup data integrity check failed")

            # Check resource counts
            total_resources = (
                len(backup_data.users)
                + len(backup_data.groups)
                + len(backup_data.permission_sets)
                + len(backup_data.assignments)
            )

            if total_resources == 0:
                warnings.append("Backup contains no resources to restore")

            details["resource_counts"] = backup_data.metadata.resource_counts

            # For cross-account operations, we can't validate instance access here
            # because we don't have the cross-account configuration yet.
            # Instance access validation will happen during the actual restore operation.
            warnings.append("Cross-account validation will be performed during restore operation")

        except Exception as e:
            logger.error(f"Error during compatibility validation: {e}")
            errors.append(f"Validation error: {str(e)}")

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

    async def _validate_cross_account_restore(
        self, options: RestoreOptions, backup_data: BackupData
    ) -> ValidationResult:
        """
        Validate cross-account restore configuration and permissions.

        Args:
            options: Restore options with cross-account configuration
            backup_data: Backup data to be restored

        Returns:
            ValidationResult with validation status
        """
        if not options.cross_account_config:
            return ValidationResult(is_valid=True, errors=[], warnings=[])

        # Validate permissions for cross-account restore
        if options.target_instance_arn:
            return await self.permission_validator.validate_restore_permissions(
                options.cross_account_config, options.target_instance_arn
            )
        else:
            return ValidationResult(
                is_valid=False, errors=["Target instance ARN required for cross-account restore"]
            )

    async def _apply_resource_mappings(
        self, backup_data: BackupData, mappings: List[ResourceMapping]
    ) -> BackupData:
        """
        Apply resource mappings to backup data for cross-account/region operations.

        Args:
            backup_data: Original backup data
            mappings: List of resource mappings to apply

        Returns:
            Modified backup data with mappings applied
        """
        # Create a copy of the backup data to avoid modifying the original
        import copy

        mapped_data = copy.deepcopy(backup_data)

        # Apply mappings to permission sets
        for ps in mapped_data.permission_sets:
            # Map permission set ARN
            ps.permission_set_arn = self.resource_mapper.map_permission_set_arn(
                ps.permission_set_arn, mappings
            )

            # Map permission set name if configured
            ps.name = self.resource_mapper.map_permission_set_name(ps.name, mappings)

        # Apply mappings to assignments
        for assignment in mapped_data.assignments:
            # Map account ID
            assignment.account_id = self.resource_mapper.map_assignment_account(
                assignment.account_id, mappings
            )

            # Map permission set ARN
            assignment.permission_set_arn = self.resource_mapper.map_permission_set_arn(
                assignment.permission_set_arn, mappings
            )

        # Update metadata to reflect target account/region
        if mappings:
            primary_mapping = mappings[0]  # Use first mapping for metadata
            mapped_data.metadata.source_account = primary_mapping.target_account_id
            if primary_mapping.target_region:
                mapped_data.metadata.source_region = primary_mapping.target_region

        logger.info(f"Applied {len(mappings)} resource mappings to backup data")
        return mapped_data

    async def _get_target_client_manager(self, options: RestoreOptions) -> AWSClientManager:
        """
        Get the appropriate client manager for the target environment.

        Args:
            options: Restore options that may include cross-account configuration

        Returns:
            AWSClientManager for the target environment
        """
        if options.cross_account_config:
            # Return cross-account client manager
            return await self.cross_account_manager.get_cross_account_client_manager(
                options.cross_account_config
            )
        else:
            # Return local client manager
            return self.client_manager

    async def _create_assignment(self, assignment: AssignmentData, instance_arn: str) -> None:
        """Create a new assignment."""
        # Simplified implementation
        pass


class RestoreManager(RestoreManagerInterface):
    """
    Manages restore operations for AWS Identity Center backups.

    Provides comprehensive restore functionality including:
    - Dry-run preview capabilities
    - Conflict resolution strategies
    - Compatibility validation
    - Progress tracking and reporting
    """

    def __init__(
        self,
        storage_engine: StorageEngineInterface,
        identity_center_client: CachedIdentityCenterClient,
        identity_store_client: CachedIdentityStoreClient,
        progress_reporter: Optional[ProgressReporterInterface] = None,
        backup_monitor: Optional[BackupMonitor] = None,
        performance_optimizer: Optional[PerformanceOptimizer] = None,
    ):
        """
        Initialize the restore manager.

        Args:
            storage_engine: Storage engine for retrieving backup data
            identity_center_client: AWS Identity Center client
            identity_store_client: AWS Identity Store client
            progress_reporter: Optional progress reporter for tracking operations
        """
        self.storage_engine = storage_engine
        self.identity_center_client = identity_center_client
        self.identity_store_client = identity_store_client
        self.progress_reporter = progress_reporter
        self.backup_monitor = backup_monitor
        self.performance_optimizer = performance_optimizer or PerformanceOptimizer()

        self.compatibility_validator = CompatibilityValidator(
            identity_center_client, identity_store_client
        )

    async def restore_backup(self, backup_id: str, options: RestoreOptions) -> RestoreResult:
        """
        Restore a backup with the specified options.

        Args:
            backup_id: Unique identifier of the backup to restore
            options: Configuration options for the restore operation

        Returns:
            RestoreResult containing the outcome of the restore operation
        """
        logger.info(f"Starting restore operation for backup {backup_id}")

        try:
            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                return RestoreResult(
                    success=False,
                    message=f"Backup {backup_id} not found",
                    errors=[f"Backup {backup_id} not found"],
                )

            # Check if backup data is optimized and restore if needed
            if (
                hasattr(backup_data.metadata, "optimization_info")
                and backup_data.metadata.optimization_info
            ):
                logger.info("Restoring optimized backup data")
                try:
                    # The backup data should already be restored by the storage engine
                    # but we can verify optimization metadata
                    optimization_info = backup_data.metadata.optimization_info
                    logger.info(
                        f"Backup was optimized: {optimization_info.get('original_size', 0)} -> "
                        f"{optimization_info.get('final_size', 0)} bytes "
                        f"(ratio: {optimization_info.get('total_reduction_ratio', 1.0):.2f}x)"
                    )
                except Exception as e:
                    logger.warning(f"Failed to process optimization metadata: {e}")

            # Validate backup integrity
            if not backup_data.verify_integrity():
                return RestoreResult(
                    success=False,
                    message="Backup integrity validation failed",
                    errors=["Backup data integrity check failed"],
                )

            # Set target instance ARN if not specified
            if not options.target_instance_arn:
                options.target_instance_arn = backup_data.metadata.instance_arn

            # Validate compatibility if not skipped
            if not options.skip_validation:
                compatibility_result = await self.compatibility_validator.validate_compatibility(
                    backup_data, options.target_instance_arn
                )

                if not compatibility_result.is_valid:
                    return RestoreResult(
                        success=False,
                        message="Compatibility validation failed",
                        errors=compatibility_result.errors,
                        warnings=compatibility_result.warnings,
                    )

            # Create conflict resolver
            conflict_resolver = ConflictResolver(options.conflict_strategy)

            # Create restore processor
            restore_processor = RestoreProcessor(
                self.identity_center_client, self.identity_store_client, conflict_resolver
            )

            # Process the restore
            result = await restore_processor.process_restore(
                backup_data, options, self.progress_reporter
            )

            logger.info(f"Restore operation completed for backup {backup_id}: {result.success}")
            return result

        except Exception as e:
            logger.error(f"Error during restore operation for backup {backup_id}: {e}")
            return RestoreResult(
                success=False,
                message=f"Restore operation failed: {str(e)}",
                errors=[f"Restore operation failed: {str(e)}"],
            )

    async def preview_restore(self, backup_id: str, options: RestoreOptions) -> RestorePreview:
        """
        Preview the changes that would be made by a restore operation.

        Args:
            backup_id: Unique identifier of the backup to preview
            options: Configuration options for the restore operation

        Returns:
            RestorePreview containing details of planned changes
        """
        logger.info(f"Generating restore preview for backup {backup_id}")

        try:
            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                return RestorePreview(warnings=[f"Backup {backup_id} not found"])

            # Calculate changes summary
            changes_summary = {}
            conflicts = []
            warnings = []

            # Analyze each resource type
            if (
                ResourceType.USERS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                user_analysis = await self._analyze_user_changes(backup_data.users)
                changes_summary["users"] = user_analysis["changes"]
                conflicts.extend(user_analysis["conflicts"])
                warnings.extend(user_analysis["warnings"])

            if (
                ResourceType.GROUPS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                group_analysis = await self._analyze_group_changes(backup_data.groups)
                changes_summary["groups"] = group_analysis["changes"]
                conflicts.extend(group_analysis["conflicts"])
                warnings.extend(group_analysis["warnings"])

            if (
                ResourceType.PERMISSION_SETS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                ps_analysis = await self._analyze_permission_set_changes(
                    backup_data.permission_sets
                )
                changes_summary["permission_sets"] = ps_analysis["changes"]
                conflicts.extend(ps_analysis["conflicts"])
                warnings.extend(ps_analysis["warnings"])

            if (
                ResourceType.ASSIGNMENTS in options.target_resources
                or ResourceType.ALL in options.target_resources
            ):
                assignment_analysis = await self._analyze_assignment_changes(
                    backup_data.assignments
                )
                changes_summary["assignments"] = assignment_analysis["changes"]
                conflicts.extend(assignment_analysis["conflicts"])
                warnings.extend(assignment_analysis["warnings"])

            # Estimate duration based on total changes
            total_changes = sum(changes_summary.values())
            estimated_duration = timedelta(
                seconds=total_changes * 2
            )  # Rough estimate: 2 seconds per change

            return RestorePreview(
                changes_summary=changes_summary,
                conflicts=conflicts,
                warnings=warnings,
                estimated_duration=estimated_duration,
            )

        except Exception as e:
            logger.error(f"Error generating restore preview for backup {backup_id}: {e}")
            return RestorePreview(warnings=[f"Error generating preview: {str(e)}"])

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
        logger.info(
            f"Validating compatibility for backup {backup_id} with instance {target_instance_arn}"
        )

        try:
            # Retrieve backup data
            backup_data = await self.storage_engine.retrieve_backup(backup_id)
            if not backup_data:
                return ValidationResult(is_valid=False, errors=[f"Backup {backup_id} not found"])

            # Use compatibility validator
            result = await self.compatibility_validator.validate_compatibility(
                backup_data, target_instance_arn
            )

            logger.info(
                f"Compatibility validation completed for backup {backup_id}: {result.is_valid}"
            )
            return result

        except Exception as e:
            logger.error(f"Error during compatibility validation for backup {backup_id}: {e}")
            return ValidationResult(
                is_valid=False, errors=[f"Compatibility validation failed: {str(e)}"]
            )

    async def _analyze_user_changes(self, users: List[UserData]) -> Dict[str, Any]:
        """Analyze changes for user restoration."""
        changes = len(users)  # Simplified: assume all users are new/changed
        conflicts = []
        warnings = []

        # In a real implementation, we'd check existing users and identify conflicts
        # For now, simulate some conflicts
        if changes > 100:
            warnings.append(f"Large number of users ({changes}) will be processed")

        return {"changes": changes, "conflicts": conflicts, "warnings": warnings}

    async def _analyze_group_changes(self, groups: List[GroupData]) -> Dict[str, Any]:
        """Analyze changes for group restoration."""
        changes = len(groups)
        conflicts = []
        warnings = []

        if changes > 50:
            warnings.append(f"Large number of groups ({changes}) will be processed")

        return {"changes": changes, "conflicts": conflicts, "warnings": warnings}

    async def _analyze_permission_set_changes(
        self, permission_sets: List[PermissionSetData]
    ) -> Dict[str, Any]:
        """Analyze changes for permission set restoration."""
        changes = len(permission_sets)
        conflicts = []
        warnings = []

        if changes > 20:
            warnings.append(f"Large number of permission sets ({changes}) will be processed")

        return {"changes": changes, "conflicts": conflicts, "warnings": warnings}

    async def _analyze_assignment_changes(
        self, assignments: List[AssignmentData]
    ) -> Dict[str, Any]:
        """Analyze changes for assignment restoration."""
        changes = len(assignments)
        conflicts = []
        warnings = []

        if changes > 1000:
            warnings.append(f"Large number of assignments ({changes}) will be processed")

        return {"changes": changes, "conflicts": conflicts, "warnings": warnings}
