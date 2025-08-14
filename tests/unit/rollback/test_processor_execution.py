"""Tests for RollbackProcessor execution engine."""

from datetime import datetime, timezone
from unittest.mock import Mock, call, patch

from botocore.exceptions import ClientError

from src.awsideman.rollback.models import (
    AssignmentState,
    PrincipalType,
    RollbackAction,
    RollbackActionType,
    RollbackPlan,
)
from src.awsideman.rollback.processor import RollbackProcessor


class TestRollbackProcessorExecution:
    """Test cases for rollback execution engine."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_store = Mock()
        self.mock_aws_client_manager = Mock()
        self.mock_identity_center_client = Mock()

        # Configure AWS client manager
        self.mock_aws_client_manager.get_identity_center_client.return_value = (
            self.mock_identity_center_client
        )

        self.processor = RollbackProcessor(
            storage_directory="/tmp/test", aws_client_manager=self.mock_aws_client_manager
        )
        self.processor.store = self.mock_store

    def test_execute_rollback_dry_run(self):
        """Test rollback execution in dry run mode."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Act
        result = self.processor.execute_rollback(plan, dry_run=True)

        # Assert
        assert result.rollback_operation_id == "dry-run"
        assert result.success is True
        assert result.completed_actions == 1
        assert result.failed_actions == 0
        assert len(result.errors) == 0
        assert result.duration_ms == 0

        # Verify no AWS API calls were made
        self.mock_identity_center_client.delete_account_assignment.assert_not_called()

    def test_execute_rollback_without_aws_client(self):
        """Test rollback execution when AWS client is not available."""
        # Arrange
        processor = RollbackProcessor(storage_directory="/tmp/test")
        processor.store = self.mock_store

        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Act
        result = processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is False
        assert result.completed_actions == 0
        assert result.failed_actions == 1
        assert "AWS client not available for rollback execution" in result.errors

    def test_execute_rollback_revoke_success(self):
        """Test successful rollback execution for revoke actions."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                ),
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789013",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                ),
            ],
            estimated_duration=10,
            warnings=[],
        )

        # Mock successful AWS API calls
        self.mock_identity_center_client.delete_account_assignment.return_value = {}

        # Act
        with patch("src.awsideman.rollback.processor.uuid.uuid4", return_value="rollback-123"):
            result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.rollback_operation_id == "rollback-123"
        assert result.success is True
        assert result.completed_actions == 2
        assert result.failed_actions == 0
        assert len(result.errors) == 0
        assert result.duration_ms >= 0  # Duration should be non-negative

        # Verify AWS API calls
        expected_calls = [
            call(
                InstanceArn="arn:aws:sso:::instance/ssoins-123",
                TargetId="123456789012",
                TargetType="AWS_ACCOUNT",
                PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                PrincipalType="USER",
                PrincipalId="user-123",
            ),
            call(
                InstanceArn="arn:aws:sso:::instance/ssoins-123",
                TargetId="123456789013",
                TargetType="AWS_ACCOUNT",
                PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                PrincipalType="USER",
                PrincipalId="user-123",
            ),
        ]
        self.mock_identity_center_client.delete_account_assignment.assert_has_calls(expected_calls)

        # Verify operation was marked as rolled back
        self.mock_store.mark_operation_rolled_back.assert_called_once_with(
            "test-op-id", "rollback-123"
        )

    def test_execute_rollback_assign_success(self):
        """Test successful rollback execution for assign actions."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.ASSIGN,
            actions=[
                RollbackAction(
                    principal_id="group-456",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                    account_id="123456789012",
                    action_type=RollbackActionType.ASSIGN,
                    current_state=AssignmentState.NOT_ASSIGNED,
                    principal_type=PrincipalType.GROUP,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Mock successful AWS API calls
        self.mock_identity_center_client.create_account_assignment.return_value = {}

        # Act
        with patch("src.awsideman.rollback.processor.uuid.uuid4", return_value="rollback-456"):
            result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is True
        assert result.completed_actions == 1
        assert result.failed_actions == 0

        # Verify AWS API call
        self.mock_identity_center_client.create_account_assignment.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/ssoins-123",
            TargetId="123456789012",
            TargetType="AWS_ACCOUNT",
            PermissionSetArn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            PrincipalType="GROUP",
            PrincipalId="group-456",
        )

    def test_execute_rollback_conflict_exception_assign(self):
        """Test rollback execution with ConflictException for assign action."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.ASSIGN,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.ASSIGN,
                    current_state=AssignmentState.NOT_ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Mock ConflictException (assignment already exists)
        error_response = {
            "Error": {"Code": "ConflictException", "Message": "Assignment already exists"}
        }
        self.mock_identity_center_client.create_account_assignment.side_effect = ClientError(
            error_response, "CreateAccountAssignment"
        )

        # Act
        result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is True  # ConflictException for assign is treated as success
        assert result.completed_actions == 1
        assert result.failed_actions == 0
        assert len(result.errors) == 0

    def test_execute_rollback_conflict_exception_revoke(self):
        """Test rollback execution with ConflictException for revoke action."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Mock ConflictException (assignment doesn't exist)
        error_response = {"Error": {"Code": "ConflictException", "Message": "Assignment not found"}}
        self.mock_identity_center_client.delete_account_assignment.side_effect = ClientError(
            error_response, "DeleteAccountAssignment"
        )

        # Act
        result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is True  # ConflictException for revoke is treated as success
        assert result.completed_actions == 1
        assert result.failed_actions == 0
        assert len(result.errors) == 0

    def test_execute_rollback_access_denied_error(self):
        """Test rollback execution with AccessDenied error."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Mock AccessDenied error
        error_response = {"Error": {"Code": "AccessDenied", "Message": "Insufficient permissions"}}
        self.mock_identity_center_client.delete_account_assignment.side_effect = ClientError(
            error_response, "DeleteAccountAssignment"
        )

        # Act
        result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is False
        assert result.completed_actions == 0
        assert result.failed_actions == 1
        assert len(result.errors) == 1
        assert (
            "Account 123456789012: An error occurred (AccessDenied) when calling the DeleteAccountAssignment operation: Insufficient permissions"
            in result.errors[0]
        )

    def test_execute_rollback_mixed_success_failure(self):
        """Test rollback execution with mixed success and failure results."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                ),
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789013",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                ),
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789014",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                ),
            ],
            estimated_duration=15,
            warnings=[],
        )

        # Mock mixed results
        def mock_delete_assignment(**kwargs):
            if kwargs["TargetId"] == "123456789013":
                # Fail for second account
                error_response = {
                    "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}
                }
                raise ClientError(error_response, "DeleteAccountAssignment")
            return {}

        self.mock_identity_center_client.delete_account_assignment.side_effect = (
            mock_delete_assignment
        )

        # Act
        result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is False  # Not all actions succeeded
        assert result.completed_actions == 2
        assert result.failed_actions == 1
        assert len(result.errors) == 1
        assert (
            "Account 123456789013: An error occurred (ThrottlingException) when calling the DeleteAccountAssignment operation: Rate exceeded"
            in result.errors[0]
        )

        # Verify rollback operation was still logged (partial success)
        self.mock_store.store_rollback_record.assert_called_once()

    def test_execute_rollback_unexpected_error(self):
        """Test rollback execution with unexpected error."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Mock unexpected error
        self.mock_identity_center_client.delete_account_assignment.side_effect = Exception(
            "Unexpected error"
        )

        # Act
        result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is False
        assert result.completed_actions == 0
        assert result.failed_actions == 1
        assert len(result.errors) == 1
        assert "Account 123456789012: Unexpected error" in result.errors[0]

    def test_execute_rollback_batch_processing(self):
        """Test rollback execution with batch processing."""
        # Arrange
        # Create plan with 25 actions to test batching
        actions = []
        for i in range(25):
            actions.append(
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id=f"12345678901{i:02d}",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            )

        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=actions,
            estimated_duration=75,
            warnings=[],
        )

        # Mock successful AWS API calls
        self.mock_identity_center_client.delete_account_assignment.return_value = {}

        # Act
        result = self.processor.execute_rollback(plan, dry_run=False, batch_size=10)

        # Assert
        assert result.success is True
        assert result.completed_actions == 25
        assert result.failed_actions == 0

        # Verify all AWS API calls were made
        assert self.mock_identity_center_client.delete_account_assignment.call_count == 25

    def test_execute_rollback_invalid_permission_set_arn(self):
        """Test rollback execution with invalid permission set ARN."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="invalid-arn",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Act
        result = self.processor.execute_rollback(plan, dry_run=False)

        # Assert
        assert result.success is False
        assert result.completed_actions == 0
        assert result.failed_actions == 1
        assert "Could not extract SSO instance ARN" in result.errors

    def test_log_rollback_operation(self):
        """Test rollback operation logging."""
        # Arrange
        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=[
                RollbackAction(
                    principal_id="user-123",
                    permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                    account_id="123456789012",
                    action_type=RollbackActionType.REVOKE,
                    current_state=AssignmentState.ASSIGNED,
                    principal_type=PrincipalType.USER,
                )
            ],
            estimated_duration=5,
            warnings=[],
        )

        # Mock original operation
        from src.awsideman.rollback.models import OperationRecord, OperationType

        original_operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["TestAccount"],
            results=[],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Act
        self.processor._log_rollback_operation(plan, "rollback-123", 1, 0)

        # Assert
        self.mock_store.store_rollback_record.assert_called_once()
        call_args = self.mock_store.store_rollback_record.call_args[0][0]

        assert call_args["rollback_operation_id"] == "rollback-123"
        assert call_args["original_operation_id"] == "test-op-id"
        assert call_args["rollback_type"] == "revoke"
        assert call_args["completed_actions"] == 1
        assert call_args["failed_actions"] == 0
        assert call_args["total_actions"] == 1
        assert call_args["principal_id"] == "user-123"
        assert call_args["principal_type"] == "USER"
        assert call_args["account_ids"] == ["123456789012"]
