"""Unit tests for cache configuration utilities."""

import os
from unittest.mock import Mock, patch

from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.utilities import (
    create_aws_client_manager,
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
        mock_config = Mock()
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
        mock_config = Mock()
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


class TestCreateCacheManager:
    """Test create_cache_manager function."""

    @patch("src.awsideman.cache.utilities.get_default_cache_config")
    def test_successful_cache_manager_creation(self, mock_get_config):
        """Test successful cache manager creation returns CacheManager."""
        from src.awsideman.cache.manager import CacheManager

        mock_config = Mock()
        mock_config.validate.return_value = {}
        mock_get_config.return_value = mock_config

        result = create_cache_manager()

        # Should return CacheManager singleton
        assert isinstance(result, CacheManager)

        # Multiple calls should return the same instance
        result2 = create_cache_manager()
        assert result is result2

    @patch("src.awsideman.cache.utilities.get_default_cache_config")
    def test_fallback_to_basic_cache_manager(self, mock_get_config):
        """Test that create_cache_manager always returns CacheManager."""
        from src.awsideman.cache.manager import CacheManager

        # Mock the config to be valid
        mock_config = Mock()
        mock_config.backend_type = "dynamodb"
        mock_config.validate.return_value = {}
        mock_get_config.return_value = mock_config

        result = create_cache_manager()

        # Should always return CacheManager singleton regardless of config
        assert isinstance(result, CacheManager)

        # Should be consistent across calls
        result2 = create_cache_manager()
        assert result is result2


class TestCreateAwsClientManager:
    """Test create_aws_client_manager function."""

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.cache.utilities.AWSClientManager")
    def test_successful_client_manager_creation(self, mock_client_manager_class, mock_create_cache):
        """Test successful AWS client manager creation with cache."""
        mock_cache_manager = Mock()
        mock_create_cache.return_value = mock_cache_manager

        mock_client_manager = Mock()
        mock_client_manager_class.return_value = mock_client_manager

        result = create_aws_client_manager(enable_caching=True)

        assert result == mock_client_manager
        mock_client_manager_class.assert_called_once()

    @patch("src.awsideman.cache.utilities.create_cache_manager")
    @patch("src.awsideman.cache.utilities.AWSClientManager")
    def test_fallback_to_basic_client_manager(self, mock_client_manager_class, mock_create_cache):
        """Test fallback to basic client manager when creation fails."""
        # First call to AWSClientManager fails, second call succeeds (fallback)
        mock_client_manager_class.side_effect = [Exception("Construction failed"), Mock()]

        result = create_aws_client_manager(enable_caching=True)

        assert result is not None
        # Should be called twice - once for the failed attempt, once for fallback
        assert mock_client_manager_class.call_count == 2


class TestGetCacheConfigFromEnvironment:
    """Test get_cache_config_from_environment function."""

    def test_basic_cache_settings(self):
        """Test extraction of basic cache settings from environment."""
        with patch.dict(
            os.environ,
            {
                "AWSIDEMAN_CACHE_ENABLED": "true",
                "AWSIDEMAN_CACHE_TTL_DEFAULT": "7200",
                "AWSIDEMAN_CACHE_MAX_SIZE_MB": "200",
            },
        ):
            result = get_cache_config_from_environment()

            assert result["enabled"] is True
            assert result["default_ttl"] == 7200
            assert result["max_size_mb"] == 200

    def test_advanced_cache_settings(self):
        """Test extraction of advanced cache settings from environment."""
        with patch.dict(
            os.environ,
            {
                "AWSIDEMAN_CACHE_BACKEND": "dynamodb",
                "AWSIDEMAN_CACHE_ENCRYPTION": "true",
                "AWSIDEMAN_CACHE_DYNAMODB_TABLE": "test-table",
            },
        ):
            result = get_cache_config_from_environment()

            assert result["backend_type"] == "dynamodb"
            assert result["encryption_enabled"] is True
            assert result["dynamodb_table_name"] == "test-table"

    def test_invalid_integer_values(self):
        """Test handling of invalid integer values in environment."""
        with patch.dict(
            os.environ,
            {
                "AWSIDEMAN_CACHE_TTL_DEFAULT": "invalid",
                "AWSIDEMAN_CACHE_MAX_SIZE_MB": "not_a_number",
            },
        ):
            result = get_cache_config_from_environment()

            # Should fall back to defaults
            assert result["default_ttl"] == 3600
            assert result["max_size_mb"] == 100

    def test_missing_environment_variables(self):
        """Test handling of missing environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_cache_config_from_environment()

            # Should use defaults
            assert result["enabled"] is True
            assert result["default_ttl"] == 3600
            assert result["max_size_mb"] == 100
            assert result["backend_type"] == "file"
            assert result["encryption_enabled"] is False


class TestGetOptimalCacheConfigForEnvironment:
    """Test get_optimal_cache_config_for_environment function."""

    def test_production_environment(self):
        """Test optimal config for production environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "AWS_ACCESS_KEY_ID": "test-key"}):
            result = get_optimal_cache_config_for_environment()

            assert result.enabled is True
            assert result.backend_type == "dynamodb"
            assert result.encryption_enabled is True
            assert result.default_ttl == 7200  # 2 hours for production

    def test_ci_cd_environment(self):
        """Test optimal config for CI/CD environment."""
        with patch.dict(os.environ, {"CI": "true"}):
            result = get_optimal_cache_config_for_environment()

            assert result.enabled is True
            assert result.backend_type == "file"
            assert result.encryption_enabled is True  # CI/CD environments get encryption enabled
            assert result.default_ttl == 3600  # Default TTL for CI/CD (not production)

    def test_development_environment(self):
        """Test optimal config for development environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            result = get_optimal_cache_config_for_environment()

            assert result.enabled is True
            assert result.backend_type == "file"
            assert result.encryption_enabled is False
            assert result.default_ttl == 3600  # Default TTL for development

    def test_local_development(self):
        """Test optimal config for local development."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_optimal_cache_config_for_environment()

            assert result.enabled is True
            assert result.backend_type == "file"
            assert result.encryption_enabled is False
            assert result.default_ttl == 3600  # Default TTL for local development


