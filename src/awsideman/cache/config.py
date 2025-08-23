"""Advanced cache configuration for enhanced cache features."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.models import CacheConfig

logger = logging.getLogger(__name__)


@dataclass
class ProfileCacheConfig:
    """
    Profile-specific cache configuration.

    This allows each AWS profile to have its own cache configuration,
    including different backend types, DynamoDB tables, and file paths.
    """

    # Profile name this configuration applies to
    profile_name: str

    # Backend configuration
    backend_type: str = "file"  # "file", "dynamodb", "hybrid"

    # DynamoDB configuration (only used if backend_type is "dynamodb" or "hybrid")
    dynamodb_table_name: Optional[str] = None
    dynamodb_region: Optional[str] = None
    dynamodb_profile: Optional[str] = None

    # File backend configuration (only used if backend_type is "file" or "hybrid")
    file_cache_dir: Optional[str] = None

    # Encryption configuration
    encryption_enabled: bool = False
    encryption_type: str = "aes256"  # "none", "aes256"

    # Cache behavior configuration
    enabled: bool = True
    default_ttl: int = 3600  # 1 hour
    max_size_mb: int = 100

    # Operation-specific TTLs
    operation_ttls: Optional[Dict[str, int]] = None

    # Hybrid backend configuration
    hybrid_local_ttl: int = 300  # 5 minutes local cache for hybrid mode

    def __post_init__(self):
        """Post-initialization validation and setup."""
        # Initialize operation_ttls if not provided
        if self.operation_ttls is None:
            self.operation_ttls = {}

        # Validate backend type
        valid_backends = ["file", "dynamodb", "hybrid"]
        if self.backend_type not in valid_backends:
            logger.warning(
                f"Invalid backend type '{self.backend_type}' for profile {self.profile_name}, defaulting to 'file'"
            )
            self.backend_type = "file"

        # Validate encryption type
        valid_encryption_types = ["none", "aes256"]
        if self.encryption_type not in valid_encryption_types:
            logger.warning(
                f"Invalid encryption type '{self.encryption_type}' for profile {self.profile_name}, defaulting to 'aes256'"
            )
            self.encryption_type = "aes256"

        # If encryption is disabled, set type to none
        if not self.encryption_enabled:
            self.encryption_type = "none"

        # Validate DynamoDB configuration for DynamoDB backends
        if self.backend_type in ["dynamodb", "hybrid"]:
            if not self.dynamodb_table_name:
                logger.warning(
                    f"No DynamoDB table name specified for profile {self.profile_name} with {self.backend_type} backend"
                )

        # Validate file configuration for file backends
        if self.backend_type in ["file", "hybrid"]:
            if not self.file_cache_dir:
                # Use default file cache directory
                self.file_cache_dir = str(Path.home() / ".awsideman" / "cache" / self.profile_name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "profile_name": self.profile_name,
            "backend_type": self.backend_type,
            "dynamodb_table_name": self.dynamodb_table_name,
            "dynamodb_region": self.dynamodb_region,
            "dynamodb_profile": self.dynamodb_profile,
            "file_cache_dir": self.file_cache_dir,
            "encryption_enabled": self.encryption_enabled,
            "encryption_type": self.encryption_type,
            "enabled": self.enabled,
            "default_ttl": self.default_ttl,
            "max_size_mb": self.max_size_mb,
            "operation_ttls": self.operation_ttls.copy() if self.operation_ttls else {},
            "hybrid_local_ttl": self.hybrid_local_ttl,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], profile_name: str = None) -> "ProfileCacheConfig":
        """Create ProfileCacheConfig from dictionary."""
        # Ensure profile_name is set
        if profile_name and "profile_name" not in data:
            data["profile_name"] = profile_name
        return cls(**data)


@dataclass
class AdvancedCacheConfig(CacheConfig):
    """
    Advanced cache configuration extending the base CacheConfig.

    Adds support for backend selection, encryption, and DynamoDB configuration
    while maintaining backward compatibility with existing cache settings.

    Now also supports profile-specific configurations.
    """

    # Backend configuration
    backend_type: str = "file"  # "file", "dynamodb", "hybrid"

    # DynamoDB configuration
    dynamodb_table_name: str = "awsideman-cache"
    dynamodb_region: Optional[str] = None
    dynamodb_profile: Optional[str] = None

    # Encryption configuration
    encryption_enabled: bool = False
    encryption_type: str = "aes256"  # "none", "aes256"

    # Hybrid backend configuration
    hybrid_local_ttl: int = 300  # 5 minutes local cache for hybrid mode

    # File backend specific configuration
    file_cache_dir: Optional[str] = None

    # Profile-specific cache configurations
    profile_configs: Optional[Dict[str, ProfileCacheConfig]] = None

    def __post_init__(self):
        """Post-initialization validation and setup."""
        # Initialize operation_ttls if not provided
        if not hasattr(self, "operation_ttls") or self.operation_ttls is None:
            self.operation_ttls = {}

        # Initialize profile_configs if not provided
        if self.profile_configs is None:
            self.profile_configs = {}

        # Validate backend type (but don't auto-correct in __post_init__)
        valid_backends = ["file", "dynamodb", "hybrid"]
        if self.backend_type not in valid_backends:
            logger.warning(f"Invalid backend type '{self.backend_type}', will need correction")

        # Validate encryption type
        valid_encryption_types = ["none", "aes256"]
        if self.encryption_type not in valid_encryption_types:
            logger.warning(
                f"Invalid encryption type '{self.encryption_type}', defaulting to 'aes256'"
            )
            self.encryption_type = "aes256"

        # If encryption is disabled, set type to none
        if not self.encryption_enabled:
            self.encryption_type = "none"

    def get_profile_config(self, profile_name: str) -> "ProfileCacheConfig":
        """
        Get cache configuration for a specific profile.

        Args:
            profile_name: Name of the AWS profile

        Returns:
            ProfileCacheConfig for the specified profile, or default config if not found
        """
        if profile_name in self.profile_configs:
            return self.profile_configs[profile_name]

        # Return default configuration for this profile
        return ProfileCacheConfig(
            profile_name=profile_name,
            backend_type=self.backend_type,
            dynamodb_table_name=self.dynamodb_table_name,
            dynamodb_region=self.dynamodb_region,
            dynamodb_profile=self.dynamodb_profile,
            file_cache_dir=self.file_cache_dir,
            encryption_enabled=self.encryption_enabled,
            encryption_type=self.encryption_type,
            enabled=self.enabled,
            default_ttl=self.default_ttl,
            max_size_mb=self.max_size_mb,
            operation_ttls=self.operation_ttls.copy() if self.operation_ttls else {},
            hybrid_local_ttl=self.hybrid_local_ttl,
        )

    @classmethod
    def from_config_file(cls, config_path: Optional[str] = None) -> "AdvancedCacheConfig":
        """
        Load configuration from unified YAML config file.

        Args:
            config_path: Optional path to config file. If None, uses default location.

        Returns:
            AdvancedCacheConfig instance loaded from file
        """
        # Use the unified config system
        from ..utils.config import Config

        config = Config()
        cache_config_data = config.get_cache_config()

        # Convert basic cache config to advanced cache config format
        advanced_config_data = {
            "enabled": cache_config_data.get("enabled", True),
            "default_ttl": cache_config_data.get("default_ttl", 3600),
            "operation_ttls": cache_config_data.get("operation_ttls", {}),
            "max_size_mb": cache_config_data.get("max_size_mb", 100),
        }

        # Add advanced configuration if present in the unified config
        all_config_data = config.get_all()
        if "cache" in all_config_data and isinstance(all_config_data["cache"], dict):
            cache_section = all_config_data["cache"]

            # Add advanced settings if they exist
            for key in [
                "backend_type",
                "encryption_enabled",
                "encryption_type",
                "dynamodb_table_name",
                "dynamodb_region",
                "dynamodb_profile",
                "hybrid_local_ttl",
                "file_cache_dir",
            ]:
                if key in cache_section:
                    advanced_config_data[key] = cache_section[key]

            # Load profile-specific configurations
            profile_configs = {}
            if "profiles" in cache_section and isinstance(cache_section["profiles"], dict):
                for profile_name, profile_config in cache_section["profiles"].items():
                    if isinstance(profile_config, dict):
                        try:
                            profile_configs[profile_name] = ProfileCacheConfig.from_dict(
                                profile_config, profile_name
                            )
                            logger.debug(f"Loaded cache config for profile: {profile_name}")
                        except Exception as e:
                            logger.warning(
                                f"Failed to load cache config for profile {profile_name}: {e}"
                            )

            if profile_configs:
                advanced_config_data["profile_configs"] = profile_configs

        # Auto-configure DynamoDB profile if not specified
        if (
            advanced_config_data.get("backend_type") in ["dynamodb", "hybrid"]
            and "dynamodb_profile" not in advanced_config_data
        ):
            default_profile = config.get("default_profile")
            if default_profile:
                advanced_config_data["dynamodb_profile"] = default_profile
                logger.debug(f"Auto-configured DynamoDB profile to default: {default_profile}")

        logger.debug("Loaded cache configuration from unified config system")
        return cls(**advanced_config_data)

    @classmethod
    def from_environment(cls) -> "AdvancedCacheConfig":
        """
        Load configuration from environment variables.

        Returns:
            AdvancedCacheConfig instance loaded from environment variables
        """
        # Load base cache config from environment
        base_config = {
            "enabled": cls._get_env_bool("AWSIDEMAN_CACHE_ENABLED", True),
            "default_ttl": cls._get_env_int("AWSIDEMAN_CACHE_TTL_DEFAULT", 3600),
            "max_size_mb": cls._get_env_int("AWSIDEMAN_CACHE_MAX_SIZE_MB", 100),
        }

        # Load operation-specific TTLs
        operation_ttls = {}
        for env_var in os.environ:
            if (
                env_var.startswith("AWSIDEMAN_CACHE_TTL_")
                and env_var != "AWSIDEMAN_CACHE_TTL_DEFAULT"
            ):
                operation = env_var.replace("AWSIDEMAN_CACHE_TTL_", "").lower()
                operation_ttls[operation] = cls._get_env_int(env_var, 3600)

        if operation_ttls:
            base_config["operation_ttls"] = operation_ttls

        # Load advanced cache config from environment
        advanced_config = {
            **base_config,
            "backend_type": os.getenv("AWSIDEMAN_CACHE_BACKEND", "file"),
            "encryption_enabled": cls._get_env_bool("AWSIDEMAN_CACHE_ENCRYPTION", False),
            "encryption_type": os.getenv("AWSIDEMAN_CACHE_ENCRYPTION_TYPE", "aes256"),
            "dynamodb_table_name": os.getenv("AWSIDEMAN_CACHE_DYNAMODB_TABLE", "awsideman-cache"),
            "dynamodb_region": os.getenv("AWSIDEMAN_CACHE_DYNAMODB_REGION"),
            "dynamodb_profile": os.getenv("AWSIDEMAN_CACHE_DYNAMODB_PROFILE"),
            "hybrid_local_ttl": cls._get_env_int("AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL", 300),
            "file_cache_dir": os.getenv("AWSIDEMAN_CACHE_FILE_DIR"),
        }

        # Load profile-specific configurations from environment
        profile_configs = {}
        for env_var in os.environ:
            if env_var.startswith("AWSIDEMAN_CACHE_PROFILE_"):
                # Format: AWSIDEMAN_CACHE_PROFILE_<PROFILE_NAME>_<SETTING>
                # Example: AWSIDEMAN_CACHE_PROFILE_PROD_BACKEND_TYPE=dynamodb
                parts = env_var.replace("AWSIDEMAN_CACHE_PROFILE_", "").split("_", 1)
                if len(parts) == 2:
                    profile_name = parts[0].lower()
                    setting = parts[1].lower()
                    value = os.getenv(env_var)

                    if profile_name not in profile_configs:
                        profile_configs[profile_name] = {}

                    # Map environment variable names to config keys
                    setting_mapping = {
                        "backend_type": "backend_type",
                        "dynamodb_table_name": "dynamodb_table_name",
                        "dynamodb_region": "dynamodb_region",
                        "dynamodb_profile": "dynamodb_profile",
                        "file_cache_dir": "file_cache_dir",
                        "encryption_enabled": "encryption_enabled",
                        "encryption_type": "encryption_type",
                        "enabled": "enabled",
                        "default_ttl": "default_ttl",
                        "max_size_mb": "max_size_mb",
                    }

                    if setting in setting_mapping:
                        config_key = setting_mapping[setting]
                        if setting in ["enabled", "encryption_enabled"]:
                            profile_configs[profile_name][config_key] = value.lower() in (
                                "true",
                                "1",
                                "yes",
                                "on",
                            )
                        elif setting in ["default_ttl", "max_size_mb"]:
                            try:
                                profile_configs[profile_name][config_key] = int(value)
                            except (ValueError, TypeError):
                                logger.warning(f"Invalid value for {env_var}: {value}")
                        else:
                            profile_configs[profile_name][config_key] = value

        # Convert profile configs to ProfileCacheConfig objects
        if profile_configs:
            for profile_name, profile_data in profile_configs.items():
                try:
                    profile_data["profile_name"] = profile_name
                    profile_configs[profile_name] = ProfileCacheConfig.from_dict(profile_data)
                except Exception as e:
                    logger.warning(
                        f"Failed to create ProfileCacheConfig for profile {profile_name}: {e}"
                    )
                    del profile_configs[profile_name]

            advanced_config["profile_configs"] = profile_configs

        # Auto-configure DynamoDB profile if not specified in environment
        if advanced_config.get("backend_type") in [
            "dynamodb",
            "hybrid",
        ] and not advanced_config.get("dynamodb_profile"):
            # Try to get default profile from config file
            try:
                from ..utils.config import Config

                config = Config()
                default_profile = config.get("default_profile")
                if default_profile:
                    advanced_config["dynamodb_profile"] = default_profile
                    logger.debug(f"Auto-configured DynamoDB profile to default: {default_profile}")
            except Exception as e:
                logger.debug(f"Could not auto-configure DynamoDB profile: {e}")

        logger.debug("Loaded cache configuration from environment variables")
        return cls(**advanced_config)

    @classmethod
    def from_config_and_environment(
        cls, config_path: Optional[str] = None
    ) -> "AdvancedCacheConfig":
        """
        Load configuration from file first, then override with environment variables.

        Args:
            config_path: Optional path to config file. If None, uses default location.

        Returns:
            AdvancedCacheConfig instance with merged configuration
        """
        # Load from file first
        config = cls.from_config_file(config_path)

        # Override with environment variables
        env_config = cls.from_environment()

        # Merge configurations (environment takes precedence)
        merged_data = {
            "enabled": (
                env_config.enabled if os.getenv("AWSIDEMAN_CACHE_ENABLED") else config.enabled
            ),
            "default_ttl": (
                env_config.default_ttl
                if os.getenv("AWSIDEMAN_CACHE_TTL_DEFAULT")
                else config.default_ttl
            ),
            "max_size_mb": (
                env_config.max_size_mb
                if os.getenv("AWSIDEMAN_CACHE_MAX_SIZE_MB")
                else config.max_size_mb
            ),
            "backend_type": (
                env_config.backend_type
                if os.getenv("AWSIDEMAN_CACHE_BACKEND")
                else config.backend_type
            ),
            "encryption_enabled": (
                env_config.encryption_enabled
                if os.getenv("AWSIDEMAN_CACHE_ENCRYPTION")
                else config.encryption_enabled
            ),
            "encryption_type": (
                env_config.encryption_type
                if os.getenv("AWSIDEMAN_CACHE_ENCRYPTION_TYPE")
                else config.encryption_type
            ),
            "dynamodb_table_name": (
                env_config.dynamodb_table_name
                if os.getenv("AWSIDEMAN_CACHE_DYNAMODB_TABLE")
                else config.dynamodb_table_name
            ),
            "dynamodb_region": (
                env_config.dynamodb_region
                if os.getenv("AWSIDEMAN_CACHE_DYNAMODB_REGION")
                else config.dynamodb_region
            ),
            "dynamodb_profile": (
                env_config.dynamodb_profile
                if os.getenv("AWSIDEMAN_CACHE_DYNAMODB_PROFILE")
                else config.dynamodb_profile
            ),
            "hybrid_local_ttl": (
                env_config.hybrid_local_ttl
                if os.getenv("AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL")
                else config.hybrid_local_ttl
            ),
            "file_cache_dir": (
                env_config.file_cache_dir
                if os.getenv("AWSIDEMAN_CACHE_FILE_DIR")
                else config.file_cache_dir
            ),
        }

        # Merge operation TTLs
        operation_ttls = config.operation_ttls.copy()
        for operation, ttl in env_config.operation_ttls.items():
            operation_ttls[operation] = ttl
        merged_data["operation_ttls"] = operation_ttls

        logger.debug("Loaded cache configuration from file and environment variables")
        return cls(**merged_data)

    def validate(self) -> Dict[str, str]:
        """
        Validate the configuration and return any errors.

        Returns:
            Dictionary of validation errors (empty if valid)
        """
        errors = {}

        # Validate backend type
        valid_backends = ["file", "dynamodb", "hybrid"]
        if self.backend_type not in valid_backends:
            errors["backend_type"] = (
                f"Invalid backend type '{self.backend_type}'. Must be one of: {valid_backends}"
            )

        # Validate encryption type
        valid_encryption_types = ["none", "aes256"]
        if self.encryption_type not in valid_encryption_types:
            errors["encryption_type"] = (
                f"Invalid encryption type '{self.encryption_type}'. Must be one of: {valid_encryption_types}"
            )

        # Validate TTL values
        if self.default_ttl <= 0:
            errors["default_ttl"] = "Default TTL must be positive"

        if self.hybrid_local_ttl <= 0:
            errors["hybrid_local_ttl"] = "Hybrid local TTL must be positive"

        # Validate max size
        if self.max_size_mb <= 0:
            errors["max_size_mb"] = "Max size must be positive"

        # Validate DynamoDB configuration if using DynamoDB backend
        if self.backend_type in ["dynamodb", "hybrid"]:
            if not self.dynamodb_table_name:
                errors["dynamodb_table_name"] = (
                    "DynamoDB table name is required for DynamoDB backend"
                )
            elif not self.dynamodb_table_name.replace("-", "").replace("_", "").isalnum():
                errors["dynamodb_table_name"] = (
                    "DynamoDB table name must contain only alphanumeric characters, hyphens, and underscores"
                )

        # Validate file cache directory if specified
        if self.file_cache_dir:
            cache_dir = Path(self.file_cache_dir)
            if cache_dir.exists() and not cache_dir.is_dir():
                errors["file_cache_dir"] = (
                    f"File cache directory path exists but is not a directory: {self.file_cache_dir}"
                )

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation of the configuration
        """
        return {
            "enabled": self.enabled,
            "default_ttl": self.default_ttl,
            "operation_ttls": self.operation_ttls,
            "max_size_mb": self.max_size_mb,
            "backend_type": self.backend_type,
            "encryption_enabled": self.encryption_enabled,
            "encryption_type": self.encryption_type,
            "dynamodb_table_name": self.dynamodb_table_name,
            "dynamodb_region": self.dynamodb_region,
            "dynamodb_profile": self.dynamodb_profile,
            "hybrid_local_ttl": self.hybrid_local_ttl,
            "file_cache_dir": self.file_cache_dir,
        }

    def save_to_file(self, config_path: Optional[str] = None) -> None:
        """
        Save configuration to unified YAML config file.

        Args:
            config_path: Optional path to config file. If None, uses default location.
        """
        # Use the unified config system
        from ..utils.config import Config

        config = Config()

        # Update the cache section in the unified config
        config.set_cache_config(self.to_dict())

        logger.info("Saved cache configuration to unified config file")

    @staticmethod
    def _get_env_bool(env_var: str, default: bool) -> bool:
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

    @staticmethod
    def _get_env_int(env_var: str, default: int) -> int:
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
            logger.warning(
                f"Invalid integer value for {env_var}: {value}. Using default: {default}"
            )
            return default
