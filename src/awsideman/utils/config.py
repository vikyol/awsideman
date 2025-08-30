"""Configuration utilities for awsideman."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

console = Console()

CONFIG_DIR = Path.home() / ".awsideman"
CONFIG_FILE_YAML = CONFIG_DIR / "config.yaml"
CONFIG_FILE_JSON = CONFIG_DIR / "config.json"  # Legacy support

# Default cache configuration
DEFAULT_CACHE_CONFIG = {
    "enabled": True,
    "default_ttl": 3600,  # 1 hour
    "operation_ttls": {
        "list_users": 3600,  # 1 hour
        "list_groups": 3600,  # 1 hour
        "list_permission_sets": 7200,  # 2 hours
        "describe_user": 1800,  # 30 minutes
        "describe_group": 1800,  # 30 minutes
        "describe_permission_set": 1800,  # 30 minutes
        "list_accounts": 7200,  # 2 hours
        "describe_account": 43200,  # 12 hours (account data rarely changes)
        "list_account_assignments": 1800,  # 30 minutes
        # Organization structure operations - cache for longer since they rarely change
        "list_roots": 86400,  # 24 hours
        "list_organizational_units_for_parent": 86400,  # 24 hours
        "list_accounts_for_parent": 86400,  # 24 hours
        "list_tags_for_resource": 43200,  # 12 hours (tags change infrequently)
        "list_parents": 86400,  # 24 hours
        "list_policies_for_target": 43200,  # 12 hours
    },
    "max_size_mb": 100,
}

# Default rollback configuration
DEFAULT_ROLLBACK_CONFIG = {
    "enabled": True,
    "storage_directory": "~/.awsideman/operations",
    "retention_days": 90,
    "auto_cleanup": True,
    "max_operations": 10000,
    "confirmation_required": True,
    "dry_run_default": False,
    "verification": {
        "enabled": True,  # Whether to perform post-rollback verification
        "delay_seconds": 10,  # Wait time before verification
        "max_retries": 3,  # Maximum verification attempts
        "retry_delay_seconds": 5,  # Initial delay between retries
    },
}

# Default template configuration
DEFAULT_TEMPLATE_CONFIG = {
    "storage_directory": "~/.awsideman/templates",
    "default_format": "yaml",
    "validation": {
        "strict_mode": True,
        "require_metadata": False,
    },
    "execution": {
        "default_dry_run": False,
        "parallel_execution": True,
        "batch_size": 10,
    },
}

# Default backup configuration
DEFAULT_BACKUP_CONFIG = {
    "storage": {
        "default_backend": "filesystem",  # Options: "filesystem", "s3"
        "filesystem": {
            "path": "~/.awsideman/backups",
        },
        "s3": {
            "bucket": None,  # Must be configured by user
            "prefix": "backups",
            "region": None,  # Will use profile region if not specified
        },
    },
    "encryption": {
        "enabled": True,
        "type": "aes256",  # Options: "none", "aes256"
    },
    "compression": {
        "enabled": True,
        "type": "gzip",  # Options: "none", "gzip"
    },
    "defaults": {
        "backup_type": "full",  # Options: "full", "incremental"
        "include_inactive_users": False,
        "resource_types": "all",  # Options: "all", "users", "groups", "permission_sets", "assignments"
    },
    "retention": {
        "keep_daily": 7,
        "keep_weekly": 4,
        "keep_monthly": 12,
        "auto_cleanup": True,
    },
    "performance": {
        "deduplication_enabled": True,
        "parallel_processing_enabled": True,
        "resource_monitoring_enabled": True,
        "max_workers": 8,
    },
}


class Config:
    """Manages awsideman configuration with unified YAML support."""

    def __init__(self):
        """Initialize the configuration manager."""
        self.config_data = {}
        self._config_loaded = False
        self._config_dir_ensured = False

    def _ensure_config_dir(self):
        """Ensure the configuration directory exists."""
        if not self._config_dir_ensured:
            config_dir = getattr(self, "_config_dir", CONFIG_DIR)
            if not config_dir.exists():
                config_dir.mkdir(parents=True)
                console.print(f"Created configuration directory: {config_dir}")
            self._config_dir_ensured = True

    def _ensure_config_loaded(self):
        """Ensure configuration is loaded from file."""
        if not self._config_loaded:
            self._ensure_config_dir()
            self._load_config()
            self._config_loaded = True

    def reload_config(self):
        """Force reload configuration from file."""
        self._config_loaded = False
        self._ensure_config_loaded()

    def _load_config(self):
        """Load the configuration from file, with automatic migration from JSON to YAML."""
        config_file_yaml = getattr(self, "_config_file_yaml", CONFIG_FILE_YAML)
        config_file_json = getattr(self, "_config_file_json", CONFIG_FILE_JSON)

        # Try to load YAML config first
        if config_file_yaml.exists():
            self._load_yaml_config()
        # If no YAML config, try to load and migrate JSON config
        elif config_file_json.exists():
            self._load_and_migrate_json_config()
        else:
            self.config_data = {}

    def _load_yaml_config(self):
        """Load configuration from YAML file."""
        if not YAML_AVAILABLE:
            console.print(
                "[yellow]Warning: PyYAML not available. Cannot load YAML config. Please install PyYAML.[/yellow]"
            )
            self.config_data = {}
            return

        config_file_yaml = getattr(self, "_config_file_yaml", CONFIG_FILE_YAML)
        try:
            with open(config_file_yaml, "r", encoding="utf-8") as f:
                self.config_data = yaml.safe_load(f) or {}

            # Post-process configuration to expand tilde paths
            self._expand_tilde_paths()

        except yaml.YAMLError as e:
            console.print(
                f"[red]Error: Configuration file {config_file_yaml} is not valid YAML: {e}[/red]"
            )
            self.config_data = {}
        except Exception as e:
            console.print(f"[red]Error reading configuration file {config_file_yaml}: {e}[/red]")
            self.config_data = {}

    def _expand_tilde_paths(self):
        """Expand tilde (~) paths in configuration to actual home directory paths."""
        try:
            # Expand tilde paths in cache configuration
            if "cache" in self.config_data and isinstance(self.config_data["cache"], dict):
                cache_config = self.config_data["cache"]
                if "file_cache_dir" in cache_config and isinstance(
                    cache_config["file_cache_dir"], str
                ):
                    cache_config["file_cache_dir"] = str(
                        Path(cache_config["file_cache_dir"]).expanduser()
                    )

            # Expand tilde paths in other configuration sections that might have paths
            for section_name, section_data in self.config_data.items():
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        if isinstance(value, str) and value.startswith("~"):
                            section_data[key] = str(Path(value).expanduser())

        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not expand tilde paths in configuration: {e}[/yellow]"
            )

    def _load_and_migrate_json_config(self):
        """Load JSON config and migrate to YAML format."""
        config_file_json = getattr(self, "_config_file_json", CONFIG_FILE_JSON)
        try:
            with open(config_file_json, "r") as f:
                json_data = json.load(f)

            console.print("[blue]Migrating configuration from JSON to YAML format...[/blue]")

            # Migrate the data structure
            self.config_data = self._migrate_json_to_yaml_structure(json_data)

            # Save as YAML
            self.save_config()

            # Create backup of old JSON file
            backup_file = config_file_json.with_suffix(".json.backup")
            config_file_json.rename(backup_file)
            console.print(
                f"[green]Configuration migrated to YAML format. JSON backup saved as {backup_file}[/green]"
            )

        except json.JSONDecodeError as e:
            console.print(
                f"[red]Error: Configuration file {CONFIG_FILE_JSON} is not valid JSON: {e}[/red]"
            )
            self.config_data = {}
        except Exception as e:
            console.print(f"[red]Error migrating configuration: {e}[/red]")
            self.config_data = {}

    def _migrate_json_to_yaml_structure(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate JSON configuration structure to YAML structure.

        Args:
            json_data: Original JSON configuration data

        Returns:
            Migrated YAML configuration structure
        """
        yaml_data = {}

        # Migrate profiles
        if "profiles" in json_data:
            yaml_data["profiles"] = json_data["profiles"]

        # Migrate default profile
        if "default_profile" in json_data:
            yaml_data["default_profile"] = json_data["default_profile"]

        # Migrate cache configuration
        if "cache" in json_data:
            yaml_data["cache"] = json_data["cache"]
        else:
            # If no cache config exists, create default
            yaml_data["cache"] = DEFAULT_CACHE_CONFIG.copy()

        # Migrate rollback configuration
        if "rollback" in json_data:
            yaml_data["rollback"] = json_data["rollback"]
        else:
            # If no rollback config exists, create default
            yaml_data["rollback"] = DEFAULT_ROLLBACK_CONFIG.copy()

        # Migrate template configuration
        if "templates" in json_data:
            yaml_data["templates"] = json_data["templates"]
        else:
            # If no template config exists, create default
            yaml_data["templates"] = DEFAULT_TEMPLATE_CONFIG.copy()

        # Migrate backup configuration
        if "backup" in json_data:
            yaml_data["backup"] = json_data["backup"]
        else:
            # If no backup config exists, create default
            yaml_data["backup"] = DEFAULT_BACKUP_CONFIG.copy()

        # Migrate any other top-level configuration
        for key, value in json_data.items():
            if key not in [
                "profiles",
                "default_profile",
                "cache",
                "rollback",
                "templates",
                "backup",
            ]:
                yaml_data[key] = value

        return yaml_data

    def save_config(self):
        """Save the configuration to YAML file."""
        if not YAML_AVAILABLE:
            console.print(
                "[red]Error: PyYAML not available. Cannot save YAML config. Please install PyYAML.[/red]"
            )
            return

        config_file_yaml = getattr(self, "_config_file_yaml", CONFIG_FILE_YAML)
        try:
            with open(config_file_yaml, "w", encoding="utf-8") as f:
                yaml.dump(self.config_data, f, default_flow_style=False, indent=2, sort_keys=False)
            # Don't print save message for every operation to reduce noise
        except Exception as e:
            console.print(f"[red]Error saving configuration: {e}[/red]")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value with dot notation support.

        Args:
            key: Configuration key (supports dot notation like "backup.storage.default_backend")
            default: Default value if key doesn't exist

        Returns:
            Configuration value
        """
        self._ensure_config_loaded()

        # Handle dot notation
        if "." in key:
            keys = key.split(".")
            value = self.config_data
            try:
                for k in keys:
                    if isinstance(value, dict) and k in value:
                        value = value[k]
                    else:
                        return default
                return value
            except (KeyError, TypeError):
                return default

        # Simple key access
        return self.config_data.get(key, default)

    def set(self, key: str, value: Any):
        """
        Set a configuration value.

        Args:
            key: Configuration key
            value: Configuration value
        """
        # Ensure we have the latest config loaded
        self._ensure_config_loaded()

        # Update the specific key
        self.config_data[key] = value

        # Save the updated configuration
        self.save_config()

    def set_section(self, section: str, value: Any):
        """
        Set a configuration section, merging with existing values.

        Args:
            section: Configuration section name
            value: Configuration section value
        """
        # Ensure we have the latest config loaded
        self._ensure_config_loaded()

        # Get existing section data
        existing_section = self.config_data.get(section, {})

        # If the existing section is a dict and the new value is a dict, merge them
        if isinstance(existing_section, dict) and isinstance(value, dict):
            # Deep merge for nested dictionaries
            merged_section = self._deep_merge(existing_section, value)
            self.config_data[section] = merged_section
        else:
            # Otherwise, just replace the section
            self.config_data[section] = value

        # Save the updated configuration
        self.save_config()

    def _deep_merge(self, dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries, preserving existing values.

        Args:
            dict1: Base dictionary
            dict2: Dictionary to merge

        Returns:
            Merged dictionary
        """
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def delete(self, key: str):
        """
        Delete a configuration value.

        Args:
            key: Configuration key
        """
        if key in self.config_data:
            del self.config_data[key]
            self.save_config()

    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration values.

        Returns:
            All configuration values
        """
        self._ensure_config_loaded()
        return self.config_data.copy()

    def get_cache_config(self) -> Dict[str, Any]:
        """
        Get cache configuration with defaults and environment variable overrides.

        Returns:
            Cache configuration dictionary
        """
        self._ensure_config_loaded()
        # Start with default cache config
        cache_config = DEFAULT_CACHE_CONFIG.copy()

        # Override with config file values if they exist
        file_cache_config = self.config_data.get("cache", {})
        if file_cache_config:
            cache_config.update(file_cache_config)
            # Merge operation_ttls instead of replacing
            if "operation_ttls" in file_cache_config:
                cache_config["operation_ttls"].update(file_cache_config["operation_ttls"])

        # Override with environment variables
        cache_config["enabled"] = self._get_env_bool(
            "AWSIDEMAN_CACHE_ENABLED", cache_config["enabled"]
        )
        cache_config["default_ttl"] = self._get_env_int(
            "AWSIDEMAN_CACHE_TTL_DEFAULT", cache_config["default_ttl"]
        )
        cache_config["max_size_mb"] = self._get_env_int(
            "AWSIDEMAN_CACHE_MAX_SIZE_MB", cache_config["max_size_mb"]
        )

        # Override operation-specific TTLs from environment variables
        for operation in cache_config["operation_ttls"]:
            env_var = f"AWSIDEMAN_CACHE_TTL_{operation.upper()}"
            cache_config["operation_ttls"][operation] = self._get_env_int(
                env_var, cache_config["operation_ttls"][operation]
            )

        return cache_config

    def get_rollback_config(self) -> Dict[str, Any]:
        """
        Get rollback configuration with defaults and environment variable overrides.

        Returns:
            Rollback configuration dictionary
        """
        self._ensure_config_loaded()
        # Start with default rollback config
        rollback_config = DEFAULT_ROLLBACK_CONFIG.copy()

        # Override with config file values if they exist
        file_rollback_config = self.config_data.get("rollback", {})
        if file_rollback_config:
            rollback_config.update(file_rollback_config)

        # Override with environment variables
        rollback_config["enabled"] = self._get_env_bool(
            "AWSIDEMAN_ROLLBACK_ENABLED", rollback_config["enabled"]
        )
        rollback_config["retention_days"] = self._get_env_int(
            "AWSIDEMAN_ROLLBACK_RETENTION_DAYS", rollback_config["retention_days"]
        )
        rollback_config["max_operations"] = self._get_env_int(
            "AWSIDEMAN_ROLLBACK_MAX_OPERATIONS", rollback_config["max_operations"]
        )
        rollback_config["auto_cleanup"] = self._get_env_bool(
            "AWSIDEMAN_ROLLBACK_AUTO_CLEANUP", rollback_config["auto_cleanup"]
        )
        rollback_config["confirmation_required"] = self._get_env_bool(
            "AWSIDEMAN_ROLLBACK_CONFIRMATION_REQUIRED", rollback_config["confirmation_required"]
        )
        rollback_config["dry_run_default"] = self._get_env_bool(
            "AWSIDEMAN_ROLLBACK_DRY_RUN_DEFAULT", rollback_config["dry_run_default"]
        )

        # Handle storage directory with path expansion
        storage_dir = os.environ.get(
            "AWSIDEMAN_ROLLBACK_STORAGE_DIRECTORY", rollback_config["storage_directory"]
        )
        rollback_config["storage_directory"] = os.path.expanduser(storage_dir)

        return rollback_config

    def get_template_config(self) -> Dict[str, Any]:
        """
        Get template configuration with defaults and environment variable overrides.

        Returns:
            Template configuration dictionary
        """
        self._ensure_config_loaded()
        # Start with default template config
        template_config = DEFAULT_TEMPLATE_CONFIG.copy()

        # Override with config file values if they exist
        file_template_config = self.config_data.get("templates", {})
        if file_template_config:
            template_config.update(file_template_config)

        # Override with environment variables
        template_config["default_format"] = os.environ.get(
            "AWSIDEMAN_TEMPLATE_DEFAULT_FORMAT", template_config["default_format"]
        )
        template_config["validation"]["strict_mode"] = self._get_env_bool(
            "AWSIDEMAN_TEMPLATE_STRICT_MODE", template_config["validation"]["strict_mode"]
        )
        template_config["validation"]["require_metadata"] = self._get_env_bool(
            "AWSIDEMAN_TEMPLATE_REQUIRE_METADATA", template_config["validation"]["require_metadata"]
        )
        template_config["execution"]["default_dry_run"] = self._get_env_bool(
            "AWSIDEMAN_TEMPLATE_DEFAULT_DRY_RUN", template_config["execution"]["default_dry_run"]
        )
        template_config["execution"]["parallel_execution"] = self._get_env_bool(
            "AWSIDEMAN_TEMPLATE_PARALLEL_EXECUTION",
            template_config["execution"]["parallel_execution"],
        )
        template_config["execution"]["batch_size"] = self._get_env_int(
            "AWSIDEMAN_TEMPLATE_BATCH_SIZE", template_config["execution"]["batch_size"]
        )

        # Handle storage directory with path expansion
        storage_dir = os.environ.get(
            "AWSIDEMAN_TEMPLATE_STORAGE_DIRECTORY", template_config["storage_directory"]
        )
        template_config["storage_directory"] = os.path.expanduser(storage_dir)

        return template_config

    def set_cache_config(self, cache_config: Dict[str, Any]):
        """
        Set cache configuration.

        Args:
            cache_config: Cache configuration dictionary
        """
        self.config_data["cache"] = cache_config
        self.save_config()

    def set_rollback_config(self, rollback_config: Dict[str, Any]):
        """
        Set rollback configuration.

        Args:
            rollback_config: Rollback configuration dictionary
        """
        self.config_data["rollback"] = rollback_config
        self.save_config()

    def set_template_config(self, template_config: Dict[str, Any]):
        """
        Set template configuration.

        Args:
            template_config: Template configuration dictionary
        """
        self.config_data["templates"] = template_config
        self.save_config()

    def _get_env_bool(self, env_var: str, default: bool) -> bool:
        """
        Get boolean value from environment variable.

        Args:
            env_var: Environment variable name
            default: Default value if env var is not set

        Returns:
            Boolean value
        """
        value = os.environ.get(env_var)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def _get_env_int(self, env_var: str, default: int) -> int:
        """
        Get integer value from environment variable.

        Args:
            env_var: Environment variable name
            default: Default value if env var is not set

        Returns:
            Integer value
        """
        value = os.environ.get(env_var)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            console.print(
                f"Warning: Invalid integer value for {env_var}: {value}. Using default: {default}"
            )
            return default

    def validate_rollback_config(
        self, rollback_config: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Validate rollback configuration.

        Args:
            rollback_config: Rollback configuration to validate. If None, uses current config.

        Returns:
            List of validation errors
        """
        if rollback_config is None:
            rollback_config = self.get_rollback_config()

        errors = []

        # Validate retention_days
        retention_days = rollback_config.get("retention_days", 90)
        if not isinstance(retention_days, int) or retention_days < 1:
            errors.append("retention_days must be a positive integer")
        elif retention_days > 3650:  # 10 years
            errors.append("retention_days cannot exceed 3650 days (10 years)")

        # Validate max_operations
        max_operations = rollback_config.get("max_operations", 10000)
        if not isinstance(max_operations, int) or max_operations < 100:
            errors.append("max_operations must be an integer >= 100")
        elif max_operations > 1000000:  # 1 million
            errors.append("max_operations cannot exceed 1,000,000")

        # Validate storage_directory
        storage_dir = rollback_config.get("storage_directory")
        if not storage_dir:
            errors.append("storage_directory is required")
        else:
            try:
                expanded_dir = os.path.expanduser(storage_dir)
                # Check if parent directory exists or can be created
                parent_dir = os.path.dirname(expanded_dir)
                if parent_dir and not os.path.exists(parent_dir):
                    try:
                        os.makedirs(parent_dir, exist_ok=True)
                    except (OSError, PermissionError) as e:
                        errors.append(f"Cannot create storage directory parent '{parent_dir}': {e}")
            except Exception as e:
                errors.append(f"Invalid storage_directory path '{storage_dir}': {e}")

        # Validate boolean fields
        bool_fields = ["enabled", "auto_cleanup", "confirmation_required", "dry_run_default"]
        for field in bool_fields:
            value = rollback_config.get(field)
            if value is not None and not isinstance(value, bool):
                errors.append(f"{field} must be a boolean value")

        return errors

    def validate_template_config(
        self, template_config: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Validate template configuration.

        Args:
            template_config: Template configuration to validate. If None, uses current config.

        Returns:
            List of validation errors
        """
        if template_config is None:
            template_config = self.get_template_config()

        errors = []

        # Validate default_format
        default_format = template_config.get("default_format", "yaml")
        if default_format not in ["yaml", "json"]:
            errors.append("default_format must be 'yaml' or 'json'")

        # Validate validation settings
        validation = template_config.get("validation", {})
        if not isinstance(validation, dict):
            errors.append("validation must be a dictionary")
        else:
            strict_mode = validation.get("strict_mode", True)
            if not isinstance(strict_mode, bool):
                errors.append("validation.strict_mode must be a boolean value")

            require_metadata = validation.get("require_metadata", False)
            if not isinstance(require_metadata, bool):
                errors.append("validation.require_metadata must be a boolean value")

        # Validate execution settings
        execution = template_config.get("execution", {})
        if not isinstance(execution, dict):
            errors.append("execution must be a dictionary")
        else:
            default_dry_run = execution.get("default_dry_run", False)
            if not isinstance(default_dry_run, bool):
                errors.append("execution.default_dry_run must be a boolean value")

            parallel_execution = execution.get("parallel_execution", True)
            if not isinstance(parallel_execution, bool):
                errors.append("execution.parallel_execution must be a boolean value")

            batch_size = execution.get("batch_size", 10)
            if not isinstance(batch_size, int) or batch_size < 1:
                errors.append("execution.batch_size must be a positive integer")
            elif batch_size > 1000:
                errors.append("execution.batch_size cannot exceed 1000")

        # Validate storage_directory
        storage_dir = template_config.get("storage_directory")
        if not storage_dir:
            errors.append("storage_directory is required")
        else:
            try:
                expanded_dir = os.path.expanduser(storage_dir)
                # Check if parent directory exists or can be created
                parent_dir = os.path.dirname(expanded_dir)
                if parent_dir and not os.path.exists(parent_dir):
                    try:
                        os.makedirs(parent_dir, exist_ok=True)
                    except (OSError, PermissionError) as e:
                        errors.append(f"Cannot create storage directory parent '{parent_dir}': {e}")
            except Exception as e:
                errors.append(f"Invalid storage_directory path '{storage_dir}': {e}")

        return errors

    def get_config_file_path(self) -> Path:
        """
        Get the path to the active configuration file.

        Returns:
            Path to the configuration file being used
        """
        if CONFIG_FILE_YAML.exists():
            return CONFIG_FILE_YAML
        elif CONFIG_FILE_JSON.exists():
            return CONFIG_FILE_JSON
        else:
            return CONFIG_FILE_YAML  # Default to YAML for new configs

    def needs_migration(self) -> bool:
        """
        Check if configuration needs migration from JSON to YAML.

        Returns:
            True if migration is needed, False otherwise
        """
        return CONFIG_FILE_JSON.exists() and not CONFIG_FILE_YAML.exists()

    def migrate_to_yaml(self) -> bool:
        """
        Manually trigger migration from JSON to YAML.

        Returns:
            True if migration was successful, False otherwise
        """
        if not self.needs_migration():
            return True  # Already migrated or no migration needed

        try:
            self._load_and_migrate_json_config()
            return True
        except Exception as e:
            console.print(f"[red]Migration failed: {e}[/red]")
            return False
