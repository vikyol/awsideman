"""Integration tests for profile-specific cache configuration."""

from unittest.mock import Mock, patch

from src.awsideman.cache.config import AdvancedCacheConfig, ProfileCacheConfig
from src.awsideman.cache.utilities import create_aws_client_manager, get_profile_cache_config


class TestProfileCacheIntegration:
    """Test profile-specific cache configuration integration."""

    @patch("src.awsideman.cache.utilities.get_default_cache_config")
    def test_get_profile_cache_config_integration(self, mock_get_default):
        """Test that get_profile_cache_config returns profile-specific configuration."""
        # Mock the default config with profile-specific configs
        mock_config = Mock(spec=AdvancedCacheConfig)
        mock_config.profile_configs = {
            "prod": ProfileCacheConfig(
                profile_name="prod",
                backend_type="dynamodb",
                dynamodb_table_name="prod-cache-table",
                dynamodb_region="us-west-2",
            ),
            "dev": ProfileCacheConfig(
                profile_name="dev", backend_type="file", file_cache_dir="/tmp/dev-cache"
            ),
        }
        mock_get_default.return_value = mock_config

        # Test getting prod profile config
        prod_config = get_profile_cache_config("prod")
        assert prod_config.backend_type == "dynamodb"
        assert prod_config.dynamodb_table_name == "prod-cache-table"
        assert prod_config.dynamodb_region == "us-west-2"

        # Test getting dev profile config
        dev_config = get_profile_cache_config("dev")
        assert dev_config.backend_type == "file"
        assert dev_config.file_cache_dir == "/tmp/dev-cache"

        # Test getting non-existent profile (should return default)
        default_config = get_profile_cache_config("non-existent")
        assert default_config is mock_config

    @patch("src.awsideman.cache.utilities.get_profile_cache_config")
    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("boto3.Session")
    @patch("src.awsideman.cache.utilities.AWSClientManager")
    def test_create_aws_client_manager_with_profile(
        self,
        mock_client_manager_class,
        mock_boto3_session,
        mock_create_cache,
        mock_get_profile_config,
    ):
        """Test that create_aws_client_manager uses profile-specific cache configuration."""
        # Mock the profile-specific config with all required attributes
        mock_profile_config = Mock(spec=AdvancedCacheConfig)
        mock_profile_config.backend_type = "dynamodb"
        mock_profile_config.dynamodb_table_name = "profile-specific-table"
        mock_profile_config.operation_ttls = {}
        mock_profile_config.profile_configs = {}
        mock_profile_config.enabled = True
        mock_profile_config.default_ttl = 3600
        mock_profile_config.max_size_mb = 100
        mock_profile_config.encryption_enabled = False
        mock_profile_config.encryption_type = "none"
        mock_profile_config.dynamodb_region = None
        mock_profile_config.dynamodb_profile = None
        mock_profile_config.file_cache_dir = None
        mock_profile_config.hybrid_local_ttl = 300
        mock_profile_config.to_dict.return_value = {
            "backend_type": "dynamodb",
            "dynamodb_table_name": "profile-specific-table",
        }
        mock_get_profile_config.return_value = mock_profile_config

        # Mock the cache manager
        mock_cache_manager = Mock()
        mock_create_cache.return_value = mock_cache_manager

        # Mock the client manager
        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager

        # Create AWS client manager with profile
        _result = create_aws_client_manager(
            profile="prod", enable_caching=True, auto_configure_cache=True
        )

        # Verify that profile-specific config was requested
        mock_get_profile_config.assert_called_once_with("prod")

        # Verify that cache manager was created with profile-specific config
        mock_create_cache.assert_called_once_with(mock_profile_config, "prod")

        # Verify that client manager was created with cache manager
        mock_client_manager_class.assert_called_once_with(
            profile="prod",
            region=None,
            enable_caching=True,
            cache_manager=mock_cache_manager,
            cache_config=mock_profile_config.to_dict.return_value,
        )

    @patch("src.awsideman.cache.utilities.get_default_cache_config")
    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("boto3.Session")
    @patch("src.awsideman.cache.utilities.AWSClientManager")
    def test_create_aws_client_manager_without_profile(
        self, mock_client_manager_class, mock_boto3_session, mock_create_cache, mock_get_default
    ):
        """Test that create_aws_client_manager uses default config when no profile specified."""
        # Mock the default config with all required attributes
        mock_default_config = Mock(spec=AdvancedCacheConfig)
        mock_default_config.backend_type = "file"
        mock_default_config.operation_ttls = {}
        mock_default_config.profile_configs = {}
        mock_default_config.enabled = True
        mock_default_config.default_ttl = 3600
        mock_default_config.max_size_mb = 100
        mock_default_config.encryption_enabled = False
        mock_default_config.encryption_type = "none"
        mock_default_config.dynamodb_table_name = "awsideman-cache"
        mock_default_config.dynamodb_region = None
        mock_default_config.dynamodb_profile = None
        mock_default_config.file_cache_dir = None
        mock_default_config.hybrid_local_ttl = 300
        mock_default_config.to_dict.return_value = {"backend_type": "file"}
        mock_get_default.return_value = mock_default_config

        # Mock the cache manager
        mock_cache_manager = Mock()
        mock_create_cache.return_value = mock_cache_manager

        # Mock the client manager
        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager

        # Create AWS client manager without profile
        _result = create_aws_client_manager(enable_caching=True, auto_configure_cache=True)

        # Verify that default config was requested
        mock_get_default.assert_called_once()

        # Verify that cache manager was created with default config
        mock_create_cache.assert_called_once_with(mock_default_config, None)

        # Verify that client manager was created with cache manager
        mock_client_manager_class.assert_called_once_with(
            profile=None,
            region=None,
            enable_caching=True,
            cache_manager=mock_cache_manager,
            cache_config=mock_default_config.to_dict.return_value,
        )

    def test_profile_cache_config_serialization(self):
        """Test that ProfileCacheConfig can be serialized and deserialized."""
        # Create a profile config
        original_config = ProfileCacheConfig(
            profile_name="test-profile",
            backend_type="dynamodb",
            dynamodb_table_name="test-table",
            dynamodb_region="us-east-1",
            encryption_enabled=True,
            encryption_type="aes256",
            default_ttl=7200,
            max_size_mb=200,
            operation_ttls={"list_users": 3600, "list_groups": 7200},
        )

        # Convert to dict
        config_dict = original_config.to_dict()

        # Convert back to ProfileCacheConfig
        restored_config = ProfileCacheConfig.from_dict(config_dict)

        # Verify all attributes are preserved
        assert restored_config.profile_name == original_config.profile_name
        assert restored_config.backend_type == original_config.backend_type
        assert restored_config.dynamodb_table_name == original_config.dynamodb_table_name
        assert restored_config.dynamodb_region == original_config.dynamodb_region
        assert restored_config.encryption_enabled == original_config.encryption_enabled
        assert restored_config.encryption_type == original_config.encryption_type
        assert restored_config.default_ttl == original_config.default_ttl
        assert restored_config.max_size_mb == original_config.max_size_mb
        assert restored_config.operation_ttls == original_config.operation_ttls

    def test_advanced_cache_config_profile_integration(self):
        """Test that AdvancedCacheConfig properly integrates with profile configs."""
        # Create profile configs
        prod_config = ProfileCacheConfig(
            profile_name="prod", backend_type="dynamodb", dynamodb_table_name="prod-table"
        )

        dev_config = ProfileCacheConfig(
            profile_name="dev", backend_type="file", file_cache_dir="/tmp/dev"
        )

        # Create advanced config with profile configs
        advanced_config = AdvancedCacheConfig(
            backend_type="file",  # Default backend
            profile_configs={"prod": prod_config, "dev": dev_config},
        )

        # Test getting existing profile configs
        prod_result = advanced_config.get_profile_config("prod")
        assert prod_result is prod_config
        assert prod_result.backend_type == "dynamodb"

        dev_result = advanced_config.get_profile_config("dev")
        assert dev_result is dev_config
        assert dev_result.backend_type == "file"

        # Test getting non-existent profile (should return default-based config)
        default_result = advanced_config.get_profile_config("non-existent")
        assert default_result.profile_name == "non-existent"
        assert default_result.backend_type == "file"  # Uses default backend
        # The default config has a default DynamoDB table name, so it's not None
        assert default_result.dynamodb_table_name == "awsideman-cache"
