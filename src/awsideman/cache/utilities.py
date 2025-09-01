"""Cache configuration utilities for awsideman.

This module provides utilities for:
- Loading and managing cache configuration
- Creating AWS client managers with cache integration
- Configuration validation and fallback handling
"""

import logging
import os
from typing import Any, Dict, Optional, Union

from ..aws_clients.manager import AWSClientManager
from .config import AdvancedCacheConfig
from .manager import CacheManager

logger = logging.getLogger(__name__)


def get_default_cache_config() -> AdvancedCacheConfig:
    """
    Get default cache configuration with proper fallback handling.

    This function implements a hierarchical configuration loading strategy:
    1. Try to load from unified config file
    2. Override with environment variables
    3. Fall back to sensible defaults

    Returns:
        AdvancedCacheConfig instance with optimal settings
    """
    try:
        # First, try to load from unified config file
        logger.debug("Attempting to load cache configuration from unified config file")
        config = AdvancedCacheConfig.from_config_file()

        # Then override with environment variables
        logger.debug("Overriding config with environment variables")
        config = AdvancedCacheConfig.from_config_and_environment()

        logger.info("Successfully loaded cache configuration from config file and environment")
        return config

    except Exception as e:
        logger.warning(f"Failed to load cache configuration from file: {e}")

        try:
            # Fall back to environment-only configuration
            logger.debug("Falling back to environment-only configuration")
            config = AdvancedCacheConfig.from_environment()
            logger.info("Successfully loaded cache configuration from environment variables")
            return config

        except Exception as env_error:
            logger.warning(f"Failed to load cache configuration from environment: {env_error}")

            # Final fallback to hardcoded defaults
            logger.info("Using hardcoded default cache configuration")
            return AdvancedCacheConfig(
                enabled=True,
                backend_type="file",  # Safe default that always works
                default_ttl=3600,  # 1 hour
                max_size_mb=100,  # 100 MB
                encryption_enabled=False,  # Disable encryption for simplicity
                encryption_type="none",
            )


def get_profile_cache_config(profile_name: str) -> AdvancedCacheConfig:
    """
    Get cache configuration for a specific profile.

    This function loads the cache configuration and returns the profile-specific
    configuration if available, otherwise falls back to the default configuration.

    Args:
        profile_name: Name of the AWS profile

    Returns:
        AdvancedCacheConfig instance with profile-specific settings
    """
    try:
        # First, try to get profile config from the default cache config (for testing and programmatic configs)
        default_config = get_default_cache_config()
        if hasattr(default_config, "profile_configs") and default_config.profile_configs:
            if profile_name in default_config.profile_configs:
                profile_config = default_config.profile_configs[profile_name]
                logger.debug(
                    f"Using profile-specific cache config from default config for {profile_name}"
                )

                # Convert ProfileCacheConfig to AdvancedCacheConfig
                if hasattr(profile_config, "to_dict"):
                    config_dict = profile_config.to_dict()
                    # Remove profile_name since AdvancedCacheConfig doesn't accept it
                    config_dict.pop("profile_name", None)
                    return AdvancedCacheConfig(**config_dict)
                else:
                    # Handle case where it's already a dict
                    # Remove profile_name since AdvancedCacheConfig doesn't accept it
                    config_dict = dict(profile_config)
                    config_dict.pop("profile_name", None)
                    return AdvancedCacheConfig(**config_dict)
            else:
                # Profile not found in profile_configs, return the default config for testing
                logger.debug(
                    f"Profile {profile_name} not found in profile_configs, returning default config"
                )
                return default_config

        # Fall back to file-based configuration
        # Force reload configuration to ensure we get the latest profile-specific settings
        from ..utils.config import Config

        config = Config()
        config.reload_config()

        # Load the main cache configuration with fresh config
        config_data = config.get_all()
        cache_section = config_data.get("cache", {})

        # Create base configuration from cache section
        base_config = {
            "enabled": cache_section.get("enabled", True),
            "backend_type": cache_section.get("backend_type", "file"),
            "default_ttl": cache_section.get("default_ttl", 3600),
            "max_size_mb": cache_section.get("max_size_mb", 100),
            "operation_ttls": cache_section.get("operation_ttls", {}),
            "dynamodb_table_name": cache_section.get("dynamodb_table_name", "awsideman-cache"),
            "dynamodb_region": cache_section.get("dynamodb_region"),
            "dynamodb_profile": cache_section.get("dynamodb_profile"),
            "file_cache_dir": cache_section.get("file_cache_dir"),
            "encryption_enabled": cache_section.get("encryption_enabled", False),
            "encryption_type": cache_section.get("encryption_type", "none"),
            "hybrid_local_ttl": cache_section.get("hybrid_local_ttl", 300),
        }

        # If profile-specific config exists, merge it with base config
        profile_configs = cache_section.get("profiles", {})
        if profile_name in profile_configs:
            profile_config = profile_configs[profile_name]
            logger.debug(f"Using profile-specific cache config from file for {profile_name}")

            # Override base config with profile-specific settings
            for key, value in profile_config.items():
                if value is not None:  # Only override if value is explicitly set
                    base_config[key] = value

            return AdvancedCacheConfig(**base_config)

        # Otherwise, use the base configuration
        logger.debug(
            f"No profile-specific cache config found for {profile_name}, using base config"
        )
        return AdvancedCacheConfig(**base_config)

    except Exception as e:
        logger.warning(f"Failed to get profile-specific cache config for {profile_name}: {e}")
        # Fall back to default config
        return get_default_cache_config()


