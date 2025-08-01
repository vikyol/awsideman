"""
Unit tests for PolicyResolver class.

Tests the policy aggregation logic, hierarchy traversal, and policy status determination
for both Service Control Policies (SCPs) and Resource Control Policies (RCPs).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from src.awsideman.utils.aws_client import PolicyResolver, OrganizationsClient
from src.awsideman.utils.models import (
    PolicyInfo, PolicyType, HierarchyPath, NodeType
)


class TestPolicyResolver:
    """Test PolicyResolver functionality."""

    @pytest.fixture
    def mock_organizations_client(self):
        """Create a mock OrganizationsClient for testing."""
        return Mock(spec=OrganizationsClient)

    @pytest.fixture
    def policy_resolver(self, mock_organizations_client):
        """Create a PolicyResolver instance with mocked client."""
        return PolicyResolver(mock_organizations_client)

    def test_init(self, mock_organizations_client):
        """Test PolicyResolver initialization."""
        resolver = PolicyResolver(mock_organizations_client)
        assert resolver.organizations_client == mock_organizations_client

    def test_resolve_policies_for_account_success(self, policy_resolver, mock_organizations_client):
        """Test successful policy resolution for an account."""
        account_id = "111111111111"
        
        # Mock hierarchy path
        hierarchy_path = HierarchyPath(
            ids=["r-1234", "ou-5678", account_id],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT]
        )
        
        # Mock SCP policies
        scp_policies = [
            PolicyInfo(
                id="p-scp1",
                name="FullAccess",
                type=PolicyType.SERVICE_CONTROL_POLICY,
                description="Full access policy",
                aws_managed=True,
                attachment_point="r-1234",
                attachment_point_name="Root",
                effective_status="ENABLED"
            ),
            PolicyInfo(
                id="p-scp2",
                name="DenyHighRisk",
                type=PolicyType.SERVICE_CONTROL_POLICY,
                description="Deny high risk actions",
                aws_managed=False,
                attachment_point="ou-5678",
                attachment_point_name="Engineering",
                effective_status="ENABLED"
            )
        ]
        
        # Mock RCP policies
        rcp_policies = [
            PolicyInfo(
                id="p-rcp1",
                name="ResourceControl",
                type=PolicyType.RESOURCE_CONTROL_POLICY,
                description="Resource access control",
                aws_managed=False,
                attachment_point="ou-5678",
                attachment_point_name="Engineering",
                effective_status="ENABLED"
            )
        ]
        
        with patch.object(policy_resolver, '_get_hierarchy_path', return_value=hierarchy_path):
            with patch.object(policy_resolver, '_get_policies_for_target') as mock_get_policies:
                # Configure mock to return different policies for different calls
                mock_get_policies.side_effect = [
                    [scp_policies[0]],  # Root SCP
                    [],  # Root RCP (none)
                    [scp_policies[1]],  # OU SCP
                    [rcp_policies[0]],  # OU RCP
                    [],  # Account SCP (none)
                    []   # Account RCP (none)
                ]
                
                result = policy_resolver.resolve_policies_for_account(account_id)
                
                # Verify all policies are returned
                assert len(result) == 3
                assert scp_policies[0] in result
                assert scp_policies[1] in result
                assert rcp_policies[0] in result
                
                # Verify _get_policies_for_target was called correctly
                assert mock_get_policies.call_count == 6  # 2 policy types × 3 hierarchy levels
                
                # Verify calls for each hierarchy level and policy type
                calls = mock_get_policies.call_args_list
                assert calls[0][0] == ("r-1234", PolicyType.SERVICE_CONTROL_POLICY, "Root", NodeType.ROOT)
                assert calls[1][0] == ("r-1234", PolicyType.RESOURCE_CONTROL_POLICY, "Root", NodeType.ROOT)
                assert calls[2][0] == ("ou-5678", PolicyType.SERVICE_CONTROL_POLICY, "Engineering", NodeType.OU)
                assert calls[3][0] == ("ou-5678", PolicyType.RESOURCE_CONTROL_POLICY, "Engineering", NodeType.OU)
                assert calls[4][0] == (account_id, PolicyType.SERVICE_CONTROL_POLICY, "dev-account", NodeType.ACCOUNT)
                assert calls[5][0] == (account_id, PolicyType.RESOURCE_CONTROL_POLICY, "dev-account", NodeType.ACCOUNT)

    def test_resolve_policies_for_account_empty_hierarchy(self, policy_resolver):
        """Test policy resolution when hierarchy path is empty."""
        account_id = "111111111111"
        
        empty_hierarchy = HierarchyPath(ids=[], names=[], types=[])
        
        with patch.object(policy_resolver, '_get_hierarchy_path', return_value=empty_hierarchy):
            with pytest.raises(ValueError, match="Could not determine hierarchy path"):
                policy_resolver.resolve_policies_for_account(account_id)

    def test_resolve_policies_for_account_with_policy_errors(self, policy_resolver, mock_organizations_client):
        """Test policy resolution when some policy calls fail."""
        account_id = "111111111111"
        
        hierarchy_path = HierarchyPath(
            ids=["r-1234", "ou-5678"],
            names=["Root", "Engineering"],
            types=[NodeType.ROOT, NodeType.OU]
        )
        
        successful_policy = PolicyInfo(
            id="p-scp1",
            name="FullAccess",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Full access policy",
            aws_managed=True,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED"
        )
        
        with patch.object(policy_resolver, '_get_hierarchy_path', return_value=hierarchy_path):
            with patch.object(policy_resolver, '_get_policies_for_target') as mock_get_policies:
                # First call succeeds, second call fails, third succeeds, fourth fails
                mock_get_policies.side_effect = [
                    [successful_policy],  # Root SCP - success
                    Exception("API Error"),  # Root RCP - error
                    [],  # OU SCP - success (empty)
                    Exception("Another API Error")  # OU RCP - error
                ]
                
                # Should not raise exception, but continue processing
                result = policy_resolver.resolve_policies_for_account(account_id)
                
                # Should return the one successful policy
                assert len(result) == 1
                assert result[0] == successful_policy

    def test_resolve_policies_for_account_client_error(self, policy_resolver):
        """Test policy resolution when client error occurs."""
        account_id = "111111111111"
        
        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            operation_name='ListPoliciesForTarget'
        )
        
        with patch.object(policy_resolver, '_get_hierarchy_path', side_effect=client_error):
            with pytest.raises(ClientError):
                policy_resolver.resolve_policies_for_account(account_id)

    def test_get_hierarchy_path_success(self, policy_resolver, mock_organizations_client):
        """Test successful hierarchy path retrieval."""
        account_id = "111111111111"
        
        # Mock account details
        mock_organizations_client.describe_account.return_value = {
            'Id': account_id,
            'Name': 'dev-account'
        }
        
        # Mock parent hierarchy: account -> OU -> root
        # The implementation calls list_parents for account, then for OU, then for OU again to get grandparent
        mock_organizations_client.list_parents.side_effect = [
            [{'Id': 'ou-5678', 'Type': 'ORGANIZATIONAL_UNIT'}],  # Account's parent
            [{'Id': 'r-1234', 'Type': 'ROOT'}],  # OU's parent
            [{'Id': 'r-1234', 'Type': 'ROOT'}],  # OU's parent (called again to get grandparent for OU name lookup)
        ]
        
        # Mock root details
        mock_organizations_client.list_roots.return_value = [
            {'Id': 'r-1234', 'Name': 'Root'}
        ]
        
        # Mock OU details - called to get OU name
        mock_organizations_client.list_organizational_units_for_parent.return_value = [
            {'Id': 'ou-5678', 'Name': 'Engineering'}
        ]
        
        result = policy_resolver._get_hierarchy_path(account_id)
        
        # Path should be from root to account
        assert result.ids == ['r-1234', 'ou-5678', account_id]
        assert result.names == ['Root', 'Engineering', 'dev-account']
        assert result.types == [NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT]

    def test_get_hierarchy_path_account_directly_under_root(self, policy_resolver, mock_organizations_client):
        """Test hierarchy path for account directly under root."""
        account_id = "111111111111"
        
        # Mock account details
        mock_organizations_client.describe_account.return_value = {
            'Id': account_id,
            'Name': 'root-account'
        }
        
        # Mock parent hierarchy: account -> root
        mock_organizations_client.list_parents.side_effect = [
            [{'Id': 'r-1234', 'Type': 'ROOT'}],  # Account's parent is root
            []  # Root has no parent
        ]
        
        # Mock root details
        mock_organizations_client.list_roots.return_value = [
            {'Id': 'r-1234', 'Name': 'Root'}
        ]
        
        result = policy_resolver._get_hierarchy_path(account_id)
        
        # Path should be root -> account
        assert result.ids == ['r-1234', account_id]
        assert result.names == ['Root', 'root-account']
        assert result.types == [NodeType.ROOT, NodeType.ACCOUNT]

    def test_get_hierarchy_path_with_errors(self, policy_resolver, mock_organizations_client):
        """Test hierarchy path retrieval with API errors."""
        account_id = "111111111111"
        
        # Mock account describe failure
        mock_organizations_client.describe_account.side_effect = Exception("Account not found")
        
        # Mock parent hierarchy
        mock_organizations_client.list_parents.side_effect = [
            [{'Id': 'r-1234', 'Type': 'ROOT'}]
        ]
        
        # Mock root details
        mock_organizations_client.list_roots.return_value = [
            {'Id': 'r-1234', 'Name': 'Root'}
        ]
        
        result = policy_resolver._get_hierarchy_path(account_id)
        
        # Should still work but use account ID as name
        assert result.ids == ['r-1234', account_id]
        assert result.names == ['Root', account_id]
        assert result.types == [NodeType.ROOT, NodeType.ACCOUNT]

    def test_get_policies_for_target_scp_success(self, policy_resolver, mock_organizations_client):
        """Test successful SCP retrieval for a target."""
        target_id = "ou-1234"
        target_name = "Engineering"
        
        # Mock policy data from AWS API
        mock_policy_data = [
            {
                'Id': 'p-scp1',
                'Name': 'FullAccess',
                'Description': 'Full access policy',
                'AwsManaged': True
            },
            {
                'Id': 'p-scp2',
                'Name': 'DenyHighRisk',
                'Description': 'Deny high risk actions',
                'AwsManaged': False
            }
        ]
        
        mock_organizations_client.list_policies_for_target.return_value = mock_policy_data
        
        with patch.object(policy_resolver, '_determine_policy_status', return_value="ENABLED"):
            result = policy_resolver._get_policies_for_target(
                target_id, 
                PolicyType.SERVICE_CONTROL_POLICY,
                target_name,
                NodeType.OU
            )
        
        assert len(result) == 2
        
        # Verify first policy
        assert result[0].id == 'p-scp1'
        assert result[0].name == 'FullAccess'
        assert result[0].type == PolicyType.SERVICE_CONTROL_POLICY
        assert result[0].description == 'Full access policy'
        assert result[0].aws_managed is True
        assert result[0].attachment_point == target_id
        assert result[0].attachment_point_name == target_name
        assert result[0].effective_status == "ENABLED"
        
        # Verify second policy
        assert result[1].id == 'p-scp2'
        assert result[1].name == 'DenyHighRisk'
        assert result[1].type == PolicyType.SERVICE_CONTROL_POLICY
        assert result[1].aws_managed is False

    def test_get_policies_for_target_rcp_success(self, policy_resolver, mock_organizations_client):
        """Test successful RCP retrieval for a target."""
        target_id = "r-1234"
        target_name = "Root"
        
        mock_policy_data = [
            {
                'Id': 'p-rcp1',
                'Name': 'ResourceControl',
                'Description': 'Resource access control',
                'AwsManaged': False
            }
        ]
        
        mock_organizations_client.list_policies_for_target.return_value = mock_policy_data
        
        with patch.object(policy_resolver, '_determine_policy_status', return_value="CONDITIONAL"):
            result = policy_resolver._get_policies_for_target(
                target_id,
                PolicyType.RESOURCE_CONTROL_POLICY,
                target_name,
                NodeType.ROOT
            )
        
        assert len(result) == 1
        assert result[0].id == 'p-rcp1'
        assert result[0].name == 'ResourceControl'
        assert result[0].type == PolicyType.RESOURCE_CONTROL_POLICY
        assert result[0].effective_status == "CONDITIONAL"

    def test_get_policies_for_target_policy_type_not_enabled(self, policy_resolver, mock_organizations_client):
        """Test handling when policy type is not enabled for target."""
        target_id = "ou-1234"
        
        # Mock PolicyTypeNotEnabledException
        client_error = ClientError(
            error_response={'Error': {'Code': 'PolicyTypeNotEnabledException', 'Message': 'Policy type not enabled'}},
            operation_name='ListPoliciesForTarget'
        )
        
        mock_organizations_client.list_policies_for_target.side_effect = client_error
        
        result = policy_resolver._get_policies_for_target(
            target_id,
            PolicyType.RESOURCE_CONTROL_POLICY,
            "Engineering",
            NodeType.OU
        )
        
        # Should return empty list, not raise exception
        assert result == []

    def test_get_policies_for_target_other_client_error(self, policy_resolver, mock_organizations_client):
        """Test handling of other client errors."""
        target_id = "ou-1234"
        
        # Mock other client error
        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
            operation_name='ListPoliciesForTarget'
        )
        
        mock_organizations_client.list_policies_for_target.side_effect = client_error
        
        result = policy_resolver._get_policies_for_target(
            target_id,
            PolicyType.SERVICE_CONTROL_POLICY,
            "Engineering",
            NodeType.OU
        )
        
        # Should return empty list and log warning
        assert result == []

    def test_get_policies_for_target_malformed_policy_data(self, policy_resolver, mock_organizations_client):
        """Test handling of malformed policy data."""
        target_id = "ou-1234"
        
        # Mock malformed policy data (missing required fields)
        mock_policy_data = [
            {
                'Id': 'p-scp1',
                'Name': 'FullAccess'
                # Missing other fields
            },
            {
                # Missing Id field - will get empty string as default
                'Name': 'InvalidPolicy'
            }
        ]
        
        mock_organizations_client.list_policies_for_target.return_value = mock_policy_data
        
        with patch.object(policy_resolver, '_determine_policy_status', return_value="ENABLED"):
            result = policy_resolver._get_policies_for_target(
                target_id,
                PolicyType.SERVICE_CONTROL_POLICY,
                "Engineering",
                NodeType.OU
            )
        
        # Should process both policies, even with missing fields (using defaults)
        assert len(result) == 2
        assert result[0].id == 'p-scp1'
        assert result[0].name == 'FullAccess'
        assert result[0].description == ''  # Default value
        assert result[0].aws_managed is False  # Default value
        
        # Second policy with empty ID
        assert result[1].id == ''  # Default for missing Id
        assert result[1].name == 'InvalidPolicy'
        assert result[1].description == ''  # Default value
        assert result[1].aws_managed is False  # Default value

    def test_determine_policy_status_enabled_default(self, policy_resolver):
        """Test policy status determination - default enabled."""
        policy_data = {
            'Id': 'p-1234',
            'Name': 'TestPolicy'
        }
        
        result = policy_resolver._determine_policy_status(policy_data, NodeType.OU)
        assert result == "ENABLED"

    def test_determine_policy_status_conditional(self, policy_resolver):
        """Test policy status determination - conditional policy."""
        policy_data = {
            'Id': 'p-1234',
            'Name': 'TestPolicy',
            'Type': 'CONDITIONAL_POLICY'
        }
        
        result = policy_resolver._determine_policy_status(policy_data, NodeType.OU)
        assert result == "CONDITIONAL"

    def test_determine_policy_status_disabled(self, policy_resolver):
        """Test policy status determination - disabled policy."""
        policy_data = {
            'Id': 'p-1234',
            'Name': 'TestPolicy',
            'Status': 'DISABLED'
        }
        
        result = policy_resolver._determine_policy_status(policy_data, NodeType.OU)
        assert result == "DISABLED"

    def test_scp_vs_rcp_distinction(self, policy_resolver, mock_organizations_client):
        """Test that SCPs and RCPs are properly distinguished."""
        account_id = "111111111111"
        
        hierarchy_path = HierarchyPath(
            ids=["r-1234"],
            names=["Root"],
            types=[NodeType.ROOT]
        )
        
        # Create test policies of both types
        scp_policy = PolicyInfo(
            id="p-scp1",
            name="TestSCP",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Test SCP",
            aws_managed=True,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED"
        )
        
        rcp_policy = PolicyInfo(
            id="p-rcp1",
            name="TestRCP",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="Test RCP",
            aws_managed=False,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED"
        )
        
        with patch.object(policy_resolver, '_get_hierarchy_path', return_value=hierarchy_path):
            with patch.object(policy_resolver, '_get_policies_for_target') as mock_get_policies:
                # Return SCP for SCP call, RCP for RCP call
                mock_get_policies.side_effect = [
                    [scp_policy],  # SCP call
                    [rcp_policy]   # RCP call
                ]
                
                result = policy_resolver.resolve_policies_for_account(account_id)
                
                # Verify both policies are returned with correct types
                assert len(result) == 2
                
                scp_results = [p for p in result if p.is_scp()]
                rcp_results = [p for p in result if p.is_rcp()]
                
                assert len(scp_results) == 1
                assert len(rcp_results) == 1
                
                assert scp_results[0].type == PolicyType.SERVICE_CONTROL_POLICY
                assert rcp_results[0].type == PolicyType.RESOURCE_CONTROL_POLICY

    def test_policy_aggregation_across_hierarchy(self, policy_resolver, mock_organizations_client):
        """Test that policies are properly aggregated across the entire OU hierarchy."""
        account_id = "111111111111"
        
        # Create a deep hierarchy: Root -> OU1 -> OU2 -> Account
        hierarchy_path = HierarchyPath(
            ids=["r-1234", "ou-5678", "ou-9012", account_id],
            names=["Root", "Engineering", "DevTeam", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.OU, NodeType.ACCOUNT]
        )
        
        # Create policies at different levels
        root_scp = PolicyInfo(
            id="p-root-scp",
            name="RootSCP",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Root level SCP",
            aws_managed=True,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED"
        )
        
        ou1_scp = PolicyInfo(
            id="p-ou1-scp",
            name="OU1SCP",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="OU1 level SCP",
            aws_managed=False,
            attachment_point="ou-5678",
            attachment_point_name="Engineering",
            effective_status="ENABLED"
        )
        
        ou2_rcp = PolicyInfo(
            id="p-ou2-rcp",
            name="OU2RCP",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="OU2 level RCP",
            aws_managed=False,
            attachment_point="ou-9012",
            attachment_point_name="DevTeam",
            effective_status="CONDITIONAL"
        )
        
        account_scp = PolicyInfo(
            id="p-account-scp",
            name="AccountSCP",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Account level SCP",
            aws_managed=False,
            attachment_point=account_id,
            attachment_point_name="dev-account",
            effective_status="ENABLED"
        )
        
        with patch.object(policy_resolver, '_get_hierarchy_path', return_value=hierarchy_path):
            with patch.object(policy_resolver, '_get_policies_for_target') as mock_get_policies:
                # Configure mock to return policies at different levels
                mock_get_policies.side_effect = [
                    [root_scp],  # Root SCP
                    [],          # Root RCP (none)
                    [ou1_scp],   # OU1 SCP
                    [],          # OU1 RCP (none)
                    [],          # OU2 SCP (none)
                    [ou2_rcp],   # OU2 RCP
                    [account_scp], # Account SCP
                    []           # Account RCP (none)
                ]
                
                result = policy_resolver.resolve_policies_for_account(account_id)
                
                # Verify all policies from all levels are included
                assert len(result) == 4
                
                # Verify each policy is present
                policy_ids = [p.id for p in result]
                assert "p-root-scp" in policy_ids
                assert "p-ou1-scp" in policy_ids
                assert "p-ou2-rcp" in policy_ids
                assert "p-account-scp" in policy_ids
                
                # Verify attachment points are correct
                attachment_points = {p.id: p.attachment_point for p in result}
                assert attachment_points["p-root-scp"] == "r-1234"
                assert attachment_points["p-ou1-scp"] == "ou-5678"
                assert attachment_points["p-ou2-rcp"] == "ou-9012"
                assert attachment_points["p-account-scp"] == account_id
                
                # Verify policy types are preserved
                scp_count = len([p for p in result if p.is_scp()])
                rcp_count = len([p for p in result if p.is_rcp()])
                assert scp_count == 3
                assert rcp_count == 1

    def test_conditional_and_inherited_policies(self, policy_resolver, mock_organizations_client):
        """Test handling of conditional and inherited policies with different statuses."""
        account_id = "111111111111"
        
        hierarchy_path = HierarchyPath(
            ids=["r-1234", "ou-5678", account_id],
            names=["Root", "Engineering", "dev-account"],
            types=[NodeType.ROOT, NodeType.OU, NodeType.ACCOUNT]
        )
        
        # Create policies with different statuses
        enabled_policy = PolicyInfo(
            id="p-enabled",
            name="EnabledPolicy",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Always enabled policy",
            aws_managed=True,
            attachment_point="r-1234",
            attachment_point_name="Root",
            effective_status="ENABLED"
        )
        
        conditional_policy = PolicyInfo(
            id="p-conditional",
            name="ConditionalPolicy",
            type=PolicyType.RESOURCE_CONTROL_POLICY,
            description="Conditionally applied policy",
            aws_managed=False,
            attachment_point="ou-5678",
            attachment_point_name="Engineering",
            effective_status="CONDITIONAL"
        )
        
        disabled_policy = PolicyInfo(
            id="p-disabled",
            name="DisabledPolicy",
            type=PolicyType.SERVICE_CONTROL_POLICY,
            description="Disabled policy",
            aws_managed=False,
            attachment_point="ou-5678",
            attachment_point_name="Engineering",
            effective_status="DISABLED"
        )
        
        with patch.object(policy_resolver, '_get_hierarchy_path', return_value=hierarchy_path):
            with patch.object(policy_resolver, '_get_policies_for_target') as mock_get_policies:
                mock_get_policies.side_effect = [
                    [enabled_policy],     # Root SCP
                    [],                   # Root RCP
                    [disabled_policy],    # OU SCP
                    [conditional_policy], # OU RCP
                    [],                   # Account SCP
                    []                    # Account RCP
                ]
                
                result = policy_resolver.resolve_policies_for_account(account_id)
                
                # All policies should be returned regardless of status
                assert len(result) == 3
                
                # Verify statuses are preserved
                status_map = {p.id: p.effective_status for p in result}
                assert status_map["p-enabled"] == "ENABLED"
                assert status_map["p-conditional"] == "CONDITIONAL"
                assert status_map["p-disabled"] == "DISABLED"
                
                # Verify inheritance - policies from parent levels should be included
                attachment_points = {p.id: p.attachment_point for p in result}
                assert attachment_points["p-enabled"] == "r-1234"  # From root
                assert attachment_points["p-conditional"] == "ou-5678"  # From OU
                assert attachment_points["p-disabled"] == "ou-5678"  # From OU