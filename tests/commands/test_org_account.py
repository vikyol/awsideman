"""Tests for the org account command."""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from typer.testing import CliRunner as TyperCliRunner

from src.awsideman.commands.org import app
from src.awsideman.utils.models import AccountDetails


@pytest.fixture
def mock_account_details():
    """Create mock account details for testing."""
    return AccountDetails(
        id="111111111111",
        name="test-account",
        email="test@example.com",
        status="ACTIVE",
        joined_timestamp=datetime(2021, 1, 1, 12, 0, 0),
        tags={"Environment": "Development", "Team": "Engineering"},
        ou_path=["Root", "Engineering", "Development"]
    )


@pytest.fixture
def mock_config():
    """Mock configuration."""
    with patch('src.awsideman.commands.org.config') as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {
            'default_profile': 'test-profile',
            'profiles': {
                'test-profile': {
                    'region': 'us-east-1',
                    'instance_arn': 'arn:aws:sso:::instance/ssoins-1234567890abcdef',
                    'identity_store_id': 'd-1234567890'
                }
            }
        }.get(key, default)
        yield mock_config


@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_account_command_table_format(mock_client_manager, mock_org_client, mock_get_account_details, mock_config, mock_account_details):
    """Test the account command with table format (default)."""
    # Setup mocks
    mock_get_account_details.return_value = mock_account_details
    
    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    
    # Verify the command executed successfully
    assert result.exit_code == 0
    
    # Verify the output contains expected elements
    assert "Account Details: test-account (111111111111)" in result.stdout
    assert "Account ID" in result.stdout
    assert "111111111111" in result.stdout
    assert "test-account" in result.stdout
    assert "test@example.com" in result.stdout
    assert "ACTIVE" in result.stdout
    assert "2021-01-01 12:00:00 UTC" in result.stdout
    assert "Root → Engineering → Development" in result.stdout
    assert "Environment=Development, Team=Engineering" in result.stdout


@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_account_command_json_format(mock_client_manager, mock_org_client, mock_get_account_details, mock_config, mock_account_details):
    """Test the account command with JSON format."""
    # Setup mocks
    mock_get_account_details.return_value = mock_account_details
    
    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "111111111111", "--json", "--profile", "test-profile"])
    
    # Verify the command executed successfully
    assert result.exit_code == 0
    
    # Verify the output is valid JSON and contains expected structure
    import json
    try:
        output_data = json.loads(result.stdout)
        assert output_data["id"] == "111111111111"
        assert output_data["name"] == "test-account"
        assert output_data["email"] == "test@example.com"
        assert output_data["status"] == "ACTIVE"
        assert output_data["joined_timestamp"] == "2021-01-01T12:00:00"
        assert output_data["tags"]["Environment"] == "Development"
        assert output_data["tags"]["Team"] == "Engineering"
        assert output_data["ou_path"] == ["Root", "Engineering", "Development"]
        
    except json.JSONDecodeError:
        pytest.fail("Output is not valid JSON")


def test_account_command_invalid_account_id_format():
    """Test the account command fails with invalid account ID format."""
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "invalid-id"])
    
    # Verify the command failed
    assert result.exit_code == 1
    assert "Invalid account ID format 'invalid-id'" in result.stdout
    # Check for the text across line breaks
    assert "12-digit" in result.stdout and "number" in result.stdout


def test_account_command_short_account_id():
    """Test the account command fails with short account ID."""
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "12345"])
    
    # Verify the command failed
    assert result.exit_code == 1
    assert "Invalid account ID format '12345'" in result.stdout


def test_account_command_long_account_id():
    """Test the account command fails with long account ID."""
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "1234567890123"])
    
    # Verify the command failed
    assert result.exit_code == 1
    assert "Invalid account ID format '1234567890123'" in result.stdout


def test_account_command_no_profile_error():
    """Test the account command fails when no profile is available."""
    # Mock config to return no default profile
    with patch('src.awsideman.commands.org.config') as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {
            'profiles': {}
        }.get(key, default)
        
        runner = TyperCliRunner()
        result = runner.invoke(app, ["account", "111111111111"])
        
        # Verify the command failed
        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout


def test_account_command_invalid_profile_error():
    """Test the account command fails when an invalid profile is specified."""
    with patch('src.awsideman.commands.org.config') as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {
            'default_profile': 'test-profile',
            'profiles': {
                'test-profile': {
                    'region': 'us-east-1',
                    'instance_arn': 'arn:aws:sso:::instance/ssoins-1234567890abcdef',
                    'identity_store_id': 'd-1234567890'
                }
            }
        }.get(key, default)
        
        runner = TyperCliRunner()
        result = runner.invoke(app, ["account", "111111111111", "--profile", "nonexistent-profile"])
        
        # Verify the command failed
        assert result.exit_code == 1
        assert "Profile 'nonexistent-profile' does not exist" in result.stdout


@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_account_command_account_not_found(mock_client_manager, mock_org_client, mock_get_account_details, mock_config):
    """Test the account command handles account not found error."""
    # Setup mocks to raise an exception
    mock_get_account_details.side_effect = Exception("Account 999999999999 not found")
    
    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "999999999999", "--profile", "test-profile"])
    
    # Verify the command failed
    assert result.exit_code == 1
    assert "Account 999999999999 not found" in result.stdout


@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_account_command_no_tags(mock_client_manager, mock_org_client, mock_get_account_details, mock_config):
    """Test the account command with an account that has no tags."""
    # Create account details without tags
    account_details = AccountDetails(
        id="111111111111",
        name="test-account",
        email="test@example.com",
        status="ACTIVE",
        joined_timestamp=datetime(2021, 1, 1, 12, 0, 0),
        tags={},
        ou_path=["Root"]
    )
    
    # Setup mocks
    mock_get_account_details.return_value = account_details
    
    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    
    # Verify the command executed successfully
    assert result.exit_code == 0
    
    # Verify the output shows "None" for tags
    assert "Tags" in result.stdout
    assert "None" in result.stdout


@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_account_command_empty_ou_path(mock_client_manager, mock_org_client, mock_get_account_details, mock_config):
    """Test the account command with an account that has empty OU path."""
    # Create account details with empty OU path
    account_details = AccountDetails(
        id="111111111111",
        name="test-account",
        email="test@example.com",
        status="ACTIVE",
        joined_timestamp=datetime(2021, 1, 1, 12, 0, 0),
        tags={},
        ou_path=[]
    )
    
    # Setup mocks
    mock_get_account_details.return_value = account_details
    
    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    
    # Verify the command executed successfully
    assert result.exit_code == 0
    
    # Verify the output shows "Root" for empty OU path
    assert "OU Path" in result.stdout
    assert "Root" in result.stdout