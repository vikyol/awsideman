"""Tests for rollback configuration in Config class."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.awsideman.utils.config import DEFAULT_ROLLBACK_CONFIG, Config


class TestRollbackConfig:
    """Test rollback configuration functionality."""

    def setup_method(self):
        """Setup test method with temporary config directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.temp_dir) / ".awsideman"
        self.config_file = self.config_dir / "config.yaml"

        # Create the config object first
        self.config = Config()

        # Then patch the instance methods to use our test paths
        self.config._config_dir = self.config_dir
        self.config._config_file_yaml = self.config_file
        self.config._config_dir_ensured = False
        self.config._config_loaded = False

    def test_get_rollback_config_defaults(self):
        """Test getting rollback config with defaults."""
        rollback_config = self.config.get_rollback_config()

        assert rollback_config["enabled"] is True
        assert rollback_config["storage_directory"] == os.path.expanduser("~/.awsideman/operations")
        assert rollback_config["retention_days"] == 90
        assert rollback_config["auto_cleanup"] is True
        assert rollback_config["max_operations"] == 10000
        assert rollback_config["confirmation_required"] is True
        assert rollback_config["dry_run_default"] is False

    def test_get_rollback_config_from_file(self):
        """Test getting rollback config from file."""
        # Create a config file with rollback data
        config_data = {
            "rollback": {
                "enabled": False,
                "storage_directory": "/custom/path",
                "retention_days": 30,
                "auto_cleanup": False,
                "max_operations": 5000,
                "confirmation_required": False,
                "dry_run_default": True,
            }
        }

        # Write config to file
        import yaml

        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            yaml.dump(config_data, f)

        # Clear any existing environment variables that might override config
        with patch.dict(os.environ, {}, clear=True):
            # Reload config from file
            self.config.reload_config()
            rollback_config = self.config.get_rollback_config()

            assert rollback_config["enabled"] is False
            assert rollback_config["storage_directory"] == "/custom/path"
            assert rollback_config["retention_days"] == 30
            assert rollback_config["auto_cleanup"] is False
            assert rollback_config["max_operations"] == 5000
            assert rollback_config["confirmation_required"] is False
            assert rollback_config["dry_run_default"] is True

    @patch.dict(
        os.environ,
        {
            "AWSIDEMAN_ROLLBACK_ENABLED": "false",
            "AWSIDEMAN_ROLLBACK_RETENTION_DAYS": "60",
            "AWSIDEMAN_ROLLBACK_MAX_OPERATIONS": "20000",
            "AWSIDEMAN_ROLLBACK_AUTO_CLEANUP": "false",
            "AWSIDEMAN_ROLLBACK_CONFIRMATION_REQUIRED": "false",
            "AWSIDEMAN_ROLLBACK_DRY_RUN_DEFAULT": "true",
            "AWSIDEMAN_ROLLBACK_STORAGE_DIRECTORY": "/env/path",
        },
    )
    def test_get_rollback_config_environment_overrides(self):
        """Test rollback config with environment variable overrides."""
        rollback_config = self.config.get_rollback_config()

        assert rollback_config["enabled"] is False
        assert rollback_config["storage_directory"] == "/env/path"
        assert rollback_config["retention_days"] == 60
        assert rollback_config["auto_cleanup"] is False
        assert rollback_config["max_operations"] == 20000
        assert rollback_config["confirmation_required"] is False
        assert rollback_config["dry_run_default"] is True

    @patch.dict(os.environ, {"AWSIDEMAN_ROLLBACK_STORAGE_DIRECTORY": "~/custom/operations"})
    def test_get_rollback_config_path_expansion(self):
        """Test storage directory path expansion."""
        rollback_config = self.config.get_rollback_config()

        expected_path = os.path.expanduser("~/custom/operations")
        assert rollback_config["storage_directory"] == expected_path

    def test_set_rollback_config(self):
        """Test setting rollback configuration."""
        new_config = {
            "enabled": False,
            "storage_directory": "/new/path",
            "retention_days": 45,
            "auto_cleanup": False,
            "max_operations": 15000,
            "confirmation_required": False,
            "dry_run_default": True,
        }

        with patch.object(self.config, "save_config") as mock_save:
            self.config.set_rollback_config(new_config)

            assert self.config.config_data["rollback"] == new_config
            mock_save.assert_called_once()

    def test_validate_rollback_config_valid(self):
        """Test validation of valid rollback config."""
        # Use a temporary directory that we know exists and is writable
        valid_config = {
            "enabled": True,
            "storage_directory": self.temp_dir,
            "retention_days": 90,
            "auto_cleanup": True,
            "max_operations": 10000,
            "confirmation_required": True,
            "dry_run_default": False,
        }

        errors = self.config.validate_rollback_config(valid_config)
        assert errors == []

    def test_validate_rollback_config_invalid_retention_days(self):
        """Test validation with invalid retention_days."""
        # Test negative value
        config = DEFAULT_ROLLBACK_CONFIG.copy()
        config["retention_days"] = -1
        errors = self.config.validate_rollback_config(config)
        assert any("retention_days must be a positive integer" in error for error in errors)

        # Test zero value
        config["retention_days"] = 0
        errors = self.config.validate_rollback_config(config)
        assert any("retention_days must be a positive integer" in error for error in errors)

        # Test too large value
        config["retention_days"] = 4000
        errors = self.config.validate_rollback_config(config)
        assert any("retention_days cannot exceed 3650 days" in error for error in errors)

        # Test non-integer value
        config["retention_days"] = "invalid"
        errors = self.config.validate_rollback_config(config)
        assert any("retention_days must be a positive integer" in error for error in errors)

    def test_validate_rollback_config_invalid_max_operations(self):
        """Test validation with invalid max_operations."""
        # Test too small value
        config = DEFAULT_ROLLBACK_CONFIG.copy()
        config["max_operations"] = 50
        errors = self.config.validate_rollback_config(config)
        assert any("max_operations must be an integer >= 100" in error for error in errors)

        # Test too large value
        config["max_operations"] = 2000000
        errors = self.config.validate_rollback_config(config)
        assert any("max_operations cannot exceed 1,000,000" in error for error in errors)

        # Test non-integer value
        config["max_operations"] = "invalid"
        errors = self.config.validate_rollback_config(config)
        assert any("max_operations must be an integer >= 100" in error for error in errors)

    def test_validate_rollback_config_invalid_storage_directory(self):
        """Test validation with invalid storage_directory."""
        # Test empty storage directory
        config = DEFAULT_ROLLBACK_CONFIG.copy()
        config["storage_directory"] = ""
        errors = self.config.validate_rollback_config(config)
        assert any("storage_directory is required" in error for error in errors)

        # Test None storage directory
        config["storage_directory"] = None
        errors = self.config.validate_rollback_config(config)
        assert any("storage_directory is required" in error for error in errors)

    def test_validate_rollback_config_invalid_boolean_fields(self):
        """Test validation with invalid boolean fields."""
        config = DEFAULT_ROLLBACK_CONFIG.copy()

        # Test invalid enabled field
        config["enabled"] = "not_a_boolean"
        errors = self.config.validate_rollback_config(config)
        assert any("enabled must be a boolean value" in error for error in errors)

        # Test invalid auto_cleanup field
        config = DEFAULT_ROLLBACK_CONFIG.copy()
        config["auto_cleanup"] = "not_a_boolean"
        errors = self.config.validate_rollback_config(config)
        assert any("auto_cleanup must be a boolean value" in error for error in errors)

        # Test invalid confirmation_required field
        config = DEFAULT_ROLLBACK_CONFIG.copy()
        config["confirmation_required"] = "not_a_boolean"
        errors = self.config.validate_rollback_config(config)
        assert any("confirmation_required must be a boolean value" in error for error in errors)

        # Test invalid dry_run_default field
        config = DEFAULT_ROLLBACK_CONFIG.copy()
        config["dry_run_default"] = "not_a_boolean"
        errors = self.config.validate_rollback_config(config)
        assert any("dry_run_default must be a boolean value" in error for error in errors)

    def test_validate_rollback_config_multiple_errors(self):
        """Test validation with multiple errors."""
        invalid_config = {
            "enabled": "not_boolean",
            "storage_directory": "",
            "retention_days": -5,
            "auto_cleanup": "not_boolean",
            "max_operations": 50,
            "confirmation_required": "not_boolean",
            "dry_run_default": "not_boolean",
        }

        errors = self.config.validate_rollback_config(invalid_config)

        # Should have multiple errors
        assert len(errors) >= 6
        assert any("enabled must be a boolean value" in error for error in errors)
        assert any("storage_directory is required" in error for error in errors)
        assert any("retention_days must be a positive integer" in error for error in errors)
        assert any("auto_cleanup must be a boolean value" in error for error in errors)
        assert any("max_operations must be an integer >= 100" in error for error in errors)
        assert any("confirmation_required must be a boolean value" in error for error in errors)
        assert any("dry_run_default must be a boolean value" in error for error in errors)

    def test_validate_rollback_config_none_uses_current(self):
        """Test validation with None parameter uses current config."""
        # Create a config file with invalid rollback data
        config_data = {"rollback": {"retention_days": -1}}

        # Write config to file
        import yaml

        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            yaml.dump(config_data, f)

        # Clear any existing environment variables that might override config
        with patch.dict(os.environ, {}, clear=True):
            # Reload config from file
            self.config.reload_config()
            errors = self.config.validate_rollback_config(None)
            assert any("retention_days must be a positive integer" in error for error in errors)

    def test_migration_includes_rollback_config(self):
        """Test that migration includes rollback configuration."""
        json_data = {
            "profiles": {"default": {}},
            "cache": {"enabled": True},
            "rollback": {"enabled": False, "retention_days": 30},
        }

        yaml_data = self.config._migrate_json_to_yaml_structure(json_data)

        assert "rollback" in yaml_data
        assert yaml_data["rollback"]["enabled"] is False
        assert yaml_data["rollback"]["retention_days"] == 30

    def test_migration_creates_default_rollback_config(self):
        """Test that migration creates default rollback config when missing."""
        json_data = {"profiles": {"default": {}}, "cache": {"enabled": True}}

        yaml_data = self.config._migrate_json_to_yaml_structure(json_data)

        assert "rollback" in yaml_data
        assert yaml_data["rollback"] == DEFAULT_ROLLBACK_CONFIG

    @patch.dict(os.environ, {"AWSIDEMAN_ROLLBACK_ENABLED": "invalid_bool"})
    def test_get_rollback_config_invalid_env_bool(self):
        """Test rollback config with invalid boolean environment variable."""
        # Invalid boolean values are treated as False
        rollback_config = self.config.get_rollback_config()
        assert rollback_config["enabled"] is False

    @patch.dict(os.environ, {"AWSIDEMAN_ROLLBACK_RETENTION_DAYS": "invalid_int"})
    def test_get_rollback_config_invalid_env_int(self):
        """Test rollback config with invalid integer environment variable."""
        # Should use default value when env var is invalid
        rollback_config = self.config.get_rollback_config()
        assert rollback_config["retention_days"] == 90  # Default value

    def test_rollback_config_boundary_values(self):
        """Test rollback config validation with boundary values."""
        # Test minimum valid values
        config = DEFAULT_ROLLBACK_CONFIG.copy()
        config["retention_days"] = 1
        config["max_operations"] = 100
        errors = self.config.validate_rollback_config(config)
        assert errors == []

        # Test maximum valid values
        config["retention_days"] = 3650
        config["max_operations"] = 1000000
        errors = self.config.validate_rollback_config(config)
        assert errors == []


if __name__ == "__main__":
    pytest.main([__file__])
