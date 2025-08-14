"""Tests for status command functionality."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from src.awsideman.commands.status import app, validate_output_format, validate_status_type
from src.awsideman.utils.status_models import (
    BaseStatusResult,
    HealthStatus,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    OutputFormat,
    PrincipalType,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Mock configuration with test profile."""
    with patch("src.awsideman.commands.status.config") as mock_config:
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
    with patch("src.awsideman.commands.status.AWSClientManager") as mock_client:
        yield mock_client


@pytest.fixture
def sample_status_report():
    """Create a sample status report for testing."""
    timestamp = datetime.now(timezone.utc)

    health_status = HealthStatus(
        timestamp=timestamp,
        status=StatusLevel.HEALTHY,
        message="All systems operational",
        service_available=True,
        connectivity_status="Connected",
    )

    provisioning_status = ProvisioningStatus(
        timestamp=timestamp,
        status=StatusLevel.HEALTHY,
        message="No active operations",
        active_operations=[],
        failed_operations=[],
        completed_operations=[],
        pending_count=0,
    )

    orphaned_status = OrphanedAssignmentStatus(
        timestamp=timestamp,
        status=StatusLevel.HEALTHY,
        message="No orphaned assignments",
        orphaned_assignments=[],
        cleanup_available=False,
    )

    sync_status = SyncMonitorStatus(
        timestamp=timestamp,
        status=StatusLevel.HEALTHY,
        message="All providers synchronized",
        sync_providers=[],
        providers_configured=0,
        providers_healthy=0,
        providers_with_errors=0,
    )

    summary_stats = SummaryStatistics(
        total_users=100,
        total_groups=10,
        total_permission_sets=5,
        total_assignments=200,
        active_accounts=3,
        last_updated=timestamp,
    )

    return StatusReport(
        timestamp=timestamp,
        overall_health=health_status,
        provisioning_status=provisioning_status,
        orphaned_assignment_status=orphaned_status,
        sync_status=sync_status,
        summary_statistics=summary_stats,
        check_duration_seconds=2.5,
    )


class TestValidationFunctions:
    """Test validation helper functions."""

    def test_validate_output_format_valid_formats(self):
        """Test validation of valid output formats."""
        assert validate_output_format("json") == OutputFormat.JSON
        assert validate_output_format("JSON") == OutputFormat.JSON
        assert validate_output_format("csv") == OutputFormat.CSV
        assert validate_output_format("CSV") == OutputFormat.CSV
        assert validate_output_format("table") == OutputFormat.TABLE
        assert validate_output_format("TABLE") == OutputFormat.TABLE
        assert validate_output_format(None) == OutputFormat.TABLE

    def test_validate_output_format_invalid_format(self):
        """Test validation of invalid output format."""
        with pytest.raises((SystemExit, Exception)):
            validate_output_format("xml")

    def test_validate_status_type_valid_types(self):
        """Test validation of valid status types."""
        assert validate_status_type("health") == "health"
        assert validate_status_type("provisioning") == "provisioning"
        assert validate_status_type("orphaned") == "orphaned"
        assert validate_status_type("sync") == "sync"
        assert validate_status_type("resource") == "resource"
        assert validate_status_type("summary") == "summary"
        assert validate_status_type(None) is None

    def test_validate_status_type_invalid_type(self):
        """Test validation of invalid status type."""
        with pytest.raises((SystemExit, Exception)):
            validate_status_type("invalid")


