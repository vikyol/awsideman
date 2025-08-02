"""Configuration utilities for awsideman."""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console

console = Console()

CONFIG_DIR = Path.home() / ".awsideman"
CONFIG_FILE = CONFIG_DIR / "config.json"

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
    """Manages awsideman configuration."""
    
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
        """Load the configuration from file."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config_data = json.load(f)
            except json.JSONDecodeError:
                console.print(f"Error: Configuration file {CONFIG_FILE} is not valid JSON.")
                self.config_data = {}
        else:
            self.config_data = {}
    
    def save_config(self):
        """Save the configuration to file."""
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config_data, f, indent=2)
        console.print(f"Configuration saved to {CONFIG_FILE}")
    
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