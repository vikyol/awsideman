"""Tests for the org trace-policies command."""
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner as TyperCliRunner

from src.awsideman.commands.org import app
from src.awsideman.utils.models import PolicyInfo, PolicyType


@pytest.fixture
def mock_policies():
    """Create mock policy list for testing."""
    return [
        PolicyInfo(
            id="p-1234567890abcdef",
            name="FullAWSAccess",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Provides full access to AWS services",
            aws_managed=True,
            attachment_point="r-abcd",
            attachment_point_name="Root",
            effective_status="ENABLED",
        ),
        PolicyInfo(
            id="p-fedcba0987654321",
            name="DenyHighRiskActions",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Denies high-risk actions",
            aws_managed=False,
            attachment_point="ou-abcd-efgh1234",
            attachment_point_name="Engineering",
            effective_status="ENABLED",
        ),
        PolicyInfo(
            id="p-rcp123456789abc",
            name="ResourceAccessControl",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="Controls resource access",
            aws_managed=False,
            attachment_point="ou-abcd-efgh1234",
            attachment_point_name="Engineering",
            effective_status="CONDITIONAL",
        ),
    ]


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


@patch("src.awsideman.utils.aws_client.PolicyResolver")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_trace_policies_command_table_format(
    mock_client_manager, mock_org_client, mock_policy_resolver_class, mock_config, mock_policies
):
    """Test the trace-policies command with table format (default)."""
    # Setup mocks
    mock_policy_resolver = Mock()
    mock_policy_resolver.resolve_policies_for_account.return_value = mock_policies
    mock_policy_resolver._get_hierarchy_path.return_value = Mock(
        names=["Root", "Engineering", "test-account"]
    )
    mock_policy_resolver_class.return_value = mock_policy_resolver

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output contains expected elements
    assert "Policy Trace for Account: 111111111111" in result.stdout
    assert "Service Control Policies (SCPs):" in result.stdout
    assert "Resource Control Policies (RCPs):" in result.stdout
    assert "FullAWSAccess" in result.stdout
    assert "DenyHighRiskActions" in result.stdout
    assert "ResourceAccessCont" in result.stdout
    assert "Total policies affecting account 111111111111: 3" in result.stdout
    assert "Service Control Policies: 2" in result.stdout
    assert "Resource Control Policies: 1" in result.stdout


@patch("src.awsideman.utils.aws_client.PolicyResolver")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_trace_policies_command_json_format(
    mock_client_manager, mock_org_client, mock_policy_resolver_class, mock_config, mock_policies
):
    """Test the trace-policies command with JSON format."""
    # Setup mocks
    mock_policy_resolver = Mock()
    mock_policy_resolver.resolve_policies_for_account.return_value = mock_policies
    mock_policy_resolver_class.return_value = mock_policy_resolver

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(
        app, ["trace-policies", "111111111111", "--json", "--profile", "test-profile"]
    )

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output is valid JSON and contains expected structure
    import json

    try:
        output_data = json.loads(result.stdout)
        assert output_data["account_id"] == "111111111111"
        assert len(output_data["policies"]) == 3

        # Check first policy (SCP)
        scp_policy = output_data["policies"][0]
        assert scp_policy["id"] == "p-1234567890abcdef"
        assert scp_policy["name"] == "FullAWSAccess"
        assert scp_policy["type"] == "SERVICE_CONTROL_POLICY"
        assert scp_policy["aws_managed"] is True
        assert scp_policy["attachment_point"] == "r-abcd"
        assert scp_policy["attachment_point_name"] == "Root"
        assert scp_policy["effective_status"] == "ENABLED"

        # Check RCP policy
        rcp_policy = output_data["policies"][2]
        assert rcp_policy["type"] == "RESOURCE_CONTROL_POLICY"
        assert rcp_policy["effective_status"] == "CONDITIONAL"

    except json.JSONDecodeError:
        pytest.fail("Output is not valid JSON")


@patch("src.awsideman.utils.aws_client.PolicyResolver")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_trace_policies_command_no_policies(
    mock_client_manager, mock_org_client, mock_policy_resolver_class, mock_config
):
    """Test the trace-policies command when no policies are found."""
    # Setup mocks to return empty policy list
    mock_policy_resolver = Mock()
    mock_policy_resolver.resolve_policies_for_account.return_value = []
    mock_policy_resolver._get_hierarchy_path.return_value = Mock(names=["Root", "test-account"])
    mock_policy_resolver_class.return_value = mock_policy_resolver

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output shows no policies found
    assert "No policies found affecting account 111111111111" in result.stdout


