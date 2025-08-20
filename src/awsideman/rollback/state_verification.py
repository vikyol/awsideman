"""State verification and consistency checks for rollback operations."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console

from ..aws_clients.manager import AWSClientManager
from .error_recovery import RollbackErrorRecovery, get_error_recovery
from .exceptions import (
    AWSClientNotAvailableError,
    IdempotencyViolationError,
    StateVerificationError,
)
from .models import (
    AssignmentState,
    OperationRecord,
    OperationType,
    RollbackAction,
    RollbackActionType,
)
from .storage import OperationStore

console = Console()
logger = logging.getLogger(__name__)


class VerificationLevel(str, Enum):
    """Levels of verification to perform."""

    BASIC = "basic"  # Check if assignment exists/doesn't exist
    DETAILED = "detailed"  # Check assignment details and metadata
    COMPREHENSIVE = "comprehensive"  # Full state verification with history


@dataclass
class AssignmentVerificationResult:
    """Result of verifying a single assignment."""

    account_id: str
    principal_id: str
    permission_set_arn: str
    expected_state: AssignmentState
    actual_state: AssignmentState
    verified: bool
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateVerificationResult:
    """Result of state verification for an operation."""

    operation_id: str
    verification_level: VerificationLevel
    total_assignments: int
    verified_assignments: int
    failed_verifications: int
    assignment_results: List[AssignmentVerificationResult] = field(default_factory=list)
    overall_verified: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verification_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class IdempotencyCheck:
    """Result of idempotency check."""

    operation_id: str
    is_idempotent: bool
    existing_rollback_ids: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class RollbackStateVerifier:
    """State verification system for rollback operations."""

    def __init__(
        self,
        aws_client_manager: Optional[AWSClientManager] = None,
        storage_directory: Optional[str] = None,
        store: Optional[OperationStore] = None,
        error_recovery: Optional[RollbackErrorRecovery] = None,
    ):
        """Initialize the state verifier.

        Args:
            aws_client_manager: AWS client manager for API calls
            storage_directory: Directory where operation records are stored
            store: Operation store instance (takes precedence over storage_directory)
            error_recovery: Error recovery system for handling failures
        """
        self.aws_client_manager = aws_client_manager
        self.store = store or OperationStore(storage_directory)
        self.error_recovery = error_recovery or get_error_recovery()

        # Initialize AWS clients if manager provided
        if self.aws_client_manager:
            self.identity_center_client = self.aws_client_manager.get_identity_center_client()
            self.identity_store_client = self.aws_client_manager.get_identity_store_client()
        else:
            self.identity_center_client = None
            self.identity_store_client = None

    def verify_pre_rollback_state(
        self,
        operation: OperationRecord,
        verification_level: VerificationLevel = VerificationLevel.BASIC,
    ) -> StateVerificationResult:
        """Verify the current state before performing rollback.

        Args:
            operation: The operation record to verify state for
            verification_level: Level of verification to perform

        Returns:
            StateVerificationResult: Results of state verification

        Raises:
            AWSClientNotAvailableError: If AWS client is not available
            StateVerificationError: If critical state verification fails
        """
        if not self.identity_center_client:
            raise AWSClientNotAvailableError("pre-rollback state verification")

        logger.info(
            f"Starting pre-rollback state verification for operation {operation.operation_id}"
        )

        # Extract SSO instance ARN
        sso_instance_arn = self._extract_sso_instance_arn(operation.permission_set_arn)
        if not sso_instance_arn:
            raise StateVerificationError(
                operation.operation_id,
                "unknown",
                "extractable_sso_instance",
                "not_extractable",
                {"permission_set_arn": operation.permission_set_arn},
            )

        assignment_results = []
        errors = []
        warnings = []

        # Verify each successful result from the original operation
        # Handle different operation record types
        if hasattr(operation, "results"):
            results_to_check = operation.results
        elif hasattr(operation, "accounts_affected"):
            # For PermissionCloningOperationRecord, create mock results from accounts
            results_to_check = [
                type("MockResult", (), {"account_id": account_id, "success": True})()
                for account_id in operation.accounts_affected
            ]
        else:
            results_to_check = []

        for result in results_to_check:
            if not result.success:
                warnings.append(f"Skipping verification for failed account {result.account_id}")
                continue

            verification_result = self._verify_single_assignment(
                operation=operation,
                account_id=result.account_id,
                sso_instance_arn=sso_instance_arn,
                verification_level=verification_level,
                is_pre_rollback=True,
            )

            assignment_results.append(verification_result)

            if not verification_result.verified and verification_result.error:
                errors.append(verification_result.error)

        # Calculate overall results
        total_assignments = len(assignment_results)
        verified_assignments = sum(1 for r in assignment_results if r.verified)
        failed_verifications = total_assignments - verified_assignments

        overall_verified = failed_verifications == 0

        result = StateVerificationResult(
            operation_id=operation.operation_id,
            verification_level=verification_level,
            total_assignments=total_assignments,
            verified_assignments=verified_assignments,
            failed_verifications=failed_verifications,
            assignment_results=assignment_results,
            overall_verified=overall_verified,
            errors=errors,
            warnings=warnings,
        )

        logger.info(
            f"Pre-rollback verification completed: {verified_assignments}/{total_assignments} verified"
        )

        return result

    def verify_post_rollback_state(
        self,
        operation: OperationRecord,
        rollback_actions: List[RollbackAction],
        verification_level: VerificationLevel = VerificationLevel.BASIC,
    ) -> StateVerificationResult:
        """Verify the state after performing rollback.

        Args:
            operation: The original operation record
            rollback_actions: The rollback actions that were performed
            verification_level: Level of verification to perform

        Returns:
            StateVerificationResult: Results of state verification

        Raises:
            AWSClientNotAvailableError: If AWS client is not available
        """
        if not self.identity_center_client:
            raise AWSClientNotAvailableError("post-rollback state verification")

        logger.info(
            f"Starting post-rollback state verification for operation {operation.operation_id}"
        )

        # Extract SSO instance ARN
        sso_instance_arn = self._extract_sso_instance_arn(operation.permission_set_arn)
        if not sso_instance_arn:
            return StateVerificationResult(
                operation_id=operation.operation_id,
                verification_level=verification_level,
                total_assignments=0,
                verified_assignments=0,
                failed_verifications=0,
                errors=["Could not extract SSO instance ARN"],
            )

        assignment_results = []
        errors = []
        warnings = []

        # Verify each rollback action
        for action in rollback_actions:
            verification_result = self._verify_rollback_action_result(
                operation=operation,
                action=action,
                sso_instance_arn=sso_instance_arn,
                verification_level=verification_level,
            )

            assignment_results.append(verification_result)

            if not verification_result.verified and verification_result.error:
                errors.append(verification_result.error)

        # Calculate overall results
        total_assignments = len(assignment_results)
        verified_assignments = sum(1 for r in assignment_results if r.verified)
        failed_verifications = total_assignments - verified_assignments

        overall_verified = failed_verifications == 0

        result = StateVerificationResult(
            operation_id=operation.operation_id,
            verification_level=verification_level,
            total_assignments=total_assignments,
            verified_assignments=verified_assignments,
            failed_verifications=failed_verifications,
            assignment_results=assignment_results,
            overall_verified=overall_verified,
            errors=errors,
            warnings=warnings,
        )

        logger.info(
            f"Post-rollback verification completed: {verified_assignments}/{total_assignments} verified"
        )

        return result

    def check_idempotency(self, operation_id: str) -> IdempotencyCheck:
        """Check if a rollback operation would be idempotent.

        Args:
            operation_id: The operation ID to check

        Returns:
            IdempotencyCheck: Results of idempotency check

        Raises:
            IdempotencyViolationError: If idempotency is violated
        """
        logger.debug(f"Checking idempotency for operation {operation_id}")

        # Check if operation exists
        operation = self.store.get_operation(operation_id)
        if not operation:
            return IdempotencyCheck(
                operation_id=operation_id,
                is_idempotent=False,
                conflicts=[f"Operation {operation_id} not found"],
            )

        # Check if already rolled back
        if operation.rolled_back:
            existing_rollback_id = operation.rollback_operation_id
            raise IdempotencyViolationError(operation_id, existing_rollback_id)

        # Check for duplicate rollback attempts in progress
        existing_rollbacks = self._find_existing_rollbacks(operation_id)
        if existing_rollbacks:
            return IdempotencyCheck(
                operation_id=operation_id,
                is_idempotent=False,
                existing_rollback_ids=existing_rollbacks,
                conflicts=[f"Found {len(existing_rollbacks)} existing rollback attempts"],
            )

        # Check for conflicting operations on the same resources
        conflicts = self._check_resource_conflicts(operation)

        is_idempotent = len(conflicts) == 0

        return IdempotencyCheck(
            operation_id=operation_id,
            is_idempotent=is_idempotent,
            conflicts=conflicts,
        )

    def _verify_single_assignment(
        self,
        operation: OperationRecord,
        account_id: str,
        sso_instance_arn: str,
        verification_level: VerificationLevel,
        is_pre_rollback: bool = True,
    ) -> AssignmentVerificationResult:
        """Verify a single assignment state.

        Args:
            operation: The operation record
            account_id: The account ID to verify
            sso_instance_arn: The SSO instance ARN
            verification_level: Level of verification to perform
            is_pre_rollback: Whether this is pre-rollback verification

        Returns:
            AssignmentVerificationResult: Verification result for the assignment
        """
        # Determine expected state based on original operation type
        if is_pre_rollback:
            # For pre-rollback, we expect the state to match the original operation
            if operation.operation_type == OperationType.ASSIGN:
                expected_state = AssignmentState.ASSIGNED
            else:
                expected_state = AssignmentState.NOT_ASSIGNED
        else:
            # For post-rollback, we expect the inverse state
            if operation.operation_type == OperationType.ASSIGN:
                expected_state = AssignmentState.NOT_ASSIGNED
            else:
                expected_state = AssignmentState.ASSIGNED

        def check_assignment_state():
            return self._get_current_assignment_state(operation, account_id, sso_instance_arn)

        # Use error recovery for state checking
        result = self.error_recovery.execute_with_recovery(
            check_assignment_state,
            "verify_assignment_state",
            {
                "operation_id": operation.operation_id,
                "account_id": account_id,
                "expected_state": expected_state.value,
            },
        )

        if result.success:
            actual_state = result  # This would be the return value from check_assignment_state
            # Note: This is simplified - in reality we'd need to handle the return value properly
            actual_state = self._get_current_assignment_state(
                operation, account_id, sso_instance_arn
            )
        else:
            actual_state = AssignmentState.UNKNOWN

        verified = actual_state == expected_state
        error = None
        warnings = []

        if not verified:
            if actual_state == AssignmentState.UNKNOWN:
                error = f"Could not determine assignment state for account {account_id}"
                if result.final_error:
                    error += f": {str(result.final_error)}"
            else:
                error = f"State mismatch for account {account_id}: expected {expected_state.value}, found {actual_state.value}"

        # Add recovery notes as warnings
        if result.recovery_notes:
            warnings.extend(result.recovery_notes)

        metadata = {}
        if verification_level in [VerificationLevel.DETAILED, VerificationLevel.COMPREHENSIVE]:
            metadata = self._get_assignment_metadata(
                operation, account_id, sso_instance_arn, verification_level
            )

        return AssignmentVerificationResult(
            account_id=account_id,
            principal_id=operation.principal_id,
            permission_set_arn=operation.permission_set_arn,
            expected_state=expected_state,
            actual_state=actual_state,
            verified=verified,
            error=error,
            warnings=warnings,
            metadata=metadata,
        )

    def _verify_rollback_action_result(
        self,
        operation: OperationRecord,
        action: RollbackAction,
        sso_instance_arn: str,
        verification_level: VerificationLevel,
    ) -> AssignmentVerificationResult:
        """Verify the result of a rollback action.

        Args:
            operation: The original operation record
            action: The rollback action that was performed
            sso_instance_arn: The SSO instance ARN
            verification_level: Level of verification to perform

        Returns:
            AssignmentVerificationResult: Verification result for the action
        """
        # Expected state after rollback action
        if action.action_type == RollbackActionType.ASSIGN:
            expected_state = AssignmentState.ASSIGNED
        else:
            expected_state = AssignmentState.NOT_ASSIGNED

        actual_state = self._get_current_assignment_state(
            operation, action.account_id, sso_instance_arn
        )

        verified = actual_state == expected_state
        error = None
        warnings = []

        if not verified:
            if actual_state == AssignmentState.UNKNOWN:
                error = f"Could not determine assignment state for account {action.account_id}"
            else:
                error = f"Rollback verification failed for account {action.account_id}: expected {expected_state.value}, found {actual_state.value}"

        metadata = {}
        if verification_level in [VerificationLevel.DETAILED, VerificationLevel.COMPREHENSIVE]:
            metadata = self._get_assignment_metadata(
                operation, action.account_id, sso_instance_arn, verification_level
            )

        return AssignmentVerificationResult(
            account_id=action.account_id,
            principal_id=action.principal_id,
            permission_set_arn=action.permission_set_arn,
            expected_state=expected_state,
            actual_state=actual_state,
            verified=verified,
            error=error,
            warnings=warnings,
            metadata=metadata,
        )

    def _get_current_assignment_state(
        self, operation: OperationRecord, account_id: str, sso_instance_arn: str
    ) -> AssignmentState:
        """Get the current state of an assignment.

        Args:
            operation: The operation record
            account_id: The account ID to check
            sso_instance_arn: The SSO instance ARN

        Returns:
            AssignmentState: Current assignment state
        """
        if not self.identity_center_client:
            return AssignmentState.UNKNOWN

        try:
            # Check if assignment exists
            current_assignments = self.identity_center_client.list_account_assignments(
                InstanceArn=sso_instance_arn,
                AccountId=account_id,
                PermissionSetArn=operation.permission_set_arn,
            )

            # Look for matching assignment
            for assignment in current_assignments.get("AccountAssignments", []):
                if (
                    assignment["PrincipalId"] == operation.principal_id
                    and assignment["PrincipalType"] == operation.principal_type.value
                ):
                    return AssignmentState.ASSIGNED

            return AssignmentState.NOT_ASSIGNED

        except ClientError as e:
            logger.warning(f"Could not check assignment state for account {account_id}: {e}")
            return AssignmentState.UNKNOWN
        except Exception as e:
            logger.warning(
                f"Unexpected error checking assignment state for account {account_id}: {e}"
            )
            return AssignmentState.UNKNOWN

    def _get_assignment_metadata(
        self,
        operation: OperationRecord,
        account_id: str,
        sso_instance_arn: str,
        verification_level: VerificationLevel,
    ) -> Dict[str, Any]:
        """Get metadata about an assignment for detailed verification.

        Args:
            operation: The operation record
            account_id: The account ID
            sso_instance_arn: The SSO instance ARN
            verification_level: Level of verification

        Returns:
            Dict containing assignment metadata
        """
        metadata = {}

        try:
            if verification_level == VerificationLevel.DETAILED:
                # Get basic assignment details
                metadata["account_id"] = account_id
                metadata["permission_set_name"] = operation.permission_set_name
                metadata["principal_name"] = operation.principal_name
                metadata["principal_type"] = operation.principal_type.value

            elif verification_level == VerificationLevel.COMPREHENSIVE:
                # Get comprehensive assignment information
                metadata.update(
                    {
                        "account_id": account_id,
                        "permission_set_name": operation.permission_set_name,
                        "principal_name": operation.principal_name,
                        "principal_type": operation.principal_type.value,
                        "verification_timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

                # Try to get additional assignment details
                try:
                    assignments = self.identity_center_client.list_account_assignments(
                        InstanceArn=sso_instance_arn,
                        AccountId=account_id,
                        PermissionSetArn=operation.permission_set_arn,
                    )

                    for assignment in assignments.get("AccountAssignments", []):
                        if (
                            assignment["PrincipalId"] == operation.principal_id
                            and assignment["PrincipalType"] == operation.principal_type.value
                        ):
                            metadata["assignment_details"] = assignment
                            break

                except Exception as e:
                    metadata["assignment_details_error"] = str(e)

        except Exception as e:
            metadata["metadata_error"] = str(e)

        return metadata

    def _extract_sso_instance_arn(self, permission_set_arn: str) -> Optional[str]:
        """Extract SSO instance ARN from permission set ARN.

        Args:
            permission_set_arn: Permission set ARN

        Returns:
            SSO instance ARN if extractable, None otherwise
        """
        try:
            # Permission set ARN format: arn:aws:sso:::permissionSet/ssoins-{instance-id}/ps-{permission-set-id}
            parts = permission_set_arn.split("/")
            if len(parts) >= 2 and parts[1].startswith("ssoins-"):
                instance_id = parts[1]
                # SSO instance ARN format: arn:aws:sso:::instance/{instance-id}
                return f"arn:aws:sso:::instance/{instance_id}"
        except Exception:
            pass
        return None

    def _find_existing_rollbacks(self, operation_id: str) -> List[str]:
        """Find existing rollback operations for the given operation ID.

        Args:
            operation_id: The operation ID to check

        Returns:
            List of existing rollback operation IDs
        """
        try:
            # This would need to be implemented based on how rollback records are stored
            # For now, return empty list as placeholder
            return []
        except Exception as e:
            logger.warning(f"Could not check for existing rollbacks: {e}")
            return []

    def _check_resource_conflicts(self, operation: OperationRecord) -> List[str]:
        """Check for conflicting operations on the same resources.

        Args:
            operation: The operation record to check

        Returns:
            List of conflict descriptions
        """
        conflicts = []

        try:
            # Check for recent operations on the same principal/permission set/accounts
            # This would need to be implemented based on operation history
            # For now, return empty list as placeholder
            pass

        except Exception as e:
            logger.warning(f"Could not check for resource conflicts: {e}")
            conflicts.append(f"Could not check for resource conflicts: {str(e)}")

        return conflicts


# Global state verifier instance
_global_state_verifier: Optional[RollbackStateVerifier] = None


def get_state_verifier(
    aws_client_manager: Optional[AWSClientManager] = None,
    storage_directory: Optional[str] = None,
) -> RollbackStateVerifier:
    """Get the global state verifier instance."""
    global _global_state_verifier
    if _global_state_verifier is None:
        _global_state_verifier = RollbackStateVerifier(
            aws_client_manager=aws_client_manager,
            storage_directory=storage_directory,
        )
    return _global_state_verifier
