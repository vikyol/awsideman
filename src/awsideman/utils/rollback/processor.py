"""Rollback processor for handling rollback operations."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console

from ...aws_clients.manager import AWSClientManager
from ..config import Config
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
from .storage import OperationStore

console = Console()


class RollbackProcessor:
    """Processor for handling rollback operations."""

    def __init__(
        self,
        storage_directory: Optional[str] = None,
        aws_client_manager: Optional[AWSClientManager] = None,
        config: Optional[Config] = None,
    ):
        """Initialize the rollback processor.

        Args:
            storage_directory: Directory where operation records are stored.
            aws_client_manager: AWS client manager for API calls.
            config: Configuration object.
        """
        self.store = OperationStore(storage_directory)
        self.aws_client_manager = aws_client_manager
        self.config = config or Config()

        # Initialize AWS clients if manager provided
        if self.aws_client_manager:
            self.identity_center_client = self.aws_client_manager.get_identity_center_client()
            self.identity_store_client = self.aws_client_manager.get_identity_store_client()
        else:
            self.identity_center_client = None
            self.identity_store_client = None

    def validate_rollback(self, operation_id: str) -> RollbackValidation:
        """Validate if a rollback operation is feasible.

        Args:
            operation_id: The operation ID to validate for rollback

        Returns:
            RollbackValidation with validation results
        """
        errors = []
        warnings = []

        # Check if operation exists
        operation = self.store.get_operation(operation_id)
        if not operation:
            errors.append(f"Operation {operation_id} not found")
            return RollbackValidation(valid=False, errors=errors)

        # Check if already rolled back
        if operation.rolled_back:
            errors.append(f"Operation {operation_id} has already been rolled back")
            if operation.rollback_operation_id:
                errors.append(f"Rollback operation ID: {operation.rollback_operation_id}")

        # Check if all results were successful
        failed_results = [r for r in operation.results if not r.success]
        successful_results = [r for r in operation.results if r.success]

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
                    self.identity_center_client.list_permission_sets(
                        InstanceArn=sso_instance_arn, MaxResults=1
                    )
                else:
                    warnings.append("Could not extract SSO instance ARN from permission set ARN")
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code in ["AccessDenied", "UnauthorizedOperation"]:
                    errors.append(f"Insufficient permissions for rollback operations: {error_code}")
                else:
                    warnings.append(f"Could not verify AWS permissions: {error_code}")
            except Exception as e:
                warnings.append(f"Could not verify AWS permissions: {str(e)}")

        # Check for state conflicts if AWS client is available
        if self.identity_center_client and successful_results:
            state_conflicts = self._check_state_conflicts(operation)
            if state_conflicts:
                warnings.extend(state_conflicts)

        is_valid = len(errors) == 0
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
            for result in operation.results:
                if not result.success:
                    continue

                try:
                    # Check if assignment currently exists
                    current_assignments = self.identity_center_client.list_account_assignments(
                        InstanceArn=sso_instance_arn,
                        AccountId=result.account_id,
                        PermissionSetArn=operation.permission_set_arn,
                    )

                    # Look for matching assignment
                    assignment_exists = False
                    for assignment in current_assignments.get("AccountAssignments", []):
                        if (
                            assignment["PrincipalId"] == operation.principal_id
                            and assignment["PrincipalType"] == operation.principal_type.value
                        ):
                            assignment_exists = True
                            break

                    # Check for conflicts based on operation type
                    if operation.operation_type == OperationType.ASSIGN:
                        # If original was assign, rollback is revoke
                        # Assignment should exist for rollback to work
                        if not assignment_exists:
                            conflicts.append(
                                f"Assignment no longer exists for account {result.account_id} "
                                f"(may have been manually revoked)"
                            )
                    else:
                        # If original was revoke, rollback is assign
                        # Assignment should not exist for rollback to work
                        if assignment_exists:
                            conflicts.append(
                                f"Assignment already exists for account {result.account_id} "
                                f"(may have been manually re-assigned)"
                            )

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    conflicts.append(
                        f"Could not verify state for account {result.account_id}: {error_code}"
                    )
                except Exception as e:
                    conflicts.append(
                        f"Could not verify state for account {result.account_id}: {str(e)}"
                    )

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
        if operation.operation_type == OperationType.ASSIGN:
            rollback_type = RollbackActionType.REVOKE
        else:
            rollback_type = RollbackActionType.ASSIGN

        # Generate rollback actions for successful results only
        actions = []
        warnings = []

        for result in operation.results:
            if result.success:
                # Determine current state if AWS client is available
                current_state = self._get_current_assignment_state(operation, result.account_id)

                action = RollbackAction(
                    principal_id=operation.principal_id,
                    permission_set_arn=operation.permission_set_arn,
                    account_id=result.account_id,
                    action_type=rollback_type,
                    current_state=current_state,
                    principal_type=operation.principal_type,
                )
                actions.append(action)
            else:
                warnings.append(
                    f"Skipping rollback for account {result.account_id} due to original failure: {result.error}"
                )

        # Add warnings for state mismatches
        for action in actions:
            if (
                rollback_type == RollbackActionType.REVOKE
                and action.current_state == AssignmentState.NOT_ASSIGNED
            ):
                warnings.append(
                    f"Account {action.account_id}: Assignment already revoked, rollback may be unnecessary"
                )
            elif (
                rollback_type == RollbackActionType.ASSIGN
                and action.current_state == AssignmentState.ASSIGNED
            ):
                warnings.append(
                    f"Account {action.account_id}: Assignment already exists, rollback may conflict"
                )

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
            sso_instance_arn = self._extract_sso_instance_arn(operation.permission_set_arn)
            if not sso_instance_arn:
                return AssignmentState.UNKNOWN

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
        self, plan: RollbackPlan, dry_run: bool = False, batch_size: int = 10
    ) -> RollbackResult:
        """Execute a rollback plan.

        Args:
            plan: The rollback plan to execute
            dry_run: If True, simulate the rollback without making changes
            batch_size: Number of actions to process in parallel

        Returns:
            RollbackResult with execution results
        """
        rollback_operation_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)

        if dry_run:
            # Simulate successful execution for dry run
            return RollbackResult(
                rollback_operation_id="dry-run",
                success=True,
                completed_actions=len(plan.actions),
                failed_actions=0,
                errors=[],
                duration_ms=0,
            )

        if not self.identity_center_client:
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

        # Get SSO instance ARN
        sso_instance_arn = None
        if plan.actions:
            sso_instance_arn = self._extract_sso_instance_arn(plan.actions[0].permission_set_arn)
            if not sso_instance_arn:
                return RollbackResult(
                    rollback_operation_id=rollback_operation_id,
                    success=False,
                    completed_actions=0,
                    failed_actions=len(plan.actions),
                    errors=["Could not extract SSO instance ARN"],
                    duration_ms=0,
                )

        # Process actions in batches
        for i in range(0, len(plan.actions), batch_size):
            batch = plan.actions[i : i + batch_size]

            for action in batch:
                try:
                    if action.action_type == RollbackActionType.ASSIGN:
                        # Create assignment
                        self.identity_center_client.create_account_assignment(
                            InstanceArn=sso_instance_arn,
                            TargetId=action.account_id,
                            TargetType="AWS_ACCOUNT",
                            PermissionSetArn=action.permission_set_arn,
                            PrincipalType=self._get_principal_type_from_action(action),
                            PrincipalId=action.principal_id,
                        )
                    else:
                        # Delete assignment
                        self.identity_center_client.delete_account_assignment(
                            InstanceArn=sso_instance_arn,
                            TargetId=action.account_id,
                            TargetType="AWS_ACCOUNT",
                            PermissionSetArn=action.permission_set_arn,
                            PrincipalType=self._get_principal_type_from_action(action),
                            PrincipalId=action.principal_id,
                        )

                    completed_actions += 1

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    error_message = e.response.get("Error", {}).get("Message", str(e))

                    # Handle specific error cases
                    if error_code == "ConflictException":
                        if action.action_type == RollbackActionType.ASSIGN:
                            # Assignment already exists - this might be OK
                            console.print(
                                f"[yellow]Warning: Assignment already exists for account {action.account_id}[/yellow]"
                            )
                            completed_actions += 1  # Count as success
                        else:
                            # Assignment doesn't exist - this might be OK
                            console.print(
                                f"[yellow]Warning: Assignment already revoked for account {action.account_id}[/yellow]"
                            )
                            completed_actions += 1  # Count as success
                    else:
                        failed_actions += 1
                        error_msg = f"Account {action.account_id}: {error_code} - {error_message}"
                        errors.append(error_msg)
                        console.print(f"[red]Error: {error_msg}[/red]")

                except Exception as e:
                    failed_actions += 1
                    error_msg = f"Account {action.account_id}: Unexpected error - {str(e)}"
                    errors.append(error_msg)
                    console.print(f"[red]Error: {error_msg}[/red]")

        # Calculate duration
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Log the rollback operation
        if completed_actions > 0:
            self._log_rollback_operation(
                plan, rollback_operation_id, completed_actions, failed_actions
            )

            # Mark original operation as rolled back if all actions succeeded
            if failed_actions == 0:
                self.store.mark_operation_rolled_back(plan.operation_id, rollback_operation_id)

        success = failed_actions == 0 and completed_actions > 0

        return RollbackResult(
            rollback_operation_id=rollback_operation_id,
            success=success,
            completed_actions=completed_actions,
            failed_actions=failed_actions,
            errors=errors,
            duration_ms=duration_ms,
        )

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

            # Create rollback record
            rollback_record = {
                "rollback_operation_id": rollback_operation_id,
                "original_operation_id": plan.operation_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "rollback_type": plan.rollback_type.value,
                "completed_actions": completed_actions,
                "failed_actions": failed_actions,
                "total_actions": len(plan.actions),
                "principal_id": original_operation.principal_id,
                "principal_type": original_operation.principal_type.value,
                "principal_name": original_operation.principal_name,
                "permission_set_arn": original_operation.permission_set_arn,
                "permission_set_name": original_operation.permission_set_name,
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
