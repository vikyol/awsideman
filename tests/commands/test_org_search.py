"""Tests for the org search command."""
from datetime import datetime
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.awsideman.commands.org import app
from src.awsideman.utils.models import AccountDetails


@pytest.fixture
def mock_config():
    """Mock configuration with test profile."""
    with patch("src.awsideman.commands.org.config") as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {
            "default_profile": "test-profile",
            "profiles": {
                "test-profile": {
                    "instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    "region": "us-east-1",
                }
            },
        }.get(key, default)
        yield mock_config


@pytest.fixture
def sample_account_details():
    """Sample account details for testing."""
    return [
        AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1),
            tags={"Environment": "Development", "Team": "Engineering"},
            ou_path=["Root", "Engineering", "Development"],
        ),
        AccountDetails(
            id="222222222222",
            name="prod-account",
            email="prod@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 2, 1),
            tags={"Environment": "Production", "Team": "Engineering"},
            ou_path=["Root", "Engineering", "Production"],
        ),
        AccountDetails(
            id="333333333333",
            name="test-account",
            email="test@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 3, 1),
            tags={"Environment": "Testing", "Team": "QA"},
            ou_path=["Root", "QA"],
        ),
    ]


def test_search_command_basic_functionality(mock_config, sample_account_details):
    """Test basic search functionality with table output."""
    runner = CliRunner()

    with patch("src.awsideman.utils.aws_client.search_accounts") as mock_search:
        # Mock the search function to return sample accounts
        mock_search.return_value = [sample_account_details[0]]  # Return dev-account

        result = runner.invoke(app, ["search", "dev"])

        assert result.exit_code == 0
        assert "dev-account" in result.output
        # Account ID might be truncated in table display
        assert "11111" in result.output  # Check for beginning of account ID
        assert "dev@example.com" in result.output
        # Check for OU path components
        assert "Root" in result.output
        assert "Engineering" in result.output
        assert "Development" in result.output
        assert "Found 1 account(s) matching 'dev'" in result.output
        mock_search.assert_called_once()


def test_search_command_json_output(mock_config, sample_account_details):
    """Test search command with JSON output format."""
    runner = CliRunner()

    with patch("src.awsideman.utils.aws_client.search_accounts") as mock_search:
        mock_search.return_value = [sample_account_details[0]]

        result = runner.invoke(app, ["search", "dev", "--json"])

        assert result.exit_code == 0
        assert '"id": "111111111111"' in result.output
        assert '"name": "dev-account"' in result.output
        assert '"email": "dev@example.com"' in result.output
        mock_search.assert_called_once()


def test_search_command_with_ou_filter(mock_config, sample_account_details):
    """Test search command with OU filter."""
    runner = CliRunner()

    with patch("src.awsideman.utils.aws_client.search_accounts") as mock_search:
        mock_search.return_value = [sample_account_details[0]]

        result = runner.invoke(app, ["search", "account", "--ou", "ou-engineering"])

        assert result.exit_code == 0
        # Verify that search_accounts was called with the OU filter
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[1]["ou_filter"] == "ou-engineering"


def test_search_command_with_tag_filter(mock_config, sample_account_details):
    """Test search command with tag filter."""
    runner = CliRunner()

    with patch("src.awsideman.utils.aws_client.search_accounts") as mock_search:
        mock_search.return_value = [sample_account_details[0]]

        result = runner.invoke(app, ["search", "account", "--tag", "Environment=Development"])

        assert result.exit_code == 0
        # Verify that search_accounts was called with the tag filter
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[1]["tag_filter"] == {"Environment": "Development"}


def test_search_command_invalid_tag_format(mock_config):
    """Test search command with invalid tag format."""
    runner = CliRunner()

    result = runner.invoke(app, ["search", "account", "--tag", "InvalidFormat"])

    assert result.exit_code == 1
    assert "Tag filter must be in format 'Key=Value'" in result.output


def test_search_command_no_results(mock_config):
    """Test search command when no accounts match."""
    runner = CliRunner()

    with patch("src.awsideman.utils.aws_client.search_accounts") as mock_search:
        mock_search.return_value = []

        result = runner.invoke(app, ["search", "nonexistent"])

        assert result.exit_code == 0
        assert "No accounts found matching 'nonexistent'" in result.output


def test_search_command_no_results_json(mock_config):
    """Test search command with JSON output when no accounts match."""
    runner = CliRunner()

    with patch("src.awsideman.utils.aws_client.search_accounts") as mock_search:
        mock_search.return_value = []

        result = runner.invoke(app, ["search", "nonexistent", "--json"])

        assert result.exit_code == 0
        assert result.output.strip() == "[]"


def test_search_command_multiple_results(mock_config, sample_account_details):
    """Test search command with multiple matching accounts."""
    runner = CliRunner()

    with patch("src.awsideman.utils.aws_client.search_accounts") as mock_search:
        # Return multiple accounts that match "account"
        mock_search.return_value = sample_account_details

        result = runner.invoke(app, ["search", "account"])

        assert result.exit_code == 0
        assert "dev-account" in result.output
        assert "prod-account" in result.output
        assert "test-account" in result.output
        assert "Found 3 account(s) matching 'account'" in result.output


def test_search_command_no_profile_error(mock_config):
    """Test search command with no profile configured."""
    runner = CliRunner()

    with patch("src.awsideman.commands.org.config") as mock_config_no_profile:
        mock_config_no_profile.get.side_effect = lambda key, default=None: {
            "default_profile": None,
            "profiles": {},
        }.get(key, default)

        result = runner.invoke(app, ["search", "test"])

        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.output


def test_search_command_invalid_profile_error(mock_config):
    """Test search command with invalid profile."""
    runner = CliRunner()

    result = runner.invoke(app, ["search", "test", "--profile", "nonexistent"])

    assert result.exit_code == 1
    assert "Profile 'nonexistent' does not exist" in result.output


def test_parse_tag_filter_valid():
    """Test _parse_tag_filter with valid input."""
    from src.awsideman.commands.org import _parse_tag_filter

    result = _parse_tag_filter("Environment=Production")
    assert result == {"Environment": "Production"}

    # Test with value containing equals sign
    result = _parse_tag_filter("URL=https://example.com")
    assert result == {"URL": "https://example.com"}


def test_parse_tag_filter_invalid():
    """Test _parse_tag_filter with invalid input."""
    from src.awsideman.commands.org import _parse_tag_filter

    with pytest.raises(ValueError, match="Tag filter must be in format 'Key=Value'"):
        _parse_tag_filter("InvalidFormat")

    with pytest.raises(ValueError, match="Tag filter must be in format 'Key=Value'"):
        _parse_tag_filter("")

    with pytest.raises(ValueError, match="Tag key cannot be empty"):
        _parse_tag_filter("=Value")
