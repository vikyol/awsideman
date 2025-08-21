"""Tests for RollbackProcessor execution engine - Ultra Simplified Version."""

from unittest.mock import Mock

from src.awsideman.rollback.models import (
    AssignmentState,
    PrincipalType,
    RollbackAction,
    RollbackActionType,
    RollbackPlan,
)
from src.awsideman.rollback.processor import RollbackProcessor


class TestRollbackProcessorExecution:
    """Ultra simplified test cases for rollback execution engine."""

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
        assert "AWS client not available" in result.errors[0]

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
        assert len(result.errors) == 1
        assert "could not extract sso instance arn" in result.errors[0].lower()

    def test_rollback_plan_validation(self):
        """Test that rollback plans are properly validated."""
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

        # Act & Assert - Just verify the plan structure is correct
        assert plan.operation_id == "test-op-id"
        assert plan.rollback_type == RollbackActionType.REVOKE
        assert len(plan.actions) == 1
        assert plan.actions[0].principal_id == "user-123"
        assert plan.actions[0].account_id == "123456789012"

    def test_rollback_action_creation(self):
        """Test rollback action creation and properties."""
        # Arrange
        action = RollbackAction(
            principal_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            account_id="123456789012",
            action_type=RollbackActionType.REVOKE,
            current_state=AssignmentState.ASSIGNED,
            principal_type=PrincipalType.USER,
        )

        # Assert
        assert action.principal_id == "user-123"
        assert action.permission_set_arn == "arn:aws:sso:::permissionSet/ssoins-123/ps-123"
        assert action.account_id == "123456789012"
        assert action.action_type == RollbackActionType.REVOKE
        assert action.current_state == AssignmentState.ASSIGNED
        assert action.principal_type == PrincipalType.USER

    def test_rollback_plan_creation(self):
        """Test rollback plan creation and properties."""
        # Arrange
        actions = [
            RollbackAction(
                principal_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                account_id="123456789012",
                action_type=RollbackActionType.REVOKE,
                current_state=AssignmentState.ASSIGNED,
                principal_type=PrincipalType.USER,
            )
        ]

        plan = RollbackPlan(
            operation_id="test-op-id",
            rollback_type=RollbackActionType.REVOKE,
            actions=actions,
            estimated_duration=5,
            warnings=["Test warning"],
        )

        # Assert
        assert plan.operation_id == "test-op-id"
        assert plan.rollback_type == RollbackActionType.REVOKE
        assert len(plan.actions) == 1
        assert plan.estimated_duration == 5
        assert len(plan.warnings) == 1
        assert "Test warning" in plan.warnings[0]

    def test_processor_initialization(self):
        """Test that the processor initializes correctly."""
        # Arrange & Act
        processor = RollbackProcessor(storage_directory="/tmp/test")

        # Assert
        assert processor.store is not None
        assert processor.aws_client_manager is None

        # Test with AWS client manager
        processor_with_aws = RollbackProcessor(
            storage_directory="/tmp/test", aws_client_manager=self.mock_aws_client_manager
        )
        assert processor_with_aws.aws_client_manager == self.mock_aws_client_manager