class TestStatusCheckCommand:
    """Test the status check command."""

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.StatusOrchestrator")
    def test_check_status_comprehensive_success(
        self,
        mock_orchestrator,
        mock_asyncio_run,
        runner,
        mock_config,
        mock_aws_client,
        sample_status_report,
    ):
        """Test successful comprehensive status check."""
        # Setup mocks
        mock_orchestrator_instance = Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance
        mock_asyncio_run.return_value = sample_status_report

        # Run command
        result = runner.invoke(app, ["check"])

        # Verify success
        assert result.exit_code == 0
        mock_orchestrator.assert_called_once()
        mock_asyncio_run.assert_called_once()

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.StatusOrchestrator")
    def test_check_status_specific_type_success(
        self, mock_orchestrator, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test successful specific status type check."""
        # Setup mocks
        mock_orchestrator_instance = Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance

        specific_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Health check passed",
        )
        mock_asyncio_run.return_value = specific_result

        # Run command with specific type
        result = runner.invoke(app, ["check", "--type", "health"])

        # Verify success
        assert result.exit_code == 0
        mock_orchestrator.assert_called_once()
        mock_asyncio_run.assert_called_once()

    def test_check_status_invalid_format(self, runner, mock_config, mock_aws_client):
        """Test status check with invalid output format."""
        result = runner.invoke(app, ["check", "--format", "xml"])
        assert result.exit_code == 1
        assert "Invalid output format" in result.stdout

    def test_check_status_invalid_type(self, runner, mock_config, mock_aws_client):
        """Test status check with invalid status type."""
        result = runner.invoke(app, ["check", "--type", "invalid"])
        assert result.exit_code == 1
        assert "Invalid status type" in result.stdout

    def test_check_status_no_profile_configured(self, runner):
        """Test status check with no profile configured."""
        with patch("src.awsideman.commands.status.config") as mock_config:
            mock_config.get.return_value = None

            result = runner.invoke(app, ["check"])
            assert result.exit_code == 1
            assert "No profile specified" in result.stdout

    def test_check_status_profile_not_found(self, runner):
        """Test status check with non-existent profile."""
        with patch("src.awsideman.commands.status.config") as mock_config:
            mock_config.get.side_effect = lambda key, default=None: {
                "default_profile": "nonexistent",
                "profiles": {},
            }.get(key, default)

            result = runner.invoke(app, ["check"])
            assert result.exit_code == 1
            assert "Profile 'nonexistent' does not exist" in result.stdout

    def test_check_status_no_sso_instance(self, runner):
        """Test status check with no SSO instance configured."""
        with patch("src.awsideman.commands.status.config") as mock_config:
            mock_config.get.side_effect = lambda key, default=None: {
                "default_profile": "test-profile",
                "profiles": {
                    "test-profile": {
                        "region": "us-east-1"
                        # Missing sso_instance_arn and identity_store_id
                    }
                },
            }.get(key, default)

            result = runner.invoke(app, ["check"])
            assert result.exit_code == 1
            assert "No SSO instance configured" in result.stdout

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.StatusOrchestrator")
    def test_check_status_aws_error(
        self, mock_orchestrator, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test status check with AWS API error."""
        # Setup mock to raise ClientError
        mock_asyncio_run.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="DescribeInstance",
        )

        result = runner.invoke(app, ["check"])
        assert result.exit_code == 1
        assert "AWS Error (AccessDenied)" in result.stdout

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.StatusOrchestrator")
    def test_check_status_json_output(
        self,
        mock_orchestrator,
        mock_asyncio_run,
        runner,
        mock_config,
        mock_aws_client,
        sample_status_report,
    ):
        """Test status check with JSON output format."""
        # Setup mocks
        mock_orchestrator_instance = Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance
        mock_asyncio_run.return_value = sample_status_report

        # Run command with JSON format
        result = runner.invoke(app, ["check", "--format", "json"])

        # Verify success and JSON output
        assert result.exit_code == 0
        assert "timestamp" in result.stdout
        assert "overall_status" in result.stdout

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.StatusOrchestrator")
    def test_check_status_csv_output(
        self,
        mock_orchestrator,
        mock_asyncio_run,
        runner,
        mock_config,
        mock_aws_client,
        sample_status_report,
    ):
        """Test status check with CSV output format."""
        # Setup mocks
        mock_orchestrator_instance = Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance
        mock_asyncio_run.return_value = sample_status_report

        # Run command with CSV format
        result = runner.invoke(app, ["check", "--format", "csv"])

        # Verify success and CSV output
        assert result.exit_code == 0
        assert "# Status Summary" in result.stdout

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.StatusOrchestrator")
    def test_check_status_custom_timeout(
        self,
        mock_orchestrator,
        mock_asyncio_run,
        runner,
        mock_config,
        mock_aws_client,
        sample_status_report,
    ):
        """Test status check with custom timeout."""
        # Setup mocks
        mock_orchestrator_instance = Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance
        mock_asyncio_run.return_value = sample_status_report

        # Run command with custom timeout
        result = runner.invoke(app, ["check", "--timeout", "60"])

        # Verify success
        assert result.exit_code == 0

        # Verify StatusOrchestrator was called with correct config
        call_args = mock_orchestrator.call_args
        config_arg = call_args[0][1]  # Second argument is the config
        assert config_arg.timeout_seconds == 60

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.StatusOrchestrator")
    def test_check_status_sequential_mode(
        self,
        mock_orchestrator,
        mock_asyncio_run,
        runner,
        mock_config,
        mock_aws_client,
        sample_status_report,
    ):
        """Test status check with sequential execution mode."""
        # Setup mocks
        mock_orchestrator_instance = Mock()
        mock_orchestrator.return_value = mock_orchestrator_instance
        mock_asyncio_run.return_value = sample_status_report

        # Run command with sequential mode
        result = runner.invoke(app, ["check", "--sequential"])

        # Verify success
        assert result.exit_code == 0

        # Verify StatusOrchestrator was called with correct config
        call_args = mock_orchestrator.call_args
        config_arg = call_args[0][1]  # Second argument is the config
        assert config_arg.enable_parallel_checks is False


