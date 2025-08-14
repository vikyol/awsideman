"""Tests for RollbackProcessor plan generation logic."""

from datetime import datetime, timezone
from unittest.mock import Mock

from botocore.exceptions import ClientError

from src.awsideman.rollback.models import (
    AssignmentState,
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
    RollbackActionType,
)
from src.awsideman.rollback.processor import RollbackProcessor


class TestRollbackProcessorPlanGeneration:
    """Test cases for rollback plan generation logic."""

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

    def test_generate_plan_operation_not_found(self):
        """Test plan generation when operation doesn't exist."""
        # Arrange
        self.mock_store.get_operation.return_value = None

        # Act
        result = self.processor.generate_plan("nonexistent-id")

        # Assert
        assert result is None

    def test_generate_plan_assign_operation(self):
        """Test plan generation for assign operation (rollback is revoke)."""
        # Arrange
        operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012", "123456789013"],
            account_names=["TestAccount1", "TestAccount2"],
            results=[
                OperationResult(account_id="123456789012", success=True),
                OperationResult(account_id="123456789013", success=True),
            ],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Mock current assignment state
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                }
            ]
        }

        # Act
        result = self.processor.generate_plan("test-op-id")

        # Assert
        assert result is not None
        assert result.operation_id == "test-op-id"
        assert result.rollback_type == RollbackActionType.REVOKE
        assert len(result.actions) == 2

        # Check first action
        action1 = result.actions[0]
        assert action1.principal_id == "user-123"
        assert action1.permission_set_arn == "arn:aws:sso:::permissionSet/ssoins-123/ps-123"
        assert action1.account_id == "123456789012"
        assert action1.action_type == RollbackActionType.REVOKE
        assert action1.current_state == AssignmentState.ASSIGNED
        assert action1.principal_type == PrincipalType.USER

        # Check second action
        action2 = result.actions[1]
        assert action2.account_id == "123456789013"
        assert action2.action_type == RollbackActionType.REVOKE

        # Check estimated duration
        assert result.estimated_duration > 0
        assert len(result.warnings) == 0

    def test_generate_plan_revoke_operation(self):
        """Test plan generation for revoke operation (rollback is assign)."""
        # Arrange
        operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.REVOKE,
            principal_id="group-456",
            principal_type=PrincipalType.GROUP,
            principal_name="test.group",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["TestAccount"],
            results=[OperationResult(account_id="123456789012", success=True)],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Mock no current assignment (assignment was revoked)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": []
        }

        # Act
        result = self.processor.generate_plan("test-op-id")

        # Assert
        assert result is not None
        assert result.operation_id == "test-op-id"
        assert result.rollback_type == RollbackActionType.ASSIGN
        assert len(result.actions) == 1

        action = result.actions[0]
        assert action.principal_id == "group-456"
        assert action.principal_type == PrincipalType.GROUP
        assert action.action_type == RollbackActionType.ASSIGN
        assert action.current_state == AssignmentState.NOT_ASSIGNED

    def test_generate_plan_mixed_results(self):
        """Test plan generation with mixed successful and failed results."""
        # Arrange
        operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012", "123456789013", "123456789014"],
            account_names=["TestAccount1", "TestAccount2", "TestAccount3"],
            results=[
                OperationResult(account_id="123456789012", success=True),
                OperationResult(account_id="123456789013", success=False, error="Access denied"),
                OperationResult(account_id="123456789014", success=True),
            ],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Mock current assignment state
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                }
            ]
        }

        # Act
        result = self.processor.generate_plan("test-op-id")

        # Assert
        assert result is not None
        assert len(result.actions) == 2  # Only successful results
        assert len(result.warnings) == 1
        assert (
            "Skipping rollback for account 123456789013 due to original failure: Access denied"
            in result.warnings[0]
        )

        # Check that only successful accounts are included
        account_ids = [action.account_id for action in result.actions]
        assert "123456789012" in account_ids
        assert "123456789014" in account_ids
        assert "123456789013" not in account_ids

    def test_generate_plan_state_mismatch_warnings(self):
        """Test plan generation with state mismatch warnings."""
        # Arrange
        operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012", "123456789013"],
            account_names=["TestAccount1", "TestAccount2"],
            results=[
                OperationResult(account_id="123456789012", success=True),
                OperationResult(account_id="123456789013", success=True),
            ],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Mock mixed current states - one assigned, one not assigned
        def mock_list_assignments(InstanceArn, AccountId, PermissionSetArn):
            if AccountId == "123456789012":
                # Assignment exists
                return {
                    "AccountAssignments": [
                        {
                            "PrincipalId": "user-123",
                            "PrincipalType": "USER",
                            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                        }
                    ]
                }
            else:
                # Assignment doesn't exist (already revoked)
                return {"AccountAssignments": []}

        self.mock_identity_center_client.list_account_assignments.side_effect = (
            mock_list_assignments
        )

        # Act
        result = self.processor.generate_plan("test-op-id")

        # Assert
        assert result is not None
        assert len(result.actions) == 2
        assert len(result.warnings) == 1
        assert (
            "Account 123456789013: Assignment already revoked, rollback may be unnecessary"
            in result.warnings[0]
        )

        # Check states
        action1 = next(a for a in result.actions if a.account_id == "123456789012")
        action2 = next(a for a in result.actions if a.account_id == "123456789013")
        assert action1.current_state == AssignmentState.ASSIGNED
        assert action2.current_state == AssignmentState.NOT_ASSIGNED

    def test_generate_plan_revoke_with_existing_assignment_warning(self):
        """Test plan generation for revoke operation with existing assignment warning."""
        # Arrange
        operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.REVOKE,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["TestAccount"],
            results=[OperationResult(account_id="123456789012", success=True)],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Mock existing assignment (conflict for revoke rollback)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                }
            ]
        }

        # Act
        result = self.processor.generate_plan("test-op-id")

        # Assert
        assert result is not None
        assert result.rollback_type == RollbackActionType.ASSIGN
        assert len(result.actions) == 1
        assert len(result.warnings) == 1
        assert (
            "Account 123456789012: Assignment already exists, rollback may conflict"
            in result.warnings[0]
        )

        action = result.actions[0]
        assert action.current_state == AssignmentState.ASSIGNED

    def test_generate_plan_large_batch_duration_estimate(self):
        """Test plan generation with large batch duration estimation."""
        # Arrange
        # Create operation with many accounts
        account_ids = [f"12345678901{i}" for i in range(15)]  # 15 accounts
        account_names = [f"TestAccount{i}" for i in range(15)]
        results = [OperationResult(account_id=acc_id, success=True) for acc_id in account_ids]

        operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=account_ids,
            account_names=account_names,
            results=results,
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Mock current assignment state
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
                }
            ]
        }

        # Act
        result = self.processor.generate_plan("test-op-id")

        # Assert
        assert result is not None
        assert len(result.actions) == 15
        # Large batch should have complexity factor applied
        expected_duration = int(15 * 3 * 1.2)  # 15 actions * 3 seconds * 1.2 complexity factor
        assert result.estimated_duration == expected_duration

    def test_generate_plan_without_aws_client(self):
        """Test plan generation when AWS client is not available."""
        # Arrange
        processor = RollbackProcessor(storage_directory="/tmp/test")
        processor.store = self.mock_store

        operation = OperationRecord(
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
            results=[OperationResult(account_id="123456789012", success=True)],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Act
        result = processor.generate_plan("test-op-id")

        # Assert
        assert result is not None
        assert len(result.actions) == 1
        action = result.actions[0]
        assert action.current_state == AssignmentState.UNKNOWN  # Can't determine without AWS client

    def test_get_current_assignment_state_api_error(self):
        """Test current assignment state retrieval with AWS API error."""
        # Arrange
        operation = OperationRecord(
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
            results=[OperationResult(account_id="123456789012", success=True)],
            rolled_back=False,
        )

        # Mock AWS API error
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        self.mock_identity_center_client.list_account_assignments.side_effect = ClientError(
            error_response, "ListAccountAssignments"
        )

        # Act
        state = self.processor._get_current_assignment_state(operation, "123456789012")

        # Assert
        assert state == AssignmentState.UNKNOWN

    def test_get_current_assignment_state_invalid_arn(self):
        """Test current assignment state retrieval with invalid permission set ARN."""
        # Arrange
        operation = OperationRecord(
            operation_id="test-op-id",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="invalid-arn",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["TestAccount"],
            results=[OperationResult(account_id="123456789012", success=True)],
            rolled_back=False,
        )

        # Act
        state = self.processor._get_current_assignment_state(operation, "123456789012")

        # Assert
        assert state == AssignmentState.UNKNOWN
