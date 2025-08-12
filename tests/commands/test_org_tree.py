"""Tests for the org tree command."""
from unittest.mock import patch

import pytest
from typer.testing import CliRunner as TyperCliRunner

from src.awsideman.commands.org import app
from src.awsideman.utils.models import NodeType, OrgNode


@pytest.fixture
def mock_organization_tree():
    """Create a mock organization tree for testing."""
    # Create a simple organization structure
    root = OrgNode(id="r-1234567890", name="Root", type=NodeType.ROOT, children=[])

    # Add an OU
    ou = OrgNode(id="ou-1234567890-abcdefgh", name="Engineering", type=NodeType.OU, children=[])

    # Add accounts
    account1 = OrgNode(id="111111111111", name="dev-account", type=NodeType.ACCOUNT, children=[])

    account2 = OrgNode(id="222222222222", name="prod-account", type=NodeType.ACCOUNT, children=[])

    # Build the hierarchy
    ou.add_child(account1)
    ou.add_child(account2)
    root.add_child(ou)

    return [root]


@pytest.fixture
def mock_config():
    """Mock configuration."""
    with patch("src.awsideman.commands.org.config") as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {
            "default_profile": "test-profile",
            "profiles": {
                "test-profile": {
                    "region": "us-east-1",
                    "instance_arn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    "identity_store_id": "d-1234567890",
                }
            },
        }.get(key, default)
        yield mock_config


@patch("src.awsideman.commands.org.build_organization_hierarchy")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_tree_command_visual_format(
    mock_client_manager, mock_org_client, mock_build_hierarchy, mock_config, mock_organization_tree
):
    """Test the tree command with visual format (default)."""
    # Setup mocks
    mock_build_hierarchy.return_value = mock_organization_tree

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["tree", "--profile", "test-profile"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output contains expected elements
    assert "AWS Organization Structure" in result.stdout
    assert "Root: Root (r-1234567890)" in result.stdout
    assert "OU: Engineering (ou-1234567890-abcdefgh)" in result.stdout
    assert "Account: dev-account (111111111111)" in result.stdout
    assert "Account: prod-account (222222222222)" in result.stdout


@patch("src.awsideman.commands.org.build_organization_hierarchy")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_tree_command_flat_format(
    mock_client_manager, mock_org_client, mock_build_hierarchy, mock_config, mock_organization_tree
):
    """Test the tree command with flat format."""
    # Setup mocks
    mock_build_hierarchy.return_value = mock_organization_tree

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["tree", "--flat", "--profile", "test-profile"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output contains expected elements
    assert "AWS Organization Structure (Flat View)" in result.stdout
    assert "ROOT" in result.stdout
    assert "OU" in result.stdout
    assert "ACCOUNT" in result.stdout


@patch("src.awsideman.commands.org.build_organization_hierarchy")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_tree_command_json_format(
    mock_client_manager, mock_org_client, mock_build_hierarchy, mock_config, mock_organization_tree
):
    """Test the tree command with JSON format."""
    # Setup mocks
    mock_build_hierarchy.return_value = mock_organization_tree

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["tree", "--json", "--profile", "test-profile"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output is valid JSON and contains expected structure
    import json

    try:
        output_data = json.loads(result.stdout)
        assert isinstance(output_data, list)
        assert len(output_data) == 1

        root = output_data[0]
        assert root["id"] == "r-1234567890"
        assert root["name"] == "Root"
        assert root["type"] == "ROOT"
        assert len(root["children"]) == 1

        ou = root["children"][0]
        assert ou["id"] == "ou-1234567890-abcdefgh"
        assert ou["name"] == "Engineering"
        assert ou["type"] == "OU"
        assert len(ou["children"]) == 2

    except json.JSONDecodeError:
        pytest.fail("Output is not valid JSON")


def test_tree_command_no_profile_error(mock_config):
    """Test the tree command fails when no profile is available."""
    # Mock config to return no default profile
    with patch("src.awsideman.commands.org.config") as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {"profiles": {}}.get(key, default)

        runner = TyperCliRunner()
        result = runner.invoke(app, ["tree"])

        # Verify the command failed
        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout


def test_tree_command_invalid_profile_error(mock_config):
    """Test the tree command fails when an invalid profile is specified."""
    runner = TyperCliRunner()
    result = runner.invoke(app, ["tree", "--profile", "nonexistent-profile"])

    # Verify the command failed
    assert result.exit_code == 1
    assert "Profile 'nonexistent-profile' does not exist" in result.stdout
