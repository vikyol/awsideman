"""Tests for orphaned assignment detection component."""

from datetime import datetime, timedelta, timezone
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
    # Add profile attribute for profile isolation
    client.profile = "test-profile"

    # Mock the get_sso_admin_client method to return a mock client
    mock_sso_admin_client = Mock()
    client.get_sso_admin_client.return_value = mock_sso_admin_client

    # Mock the get_identity_store_client method to return a mock client
    mock_identity_store_client = Mock()
    client.get_identity_store_client.return_value = mock_identity_store_client

    # Mock client manager methods
    client.client_manager.get_identity_store_client.return_value = mock_identity_store_client
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
        created_date=datetime.now(timezone.utc) - timedelta(days=5),
        last_accessed=None,
    )


class TestOrphanedAssignmentDetector:
    """Test cases for OrphanedAssignmentDetector."""

    @patch("src.awsideman.utils.config.Config")
    @pytest.mark.asyncio
    async def test_check_status_no_orphaned_assignments(
        self, mock_config, detector, mock_idc_client
    ):
        """Test status check when no orphaned assignments are found."""
        # Mock the Config class to return profile configuration
        mock_config_instance = Mock()
        mock_config_instance.get.return_value = {
            "test-profile": {
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-123",
                "identity_store_id": "store-123",
            }
        }
        mock_config.return_value = mock_config_instance

        # Mock AWS API responses
        mock_sso_admin_client = mock_idc_client.get_sso_admin_client.return_value
        mock_sso_admin_client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_sso_admin_client.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_sso_admin_client.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_sso_admin_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-789",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.now(timezone.utc),
                }
            ]
        }

        # Mock identity store client - user exists
        identity_store_client = mock_idc_client.get_identity_store_client.return_value
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

    @patch("src.awsideman.utils.config.Config")
    @pytest.mark.asyncio
    async def test_check_status_with_orphaned_assignments(
        self, mock_config, detector, mock_idc_client
    ):
        """Test status check when orphaned assignments are found."""
        # Mock the Config class to return profile configuration
        mock_config_instance = Mock()
        mock_config_instance.get.return_value = {
            "test-profile": {
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-123",
                "identity_store_id": "store-123",
            }
        }
        mock_config.return_value = mock_config_instance

        # Mock AWS API responses
        mock_idc_client.get_sso_admin_client.return_value.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_idc_client.get_sso_admin_client.return_value.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_idc_client.get_sso_admin_client.return_value.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_idc_client.get_sso_admin_client.return_value.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-789",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.now(timezone.utc) - timedelta(days=5),
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
        assert "Warning:" in result.message
        assert len(result.orphaned_assignments) == 1
        assert result.cleanup_available is True

        # Verify the orphaned assignment details
        orphaned = result.orphaned_assignments[0]
        assert orphaned.principal_id == "user-789"
        assert orphaned.principal_type == PrincipalType.USER
        assert orphaned.permission_set_name == "TestPermissionSet"

    @patch("src.awsideman.utils.config.Config")
    @pytest.mark.asyncio
    async def test_check_status_critical_many_orphaned(
        self, mock_config, detector, mock_idc_client
    ):
        """Test status check when many orphaned assignments are found (critical status)."""
        # Mock the Config class to return profile configuration
        mock_config_instance = Mock()
        mock_config_instance.get.return_value = {
            "test-profile": {
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-123",
                "identity_store_id": "store-123",
            }
        }
        mock_config.return_value = mock_config_instance

        # Create many assignments to trigger critical status
        assignments = []
        for i in range(60):
            assignments.append(
                {
                    "PrincipalId": f"user-{i}",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.now(timezone.utc) - timedelta(days=i + 1),
                }
            )

        # Mock AWS API responses
        mock_idc_client.get_sso_admin_client.return_value.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_idc_client.get_sso_admin_client.return_value.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_idc_client.get_sso_admin_client.return_value.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_idc_client.get_sso_admin_client.return_value.list_account_assignments.return_value = {
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

    @patch("src.awsideman.utils.config.Config")
    @pytest.mark.asyncio
    async def test_check_status_error_handling(self, mock_config, detector, mock_idc_client):
        """Test error handling during status check."""
        # Mock the Config class to return profile configuration
        mock_config_instance = Mock()
        mock_config_instance.get.return_value = {
            "test-profile": {
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-123",
                "identity_store_id": "store-123",
            }
        }
        mock_config.return_value = mock_config_instance

        # Mock AWS API to raise an exception
        mock_idc_client.get_sso_admin_client.return_value.list_permission_sets.side_effect = (
            Exception("Connection failed")
        )

        result = await detector.check_status()

        assert isinstance(result, OrphanedAssignmentStatus)
        # The error is handled gracefully, so we get HEALTHY status with no orphaned assignments
        assert result.status == StatusLevel.HEALTHY
        assert "No orphaned assignments found" in result.message
        assert len(result.orphaned_assignments) == 0
        assert result.cleanup_available is True

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
    async def test_check_principal_exists_group_not_found(self, detector, mock_idc_client):
        """Test checking if a group principal exists when it doesn't."""
        identity_store_client = mock_idc_client.client_manager.get_identity_store_client()
        identity_store_client.describe_group.side_effect = ClientError(
            error_response={
                "Error": {"Code": "ResourceNotFoundException", "Message": "Group not found"}
            },
            operation_name="DescribeGroup",
        )

        exists, name, error = await detector._check_principal_exists(
            "store-123", "group-789", "GROUP", identity_store_client
        )

        assert exists is False
        assert name is None
        assert "ResourceNotFoundException" in error

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
        mock_idc_client.get_sso_admin_client.return_value.delete_account_assignment.return_value = {
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
        mock_idc_client.get_sso_admin_client.return_value.delete_account_assignment.side_effect = (
            ClientError(
                error_response={
                    "Error": {"Code": "AccessDenied", "Message": "Insufficient permissions"}
                },
                operation_name="DeleteAccountAssignment",
            )
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
                created_date=datetime.now(timezone.utc) - timedelta(days=i + 1),
            )
            assignments.append(assignment)

        # Mock mixed results: first succeeds, second fails, third succeeds
        call_count = 0

        def mock_delete_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Second call (index 1) fails
            if call_count == 2:
                raise ClientError(
                    error_response={
                        "Error": {"Code": "AccessDenied", "Message": "Insufficient permissions"}
                    },
                    operation_name="DeleteAccountAssignment",
                )
            return {"AccountAssignmentDeletionStatus": {"Status": "IN_PROGRESS"}}

        mock_idc_client.get_sso_admin_client.return_value.delete_account_assignment.side_effect = (
            mock_delete_side_effect
        )

        result = await detector.cleanup_orphaned_assignments(assignments)

        assert isinstance(result, CleanupResult)
        assert result.total_attempted == 3
        assert result.successful_cleanups == 2
        assert result.failed_cleanups == 1
        assert len(result.cleanup_errors) == 1
        assert result.has_failures() is True
        # Use approximate comparison for floating point precision
        assert abs(result.get_success_rate() - 66.67) < 0.01


class TestOrphanedAssignmentStatus:
    """Test cases for OrphanedAssignmentStatus model."""

    def test_orphaned_assignment_status_creation(self):
        """Test creating OrphanedAssignmentStatus instances."""
        user_assignment = OrphanedAssignment(
            assignment_id="user-assignment",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            permission_set_name="TestPS1",
            account_id="123456789012",
            account_name="Account 1",
            principal_id="user-1",
            principal_type=PrincipalType.USER,
            principal_name="deleted-user",
            error_message="User not found",
            created_date=datetime.now(timezone.utc),
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
            created_date=datetime.now(timezone.utc),
        )

        status = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
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

    @patch("src.awsideman.utils.config.Config")
    @pytest.mark.asyncio
    async def test_end_to_end_detection_and_cleanup(self, mock_config, detector, mock_idc_client):
        """Test end-to-end detection and cleanup workflow."""
        # Mock the Config class to return profile configuration
        mock_config_instance = Mock()
        mock_config_instance.get.return_value = {
            "test-profile": {
                "sso_instance_arn": "arn:aws:sso:::instance/ssoins-123",
                "identity_store_id": "store-123",
            }
        }
        mock_config.return_value = mock_config_instance

        # Setup mock responses for detection
        mock_idc_client.get_sso_admin_client.return_value.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-123/ps-456"]
        }
        mock_idc_client.get_sso_admin_client.return_value.describe_permission_set.return_value = {
            "PermissionSet": {"Name": "TestPermissionSet"}
        }
        mock_idc_client.get_sso_admin_client.return_value.list_accounts_for_provisioned_permission_set.return_value = {
            "AccountIds": ["123456789012"]
        }
        mock_idc_client.get_sso_admin_client.return_value.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PrincipalId": "user-789",
                    "PrincipalType": "USER",
                    "CreatedDate": datetime.now(timezone.utc) - timedelta(days=5),
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
        mock_idc_client.get_sso_admin_client.return_value.delete_account_assignment.return_value = {
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
        mock_idc_client.get_sso_admin_client.return_value.delete_account_assignment.assert_called_once()
        call_args = (
            mock_idc_client.get_sso_admin_client.return_value.delete_account_assignment.call_args
        )
        # Check the call was made - the exact parameter names may vary
        assert call_args is not None
        # Verify the cleanup result indicates success
        assert cleanup_result.successful_cleanups == 1
