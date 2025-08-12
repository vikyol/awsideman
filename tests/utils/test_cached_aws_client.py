"""Tests for cached AWS client functionality."""

from unittest.mock import Mock, patch

import pytest

from src.awsideman.aws_clients.cached_client import (
    CachedAwsClient,
    CachedOrganizationsClient,
    create_cached_client_manager,
)
from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.cache.manager import CacheManager
from src.awsideman.utils.models import CacheConfig


class TestCachedAwsClient:
    """Test cases for CachedAwsClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock(spec=AWSClientManager)
        self.mock_cache_manager = Mock(spec=CacheManager)
        self.cached_client = CachedAwsClient(self.mock_client_manager, self.mock_cache_manager)

    def test_init(self):
        """Test CachedAwsClient initialization."""
        assert self.cached_client.client_manager == self.mock_client_manager
        assert self.cached_client.cache_manager == self.mock_cache_manager

    def test_init_with_default_cache_manager(self):
        """Test CachedAwsClient initialization with default cache manager."""
        with patch("src.awsideman.aws_clients.cached_client.CacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance

            client = CachedAwsClient(self.mock_client_manager)

            assert client.client_manager == self.mock_client_manager
            mock_cache_class.assert_called_once()

    def test_generate_cache_key(self):
        """Test cache key generation."""
        # Set up client manager attributes
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-west-2"

        # Test basic key generation
        key1 = self.cached_client._generate_cache_key("list_roots", {})
        key2 = self.cached_client._generate_cache_key("list_roots", {})

        # Keys should be consistent
        assert key1 == key2
        assert key1.startswith("list_roots_")

        # Different operations should have different keys
        key3 = self.cached_client._generate_cache_key(
            "describe_account", {"account_id": "123456789012"}
        )
        assert key1 != key3

        # Different parameters should have different keys
        key4 = self.cached_client._generate_cache_key(
            "describe_account", {"account_id": "123456789013"}
        )
        assert key3 != key4

    def test_generate_cache_key_deterministic(self):
        """Test that cache key generation is deterministic."""
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-west-2"

        # Same parameters in different order should produce same key
        params1 = {"account_id": "123456789012", "parent_id": "ou-123"}
        params2 = {"parent_id": "ou-123", "account_id": "123456789012"}

        key1 = self.cached_client._generate_cache_key("test_operation", params1)
        key2 = self.cached_client._generate_cache_key("test_operation", params2)

        assert key1 == key2

    def test_generate_cache_key_with_complex_params(self):
        """Test cache key generation with complex parameters."""
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-west-2"

        complex_params = {
            "string_param": "test_value",
            "int_param": 42,
            "list_param": ["item1", "item2"],
            "dict_param": {"nested": "value"},
            "bool_param": True,
            "none_param": None,
        }

        # Should not raise exception
        key = self.cached_client._generate_cache_key("complex_operation", complex_params)
        assert key.startswith("complex_operation_")
        assert len(key) > len("complex_operation_")

    def test_generate_cache_key_includes_profile_and_region(self):
        """Test that cache keys include profile and region to avoid conflicts."""
        # Test with different profiles
        self.mock_client_manager.profile = "profile1"
        self.mock_client_manager.region = "us-east-1"
        key1 = self.cached_client._generate_cache_key("list_roots", {})

        self.mock_client_manager.profile = "profile2"
        self.mock_client_manager.region = "us-east-1"
        key2 = self.cached_client._generate_cache_key("list_roots", {})

        assert key1 != key2

        # Test with different regions
        self.mock_client_manager.profile = "profile1"
        self.mock_client_manager.region = "us-west-2"
        key3 = self.cached_client._generate_cache_key("list_roots", {})

        assert key1 != key3

    def test_generate_cache_key_with_none_profile(self):
        """Test cache key generation with None profile."""
        self.mock_client_manager.profile = None
        self.mock_client_manager.region = "us-east-1"

        key = self.cached_client._generate_cache_key("list_roots", {})
        assert key.startswith("list_roots_")

    def test_is_cacheable_operation(self):
        """Test cacheable operation detection."""
        # Test cacheable operations
        cacheable_ops = [
            "list_roots",
            "list_organizational_units_for_parent",
            "list_accounts_for_parent",
            "describe_account",
            "list_tags_for_resource",
            "list_policies_for_target",
            "list_parents",
        ]

        for op in cacheable_ops:
            assert self.cached_client._is_cacheable_operation(
                op
            ), f"Operation {op} should be cacheable"

        # Test non-cacheable operations
        non_cacheable_ops = [
            "create_account",
            "delete_account",
            "update_account",
            "move_account",
            "create_organizational_unit",
        ]

        for op in non_cacheable_ops:
            assert not self.cached_client._is_cacheable_operation(
                op
            ), f"Operation {op} should not be cacheable"

    def test_execute_with_cache_hit(self):
        """Test cache hit scenario."""
        # Set up cache hit
        cached_data = {"test": "data"}
        self.mock_cache_manager.get.return_value = cached_data

        # Mock API call that should not be executed
        api_call = Mock()

        result = self.cached_client._execute_with_cache("list_roots", {}, api_call)

        # Verify cache was checked and API call was not made
        self.mock_cache_manager.get.assert_called_once()
        api_call.assert_not_called()
        assert result == cached_data

    def test_execute_with_cache_miss(self):
        """Test cache miss scenario."""
        # Set up cache miss
        self.mock_cache_manager.get.return_value = None

        # Mock API call
        api_response = {"api": "response"}
        api_call = Mock(return_value=api_response)

        result = self.cached_client._execute_with_cache("list_roots", {}, api_call)

        # Verify cache was checked, API call was made, and result was cached
        self.mock_cache_manager.get.assert_called_once()
        api_call.assert_called_once()
        self.mock_cache_manager.set.assert_called_once()
        assert result == api_response

    def test_execute_with_cache_non_cacheable_operation(self):
        """Test non-cacheable operation bypasses cache."""
        # Mock API call
        api_response = {"api": "response"}
        api_call = Mock(return_value=api_response)

        result = self.cached_client._execute_with_cache("create_account", {}, api_call)

        # Verify cache was not checked and API call was made directly
        self.mock_cache_manager.get.assert_not_called()
        self.mock_cache_manager.set.assert_not_called()
        api_call.assert_called_once()
        assert result == api_response

    def test_execute_with_cache_api_error(self):
        """Test API error handling."""
        # Set up cache miss
        self.mock_cache_manager.get.return_value = None

        # Mock API call that raises an exception
        api_call = Mock(side_effect=Exception("API Error"))

        with pytest.raises(Exception, match="API Error"):
            self.cached_client._execute_with_cache("list_roots", {}, api_call)

        # Verify cache was checked but not set due to error
        self.mock_cache_manager.get.assert_called_once()
        self.mock_cache_manager.set.assert_not_called()

    def test_execute_with_cache_key_generation_error(self):
        """Test handling of cache key generation errors."""
        # Mock cache key generation to fail
        with patch.object(
            self.cached_client, "_generate_cache_key", side_effect=Exception("Key generation error")
        ):
            api_response = {"fallback": "response"}
            api_call = Mock(return_value=api_response)

            result = self.cached_client._execute_with_cache("list_roots", {}, api_call)

            # Should fall back to API call
            assert result == api_response
            api_call.assert_called_once()
            self.mock_cache_manager.get.assert_not_called()
            self.mock_cache_manager.set.assert_not_called()

    def test_execute_with_cache_retrieval_error(self):
        """Test handling of cache retrieval errors."""
        # Mock cache retrieval to fail
        self.mock_cache_manager.get.side_effect = Exception("Cache retrieval error")

        api_response = {"fallback": "response"}
        api_call = Mock(return_value=api_response)

        result = self.cached_client._execute_with_cache("list_roots", {}, api_call)

        # Should fall back to API call
        assert result == api_response
        api_call.assert_called_once()
        # Cache set should still be attempted
        self.mock_cache_manager.set.assert_called_once()

    def test_execute_with_cache_storage_error(self):
        """Test handling of cache storage errors."""
        # Set up cache miss
        self.mock_cache_manager.get.return_value = None
        # Mock cache storage to fail
        self.mock_cache_manager.set.side_effect = Exception("Cache storage error")

        api_response = {"api": "response"}
        api_call = Mock(return_value=api_response)

        # Should not raise exception even if caching fails
        result = self.cached_client._execute_with_cache("list_roots", {}, api_call)

        assert result == api_response
        api_call.assert_called_once()
        self.mock_cache_manager.set.assert_called_once()

    def test_get_organizations_client(self):
        """Test get_organizations_client method."""
        result = self.cached_client.get_organizations_client()

        assert isinstance(result, CachedOrganizationsClient)
        assert result.client_manager == self.mock_client_manager
        assert result.cache_manager == self.mock_cache_manager

    def test_get_identity_center_client(self):
        """Test get_identity_center_client method returns cached client."""
        from src.awsideman.aws_clients.cached_client import CachedIdentityCenterClient

        result = self.cached_client.get_identity_center_client()

        assert isinstance(result, CachedIdentityCenterClient)
        assert result.client_manager == self.mock_client_manager
        assert result.cache_manager == self.mock_cache_manager

    def test_get_identity_store_client(self):
        """Test get_identity_store_client method returns cached client."""
        from src.awsideman.aws_clients.cached_client import CachedIdentityStoreClient

        result = self.cached_client.get_identity_store_client()

        assert isinstance(result, CachedIdentityStoreClient)
        assert result.client_manager == self.mock_client_manager
        assert result.cache_manager == self.mock_cache_manager


class TestCachedOrganizationsClient:
    """Test cases for CachedOrganizationsClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock(spec=AWSClientManager)
        self.mock_cache_manager = Mock(spec=CacheManager)

        # Mock the underlying OrganizationsClientWrapper
        with patch(
            "src.awsideman.aws_clients.cached_client.OrganizationsClientWrapper"
        ) as mock_org_client_class:
            self.mock_org_client = Mock()
            mock_org_client_class.return_value = self.mock_org_client

            self.cached_org_client = CachedOrganizationsClient(
                self.mock_client_manager, self.mock_cache_manager
            )

    def test_init(self):
        """Test CachedOrganizationsClient initialization."""
        assert self.cached_org_client.client_manager == self.mock_client_manager
        assert self.cached_org_client.cache_manager == self.mock_cache_manager

    def test_client_property(self):
        """Test client property returns underlying client."""
        self.mock_org_client.client = Mock()
        assert self.cached_org_client.client == self.mock_org_client.client

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    def test_list_roots(self, mock_cached_aws_client_class):
        """Test list_roots method."""
        # Set up mocks
        mock_cached_aws_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_aws_client

        expected_result = [{"Id": "r-123", "Name": "Root"}]
        mock_cached_aws_client._execute_with_cache.return_value = expected_result

        # Create new instance to use the mocked CachedAwsClient
        cached_org_client = CachedOrganizationsClient(
            self.mock_client_manager, self.mock_cache_manager
        )

        result = cached_org_client.list_roots()

        # Verify the cached execution was called correctly
        mock_cached_aws_client._execute_with_cache.assert_called_once()
        call_args = mock_cached_aws_client._execute_with_cache.call_args
        assert call_args[0][0] == "list_roots"  # operation
        assert call_args[0][1] == {}  # params
        assert result == expected_result

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    def test_describe_account(self, mock_cached_aws_client_class):
        """Test describe_account method."""
        # Set up mocks
        mock_cached_aws_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_aws_client

        expected_result = {"Id": "123456789012", "Name": "Test Account"}
        mock_cached_aws_client._execute_with_cache.return_value = expected_result

        # Create new instance to use the mocked CachedAwsClient
        cached_org_client = CachedOrganizationsClient(
            self.mock_client_manager, self.mock_cache_manager
        )

        result = cached_org_client.describe_account("123456789012")

        # Verify the cached execution was called correctly
        mock_cached_aws_client._execute_with_cache.assert_called_once()
        call_args = mock_cached_aws_client._execute_with_cache.call_args
        assert call_args[0][0] == "describe_account"  # operation
        assert call_args[0][1] == {"account_id": "123456789012"}  # params
        assert result == expected_result

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    def test_list_organizational_units_for_parent(self, mock_cached_aws_client_class):
        """Test list_organizational_units_for_parent method."""
        mock_cached_aws_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_aws_client

        expected_result = [{"Id": "ou-123", "Name": "Test OU"}]
        mock_cached_aws_client._execute_with_cache.return_value = expected_result

        cached_org_client = CachedOrganizationsClient(
            self.mock_client_manager, self.mock_cache_manager
        )

        result = cached_org_client.list_organizational_units_for_parent("r-123")

        mock_cached_aws_client._execute_with_cache.assert_called_once()
        call_args = mock_cached_aws_client._execute_with_cache.call_args
        assert call_args[0][0] == "list_organizational_units_for_parent"
        assert call_args[0][1] == {"parent_id": "r-123"}
        assert result == expected_result

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    def test_list_accounts_for_parent(self, mock_cached_aws_client_class):
        """Test list_accounts_for_parent method."""
        mock_cached_aws_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_aws_client

        expected_result = [{"Id": "123456789012", "Name": "Test Account"}]
        mock_cached_aws_client._execute_with_cache.return_value = expected_result

        cached_org_client = CachedOrganizationsClient(
            self.mock_client_manager, self.mock_cache_manager
        )

        result = cached_org_client.list_accounts_for_parent("ou-123")

        mock_cached_aws_client._execute_with_cache.assert_called_once()
        call_args = mock_cached_aws_client._execute_with_cache.call_args
        assert call_args[0][0] == "list_accounts_for_parent"
        assert call_args[0][1] == {"parent_id": "ou-123"}
        assert result == expected_result

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    def test_list_tags_for_resource(self, mock_cached_aws_client_class):
        """Test list_tags_for_resource method."""
        mock_cached_aws_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_aws_client

        expected_result = [{"Key": "Environment", "Value": "Production"}]
        mock_cached_aws_client._execute_with_cache.return_value = expected_result

        cached_org_client = CachedOrganizationsClient(
            self.mock_client_manager, self.mock_cache_manager
        )

        result = cached_org_client.list_tags_for_resource("123456789012")

        mock_cached_aws_client._execute_with_cache.assert_called_once()
        call_args = mock_cached_aws_client._execute_with_cache.call_args
        assert call_args[0][0] == "list_tags_for_resource"
        assert call_args[0][1] == {"resource_id": "123456789012"}
        assert result == expected_result

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    def test_list_policies_for_target(self, mock_cached_aws_client_class):
        """Test list_policies_for_target method."""
        mock_cached_aws_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_aws_client

        expected_result = [{"Id": "p-123", "Name": "Test Policy"}]
        mock_cached_aws_client._execute_with_cache.return_value = expected_result

        cached_org_client = CachedOrganizationsClient(
            self.mock_client_manager, self.mock_cache_manager
        )

        result = cached_org_client.list_policies_for_target("ou-123", "SERVICE_CONTROL_POLICY")

        mock_cached_aws_client._execute_with_cache.assert_called_once()
        call_args = mock_cached_aws_client._execute_with_cache.call_args
        assert call_args[0][0] == "list_policies_for_target"
        assert call_args[0][1] == {"target_id": "ou-123", "filter_type": "SERVICE_CONTROL_POLICY"}
        assert result == expected_result

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    def test_list_parents(self, mock_cached_aws_client_class):
        """Test list_parents method."""
        mock_cached_aws_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_aws_client

        expected_result = [{"Id": "ou-parent", "Type": "ORGANIZATIONAL_UNIT"}]
        mock_cached_aws_client._execute_with_cache.return_value = expected_result

        cached_org_client = CachedOrganizationsClient(
            self.mock_client_manager, self.mock_cache_manager
        )

        result = cached_org_client.list_parents("123456789012")

        mock_cached_aws_client._execute_with_cache.assert_called_once()
        call_args = mock_cached_aws_client._execute_with_cache.call_args
        assert call_args[0][0] == "list_parents"
        assert call_args[0][1] == {"child_id": "123456789012"}
        assert result == expected_result


