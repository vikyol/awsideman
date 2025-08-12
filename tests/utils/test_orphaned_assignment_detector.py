"""Tests for orphaned assignment detection component."""
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.orphaned_assignment_detector import OrphanedAssignmentDetector
from src.awsideman.utils.status_infrastructure import StatusCheckConfig
from src.awsideman.utils.status_models import (
    CleanupResult,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    PrincipalType,
    StatusLevel,
)


@pytest.fixture
def mock_idc_client():
    """Create a mock Identity Center client."""
    client = Mock()
    client.client = Mock()
    client.client_manager = Mock()

    # Mock client manager methods
    client.client_manager.get_identity_store_client.return_value = Mock()
    client.client_manager.get_organizations_client.return_value = Mock()

    return client


@pytest.fixture
def detector(mock_idc_client):
    """Create an OrphanedAssignmentDetector instance."""
    config = StatusCheckConfig(timeout_seconds=10, retry_attempts=1)
    return OrphanedAssignmentDetector(mock_idc_client, config)


@pytest.fixture
def sample_orphaned_assignment():
    """Create a sample orphaned assignment."""
    return OrphanedAssignment(
        assignment_id="arn:aws:sso:::permissionSet/ssoins-123/ps-456#user-789#123456789012",
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
        permission_set_name="TestPermissionSet",
        account_id="123456789012",
        account_name="Test Account",
        principal_id="user-789",
        principal_type=PrincipalType.USER,
        principal_name="deleted-user",
        error_message="AWS Error ResourceNotFoundException: User not found",
        created_date=datetime.utcnow() - timedelta(days=5),
        last_accessed=None,
    )


