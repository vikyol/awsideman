"""Configuration utilities for awsideman."""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from rich.console import Console

console = Console()

CONFIG_DIR = Path.home() / ".awsideman"
CONFIG_FILE = CONFIG_DIR / "config.json"


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