class TestCreateCachedClientManager:
    """Test cases for create_cached_client_manager factory function."""

    @patch("src.awsideman.aws_clients.cached_client.AWSClientManager")
    @patch("src.awsideman.aws_clients.cached_client.CacheManager")
    def test_create_cached_client_manager(
        self, mock_cache_manager_class, mock_client_manager_class
    ):
        """Test factory function creates client correctly."""
        # Set up mocks
        mock_client_manager = Mock()
        mock_cache_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager
        mock_cache_manager_class.return_value = mock_cache_manager

        # Test with all parameters
        cache_config = CacheConfig(enabled=True, default_ttl=1800)
        result = create_cached_client_manager(
            profile="test-profile", region="us-west-2", cache_config=cache_config
        )

        # Verify correct initialization
        mock_client_manager_class.assert_called_once_with(
            profile="test-profile", region="us-west-2"
        )
        mock_cache_manager_class.assert_called_once_with(config=cache_config)

        assert isinstance(result, CachedAwsClient)
        assert result.client_manager == mock_client_manager
        assert result.cache_manager == mock_cache_manager

    @patch("src.awsideman.aws_clients.cached_client.AWSClientManager")
    @patch("src.awsideman.aws_clients.cached_client.CacheManager")
    def test_create_cached_client_manager_defaults(
        self, mock_cache_manager_class, mock_client_manager_class
    ):
        """Test factory function with default parameters."""
        # Set up mocks
        mock_client_manager = Mock()
        mock_cache_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager
        mock_cache_manager_class.return_value = mock_cache_manager

        result = create_cached_client_manager()

        # Verify correct initialization with defaults
        mock_client_manager_class.assert_called_once_with(profile=None, region=None)
        mock_cache_manager_class.assert_called_once_with(config=None)

        assert isinstance(result, CachedAwsClient)


