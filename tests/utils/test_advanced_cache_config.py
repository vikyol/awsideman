"""Tests for advanced cache configuration."""

import os
import tempfile
from unittest.mock import Mock, patch

from src.awsideman.cache.config import AdvancedCacheConfig


class TestAdvancedCacheConfig:
    """Test cases for AdvancedCacheConfig."""

    def test_default_initialization(self):
        """Test default configuration initialization."""
        config = AdvancedCacheConfig()

        # Test default values
        assert config.enabled is True
        assert config.default_ttl == 3600
        assert config.operation_ttls == {}
        assert config.max_size_mb == 100
        assert config.backend_type == "file"
        assert config.encryption_enabled is False
        assert (
            config.encryption_type == "none"
        )  # Should be "none" when encryption is disabled by default
        assert config.dynamodb_table_name == "awsideman-cache"
        assert config.dynamodb_region is None
        assert config.dynamodb_profile is None
        assert config.hybrid_local_ttl == 300
        assert config.file_cache_dir is None

    def test_custom_initialization(self):
        """Test configuration initialization with custom values."""
        config = AdvancedCacheConfig(
            enabled=False,
            default_ttl=7200,
            operation_ttls={"list_users": 1800},
            max_size_mb=200,
            backend_type="dynamodb",
            encryption_enabled=True,
            encryption_type="aes256",
            dynamodb_table_name="custom-cache-table",
            dynamodb_region="us-west-2",
            dynamodb_profile="custom-profile",
            hybrid_local_ttl=600,
            file_cache_dir="/custom/cache/dir",
        )

        assert config.enabled is False
        assert config.default_ttl == 7200
        assert config.operation_ttls == {"list_users": 1800}
        assert config.max_size_mb == 200
        assert config.backend_type == "dynamodb"
        assert config.encryption_enabled is True
        assert config.encryption_type == "aes256"
        assert config.dynamodb_table_name == "custom-cache-table"
        assert config.dynamodb_region == "us-west-2"
        assert config.dynamodb_profile == "custom-profile"
        assert config.hybrid_local_ttl == 600
        assert config.file_cache_dir == "/custom/cache/dir"

    def test_post_init_validation(self):
        """Test post-initialization validation."""
        # Test invalid backend type warning
        with patch("src.awsideman.cache.config.logger") as mock_logger:
            config = AdvancedCacheConfig(backend_type="invalid")
            mock_logger.warning.assert_called_with(
                "Invalid backend type 'invalid', will need correction"
            )

        # Test invalid encryption type correction
        with patch("src.awsideman.cache.config.logger") as mock_logger:
            config = AdvancedCacheConfig(encryption_type="invalid")
            mock_logger.warning.assert_called_with(
                "Invalid encryption type 'invalid', defaulting to 'aes256'"
            )
            assert (
                config.encryption_type == "none"
            )  # Should be "none" because encryption_enabled defaults to False

    def test_post_init_encryption_disabled(self):
        """Test that encryption type is set to none when encryption is disabled."""
        config = AdvancedCacheConfig(encryption_enabled=False, encryption_type="aes256")

        assert config.encryption_enabled is False
        assert config.encryption_type == "none"

    def test_from_config_file(self):
        """Test loading configuration from config file."""
        mock_config = Mock()
        mock_config.get_cache_config.return_value = {
            "enabled": True,
            "default_ttl": 7200,
            "operation_ttls": {"list_users": 1800},
            "max_size_mb": 200,
        }
        mock_config.get_all.return_value = {
            "cache": {
                "backend_type": "dynamodb",
                "encryption_enabled": True,
                "dynamodb_table_name": "test-table",
                "dynamodb_region": "us-east-1",
            }
        }

        with patch("src.awsideman.utils.config.Config", return_value=mock_config):
            config = AdvancedCacheConfig.from_config_file()

        assert config.enabled is True
        assert config.default_ttl == 7200
        assert config.operation_ttls == {"list_users": 1800}
        assert config.max_size_mb == 200
        assert config.backend_type == "dynamodb"
        assert config.encryption_enabled is True
        assert config.dynamodb_table_name == "test-table"
        assert config.dynamodb_region == "us-east-1"

    def test_from_config_file_minimal(self):
        """Test loading configuration from config file with minimal data."""
        mock_config = Mock()
        mock_config.get_cache_config.return_value = {
            "enabled": True,
            "default_ttl": 3600,
            "operation_ttls": {},
            "max_size_mb": 100,
        }
        mock_config.get_all.return_value = {}

        with patch("src.awsideman.utils.config.Config", return_value=mock_config):
            config = AdvancedCacheConfig.from_config_file()

        # Should use defaults for advanced settings
        assert config.backend_type == "file"
        assert config.encryption_enabled is False
        assert config.dynamodb_table_name == "awsideman-cache"

    def test_from_environment_basic(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            "AWSIDEMAN_CACHE_ENABLED": "false",
            "AWSIDEMAN_CACHE_TTL_DEFAULT": "7200",
            "AWSIDEMAN_CACHE_MAX_SIZE_MB": "200",
            "AWSIDEMAN_CACHE_BACKEND": "dynamodb",
            "AWSIDEMAN_CACHE_ENCRYPTION": "true",
            "AWSIDEMAN_CACHE_ENCRYPTION_TYPE": "aes256",
            "AWSIDEMAN_CACHE_DYNAMODB_TABLE": "env-cache-table",
            "AWSIDEMAN_CACHE_DYNAMODB_REGION": "us-west-2",
            "AWSIDEMAN_CACHE_DYNAMODB_PROFILE": "env-profile",
            "AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL": "600",
            "AWSIDEMAN_CACHE_FILE_DIR": "/env/cache/dir",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = AdvancedCacheConfig.from_environment()

        assert config.enabled is False
        assert config.default_ttl == 7200
        assert config.max_size_mb == 200
        assert config.backend_type == "dynamodb"
        assert config.encryption_enabled is True
        assert config.encryption_type == "aes256"
        assert config.dynamodb_table_name == "env-cache-table"
        assert config.dynamodb_region == "us-west-2"
        assert config.dynamodb_profile == "env-profile"
        assert config.hybrid_local_ttl == 600
        assert config.file_cache_dir == "/env/cache/dir"

    def test_from_environment_operation_ttls(self):
        """Test loading operation-specific TTLs from environment."""
        env_vars = {
            "AWSIDEMAN_CACHE_TTL_LIST_USERS": "1800",
            "AWSIDEMAN_CACHE_TTL_DESCRIBE_ACCOUNT": "7200",
            "AWSIDEMAN_CACHE_TTL_LIST_GROUPS": "3600",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = AdvancedCacheConfig.from_environment()

        expected_operation_ttls = {
            "list_users": 1800,
            "describe_account": 7200,
            "list_groups": 3600,
        }
        assert config.operation_ttls == expected_operation_ttls

    def test_from_environment_defaults(self):
        """Test loading configuration from environment with defaults."""
        with patch.dict(os.environ, {}, clear=True):
            config = AdvancedCacheConfig.from_environment()

        # Should use default values
        assert config.enabled is True
        assert config.default_ttl == 3600
        assert config.max_size_mb == 100
        assert config.backend_type == "file"
        assert config.encryption_enabled is False
        assert config.dynamodb_table_name == "awsideman-cache"

    def test_from_config_and_environment(self):
        """Test loading configuration from both file and environment."""
        # Mock config file
        mock_config = Mock()
        mock_config.get_cache_config.return_value = {
            "enabled": True,
            "default_ttl": 3600,
            "operation_ttls": {"list_users": 1800},
            "max_size_mb": 100,
        }
        mock_config.get_all.return_value = {
            "cache": {
                "backend_type": "file",
                "encryption_enabled": False,
                "dynamodb_table_name": "file-table",
            }
        }

        # Environment variables (should override file)
        env_vars = {
            "AWSIDEMAN_CACHE_BACKEND": "dynamodb",
            "AWSIDEMAN_CACHE_ENCRYPTION": "true",
            "AWSIDEMAN_CACHE_DYNAMODB_TABLE": "env-table",
        }

        with patch("src.awsideman.utils.config.Config", return_value=mock_config):
            with patch.dict(os.environ, env_vars, clear=True):
                config = AdvancedCacheConfig.from_config_and_environment()

        # File values should be used where env vars are not set
        assert config.enabled is True  # From file
        assert config.default_ttl == 3600  # From file
        assert config.operation_ttls == {"list_users": 1800}  # From file

        # Environment values should override file values
        assert config.backend_type == "dynamodb"  # From env
        assert config.encryption_enabled is True  # From env
        assert config.dynamodb_table_name == "env-table"  # From env

    def test_validate_success(self):
        """Test successful configuration validation."""
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            encryption_type="aes256",
            default_ttl=3600,
            hybrid_local_ttl=300,
            max_size_mb=100,
            dynamodb_table_name="valid-table-name",
        )

        errors = config.validate()
        assert errors == {}

    def test_validate_invalid_backend_type(self):
        """Test validation with invalid backend type."""
        config = AdvancedCacheConfig(backend_type="invalid")

        errors = config.validate()
        assert "backend_type" in errors
        assert "Invalid backend type 'invalid'" in errors["backend_type"]

    def test_validate_invalid_encryption_type(self):
        """Test validation with invalid encryption type."""
        # Need to enable encryption to test encryption type validation
        config = AdvancedCacheConfig(encryption_enabled=True, encryption_type="invalid")

        errors = config.validate()
        # The invalid type should be corrected to "aes256" in __post_init__, but then set to "none" because encryption is disabled
        # Let's test with a truly invalid type that won't be corrected
        config.encryption_type = "truly_invalid"  # Set after init to bypass correction
        errors = config.validate()
        assert "encryption_type" in errors
        assert "Invalid encryption type 'truly_invalid'" in errors["encryption_type"]

    def test_validate_invalid_ttl_values(self):
        """Test validation with invalid TTL values."""
        config = AdvancedCacheConfig(default_ttl=-1, hybrid_local_ttl=0)

        errors = config.validate()
        assert "default_ttl" in errors
        assert "hybrid_local_ttl" in errors
        assert "must be positive" in errors["default_ttl"]
        assert "must be positive" in errors["hybrid_local_ttl"]

    def test_validate_invalid_max_size(self):
        """Test validation with invalid max size."""
        config = AdvancedCacheConfig(max_size_mb=-10)

        errors = config.validate()
        assert "max_size_mb" in errors
        assert "must be positive" in errors["max_size_mb"]

    def test_validate_dynamodb_missing_table_name(self):
        """Test validation with missing DynamoDB table name."""
        config = AdvancedCacheConfig(backend_type="dynamodb", dynamodb_table_name="")

        errors = config.validate()
        assert "dynamodb_table_name" in errors
        assert "is required for DynamoDB backend" in errors["dynamodb_table_name"]

    def test_validate_dynamodb_invalid_table_name(self):
        """Test validation with invalid DynamoDB table name."""
        config = AdvancedCacheConfig(
            backend_type="dynamodb", dynamodb_table_name="invalid@table#name"
        )

        errors = config.validate()
        assert "dynamodb_table_name" in errors
        assert "must contain only alphanumeric characters" in errors["dynamodb_table_name"]

    def test_validate_hybrid_backend_requirements(self):
        """Test validation for hybrid backend requirements."""
        config = AdvancedCacheConfig(backend_type="hybrid", dynamodb_table_name="")

        errors = config.validate()
        assert "dynamodb_table_name" in errors

    def test_validate_invalid_file_cache_dir(self):
        """Test validation with invalid file cache directory."""
        # Create a temporary file (not directory)
        with tempfile.NamedTemporaryFile() as temp_file:
            config = AdvancedCacheConfig(file_cache_dir=temp_file.name)

            errors = config.validate()
            assert "file_cache_dir" in errors
            assert "exists but is not a directory" in errors["file_cache_dir"]

    def test_to_dict(self):
        """Test converting configuration to dictionary."""
        config = AdvancedCacheConfig(
            enabled=False,
            default_ttl=7200,
            operation_ttls={"list_users": 1800},
            max_size_mb=200,
            backend_type="dynamodb",
            encryption_enabled=True,
            encryption_type="aes256",
            dynamodb_table_name="test-table",
            dynamodb_region="us-east-1",
            dynamodb_profile="test-profile",
            hybrid_local_ttl=600,
            file_cache_dir="/test/cache",
        )

        result = config.to_dict()

        expected = {
            "enabled": False,
            "default_ttl": 7200,
            "operation_ttls": {"list_users": 1800},
            "max_size_mb": 200,
            "backend_type": "dynamodb",
            "encryption_enabled": True,
            "encryption_type": "aes256",
            "dynamodb_table_name": "test-table",
            "dynamodb_region": "us-east-1",
            "dynamodb_profile": "test-profile",
            "hybrid_local_ttl": 600,
            "file_cache_dir": "/test/cache",
        }

        assert result == expected

    def test_save_to_file(self):
        """Test saving configuration to file."""
        config = AdvancedCacheConfig(backend_type="dynamodb", encryption_enabled=True)

        mock_config = Mock()

        with patch("src.awsideman.utils.config.Config", return_value=mock_config):
            config.save_to_file()

        # Should call set_cache_config with the configuration dictionary
        mock_config.set_cache_config.assert_called_once_with(config.to_dict())

    def test_get_env_bool_true_values(self):
        """Test _get_env_bool with various true values."""
        true_values = ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]

        for value in true_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                result = AdvancedCacheConfig._get_env_bool("TEST_BOOL", False)
                assert result is True, f"Failed for value: {value}"

    def test_get_env_bool_false_values(self):
        """Test _get_env_bool with various false values."""
        false_values = ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF", "anything_else"]

        for value in false_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}):
                result = AdvancedCacheConfig._get_env_bool("TEST_BOOL", True)
                assert result is False, f"Failed for value: {value}"

    def test_get_env_bool_default(self):
        """Test _get_env_bool with missing environment variable."""
        with patch.dict(os.environ, {}, clear=True):
            result = AdvancedCacheConfig._get_env_bool("MISSING_VAR", True)
            assert result is True

            result = AdvancedCacheConfig._get_env_bool("MISSING_VAR", False)
            assert result is False

    def test_get_env_int_valid_values(self):
        """Test _get_env_int with valid integer values."""
        test_values = ["0", "42", "-10", "3600"]
        expected_values = [0, 42, -10, 3600]

        for env_value, expected in zip(test_values, expected_values):
            with patch.dict(os.environ, {"TEST_INT": env_value}):
                result = AdvancedCacheConfig._get_env_int("TEST_INT", 999)
                assert result == expected

    def test_get_env_int_invalid_values(self):
        """Test _get_env_int with invalid integer values."""
        invalid_values = ["not_a_number", "3.14", ""]

        with patch("src.awsideman.cache.config.logger") as mock_logger:
            for value in invalid_values:
                with patch.dict(os.environ, {"TEST_INT": value}):
                    result = AdvancedCacheConfig._get_env_int("TEST_INT", 999)
                    assert result == 999  # Should return default
                    mock_logger.warning.assert_called()

    def test_get_env_int_default(self):
        """Test _get_env_int with missing environment variable."""
        with patch.dict(os.environ, {}, clear=True):
            result = AdvancedCacheConfig._get_env_int("MISSING_VAR", 42)
            assert result == 42