def create_cache_manager(
    config: Optional[AdvancedCacheConfig] = None, profile: Optional[str] = None
) -> "CacheManager":
    """
    Create a unified cache manager instance (singleton pattern).

    This function now returns the CacheManager singleton instance,
    ensuring consistent cache behavior across the entire system.

    Args:
        config: Optional AdvancedCacheConfig instance (ignored for singleton)
        profile: AWS profile name for isolation

    Returns:
        CacheManager singleton instance
    """
    from .manager import CacheManager

    # The CacheManager is a singleton, so we just return the instance
    # Configuration is handled internally by the singleton
    logger.debug(f"Getting CacheManager singleton instance (profile: {profile or 'default'})")
    cache_manager = CacheManager(profile=profile)

    logger.info(
        f"Successfully retrieved unified cache manager singleton (profile: {profile or 'default'})"
    )
    return cache_manager


def create_legacy_cache_manager(config: Optional[AdvancedCacheConfig] = None) -> CacheManager:
    """
    Create a legacy cache manager instance with proper configuration.

    This function is kept for backward compatibility and testing purposes.

    Args:
        config: Optional AdvancedCacheConfig instance. If None, loads default config.

    Returns:
        Configured CacheManager instance
    """
    if config is None:
        config = get_default_cache_config()

    try:
        logger.debug(f"Creating legacy cache manager with backend type: {config.backend_type}")
        cache_manager = CacheManager(config=config)

        # Validate the cache manager configuration
        validation_errors = config.validate()
        if validation_errors:
            logger.warning(f"Cache configuration validation warnings: {validation_errors}")
            # Continue with warnings rather than failing

        logger.info("Successfully created legacy cache manager")
        return cache_manager

    except Exception as e:
        logger.error(f"Failed to create legacy cache manager: {e}")

        # Fall back to basic cache manager
        logger.info("Falling back to basic legacy cache manager")
        fallback_config = AdvancedCacheConfig(
            enabled=True,
            backend_type="file",
            default_ttl=3600,
            max_size_mb=100,
            encryption_enabled=False,
            encryption_type="none",
        )
        return CacheManager(config=fallback_config)


