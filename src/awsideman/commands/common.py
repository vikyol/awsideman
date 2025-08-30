"""Common command infrastructure for awsideman CLI commands.

This module provides shared functionality for all CLI commands including:
- Cache management options
- Profile validation with cache integration
- Consistent command parameter handling
- Error handling and logging
"""

import logging
from typing import Any, Dict, Optional, Tuple

import typer
from rich.console import Console

from ..aws_clients.manager import AWSClientManager
from ..cache.utilities import create_aws_client_manager

# Shared instances
console = Console()
logger = logging.getLogger(__name__)


def cache_option(default: bool = True, advanced: bool = False) -> Any:
    """
    Create a standardized --no-cache option for commands.

    Args:
        default: Default caching behavior (True = caching enabled by default)
        advanced: Whether this is an advanced debugging option (affects help text)

    Returns:
        Typer option for cache control
    """
    if advanced:
        help_text = "Advanced debugging option"
    else:
        help_text = "Advanced debugging option"

    return typer.Option(
        not default,  # Invert the default so --no-cache disables caching
        "--no-cache",
        help=help_text,
        hidden=True,  # Always hide from normal help output
    )


def advanced_cache_option(default: bool = True) -> Any:
    """
    Create an advanced --no-cache option for debugging commands.

    Args:
        default: Default caching behavior (True = caching enabled by default)

    Returns:
        Typer option for advanced cache control
    """
    return typer.Option(
        not default,  # Invert the default so --no-cache disables caching
        "--no-cache",
        help="Advanced debugging option",
        hidden=True,  # Hide from normal help output
    )


def profile_option() -> Any:
    """
    Create a standardized --profile option for commands.

    Returns:
        Typer option for AWS profile selection
    """
    return typer.Option(
        None, "--profile", "-p", help="AWS profile to use (uses default profile if not specified)"
    )


def region_option() -> Any:
    """
    Create a standardized --region option for commands.

    Returns:
        Typer option for AWS region selection
    """
    return typer.Option(
        None, "--region", "-r", help="AWS region to use (uses profile default if not specified)"
    )


def verbose_option() -> Any:
    """Create a verbose option for CLI commands."""
    return typer.Option(False, "--verbose", "-v", help="Show detailed output")


def validate_profile_with_cache(
    profile: Optional[str] = None, enable_caching: bool = True, region: Optional[str] = None
) -> Tuple[str, Dict[str, Any], AWSClientManager]:
    """
    Validate AWS profile and create AWS client manager with cache integration.

    This function combines profile validation with cache-enabled client creation,
    providing a standardized way for commands to get AWS clients.

    Args:
        profile: AWS profile name to validate
        enable_caching: Whether to enable caching for the client
        region: AWS region override

    Returns:
        Tuple of (profile_name, profile_data, aws_client_manager)

    Raises:
        typer.Exit: If profile validation fails
    """
    try:
        # Validate profile using existing logic
        from .user.helpers import validate_profile

        profile_name, profile_data = validate_profile(profile)

        # Use region from parameter or profile
        effective_region = region or profile_data.get("region")

        # Create AWS client manager with cache integration
        aws_client = create_aws_client_manager(
            profile=profile_name,
            region=effective_region,
            enable_caching=enable_caching,
            auto_configure_cache=True,
        )

        # Validate that the session is active and credentials are valid
        if not aws_client.validate_session():
            console.print("[red]❌ Error: AWS session validation failed.[/red]")
            console.print("\n[yellow]This usually means:[/yellow]")
            console.print("1. Your AWS SSO token has expired")
            console.print("2. Your AWS credentials are invalid")
            console.print("3. Your profile configuration is incorrect")
            console.print("\n[yellow]To fix this issue:[/yellow]")
            console.print(
                "1. Refresh your SSO login: [cyan]aws sso login --profile your-profile[/cyan]"
            )
            console.print("2. Or use a different profile: [cyan]--profile other-profile[/cyan]")
            console.print("3. Verify your AWS configuration")
            raise typer.Exit(1)

        logger.debug(
            f"Created AWS client manager: profile={profile_name}, region={effective_region}, caching={enable_caching}"
        )
        return profile_name, profile_data, aws_client

    except Exception as e:
        console.print(f"[red]Error setting up AWS client: {e}[/red]")
        raise typer.Exit(1)


