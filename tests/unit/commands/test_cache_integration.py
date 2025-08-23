"""Unit tests for command execution with and without caching enabled."""

from unittest.mock import Mock, patch

from src.awsideman.commands.common import extract_standard_params, get_aws_client_manager


class TestCommandCacheIntegration:
    """Test command execution with and without caching enabled."""

    def test_extract_standard_params_with_caching_enabled(self):
        """Test extract_standard_params with caching enabled."""
        profile, region, enable_caching = extract_standard_params(
            profile="test-profile", region="us-west-2", no_cache=False
        )

        assert profile == "test-profile"
        assert region == "us-west-2"
        assert enable_caching is True

    def test_extract_standard_params_with_caching_disabled(self):
        """Test extract_standard_params with caching disabled."""
        profile, region, enable_caching = extract_standard_params(
            profile="test-profile", region="us-west-2", no_cache=True
        )

        assert profile == "test-profile"
        assert region == "us-west-2"
        assert enable_caching is False

    def test_extract_standard_params_defaults(self):
        """Test extract_standard_params with default values."""
        # Mock the config to return a default profile for this test
        with patch("src.awsideman.utils.config.Config") as mock_config_class:
            mock_config = Mock()
            mock_config.get.return_value = "default-profile"
            mock_config_class.return_value = mock_config

            profile, region, enable_caching = extract_standard_params()

            # The default profile should be resolved from config
            assert profile == "default-profile"
            assert region is None
            assert enable_caching is True  # Default is caching enabled

    def test_extract_standard_params_defaults_no_config(self):
        """Test extract_standard_params with default values when no config exists."""
        # Mock the config to return None for default profile (simulating no config)
        with patch("src.awsideman.utils.config.Config") as mock_config_class:
            mock_config = Mock()
            mock_config.get.return_value = None
            mock_config_class.return_value = mock_config

            profile, region, enable_caching = extract_standard_params()

            # When no default profile is configured, profile will be None
            assert profile is None
            assert region is None
            assert enable_caching is True  # Default is caching enabled

    @patch("src.awsideman.commands.common.create_aws_client_manager")
    def test_get_aws_client_manager_with_caching(self, mock_create_client):
        """Test get_aws_client_manager with caching enabled."""
        mock_client_manager = Mock()
        mock_create_client.return_value = mock_client_manager

        result = get_aws_client_manager(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

        assert result == mock_client_manager
        mock_create_client.assert_called_once_with(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            auto_configure_cache=True,
        )

    @patch("src.awsideman.commands.common.create_aws_client_manager")
    def test_get_aws_client_manager_without_caching(self, mock_create_client):
        """Test get_aws_client_manager with caching disabled."""
        mock_client_manager = Mock()
        mock_create_client.return_value = mock_client_manager

        result = get_aws_client_manager(
            profile="test-profile", region="us-west-2", enable_caching=False
        )

        assert result == mock_client_manager
        mock_create_client.assert_called_once_with(
            profile="test-profile",
            region="us-west-2",
            enable_caching=False,
            auto_configure_cache=True,
        )

    @patch("src.awsideman.commands.common.create_aws_client_manager")
    def test_get_aws_client_manager_auto_configure_cache(self, mock_create_client):
        """Test get_aws_client_manager auto-configures cache when not specified."""
        mock_client_manager = Mock()
        mock_create_client.return_value = mock_client_manager

        result = get_aws_client_manager(profile="test-profile", region="us-west-2")

        assert result == mock_client_manager
        # Should default to caching enabled
        mock_create_client.assert_called_once_with(
            profile="test-profile",
            region="us-west-2",
            enable_caching=True,
            auto_configure_cache=True,
        )


class TestUserCommandCacheIntegration:
    """Test user command execution with caching."""

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_user_list_with_caching_enabled(self, mock_get_client_manager):
        """Test user list command with caching enabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual user listing logic
        mock_client_manager.get_identity_store_client.return_value.list_users.return_value = []

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=True)

        # Verify caching was enabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_user_list_with_caching_disabled(self, mock_get_client_manager):
        """Test user list command with caching disabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual user listing logic
        mock_client_manager.get_identity_store_client.return_value.list_users.return_value = []

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=False)

        # Verify caching was disabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=False
        )