class TestAWSClientManagerIntegration:
    """Test cases for AWSClientManager integration with caching."""

    @patch("src.awsideman.utils.aws_client.boto3.Session")
    def test_aws_client_manager_init_with_caching(self, mock_session):
        """Test AWSClientManager initialization with caching enabled."""
        mock_session.return_value = Mock()

        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is True
        assert client_manager._cached_client is None  # Lazy initialization

    @patch("src.awsideman.utils.aws_client.boto3.Session")
    def test_aws_client_manager_init_without_caching(self, mock_session):
        """Test AWSClientManager initialization with caching disabled."""
        mock_session.return_value = Mock()

        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        assert client_manager.enable_caching is False

    @patch("src.awsideman.aws_clients.cached_client.CachedAwsClient")
    @patch("src.awsideman.aws_clients.manager.boto3.Session")
    def test_get_cached_client(self, mock_session, mock_cached_aws_client_class):
        """Test get_cached_client method."""
        mock_session.return_value = Mock()
        mock_cached_client = Mock()
        mock_cached_aws_client_class.return_value = mock_cached_client

        client_manager = AWSClientManager(enable_caching=True)

        # First call should create the cached client
        result1 = client_manager.get_cached_client()
        assert result1 == mock_cached_client
        mock_cached_aws_client_class.assert_called_once_with(client_manager)

        # Second call should return the same instance
        result2 = client_manager.get_cached_client()
        assert result2 == mock_cached_client
        assert result1 is result2
        # Should not create a new instance
        assert mock_cached_aws_client_class.call_count == 1

    @patch("src.awsideman.aws_clients.manager.OrganizationsClientWrapper")
    def test_get_organizations_client_with_caching_enabled(self, mock_org_client_class):
        """Test get_organizations_client with caching enabled."""
        client_manager = AWSClientManager(enable_caching=True)

        # Mock the cached client
        mock_cached_client = Mock()
        mock_cached_org_client = Mock()
        mock_cached_client.get_organizations_client.return_value = mock_cached_org_client
        client_manager._cached_client = mock_cached_client

        result = client_manager.get_organizations_client()

        assert result == mock_cached_org_client
        mock_cached_client.get_organizations_client.assert_called_once()
        mock_org_client_class.assert_not_called()

    @patch("src.awsideman.aws_clients.manager.OrganizationsClientWrapper")
    def test_get_organizations_client_with_caching_disabled(self, mock_org_client_class):
        """Test get_organizations_client with caching disabled."""
        mock_org_client = Mock()
        mock_org_client_class.return_value = mock_org_client

        client_manager = AWSClientManager(enable_caching=False)

        result = client_manager.get_organizations_client()

        assert result == mock_org_client
        mock_org_client_class.assert_called_once_with(client_manager)


