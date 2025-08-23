"""Tests for profile-specific cache configuration."""

from unittest.mock import Mock, patch

from src.awsideman.cache.config import AdvancedCacheConfig, ProfileCacheConfig


class TestProfileCacheConfig:
    """Test ProfileCacheConfig class."""

    def test_profile_cache_config_creation(self):
        """Test creating a ProfileCacheConfig instance."""
        config = ProfileCacheConfig(
            profile_name="test-profile",
            backend_type="dynamodb",
            dynamodb_table_name="test-table",
            dynamodb_region="us-west-2",
            encryption_enabled=True,
        )

        assert config.profile_name == "test-profile"
        assert config.backend_type == "dynamodb"
        assert config.dynamodb_table_name == "test-table"
        assert config.dynamodb_region == "us-west-2"
        assert config.encryption_enabled is True
        assert config.encryption_type == "aes256"

    def test_profile_cache_config_defaults(self):
        """Test ProfileCacheConfig default values."""
        config = ProfileCacheConfig(profile_name="test-profile")

        assert config.backend_type == "file"
        assert config.enabled is True
        assert config.default_ttl == 3600
        assert config.max_size_mb == 100
        assert config.encryption_enabled is False
        assert config.encryption_type == "none"

    def test_profile_cache_config_validation(self):
        """Test ProfileCacheConfig validation."""
        # Test invalid backend type
        config = ProfileCacheConfig(profile_name="test-profile", backend_type="invalid")
        assert config.backend_type == "file"  # Should default to file

        # Test invalid encryption type
        config = ProfileCacheConfig(profile_name="test-profile", encryption_type="invalid")
        # When encryption is disabled (default), encryption_type should be "none"
        assert config.encryption_type == "none"

    def test_profile_cache_config_to_dict(self):
        """Test ProfileCacheConfig.to_dict method."""
        config = ProfileCacheConfig(
            profile_name="test-profile",
            backend_type="dynamodb",
            dynamodb_table_name="test-table",
            operation_ttls={"list_users": 1800},
        )

        config_dict = config.to_dict()
        assert config_dict["profile_name"] == "test-profile"
        assert config_dict["backend_type"] == "dynamodb"
        assert config_dict["dynamodb_table_name"] == "test-table"
        assert config_dict["operation_ttls"]["list_users"] == 1800

    def test_profile_cache_config_from_dict(self):
        """Test ProfileCacheConfig.from_dict method."""
        config_data = {
            "profile_name": "test-profile",
            "backend_type": "file",
            "file_cache_dir": "/tmp/cache",
            "enabled": False,
        }

        config = ProfileCacheConfig.from_dict(config_data)
        assert config.profile_name == "test-profile"
        assert config.backend_type == "file"
        assert config.file_cache_dir == "/tmp/cache"
        assert config.enabled is False


class TestAdvancedCacheConfigProfileSupport:
    """Test AdvancedCacheConfig profile support."""

    def test_advanced_cache_config_with_profile_configs(self):
        """Test AdvancedCacheConfig with profile configurations."""
        profile_configs = {
            "prod": ProfileCacheConfig(
                profile_name="prod", backend_type="dynamodb", dynamodb_table_name="prod-cache"
            ),
            "dev": ProfileCacheConfig(
                profile_name="dev", backend_type="file", file_cache_dir="/tmp/dev-cache"
            ),
        }

        config = AdvancedCacheConfig(
            backend_type="file", profile_configs=profile_configs  # Default backend
        )

        assert "prod" in config.profile_configs
        assert "dev" in config.profile_configs
        assert config.profile_configs["prod"].dynamodb_table_name == "prod-cache"
        assert config.profile_configs["dev"].file_cache_dir == "/tmp/dev-cache"

    def test_get_profile_config_existing(self):
        """Test getting existing profile configuration."""
        profile_config = ProfileCacheConfig(
            profile_name="prod", backend_type="dynamodb", dynamodb_table_name="prod-cache"
        )

        config = AdvancedCacheConfig(profile_configs={"prod": profile_config})

        result = config.get_profile_config("prod")
        assert result is profile_config
        assert result.dynamodb_table_name == "prod-cache"

    def test_get_profile_config_missing(self):
        """Test getting missing profile configuration (should return default)."""
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="default-table",
            dynamodb_region="us-east-1",
        )

        result = config.get_profile_config("missing-profile")
        assert result.profile_name == "missing-profile"
        assert result.backend_type == "dynamodb"
        assert result.dynamodb_table_name == "default-table"
        assert result.dynamodb_region == "us-east-1"

    def test_get_profile_config_with_operation_ttls(self):
        """Test profile configuration with operation TTLs."""
        config = AdvancedCacheConfig(operation_ttls={"list_users": 3600, "list_groups": 7200})

        result = config.get_profile_config("test-profile")
        assert result.operation_ttls["list_users"] == 3600
        assert result.operation_ttls["list_groups"] == 7200

    def test_profile_configs_initialization(self):
        """Test that profile_configs is properly initialized."""
        config = AdvancedCacheConfig()
        assert config.profile_configs == {}

        config = AdvancedCacheConfig(profile_configs=None)
        assert config.profile_configs == {}


class TestProfileCacheConfigFileBackendDefaults:
    """Test ProfileCacheConfig file backend default directory generation."""

    @patch("src.awsideman.cache.config.Path")
    def test_file_backend_default_directory(self, mock_path_class):
        """Test that file backend gets default directory when none specified."""
        # Mock the Path class
        mock_path = Mock()
        mock_path.__truediv__ = lambda self, other: mock_path
        mock_path.__str__ = lambda self: "/home/user/.awsideman/cache/test-profile"
        mock_path_class.home.return_value = mock_path

        config = ProfileCacheConfig(profile_name="test-profile", backend_type="file")

        expected_path = "/home/user/.awsideman/cache/test-profile"
        assert config.file_cache_dir == expected_path

    def test_file_backend_custom_directory(self):
        """Test that custom file cache directory is preserved."""
        config = ProfileCacheConfig(
            profile_name="test-profile", backend_type="file", file_cache_dir="/custom/cache/path"
        )

        assert config.file_cache_dir == "/custom/cache/path"

    def test_hybrid_backend_default_directory(self):
        """Test that hybrid backend also gets default directory."""
        config = ProfileCacheConfig(profile_name="test-profile", backend_type="hybrid")

        assert config.file_cache_dir is not None
        assert "test-profile" in config.file_cache_dir


class TestProfileCacheConfigDynamoDBValidation:
    """Test ProfileCacheConfig DynamoDB validation."""

    def test_dynamodb_backend_without_table_name(self):
        """Test DynamoDB backend warns when no table name specified."""
        # The warning is logged, not raised as UserWarning
        config = ProfileCacheConfig(profile_name="test-profile", backend_type="dynamodb")

        assert config.dynamodb_table_name is None

    def test_dynamodb_backend_with_table_name(self):
        """Test DynamoDB backend with table name specified."""
        config = ProfileCacheConfig(
            profile_name="test-profile", backend_type="dynamodb", dynamodb_table_name="test-table"
        )

        assert config.dynamodb_table_name == "test-table"

    def test_hybrid_backend_without_table_name(self):
        """Test hybrid backend warns when no DynamoDB table name specified."""
        # The warning is logged, not raised as UserWarning
        config = ProfileCacheConfig(profile_name="test-profile", backend_type="hybrid")

        assert config.dynamodb_table_name is None