def test_trace_policies_command_invalid_account_id_format():
    """Test the trace-policies command fails with invalid account ID format."""
    runner = TyperCliRunner()
    result = runner.invoke(app, ["trace-policies", "invalid-id"])

    # Verify the command failed
    assert result.exit_code == 1
    assert "Invalid account ID format 'invalid-id'" in result.stdout
    assert "12-digit" in result.stdout and "number" in result.stdout


def test_trace_policies_command_no_profile_error():
    """Test the trace-policies command fails when no profile is available."""
    # Mock config to return no default profile
    with patch("src.awsideman.commands.org.config") as mock_config:
        mock_config.get.side_effect = lambda key, default=None: {"profiles": {}}.get(key, default)

        runner = TyperCliRunner()
        result = runner.invoke(app, ["trace-policies", "111111111111"])

        # Verify the command failed
        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout


@patch("src.awsideman.utils.aws_client.PolicyResolver")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_trace_policies_command_policy_resolver_error(
    mock_client_manager, mock_org_client, mock_policy_resolver_class, mock_config
):
    """Test the trace-policies command handles policy resolver errors."""
    # Setup mocks to raise an exception
    mock_policy_resolver = Mock()
    mock_policy_resolver.resolve_policies_for_account.side_effect = Exception(
        "Failed to resolve policies"
    )
    mock_policy_resolver_class.return_value = mock_policy_resolver

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])

    # Verify the command failed
    assert result.exit_code == 1
    assert "Failed to resolve policies" in result.stdout


@patch("src.awsideman.utils.aws_client.PolicyResolver")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_trace_policies_command_only_scps(
    mock_client_manager, mock_org_client, mock_policy_resolver_class, mock_config
):
    """Test the trace-policies command with only SCPs."""
    # Create mock policies with only SCPs
    scp_only_policies = [
        PolicyInfo(
            id="p-1234567890abcdef",
            name="FullAWSAccess",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Provides full access to AWS services",
            aws_managed=True,
            attachment_point="r-abcd",
            attachment_point_name="Root",
            effective_status="ENABLED",
        )
    ]

    # Setup mocks
    mock_policy_resolver = Mock()
    mock_policy_resolver.resolve_policies_for_account.return_value = scp_only_policies
    mock_policy_resolver._get_hierarchy_path.return_value = Mock(names=["Root", "test-account"])
    mock_policy_resolver_class.return_value = mock_policy_resolver

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output contains SCPs but not RCPs section
    assert "Service Control Policies (SCPs):" in result.stdout
    assert "Resource Control Policies (RCPs):" not in result.stdout
    assert "Service Control Policies: 1" in result.stdout
    assert "Resource Control Policies:" not in result.stdout  # Should not show RCP count


@patch("src.awsideman.utils.aws_client.PolicyResolver")
@patch("src.awsideman.commands.org.OrganizationsClient")
@patch("src.awsideman.commands.org.AWSClientManager")
def test_trace_policies_command_only_rcps(
    mock_client_manager, mock_org_client, mock_policy_resolver_class, mock_config
):
    """Test the trace-policies command with only RCPs."""
    # Create mock policies with only RCPs
    rcp_only_policies = [
        PolicyInfo(
            id="p-rcp123456789abc",
            name="ResourceAccessControl",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="Controls resource access",
            aws_managed=False,
            attachment_point="ou-abcd-efgh1234",
            attachment_point_name="Engineering",
            effective_status="ENABLED",
        )
    ]

    # Setup mocks
    mock_policy_resolver = Mock()
    mock_policy_resolver.resolve_policies_for_account.return_value = rcp_only_policies
    mock_policy_resolver._get_hierarchy_path.return_value = Mock(
        names=["Root", "Engineering", "test-account"]
    )
    mock_policy_resolver_class.return_value = mock_policy_resolver

    # Run the command
    runner = TyperCliRunner()
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])

    # Verify the command executed successfully
    assert result.exit_code == 0

    # Verify the output contains RCPs but not SCPs section
    assert "Resource Control Policies (RCPs):" in result.stdout
    assert "Service Control Policies (SCPs):" not in result.stdout
    assert "Resource Control Policies: 1" in result.stdout
    assert "Service Control Policies:" not in result.stdout  # Should not show SCP count
