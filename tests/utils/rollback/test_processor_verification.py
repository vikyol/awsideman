"""Tests for RollbackProcessor verification logic."""

from datetime import datetime, timezone
from unittest.mock import Mock

from botocore.exceptions import ClientError

from src.awsideman.utils.rollback.models import OperationRecord, OperationType, PrincipalType
from src.awsideman.utils.rollback.processor import RollbackProcessor


class TestRollbackProcessorVerification:
    """Test cases for rollback verification logic."""

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

    def test_verify_rollback_without_aws_client(self):
        """Test rollback verification when AWS client is not available."""
        # Arrange
        processor = RollbackProcessor(storage_directory="/tmp/test")
        processor.store = self.mock_store

        # Act
        result = processor.verify_rollback("rollback-123")

        # Assert
        assert not result.verified
        assert "AWS client not available for verification" in result.mismatches
        assert len(result.warnings) == 0

    def test_verify_rollback_record_not_found(self):
        """Test rollback verification when rollback record is not found."""
        # Arrange
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": []}

        # Act
        result = self.processor.verify_rollback("nonexistent-rollback")

        # Assert
        assert not result.verified
        assert "Rollback operation nonexistent-rollback not found" in result.mismatches
        assert len(result.warnings) == 0

    def test_verify_rollback_original_operation_not_found(self):
        """Test rollback verification when original operation is not found."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "revoke",
            "account_ids": ["123456789012"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}
        self.mock_store.get_operation.return_value = None

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert not result.verified
        assert "Original operation not found for verification" in result.mismatches
        assert len(result.warnings) == 0

    def test_verify_rollback_invalid_permission_set_arn(self):
        """Test rollback verification with invalid permission set ARN."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "revoke",
            "account_ids": ["123456789012"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="invalid-arn",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["TestAccount"],
            results=[],
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert not result.verified
        assert "Could not extract SSO instance ARN for verification" in result.mismatches
        assert len(result.warnings) == 0

    def test_verify_rollback_revoke_success(self):
        """Test successful rollback verification for revoke rollback."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "revoke",
            "account_ids": ["123456789012", "123456789013"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012", "123456789013"],
            account_names=["TestAccount1", "TestAccount2"],
            results=[],
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Mock no assignments exist (successful revoke rollback)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": []
        }

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert result.verified
        assert len(result.mismatches) == 0
        assert len(result.warnings) == 0

        # Verify AWS API calls
        expected_calls = [  # noqa: F841
            {
                "InstanceArn": "arn:aws:sso:::instance/ssoins-123",
                "AccountId": "123456789012",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            },
            {
                "InstanceArn": "arn:aws:sso:::instance/ssoins-123",
                "AccountId": "123456789013",
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            },
        ]
        assert self.mock_identity_center_client.list_account_assignments.call_count == 2

    def test_verify_rollback_assign_success(self):
        """Test successful rollback verification for assign rollback."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "assign",
            "account_ids": ["123456789012"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.REVOKE,
            principal_id="group-456",
            principal_type=PrincipalType.GROUP,
            principal_name="test.group",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["TestAccount"],
            results=[],
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Mock assignment exists (successful assign rollback)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "group-456",
                    "PrincipalType": "GROUP",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                }
            ]
        }

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert result.verified
        assert len(result.mismatches) == 0
        assert len(result.warnings) == 0

    def test_verify_rollback_revoke_mismatch(self):
        """Test rollback verification with mismatch for revoke rollback."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "revoke",
            "account_ids": ["123456789012"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
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
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Mock assignment still exists (failed revoke rollback)
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
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert not result.verified
        assert len(result.mismatches) == 1
        assert (
            "Account 123456789012: Assignment still exists after revoke rollback"
            in result.mismatches[0]
        )
        assert len(result.warnings) == 0

    def test_verify_rollback_assign_mismatch(self):
        """Test rollback verification with mismatch for assign rollback."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "assign",
            "account_ids": ["123456789012"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.REVOKE,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012"],
            account_names=["TestAccount"],
            results=[],
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Mock no assignment exists (failed assign rollback)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": []
        }

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert not result.verified
        assert len(result.mismatches) == 1
        assert (
            "Account 123456789012: Assignment does not exist after assign rollback"
            in result.mismatches[0]
        )
        assert len(result.warnings) == 0

    def test_verify_rollback_api_error(self):
        """Test rollback verification with AWS API error."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "revoke",
            "account_ids": ["123456789012", "123456789013"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012", "123456789013"],
            account_names=["TestAccount1", "TestAccount2"],
            results=[],
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Mock mixed results - success for first account, error for second
        def mock_list_assignments(**kwargs):
            if kwargs["AccountId"] == "123456789012":
                return {"AccountAssignments": []}
            else:
                error_response = {
                    "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}
                }
                raise ClientError(error_response, "ListAccountAssignments")

        self.mock_identity_center_client.list_account_assignments.side_effect = (
            mock_list_assignments
        )

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert result.verified  # Should be verified despite warnings
        assert len(result.mismatches) == 0
        assert len(result.warnings) == 1
        assert "Could not verify account 123456789013: ThrottlingException" in result.warnings[0]

    def test_verify_rollback_unexpected_error(self):
        """Test rollback verification with unexpected error."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "revoke",
            "account_ids": ["123456789012"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
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
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Mock unexpected error
        self.mock_identity_center_client.list_account_assignments.side_effect = Exception(
            "Unexpected error"
        )

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert result.verified  # Should be verified despite warnings
        assert len(result.mismatches) == 0
        assert len(result.warnings) == 1
        assert "Could not verify account 123456789012: Unexpected error" in result.warnings[0]

    def test_verify_rollback_mixed_results(self):
        """Test rollback verification with mixed success and mismatch results."""
        # Arrange
        rollback_record = {
            "rollback_operation_id": "rollback-123",
            "original_operation_id": "original-456",
            "rollback_type": "revoke",
            "account_ids": ["123456789012", "123456789013", "123456789014"],
        }
        self.mock_store._read_rollbacks_file.return_value = {"rollbacks": [rollback_record]}

        original_operation = OperationRecord(
            operation_id="original-456",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="test.user",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-123",
            permission_set_name="TestPermissionSet",
            account_ids=["123456789012", "123456789013", "123456789014"],
            account_names=["TestAccount1", "TestAccount2", "TestAccount3"],
            results=[],
            rolled_back=True,
        )
        self.mock_store.get_operation.return_value = original_operation

        # Mock mixed results
        def mock_list_assignments(**kwargs):
            if kwargs["AccountId"] == "123456789012":
                # Success - no assignment
                return {"AccountAssignments": []}
            elif kwargs["AccountId"] == "123456789013":
                # Mismatch - assignment still exists
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
                # Success - no assignment
                return {"AccountAssignments": []}

        self.mock_identity_center_client.list_account_assignments.side_effect = (
            mock_list_assignments
        )

        # Act
        result = self.processor.verify_rollback("rollback-123")

        # Assert
        assert not result.verified  # Should not be verified due to mismatch
        assert len(result.mismatches) == 1
        assert (
            "Account 123456789013: Assignment still exists after revoke rollback"
            in result.mismatches[0]
        )
        assert len(result.warnings) == 0

    def test_get_rollback_record_success(self):
        """Test successful rollback record retrieval."""
        # Arrange
        rollback_records = {
            "rollbacks": [
                {
                    "rollback_operation_id": "rollback-123",
                    "original_operation_id": "original-456",
                    "rollback_type": "revoke",
                },
                {
                    "rollback_operation_id": "rollback-789",
                    "original_operation_id": "original-101",
                    "rollback_type": "assign",
                },
            ]
        }
        self.mock_store._read_rollbacks_file.return_value = rollback_records

        # Act
        result = self.processor._get_rollback_record("rollback-123")

        # Assert
        assert result is not None
        assert result["rollback_operation_id"] == "rollback-123"
        assert result["original_operation_id"] == "original-456"
        assert result["rollback_type"] == "revoke"

    def test_get_rollback_record_not_found(self):
        """Test rollback record retrieval when record is not found."""
        # Arrange
        rollback_records = {"rollbacks": []}
        self.mock_store._read_rollbacks_file.return_value = rollback_records

        # Act
        result = self.processor._get_rollback_record("nonexistent-rollback")

        # Assert
        assert result is None

    def test_get_rollback_record_file_error(self):
        """Test rollback record retrieval with file read error."""
        # Arrange
        self.mock_store._read_rollbacks_file.side_effect = Exception("File read error")

        # Act
        result = self.processor._get_rollback_record("rollback-123")

        # Assert
        assert result is None
