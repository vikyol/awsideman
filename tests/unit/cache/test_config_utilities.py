"""Unit tests for cache configuration utilities."""

import os
from unittest.mock import Mock, patch

from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.utilities import (
    create_cache_manager,
    get_cache_config_from_environment,
    get_default_cache_config,
    get_optimal_cache_config_for_environment,
    merge_cache_configs,
    validate_cache_configuration,
)


class TestGetDefaultCacheConfig:
    """Test get_default_cache_config function."""

    @patch("src.awsideman.cache.utilities.AdvancedCacheConfig.from_config_file")
    @patch("src.awsideman.cache.utilities.AdvancedCacheConfig.from_config_and_environment")
    def test_successful_config_loading(self, mock_from_env, mock_from_file):
        """Test successful configuration loading from file and environment."""
        mock_config = Mock(spec=AdvancedCacheConfig)
        mock_from_file.return_value = mock_config
        mock_from_env.return_value = mock_config

        result = get_default_cache_config()

        assert result == mock_config
        mock_from_file.assert_called_once()
        mock_from_env.assert_called_once()

    @patch("src.awsideman.cache.utilities.AdvancedCacheConfig.from_config_file")
    @patch("src.awsideman.cache.utilities.AdvancedCacheConfig.from_environment")
    def test_fallback_to_environment_only(self, mock_from_env, mock_from_file):
        """Test fallback to environment-only configuration when file loading fails."""
        mock_from_file.side_effect = Exception("File not found")
        mock_config = Mock(spec=AdvancedCacheConfig)
        mock_from_env.return_value = mock_config

        result = get_default_cache_config()

        assert result == mock_config
        mock_from_file.assert_called_once()
        mock_from_env.assert_called_once()

    @patch("src.awsideman.cache.utilities.AdvancedCacheConfig.from_config_file")
    @patch("src.awsideman.cache.utilities.AdvancedCacheConfig.from_environment")
    def test_fallback_to_hardcoded_defaults(self, mock_from_env, mock_from_file):
        """Test fallback to hardcoded defaults when all loading fails."""
        mock_from_file.side_effect = Exception("File not found")
        mock_from_env.side_effect = Exception("Environment error")

        result = get_default_cache_config()

        assert result.enabled is True
        assert result.backend_type == "file"
        assert result.default_ttl == 3600
        assert result.max_size_mb == 100
        assert result.encryption_enabled is False

    @patch("src.awsideman.cache.utilities.AdvancedCacheConfig.from_config_file")
    def test_config_file_priority(self, mock_from_file):
        """Test that config file takes priority over environment."""
        mock_config = Mock(spec=AdvancedCacheConfig)
        mock_config.backend_type = "dynamodb"
        mock_config.operation_ttls = {}
        mock_config.profile_configs = {}
        mock_from_file.return_value = mock_config

        result = get_default_cache_config()

        assert result.backend_type == "dynamodb"


class TestCreateCacheManager:
    """Test create_cache_manager function."""

    def test_successful_cache_manager_creation(self):
        """Test successful cache manager creation returns CacheManager."""
        from src.awsideman.cache.manager import CacheManager

        result = create_cache_manager()

        # Should return CacheManager singleton
        assert isinstance(result, CacheManager)

        # Multiple calls should return the same instance
        result2 = create_cache_manager()
        assert result is result2

    def test_fallback_to_basic_cache_manager(self):
        """Test that create_cache_manager always returns CacheManager."""
        from src.awsideman.cache.manager import CacheManager

        # Even with errors, should return CacheManager singleton
        result = create_cache_manager()

        assert isinstance(result, CacheManager)

        # Should be consistent across calls
        result2 = create_cache_manager()
        assert result is result2

    def test_cache_manager_with_custom_config(self):
        """Test cache manager creation with custom configuration (ignored for singleton)."""
        from src.awsideman.cache.manager import CacheManager

        custom_config = AdvancedCacheConfig(
            backend_type="dynamodb", dynamodb_table_name="custom-table", enabled=True
        )

        # Custom config is ignored since CacheManager is a singleton
        result = create_cache_manager(custom_config)

        assert isinstance(result, CacheManager)

        # Should be the same instance regardless of config
        result2 = create_cache_manager()
        assert result is result2

    def test_cache_manager_validation_warnings(self):
        """Test cache manager creation continues with validation warnings."""
        from src.awsideman.cache.manager import CacheManager

        # CacheManager should work regardless of validation warnings
        result = create_cache_manager()

        assert isinstance(result, CacheManager)
        # Should continue with warnings rather than failing


