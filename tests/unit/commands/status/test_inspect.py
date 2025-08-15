"""Tests for status inspect command functionality."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.status import app
from src.awsideman.utils.status_models import BaseStatusResult, StatusLevel


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
    with patch("src.awsideman.commands.status.inspect.AWSClientManager") as mock_client:
        yield mock_client


class TestInspectResourceCommand:
    """Test the inspect resource command."""

    @patch("src.awsideman.commands.status.inspect.asyncio.run")
    @patch("src.awsideman.commands.status.inspect.ResourceInspector")
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

    @patch("src.awsideman.commands.status.inspect.asyncio.run")
    @patch("src.awsideman.commands.status.inspect.ResourceInspector")
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

    @patch("src.awsideman.commands.status.inspect.asyncio.run")
    @patch("src.awsideman.commands.status.inspect.ResourceInspector")
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

    @patch("src.awsideman.commands.status.inspect.asyncio.run")
    @patch("src.awsideman.commands.status.inspect.ResourceInspector")
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

    @patch("src.awsideman.commands.status.inspect.asyncio.run")
    @patch("src.awsideman.commands.status.inspect.ResourceInspector")
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
