"""Rollback processor for handling rollback operations."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console

from ..aws_clients.manager import AWSClientManager
from ..utils.config import Config
from .error_recovery import RollbackErrorRecovery, get_error_recovery
from .exceptions import IdempotencyViolationError, StateVerificationError
from .models import (
    AssignmentState,
    OperationRecord,
    OperationType,
    RollbackAction,
    RollbackActionType,
    RollbackPlan,
    RollbackResult,
    RollbackValidation,
    RollbackVerification,
)
from .performance import PerformanceTracker, measure_time
from .state_verification import RollbackStateVerifier, VerificationLevel
from .storage_monitor import StorageMonitor

console = Console()


class RollbackProcessor:
    """Processor for handling rollback operations."""

    def __init__(
        self,
        storage_directory: Optional[str] = None,
        aws_client_manager: Optional[AWSClientManager] = None,
        config: Optional[Config] = None,
        error_recovery: Optional[RollbackErrorRecovery] = None,
        state_verifier: Optional[RollbackStateVerifier] = None,
        performance_tracker: Optional[PerformanceTracker] = None,
        show_progress: bool = False,  # Changed default to False to disable progress tracking
    ):
        """Initialize the rollback processor.

        Args:
            storage_directory: Directory where operation records are stored.
            aws_client_manager: AWS client manager for API calls.
            config: Configuration object.
            error_recovery: Error recovery system for handling failures.
            state_verifier: State verification system for consistency checks.
            performance_tracker: Performance tracking system.
            show_progress: Whether to show progress bars during operations. Defaults to False.
        """
        # Set config first since it's used in other initializations
        self.config = config or Config()

        # Use the same storage backend as OperationLogger for consistency
        from .storage import OperationStore

        self.store = OperationStore(storage_directory=storage_directory)
        self.storage_monitor = StorageMonitor(storage_directory)
        self.aws_client_manager = aws_client_manager
        self.error_recovery = error_recovery or get_error_recovery()
        self.state_verifier = state_verifier or RollbackStateVerifier(
            aws_client_manager=aws_client_manager,
            storage_directory=storage_directory,
            store=self.store,  # Pass the store instance
            error_recovery=self.error_recovery,
        )
        self.performance_tracker = performance_tracker or PerformanceTracker(storage_directory)
        # Disable progress tracking completely
        self.progress_tracker = None

        # Initialize AWS clients if manager provided
        if self.aws_client_manager:
            self.identity_center_client = self.aws_client_manager.get_identity_center_client()
            self.identity_store_client = self.aws_client_manager.get_identity_store_client()
        else:
            self.identity_center_client = None
            self.identity_store_client = None

    def validate_rollback(
        self,
        operation_id: str,
        verify_state: bool = True,
        check_idempotency: bool = True,
    ) -> RollbackValidation:
        """Validate if a rollback operation is feasible.

        Args:
            operation_id: The operation ID to validate for rollback
            verify_state: Whether to perform state verification
            check_idempotency: Whether to check for idempotency violations

        Returns:
            RollbackValidation with validation results

        Raises:
            OperationNotFoundError: If the operation is not found
            OperationAlreadyRolledBackError: If the operation is already rolled back
            IdempotencyViolationError: If idempotency is violated
            RollbackValidationError: If validation fails with multiple errors
        """
        errors = []
        warnings = []

        # Check if operation exists
        operation = self.store.get_operation(operation_id)
        if not operation:
            return RollbackValidation(
                valid=False, errors=[f"Operation {operation_id} not found"], warnings=[]
            )

        # Check idempotency if requested
        if check_idempotency:
            try:
                idempotency_check = self.state_verifier.check_idempotency(operation_id)
                if not idempotency_check.is_idempotent:
                    if idempotency_check.existing_rollback_ids:
                        # Handle idempotency violations by returning validation result
                        return RollbackValidation(
                            valid=False,
                            errors=[
                                f"Operation {operation_id} has already been rolled back",
                                f"Rollback operation ID: {idempotency_check.existing_rollback_ids[0]}",
                            ],
                            warnings=[],
                        )
                    else:
                        warnings.extend(idempotency_check.conflicts)
            except IdempotencyViolationError as e:
                # Handle idempotency violations by returning validation result
                return RollbackValidation(
                    valid=False,
                    errors=[
                        f"Operation {operation_id} has already been rolled back",
                        f"Rollback operation ID: {e.duplicate_rollback_id}",
                    ],
                    warnings=[],
                )
            except Exception as e:
                warnings.append(f"Could not check idempotency: {str(e)}")

        # Check if already rolled back (this is also checked in idempotency)
        if operation.rolled_back:
            return RollbackValidation(
                valid=False,
                errors=[
                    f"Operation {operation_id} has already been rolled back",
                    f"Rollback operation ID: {operation.rollback_operation_id}",
                ],
                warnings=[],
            )

        # Check if all results were successful
        # Handle different operation record types
        if hasattr(operation, "results"):
            failed_results = [r for r in operation.results if not r.success]
            successful_results = [r for r in operation.results if r.success]
        elif hasattr(operation, "assignments_copied"):
            # For PermissionCloningOperationRecord, all assignments are considered successful
            failed_results = []
            successful_results = operation.assignments_copied
        else:
            failed_results = []
            successful_results = []

        if failed_results:
            warnings.append(
                f"Operation had {len(failed_results)} failed results that cannot be rolled back"
            )

        if not successful_results:
            errors.append("Operation has no successful results to roll back")

        # Validate AWS permissions if client is available
        if self.identity_center_client and successful_results:
            try:
                # Check if we can access the SSO instance
                sso_instance_arn = self._extract_sso_instance_arn(operation.permission_set_arn)
                if sso_instance_arn:
                    # Try to list permission sets to verify access
                    def verify_permissions():
                        return self.identity_center_client.list_permission_sets(
                            InstanceArn=sso_instance_arn, MaxResults=1
                        )

                    # Use error recovery for permission verification
                    result = self.error_recovery.execute_with_recovery(
                        verify_permissions,
                        "verify_aws_permissions",
                        {"operation_id": operation_id, "sso_instance_arn": sso_instance_arn},
                    )

                    if not result.success and result.final_error:
                        if isinstance(result.final_error, ClientError):
                            error_code = result.final_error.response.get("Error", {}).get(
                                "Code", "Unknown"
                            )
                            if error_code in ["AccessDenied", "UnauthorizedOperation"]:
                                errors.append(
                                    f"Insufficient permissions for rollback operations: {error_code}"
                                )
                            else:
                                warnings.append(f"Could not verify AWS permissions: {error_code}")
                        else:
                            warnings.append(
                                f"Could not verify AWS permissions: {str(result.final_error)}"
                            )
                else:
                    warnings.append("Could not extract SSO instance ARN from permission set ARN")
            except Exception as e:
                warnings.append(f"Could not verify AWS permissions: {str(e)}")

        # Check for state conflicts if AWS client is available
        if self.identity_center_client and successful_results:
            try:
                state_conflicts = self._check_state_conflicts(operation)
                warnings.extend(state_conflicts)
            except Exception as e:
                warnings.append(f"Could not check state conflicts: {str(e)}")

        # Perform state verification if requested
        if verify_state and self.identity_center_client and successful_results:
            try:
                state_verification = self.state_verifier.verify_pre_rollback_state(
                    operation, VerificationLevel.BASIC
                )

                if not state_verification.overall_verified:
                    warnings.append(
                        f"State verification found {state_verification.failed_verifications} mismatches"
                    )
                    warnings.extend(state_verification.warnings)

                    # Add specific state errors as warnings (not blocking errors)
                    for error in state_verification.errors:
                        warnings.append(f"State verification: {error}")

            except StateVerificationError as e:
                # State verification errors are warnings, not blocking errors
                warnings.append(f"State verification failed: {str(e)}")
            except Exception as e:
                warnings.append(f"Could not perform state verification: {str(e)}")

        is_valid = len(errors) == 0

        # Return validation result instead of raising exception
        return RollbackValidation(valid=is_valid, errors=errors, warnings=warnings)

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

    def _check_state_conflicts(self, operation: OperationRecord) -> List[str]:
        """Check for state conflicts that might prevent rollback.

        Args:
            operation: The operation record to check

        Returns:
            List of conflict warnings
        """
        conflicts = []

        try:
            sso_instance_arn = self._extract_sso_instance_arn(operation.permission_set_arn)
            if not sso_instance_arn:
                return ["Could not extract SSO instance ARN for state verification"]

            # Check current assignment state for successful results
            # Handle different operation record types
            if hasattr(operation, "results"):
                results_to_check = operation.results
            elif hasattr(operation, "accounts_affected"):
                # For PermissionCloningOperationRecord, create mock results from accounts
                results_to_check = [
                    {"account_id": account_id, "success": True}
                    for account_id in operation.accounts_affected
                ]
            else:
                results_to_check = []

            for result in results_to_check:
                # Handle different result formats
                if hasattr(result, "success"):
                    if not result.success:
                        continue
                    account_id = result.account_id
                elif isinstance(result, dict):
                    if not result.get("success", True):
                        continue
                    account_id = result["account_id"]
                else:
                    continue

                try:
                    # Check if assignment currently exists
                    current_assignments = self.identity_center_client.list_account_assignments(
                        InstanceArn=sso_instance_arn,
                        AccountId=account_id,
                        PermissionSetArn=operation.permission_set_arn,
                    )

                    # Look for matching assignment
                    assignment_exists = False

                    # Determine which principal to check based on operation type
                    if hasattr(operation, "principal_id"):
                        check_principal_id = operation.principal_id
                        check_principal_type = operation.principal_type.value
                    elif hasattr(operation, "source_entity_id"):
                        if operation.operation_type == OperationType.COPY_ASSIGNMENTS:
                            # For copy operations, check the target user's assignments
                            check_principal_id = operation.target_entity_id
                            check_principal_type = operation.target_entity_type.value
                        else:
                            # For other operations, use source entity info
                            check_principal_id = operation.source_entity_id
                            check_principal_type = operation.source_entity_type.value
                    else:
                        continue

                    for assignment in current_assignments.get("AccountAssignments", []):
                        if (
                            assignment["PrincipalId"] == check_principal_id
                            and assignment["PrincipalType"] == check_principal_type
                        ):
                            assignment_exists = True
                            break

                    # Check for conflicts based on operation type
                    if (
                        operation.operation_type == OperationType.ASSIGN
                        or operation.operation_type == OperationType.COPY_ASSIGNMENTS
                    ):
                        # If original was assign or copy, rollback is revoke
                        # Assignment should exist for rollback to work
                        if not assignment_exists:
                            conflicts.append(
                                f"Assignment no longer exists for account {account_id} "
                                f"(may have been manually revoked)"
                            )
                    else:
                        # If original was revoke, rollback is assign
                        # Assignment should not exist for rollback to work
                        if assignment_exists:
                            conflicts.append(
                                f"Assignment already exists for account {account_id} "
                                f"(may have been manually re-assigned)"
                            )

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    conflicts.append(
                        f"Could not verify state for account {account_id}: {error_code}"
                    )
                except Exception as e:
                    conflicts.append(f"Could not verify state for account {account_id}: {str(e)}")

        except Exception as e:
            conflicts.append(f"State conflict check failed: {str(e)}")

        return conflicts

    def generate_plan(self, operation_id: str) -> Optional[RollbackPlan]:
        """Generate a rollback plan for the specified operation.

        Args:
            operation_id: The operation ID to generate a rollback plan for

        Returns:
            RollbackPlan if the operation can be rolled back, None otherwise
        """
        operation = self.store.get_operation(operation_id)
        if not operation:
            return None

        # Determine rollback type (inverse of original operation)
        if (
            operation.operation_type == OperationType.ASSIGN
            or operation.operation_type == OperationType.COPY_ASSIGNMENTS
        ):
            # Both ASSIGN and COPY_ASSIGNMENTS operations assign permissions, so rollback should revoke
            rollback_type = RollbackActionType.REVOKE
        else:
            # REVOKE operations remove permissions, so rollback should assign back
            rollback_type = RollbackActionType.ASSIGN

        # Generate rollback actions for successful results only
        actions = []
        warnings = []

        # Handle different operation record types
        if hasattr(operation, "results"):
            results_to_process = operation.results
        elif hasattr(operation, "accounts_affected"):
            # For PermissionCloningOperationRecord, create mock results from accounts
            results_to_process = [
                {"account_id": account_id, "success": True}
                for account_id in operation.accounts_affected
            ]
        else:
            results_to_process = []

        for result in results_to_process:
            # Handle different result formats
            if hasattr(result, "success"):
                success = result.success
                account_id = result.account_id
                error = getattr(result, "error", "Unknown error")
            elif isinstance(result, dict):
                success = result.get("success", True)
                account_id = result["account_id"]
                error = result.get("error", "Unknown error")
            else:
                continue

            if success:
                # Determine current state if AWS client is available
                current_state = self._get_current_assignment_state(operation, account_id)

                # Handle different operation record types for principal and permission set info
                if hasattr(operation, "principal_id"):
                    principal_id = operation.principal_id
                    permission_set_arn = operation.permission_set_arn
                    principal_type = operation.principal_type
                elif hasattr(operation, "source_entity_id"):
                    # For PermissionCloningOperationRecord, determine the correct principal based on operation type
                    if operation.operation_type == OperationType.COPY_ASSIGNMENTS:
                        # For copy operations, rollback should affect the TARGET user (who received the permissions)
                        principal_id = operation.target_entity_id
                        principal_type = operation.target_entity_type
                    else:
                        # For other operations, use source entity info
                        principal_id = operation.source_entity_id
                        principal_type = operation.source_entity_type

                    permission_set_arn = (
                        operation.permission_sets_involved[0]
                        if operation.permission_sets_involved
                        else ""
                    )
                else:
                    continue

                action = RollbackAction(
                    principal_id=principal_id,
                    permission_set_arn=permission_set_arn,
                    account_id=account_id,
                    action_type=rollback_type,
                    current_state=current_state,
                    principal_type=principal_type,
                )
                actions.append(action)
            else:
                warnings.append(
                    f"Skipping rollback for account {account_id} due to original failure: {error}"
                )

        # Filter out actions that are already in the desired state and add warnings
        filtered_actions = []
        for action in actions:
            if (
                rollback_type == RollbackActionType.REVOKE
                and action.current_state == AssignmentState.NOT_ASSIGNED
            ):
                warnings.append(
                    f"Account {action.account_id}: Assignment already revoked, skipping rollback action"
                )
                # Skip this action as it's already in the desired state
            elif (
                rollback_type == RollbackActionType.ASSIGN
                and action.current_state == AssignmentState.ASSIGNED
            ):
                warnings.append(
                    f"Account {action.account_id}: Assignment already exists, skipping rollback action"
                )
                # Skip this action as it's already in the desired state
            else:
                # Include this action as it needs to be processed
                filtered_actions.append(action)

        # Update actions list to only include necessary actions
        actions = filtered_actions

        # Estimate duration based on number of actions and complexity
        base_time_per_action = 3  # Base time in seconds
        complexity_factor = 1.2 if len(actions) > 10 else 1.0  # More time for larger batches
        estimated_duration = int(len(actions) * base_time_per_action * complexity_factor)

        return RollbackPlan(
            operation_id=operation_id,
            rollback_type=rollback_type,
            actions=actions,
            estimated_duration=estimated_duration,
            warnings=warnings,
        )

    def _get_current_assignment_state(
        self, operation: OperationRecord, account_id: str
    ) -> AssignmentState:
        """Get the current state of an assignment.

        Args:
            operation: The operation record
            account_id: The account ID to check

        Returns:
            Current assignment state
        """
        if not self.identity_center_client:
            return AssignmentState.UNKNOWN

        try:
            # Handle different operation record types
            if hasattr(operation, "permission_set_arn"):
                permission_set_arn = operation.permission_set_arn
                principal_id = operation.principal_id
                principal_type = operation.principal_type.value
            elif (
                hasattr(operation, "permission_sets_involved")
                and operation.permission_sets_involved
            ):
                permission_set_arn = operation.permission_sets_involved[0]
                if operation.operation_type == OperationType.COPY_ASSIGNMENTS:
                    # For copy operations, check the target user's assignments
                    principal_id = operation.target_entity_id
                    principal_type = operation.target_entity_type.value
                else:
                    # For other operations, use source entity info
                    principal_id = operation.source_entity_id
                    principal_type = operation.source_entity_type.value
            else:
                return AssignmentState.UNKNOWN

            sso_instance_arn = self._extract_sso_instance_arn(permission_set_arn)
            if not sso_instance_arn:
                return AssignmentState.UNKNOWN

            # Check if assignment exists
            current_assignments = self.identity_center_client.list_account_assignments(
                InstanceArn=sso_instance_arn,
                AccountId=account_id,
                PermissionSetArn=permission_set_arn,
            )

            # Look for matching assignment
            for assignment in current_assignments.get("AccountAssignments", []):
                if (
                    assignment["PrincipalId"] == principal_id
                    and assignment["PrincipalType"] == principal_type
                ):
                    return AssignmentState.ASSIGNED

            return AssignmentState.NOT_ASSIGNED

        except ClientError as e:
            console.print(
                f"[yellow]Warning: Could not check assignment state for account {account_id}: {e}[/yellow]"
            )
            return AssignmentState.UNKNOWN
        except Exception as e:
            console.print(
                f"[yellow]Warning: Unexpected error checking assignment state for account {account_id}: {e}[/yellow]"
            )
            return AssignmentState.UNKNOWN

    def execute_rollback(
        self,
        plan: RollbackPlan,
        dry_run: bool = False,
        batch_size: int = 10,
        verify_post_rollback: bool = True,
    ) -> RollbackResult:
        """Execute a rollback plan with comprehensive error handling and performance monitoring.

        Args:
            plan: The rollback plan to execute
            dry_run: If True, simulate the rollback without making changes
            batch_size: Number of actions to process in parallel
            verify_post_rollback: Whether to verify state after rollback

        Returns:
            RollbackResult with execution results

        Raises:
            AWSClientNotAvailableError: If AWS client is not available
            RollbackExecutionError: If rollback execution fails completely
        """
        rollback_operation_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)

        # Start performance tracking
        _operation_metrics = self.performance_tracker.start_operation_tracking(
            plan.operation_id,
            rollback_operation_id,
            len(plan.actions),
            batch_size,
        )

        if dry_run:
            # Simulate successful execution for dry run
            self.performance_tracker.finish_operation_tracking(rollback_operation_id)
            return RollbackResult(
                rollback_operation_id="dry-run",
                success=True,
                completed_actions=len(plan.actions),
                failed_actions=0,
                errors=[],
                duration_ms=0,
            )

        if not self.identity_center_client:
            self.performance_tracker.finish_operation_tracking(rollback_operation_id)
            return RollbackResult(
                rollback_operation_id=rollback_operation_id,
                success=False,
                completed_actions=0,
                failed_actions=len(plan.actions),
                errors=["AWS client not available for rollback execution"],
                duration_ms=0,
            )

        completed_actions = 0
        failed_actions = 0
        errors = []
        recovery_results = []

        # Get SSO instance ARN
        sso_instance_arn = None
        if plan.actions:
            with measure_time(
                "extract_sso_instance_arn", self.performance_tracker, rollback_operation_id
            ):
                sso_instance_arn = self._extract_sso_instance_arn(
                    plan.actions[0].permission_set_arn
                )
                if not sso_instance_arn:
                    self.performance_tracker.finish_operation_tracking(rollback_operation_id)
                    return RollbackResult(
                        rollback_operation_id=rollback_operation_id,
                        success=False,
                        completed_actions=0,
                        failed_actions=len(plan.actions),
                        errors=["Could not extract SSO instance ARN"],
                        duration_ms=0,
                    )

        # Check if there are actions to process
        if not plan.actions:
            # If no actions, return early
            return RollbackResult(
                success=True,
                rollback_operation_id=rollback_operation_id,
                completed_actions=0,
                failed_actions=0,
                errors=[],
                duration_ms=0,
            )

        # Process actions in batches (progress tracking disabled)
        console.print(f"[blue]Rolling back {len(plan.actions)} assignments...[/blue]")
        for i in range(0, len(plan.actions), batch_size):
            batch = plan.actions[i : i + batch_size]
            batch_start_time = datetime.now(timezone.utc)

            with measure_time(
                f"batch_{i//batch_size}", self.performance_tracker, rollback_operation_id
            ):
                for action in batch:
                    action_start_time = datetime.now(timezone.utc)

                    def execute_action():
                        import concurrent.futures

                        def aws_api_call():
                            try:
                                if action.action_type == RollbackActionType.ASSIGN:
                                    # For assign operations, check if assignment already exists
                                    existing_assignments = (
                                        self.identity_center_client.list_account_assignments(
                                            InstanceArn=sso_instance_arn,
                                            AccountId=action.account_id,
                                            PermissionSetArn=action.permission_set_arn,
                                        )
                                    )

                                    # Check if assignment already exists
                                    assignment_exists = any(
                                        assignment.get("PrincipalId") == action.principal_id
                                        and assignment.get("PrincipalType")
                                        == action.principal_type.value
                                        for assignment in existing_assignments.get(
                                            "AccountAssignments", []
                                        )
                                    )

                                    if assignment_exists:
                                        console.print(
                                            f"[yellow]Assignment already exists for account {action.account_id}, skipping creation[/yellow]"
                                        )
                                        # Return a mock successful response
                                        return {
                                            "AccountAssignmentCreationStatus": {
                                                "Status": "SUCCEEDED",
                                                "TargetId": action.account_id,
                                                "RequestId": "already-exists",
                                            }
                                        }

                                    # Create assignment
                                    response = (
                                        self.identity_center_client.create_account_assignment(
                                            InstanceArn=sso_instance_arn,
                                            TargetId=action.account_id,
                                            TargetType="AWS_ACCOUNT",
                                            PermissionSetArn=action.permission_set_arn,
                                            PrincipalType=self._get_principal_type_from_action(
                                                action
                                            ),
                                            PrincipalId=action.principal_id,
                                        )
                                    )
                                    return response
                                else:
                                    # For delete operations, check if assignment exists before attempting deletion
                                    existing_assignments = (
                                        self.identity_center_client.list_account_assignments(
                                            InstanceArn=sso_instance_arn,
                                            AccountId=action.account_id,
                                            PermissionSetArn=action.permission_set_arn,
                                        )
                                    )

                                    # Check if assignment exists
                                    assignment_exists = any(
                                        assignment.get("PrincipalId") == action.principal_id
                                        and assignment.get("PrincipalType")
                                        == action.principal_type.value
                                        for assignment in existing_assignments.get(
                                            "AccountAssignments", []
                                        )
                                    )
                                    if not assignment_exists:
                                        console.print(
                                            f"[yellow]Assignment already deleted for account {action.account_id}, skipping deletion[/yellow]"
                                        )
                                        # Return a mock successful response
                                        return {
                                            "AccountAssignmentDeletionStatus": {
                                                "Status": "SUCCEEDED",
                                                "TargetId": action.account_id,
                                                "RequestId": "already-deleted",
                                            }
                                        }

                                    # Delete assignment
                                    response = (
                                        self.identity_center_client.delete_account_assignment(
                                            InstanceArn=sso_instance_arn,
                                            TargetId=action.account_id,
                                            TargetType="AWS_ACCOUNT",
                                            PermissionSetArn=action.permission_set_arn,
                                            PrincipalType=self._get_principal_type_from_action(
                                                action
                                            ),
                                            PrincipalId=action.principal_id,
                                        )
                                    )
                                    return response
                            except Exception as e:
                                console.print(f"[red]AWS API call failed: {str(e)}[/red]")
                                raise

                        # Execute AWS API call with timeout using ThreadPoolExecutor
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(aws_api_call)
                            try:
                                # Wait up to 60 seconds for the AWS API call to complete
                                result = future.result(timeout=60)
                                return result
                            except concurrent.futures.TimeoutError:
                                console.print(
                                    f"[red]AWS API call timed out after 60 seconds for account {action.account_id}[/red]"
                                )
                                raise TimeoutError("AWS API call timed out after 60 seconds")

                    # Execute action with error recovery
                    result = self.error_recovery.execute_with_recovery(
                        execute_action,
                        f"rollback_action_{action.action_type.value}",
                        {
                            "operation_id": plan.operation_id,
                            "rollback_operation_id": rollback_operation_id,
                            "account_id": action.account_id,
                            "action_type": action.action_type.value,
                        },
                    )

                    recovery_results.append(result)

                    # Record action performance metrics
                    action_duration = (
                        datetime.now(timezone.utc) - action_start_time
                    ).total_seconds() * 1000
                    self.performance_tracker.add_operation_metric(
                        rollback_operation_id,
                        f"action_{action.action_type.value}_duration",
                        action_duration,
                        "ms",
                        {
                            "account_id": action.account_id,
                            "success": result.success,
                            "attempts": getattr(result, "attempts", 1),
                        },
                    )

                    if result.success:
                        completed_actions += 1
                        if result.recovery_notes:
                            console.print(
                                f"[yellow]Account {action.account_id}: {'; '.join(result.recovery_notes)}[/yellow]"
                            )
                    else:
                        failed_actions += 1
                        error_msg = f"Account {action.account_id}: {str(result.final_error)}"
                        errors.append(error_msg)
                        console.print(f"[red]Error: {error_msg}[/red]")

                    # Progress tracking disabled - continuing with operation

                    # Update performance tracking
                    self.performance_tracker.update_operation_progress(
                        rollback_operation_id, completed_actions, failed_actions
                    )

                # Record batch performance metrics
                batch_duration = (
                    datetime.now(timezone.utc) - batch_start_time
                ).total_seconds() * 1000
                self.performance_tracker.add_operation_metric(
                    rollback_operation_id,
                    f"batch_{i//batch_size}_duration",
                    batch_duration,
                    "ms",
                    {
                        "batch_size": len(batch),
                        "completed_in_batch": sum(
                            1 for r in recovery_results[-len(batch) :] if r.success
                        ),
                        "failed_in_batch": sum(
                            1 for r in recovery_results[-len(batch) :] if not r.success
                        ),
                    },
                )

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Handle partial failures using error recovery
        if failed_actions > 0 and completed_actions > 0:
            partial_result = self.error_recovery.handle_partial_failure(
                plan.operation_id,
                rollback_operation_id,
                completed_actions,
                failed_actions,
                len(plan.actions),
                errors,
            )

            # Log recovery notes
            if partial_result.recovery_notes:
                for note in partial_result.recovery_notes:
                    console.print(f"[blue]Recovery: {note}[/blue]")

        # Log the rollback operation
        if completed_actions > 0:
            try:
                with measure_time(
                    "log_rollback_operation", self.performance_tracker, rollback_operation_id
                ):
                    self._log_rollback_operation(
                        plan, rollback_operation_id, completed_actions, failed_actions
                    )

                    # Mark original operation as rolled back if all actions succeeded
                    if failed_actions == 0:
                        self.store.mark_operation_rolled_back(
                            plan.operation_id, rollback_operation_id
                        )
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not log rollback operation: {str(e)}[/yellow]"
                )

        success = failed_actions == 0 and completed_actions > 0

        # Print recovery summary
        if recovery_results:
            summary = self.error_recovery.get_recovery_summary(recovery_results)
            console.print(
                f"[dim]Recovery Summary: {summary['successful_operations']}/{summary['total_operations']} actions successful, "
                f"avg attempts: {summary['average_attempts']:.1f}[/dim]"
            )

        # Finish performance tracking and get final metrics
        final_metrics = self.performance_tracker.finish_operation_tracking(rollback_operation_id)
        if (
            final_metrics
            and hasattr(final_metrics, "actions_per_second")
            and final_metrics.actions_per_second is not None
        ):
            console.print(
                f"[dim]Performance: {final_metrics.actions_per_second:.1f} actions/sec, "
                f"{final_metrics.duration_ms}ms total[/dim]"
            )

            # Get optimization recommendations
            from .performance import PerformanceBenchmark

            recommendations = PerformanceBenchmark.get_optimization_recommendations(final_metrics)
            if recommendations:
                console.print("[dim]Optimization suggestions:[/dim]")
                for rec in recommendations[:3]:  # Show top 3 recommendations
                    console.print(f"[dim]  • {rec}[/dim]")

        result = RollbackResult(
            rollback_operation_id=rollback_operation_id,
            success=success,
            completed_actions=completed_actions,
            failed_actions=failed_actions,
            errors=errors,
            duration_ms=duration_ms,
        )

        # Perform post-rollback state verification if requested and not dry run
        verification_enabled = (
            getattr(self.config, "rollback", {}).get("verification", {}).get("enabled", True)
        )
        if verify_post_rollback and verification_enabled and not dry_run and completed_actions > 0:
            try:
                operation = self.store.get_operation(plan.operation_id)
                if operation:
                    console.print("[dim]Verifying rollback results...[/dim]")

                    # Only verify actions that completed successfully
                    successful_actions = []
                    for i, action in enumerate(plan.actions):
                        if i < len(recovery_results) and recovery_results[i].success:
                            successful_actions.append(action)

                    if successful_actions:
                        # Add delay to allow AWS Identity Center to propagate changes
                        import time

                        verification_delay = (
                            getattr(self.config, "rollback", {})
                            .get("verification", {})
                            .get("delay_seconds", 10)
                        )
                        if verification_delay > 0:
                            console.print(
                                f"[dim]Waiting {verification_delay} seconds for AWS Identity Center to propagate changes...[/dim]"
                            )
                            time.sleep(verification_delay)

                        with measure_time(
                            "post_rollback_verification",
                            self.performance_tracker,
                            rollback_operation_id,
                        ):
                            # Try verification with retries for eventual consistency
                            max_retries = (
                                getattr(self.config, "rollback", {})
                                .get("verification", {})
                                .get("max_retries", 3)
                            )
                            retry_delay = (
                                getattr(self.config, "rollback", {})
                                .get("verification", {})
                                .get("retry_delay_seconds", 5)
                            )

                            verification_result = None
                            for attempt in range(max_retries):
                                verification_result = (
                                    self.state_verifier.verify_post_rollback_state(
                                        operation, successful_actions, VerificationLevel.BASIC
                                    )
                                )

                                if verification_result.overall_verified:
                                    break

                                if attempt < max_retries - 1:  # Don't sleep on last attempt
                                    console.print(
                                        f"[dim]Verification attempt {attempt + 1} failed, retrying in {retry_delay} seconds...[/dim]"
                                    )
                                    time.sleep(retry_delay)
                                    retry_delay *= 2  # Exponential backoff

                        if verification_result.overall_verified:
                            console.print(
                                f"[green]✓ Post-rollback verification passed: {verification_result.verified_assignments}/{verification_result.total_assignments} assignments verified[/green]"
                            )
                        else:
                            console.print(
                                f"[yellow]⚠ Post-rollback verification issues: {verification_result.failed_verifications}/{verification_result.total_assignments} verifications failed[/yellow]"
                            )

                            # Add verification warnings to result
                            for warning in verification_result.warnings:
                                console.print(f"[yellow]  Warning: {warning}[/yellow]")

                            for error in verification_result.errors:
                                console.print(f"[red]  Verification Error: {error}[/red]")

                        # Record verification metrics
                        self.performance_tracker.add_operation_metric(
                            rollback_operation_id,
                            "verification_success_rate",
                            (
                                (
                                    verification_result.verified_assignments
                                    / verification_result.total_assignments
                                    * 100
                                )
                                if verification_result.total_assignments > 0
                                else 0
                            ),
                            "percent",
                            {
                                "verified_assignments": verification_result.verified_assignments,
                                "total_assignments": verification_result.total_assignments,
                                "failed_verifications": verification_result.failed_verifications,
                            },
                        )

            except Exception as e:
                console.print(
                    f"[yellow]Warning: Post-rollback verification failed: {str(e)}[/yellow]"
                )

        # For complete failures, return result instead of raising exception
        # This allows tests to verify the error conditions
        if completed_actions == 0 and failed_actions > 0:
            # Don't raise exception, just return the failed result
            pass

        return result

    def _get_principal_type_from_action(self, action: RollbackAction) -> str:
        """Get principal type for AWS API call from rollback action.

        Args:
            action: The rollback action

        Returns:
            Principal type string for AWS API
        """
        return action.principal_type.value

    def _log_rollback_operation(
        self,
        plan: RollbackPlan,
        rollback_operation_id: str,
        completed_actions: int,
        failed_actions: int,
    ) -> None:
        """Log the rollback operation for audit purposes.

        Args:
            plan: The rollback plan that was executed
            rollback_operation_id: The rollback operation ID
            completed_actions: Number of completed actions
            failed_actions: Number of failed actions
        """
        try:
            # Get original operation for context
            original_operation = self.store.get_operation(plan.operation_id)
            if not original_operation:
                return

            # Handle different operation record types
            if hasattr(original_operation, "principal_id"):
                principal_id = original_operation.principal_id
                principal_type = original_operation.principal_type.value
                principal_name = original_operation.principal_name
                permission_set_arn = original_operation.permission_set_arn
                permission_set_name = original_operation.permission_set_name
            elif hasattr(original_operation, "source_entity_id"):
                # For PermissionCloningOperationRecord, determine the correct principal based on operation type
                if original_operation.operation_type == OperationType.COPY_ASSIGNMENTS:
                    # For copy operations, rollback affects the TARGET user (who received the permissions)
                    principal_id = original_operation.target_entity_id
                    principal_type = original_operation.target_entity_type.value
                    principal_name = original_operation.target_entity_name
                else:
                    # For other operations, use source entity info
                    principal_id = original_operation.source_entity_id
                    principal_type = original_operation.source_entity_type.value
                    principal_name = original_operation.source_entity_name
                permission_set_arn = (
                    original_operation.permission_sets_involved[0]
                    if original_operation.permission_sets_involved
                    else ""
                )
                permission_set_name = (
                    permission_set_arn.split("/")[-1] if permission_set_arn else "Unknown"
                )
            else:
                principal_id = "Unknown"
                principal_type = "Unknown"
                principal_name = "Unknown"
                permission_set_arn = "Unknown"
                permission_set_name = "Unknown"

            # Create rollback record
            rollback_record = {
                "rollback_operation_id": rollback_operation_id,
                "original_operation_id": plan.operation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "rollback_type": plan.rollback_type.value,
                "completed_actions": completed_actions,
                "failed_actions": failed_actions,
                "total_actions": len(plan.actions),
                "principal_id": principal_id,
                "principal_type": principal_type,
                "principal_name": principal_name,
                "permission_set_arn": permission_set_arn,
                "permission_set_name": permission_set_name,
                "account_ids": [action.account_id for action in plan.actions],
            }

            # Store rollback record
            self.store.store_rollback_record(rollback_record)

        except Exception as e:
            console.print(f"[yellow]Warning: Could not log rollback operation: {str(e)}[/yellow]")

    def verify_rollback(self, rollback_operation_id: str) -> RollbackVerification:
        """Verify that a rollback operation completed successfully.

        Args:
            rollback_operation_id: The rollback operation ID to verify

        Returns:
            RollbackVerification with verification results
        """
        mismatches = []
        warnings = []

        if not self.identity_center_client:
            return RollbackVerification(
                verified=False,
                mismatches=["AWS client not available for verification"],
                warnings=[],
            )

        try:
            # Get rollback record
            rollback_data = self._get_rollback_record(rollback_operation_id)
            if not rollback_data:
                return RollbackVerification(
                    verified=False,
                    mismatches=[f"Rollback operation {rollback_operation_id} not found"],
                    warnings=[],
                )

            # Get original operation
            original_operation = self.store.get_operation(rollback_data["original_operation_id"])
            if not original_operation:
                return RollbackVerification(
                    verified=False,
                    mismatches=["Original operation not found for verification"],
                    warnings=[],
                )

            # Extract SSO instance ARN
            sso_instance_arn = self._extract_sso_instance_arn(original_operation.permission_set_arn)
            if not sso_instance_arn:
                return RollbackVerification(
                    verified=False,
                    mismatches=["Could not extract SSO instance ARN for verification"],
                    warnings=[],
                )

            # Verify each account assignment
            for account_id in rollback_data["account_ids"]:
                try:
                    # Check current assignment state
                    current_assignments = self.identity_center_client.list_account_assignments(
                        InstanceArn=sso_instance_arn,
                        AccountId=account_id,
                        PermissionSetArn=original_operation.permission_set_arn,
                    )

                    # Look for matching assignment
                    assignment_exists = False
                    for assignment in current_assignments.get("AccountAssignments", []):
                        if (
                            assignment["PrincipalId"] == original_operation.principal_id
                            and assignment["PrincipalType"]
                            == original_operation.principal_type.value
                        ):
                            assignment_exists = True
                            break

                    # Verify expected state based on rollback type
                    rollback_type = RollbackActionType(rollback_data["rollback_type"])
                    if rollback_type == RollbackActionType.REVOKE:
                        # After revoke rollback, assignment should not exist
                        if assignment_exists:
                            mismatches.append(
                                f"Account {account_id}: Assignment still exists after revoke rollback"
                            )
                    else:
                        # After assign rollback, assignment should exist
                        if not assignment_exists:
                            mismatches.append(
                                f"Account {account_id}: Assignment does not exist after assign rollback"
                            )

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    warnings.append(f"Could not verify account {account_id}: {error_code}")
                except Exception as e:
                    warnings.append(f"Could not verify account {account_id}: {str(e)}")

        except Exception as e:
            return RollbackVerification(
                verified=False,
                mismatches=[f"Verification failed: {str(e)}"],
                warnings=[],
            )

        verified = len(mismatches) == 0
        return RollbackVerification(
            verified=verified,
            mismatches=mismatches,
            warnings=warnings,
        )

    def _get_rollback_record(self, rollback_operation_id: str) -> Optional[Dict[str, Any]]:
        """Get rollback record by ID.

        Args:
            rollback_operation_id: The rollback operation ID

        Returns:
            Rollback record dictionary if found, None otherwise
        """
        try:
            rollbacks_data = self.store._read_rollbacks_file()
            for rollback in rollbacks_data.get("rollbacks", []):
                if rollback.get("rollback_operation_id") == rollback_operation_id:
                    return rollback
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read rollback records: {str(e)}[/yellow]")

        return None

    def get_storage_optimization_recommendations(self) -> List[str]:
        """Get storage optimization recommendations.

        Returns:
            List of optimization recommendations
        """
        recommendations = []

        try:
            # Get storage stats
            stats = self.store.get_storage_stats()
            self.storage_monitor.get_storage_summary()

            # Check file sizes
            operations_size_mb = stats["operations_file_size"] / 1024 / 1024
            if operations_size_mb > 50:
                recommendations.append(
                    f"Operations file is large ({operations_size_mb:.1f}MB). "
                    "Consider running cleanup_old_operations() to remove old records."
                )

            # Check compression
            if not stats["compression_enabled"]:
                recommendations.append(
                    "Compression is disabled. Enable compression to reduce storage usage by 60-80%."
                )
            elif stats.get("operations_compression_ratio", 0) > 0.5:
                recommendations.append(
                    f"Poor compression ratio ({stats['operations_compression_ratio']:.2f}). "
                    "Data may not be compressing well due to high entropy."
                )

            # Check operation count
            if stats["total_operations"] > 10000:
                recommendations.append(
                    f"High number of operations ({stats['total_operations']}). "
                    "Consider implementing automatic cleanup policies."
                )

            # Check recent alerts
            recent_alerts = self.storage_monitor.get_recent_alerts(hours=24)
            if recent_alerts:
                critical_alerts = [a for a in recent_alerts if a.severity == "critical"]
                if critical_alerts:
                    recommendations.append(
                        f"Critical storage alerts detected ({len(critical_alerts)}). "
                        "Immediate attention required."
                    )

            # Check index memory usage
            index_memory_mb = stats.get("index_memory_usage", 0) / 1024 / 1024
            if index_memory_mb > 20:
                recommendations.append(
                    f"High index memory usage ({index_memory_mb:.1f}MB). "
                    "Consider reducing the number of stored operations."
                )

        except Exception as e:
            recommendations.append(f"Could not analyze storage: {str(e)}")

        return recommendations

    def optimize_storage(self) -> Dict[str, Any]:
        """Perform storage optimization.

        Returns:
            Dictionary with optimization results
        """
        try:
            # Run storage optimization
            optimization_results = self.store.optimize_storage()

            # Run health check
            alerts = self.storage_monitor.check_storage_health()

            # Get final stats
            final_stats = self.store.get_storage_stats()

            return {
                "optimization_results": optimization_results,
                "health_alerts": len(alerts),
                "final_stats": final_stats,
                "recommendations": self.get_storage_optimization_recommendations(),
            }

        except Exception as e:
            return {
                "error": f"Storage optimization failed: {str(e)}",
                "recommendations": ["Manual intervention may be required"],
            }