def get_aws_client_manager(
    profile: Optional[str] = None,
    region: Optional[str] = None,
    enable_caching: bool = True,
    verbose: bool = False,
) -> AWSClientManager:
    """
    Get a configured AWS client manager with cache integration.

    This is a simplified version of validate_profile_with_cache for commands
    that don't need full profile validation.

    Args:
        profile: AWS profile name
        region: AWS region
        enable_caching: Whether to enable caching
        verbose: Whether to show verbose output

    Returns:
        Configured AWSClientManager instance
    """
    try:
        aws_client = create_aws_client_manager(
            profile=profile, region=region, enable_caching=enable_caching, auto_configure_cache=True
        )

        if verbose:
            console.print(f"[blue]Using AWS profile: {aws_client.profile or 'default'}[/blue]")
            console.print(f"[blue]Using AWS region: {aws_client.region or 'default'}[/blue]")
            console.print(f"[blue]Caching enabled: {aws_client.is_caching_enabled()}[/blue]")

        return aws_client

    except Exception as e:
        console.print(f"[red]Error creating AWS client manager: {e}[/red]")
        raise typer.Exit(1)


def handle_aws_error(error: Exception, operation: str, verbose: bool = False) -> None:
    """
    Handle AWS errors consistently across commands.

    Args:
        error: The error that occurred
        operation: Description of the operation that failed
        verbose: Whether to show detailed error information
    """
    from botocore.exceptions import ClientError

    if isinstance(error, ClientError):
        error_code = error.response.get("Error", {}).get("Code", "Unknown")
        error_message = error.response.get("Error", {}).get("Message", str(error))
        console.print(f"[red]AWS Error in {operation} ({error_code}): {error_message}[/red]")
    else:
        console.print(f"[red]Error in {operation}: {error}[/red]")

    if verbose:
        console.print_exception()


def get_cache_status_summary() -> Dict[str, Any]:
    """
    Get a summary of current cache status for command output.

    Returns:
        Dictionary with cache status information
    """
    try:
        from ..commands.cache.helpers import get_cache_manager

        cache_manager = get_cache_manager()
        stats = cache_manager.get_cache_stats()

        return {
            "enabled": stats.get("enabled", False),
            "backend_type": stats.get("backend_type", "unknown"),
            "total_entries": stats.get("total_entries", 0),
            "hit_rate": stats.get("hit_rate", 0),
        }
    except Exception as e:
        logger.warning(f"Failed to get cache status: {e}")
        return {"enabled": False, "backend_type": "unknown", "total_entries": 0, "hit_rate": 0}


def show_cache_info(verbose: bool = False) -> None:
    """
    Show cache information if verbose mode is enabled.

    Args:
        verbose: Whether to show cache information
    """
    if verbose:
        cache_status = get_cache_status_summary()
        if cache_status["enabled"]:
            console.print(
                f"[blue]Cache: {cache_status['backend_type']} backend, "
                f"{cache_status['total_entries']} entries, "
                f"{cache_status['hit_rate']:.1f}% hit rate[/blue]"
            )
        else:
            console.print("[blue]Cache: Disabled[/blue]")


# Common parameter combinations for reuse
StandardCommandParams = Tuple[Optional[str], Optional[str], bool]


def extract_standard_params(
    profile: Optional[str] = None, region: Optional[str] = None, no_cache: Optional[bool] = None
) -> StandardCommandParams:
    """
    Extract and process standard command parameters.

    Args:
        profile: AWS profile name
        region: AWS region
        no_cache: Whether caching is disabled (None means caching enabled by default)

    Returns:
        Tuple of (profile, region, enable_caching)
    """
    # Resolve default profile if none specified
    if profile is None:
        try:
            from ..utils.config import Config

            config = Config()
            profile = config.get("default_profile")
            if profile:
                logger.debug(f"Using default profile: {profile}")
        except Exception as e:
            logger.debug(f"Could not resolve default profile: {e}")

    # Default to caching enabled if no_cache is not specified
    enable_caching = not (no_cache or False)
    return profile, region, enable_caching