class TestOrphanedAssignmentDetector:
    """Test cases for OrphanedAssignmentDetector."""

    @pytest.mark.asyncio
    async def test_check_status_no_orphaned_assignments(self, detector, mock_idc_client):
        """Test status check when no orphaned assignments are found."""
        # Mock AWS API responses
        mock_idc_client.client.list_instances.return_value = {
            "Instances": [
                {"InstanceArn": "arn:aws:sso:::instance/ssoins-123", "IdentityStoreId": "store-123"}
            ]
        }
        mock_idc_client.client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_idc_client.client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_idc_client.client.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_idc_client.client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-789",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.utcnow(),
                }
            ]
        }

        # Mock identity store client - user exists
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_user.return_value = {
            "UserName": "test-user",
            "DisplayName": "Test User",
        }

        # Mock organizations client
        org_client = mock_idc_client.client_manager.get_organizations_client()
        org_client.describe_account.return_value = {"Name": "Test Account"}

        result = await detector.check_status()

        assert isinstance(result, OrphanedAssignmentStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.message == "No orphaned assignments found"
        assert len(result.orphaned_assignments) == 0
        assert result.cleanup_available is True

    @pytest.mark.asyncio
    async def test_check_status_with_orphaned_assignments(self, detector, mock_idc_client):
        """Test status check when orphaned assignments are found."""
        # Mock AWS API responses
        mock_idc_client.client.list_instances.return_value = {
            "Instances": [
                {"InstanceArn": "arn:aws:sso:::instance/ssoins-123", "IdentityStoreId": "store-123"}
            ]
        }
        mock_idc_client.client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_idc_client.client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_idc_client.client.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_idc_client.client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-789",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.utcnow() - timedelta(days=5),
                }
            ]
        }

        # Mock identity store client - user does not exist (orphaned)
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_user.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ResourceNotFoundException", "Message": "User not found"}
            },
            operation_name="DescribeUser",
        )

        # Mock organizations client
        org_client = mock_idc_client.client_manager.get_organizations_client()
        org_client.describe_account.return_value = {"Name": "Test Account"}

        result = await detector.check_status()

        assert isinstance(result, OrphanedAssignmentStatus)
        assert result.status == StatusLevel.WARNING
        assert "orphaned assignments found" in result.message
        assert len(result.orphaned_assignments) == 1

        orphaned = result.orphaned_assignments[0]
        assert orphaned.principal_id == "user-789"
        assert orphaned.principal_type == PrincipalType.USER
        assert "ResourceNotFoundException" in orphaned.error_message
        assert orphaned.permission_set_name == "TestPermissionSet"

    @pytest.mark.asyncio
    async def test_check_status_critical_many_orphaned(self, detector, mock_idc_client):
        """Test status check when many orphaned assignments trigger critical status."""
        # Create many orphaned assignments
        assignments = []
        for i in range(60):  # More than 50 to trigger critical
            assignments.append(
                {
                    "PrincipalId": f"user-{i}",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.utcnow()
                    - timedelta(days=i % 40),  # Some old assignments
                }
            )

        # Mock AWS API responses
        mock_idc_client.client.list_instances.return_value = {
            "Instances": [
                {"InstanceArn": "arn:aws:sso:::instance/ssoins-123", "IdentityStoreId": "store-123"}
            ]
        }
        mock_idc_client.client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_idc_client.client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_idc_client.client.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_idc_client.client.list_account_assignments.return_value = {
            "AccountAssignments": assignments
        }

        # Mock identity store client - all users do not exist (orphaned)
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_user.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ResourceNotFoundException", "Message": "User not found"}
            },
            operation_name="DescribeUser",
        )

        # Mock organizations client
        org_client = mock_idc_client.client_manager.get_organizations_client()
        org_client.describe_account.return_value = {"Name": "Test Account"}

        result = await detector.check_status()

        assert isinstance(result, OrphanedAssignmentStatus)
        assert result.status == StatusLevel.CRITICAL
        assert "Critical:" in result.message
        assert len(result.orphaned_assignments) == 60

    @pytest.mark.asyncio
    async def test_check_status_error_handling(self, detector, mock_idc_client):
        """Test error handling during status check."""
        # Mock AWS API to raise an exception
        mock_idc_client.client.list_instances.side_effect = Exception("Connection failed")

        result = await detector.check_status()

        assert isinstance(result, OrphanedAssignmentStatus)
        assert result.status == StatusLevel.CRITICAL
        assert "Orphaned assignment detection failed" in result.message
        assert len(result.errors) > 0
        assert result.cleanup_available is False

    @pytest.mark.asyncio
    async def test_check_principal_exists_user_exists(self, detector, mock_idc_client):
        """Test checking if a user principal exists."""
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_user.return_value = {
            "UserName": "test-user",
            "DisplayName": "Test User",
        }

        exists, name, error = await detector._check_principal_exists(
            "store-123", "user-789", "USER", identity_store_client
        )

        assert exists is True
        assert name == "test-user"
        assert error is None

    @pytest.mark.asyncio
    async def test_check_principal_exists_user_not_found(self, detector, mock_idc_client):
        """Test checking if a user principal exists when it doesn't."""
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_user.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ResourceNotFoundException", "Message": "User not found"}
            },
            operation_name="DescribeUser",
        )

        exists, name, error = await detector._check_principal_exists(
            "store-123", "user-789", "USER", identity_store_client
        )

        assert exists is False
        assert name is None
        assert "ResourceNotFoundException" in error

    @pytest.mark.asyncio
    async def test_check_principal_exists_group_exists(self, detector, mock_idc_client):
        """Test checking if a group principal exists."""
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_group.return_value = {"DisplayName": "Test Group"}

        exists, name, error = await detector._check_principal_exists(
            "store-123", "group-789", "GROUP", identity_store_client
        )

        assert exists is True
        assert name == "Test Group"
        assert error is None

    @pytest.mark.asyncio
    async def test_check_principal_exists_access_denied(self, detector, mock_idc_client):
        """Test checking principal when access is denied."""
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_user.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="DescribeUser",
        )

        exists, name, error = await detector._check_principal_exists(
            "store-123", "user-789", "USER", identity_store_client
        )

        # Should assume principal exists when access is denied to avoid false positives
        assert exists is True
        assert name == "Unknown user"
        assert error is None

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_assignments_success(
        self, detector, mock_idc_client, sample_orphaned_assignment
    ):
        """Test successful cleanup of orphaned assignments."""
        assignments = [sample_orphaned_assignment]

        # Mock successful delete operation
        mock_idc_client.client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS", "RequestId": "req-123"}
        }

        result = await detector.cleanup_orphaned_assignments(assignments)

        assert isinstance(result, CleanupResult)
        assert result.total_attempted == 1
        assert result.successful_cleanups == 1
        assert result.failed_cleanups == 0
        assert len(result.cleaned_assignments) == 1
        assert result.is_complete_success() is True
        assert result.get_success_rate() == 100.0

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_assignments_failure(
        self, detector, mock_idc_client, sample_orphaned_assignment
    ):
        """Test cleanup failure handling."""
        assignments = [sample_orphaned_assignment]

        # Mock failed delete operation
        mock_idc_client.client.delete_account_assignment.side_effect = ClientError(
            error_response={
                "Error": {"Code": "AccessDenied", "Message": "Insufficient permissions"}
            },
            operation_name="DeleteAccountAssignment",
        )

        result = await detector.cleanup_orphaned_assignments(assignments)

        assert isinstance(result, CleanupResult)
        assert result.total_attempted == 1
        assert result.successful_cleanups == 0
        assert result.failed_cleanups == 1
        assert len(result.cleanup_errors) == 1
        assert result.has_failures() is True
        assert result.get_success_rate() == 0.0

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_assignments_empty_list(self, detector):
        """Test cleanup with empty assignment list."""
        result = await detector.cleanup_orphaned_assignments([])

        assert isinstance(result, CleanupResult)
        assert result.total_attempted == 0
        assert result.successful_cleanups == 0
        assert result.failed_cleanups == 0
        assert len(result.cleanup_errors) == 0

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_assignments_mixed_results(self, detector, mock_idc_client):
        """Test cleanup with mixed success and failure results."""
        # Create multiple assignments
        assignments = []
        for i in range(3):
            assignment = OrphanedAssignment(
                assignment_id=f"assignment-{i}",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                permission_set_name="TestPermissionSet",
                account_id="123456789012",
                account_name="Test Account",
                principal_id=f"user-{i}",
                principal_type=PrincipalType.USER,
                principal_name=f"deleted-user-{i}",
                error_message="User not found",
                created_date=datetime.utcnow() - timedelta(days=i + 1),
            )
            assignments.append(assignment)

        # Mock mixed results: first succeeds, second fails, third succeeds
        def mock_delete_side_effect(*args, **kwargs):
            principal_id = kwargs.get("PrincipalId", "")
            if principal_id == "user-1":  # Second call fails
                raise ClientError(
                    error_response={
                        "Error": {"Code": "AccessDenied", "Message": "Insufficient permissions"}
                    },
                    operation_name="DeleteAccountAssignment",
                )
            return {"AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS"}}

        mock_idc_client.client.delete_account_assignment.side_effect = mock_delete_side_effect

        result = await detector.cleanup_orphaned_assignments(assignments)

        assert isinstance(result, CleanupResult)
        assert result.total_attempted == 3
        assert result.successful_cleanups == 2
        assert result.failed_cleanups == 1
        assert len(result.cleanup_errors) == 1
        assert len(result.cleaned_assignments) == 2
        assert result.get_success_rate() == pytest.approx(66.7, rel=1e-1)

    def test_prompt_for_cleanup_empty_list(self, detector):
        """Test prompt for cleanup with empty assignment list."""
        result = detector.prompt_for_cleanup([])
        assert result is False

    @patch("builtins.input")
    def test_prompt_for_cleanup_user_confirms(
        self, mock_input, detector, sample_orphaned_assignment
    ):
        """Test prompt for cleanup when user confirms."""
        mock_input.return_value = "yes"

        result = detector.prompt_for_cleanup([sample_orphaned_assignment])
        assert result is True

    @patch("builtins.input")
    def test_prompt_for_cleanup_user_declines(
        self, mock_input, detector, sample_orphaned_assignment
    ):
        """Test prompt for cleanup when user declines."""
        mock_input.return_value = "no"

        result = detector.prompt_for_cleanup([sample_orphaned_assignment])
        assert result is False

    @patch("builtins.input")
    def test_prompt_for_cleanup_invalid_then_valid_input(
        self, mock_input, detector, sample_orphaned_assignment
    ):
        """Test prompt for cleanup with invalid input followed by valid input."""
        mock_input.side_effect = ["maybe", "invalid", "yes"]

        result = detector.prompt_for_cleanup([sample_orphaned_assignment])
        assert result is True
        assert mock_input.call_count == 3

    @patch("builtins.input")
    def test_prompt_for_cleanup_keyboard_interrupt(
        self, mock_input, detector, sample_orphaned_assignment
    ):
        """Test prompt for cleanup when user interrupts with Ctrl+C."""
        mock_input.side_effect = KeyboardInterrupt()

        result = detector.prompt_for_cleanup([sample_orphaned_assignment])
        assert result is False

    def test_get_assignment_errors(self, detector, sample_orphaned_assignment):
        """Test getting detailed error information for assignments."""
        assignments = [sample_orphaned_assignment]

        errors = detector.get_assignment_errors(assignments)

        assert len(errors) == 1
        error = errors[0]
        assert error["assignment_id"] == sample_orphaned_assignment.assignment_id
        assert error["permission_set_name"] == sample_orphaned_assignment.permission_set_name
        assert error["principal_id"] == sample_orphaned_assignment.principal_id
        assert error["error_message"] == sample_orphaned_assignment.error_message
        assert "age_days" in error
        assert "display_name" in error

    def test_format_cleanup_summary(self, detector):
        """Test formatting cleanup summary."""
        # Test with no operations
        result = CleanupResult(
            total_attempted=0, successful_cleanups=0, failed_cleanups=0, duration_seconds=0.0
        )
        summary = detector.format_cleanup_summary(result)
        assert summary == "No cleanup operations attempted"

        # Test with successful operations
        result = CleanupResult(
            total_attempted=5, successful_cleanups=4, failed_cleanups=1, duration_seconds=2.5
        )
        summary = detector.format_cleanup_summary(result)
        assert "2.50s" in summary
        assert "Attempted: 5" in summary
        assert "Successful: 4" in summary
        assert "Failed: 1" in summary
        assert "80.0%" in summary

    def test_format_orphaned_assignment_summary(self, detector):
        """Test formatting orphaned assignment summary."""
        # Create sample status
        orphaned_assignments = [
            OrphanedAssignment(
                assignment_id="assignment-1",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                permission_set_name="TestPS",
                account_id="123456789012",
                account_name="Test Account",
                principal_id="user-1",
                principal_type=PrincipalType.USER,
                principal_name="deleted-user-1",
                error_message="User not found",
                created_date=datetime.utcnow(),
            ),
            OrphanedAssignment(
                assignment_id="assignment-2",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-789",
                permission_set_name="TestPS2",
                account_id="123456789012",
                account_name="Test Account",
                principal_id="group-1",
                principal_type=PrincipalType.GROUP,
                principal_name="deleted-group-1",
                error_message="Group not found",
                created_date=datetime.utcnow(),
            ),
        ]

        status = OrphanedAssignmentStatus(
            timestamp=datetime.utcnow(),
            status=StatusLevel.WARNING,
            message="2 orphaned assignments found",
            orphaned_assignments=orphaned_assignments,
            cleanup_available=True,
        )

        summary = detector.format_orphaned_assignment_summary(status)

        assert "Status: Warning" in summary
        assert "Orphaned: 2" in summary
        assert "Users: 1" in summary
        assert "Groups: 1" in summary
        assert "Accounts: 1" in summary
        assert "Cleanup: Available" in summary

    def test_orphaned_assignment_model_methods(self, sample_orphaned_assignment):
        """Test OrphanedAssignment model methods."""
        assignment = sample_orphaned_assignment

        # Test display name
        display_name = assignment.get_display_name()
        assert "deleted-user" in display_name
        assert "TestPermissionSet" in display_name
        assert "Test Account" in display_name

        # Test type checks
        assert assignment.is_user_assignment() is True
        assert assignment.is_group_assignment() is False

        # Test age calculation
        age_days = assignment.get_age_days()
        assert age_days >= 4  # Should be around 5 days old
        assert age_days <= 6

    def test_cleanup_result_model_methods(self):
        """Test CleanupResult model methods."""
        result = CleanupResult(
            total_attempted=10,
            successful_cleanups=8,
            failed_cleanups=2,
            cleanup_errors=["Error 1", "Error 2"],
            cleaned_assignments=["assignment-1", "assignment-2"],
            duration_seconds=5.0,
        )

        assert result.get_success_rate() == 80.0
        assert result.has_failures() is True
        assert result.is_complete_success() is False

        # Test complete success
        success_result = CleanupResult(total_attempted=5, successful_cleanups=5, failed_cleanups=0)
        assert success_result.is_complete_success() is True
        assert success_result.has_failures() is False
        assert success_result.get_success_rate() == 100.0

    def test_orphaned_assignment_status_model_methods(self):
        """Test OrphanedAssignmentStatus model methods."""
        user_assignment = OrphanedAssignment(
            assignment_id="user-assignment",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="TestPS",
            account_id="123456789012",
            account_name="Account 1",
            principal_id="user-1",
            principal_type=PrincipalType.USER,
            principal_name="deleted-user",
            error_message="User not found",
            created_date=datetime.utcnow(),
        )

        group_assignment = OrphanedAssignment(
            assignment_id="group-assignment",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-789",
            permission_set_name="TestPS2",
            account_id="987654321098",
            account_name="Account 2",
            principal_id="group-1",
            principal_type=PrincipalType.GROUP,
            principal_name="deleted-group",
            error_message="Group not found",
            created_date=datetime.utcnow(),
        )

        status = OrphanedAssignmentStatus(
            timestamp=datetime.utcnow(),
            status=StatusLevel.WARNING,
            message="Test message",
            orphaned_assignments=[user_assignment, group_assignment],
        )

        assert status.get_orphaned_count() == 2
        assert status.has_orphaned_assignments() is True

        user_orphans = status.get_user_orphans()
        assert len(user_orphans) == 1
        assert user_orphans[0].principal_type == PrincipalType.USER

        group_orphans = status.get_group_orphans()
        assert len(group_orphans) == 1
        assert group_orphans[0].principal_type == PrincipalType.GROUP

        accounts = status.get_accounts_with_orphans()
        assert len(accounts) == 2
        assert "123456789012" in accounts
        assert "987654321098" in accounts


