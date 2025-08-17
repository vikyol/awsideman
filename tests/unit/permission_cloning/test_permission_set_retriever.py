"""
Unit tests for the PermissionSetRetriever class.

Tests core functionality for retrieving permission set configurations.
"""

from unittest.mock import Mock

import pytest

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.permission_cloning.permission_set_retriever import PermissionSetRetriever


class TestPermissionSetRetriever:
    """Test cases for PermissionSetRetriever class."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        return Mock(spec=AWSClientManager)

    @pytest.fixture
    def mock_sso_client(self):
        """Create a mock SSO Admin client."""
        return Mock()

    @pytest.fixture
    def permission_set_retriever(self, mock_client_manager):
        """Create a PermissionSetRetriever instance."""
        mock_client_manager.get_sso_admin_client.return_value = Mock()
        return PermissionSetRetriever(mock_client_manager, "arn:aws:sso:::instance/test")

    def test_init(self, permission_set_retriever, mock_client_manager):
        """Test PermissionSetRetriever initialization."""
        assert permission_set_retriever.client_manager == mock_client_manager
        assert permission_set_retriever.instance_arn == "arn:aws:sso:::instance/test"
        assert permission_set_retriever._permission_set_cache == {}

    def test_sso_admin_client_property(self, permission_set_retriever, mock_client_manager):
        """Test sso_admin_client property."""
        mock_sso_client = Mock()
        mock_client_manager.get_sso_admin_client.return_value = mock_sso_client

        client = permission_set_retriever.sso_admin_client

        assert client == mock_sso_client
        mock_client_manager.get_sso_admin_client.assert_called_once()

    def test_get_permission_set_config_success(self, permission_set_retriever, mock_client_manager):
        """Test successful permission set configuration retrieval."""
        mock_sso_client = Mock()
        mock_client_manager.get_sso_admin_client.return_value = mock_sso_client

        # Mock basic info response
        mock_sso_client.describe_permission_set.return_value = {
            "PermissionSet": {
                "Name": "TestPermissionSet",
                "Description": "Test Description",
                "SessionDuration": "PT2H",
                "RelayState": "https://example.com",
            }
        }

        # Mock managed policies response
        mock_sso_client.list_managed_policies_in_permission_set.return_value = {
            "AttachedManagedPolicies": [
                {"Type": "AWS_MANAGED", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"},
                {
                    "Type": "CUSTOMER_MANAGED",
                    "Arn": "arn:aws:iam::123456789012:policy/CustomPolicy",
                },
            ]
        }

        # Mock inline policy response
        mock_sso_client.get_inline_policy_for_permission_set.return_value = {
            "InlinePolicy": '{"Version": "2012-10-17", "Statement": []}'
        }

        config = permission_set_retriever.get_permission_set_config(
            "arn:aws:sso:::permissionSet/test"
        )

        assert config.name == "TestPermissionSet"
        assert config.description == "Test Description"
        assert config.session_duration == "PT2H"
        assert config.relay_state_url == "https://example.com"
        assert len(config.aws_managed_policies) == 1
        assert len(config.customer_managed_policies) == 1
        assert config.inline_policy is not None

    def test_get_permission_set_config_caching(self, permission_set_retriever, mock_client_manager):
        """Test that permission set configurations are cached."""
        mock_sso_client = Mock()
        mock_client_manager.get_sso_admin_client.return_value = mock_sso_client

        # Mock responses
        mock_sso_client.describe_permission_set.return_value = {
            "PermissionSet": {
                "Name": "TestPermissionSet",
                "Description": "Test Description",
                "SessionDuration": "PT1H",
            }
        }
        mock_sso_client.list_managed_policies_in_permission_set.return_value = {
            "AttachedManagedPolicies": []
        }
        mock_sso_client.get_inline_policy_for_permission_set.return_value = {}

        # First call should hit the API
        config1 = permission_set_retriever.get_permission_set_config(
            "arn:aws:sso:::permissionSet/test"
        )

        # Second call should use cache
        config2 = permission_set_retriever.get_permission_set_config(
            "arn:aws:sso:::permissionSet/test"
        )

        assert config1 == config2
        assert mock_sso_client.describe_permission_set.call_count == 1

    def test_clear_cache(self, permission_set_retriever):
        """Test cache clearing functionality."""
        # Populate cache
        permission_set_retriever._permission_set_cache["test"] = Mock()

        permission_set_retriever.clear_cache()

        assert len(permission_set_retriever._permission_set_cache) == 0

    def test_get_cache_stats(self, permission_set_retriever):
        """Test cache statistics retrieval."""
        # Populate cache
        permission_set_retriever._permission_set_cache["test1"] = Mock()
        permission_set_retriever._permission_set_cache["test2"] = Mock()

        stats = permission_set_retriever.get_cache_stats()

        assert stats["cached_permission_sets"] == 2