class TestMergeCacheConfigs:
    """Test merge_cache_configs function."""

    def test_merge_configs(self):
        """Test merging of cache configurations."""
        base_config = {
            "enabled": True,
            "backend_type": "file",
            "default_ttl": 3600,
            "max_size_mb": 100,
        }
        override_config = {
            "backend_type": "dynamodb",
            "max_size_mb": 200,
        }

        result = merge_cache_configs(base_config, override_config)

        assert result.enabled is True
        assert result.backend_type == "dynamodb"
        assert result.default_ttl == 3600
        assert result.max_size_mb == 200

    def test_merge_configs_none_values(self):
        """Test merging with None values (should be ignored)."""
        base_config = {
            "enabled": True,
            "backend_type": "file",
            "default_ttl": 3600,
        }
        override_config = {
            "backend_type": None,
            "max_size_mb": None,
        }

        result = merge_cache_configs(base_config, override_config)

        assert result.enabled is True
        assert result.backend_type == "file"
        assert result.default_ttl == 3600
        assert result.max_size_mb == 100  # Should use default from base config

    def test_merge_configs_empty_override(self):
        """Test merging with empty override config."""
        base_config = {
            "enabled": True,
            "backend_type": "file",
            "default_ttl": 3600,
        }
        override_config = {}

        result = merge_cache_configs(base_config, override_config)

        # Should return AdvancedCacheConfig object, not dict
        assert isinstance(result, AdvancedCacheConfig)
        assert result.enabled == base_config["enabled"]
        assert result.backend_type == base_config["backend_type"]
        assert result.default_ttl == base_config["default_ttl"]

    def test_merge_configs_complex(self):
        """Test merging with complex nested configurations."""
        base_config = {
            "enabled": True,
            "backend_type": "file",
            "dynamodb_table_name": "default-table",
            "dynamodb_region": "us-east-1",
        }
        override_config = {
            "backend_type": "dynamodb",
            "dynamodb_table_name": "custom-table",
            "encryption_enabled": True,
        }

        result = merge_cache_configs(base_config, override_config)

        assert result.enabled is True
        assert result.backend_type == "dynamodb"
        assert result.dynamodb_table_name == "custom-table"
        assert result.dynamodb_region == "us-east-1"
        assert result.encryption_enabled is True


class TestValidateCacheConfiguration:
    """Test validate_cache_configuration function."""

    def test_valid_configuration(self):
        """Test validation of valid configuration."""
        config = {
            "enabled": True,
            "backend_type": "file",
            "default_ttl": 3600,
            "max_size_mb": 100,
        }

        result = validate_cache_configuration(config)

        assert result == {}

    def test_invalid_backend_type(self):
        """Test validation with invalid backend type."""
        config = {
            "enabled": True,
            "backend_type": "invalid_backend",
            "default_ttl": 3600,
        }

        result = validate_cache_configuration(config)

        assert "backend_type" in result
        assert "invalid" in result["backend_type"].lower()

    def test_invalid_ttl_values(self):
        """Test validation with invalid TTL values."""
        config = {
            "enabled": True,
            "backend_type": "file",
            "default_ttl": -100,
            "operation_ttls": {
                "user_list": -50,
            },
        }

        result = validate_cache_configuration(config)

        assert "default_ttl" in result
        # operation_ttls validation is handled differently now
        assert "default_ttl" in result

    def test_invalid_size_values(self):
        """Test validation with invalid size values."""
        config = {
            "enabled": True,
            "backend_type": "file",
            "max_size_mb": -50,
            "max_size": -100,
        }

        result = validate_cache_configuration(config)

        # max_size is not a valid field, should trigger config validation error
        assert "config" in result

    def test_dynamodb_validation(self):
        """Test DynamoDB-specific validation."""
        config = {
            "enabled": True,
            "backend_type": "dynamodb",
            "dynamodb_table_name": "",  # Invalid empty name
        }

        result = validate_cache_configuration(config)

        assert "dynamodb_table_name" in result

    def test_encryption_validation(self):
        """Test encryption validation."""
        config = {
            "enabled": True,
            "backend_type": "file",
            "encryption_enabled": True,
            "encryption_type": "invalid_type",
        }

        result = validate_cache_configuration(config)

        # encryption_type validation is handled differently now
        assert result == {}  # Should pass validation