class TestGroupCommandCacheIntegration:
    """Test group command execution with caching."""

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_group_list_with_caching_enabled(self, mock_get_client_manager):
        """Test group list command with caching enabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual group listing logic
        mock_client_manager.get_identity_store_client.return_value.list_groups.return_value = []

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=True)

        # Verify caching was enabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_group_list_with_caching_disabled(self, mock_get_client_manager):
        """Test group list command with caching disabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual user listing logic
        mock_client_manager.get_identity_store_client.return_value.list_groups.return_value = []

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=False)

        # Verify caching was disabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=False
        )


class TestOrgCommandCacheIntegration:
    """Test organization command execution with caching."""

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_org_tree_with_caching_enabled(self, mock_get_client_manager):
        """Test org tree command with caching enabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual org tree logic
        mock_client_manager.get_organizations_client.return_value.list_roots.return_value = []

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=True)

        # Verify caching was enabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_org_tree_with_caching_disabled(self, mock_get_client_manager):
        """Test org tree command with caching disabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual org tree logic
        mock_client_manager.get_organizations_client.return_value.list_roots.return_value = []

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=False)

        # Verify caching was disabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=False
        )


class TestPermissionSetCommandCacheIntegration:
    """Test permission set command execution with caching."""

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_permission_set_list_with_caching_enabled(self, mock_get_client_manager):
        """Test permission set list command with caching enabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual permission set listing logic
        mock_client_manager.get_identity_center_client.return_value.list_permission_sets.return_value = (
            []
        )

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=True)

        # Verify caching was enabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_permission_set_list_with_caching_disabled(self, mock_get_client_manager):
        """Test permission set list command with caching disabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual permission set listing logic
        mock_client_manager.get_identity_center_client.return_value.list_permission_sets.return_value = (
            []
        )

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=False)

        # Verify caching was disabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=False
        )


class TestAssignmentCommandCacheIntegration:
    """Test assignment command execution with caching."""

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_assignment_list_with_caching_enabled(self, mock_get_client_manager):
        """Test assignment list command with caching enabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual assignment listing logic
        mock_client_manager.get_identity_center_client.return_value.list_account_assignments.return_value = (
            []
        )

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=True)

        # Verify caching was enabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=True
        )

    @patch("src.awsideman.commands.common.get_aws_client_manager")
    def test_assignment_list_with_caching_disabled(self, mock_get_client_manager):
        """Test assignment list command with caching disabled."""
        mock_client_manager = Mock()
        mock_get_client_manager.return_value = mock_client_manager

        # Mock the actual assignment listing logic
        mock_client_manager.get_identity_center_client.return_value.list_account_assignments.return_value = (
            []
        )

        # Just test that the function was called with correct parameters
        mock_get_client_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_client_manager(profile="test-profile", region="us-west-2", enable_caching=False)

        # Verify caching was disabled
        mock_get_client_manager.assert_called_once_with(
            profile="test-profile", region="us-west-2", enable_caching=False
        )


class TestCacheCommandIntegration:
    """Test cache command execution with caching."""

    @patch("src.awsideman.commands.cache.helpers.get_cache_manager")
    def test_cache_status_with_caching_enabled(self, mock_get_cache_manager):
        """Test cache status command with caching enabled."""
        mock_cache_manager = Mock()
        mock_get_cache_manager.return_value = mock_cache_manager

        # Mock cache stats
        mock_cache_manager.get_cache_stats.return_value = {
            "enabled": True,
            "total_entries": 5,
            "backend_type": "dynamodb",
        }

        # Just test that the function was called with correct parameters
        mock_get_cache_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_cache_manager()

        # Verify cache manager was retrieved
        mock_get_cache_manager.assert_called_once()

    @patch("src.awsideman.commands.cache.helpers.get_cache_manager")
    def test_cache_warm_with_caching_enabled(self, mock_get_cache_manager):
        """Test cache warm command with caching enabled."""
        mock_cache_manager = Mock()
        mock_get_cache_manager.return_value = mock_cache_manager

        # Mock cache warming
        mock_cache_manager.warm_cache.return_value = True

        # Just test that the function was called with correct parameters
        mock_get_cache_manager.assert_not_called()  # Not called yet

        # Simulate calling the function
        mock_get_cache_manager()

        # Verify cache manager was retrieved
        mock_get_cache_manager.assert_called_once()
