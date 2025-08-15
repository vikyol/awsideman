"""Tests for status check command functionality."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError
from typer.testing import CliRunner

from src.awsideman.commands.status import app
from src.awsideman.utils.status_models import (
    BaseStatusResult,
    HealthStatus,
    OrphanedAssignmentStatus,
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
    with patch("src.awsideman.commands.status.check.AWSClientManager") as mock_client:
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


class TestStatusCheckCommand:
    """Test the status check command."""

    @patch("src.awsideman.commands.status.check.asyncio.run")
    @patch("src.awsideman.commands.status.check.StatusOrchestrator")
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

    @patch("src.awsideman.commands.status.check.asyncio.run")
    @patch("src.awsideman.commands.status.check.StatusOrchestrator")
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
        with patch("src.awsideman.commands.status.helpers.config") as mock_config:
            mock_config.get.return_value = None

            result = runner.invoke(app, ["check"])
            assert result.exit_code == 1
            assert "No profile specified" in result.stdout

    def test_check_status_profile_not_found(self, runner):
        """Test status check with non-existent profile."""
        with patch("src.awsideman.commands.status.helpers.config") as mock_config:
            mock_config.get.side_effect = lambda key, default=None: {
                "default_profile": "nonexistent",
                "profiles": {},
            }.get(key, default)

            result = runner.invoke(app, ["check"])
            assert result.exit_code == 1
            assert "Profile 'nonexistent' does not exist" in result.stdout

    def test_check_status_no_sso_instance(self, runner):
        """Test status check with no SSO instance configured."""
        with patch("src.awsideman.commands.status.helpers.config") as mock_config:
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

    @patch("src.awsideman.commands.status.check.asyncio.run")
    @patch("src.awsideman.commands.status.check.StatusOrchestrator")
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

    @patch("src.awsideman.commands.status.check.asyncio.run")
    @patch("src.awsideman.commands.status.check.StatusOrchestrator")
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

    @patch("src.awsideman.commands.status.check.asyncio.run")
    @patch("src.awsideman.commands.status.check.StatusOrchestrator")
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

    @patch("src.awsideman.commands.status.check.asyncio.run")
    @patch("src.awsideman.commands.status.check.StatusOrchestrator")
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

    @patch("src.awsideman.commands.status.check.asyncio.run")
    @patch("src.awsideman.commands.status.check.StatusOrchestrator")
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