def create_aws_client_manager(
    profile: Optional[str] = None,
    region: Optional[str] = None,
    enable_caching: bool = True,
    cache_config: Optional[Union[AdvancedCacheConfig, Dict[str, Any]]] = None,
    auto_configure_cache: bool = True,
) -> "AWSClientManager":
    """
    Factory function for creating AWS client managers with consistent cache integration.

    This function provides a standardized way to create AWS client managers
    with proper cache integration and configuration.

    Args:
        profile: AWS profile name to use
        region: AWS region to use
        enable_caching: Whether to enable caching for read operations
        cache_config: Optional cache configuration (AdvancedCacheConfig or dict)
        auto_configure_cache: Whether to automatically configure cache if not provided

    Returns:
        Configured AWSClientManager instance with cache integration
    """
    # Convert dict config to AdvancedCacheConfig if needed
    if isinstance(cache_config, dict):
        try:
            cache_config = AdvancedCacheConfig(**cache_config)
        except Exception as e:
            logger.warning(f"Failed to convert dict config to AdvancedCacheConfig: {e}")
            cache_config = None

    # Auto-configure cache if requested and not provided
    cache_manager = None
    if enable_caching and auto_configure_cache:
        if cache_config is None:
            # Use profile-specific configuration if available
            if profile:
                cache_config = get_profile_cache_config(profile)
                logger.debug(f"Using profile-specific cache config for {profile}")
            else:
                cache_config = get_default_cache_config()

        try:
            cache_manager = create_cache_manager(cache_config, profile)
            logger.debug(
                f"Auto-configured cache manager for AWS client manager (profile: {profile or 'default'})"
            )
        except Exception as e:
            logger.warning(f"Failed to auto-configure cache manager: {e}")

    # Create the AWS client manager with cache integration
    try:
        client_manager = AWSClientManager(
            profile=profile,
            region=region,
            enable_caching=enable_caching,
            cache_manager=cache_manager,
            cache_config=cache_config.to_dict() if cache_config else {},
        )

        logger.info(
            f"Created AWS client manager with caching {'enabled' if enable_caching else 'disabled'}"
        )
        return client_manager

    except Exception as e:
        logger.error(f"Failed to create AWS client manager: {e}")

        # Fall back to basic client manager without caching
        logger.info("Falling back to basic AWS client manager without caching")
        return AWSClientManager(profile=profile, region=region, enable_caching=False)


def get_cache_config_from_environment() -> Dict[str, Any]:
    """
    Extract cache configuration from environment variables.

    Returns:
        Dictionary with cache configuration extracted from environment
    """
    # Start with default values
    config = {
        "enabled": True,
        "backend_type": "file",
        "default_ttl": 3600,
        "max_size_mb": 100,
        "encryption_enabled": False,
        "encryption_type": "none",
        "operation_ttls": {},
    }

    # Basic cache settings
    if os.getenv("AWSIDEMAN_CACHE_ENABLED"):
        config["enabled"] = os.getenv("AWSIDEMAN_CACHE_ENABLED").lower() in (
            "true",
            "1",
            "yes",
            "on",
        )

    if os.getenv("AWSIDEMAN_CACHE_TTL_DEFAULT"):
        try:
            config["default_ttl"] = int(os.getenv("AWSIDEMAN_CACHE_TTL_DEFAULT"))
        except ValueError:
            logger.warning("Invalid AWSIDEMAN_CACHE_TTL_DEFAULT value")

    if os.getenv("AWSIDEMAN_CACHE_MAX_SIZE_MB"):
        try:
            config["max_size_mb"] = int(os.getenv("AWSIDEMAN_CACHE_MAX_SIZE_MB"))
        except ValueError:
            logger.warning("Invalid AWSIDEMAN_CACHE_MAX_SIZE_MB value")

    # Advanced cache settings
    if os.getenv("AWSIDEMAN_CACHE_BACKEND"):
        config["backend_type"] = os.getenv("AWSIDEMAN_CACHE_BACKEND")

    if os.getenv("AWSIDEMAN_CACHE_ENCRYPTION"):
        config["encryption_enabled"] = os.getenv("AWSIDEMAN_CACHE_ENCRYPTION").lower() in (
            "true",
            "1",
            "yes",
            "on",
        )

    if os.getenv("AWSIDEMAN_CACHE_ENCRYPTION_TYPE"):
        config["encryption_type"] = os.getenv("AWSIDEMAN_CACHE_ENCRYPTION_TYPE")

    # DynamoDB specific settings
    if os.getenv("AWSIDEMAN_CACHE_DYNAMODB_TABLE"):
        config["dynamodb_table_name"] = os.getenv("AWSIDEMAN_CACHE_DYNAMODB_TABLE")

    if os.getenv("AWSIDEMAN_CACHE_DYNAMODB_REGION"):
        config["dynamodb_region"] = os.getenv("AWSIDEMAN_CACHE_DYNAMODB_REGION")

    if os.getenv("AWSIDEMAN_CACHE_DYNAMODB_PROFILE"):
        config["dynamodb_profile"] = os.getenv("AWSIDEMAN_CACHE_DYNAMODB_PROFILE")

    # File cache settings
    if os.getenv("AWSIDEMAN_CACHE_FILE_DIR"):
        config["file_cache_dir"] = os.getenv("AWSIDEMAN_CACHE_FILE_DIR")

    # Operation-specific TTLs
    operation_ttls = {}
    for key, value in os.environ.items():
        if key.startswith("AWSIDEMAN_CACHE_TTL_") and key != "AWSIDEMAN_CACHE_TTL_DEFAULT":
            operation = key.replace("AWSIDEMAN_CACHE_TTL_", "").lower()
            try:
                operation_ttls[operation] = int(value)
            except ValueError:
                logger.warning(f"Invalid TTL value for operation {operation}: {value}")

    if operation_ttls:
        config["operation_ttls"] = operation_ttls

    # Hybrid cache settings
    if os.getenv("AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL"):
        try:
            config["hybrid_local_ttl"] = int(os.getenv("AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL"))
        except ValueError:
            logger.warning("Invalid AWSIDEMAN_CACHE_HYBRID_LOCAL_TTL value")

    return config


