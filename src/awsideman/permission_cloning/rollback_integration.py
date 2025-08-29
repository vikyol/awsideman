"""
Rollback integration for permission cloning operations.

This module provides integration between permission cloning operations and the rollback system,
allowing users to undo permission assignment copies and permission set clones.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from ..aws_clients.manager import AWSClientManager
from ..rollback.models import (
    AssignmentState,
    OperationType,
    PermissionCloningOperationRecord,
    PermissionSetCloningOperationRecord,
    PrincipalType,
    RollbackAction,
    RollbackActionType,
)
from ..rollback.processor import RollbackProcessor
from .models import CloneResult, CopyResult, EntityReference, PermissionAssignment
from .progress_reporter import ProgressReporter, get_progress_reporter

logger = logging.getLogger(__name__)


class PermissionCloningRollbackIntegration:
    """
    Integrates permission cloning operations with the rollback system.

    This class provides:
    - Rollback tracking for assignment copy operations
    - Rollback support for permission set cloning
    - Rollback operations that can undo copy and clone changes
    """

    def __init__(
        self,
        client_manager: AWSClientManager,
        rollback_processor: RollbackProcessor,
        progress_reporter: Optional[ProgressReporter] = None,
    ):
        """
        Initialize the rollback integration.

        Args:
            client_manager: AWS client manager for accessing AWS services
            rollback_processor: Rollback processor for handling rollback operations
            progress_reporter: Optional progress reporter for logging rollback operations
        """
        self.client_manager = client_manager
        self.rollback_processor = rollback_processor
        self.progress_reporter = progress_reporter or get_progress_reporter()

    def track_assignment_copy_operation(
        self,
        source_entity: EntityReference,
        target_entity: EntityReference,
        assignments_copied: List[PermissionAssignment],
        copy_result: CopyResult,
    ) -> str:
        """
        Track an assignment copy operation for potential rollback.

        Args:
            source_entity: Source entity reference
            target_entity: Target entity reference
            assignments_copied: List of assignments that were copied
            copy_result: Result of the copy operation

        Returns:
            Operation ID for tracking
        """
        try:
            # Extract account IDs and permission set ARNs from assignments
            account_ids = list(set(assignment.account_id for assignment in assignments_copied))
            permission_sets = list(
                set(assignment.permission_set_arn for assignment in assignments_copied)
            )

            # Create assignment IDs (combination of permission set + account + entity)
            assignment_ids = [
                f"{assignment.permission_set_arn}:{assignment.account_id}:{target_entity.entity_id}"
                for assignment in assignments_copied
            ]

            # Create operation record
            operation_record = PermissionCloningOperationRecord.create(
                operation_type=OperationType.COPY_ASSIGNMENTS,
                source_entity_id=source_entity.entity_id,
                source_entity_type=PrincipalType(source_entity.entity_type.value),
                source_entity_name=source_entity.entity_name,
                target_entity_id=target_entity.entity_id,
                target_entity_type=PrincipalType(target_entity.entity_type.value),
                target_entity_name=target_entity.entity_name,
                assignments_copied=assignment_ids,
                permission_sets_involved=permission_sets,
                accounts_affected=account_ids,
                metadata={
                    "copy_result": {
                        "success": copy_result.success,
                        "assignments_copied_count": len(assignments_copied),
                        "assignments_skipped_count": len(copy_result.assignments_skipped),
                        "error_message": copy_result.error_message,
                    }
                },
            )

            # Store the operation record
            self.rollback_processor.store.store_operation(operation_record)

            logger.info(
                f"Tracked assignment copy operation {operation_record.operation_id} for rollback"
            )
            return operation_record.operation_id

        except Exception as e:
            logger.error(f"Failed to track assignment copy operation for rollback: {str(e)}")
            raise

    def track_permission_set_clone_operation(
        self,
        source_permission_set_name: str,
        source_permission_set_arn: str,
        target_permission_set_name: str,
        target_permission_set_arn: str,
        clone_result: CloneResult,
    ) -> str:
        """
        Track a permission set clone operation for potential rollback.

        Args:
            source_permission_set_name: Name of the source permission set
            source_permission_set_arn: ARN of the source permission set
            target_permission_set_name: Name of the target permission set
            target_permission_set_arn: ARN of the target permission set
            clone_result: Result of the clone operation

        Returns:
            Operation ID for tracking
        """
        try:
            # Extract policy information from the cloned config
            policies_copied = {}
            if clone_result.cloned_config:
                if clone_result.cloned_config.aws_managed_policies:
                    policies_copied["aws_managed"] = clone_result.cloned_config.aws_managed_policies
                if clone_result.cloned_config.customer_managed_policies:
                    policies_copied["customer_managed"] = [
                        f"{policy.path}{policy.name}"
                        for policy in clone_result.cloned_config.customer_managed_policies
                    ]
                if clone_result.cloned_config.inline_policy:
                    policies_copied["inline"] = ["inline_policy"]

            # Create operation record
            operation_record = PermissionSetCloningOperationRecord.create(
                operation_type=OperationType.CLONE_PERMISSION_SET,
                source_permission_set_name=source_permission_set_name,
                source_permission_set_arn=source_permission_set_arn,
                target_permission_set_name=target_permission_set_name,
                target_permission_set_arn=target_permission_set_arn,
                policies_copied=policies_copied,
                metadata={
                    "clone_result": {
                        "success": clone_result.success,
                        "error_message": clone_result.error_message,
                    }
                },
            )

            # Store the operation record
            self.rollback_processor.store.store_operation(operation_record)

            logger.info(
                f"Tracked permission set clone operation {operation_record.operation_id} for rollback"
            )
            return operation_record.operation_id

        except Exception as e:
            logger.error(f"Failed to track permission set clone operation for rollback: {str(e)}")
            raise

    def rollback_assignment_copy_operation(self, operation_id: str) -> Dict[str, Any]:
        """
        Rollback an assignment copy operation by revoking the copied assignments.

        Args:
            operation_id: ID of the operation to rollback

        Returns:
            Dictionary with rollback results
        """
        start_time = time.time()

        try:
            # Get the operation record
            operation_record = self.rollback_processor.store.get_operation(operation_id)
            if not operation_record:
                raise ValueError(f"Operation {operation_id} not found")

            if not isinstance(operation_record, PermissionCloningOperationRecord):
                raise ValueError(f"Operation {operation_id} is not a permission cloning operation")

            if operation_record.rolled_back:
                raise ValueError(f"Operation {operation_id} has already been rolled back")

            logger.info(f"Rolling back assignment copy operation {operation_id}")

            # Create rollback actions
            rollback_actions = []
            for assignment_id in operation_record.assignments_copied:
                # Parse assignment ID to extract components
                parts = assignment_id.split(":")
                if len(parts) >= 3:
                    permission_set_arn = parts[0]
                    account_id = parts[1]
                    entity_id = parts[2]

                    rollback_action = RollbackAction(
                        principal_id=entity_id,
                        permission_set_arn=permission_set_arn,
                        account_id=account_id,
                        action_type=RollbackActionType.REVOKE_COPIED_ASSIGNMENTS,
                        current_state=AssignmentState.ASSIGNED,
                        principal_type=operation_record.target_entity_type,
                    )
                    rollback_actions.append(rollback_action)

            # Execute rollback actions
            success_count = 0
            failure_count = 0
            errors = []

            for action in rollback_actions:
                try:
                    # Revoke the assignment
                    self._revoke_assignment(
                        action.principal_id,
                        action.permission_set_arn,
                        action.account_id,
                        action.principal_type,
                    )
                    success_count += 1
                except Exception as e:
                    failure_count += 1
                    error_msg = f"Failed to revoke assignment {action.permission_set_arn} from {action.principal_id} in account {action.account_id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Mark operation as rolled back
            operation_record.rolled_back = True
            operation_record.rollback_operation_id = f"rollback_{operation_id}"
            self.rollback_processor.store.store_operation(operation_record)

            result = {
                "operation_id": operation_id,
                "success": failure_count == 0,
                "success_count": success_count,
                "failure_count": failure_count,
                "total_actions": len(rollback_actions),
                "errors": errors,
            }

            # Log structured rollback operation
            duration_ms = (time.time() - start_time) * 1000
            self.progress_reporter.log_rollback_operation(
                operation_id, "assignment_copy", result, duration_ms
            )

            logger.info(
                f"Rollback completed for operation {operation_id}: {success_count} successful, {failure_count} failed"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to rollback assignment copy operation {operation_id}: {str(e)}")
            raise

    def rollback_permission_set_clone_operation(self, operation_id: str) -> Dict[str, Any]:
        """
        Rollback a permission set clone operation by deleting the cloned permission set.

        Args:
            operation_id: ID of the operation to rollback

        Returns:
            Dictionary with rollback results
        """
        start_time = time.time()

        try:
            # Get the operation record
            operation_record = self.rollback_processor.store.get_operation(operation_id)
            if not operation_record:
                raise ValueError(f"Operation {operation_id} not found")

            if not isinstance(operation_record, PermissionSetCloningOperationRecord):
                raise ValueError(
                    f"Operation {operation_id} is not a permission set cloning operation"
                )

            if operation_record.rolled_back:
                raise ValueError(f"Operation {operation_id} has already been rolled back")

            logger.info(f"Rolling back permission set clone operation {operation_id}")

            # Get the target permission set ARN if it's not stored in the operation record
            target_permission_set_arn = operation_record.target_permission_set_arn
            if not target_permission_set_arn:
                # Try to derive the ARN from the permission set name
                try:
                    sso_admin_client = self.client_manager.get_sso_admin_client()
                    instance_arn = self._get_instance_arn()

                    # List all permission sets and find the one with matching name
                    response = sso_admin_client.list_permission_sets(InstanceArn=instance_arn)
                    for ps_arn in response.get("PermissionSets", []):
                        ps_details = sso_admin_client.describe_permission_set(
                            InstanceArn=instance_arn, PermissionSetArn=ps_arn
                        )
                        if (
                            ps_details.get("PermissionSet", {}).get("Name")
                            == operation_record.target_permission_set_name
                        ):
                            target_permission_set_arn = ps_arn
                            break

                    if not target_permission_set_arn:
                        raise ValueError(
                            f"Could not find permission set with name '{operation_record.target_permission_set_name}'"
                        )

                except Exception as e:
                    logger.error(f"Failed to derive target permission set ARN: {str(e)}")
                    raise ValueError(
                        f"Target permission set ARN not available and could not be derived: {str(e)}"
                    )

            try:
                # Delete the cloned permission set
                self._delete_permission_set(target_permission_set_arn)

                # Mark operation as rolled back
                operation_record.rolled_back = True
                operation_record.rollback_operation_id = f"rollback_{operation_id}"
                self.rollback_processor.store.store_operation(operation_record)

                result = {
                    "operation_id": operation_id,
                    "success": True,
                    "permission_set_deleted": operation_record.target_permission_set_name,
                    "permission_set_arn": operation_record.target_permission_set_arn,
                }

                # Log structured rollback operation
                duration_ms = (time.time() - start_time) * 1000
                self.progress_reporter.log_rollback_operation(
                    operation_id, "permission_set_clone", result, duration_ms
                )

                logger.info(
                    f"Successfully rolled back permission set clone operation {operation_id}"
                )
                return result

            except Exception as e:
                error_msg = f"Failed to delete cloned permission set {operation_record.target_permission_set_name}: {str(e)}"
                logger.error(error_msg)

                result = {"operation_id": operation_id, "success": False, "error": error_msg}

                # Log structured rollback operation
                duration_ms = (time.time() - start_time) * 1000
                self.progress_reporter.log_rollback_operation(
                    operation_id, "permission_set_clone", result, duration_ms
                )

                return result

        except Exception as e:
            logger.error(
                f"Failed to rollback permission set clone operation {operation_id}: {str(e)}"
            )
            raise

    def get_rollbackable_operations(
        self,
        operation_type: Optional[OperationType] = None,
        entity_id: Optional[str] = None,
        days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get list of operations that can be rolled back.

        Args:
            operation_type: Filter by operation type
            entity_id: Filter by entity ID (source or target)
            days: Filter by operations within last N days

        Returns:
            List of rollbackable operations
        """
        try:
            operations = self.rollback_processor.store.get_operations(
                operation_type=operation_type.value if operation_type else None, days=days
            )

            rollbackable_operations = []
            for op in operations:
                # Check if it's a permission cloning operation and not already rolled back
                if hasattr(op, "rolled_back") and not op.rolled_back:
                    if (
                        entity_id is None
                        or (hasattr(op, "source_entity_id") and op.source_entity_id == entity_id)
                        or (hasattr(op, "target_entity_id") and op.target_entity_id == entity_id)
                    ):
                        rollbackable_operations.append(op.to_dict())

            return rollbackable_operations

        except Exception as e:
            logger.error(f"Failed to get rollbackable operations: {str(e)}")
            raise

    def _revoke_assignment(
        self, entity_id: str, permission_set_arn: str, account_id: str, entity_type: PrincipalType
    ) -> None:
        """Revoke a permission set assignment from an entity."""
        try:
            sso_admin_client = self.client_manager.get_sso_admin_client()

            if entity_type == PrincipalType.USER:
                sso_admin_client.delete_account_assignment(
                    InstanceArn=self._get_instance_arn(),
                    AccountId=account_id,
                    PermissionSetArn=permission_set_arn,
                    PrincipalId=entity_id,
                    PrincipalType="USER",
                )
            elif entity_type == PrincipalType.GROUP:
                sso_admin_client.delete_account_assignment(
                    InstanceArn=self._get_instance_arn(),
                    AccountId=account_id,
                    PermissionSetArn=permission_set_arn,
                    PrincipalId=entity_id,
                    PrincipalType="GROUP",
                )

            logger.debug(
                f"Revoked assignment {permission_set_arn} from {entity_type.value} {entity_id} in account {account_id}"
            )

        except Exception as e:
            logger.error(f"Failed to revoke assignment: {str(e)}")
            raise

    def _delete_permission_set(self, permission_set_arn: str) -> None:
        """Delete a permission set."""
        try:
            sso_admin_client = self.client_manager.get_sso_admin_client()

            # First, detach all managed policies
            managed_policies = sso_admin_client.list_managed_policies_in_permission_set(
                InstanceArn=self._get_instance_arn(), PermissionSetArn=permission_set_arn
            )

            for policy in managed_policies["AttachedManagedPolicies"]:
                sso_admin_client.detach_managed_policy_from_permission_set(
                    InstanceArn=self._get_instance_arn(),
                    PermissionSetArn=permission_set_arn,
                    ManagedPolicyArn=policy["Arn"],
                )

            # Delete inline policy if it exists
            try:
                sso_admin_client.delete_inline_policy_from_permission_set(
                    InstanceArn=self._get_instance_arn(), PermissionSetArn=permission_set_arn
                )
            except Exception:
                # Inline policy might not exist, ignore error
                pass

            # Delete the permission set
            sso_admin_client.delete_permission_set(
                InstanceArn=self._get_instance_arn(), PermissionSetArn=permission_set_arn
            )

            logger.debug(f"Deleted permission set {permission_set_arn}")

        except Exception as e:
            logger.error(f"Failed to delete permission set {permission_set_arn}: {str(e)}")
            raise

    def _get_instance_arn(self) -> str:
        """Get the SSO instance ARN."""
        # This is a simplified implementation - in practice, you might want to
        # get this from configuration or the client manager
        try:
            sso_admin_client = self.client_manager.get_sso_admin_client()
            response = sso_admin_client.list_instances()
            instances = response.get("Instances", [])
            if instances:
                return instances[0]["InstanceArn"]
            else:
                raise ValueError("No SSO instances found")
        except Exception as e:
            logger.error(f"Failed to get SSO instance ARN: {str(e)}")
            raise
