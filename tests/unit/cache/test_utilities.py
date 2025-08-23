"""Unit tests for cache configuration utilities."""

import os
from unittest.mock import Mock, patch

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
    @patch("src.awsideman.cache.utilities.CacheManager")
    def test_successful_cache_manager_creation(self, mock_cache_manager_class, mock_get_config):
        """Test successful cache manager creation."""
        mock_config = Mock()
        mock_config.validate.return_value = {}
        mock_get_config.return_value = mock_config

        mock_manager = Mock()
        mock_cache_manager_class.return_value = mock_manager

        result = create_cache_manager()

        assert result == mock_manager
        mock_cache_manager_class.assert_called_once_with(config=mock_config)

    @patch("src.awsideman.cache.utilities.get_default_cache_config")
    @patch("src.awsideman.cache.utilities.CacheManager")
    def test_fallback_to_basic_cache_manager(self, mock_cache_manager_class, mock_get_config):
        """Test fallback to basic cache manager when creation fails."""
        # Mock the config to be valid
        mock_config = Mock()
        mock_config.backend_type = "dynamodb"
        mock_config.validate.return_value = {}
        mock_get_config.return_value = mock_config

        # First call to CacheManager fails, second call succeeds (fallback)
        mock_cache_manager_class.side_effect = [Exception("Construction failed"), Mock()]

        result = create_cache_manager()

        assert result is not None
        # Should be called twice - once for the failed attempt, once for fallback
        assert mock_cache_manager_class.call_count == 2


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

            # Should still contain default values
            assert "default_ttl" in result
            assert "max_size_mb" in result
            assert result["default_ttl"] == 3600  # Default value
            assert result["max_size_mb"] == 100  # Default value


class TestValidateCacheConfiguration:
    """Test validate_cache_configuration function."""

    def test_valid_config_dict(self):
        """Test validation of valid configuration dictionary."""
        config = {"enabled": True, "backend_type": "file", "default_ttl": 3600, "max_size_mb": 100}

        result = validate_cache_configuration(config)

        assert result == {}

    def test_invalid_config_dict(self):
        """Test validation of invalid configuration dictionary."""
        config = {
            "enabled": True,
            "backend_type": "invalid_backend",
            "default_ttl": -1,
            "max_size_mb": 0,
        }

        result = validate_cache_configuration(config)

        assert "backend_type" in result
        assert "default_ttl" in result
        assert "max_size_mb" in result


class TestGetOptimalCacheConfigForEnvironment:
    """Test get_optimal_cache_config_for_environment function."""

    def test_production_environment(self):
        """Test optimal config for production environment."""
        with patch.dict(
            os.environ, {"ENVIRONMENT": "production", "AWS_ACCESS_KEY_ID": "test-key"}, clear=True
        ):
            result = get_optimal_cache_config_for_environment()

            assert result.backend_type == "dynamodb"
            assert result.encryption_enabled is True
            assert result.default_ttl == 7200
            assert result.max_size_mb == 200

    def test_ci_cd_environment(self):
        """Test optimal config for CI/CD environment."""
        with patch.dict(os.environ, {"CI": "true"}, clear=True):
            result = get_optimal_cache_config_for_environment()

            assert result.backend_type == "file"
            assert result.encryption_enabled is True

    def test_development_environment(self):
        """Test optimal config for development environment."""
        with patch.dict(os.environ, {"AWS_PROFILE": "dev-profile"}, clear=True):
            result = get_optimal_cache_config_for_environment()

            assert result.backend_type == "hybrid"
            assert result.encryption_enabled is False

    def test_local_development(self):
        """Test optimal config for local development without AWS."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_optimal_cache_config_for_environment()

            assert result.backend_type == "file"
            assert result.encryption_enabled is False


class TestMergeCacheConfigs:
    """Test merge_cache_configs function."""

    def test_merge_configs(self):
        """Test merging two configurations."""
        base_config = Mock()
        base_config.to_dict.return_value = {
            "enabled": True,
            "backend_type": "file",
            "default_ttl": 3600,
        }

        override_config = Mock()
        override_config.to_dict.return_value = {"backend_type": "dynamodb", "max_size_mb": 200}

        with patch("src.awsideman.cache.utilities.AdvancedCacheConfig") as mock_config_class:
            mock_config_class.return_value = Mock()

            _result = merge_cache_configs(base_config, override_config)

            mock_config_class.assert_called_once()
            call_args = mock_config_class.call_args[1]
            assert call_args["enabled"] is True
            assert call_args["backend_type"] == "dynamodb"
            assert call_args["default_ttl"] == 3600
            assert call_args["max_size_mb"] == 200