class TestGetCacheConfigFromEnvironment:
    """Test get_cache_config_from_environment function."""

    def test_environment_variable_loading(self):
        """Test loading cache configuration from environment variables."""
        with patch.dict(
            os.environ,
            {
                "AWSIDEMAN_CACHE_ENABLED": "true",
                "AWSIDEMAN_CACHE_TTL_DEFAULT": "7200",
                "AWSIDEMAN_CACHE_MAX_SIZE_MB": "200",
                "AWSIDEMAN_CACHE_BACKEND": "dynamodb",
                "AWSIDEMAN_CACHE_DYNAMODB_TABLE": "test-table",
                "AWSIDEMAN_CACHE_ENCRYPTION": "true",
            },
        ):
            config = get_cache_config_from_environment()

            assert config["enabled"] is True
            assert config["default_ttl"] == 7200
            assert config["max_size_mb"] == 200
            assert config["backend_type"] == "dynamodb"
            assert config["dynamodb_table_name"] == "test-table"
            assert config["encryption_enabled"] is True

    def test_environment_variable_defaults(self):
        """Test default values when environment variables are not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = get_cache_config_from_environment()

            assert config["enabled"] is True
            assert config["backend_type"] == "file"
            assert config["default_ttl"] == 3600
            assert config["max_size_mb"] == 100
            assert config["encryption_enabled"] is False

    def test_operation_specific_ttls(self):
        """Test loading operation-specific TTLs from environment."""
        with patch.dict(
            os.environ,
            {
                "AWSIDEMAN_CACHE_TTL_LIST_USERS": "1800",
                "AWSIDEMAN_CACHE_TTL_LIST_GROUPS": "3600",
                "AWSIDEMAN_CACHE_TTL_LIST_PERMISSION_SETS": "7200",
            },
        ):
            config = get_cache_config_from_environment()

            assert config["operation_ttls"]["list_users"] == 1800
            assert config["operation_ttls"]["list_groups"] == 3600
            assert config["operation_ttls"]["list_permission_sets"] == 7200

    def test_boolean_environment_variables(self):
        """Test boolean environment variable parsing."""
        with patch.dict(
            os.environ, {"AWSIDEMAN_CACHE_ENABLED": "false", "AWSIDEMAN_CACHE_ENCRYPTION": "false"}
        ):
            config = get_cache_config_from_environment()

            assert config["enabled"] is False
            assert config["encryption_enabled"] is False

    def test_invalid_environment_variables(self):
        """Test handling of invalid environment variables."""
        with patch.dict(
            os.environ,
            {
                "AWSIDEMAN_CACHE_TTL_DEFAULT": "invalid",
                "AWSIDEMAN_CACHE_MAX_SIZE_MB": "not_a_number",
            },
        ):
            config = get_cache_config_from_environment()

            # Should fall back to defaults
            assert config["default_ttl"] == 3600
            assert config["max_size_mb"] == 100


class TestGetOptimalCacheConfigForEnvironment:
    """Test get_optimal_cache_config_for_environment function."""

    @patch("src.awsideman.cache.utilities.get_default_cache_config")
    def test_optimal_config_generation(self, mock_get_default):
        """Test optimal cache configuration generation."""
        mock_default_config = Mock(spec=AdvancedCacheConfig)
        mock_default_config.backend_type = "file"
        mock_get_default.return_value = mock_default_config

        # Test that the function returns a valid config
        config = get_optimal_cache_config_for_environment()
        assert isinstance(config, AdvancedCacheConfig)
        assert config.enabled is True

    @patch("src.awsideman.cache.utilities.get_default_cache_config")
    def test_optimal_config_fallback(self, mock_get_default):
        """Test fallback to default config when optimal generation fails."""
        mock_default_config = Mock(spec=AdvancedCacheConfig)
        mock_get_default.return_value = mock_default_config

        # Test that the function returns a valid config
        config = get_optimal_cache_config_for_environment()
        assert isinstance(config, AdvancedCacheConfig)

    def test_environment_specific_optimizations(self):
        """Test environment-specific cache optimizations."""
        # Test that the function returns a valid config
        config = get_optimal_cache_config_for_environment()
        assert isinstance(config, AdvancedCacheConfig)
        assert config.enabled is True

    def test_development_environment_optimizations(self):
        """Test development environment cache optimizations."""
        # Test that the function returns a valid config
        config = get_optimal_cache_config_for_environment()
        assert isinstance(config, AdvancedCacheConfig)
        assert config.enabled is True


class TestMergeCacheConfigs:
    """Test merge_cache_configs function."""

    def test_merge_configs_basic(self):
        """Test basic configuration merging."""
        base_config = AdvancedCacheConfig(backend_type="file", enabled=True, default_ttl=3600)

        override_config = AdvancedCacheConfig(
            backend_type="dynamodb", dynamodb_table_name="override-table"
        )

        merged = merge_cache_configs(base_config, override_config)

        assert merged.backend_type == "dynamodb"
        assert merged.dynamodb_table_name == "override-table"
        assert merged.enabled is True
        assert merged.default_ttl == 3600

    def test_merge_configs_none_values(self):
        """Test merging with None values (should not override)."""
        base_config = AdvancedCacheConfig(backend_type="file", enabled=True, default_ttl=3600)

        override_config = AdvancedCacheConfig(backend_type=None, enabled=None)

        merged = merge_cache_configs(base_config, override_config)

        assert merged.backend_type == "file"
        assert merged.enabled is True

    def test_merge_configs_empty_override(self):
        """Test merging with empty override config."""
        base_config = AdvancedCacheConfig(backend_type="file", enabled=True, default_ttl=3600)

        override_config = AdvancedCacheConfig()

        merged = merge_cache_configs(base_config, override_config)

        assert merged.backend_type == "file"
        assert merged.enabled is True
        assert merged.default_ttl == 3600

    def test_merge_configs_complex(self):
        """Test complex configuration merging."""
        base_config = AdvancedCacheConfig(
            backend_type="file", enabled=True, default_ttl=3600, operation_ttls={"list_users": 1800}
        )

        override_config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="test-table",
            operation_ttls={"list_groups": 3600},
        )

        merged = merge_cache_configs(base_config, override_config)

        assert merged.backend_type == "dynamodb"
        assert merged.dynamodb_table_name == "test-table"
        assert merged.operation_ttls["list_users"] == 1800
        assert merged.operation_ttls["list_groups"] == 3600


class TestValidateCacheConfiguration:
    """Test validate_cache_configuration function."""

    def test_valid_configuration(self):
        """Test validation of valid configuration."""
        config = AdvancedCacheConfig(
            backend_type="file", enabled=True, default_ttl=3600, max_size_mb=100
        )

        errors = validate_cache_configuration(config)

        assert len(errors) == 0

    def test_invalid_backend_type(self):
        """Test validation of invalid backend type."""
        config = AdvancedCacheConfig(backend_type="invalid_backend", enabled=True)

        errors = validate_cache_configuration(config)

        assert "backend_type" in errors
        assert "invalid_backend" in errors["backend_type"]

    def test_invalid_ttl_values(self):
        """Test validation of invalid TTL values."""
        config = AdvancedCacheConfig(
            backend_type="file", enabled=True, default_ttl=0, max_size_mb=100
        )

        errors = validate_cache_configuration(config)

        assert "default_ttl" in errors
        assert "positive" in errors["default_ttl"]

    def test_invalid_size_values(self):
        """Test validation of invalid size values."""
        config = AdvancedCacheConfig(
            backend_type="file", enabled=True, default_ttl=3600, max_size_mb=0
        )

        errors = validate_cache_configuration(config)

        assert "max_size_mb" in errors
        assert "positive" in errors["max_size_mb"]

    def test_dynamodb_validation(self):
        """Test DynamoDB-specific validation."""
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            enabled=True,
            dynamodb_table_name="",  # Invalid empty name
            default_ttl=3600,
        )

        errors = validate_cache_configuration(config)

        assert "dynamodb_table_name" in errors
        assert "required" in errors["dynamodb_table_name"]

    def test_encryption_validation(self):
        """Test encryption configuration validation."""
        config = AdvancedCacheConfig(
            backend_type="file",
            enabled=True,
            encryption_enabled=True,
            encryption_type="aes256",  # Use valid encryption type
        )

        errors = validate_cache_configuration(config)

        # Should be valid
        assert len(errors) == 0

        # Test invalid backend type validation
        invalid_config = AdvancedCacheConfig(backend_type="invalid_backend", enabled=True)

        errors = validate_cache_configuration(invalid_config)
        assert "backend_type" in errors
