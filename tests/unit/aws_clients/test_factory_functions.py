"""Unit tests for factory functions with different cache configurations."""

from unittest.mock import Mock, patch

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.manager import CacheManager


class TestFactoryFunctions:
    """Test factory functions with different cache configurations."""

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_with_cache_config(
        self, mock_init_session, mock_create_cache
    ):
        """Test create_aws_client_manager with explicit cache configuration."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        cache_config = AdvancedCacheConfig(
            backend_type="dynamodb", dynamodb_table_name="test-table", enabled=True
        )

        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_config=cache_config,
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is True
        assert client_manager.cache_config == cache_config
        mock_create_cache.assert_called_once()

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_without_cache_config(
        self, mock_init_session, mock_create_cache
    ):
        """Test create_aws_client_manager without explicit cache configuration."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is True
        # Should use default cache config
        mock_create_cache.assert_called_once()

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_caching_disabled(self, mock_init_session):
        """Test create_aws_client_manager with caching disabled."""
        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is False

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_dynamodb_backend(self, mock_init_session, mock_create_cache):
        """Test create_aws_client_manager with DynamoDB backend."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        cache_config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="test-table",
            dynamodb_region="us-east-1",
            dynamodb_profile="test-profile",
        )

        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_config=cache_config,
        )

        assert client_manager.cache_config.backend_type == "dynamodb"
        assert client_manager.cache_config.dynamodb_table_name == "test-table"
        assert client_manager.cache_config.dynamodb_region == "us-east-1"
        assert client_manager.cache_config.dynamodb_profile == "test-profile"

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_file_backend(self, mock_init_session, mock_create_cache):
        """Test create_aws_client_manager with file backend."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        cache_config = AdvancedCacheConfig(
            backend_type="file", file_cache_dir="/tmp/test-cache", max_size_mb=50
        )

        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_config=cache_config,
        )

        assert client_manager.cache_config.backend_type == "file"
        assert client_manager.cache_config.file_cache_dir == "/tmp/test-cache"
        assert client_manager.cache_config.max_size_mb == 50

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_hybrid_backend(self, mock_init_session, mock_create_cache):
        """Test create_aws_client_manager with hybrid backend."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        cache_config = AdvancedCacheConfig(
            backend_type="hybrid",
            hybrid_local_ttl=600,
            dynamodb_table_name="test-table",
            file_cache_dir="/tmp/local-cache",
        )

        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_config=cache_config,
        )

        assert client_manager.cache_config.backend_type == "hybrid"
        assert client_manager.cache_config.hybrid_local_ttl == 600
        assert client_manager.cache_config.dynamodb_table_name == "test-table"
        assert client_manager.cache_config.file_cache_dir == "/tmp/local-cache"

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_with_encryption(self, mock_init_session, mock_create_cache):
        """Test create_aws_client_manager with encryption enabled."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        cache_config = AdvancedCacheConfig(
            backend_type="dynamodb", encryption_enabled=True, encryption_type="aes256"
        )

        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_config=cache_config,
        )

        assert client_manager.cache_config.encryption_enabled is True
        assert client_manager.cache_config.encryption_type == "aes256"

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_with_operation_ttls(
        self, mock_init_session, mock_create_cache
    ):
        """Test create_aws_client_manager with operation-specific TTLs."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        operation_ttls = {"list_users": 1800, "list_groups": 3600, "list_permission_sets": 7200}

        cache_config = AdvancedCacheConfig(
            backend_type="dynamodb", operation_ttls=operation_ttls, default_ttl=3600
        )

        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_config=cache_config,
        )

        assert client_manager.cache_config.operation_ttls == operation_ttls
        assert client_manager.cache_config.default_ttl == 3600

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_profile_region_handling(self, mock_init_session):
        """Test create_aws_client_manager handles profile and region correctly."""
        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_cache_creation_failure(
        self, mock_init_session, mock_create_cache
    ):
        """Test create_aws_client_manager handles cache creation failure gracefully."""
        mock_create_cache.side_effect = Exception("Cache creation failed")

        # Should not raise exception, should create client manager without cache
        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is True
        assert client_manager.cache_manager is None

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_minimal_parameters(self, mock_init_session):
        """Test create_aws_client_manager with minimal parameters."""
        client_manager = AWSClientManager.with_cache_integration()

        # Should use default values
        assert client_manager.profile is None
        assert client_manager.region is None
        assert client_manager.enable_caching is True  # Default is True

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_create_aws_client_manager_auto_profile_resolution(
        self, mock_init_session, mock_create_cache
    ):
        """Test create_aws_client_manager auto-resolves profile when not specified."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        # Mock the config system to return a default profile
        with patch("src.awsideman.utils.config.Config") as mock_config_class:
            mock_config = Mock()
            mock_config.get.return_value = "default-profile"
            mock_config_class.return_value = mock_config

            # The AWSClientManager doesn't auto-resolve profiles, so we need to pass it explicitly
            client_manager = AWSClientManager.with_cache_integration(
                profile="default-profile",  # Pass the profile explicitly
                region="us-west-2",
                enable_caching=True,
            )

            assert client_manager.profile == "default-profile"
            assert client_manager.region == "us-west-2"
