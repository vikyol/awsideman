"""Integration tests for org commands.

This module contains integration tests that verify end-to-end org command workflows,
including tree -> account -> search -> trace-policies operations, integration with AWS APIs,
and real-world error scenarios.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError
import json
from datetime import datetime
from typer.testing import CliRunner as TyperCliRunner

from src.awsideman.commands.org import app
from src.awsideman.utils.models import OrgNode, NodeType, AccountDetails, PolicyInfo, PolicyType


@pytest.fixture
def mock_config():
    """Mock configuration with test profile."""
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


@pytest.fixture
def mock_organization_tree():
    """Create a comprehensive mock organization tree for testing."""
    # Create root
    root = OrgNode(
        id="r-1234567890",
        name="Root",
        type=NodeType.ROOT,
        children=[]
    )
    
    # Create OUs
    engineering_ou = OrgNode(
        id="ou-1234567890-engineering",
        name="Engineering",
        type=NodeType.OU,
        children=[]
    )
    
    production_ou = OrgNode(
        id="ou-1234567890-production",
        name="Production",
        type=NodeType.OU,
        children=[]
    )
    
    # Create accounts
    dev_account = OrgNode(
        id="111111111111",
        name="dev-account",
        type=NodeType.ACCOUNT,
        children=[]
    )
    
    staging_account = OrgNode(
        id="222222222222",
        name="staging-account",
        type=NodeType.ACCOUNT,
        children=[]
    )
    
    prod_account = OrgNode(
        id="333333333333",
        name="prod-account",
        type=NodeType.ACCOUNT,
        children=[]
    )
    
    # Build hierarchy
    engineering_ou.add_child(dev_account)
    engineering_ou.add_child(staging_account)
    production_ou.add_child(prod_account)
    root.add_child(engineering_ou)
    root.add_child(production_ou)
    
    return [root]


@pytest.fixture
def mock_account_details():
    """Create comprehensive mock account details."""
    return {
        "111111111111": AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, 12, 0, 0),
            tags={"Environment": "Development", "Team": "Engineering"},
            ou_path=["Root", "Engineering"]
        ),
        "222222222222": AccountDetails(
            id="222222222222",
            name="staging-account",
            email="staging@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 2, 1, 12, 0, 0),
            tags={"Environment": "Staging", "Team": "Engineering"},
            ou_path=["Root", "Engineering"]
        ),
        "333333333333": AccountDetails(
            id="333333333333",
            name="prod-account",
            email="prod@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 3, 1, 12, 0, 0),
            tags={"Environment": "Production", "Team": "Operations"},
            ou_path=["Root", "Production"]
        )
    }


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
            attachment_point="r-1234567890",
            attachment_point_name="Root",
            effective_status="ENABLED"
        ),
        PolicyInfo(
            id="p-fedcba0987654321",
            name="DenyHighRiskActions",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Denies high-risk actions",
            aws_managed=False,
            attachment_point="ou-1234567890-engineering",
            attachment_point_name="Engineering",
            effective_status="ENABLED"
        ),
        PolicyInfo(
            id="p-rcp123456789abc",
            name="ResourceAccessControl",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="Controls resource access",
            aws_managed=False,
            attachment_point="ou-1234567890-engineering",
            attachment_point_name="Engineering",
            effective_status="CONDITIONAL"
        )
    ]


@patch('src.awsideman.commands.org.build_organization_hierarchy')
@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.utils.aws_client.search_accounts')
@patch('src.awsideman.utils.aws_client.PolicyResolver')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_complete_org_workflow_table_format(
    mock_client_manager,
    mock_org_client,
    mock_policy_resolver_class,
    mock_search_accounts,
    mock_get_account_details,
    mock_build_hierarchy,
    mock_config,
    mock_organization_tree,
    mock_account_details,
    mock_policies
):
    """Test complete org workflow: tree -> account -> search -> trace-policies with table format."""
    # Setup mocks
    mock_build_hierarchy.return_value = mock_organization_tree
    mock_get_account_details.side_effect = lambda client, account_id: mock_account_details[account_id]
    mock_search_accounts.return_value = [mock_account_details["111111111111"]]
    
    mock_policy_resolver = MagicMock()
    mock_policy_resolver.resolve_policies_for_account.return_value = mock_policies
    mock_policy_resolver_class.return_value = mock_policy_resolver
    
    runner = TyperCliRunner()
    
    # Step 1: Display organization tree
    result = runner.invoke(app, ["tree", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "AWS Organization Structure" in result.stdout
    assert "Root: Root (r-1234567890)" in result.stdout
    assert "OU: Engineering (ou-1234567890-engineering)" in result.stdout
    assert "Account: dev-account (111111111111)" in result.stdout
    
    # Step 2: Get detailed account information
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "Account Details: dev-account (111111111111)" in result.stdout
    assert "dev@example.com" in result.stdout
    assert "Environment=Development, Team=Engineering" in result.stdout
    assert "Root → Engineering" in result.stdout
    
    # Step 3: Search for accounts
    result = runner.invoke(app, ["search", "dev", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "dev-account" in result.stdout
    assert "Found 1 account(s) matching 'dev'" in result.stdout
    
    # Step 4: Trace policies for the account
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "Policy Trace for Account: 111111111111" in result.stdout
    assert "Service Control Policies (SCPs):" in result.stdout
    assert "Resource Control Policies (RCPs):" in result.stdout
    assert "FullAWSAccess" in result.stdout
    assert "Total policies affecting account 111111111111: 3" in result.stdout
    
    # Verify all mocks were called appropriately
    mock_build_hierarchy.assert_called_once()
    mock_get_account_details.assert_called_once_with(mock_org_client.return_value, "111111111111")
    mock_search_accounts.assert_called_once()
    mock_policy_resolver.resolve_policies_for_account.assert_called_once_with("111111111111")


@patch('src.awsideman.commands.org.build_organization_hierarchy')
@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.utils.aws_client.search_accounts')
@patch('src.awsideman.utils.aws_client.PolicyResolver')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_complete_org_workflow_json_format(
    mock_client_manager,
    mock_org_client,
    mock_policy_resolver_class,
    mock_search_accounts,
    mock_get_account_details,
    mock_build_hierarchy,
    mock_config,
    mock_organization_tree,
    mock_account_details,
    mock_policies
):
    """Test complete org workflow with JSON output format."""
    # Setup mocks
    mock_build_hierarchy.return_value = mock_organization_tree
    mock_get_account_details.side_effect = lambda client, account_id: mock_account_details[account_id]
    mock_search_accounts.return_value = [mock_account_details["111111111111"]]
    
    mock_policy_resolver = MagicMock()
    mock_policy_resolver.resolve_policies_for_account.return_value = mock_policies
    mock_policy_resolver_class.return_value = mock_policy_resolver
    
    runner = TyperCliRunner()
    
    # Step 1: Display organization tree in JSON
    result = runner.invoke(app, ["tree", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    # Verify JSON output is valid and contains expected structure
    tree_data = json.loads(result.stdout)
    assert isinstance(tree_data, list)
    assert len(tree_data) == 1
    assert tree_data[0]["id"] == "r-1234567890"
    assert tree_data[0]["name"] == "Root"
    assert tree_data[0]["type"] == "ROOT"
    assert len(tree_data[0]["children"]) == 2  # Engineering and Production OUs
    
    # Step 2: Get account details in JSON
    result = runner.invoke(app, ["account", "111111111111", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    account_data = json.loads(result.stdout)
    assert account_data["id"] == "111111111111"
    assert account_data["name"] == "dev-account"
    assert account_data["email"] == "dev@example.com"
    assert account_data["tags"]["Environment"] == "Development"
    assert account_data["ou_path"] == ["Root", "Engineering"]
    
    # Step 3: Search accounts in JSON
    result = runner.invoke(app, ["search", "dev", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    search_data = json.loads(result.stdout)
    assert isinstance(search_data, list)
    assert len(search_data) == 1
    assert search_data[0]["id"] == "111111111111"
    assert search_data[0]["name"] == "dev-account"
    
    # Step 4: Trace policies in JSON
    result = runner.invoke(app, ["trace-policies", "111111111111", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    policies_data = json.loads(result.stdout)
    assert policies_data["account_id"] == "111111111111"
    assert len(policies_data["policies"]) == 3
    assert policies_data["policies"][0]["name"] == "FullAWSAccess"
    assert policies_data["policies"][0]["type"] == "SERVICE_CONTROL_POLICY"


@patch('src.awsideman.commands.org.build_organization_hierarchy')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_tree_command_various_formats(
    mock_client_manager,
    mock_org_client,
    mock_build_hierarchy,
    mock_config,
    mock_organization_tree
):
    """Test tree command with various output formats."""
    mock_build_hierarchy.return_value = mock_organization_tree
    runner = TyperCliRunner()
    
    # Test visual format (default)
    result = runner.invoke(app, ["tree", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "AWS Organization Structure" in result.stdout
    assert "Root: Root (r-1234567890)" in result.stdout
    
    # Test flat format
    result = runner.invoke(app, ["tree", "--flat", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "AWS Organization Structure (Flat View)" in result.stdout
    assert "ROOT" in result.stdout
    assert "OU" in result.stdout
    assert "ACCOUNT" in result.stdout
    
    # Test JSON format
    result = runner.invoke(app, ["tree", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    tree_data = json.loads(result.stdout)
    assert isinstance(tree_data, list)
    assert tree_data[0]["type"] == "ROOT"


@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_account_command_valid_and_invalid_ids(
    mock_client_manager,
    mock_org_client,
    mock_get_account_details,
    mock_config,
    mock_account_details
):
    """Test account command with valid and invalid account IDs."""
    mock_get_account_details.side_effect = lambda client, account_id: mock_account_details[account_id]
    runner = TyperCliRunner()
    
    # Test valid account ID
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "dev-account" in result.stdout
    assert "dev@example.com" in result.stdout
    
    # Test invalid account ID format (too short)
    result = runner.invoke(app, ["account", "12345"])
    assert result.exit_code == 1
    assert "Invalid account ID format '12345'" in result.stdout
    
    # Test invalid account ID format (too long)
    result = runner.invoke(app, ["account", "1234567890123"])
    assert result.exit_code == 1
    assert "Invalid account ID format '1234567890123'" in result.stdout
    
    # Test invalid account ID format (non-numeric)
    result = runner.invoke(app, ["account", "invalid-id"])
    assert result.exit_code == 1
    assert "Invalid account ID format 'invalid-id'" in result.stdout
    
    # Test account not found
    mock_get_account_details.side_effect = Exception("Account 999999999999 not found")
    result = runner.invoke(app, ["account", "999999999999", "--profile", "test-profile"])
    assert result.exit_code == 1
    assert "Account 999999999999 not found" in result.stdout


@patch('src.awsideman.utils.aws_client.search_accounts')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_search_command_patterns_and_filters(
    mock_client_manager,
    mock_org_client,
    mock_search_accounts,
    mock_config,
    mock_account_details
):
    """Test search command with different search patterns and filters."""
    runner = TyperCliRunner()
    
    # Test basic search
    mock_search_accounts.return_value = [mock_account_details["111111111111"]]
    result = runner.invoke(app, ["search", "dev", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "dev-account" in result.stdout
    assert "Found 1 account(s) matching 'dev'" in result.stdout
    
    # Test search with OU filter
    result = runner.invoke(app, ["search", "account", "--ou", "ou-engineering", "--profile", "test-profile"])
    assert result.exit_code == 0
    mock_search_accounts.assert_called_with(
        organizations_client=mock_org_client.return_value,
        query="account",
        ou_filter="ou-engineering",
        tag_filter=None
    )
    
    # Test search with tag filter
    result = runner.invoke(app, ["search", "account", "--tag", "Environment=Development", "--profile", "test-profile"])
    assert result.exit_code == 0
    mock_search_accounts.assert_called_with(
        organizations_client=mock_org_client.return_value,
        query="account",
        ou_filter=None,
        tag_filter={"Environment": "Development"}
    )
    
    # Test search with no results
    mock_search_accounts.return_value = []
    result = runner.invoke(app, ["search", "nonexistent", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "No accounts found matching 'nonexistent'" in result.stdout
    
    # Test search with invalid tag format
    result = runner.invoke(app, ["search", "account", "--tag", "InvalidFormat"])
    assert result.exit_code == 1
    assert "Tag filter must be in format 'Key=Value'" in result.stdout
    
    # Test search with multiple results
    mock_search_accounts.return_value = list(mock_account_details.values())
    result = runner.invoke(app, ["search", "account", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "Found 3 account(s) matching 'account'" in result.stdout


@patch('src.awsideman.utils.aws_client.PolicyResolver')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_trace_policies_command_inheritance_scenarios(
    mock_client_manager,
    mock_org_client,
    mock_policy_resolver_class,
    mock_config,
    mock_policies
):
    """Test trace-policies command with policy inheritance scenarios."""
    runner = TyperCliRunner()
    
    # Test with multiple policies (SCPs and RCPs)
    mock_policy_resolver = MagicMock()
    mock_policy_resolver.resolve_policies_for_account.return_value = mock_policies
    mock_policy_resolver_class.return_value = mock_policy_resolver
    
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "Policy Trace for Account: 111111111111" in result.stdout
    assert "Service Control Policies (SCPs):" in result.stdout
    assert "Resource Control Policies (RCPs):" in result.stdout
    assert "Total policies affecting account 111111111111: 3" in result.stdout
    
    # Test with only SCPs
    scp_only_policies = [p for p in mock_policies if p.is_scp()]
    mock_policy_resolver.resolve_policies_for_account.return_value = scp_only_policies
    
    result = runner.invoke(app, ["trace-policies", "222222222222", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "Service Control Policies (SCPs):" in result.stdout
    assert "Resource Control Policies (RCPs):" not in result.stdout
    
    # Test with only RCPs
    rcp_only_policies = [p for p in mock_policies if p.is_rcp()]
    mock_policy_resolver.resolve_policies_for_account.return_value = rcp_only_policies
    
    result = runner.invoke(app, ["trace-policies", "333333333333", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "Resource Control Policies (RCPs):" in result.stdout
    assert "Service Control Policies (SCPs):" not in result.stdout
    
    # Test with no policies
    mock_policy_resolver.resolve_policies_for_account.return_value = []
    
    result = runner.invoke(app, ["trace-policies", "444444444444", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "No policies found affecting account 444444444444" in result.stdout
    
    # Test with invalid account ID
    result = runner.invoke(app, ["trace-policies", "invalid-id"])
    assert result.exit_code == 1
    assert "Invalid account ID format 'invalid-id'" in result.stdout


def test_org_commands_profile_error_scenarios(mock_config):
    """Test org commands with various profile error scenarios."""
    runner = TyperCliRunner()
    
    # Test with no profile configured
    with patch('src.awsideman.commands.org.config') as mock_no_profile:
        mock_no_profile.get.side_effect = lambda key, default=None: {
            'profiles': {}
        }.get(key, default)
        
        # Test tree command
        result = runner.invoke(app, ["tree"])
        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout
        
        # Test account command
        result = runner.invoke(app, ["account", "111111111111"])
        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout
        
        # Test search command
        result = runner.invoke(app, ["search", "test"])
        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout
        
        # Test trace-policies command
        result = runner.invoke(app, ["trace-policies", "111111111111"])
        assert result.exit_code == 1
        assert "No profile specified and no default profile set" in result.stdout
    
    # Test with invalid profile
    for command_args in [
        ["tree", "--profile", "nonexistent"],
        ["account", "111111111111", "--profile", "nonexistent"],
        ["search", "test", "--profile", "nonexistent"],
        ["trace-policies", "111111111111", "--profile", "nonexistent"]
    ]:
        result = runner.invoke(app, command_args)
        assert result.exit_code == 1
        assert "Profile 'nonexistent' does not exist" in result.stdout


@patch('src.awsideman.commands.org.build_organization_hierarchy')
@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.utils.aws_client.search_accounts')
@patch('src.awsideman.utils.aws_client.PolicyResolver')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_org_commands_aws_api_error_handling(
    mock_client_manager,
    mock_org_client,
    mock_policy_resolver_class,
    mock_search_accounts,
    mock_get_account_details,
    mock_build_hierarchy,
    mock_config
):
    """Test org commands error handling for AWS API failures."""
    runner = TyperCliRunner()
    
    # Test tree command with AWS API error
    mock_build_hierarchy.side_effect = ClientError(
        error_response={'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
        operation_name='ListRoots'
    )
    
    result = runner.invoke(app, ["tree", "--profile", "test-profile"])
    assert result.exit_code == 1
    assert "Access denied" in result.stdout
    
    # Reset mock for next test
    mock_build_hierarchy.side_effect = None
    
    # Test account command with AWS API error
    mock_get_account_details.side_effect = ClientError(
        error_response={'Error': {'Code': 'AccountNotFound', 'Message': 'Account not found'}},
        operation_name='DescribeAccount'
    )
    
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 1
    assert "Account not found" in result.stdout
    
    # Reset mock for next test
    mock_get_account_details.side_effect = None
    
    # Test search command with AWS API error
    mock_search_accounts.side_effect = ClientError(
        error_response={'Error': {'Code': 'ServiceUnavailable', 'Message': 'Service unavailable'}},
        operation_name='ListAccounts'
    )
    
    result = runner.invoke(app, ["search", "test", "--profile", "test-profile"])
    assert result.exit_code == 1
    assert "Service unavailable" in result.stdout
    
    # Reset mock for next test
    mock_search_accounts.side_effect = None
    
    # Test trace-policies command with AWS API error
    mock_policy_resolver = MagicMock()
    mock_policy_resolver.resolve_policies_for_account.side_effect = ClientError(
        error_response={'Error': {'Code': 'PolicyNotFound', 'Message': 'Policy not found'}},
        operation_name='ListPoliciesForTarget'
    )
    mock_policy_resolver_class.return_value = mock_policy_resolver
    
    result = runner.invoke(app, ["trace-policies", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 1
    assert "Policy not found" in result.stdout


@patch('src.awsideman.commands.org.build_organization_hierarchy')
@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.utils.aws_client.search_accounts')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_org_commands_edge_cases(
    mock_client_manager,
    mock_org_client,
    mock_search_accounts,
    mock_get_account_details,
    mock_build_hierarchy,
    mock_config,
    mock_account_details
):
    """Test org commands with edge cases and boundary conditions."""
    runner = TyperCliRunner()
    
    # Test tree command with empty organization
    mock_build_hierarchy.return_value = []
    result = runner.invoke(app, ["tree", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    # Test account command with account that has no tags
    account_no_tags = AccountDetails(
        id="111111111111",
        name="test-account",
        email="test@example.com",
        status="ACTIVE",
        joined_timestamp=datetime(2021, 1, 1, 12, 0, 0),
        tags={},
        ou_path=["Root"]
    )
    mock_get_account_details.return_value = account_no_tags
    
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "Tags" in result.stdout
    assert "None" in result.stdout
    
    # Test account command with account that has empty OU path
    account_empty_path = AccountDetails(
        id="111111111111",
        name="test-account",
        email="test@example.com",
        status="ACTIVE",
        joined_timestamp=datetime(2021, 1, 1, 12, 0, 0),
        tags={},
        ou_path=[]
    )
    mock_get_account_details.return_value = account_empty_path
    
    result = runner.invoke(app, ["account", "111111111111", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "OU Path" in result.stdout
    assert "Root" in result.stdout
    
    # Test search command with special characters in query
    mock_search_accounts.return_value = []
    result = runner.invoke(app, ["search", "test@example.com", "--profile", "test-profile"])
    assert result.exit_code == 0
    assert "No accounts found matching 'test@example.com'" in result.stdout
    
    # Test search command with tag containing equals sign in value
    result = runner.invoke(app, ["search", "test", "--tag", "URL=https://example.com", "--profile", "test-profile"])
    assert result.exit_code == 0
    mock_search_accounts.assert_called_with(
        organizations_client=mock_org_client.return_value,
        query="test",
        ou_filter=None,
        tag_filter={"URL": "https://example.com"}
    )


@patch('src.awsideman.commands.org.build_organization_hierarchy')
@patch('src.awsideman.commands.org.get_account_details')
@patch('src.awsideman.utils.aws_client.search_accounts')
@patch('src.awsideman.utils.aws_client.PolicyResolver')
@patch('src.awsideman.commands.org.OrganizationsClient')
@patch('src.awsideman.commands.org.AWSClientManager')
def test_org_commands_performance_scenarios(
    mock_client_manager,
    mock_org_client,
    mock_policy_resolver_class,
    mock_search_accounts,
    mock_get_account_details,
    mock_build_hierarchy,
    mock_config,
    mock_organization_tree,
    mock_account_details,
    mock_policies
):
    """Test org commands with large datasets to verify performance handling."""
    # Setup mocks for large organization
    large_org_tree = []
    for i in range(10):  # 10 roots (unusual but possible)
        root = OrgNode(f"r-{i:010d}", f"Root-{i}", NodeType.ROOT, [])
        for j in range(5):  # 5 OUs per root
            ou = OrgNode(f"ou-{i:010d}-{j:010d}", f"OU-{i}-{j}", NodeType.OU, [])
            for k in range(20):  # 20 accounts per OU
                account = OrgNode(f"{i:03d}{j:03d}{k:06d}", f"account-{i}-{j}-{k}", NodeType.ACCOUNT, [])
                ou.add_child(account)
            root.add_child(ou)
        large_org_tree.append(root)
    
    mock_build_hierarchy.return_value = large_org_tree
    
    # Create large account details list
    large_account_list = []
    for i in range(100):  # 100 accounts
        account = AccountDetails(
            id=f"{i:012d}",
            name=f"account-{i}",
            email=f"account{i}@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, 12, 0, 0),
            tags={"Environment": f"env-{i % 5}", "Team": f"team-{i % 10}"},
            ou_path=["Root", f"OU-{i % 5}"]
        )
        large_account_list.append(account)
    
    mock_search_accounts.return_value = large_account_list
    mock_get_account_details.return_value = large_account_list[0]
    
    # Create large policy list
    large_policy_list = []
    for i in range(50):  # 50 policies
        policy = PolicyInfo(
            id=f"p-{i:016x}",
            name=f"Policy-{i}",
            type=PolicyType.SERVICE_CONTROL_POLICY if i % 2 == 0 else PolicyType.RESOURCE_CONTROL_POLICY,
            description=f"Policy {i} description",
            aws_managed=i % 3 == 0,
            attachment_point=f"ou-{i % 10:010d}-{i % 5:010d}",
            attachment_point_name=f"OU-{i % 10}-{i % 5}",
            effective_status="ENABLED"
        )
        large_policy_list.append(policy)
    
    mock_policy_resolver = MagicMock()
    mock_policy_resolver.resolve_policies_for_account.return_value = large_policy_list
    mock_policy_resolver_class.return_value = mock_policy_resolver
    
    runner = TyperCliRunner()
    
    # Test tree command with large organization (JSON format for easier verification)
    result = runner.invoke(app, ["tree", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    tree_data = json.loads(result.stdout)
    assert len(tree_data) == 10  # 10 roots
    
    # Test search command with large result set (JSON format)
    result = runner.invoke(app, ["search", "account", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    search_data = json.loads(result.stdout)
    assert len(search_data) == 100  # 100 accounts
    
    # Test trace-policies command with large policy set (JSON format)
    result = runner.invoke(app, ["trace-policies", "000000000000", "--json", "--profile", "test-profile"])
    assert result.exit_code == 0
    
    policies_data = json.loads(result.stdout)
    assert len(policies_data["policies"]) == 50  # 50 policies
    
    # Verify all commands completed successfully despite large datasets
    assert all(result.exit_code == 0 for result in [result])