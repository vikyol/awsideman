"""Tests for status cleanup command functionality."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from src.awsideman.commands.status import app
from src.awsideman.utils.status_models import (
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    PrincipalType,
    StatusLevel,
)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration with test profile."""
    with patch("src.awsideman.commands.status.helpers.config") as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {
            "default_profile": "test-profile",
            "profiles": {
                "test-profile": {
                    "sso_instance_arn": "arn:aws:sso:::instance/test-instance",
                    "identity_store_id": "test-identity-store",
                    "region": "us-east-1",
                }
            },
        }.get(key, default)
        yield mock_config


@pytest.fixture
def mock_aws_client():
    """Mock AWS client manager."""
    with patch("src.awsideman.commands.status.cleanup.AWSClientManager") as mock_client:
        yield mock_client


class TestCleanupOrphanedCommand:
    """Test the cleanup orphaned command."""

    @patch("src.awsideman.commands.status.cleanup.asyncio.run")
    @patch("src.awsideman.commands.status.cleanup.OrphanedAssignmentDetector")
    def test_cleanup_dry_run_no_orphans(
        self, mock_detector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test cleanup dry run with no orphaned assignments."""
        # Setup mocks
        mock_detector_instance = Mock()
        mock_detector.return_value = mock_detector_instance

        detection_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="No orphaned assignments",
            orphaned_assignments=[],
            cleanup_available=False,
        )

        mock_asyncio_run.return_value = detection_result

        # Run command (dry run is default)
        result = runner.invoke(app, ["cleanup"])

        # Verify success
        assert result.exit_code == 0
        assert "No orphaned assignments found" in result.stdout
        mock_detector.assert_called_once()

    @patch("src.awsideman.commands.status.cleanup.asyncio.run")
    @patch("src.awsideman.commands.status.cleanup.OrphanedAssignmentDetector")
    def test_cleanup_dry_run_with_orphans(
        self, mock_detector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test cleanup dry run with orphaned assignments found."""
        # Setup mocks
        mock_detector_instance = Mock()
        mock_detector.return_value = mock_detector_instance

        # Create sample orphaned assignment
        orphaned_assignment = OrphanedAssignment(
            assignment_id="test-assignment-1",
            permission_set_arn="arn:aws:sso:::permissionSet/test-ps",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
            account_name="Test Account",
            principal_id="test-user-id",
            principal_type=PrincipalType.USER,
            principal_name="deleted-user",
            error_message="User not found",
            created_date=datetime.now(timezone.utc),
        )
        orphaned_assignment.get_age_days = Mock(return_value=30)

        detection_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Found orphaned assignments",
            orphaned_assignments=[orphaned_assignment],
            cleanup_available=True,
        )

        mock_asyncio_run.return_value = detection_result

        # Run command (dry run is default)
        result = runner.invoke(app, ["cleanup"])

        # Verify success and dry run message
        assert result.exit_code == 0
        assert "Found 1 orphaned assignments" in result.stdout
        assert "This is a dry run" in result.stdout
        mock_detector.assert_called_once()

    @patch("src.awsideman.commands.status.cleanup.typer.confirm")
    @patch("src.awsideman.commands.status.cleanup.asyncio.run")
    @patch("src.awsideman.commands.status.cleanup.OrphanedAssignmentDetector")
    def test_cleanup_execute_with_confirmation(
        self, mock_detector, mock_asyncio_run, mock_confirm, runner, mock_config, mock_aws_client
    ):
        """Test cleanup execution with user confirmation."""
        # Setup mocks
        mock_detector_instance = Mock()
        mock_detector.return_value = mock_detector_instance
        mock_confirm.return_value = True  # User confirms cleanup

        # Create sample orphaned assignment
        orphaned_assignment = OrphanedAssignment(
            assignment_id="test-assignment-1",
            permission_set_arn="arn:aws:sso:::permissionSet/test-ps",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
            account_name="Test Account",
            principal_id="test-user-id",
            principal_type=PrincipalType.USER,
            principal_name="deleted-user",
            error_message="User not found",
            created_date=datetime.now(timezone.utc),
        )
        orphaned_assignment.get_age_days = Mock(return_value=30)

        detection_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Found orphaned assignments",
            orphaned_assignments=[orphaned_assignment],
            cleanup_available=True,
        )

        # Mock cleanup result
        cleanup_result = Mock()
        cleanup_result.cleaned_count = 1
        cleanup_result.failed_count = 0

        # Setup asyncio.run to return different results for detection and cleanup
        mock_asyncio_run.side_effect = [detection_result, cleanup_result]

        # Run command with execute flag
        result = runner.invoke(app, ["cleanup", "--execute"])

        # Verify success
        assert result.exit_code == 0
        assert "Successfully cleaned up 1 orphaned assignments" in result.stdout
        mock_confirm.assert_called_once()
        assert mock_asyncio_run.call_count == 2  # Detection + cleanup

    @patch("src.awsideman.commands.status.cleanup.typer.confirm")
    @patch("src.awsideman.commands.status.cleanup.asyncio.run")
    @patch("src.awsideman.commands.status.cleanup.OrphanedAssignmentDetector")
    def test_cleanup_execute_cancelled(
        self, mock_detector, mock_asyncio_run, mock_confirm, runner, mock_config, mock_aws_client
    ):
        """Test cleanup execution cancelled by user."""
        # Setup mocks
        mock_detector_instance = Mock()
        mock_detector.return_value = mock_detector_instance
        mock_confirm.return_value = False  # User cancels cleanup

        # Create sample orphaned assignment
        orphaned_assignment = OrphanedAssignment(
            assignment_id="test-assignment-1",
            permission_set_arn="arn:aws:sso:::permissionSet/test-ps",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
            account_name="Test Account",
            principal_id="test-user-id",
            principal_type=PrincipalType.USER,
            principal_name="deleted-user",
            error_message="User not found",
            created_date=datetime.now(timezone.utc),
        )
        orphaned_assignment.get_age_days = Mock(return_value=30)

        detection_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Found orphaned assignments",
            orphaned_assignments=[orphaned_assignment],
            cleanup_available=True,
        )

        mock_asyncio_run.return_value = detection_result

        # Run command with execute flag
        result = runner.invoke(app, ["cleanup", "--execute"])

        # Verify cancellation
        assert result.exit_code == 0
        assert "Cleanup cancelled" in result.stdout
        mock_confirm.assert_called_once()
        assert mock_asyncio_run.call_count == 1  # Only detection, no cleanup

    @patch("src.awsideman.commands.status.cleanup.asyncio.run")
    @patch("src.awsideman.commands.status.cleanup.OrphanedAssignmentDetector")
    def test_cleanup_execute_force(
        self, mock_detector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test cleanup execution with force flag (no confirmation)."""
        # Setup mocks
        mock_detector_instance = Mock()
        mock_detector.return_value = mock_detector_instance

        # Create sample orphaned assignment
        orphaned_assignment = OrphanedAssignment(
            assignment_id="test-assignment-1",
            permission_set_arn="arn:aws:sso:::permissionSet/test-ps",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
            account_name="Test Account",
            principal_id="test-user-id",
            principal_type=PrincipalType.USER,
            principal_name="deleted-user",
            error_message="User not found",
            created_date=datetime.now(timezone.utc),
        )
        orphaned_assignment.get_age_days = Mock(return_value=30)

        detection_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Found orphaned assignments",
            orphaned_assignments=[orphaned_assignment],
            cleanup_available=True,
        )

        # Mock cleanup result
        cleanup_result = Mock()
        cleanup_result.cleaned_count = 1
        cleanup_result.failed_count = 0

        # Setup asyncio.run to return different results for detection and cleanup
        mock_asyncio_run.side_effect = [detection_result, cleanup_result]

        # Run command with execute and force flags
        result = runner.invoke(app, ["cleanup", "--execute", "--force"])

        # Verify success without confirmation
        assert result.exit_code == 0
        assert "Successfully cleaned up 1 orphaned assignments" in result.stdout
        assert mock_asyncio_run.call_count == 2  # Detection + cleanup

    @patch("src.awsideman.commands.status.cleanup.asyncio.run")
    @patch("src.awsideman.commands.status.cleanup.OrphanedAssignmentDetector")
    def test_cleanup_aws_error(
        self, mock_detector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test cleanup with AWS API error."""
        # Setup mock to raise ClientError
        mock_asyncio_run.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="ListAccountAssignments",
        )

        result = runner.invoke(app, ["cleanup"])
        assert result.exit_code == 1
        assert "AWS Error (AccessDenied)" in result.stdout