def validate_cache_configuration(
    config: Union[AdvancedCacheConfig, Dict[str, Any]],
) -> Dict[str, str]:
    """
    Validate cache configuration and return any errors.

    Args:
        config: Cache configuration to validate

    Returns:
        Dictionary of validation errors (empty if valid)
    """
    if isinstance(config, dict):
        try:
            config = AdvancedCacheConfig(**config)
        except Exception as e:
            return {"config": f"Invalid configuration format: {e}"}

    return config.validate()


def get_optimal_cache_config_for_environment() -> AdvancedCacheConfig:
    """
    Get optimal cache configuration based on the current environment.

    This function analyzes the environment and returns the best cache configuration
    for the current setup, considering factors like:
    - Available AWS credentials
    - Network connectivity
    - Storage availability
    - Security requirements

    Returns:
        Optimized AdvancedCacheConfig instance
    """
    try:
        # Check if we're in a production-like environment
        is_production = os.getenv("ENVIRONMENT", "").lower() in ("prod", "production", "live")
        is_ci_cd = os.getenv("CI", "").lower() in ("true", "1", "yes")

        # Check AWS credentials availability
        has_aws_credentials = (
            os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("AWS_PROFILE")
            or os.path.exists(os.path.expanduser("~/.aws/credentials"))
        )

        # Determine optimal backend type
        if is_production and has_aws_credentials:
            backend_type = "dynamodb"  # Production with AWS access
        elif is_ci_cd:
            backend_type = "file"  # CI/CD environments
        elif has_aws_credentials:
            backend_type = "hybrid"  # Development with AWS access
        else:
            backend_type = "file"  # Local development without AWS

        # Determine encryption settings
        encryption_enabled = is_production or is_ci_cd

        # Create optimal configuration
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type=backend_type,
            default_ttl=3600 if not is_production else 7200,  # Longer TTL in production
            max_size_mb=100 if not is_production else 200,  # Larger cache in production
            encryption_enabled=encryption_enabled,
            encryption_type="aes256" if encryption_enabled else "none",
            hybrid_local_ttl=300 if backend_type == "hybrid" else 300,
        )

        logger.info(
            f"Generated optimal cache config: backend={backend_type}, encryption={encryption_enabled}"
        )
        return config

    except Exception as e:
        logger.warning(f"Failed to generate optimal cache config: {e}")
        return get_default_cache_config()


def merge_cache_configs(
    base_config: Union[AdvancedCacheConfig, Dict[str, Any]],
    override_config: Union[AdvancedCacheConfig, Dict[str, Any]],
) -> AdvancedCacheConfig:
    """
    Merge two cache configurations, with override_config taking precedence.

    Args:
        base_config: Base configuration
        override_config: Configuration to override base with

    Returns:
        Merged AdvancedCacheConfig instance
    """
    # Convert to AdvancedCacheConfig if needed
    if isinstance(base_config, dict):
        base_config = AdvancedCacheConfig(**base_config)

    if isinstance(override_config, dict):
        override_config = AdvancedCacheConfig(**override_config)

    # Merge configurations
    merged_data = base_config.to_dict()
    override_data = override_config.to_dict()

    # Override base with override values (only non-None values)
    for key, value in override_data.items():
        if value is not None:
            if key == "operation_ttls" and key in merged_data:
                # Merge operation_ttls dictionaries
                merged_data[key].update(value)
            else:
                merged_data[key] = value

    return AdvancedCacheConfig(**merged_data)
