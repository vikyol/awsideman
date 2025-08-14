"""Tests for RollbackProcessor validation logic."""

from datetime import datetime, timezone
from unittest.mock import Mock

from botocore.exceptions import ClientError

from src.awsideman.rollback.models import (
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
)
from src.awsideman.rollback.processor import RollbackProcessor


class TestRollbackProcessorValidation:
    """Test cases for rollback validation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_store = Mock()
        self.mock_aws_client_manager = Mock()
        self.mock_identity_center_client = Mock()
        self.mock_identity_store_client = Mock()

        # Configure AWS client manager
        self.mock_aws_client_manager.get_identity_center_client.return_value = (
            self.mock_identity_center_client
        )
        self.mock_aws_client_manager.get_identity_store_client.return_value = (
            self.mock_identity_store_client
        )

        self.processor = RollbackProcessor(
            storage_directory="/tmp/test", aws_client_manager=self.mock_aws_client_manager
        )
        self.processor.store = self.mock_store
        # Also set the state verifier's store to use the mock
        self.processor.state_verifier.store = self.mock_store

    def test_validate_rollback_operation_not_found(self):
        """Test validation when operation doesn't exist."""
        # Arrange
        self.mock_store.get_operation.return_value = None

        # Act
        result = self.processor.validate_rollback("nonexistent-id")

        # Assert
        assert not result.valid
        assert len(result.errors) == 1
        assert "Operation nonexistent-id not found" in result.errors[0]
        assert len(result.warnings) == 0

    def test_validate_rollback_already_rolled_back(self):
        """Test validation when operation is already rolled back."""
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
            rolled_back=True,
            rollback_operation_id="rollback-123",
        )
        self.mock_store.get_operation.return_value = operation

        # Act
        result = self.processor.validate_rollback("test-op-id")

        # Assert
        assert not result.valid
        assert len(result.errors) == 2
        assert "Operation test-op-id has already been rolled back" in result.errors[0]
        assert "Rollback operation ID: rollback-123" in result.errors[1]

    def test_validate_rollback_no_successful_results(self):
        """Test validation when operation has no successful results."""
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
            results=[OperationResult(account_id="123456789012", success=False, error="Test error")],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Act
        result = self.processor.validate_rollback("test-op-id")

        # Assert
        assert not result.valid
        assert "Operation has no successful results to roll back" in result.errors
        assert "Operation had 1 failed results that cannot be rolled back" in result.warnings[0]

    def test_validate_rollback_mixed_results(self):
        """Test validation when operation has mixed successful and failed results."""
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
                OperationResult(account_id="123456789013", success=False, error="Test error"),
            ],
            rolled_back=False,
        )
        self.mock_store.get_operation.return_value = operation

        # Act
        result = self.processor.validate_rollback("test-op-id")

        # Assert
        assert result.valid  # Should be valid because there are successful results
        assert len(result.errors) == 0
        assert "Operation had 1 failed results that cannot be rolled back" in result.warnings[0]

    def test_validate_rollback_aws_permissions_check_success(self):
        """Test validation with successful AWS permissions check."""
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
        self.mock_store.get_operation.return_value = operation

        # Mock successful AWS API call
        self.mock_identity_center_client.list_permission_sets.return_value = {"PermissionSets": []}

        # Act
        result = self.processor.validate_rollback("test-op-id")

        # Assert
        assert result.valid
        assert len(result.errors) == 0
        self.mock_identity_center_client.list_permission_sets.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/ssoins-123", MaxResults=1
        )

    def test_validate_rollback_aws_permissions_access_denied(self):
        """Test validation when AWS permissions are insufficient."""
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
        self.mock_store.get_operation.return_value = operation

        # Mock AWS access denied error
        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}
        self.mock_identity_center_client.list_permission_sets.side_effect = ClientError(
            error_response, "ListPermissionSets"
        )

        # Act
        result = self.processor.validate_rollback("test-op-id")

        # Assert
        assert not result.valid
        assert "Insufficient permissions for rollback operations: AccessDenied" in result.errors

    def test_validate_rollback_state_conflicts_assign_operation(self):
        """Test validation with state conflicts for assign operation."""
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
        self.mock_store.get_operation.return_value = operation

        # Mock AWS API calls
        self.mock_identity_center_client.list_permission_sets.return_value = {"PermissionSets": []}
        # Mock no existing assignment (conflict for assign operation rollback)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": []
        }

        # Act
        result = self.processor.validate_rollback("test-op-id")

        # Assert
        assert result.valid  # Should still be valid, but with warnings
        assert len(result.errors) == 0
        assert any(
            "Assignment no longer exists for account 123456789012" in warning
            for warning in result.warnings
        )

    def test_validate_rollback_state_conflicts_revoke_operation(self):
        """Test validation with state conflicts for revoke operation."""
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

        # Mock AWS API calls
        self.mock_identity_center_client.list_permission_sets.return_value = {"PermissionSets": []}
        # Mock existing assignment (conflict for revoke operation rollback)
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
        result = self.processor.validate_rollback("test-op-id")

        # Assert
        assert result.valid  # Should still be valid, but with warnings
        assert len(result.errors) == 0
        assert any(
            "Assignment already exists for account 123456789012" in warning
            for warning in result.warnings
        )

    def test_extract_sso_instance_arn_valid(self):
        """Test SSO instance ARN extraction from valid permission set ARN."""
        # Arrange
        permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-abcdef1234567890"
        )

        # Act
        result = self.processor._extract_sso_instance_arn(permission_set_arn)

        # Assert
        assert result == "arn:aws:sso:::instance/ssoins-1234567890abcdef"

    def test_extract_sso_instance_arn_invalid(self):
        """Test SSO instance ARN extraction from invalid permission set ARN."""
        # Arrange
        invalid_arn = "invalid-arn"

        # Act
        result = self.processor._extract_sso_instance_arn(invalid_arn)

        # Assert
        assert result is None

    def test_validate_rollback_without_aws_client(self):
        """Test validation when AWS client is not available."""
        # Arrange
        processor = RollbackProcessor(storage_directory="/tmp/test")
        processor.store = self.mock_store
        # Also set the state verifier's store to use the mock
        processor.state_verifier.store = self.mock_store

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
        result = processor.validate_rollback("test-op-id")

        # Assert
        assert result.valid  # Should be valid without AWS checks
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_check_state_conflicts_api_error(self):
        """Test state conflict checking when AWS API returns error."""
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
        conflicts = self.processor._check_state_conflicts(operation)

        # Assert
        assert len(conflicts) == 1
        assert (
            "Could not verify state for account 123456789012: ThrottlingException" in conflicts[0]
        )