class TestCacheKeyGeneration:
    """Test cases specifically for cache key generation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock(spec=AWSClientManager)
        self.mock_cache_manager = Mock(spec=CacheManager)
        self.cached_client = CachedAwsClient(self.mock_client_manager, self.mock_cache_manager)

    def test_cache_key_consistency_across_calls(self):
        """Test that cache keys are consistent across multiple calls."""
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-east-1"

        params = {"account_id": "123456789012", "parent_id": "ou-123"}

        # Generate key multiple times
        keys = []
        for _ in range(10):
            key = self.cached_client._generate_cache_key("test_operation", params)
            keys.append(key)

        # All keys should be identical
        assert len(set(keys)) == 1

    def test_cache_key_uniqueness(self):
        """Test that different inputs produce different cache keys."""
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-east-1"

        test_cases = [
            ("operation1", {}),
            ("operation2", {}),
            ("operation1", {"param1": "value1"}),
            ("operation1", {"param1": "value2"}),
            ("operation1", {"param1": "value1", "param2": "value2"}),
        ]

        keys = []
        for operation, params in test_cases:
            key = self.cached_client._generate_cache_key(operation, params)
            keys.append(key)

        # All keys should be unique
        assert len(set(keys)) == len(keys)

    def test_cache_key_parameter_order_independence(self):
        """Test that parameter order doesn't affect cache key."""
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-east-1"

        params1 = {"a": 1, "b": 2, "c": 3}
        params2 = {"c": 3, "a": 1, "b": 2}
        params3 = {"b": 2, "c": 3, "a": 1}

        key1 = self.cached_client._generate_cache_key("test_op", params1)
        key2 = self.cached_client._generate_cache_key("test_op", params2)
        key3 = self.cached_client._generate_cache_key("test_op", params3)

        assert key1 == key2 == key3

    def test_cache_key_with_special_characters(self):
        """Test cache key generation with special characters in parameters."""
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-east-1"

        special_params = {
            "special_chars": "test@#$%^&*()_+-=[]{}|;:,.<>?",
            "unicode": "test_ñáéíóú_中文_🚀",
            "whitespace": "test with spaces\tand\nnewlines",
            "quotes": "test \"double\" and 'single' quotes",
        }

        # Should not raise exception
        key = self.cached_client._generate_cache_key("special_test", special_params)
        assert isinstance(key, str)
        assert len(key) > 0

    def test_cache_key_length_consistency(self):
        """Test that cache keys have consistent length regardless of input size."""
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-east-1"

        # Test with different sized inputs
        small_params = {"a": 1}
        large_params = {f"param_{i}": f"value_{i}" * 100 for i in range(50)}

        key1 = self.cached_client._generate_cache_key("test_op", small_params)
        key2 = self.cached_client._generate_cache_key("test_op", large_params)

        # Keys should have similar structure (operation prefix + hash)
        assert key1.startswith("test_op_")
        assert key2.startswith("test_op_")

        # Hash portions should have consistent length
        hash1 = key1.split("_", 2)[2]
        hash2 = key2.split("_", 2)[2]
        assert len(hash1) == len(hash2)


