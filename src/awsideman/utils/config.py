"""Configuration utilities for awsideman."""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
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
        "describe_account": 3600,  # 1 hour
        "list_account_assignments": 1800,  # 30 minutes
    },
    "max_size_mb": 100
}


class Config:
    """Manages awsideman configuration with unified YAML support."""
    
    def __init__(self):
        """Initialize the configuration manager."""
        self.config_data = {}
        self._ensure_config_dir()
        self._load_config()
        
    def _ensure_config_dir(self):
        """Ensure the configuration directory exists."""
        if not CONFIG_DIR.exists():
            CONFIG_DIR.mkdir(parents=True)
            console.print(f"Created configuration directory: {CONFIG_DIR}")
    
    def _load_config(self):
        """Load the configuration from file, with automatic migration from JSON to YAML."""
        # Try to load YAML config first
        if CONFIG_FILE_YAML.exists():
            self._load_yaml_config()
        # If no YAML config, try to load and migrate JSON config
        elif CONFIG_FILE_JSON.exists():
            self._load_and_migrate_json_config()
        else:
            self.config_data = {}
    
    def _load_yaml_config(self):
        """Load configuration from YAML file."""
        if not YAML_AVAILABLE:
            console.print(f"[yellow]Warning: PyYAML not available. Cannot load YAML config. Please install PyYAML.[/yellow]")
            self.config_data = {}
            return
        
        try:
            with open(CONFIG_FILE_YAML, "r", encoding="utf-8") as f:
                self.config_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            console.print(f"[red]Error: Configuration file {CONFIG_FILE_YAML} is not valid YAML: {e}[/red]")
            self.config_data = {}
        except Exception as e:
            console.print(f"[red]Error reading configuration file {CONFIG_FILE_YAML}: {e}[/red]")
            self.config_data = {}
    
    def _load_and_migrate_json_config(self):
        """Load JSON config and migrate to YAML format."""
        try:
            with open(CONFIG_FILE_JSON, "r") as f:
                json_data = json.load(f)
            
            console.print(f"[blue]Migrating configuration from JSON to YAML format...[/blue]")
            
            # Migrate the data structure
            self.config_data = self._migrate_json_to_yaml_structure(json_data)
            
            # Save as YAML
            self.save_config()
            
            # Create backup of old JSON file
            backup_file = CONFIG_FILE_JSON.with_suffix('.json.backup')
            CONFIG_FILE_JSON.rename(backup_file)
            console.print(f"[green]Configuration migrated to YAML format. JSON backup saved as {backup_file}[/green]")
            
        except json.JSONDecodeError as e:
            console.print(f"[red]Error: Configuration file {CONFIG_FILE_JSON} is not valid JSON: {e}[/red]")
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
        
        # Migrate any other top-level configuration
        for key, value in json_data.items():
            if key not in ["profiles", "default_profile", "cache"]:
                yaml_data[key] = value
        
        return yaml_data
    
    def save_config(self):
        """Save the configuration to YAML file."""
        if not YAML_AVAILABLE:
            console.print(f"[red]Error: PyYAML not available. Cannot save YAML config. Please install PyYAML.[/red]")
            return
        
        try:
            with open(CONFIG_FILE_YAML, "w", encoding="utf-8") as f:
                yaml.dump(self.config_data, f, default_flow_style=False, indent=2, sort_keys=False)
            # Don't print save message for every operation to reduce noise
        except Exception as e:
            console.print(f"[red]Error saving configuration: {e}[/red]")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key doesn't exist
            
        Returns:
            Configuration value
        """
        return self.config_data.get(key, default)
    
    def set(self, key: str, value: Any):
        """
        Set a configuration value.
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        self.config_data[key] = value
        self.save_config()
    
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
        return self.config_data.copy()
    
    def get_cache_config(self) -> Dict[str, Any]:
        """
        Get cache configuration with defaults and environment variable overrides.
        
        Returns:
            Cache configuration dictionary
        """
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
        cache_config["enabled"] = self._get_env_bool("AWSIDEMAN_CACHE_ENABLED", cache_config["enabled"])
        cache_config["default_ttl"] = self._get_env_int("AWSIDEMAN_CACHE_TTL_DEFAULT", cache_config["default_ttl"])
        cache_config["max_size_mb"] = self._get_env_int("AWSIDEMAN_CACHE_MAX_SIZE_MB", cache_config["max_size_mb"])
        
        # Override operation-specific TTLs from environment variables
        for operation in cache_config["operation_ttls"]:
            env_var = f"AWSIDEMAN_CACHE_TTL_{operation.upper()}"
            cache_config["operation_ttls"][operation] = self._get_env_int(
                env_var, cache_config["operation_ttls"][operation]
            )
        
        return cache_config
    
    def set_cache_config(self, cache_config: Dict[str, Any]):
        """
        Set cache configuration.
        
        Args:
            cache_config: Cache configuration dictionary
        """
        self.config_data["cache"] = cache_config
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
            console.print(f"Warning: Invalid integer value for {env_var}: {value}. Using default: {default}")
            return default
    
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