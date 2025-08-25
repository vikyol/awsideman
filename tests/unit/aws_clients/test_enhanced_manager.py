"""Unit tests for enhanced AWSClientManager with cache integration."""

from unittest.mock import Mock, patch

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.cache.manager import CacheManager


class TestEnhancedAWSClientManager:
    """Test enhanced AWSClientManager with cache integration."""

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_init_with_cache_integration(self, mock_init_session):
        """Test AWSClientManager initialization with cache integration."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_cache_config = {"backend_type": "dynamodb", "enabled": True}

        client_manager = AWSClientManager(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_manager=mock_cache_manager,
            cache_config=mock_cache_config,
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is True
        assert client_manager.cache_manager == mock_cache_manager
        assert client_manager.cache_config == mock_cache_config

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_init_without_cache_integration(self, mock_init_session):
        """Test AWSClientManager initialization without cache integration."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is False
        assert client_manager.cache_manager is None
        assert client_manager.cache_config == {}

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    def test_with_cache_integration_class_method(self, mock_create_cache):
        """Test with_cache_integration class method."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        with patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session"):
            client_manager = AWSClientManager.with_cache_integration(
                profile="test-profile", region="us-west-2", enable_caching=True
            )

            assert client_manager.profile == "test-profile"
            assert client_manager.region == "us-west-2"
            assert client_manager.enable_caching is True
            assert client_manager.cache_manager == mock_cache_manager

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_with_cache_integration_disabled(self, mock_init_session):
        """Test with_cache_integration class method with caching disabled."""
        client_manager = AWSClientManager.with_cache_integration(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        assert client_manager.profile == "test-profile"
        assert client_manager.region == "us-west-2"
        assert client_manager.enable_caching is False
        assert client_manager.cache_manager is None

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    @patch("src.awsideman.cache.utilities.create_cache_manager")
    def test_get_cached_client_auto_configure(self, mock_create_cache, mock_init_session):
        """Test get_cached_client with auto-configuration."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        cached_client = client_manager.get_cached_client()

        assert cached_client is not None
        assert client_manager.cache_manager == mock_cache_manager

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    @patch("src.awsideman.cache.utilities.create_cache_manager")
    def test_get_cached_client_singleton(self, mock_create_cache, mock_init_session):
        """Test that get_cached_client returns the same instance."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

        mock_cache_manager = Mock(spec=CacheManager)
        mock_create_cache.return_value = mock_cache_manager

        cached_client1 = client_manager.get_cached_client()
        cached_client2 = client_manager.get_cached_client()

        assert cached_client1 is cached_client2

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_is_caching_enabled_with_cache_manager(self, mock_init_session):
        """Test is_caching_enabled when cache manager is available."""
        mock_cache_manager = Mock(spec=CacheManager)
        client_manager = AWSClientManager(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_manager=mock_cache_manager,
        )

        assert client_manager.is_caching_enabled() is True

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_is_caching_enabled_without_cache_manager(self, mock_init_session):
        """Test is_caching_enabled when cache manager is not available."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=True, cache_manager=None
        )

        assert client_manager.is_caching_enabled() is False

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_is_caching_enabled_disabled(self, mock_init_session):
        """Test is_caching_enabled when caching is disabled."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        assert client_manager.is_caching_enabled() is False

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_get_cache_stats_enabled(self, mock_init_session):
        """Test get_cache_stats when caching is enabled."""
        mock_cache_manager = Mock(spec=CacheManager)
        mock_cache_manager.get_cache_stats.return_value = {"enabled": True, "entries": 5}

        client_manager = AWSClientManager(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_manager=mock_cache_manager,
        )

        stats = client_manager.get_cache_stats()

        assert stats["enabled"] is True
        assert stats["entries"] == 5
        mock_cache_manager.get_cache_stats.assert_called_once()

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_get_cache_stats_disabled(self, mock_init_session):
        """Test get_cache_stats when caching is disabled."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        stats = client_manager.get_cache_stats()

        assert stats["caching_enabled"] is False

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_clear_cache_success(self, mock_init_session):
        """Test clear_cache when successful."""
        mock_cache_manager = Mock(spec=CacheManager)
        # Add the clear method to the mock
        mock_cache_manager.clear = Mock(return_value=True)

        client_manager = AWSClientManager(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_manager=mock_cache_manager,
        )

        result = client_manager.clear_cache()

        assert result is True
        mock_cache_manager.clear.assert_called_once()

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_clear_cache_failure(self, mock_init_session):
        """Test clear_cache when operation fails."""
        mock_cache_manager = Mock(spec=CacheManager)
        # Add the clear method to the mock
        mock_cache_manager.clear = Mock(side_effect=Exception("Clear failed"))

        client_manager = AWSClientManager(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_manager=mock_cache_manager,
        )

        result = client_manager.clear_cache()

        assert result is False

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_clear_cache_disabled(self, mock_init_session):
        """Test clear_cache when caching is disabled."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        result = client_manager.clear_cache()

        assert result is False

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_get_cache_manager(self, mock_init_session):
        """Test get_cache_manager returns the cache manager instance."""
        mock_cache_manager = Mock(spec=CacheManager)
        client_manager = AWSClientManager(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_manager=mock_cache_manager,
        )

        result = client_manager.get_cache_manager()

        assert result == mock_cache_manager

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_get_identity_store_client_with_caching(self, mock_init_session):
        """Test get_identity_store_client when caching is enabled."""
        mock_cache_manager = Mock(spec=CacheManager)
        client_manager = AWSClientManager(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            cache_manager=mock_cache_manager,
        )

        with patch.object(client_manager, "get_raw_identity_store_client") as mock_get_raw:
            mock_raw_client = Mock()
            mock_get_raw.return_value = mock_raw_client

            with patch(
                "src.awsideman.cache.aws_client.CachedIdentityStoreClient"
            ) as mock_cached_client_class:
                mock_cached_client = Mock()
                mock_cached_client_class.return_value = mock_cached_client

                result = client_manager.get_identity_store_client()

                assert result == mock_cached_client
                mock_cached_client_class.assert_called_once_with(
                    mock_raw_client, mock_cache_manager
                )

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_get_identity_store_client_without_caching(self, mock_init_session):
        """Test get_identity_store_client when caching is disabled."""
        client_manager = AWSClientManager(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        with patch(
            "src.awsideman.aws_clients.manager.IdentityStoreClientWrapper"
        ) as mock_wrapper_class:
            mock_wrapper = Mock()
            mock_wrapper_class.return_value = mock_wrapper

            result = client_manager.get_identity_store_client()

            assert result == mock_wrapper
            mock_wrapper_class.assert_called_once_with(client_manager)

    @patch("src.awsideman.aws_clients.manager.AWSClientManager._init_session")
    def test_get_sso_admin_client_alias(self, mock_init_session):
        """Test get_sso_admin_client is an alias for get_identity_center_client."""
        client_manager = AWSClientManager(profile="test-profile", region="us-west-2")

        with patch.object(client_manager, "get_identity_center_client") as mock_get_center:
            mock_get_center.return_value = "center_client"

            result = client_manager.get_sso_admin_client()

            assert result == "center_client"
            mock_get_center.assert_called_once()