class TestCacheableOperations:
    """Test cases for cacheable operation detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock(spec=AWSClientManager)
        self.mock_cache_manager = Mock(spec=CacheManager)
        self.cached_client = CachedAwsClient(self.mock_client_manager, self.mock_cache_manager)

    def test_all_read_operations_are_cacheable(self):
        """Test that all expected read operations are marked as cacheable."""
        expected_cacheable = [
            "list_roots",
            "list_organizational_units_for_parent",
            "list_accounts_for_parent",
            "describe_account",
            "list_tags_for_resource",
            "list_policies_for_target",
            "list_parents",
            "list_instances",
            "list_permission_sets",
            "describe_permission_set",
            "list_accounts_for_provisioned_permission_set",
            "list_permission_sets_provisioned_to_account",
            "list_users",
            "list_groups",
            "describe_user",
            "describe_group",
            "list_group_memberships",
        ]

        for operation in expected_cacheable:
            assert self.cached_client._is_cacheable_operation(
                operation
            ), f"{operation} should be cacheable"

    def test_write_operations_are_not_cacheable(self):
        """Test that write operations are not marked as cacheable."""
        write_operations = [
            "create_account",
            "delete_account",
            "update_account",
            "move_account",
            "create_organizational_unit",
            "delete_organizational_unit",
            "update_organizational_unit",
            "attach_policy",
            "detach_policy",
            "create_policy",
            "delete_policy",
            "update_policy",
            "tag_resource",
            "untag_resource",
        ]

        for operation in write_operations:
            assert not self.cached_client._is_cacheable_operation(
                operation
            ), f"{operation} should not be cacheable"

    def test_unknown_operations_are_not_cacheable(self):
        """Test that unknown operations are not marked as cacheable."""
        unknown_operations = [
            "unknown_operation",
            "custom_operation",
            "test_operation",
            "",
            "list_unknown_resources",
        ]

        for operation in unknown_operations:
            assert not self.cached_client._is_cacheable_operation(
                operation
            ), f"{operation} should not be cacheable"


class TestCacheIntegrationScenarios:
    """Test cases for realistic cache integration scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock(spec=AWSClientManager)
        self.mock_client_manager.profile = "test-profile"
        self.mock_client_manager.region = "us-east-1"

        self.mock_cache_manager = Mock(spec=CacheManager)
        self.cached_client = CachedAwsClient(self.mock_client_manager, self.mock_cache_manager)

    def test_cache_hit_miss_sequence(self):
        """Test a sequence of cache hits and misses."""
        # First call - cache miss
        self.mock_cache_manager.get.return_value = None
        api_response = {"accounts": ["account1", "account2"]}
        api_call = Mock(return_value=api_response)

        result1 = self.cached_client._execute_with_cache(
            "list_accounts_for_parent", {"parent_id": "ou-123"}, api_call
        )

        assert result1 == api_response
        self.mock_cache_manager.get.assert_called_once()
        self.mock_cache_manager.set.assert_called_once()
        api_call.assert_called_once()

        # Reset mocks for second call
        self.mock_cache_manager.reset_mock()
        api_call.reset_mock()

        # Second call - cache hit
        self.mock_cache_manager.get.return_value = api_response

        result2 = self.cached_client._execute_with_cache(
            "list_accounts_for_parent", {"parent_id": "ou-123"}, api_call
        )

        assert result2 == api_response
        self.mock_cache_manager.get.assert_called_once()
        self.mock_cache_manager.set.assert_not_called()
        api_call.assert_not_called()

    def test_different_parameters_different_cache_keys(self):
        """Test that different parameters result in different cache operations."""
        self.mock_cache_manager.get.return_value = None

        # Call with first set of parameters
        api_call1 = Mock(return_value={"result": "first"})
        self.cached_client._execute_with_cache(
            "describe_account", {"account_id": "111111111111"}, api_call1
        )

        # Call with second set of parameters
        api_call2 = Mock(return_value={"result": "second"})
        self.cached_client._execute_with_cache(
            "describe_account", {"account_id": "222222222222"}, api_call2
        )

        # Both API calls should have been made (different cache keys)
        api_call1.assert_called_once()
        api_call2.assert_called_once()

        # Cache should have been checked twice with different keys
        assert self.mock_cache_manager.get.call_count == 2
        assert self.mock_cache_manager.set.call_count == 2

        # Verify different cache keys were used
        get_calls = self.mock_cache_manager.get.call_args_list
        set_calls = self.mock_cache_manager.set.call_args_list

        assert get_calls[0][0][0] != get_calls[1][0][0]  # Different cache keys
        assert set_calls[0][0][0] != set_calls[1][0][0]  # Different cache keys

    def test_profile_region_isolation(self):
        """Test that different profiles/regions use different cache keys."""
        self.mock_cache_manager.get.return_value = None
        api_call = Mock(return_value={"result": "test"})

        # First call with profile1/region1
        self.mock_client_manager.profile = "profile1"
        self.mock_client_manager.region = "us-east-1"
        self.cached_client._execute_with_cache("list_roots", {}, api_call)

        # Second call with profile2/region1
        self.mock_client_manager.profile = "profile2"
        self.mock_client_manager.region = "us-east-1"
        self.cached_client._execute_with_cache("list_roots", {}, api_call)

        # Third call with profile1/region2
        self.mock_client_manager.profile = "profile1"
        self.mock_client_manager.region = "us-west-2"
        self.cached_client._execute_with_cache("list_roots", {}, api_call)

        # All calls should result in different cache keys
        assert self.mock_cache_manager.get.call_count == 3
        assert self.mock_cache_manager.set.call_count == 3
        assert api_call.call_count == 3

        # Verify all cache keys are different
        get_calls = self.mock_cache_manager.get.call_args_list
        cache_keys = [call[0][0] for call in get_calls]
        assert len(set(cache_keys)) == 3  # All unique

    def test_error_resilience(self):
        """Test that cache errors don't break the API functionality."""
        # Test cache get error
        self.mock_cache_manager.get.side_effect = Exception("Cache get error")
        api_response = {"result": "success"}
        api_call = Mock(return_value=api_response)

        result = self.cached_client._execute_with_cache("list_roots", {}, api_call)

        assert result == api_response
        api_call.assert_called_once()

        # Reset for cache set error test
        self.mock_cache_manager.get.side_effect = None
        self.mock_cache_manager.get.return_value = None
        self.mock_cache_manager.set.side_effect = Exception("Cache set error")
        api_call.reset_mock()

        result = self.cached_client._execute_with_cache("list_roots", {}, api_call)

        assert result == api_response
        api_call.assert_called_once()
        # Cache set error should not prevent successful API response


