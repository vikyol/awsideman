"""Tests for rollback state verification system."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.rollback.exceptions import (
    AWSClientNotAvailableError,
    IdempotencyViolationError,
    StateVerificationError,
)
from src.awsideman.rollback.models import (
    AssignmentState,
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
    RollbackAction,
    RollbackActionType,
)
from src.awsideman.rollback.state_verification import (
    AssignmentVerificationResult,
    IdempotencyCheck,
    RollbackStateVerifier,
    StateVerificationResult,
    VerificationLevel,
    get_state_verifier,
)


class TestAssignmentVerificationResult:
    """Test the AssignmentVerificationResult class."""

    def test_assignment_verification_result_creation(self):
        """Test creating assignment verification result."""
        result = AssignmentVerificationResult(
            account_id="123456789012",
            principal_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            expected_state=AssignmentState.ASSIGNED,
            actual_state=AssignmentState.ASSIGNED,
            verified=True,
        )

        assert result.account_id == "123456789012"
        assert result.principal_id == "user-123"
        assert result.expected_state == AssignmentState.ASSIGNED
        assert result.actual_state == AssignmentState.ASSIGNED
        assert result.verified is True
        assert result.error is None
        assert result.warnings == []
        assert result.metadata == {}

    def test_assignment_verification_result_with_error(self):
        """Test assignment verification result with error."""
        result = AssignmentVerificationResult(
            account_id="123456789012",
            principal_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            expected_state=AssignmentState.ASSIGNED,
            actual_state=AssignmentState.NOT_ASSIGNED,
            verified=False,
            error="State mismatch",
            warnings=["Warning 1", "Warning 2"],
            metadata={"key": "value"},
        )

        assert result.verified is False
        assert result.error == "State mismatch"
        assert result.warnings == ["Warning 1", "Warning 2"]
        assert result.metadata == {"key": "value"}


class TestStateVerificationResult:
    """Test the StateVerificationResult class."""

    def test_state_verification_result_creation(self):
        """Test creating state verification result."""
        assignment_results = [
            AssignmentVerificationResult(
                account_id="123456789012",
                principal_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                expected_state=AssignmentState.ASSIGNED,
                actual_state=AssignmentState.ASSIGNED,
                verified=True,
            )
        ]

        result = StateVerificationResult(
            operation_id="op-123",
            verification_level=VerificationLevel.BASIC,
            total_assignments=1,
            verified_assignments=1,
            failed_verifications=0,
            assignment_results=assignment_results,
            overall_verified=True,
        )

        assert result.operation_id == "op-123"
        assert result.verification_level == VerificationLevel.BASIC
        assert result.total_assignments == 1
        assert result.verified_assignments == 1
        assert result.failed_verifications == 0
        assert result.overall_verified is True
        assert len(result.assignment_results) == 1
        assert result.errors == []
        assert result.warnings == []


class TestIdempotencyCheck:
    """Test the IdempotencyCheck class."""

    def test_idempotency_check_success(self):
        """Test successful idempotency check."""
        check = IdempotencyCheck(
            operation_id="op-123",
            is_idempotent=True,
        )

        assert check.operation_id == "op-123"
        assert check.is_idempotent is True
        assert check.existing_rollback_ids == []
        assert check.conflicts == []
        assert check.warnings == []

    def test_idempotency_check_failure(self):
        """Test failed idempotency check."""
        check = IdempotencyCheck(
            operation_id="op-123",
            is_idempotent=False,
            existing_rollback_ids=["rollback-456"],
            conflicts=["Conflict 1", "Conflict 2"],
            warnings=["Warning 1"],
        )

        assert check.is_idempotent is False
        assert check.existing_rollback_ids == ["rollback-456"]
        assert check.conflicts == ["Conflict 1", "Conflict 2"]
        assert check.warnings == ["Warning 1"]


class TestRollbackStateVerifier:
    """Test the RollbackStateVerifier class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_aws_client_manager = Mock()
        self.mock_identity_center_client = Mock()
        self.mock_identity_store_client = Mock()

        self.mock_aws_client_manager.get_identity_center_client.return_value = (
            self.mock_identity_center_client
        )
        self.mock_aws_client_manager.get_identity_store_client.return_value = (
            self.mock_identity_store_client
        )

        self.verifier = RollbackStateVerifier(
            aws_client_manager=self.mock_aws_client_manager,
        )

    def test_initialization(self):
        """Test verifier initialization."""
        assert self.verifier.aws_client_manager == self.mock_aws_client_manager
        assert self.verifier.identity_center_client == self.mock_identity_center_client
        assert self.verifier.identity_store_client == self.mock_identity_store_client

    def test_initialization_without_aws_client(self):
        """Test verifier initialization without AWS client."""
        verifier = RollbackStateVerifier()

        assert verifier.aws_client_manager is None
        assert verifier.identity_center_client is None
        assert verifier.identity_store_client is None

    def test_extract_sso_instance_arn_success(self):
        """Test successful SSO instance ARN extraction."""
        permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-123456789012/ps-abcdef123456"

        result = self.verifier._extract_sso_instance_arn(permission_set_arn)

        assert result == "arn:aws:sso:::instance/ssoins-123456789012"

    def test_extract_sso_instance_arn_invalid_format(self):
        """Test SSO instance ARN extraction with invalid format."""
        permission_set_arn = "invalid-arn-format"

        result = self.verifier._extract_sso_instance_arn(permission_set_arn)

        assert result is None

    def test_get_current_assignment_state_assigned(self):
        """Test getting current assignment state when assigned."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
        )

        # Mock AWS response showing assignment exists
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                }
            ]
        }

        result = self.verifier._get_current_assignment_state(
            operation, "123456789012", "arn:aws:sso:::instance/ssoins-123"
        )

        assert result == AssignmentState.ASSIGNED

    def test_get_current_assignment_state_not_assigned(self):
        """Test getting current assignment state when not assigned."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
        )

        # Mock AWS response showing no assignments
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": []
        }

        result = self.verifier._get_current_assignment_state(
            operation, "123456789012", "arn:aws:sso:::instance/ssoins-123"
        )

        assert result == AssignmentState.NOT_ASSIGNED

    def test_get_current_assignment_state_client_error(self):
        """Test getting current assignment state with client error."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
        )

        # Mock AWS client error
        self.mock_identity_center_client.list_account_assignments.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="ListAccountAssignments",
        )

        result = self.verifier._get_current_assignment_state(
            operation, "123456789012", "arn:aws:sso:::instance/ssoins-123"
        )

        assert result == AssignmentState.UNKNOWN

    def test_get_current_assignment_state_no_client(self):
        """Test getting current assignment state without AWS client."""
        verifier = RollbackStateVerifier()  # No AWS client

        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
        )

        result = verifier._get_current_assignment_state(
            operation, "123456789012", "arn:aws:sso:::instance/ssoins-123"
        )

        assert result == AssignmentState.UNKNOWN

    def test_verify_pre_rollback_state_no_client(self):
        """Test pre-rollback state verification without AWS client."""
        verifier = RollbackStateVerifier()  # No AWS client

        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True)],
        )

        with pytest.raises(AWSClientNotAvailableError):
            verifier.verify_pre_rollback_state(operation)

    def test_verify_pre_rollback_state_invalid_permission_set_arn(self):
        """Test pre-rollback state verification with invalid permission set ARN."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="invalid-arn",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True)],
        )

        with pytest.raises(StateVerificationError) as exc_info:
            self.verifier.verify_pre_rollback_state(operation)

        assert "not_extractable" in str(exc_info.value)

    def test_verify_pre_rollback_state_success(self):
        """Test successful pre-rollback state verification."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True)],
        )

        # Mock AWS response showing assignment exists (expected for assign operation)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                }
            ]
        }

        result = self.verifier.verify_pre_rollback_state(operation)

        assert result.operation_id == "op-123"
        assert result.verification_level == VerificationLevel.BASIC
        assert result.total_assignments == 1
        assert result.verified_assignments == 1
        assert result.failed_verifications == 0
        assert result.overall_verified is True

    def test_verify_pre_rollback_state_with_failed_results(self):
        """Test pre-rollback state verification with failed results."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012", "123456789013"],
            account_names=["Production", "Staging"],
            results=[
                OperationResult(account_id="123456789012", success=True),
                OperationResult(
                    account_id="123456789013", success=False, error="Permission denied"
                ),
            ],
        )

        # Mock AWS response for successful account
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                }
            ]
        }

        result = self.verifier.verify_pre_rollback_state(operation)

        assert result.total_assignments == 1  # Only successful results are verified
        assert result.verified_assignments == 1
        assert result.failed_verifications == 0
        assert result.overall_verified is True
        assert len(result.warnings) > 0  # Should warn about skipped failed result

    def test_verify_post_rollback_state_success(self):
        """Test successful post-rollback state verification."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True)],
        )

        rollback_actions = [
            RollbackAction(
                principal_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                account_id="123456789012",
                action_type=RollbackActionType.REVOKE,  # Rollback of assign is revoke
                current_state=AssignmentState.NOT_ASSIGNED,
                principal_type=PrincipalType.USER,
            )
        ]

        # Mock AWS response showing assignment no longer exists (expected after revoke)
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": []
        }

        result = self.verifier.verify_post_rollback_state(operation, rollback_actions)

        assert result.operation_id == "op-123"
        assert result.total_assignments == 1
        assert result.verified_assignments == 1
        assert result.failed_verifications == 0
        assert result.overall_verified is True

    def test_check_idempotency_operation_not_found(self):
        """Test idempotency check with operation not found."""
        with patch.object(self.verifier.store, "get_operation", return_value=None):
            result = self.verifier.check_idempotency("nonexistent-op")

        assert result.operation_id == "nonexistent-op"
        assert result.is_idempotent is False
        assert "not found" in result.conflicts[0]

    def test_check_idempotency_already_rolled_back(self):
        """Test idempotency check with already rolled back operation."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
            rolled_back=True,
            rollback_operation_id="rollback-456",
        )

        with patch.object(self.verifier.store, "get_operation", return_value=operation):
            with pytest.raises(IdempotencyViolationError) as exc_info:
                self.verifier.check_idempotency("op-123")

        assert exc_info.value.operation_id == "op-123"
        assert exc_info.value.duplicate_rollback_id == "rollback-456"

    def test_check_idempotency_success(self):
        """Test successful idempotency check."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
            rolled_back=False,
        )

        with patch.object(self.verifier.store, "get_operation", return_value=operation):
            with patch.object(self.verifier, "_find_existing_rollbacks", return_value=[]):
                with patch.object(self.verifier, "_check_resource_conflicts", return_value=[]):
                    result = self.verifier.check_idempotency("op-123")

        assert result.operation_id == "op-123"
        assert result.is_idempotent is True
        assert result.existing_rollback_ids == []
        assert result.conflicts == []

    def test_get_assignment_metadata_basic(self):
        """Test getting assignment metadata for basic verification."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
        )

        metadata = self.verifier._get_assignment_metadata(
            operation, "123456789012", "arn:aws:sso:::instance/ssoins-123", VerificationLevel.BASIC
        )

        assert metadata == {}  # Basic level returns empty metadata

    def test_get_assignment_metadata_detailed(self):
        """Test getting assignment metadata for detailed verification."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
        )

        metadata = self.verifier._get_assignment_metadata(
            operation,
            "123456789012",
            "arn:aws:sso:::instance/ssoins-123",
            VerificationLevel.DETAILED,
        )

        assert metadata["account_id"] == "123456789012"
        assert metadata["permission_set_name"] == "ReadOnlyAccess"
        assert metadata["principal_name"] == "john.doe"
        assert metadata["principal_type"] == "USER"

    def test_get_assignment_metadata_comprehensive(self):
        """Test getting assignment metadata for comprehensive verification."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[],
        )

        # Mock AWS response
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                    "AccountId": "123456789012",
                }
            ]
        }

        metadata = self.verifier._get_assignment_metadata(
            operation,
            "123456789012",
            "arn:aws:sso:::instance/ssoins-123",
            VerificationLevel.COMPREHENSIVE,
        )

        assert metadata["account_id"] == "123456789012"
        assert metadata["permission_set_name"] == "ReadOnlyAccess"
        assert metadata["principal_name"] == "john.doe"
        assert metadata["principal_type"] == "USER"
        assert "verification_timestamp" in metadata
        assert "assignment_details" in metadata