class TestOrphanedAssignmentDetectorIntegration:
    """Integration tests for OrphanedAssignmentDetector."""

    @pytest.mark.asyncio
    async def test_end_to_end_detection_and_cleanup(self, detector, mock_idc_client):
        """Test end-to-end detection and cleanup workflow."""
        # Setup mock responses for detection
        mock_idc_client.client.list_instances.return_value = {
            "Instances": [
                {"InstanceArn": "arn:aws:sso:::instance/ssoins-123", "IdentityStoreId": "store-123"}
            ]
        }
        mock_idc_client.client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_idc_client.client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_idc_client.client.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_idc_client.client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-789",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.utcnow() - timedelta(days=5),
                }
            ]
        }

        # Mock identity store client - user does not exist (orphaned)
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_user.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ResourceNotFoundException", "Message": "User not found"}
            },
            operation_name="DescribeUser",
        )

        # Mock organizations client
        org_client = mock_idc_client.client_manager.get_organizations_client()
        org_client.describe_account.return_value = {"Name": "Test Account"}

        # Mock cleanup success
        mock_idc_client.client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS"}
        }

        # Step 1: Detect orphaned assignments
        status = await detector.check_status()
        assert status.status == StatusLevel.WARNING
        assert len(status.orphaned_assignments) == 1

        # Step 2: Clean up orphaned assignments
        cleanup_result = await detector.cleanup_orphaned_assignments(status.orphaned_assignments)
        assert cleanup_result.is_complete_success()
        assert cleanup_result.successful_cleanups == 1

        # Verify cleanup was called with correct parameters
        mock_idc_client.client.delete_account_assignment.assert_called_once()
        call_args = mock_idc_client.client.delete_account_assignment.call_args
        assert call_args[1]["PrincipalId"] == "user-789"
        assert call_args[1]["PrincipalType"] == "USER"
        assert call_args[1]["AccountId"] == "123456789012"