class TestInspectResourceCommand:
    """Test the inspect resource command."""

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.ResourceInspector")
    def test_inspect_user_success(
        self, mock_inspector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test successful user resource inspection."""
        # Setup mocks
        mock_inspector_instance = Mock()
        mock_inspector.return_value = mock_inspector_instance

        inspection_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="User found and healthy",
        )
        inspection_result.resource_found = Mock(return_value=True)
        inspection_result.has_suggestions = Mock(return_value=False)

        mock_asyncio_run.return_value = inspection_result

        # Run command
        result = runner.invoke(app, ["inspect", "user", "john.doe@example.com"])

        # Verify success
        assert result.exit_code == 0
        mock_inspector.assert_called_once()
        mock_asyncio_run.assert_called_once()

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.ResourceInspector")
    def test_inspect_group_success(
        self, mock_inspector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test successful group resource inspection."""
        # Setup mocks
        mock_inspector_instance = Mock()
        mock_inspector.return_value = mock_inspector_instance

        inspection_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Group found and healthy",
        )
        inspection_result.resource_found = Mock(return_value=True)
        inspection_result.has_suggestions = Mock(return_value=False)

        mock_asyncio_run.return_value = inspection_result

        # Run command
        result = runner.invoke(app, ["inspect", "group", "Administrators"])

        # Verify success
        assert result.exit_code == 0
        mock_inspector.assert_called_once()
        mock_asyncio_run.assert_called_once()

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.ResourceInspector")
    def test_inspect_permission_set_success(
        self, mock_inspector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test successful permission set resource inspection."""
        # Setup mocks
        mock_inspector_instance = Mock()
        mock_inspector.return_value = mock_inspector_instance

        inspection_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Permission set found and healthy",
        )
        inspection_result.resource_found = Mock(return_value=True)
        inspection_result.has_suggestions = Mock(return_value=False)

        mock_asyncio_run.return_value = inspection_result

        # Run command
        result = runner.invoke(app, ["inspect", "permission-set", "ReadOnlyAccess"])

        # Verify success
        assert result.exit_code == 0
        mock_inspector.assert_called_once()
        mock_asyncio_run.assert_called_once()

    def test_inspect_invalid_resource_type(self, runner, mock_config, mock_aws_client):
        """Test inspect with invalid resource type."""
        result = runner.invoke(app, ["inspect", "invalid", "test-id"])
        assert result.exit_code == 1
        assert "Invalid resource type" in result.stdout

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.ResourceInspector")
    def test_inspect_resource_not_found(
        self, mock_inspector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test inspect when resource is not found."""
        # Setup mocks
        mock_inspector_instance = Mock()
        mock_inspector.return_value = mock_inspector_instance

        inspection_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.CRITICAL,
            message="Resource not found",
        )
        inspection_result.resource_found = Mock(return_value=False)
        inspection_result.has_suggestions = Mock(return_value=True)
        inspection_result.similar_resources = ["similar-user-1", "similar-user-2"]

        mock_asyncio_run.return_value = inspection_result

        # Run command
        result = runner.invoke(app, ["inspect", "user", "nonexistent@example.com"])

        # Verify success (command succeeds even if resource not found)
        assert result.exit_code == 0
        assert "Similar Resources" in result.stdout

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.ResourceInspector")
    def test_inspect_json_output(
        self, mock_inspector, mock_asyncio_run, runner, mock_config, mock_aws_client
    ):
        """Test inspect with JSON output format."""
        # Setup mocks
        mock_inspector_instance = Mock()
        mock_inspector.return_value = mock_inspector_instance

        inspection_result = BaseStatusResult(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="User found and healthy",
        )
        inspection_result.resource_found = Mock(return_value=True)
        inspection_result.has_suggestions = Mock(return_value=False)

        mock_asyncio_run.return_value = inspection_result

        # Run command with JSON format
        result = runner.invoke(app, ["inspect", "user", "john.doe@example.com", "--format", "json"])

        # Verify success and JSON output
        assert result.exit_code == 0
        assert "timestamp" in result.stdout
        assert "status" in result.stdout


class TestCleanupOrphanedCommand:
    """Test the cleanup orphaned command."""

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.OrphanedAssignmentDetector")
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

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.OrphanedAssignmentDetector")
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

    @patch("src.awsideman.commands.status.typer.confirm")
    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.OrphanedAssignmentDetector")
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

    @patch("src.awsideman.commands.status.typer.confirm")
    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.OrphanedAssignmentDetector")
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

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.OrphanedAssignmentDetector")
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

    @patch("src.awsideman.commands.status.asyncio.run")
    @patch("src.awsideman.commands.status.OrphanedAssignmentDetector")
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


class TestCommandIntegration:
    """Test command integration and edge cases."""

    def test_app_help(self, runner):
        """Test that the app help displays correctly."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Monitor AWS Identity Center status and health" in result.stdout
        assert "check" in result.stdout
        assert "inspect" in result.stdout
        assert "cleanup" in result.stdout

    def test_check_command_help(self, runner):
        """Test that the check command help displays correctly."""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "Check AWS Identity Center status and health" in result.stdout
        assert "--format" in result.stdout
        assert "--type" in result.stdout
        assert "--timeout" in result.stdout
        assert "--parallel" in result.stdout

    def test_inspect_command_help(self, runner):
        """Test that the inspect command help displays correctly."""
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "Inspect detailed status of a specific resource" in result.stdout
        assert "resource_type" in result.stdout
        assert "resource_id" in result.stdout

    def test_cleanup_command_help(self, runner):
        """Test that the cleanup command help displays correctly."""
        result = runner.invoke(app, ["cleanup", "--help"])
        assert result.exit_code == 0
        assert "Clean up orphaned permission set assignments" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--force" in result.stdout