class TestCachedOrganizationsClientIntegration:
    """Integration tests for CachedOrganizationsClient."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client_manager = Mock(spec=AWSClientManager)
        self.mock_cache_manager = Mock(spec=CacheManager)

        # Create a real CachedOrganizationsClient (not mocked)
        with patch(
            "src.awsideman.aws_clients.cached_client.OrganizationsClientWrapper"
        ) as mock_org_client_class:
            self.mock_org_client = Mock()
            mock_org_client_class.return_value = self.mock_org_client

            self.cached_org_client = CachedOrganizationsClient(
                self.mock_client_manager, self.mock_cache_manager
            )

    def test_all_methods_use_caching(self):
        """Test that all CachedOrganizationsClient methods use caching."""
        # Set up cache miss for all calls
        self.mock_cache_manager.get.return_value = None

        # Mock the underlying client methods
        self.mock_org_client.list_roots.return_value = [{"Id": "r-123"}]
        self.mock_org_client.list_organizational_units_for_parent.return_value = [{"Id": "ou-123"}]
        self.mock_org_client.list_accounts_for_parent.return_value = [{"Id": "123456789012"}]
        self.mock_org_client.describe_account.return_value = {"Id": "123456789012", "Name": "Test"}
        self.mock_org_client.list_tags_for_resource.return_value = [{"Key": "Env", "Value": "Test"}]
        self.mock_org_client.list_policies_for_target.return_value = [{"Id": "p-123"}]
        self.mock_org_client.list_parents.return_value = [{"Id": "ou-parent"}]

        # Call all methods
        methods_and_args = [
            ("list_roots", []),
            ("list_organizational_units_for_parent", ["ou-123"]),
            ("list_accounts_for_parent", ["ou-123"]),
            ("describe_account", ["123456789012"]),
            ("list_tags_for_resource", ["123456789012"]),
            ("list_policies_for_target", ["ou-123", "SERVICE_CONTROL_POLICY"]),
            ("list_parents", ["123456789012"]),
        ]

        for method_name, args in methods_and_args:
            method = getattr(self.cached_org_client, method_name)
            method(*args)

        # Verify cache was used for all calls
        assert self.mock_cache_manager.get.call_count == len(methods_and_args)
        assert self.mock_cache_manager.set.call_count == len(methods_and_args)

    def test_client_property_compatibility(self):
        """Test that client property maintains compatibility."""
        self.mock_org_client.client = Mock()

        # Should return the underlying client's client property
        result = self.cached_org_client.client
        assert result == self.mock_org_client.client