class TestGlobalStateVerifier:
    """Test global state verifier functions."""

    def test_get_state_verifier_singleton(self):
        """Test that get_state_verifier returns singleton."""
        verifier1 = get_state_verifier()
        verifier2 = get_state_verifier()

        assert verifier1 is verifier2
        assert isinstance(verifier1, RollbackStateVerifier)

    def test_get_state_verifier_with_parameters(self):
        """Test get_state_verifier with parameters."""
        mock_aws_client_manager = Mock()

        verifier = get_state_verifier(
            aws_client_manager=mock_aws_client_manager,
            storage_directory="/custom/path",
        )

        assert isinstance(verifier, RollbackStateVerifier)


class TestVerificationLevels:
    """Test different verification levels."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_aws_client_manager = Mock()
        self.mock_identity_center_client = Mock()

        self.mock_aws_client_manager.get_identity_center_client.return_value = (
            self.mock_identity_center_client
        )

        self.verifier = RollbackStateVerifier(
            aws_client_manager=self.mock_aws_client_manager,
        )

    def test_verification_levels_enum(self):
        """Test verification level enum values."""
        assert VerificationLevel.BASIC == "basic"
        assert VerificationLevel.DETAILED == "detailed"
        assert VerificationLevel.COMPREHENSIVE == "comprehensive"

    def test_basic_verification_level(self):
        """Test basic verification level behavior."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True)],
        )

        # Mock AWS response
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                }
            ]
        }

        result = self.verifier.verify_pre_rollback_state(operation, VerificationLevel.BASIC)

        assert result.verification_level == VerificationLevel.BASIC
        assert len(result.assignment_results) == 1

        # Basic level should have minimal metadata
        assignment_result = result.assignment_results[0]
        assert assignment_result.metadata == {}

    def test_detailed_verification_level(self):
        """Test detailed verification level behavior."""
        operation = OperationRecord(
            operation_id="op-123",
            timestamp=datetime.now(timezone.utc),
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=[OperationResult(account_id="123456789012", success=True)],
        )

        # Mock AWS response
        self.mock_identity_center_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-123",
                    "PrincipalType": "USER",
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                }
            ]
        }

        result = self.verifier.verify_pre_rollback_state(operation, VerificationLevel.DETAILED)

        assert result.verification_level == VerificationLevel.DETAILED

        # Detailed level should have more metadata
        assignment_result = result.assignment_results[0]
        assert "account_id" in assignment_result.metadata
        assert "permission_set_name" in assignment_result.metadata
        assert "principal_name" in assignment_result.metadata
