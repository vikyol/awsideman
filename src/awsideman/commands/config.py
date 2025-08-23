"""Configuration management commands for awsideman."""

from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from ..utils.config import Config

app = typer.Typer(
    help="Manage awsideman configuration settings including profiles, cache, backup, rollback, and templates."
)
console = Console()


@app.command("show")
def show_config(
    section: str = typer.Option(
        None, "--section", "-s", help="Show specific configuration section (profiles, cache, etc.)"
    ),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, yaml, json"),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Show cache configuration for specific profile"
    ),
):
    """Show current configuration."""
    config = Config()
    config_data = config.get_all()

    if not config_data:
        console.print(
            "[yellow]No configuration found. Use 'awsideman profile add' or 'awsideman cache' commands to configure.[/yellow]"
        )
        return

    # Handle profile-specific cache configuration display
    if profile and section == "cache":
        _show_profile_cache_section(config_data, profile)
        return

    # Filter by section if specified
    if section:
        if section in config_data:
            config_data = {section: config_data[section]}
        else:
            console.print(f"[red]Configuration section '{section}' not found.[/red]")
            console.print(f"Available sections: {', '.join(config_data.keys())}")
            return

    # Display configuration
    if format == "yaml":
        try:
            import yaml

            yaml_output = yaml.dump(
                config_data, default_flow_style=False, indent=2, sort_keys=False
            )
            syntax = Syntax(yaml_output, "yaml", theme="monokai", line_numbers=True)
            console.print(syntax)
        except ImportError:
            console.print("[red]PyYAML not available. Install it to view YAML format.[/red]")
    elif format == "json":
        import json

        json_output = json.dumps(config_data, indent=2)
        syntax = Syntax(json_output, "json", theme="monokai", line_numbers=True)
        console.print(syntax)
    else:  # table format
        _display_config_table(config_data)


@app.command("path")
def show_config_path():
    """Show the path to the configuration file."""
    config = Config()
    config_path = config.get_config_file_path()

    console.print(f"[green]Configuration file:[/green] {config_path}")

    if config_path.exists():
        console.print("[green]File exists:[/green] Yes")
        console.print(f"[green]File size:[/green] {config_path.stat().st_size} bytes")
    else:
        console.print("[yellow]File exists:[/yellow] No")

    # Show migration status
    if config.needs_migration():
        console.print("[yellow]Migration needed:[/yellow] Yes (JSON config found)")
        console.print("[dim]Run 'awsideman config migrate' to migrate to YAML[/dim]")
    else:
        console.print("[green]Migration needed:[/green] No")


@app.command("set")
def set_config(
    key_value: str = typer.Argument(
        ..., help="Configuration key=value pair (e.g., cache.enabled=true)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="AWS profile to set configuration for (for cache settings)"
    ),
):
    """Set a configuration value using key=value format.

    Examples:
    - awsideman config set cache.enabled=true
    - awsideman config set cache.default_ttl=7200
    - awsideman config set cache.max_size_mb=200
    - awsideman config set cache.backend_type=dynamodb --profile prod
    """
    config = Config()

    # Parse key=value format
    if "=" not in key_value:
        console.print(
            "[red]Error: Invalid format. Use 'key=value' (e.g., cache.enabled=true)[/red]"
        )
        raise typer.Exit(1)

    key, value = key_value.split("=", 1)
    key = key.strip()
    value = value.strip()

    if not key or not value:
        console.print("[red]Error: Both key and value are required[/red]")
        raise typer.Exit(1)

    try:
        # Parse the value based on common patterns
        parsed_value = _parse_config_value(value)

        # Handle profile-specific cache configuration
        if profile and key.startswith("cache."):
            _set_profile_cache_config(config, profile, key, parsed_value)
        else:
            # Set the configuration value normally
            _set_config_value(config, key, parsed_value)

        console.print(f"[green]✓ Configuration '{key}' set to '{parsed_value}'[/green]")
        if profile:
            console.print(f"[green]Applied to profile: {profile}[/green]")

        # Show updated configuration
        console.print(f"\n[blue]Updated configuration for '{key}':[/blue]")
        if profile and key.startswith("cache."):
            _show_profile_cache_config(config, profile, key)
        else:
            _show_single_config_value(config, key)

    except Exception as e:
        console.print(f"[red]Error setting configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command("validate")
def validate_config():
    """Validate the current configuration."""
    config = Config()
    config_data = config.get_all()

    if not config_data:
        console.print("[yellow]No configuration found.[/yellow]")
        return

    console.print("[blue]Validating configuration...[/blue]")

    errors = []
    warnings = []

    # Validate profiles
    if "profiles" in config_data:
        profiles = config_data["profiles"]
        if not isinstance(profiles, dict):
            errors.append("Profiles section must be a dictionary")
        else:
            for profile_name, profile_data in profiles.items():
                if not isinstance(profile_data, dict):
                    errors.append(f"Profile '{profile_name}' must be a dictionary")
                    continue

                # Check required fields
                if "region" not in profile_data:
                    warnings.append(f"Profile '{profile_name}' missing region")

                # Validate region format
                region = profile_data.get("region", "")
                if region and not region.replace("-", "").replace("_", "").isalnum():
                    warnings.append(f"Profile '{profile_name}' has invalid region format: {region}")

    # Validate default profile
    if "default_profile" in config_data:
        default_profile = config_data["default_profile"]
        profiles = config_data.get("profiles", {})
        if default_profile not in profiles:
            errors.append(f"Default profile '{default_profile}' does not exist in profiles")

    # Validate cache configuration
    if "cache" in config_data:
        cache_config = config_data["cache"]
        if not isinstance(cache_config, dict):
            errors.append("Cache section must be a dictionary")
        else:
            # Validate cache settings
            if "enabled" in cache_config and not isinstance(cache_config["enabled"], bool):
                errors.append("Cache 'enabled' must be a boolean")

            if "default_ttl" in cache_config:
                try:
                    ttl = int(cache_config["default_ttl"])
                    if ttl <= 0:
                        errors.append("Cache 'default_ttl' must be positive")
                except (ValueError, TypeError):
                    errors.append("Cache 'default_ttl' must be an integer")

            if "max_size_mb" in cache_config:
                try:
                    size = int(cache_config["max_size_mb"])
                    if size <= 0:
                        errors.append("Cache 'max_size_mb' must be positive")
                except (ValueError, TypeError):
                    errors.append("Cache 'max_size_mb' must be an integer")

    # Validate template configuration
    if "templates" in config_data:
        template_config = config_data["templates"]
        if not isinstance(template_config, dict):
            errors.append("Templates section must be a dictionary")
        else:
            # Validate template directory
            if "directory" in template_config:
                template_dir = template_config["directory"]
                if not isinstance(template_dir, str):
                    errors.append("Template 'directory' must be a string")
                elif template_dir and not template_dir.strip():
                    errors.append("Template 'directory' cannot be empty")

            # Validate template format preference
            if "default_format" in template_config:
                default_format = template_config["default_format"]
                if default_format not in ["yaml", "json"]:
                    errors.append("Template 'default_format' must be 'yaml' or 'json'")

            # Validate template validation settings
            if "validate_on_save" in template_config and not isinstance(
                template_config["validate_on_save"], bool
            ):
                errors.append("Template 'validate_on_save' must be a boolean")

            if "auto_backup" in template_config and not isinstance(
                template_config["auto_backup"], bool
            ):
                errors.append("Template 'auto_backup' must be a boolean")

    # Display results
    if errors:
        console.print(f"[red]✗ Configuration validation failed with {len(errors)} error(s):[/red]")
        for error in errors:
            console.print(f"  [red]• {error}[/red]")
    else:
        console.print("[green]✓ Configuration validation passed[/green]")

    if warnings:
        console.print(f"[yellow]⚠ {len(warnings)} warning(s):[/yellow]")
        for warning in warnings:
            console.print(f"  [yellow]• {warning}[/yellow]")

    if not errors and not warnings:
        console.print("[green]Configuration is valid with no warnings.[/green]")


def _display_config_table(config_data: dict):
    """Display configuration data in table format."""
    for section_name, section_data in config_data.items():
        # Skip backup section as it's handled in the cache section
        if section_name == "backup":
            continue

        console.print(f"\n[bold blue]{section_name.title()} Configuration[/bold blue]")

        if section_name == "profiles" and isinstance(section_data, dict):
            # Special handling for profiles
            table = Table()
            table.add_column("Profile", style="cyan")
            table.add_column("Region", style="green")
            table.add_column("SSO Instance", style="yellow")
            table.add_column("Display Name", style="magenta")

            for profile_name, profile_info in section_data.items():
                sso_instance = profile_info.get("sso_instance_arn", "Not configured")
                if sso_instance != "Not configured":
                    sso_instance = sso_instance.split("/")[-1]  # Show just the ID

                display_name = profile_info.get("sso_display_name", "")

                table.add_row(
                    profile_name, profile_info.get("region", ""), sso_instance, display_name
                )

            console.print(table)

        elif section_name == "cache" and isinstance(section_data, dict):
            # Special handling for cache config
            table = Table()
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            for key, value in section_data.items():
                if key == "operation_ttls" and isinstance(value, dict):
                    # Show operation TTLs as a sub-table
                    table.add_row(key, f"{len(value)} operations configured")
                else:
                    table.add_row(key, str(value))

            console.print(table)

            # Show operation TTLs if they exist
            if "operation_ttls" in section_data and isinstance(
                section_data["operation_ttls"], dict
            ):
                console.print("\n[bold blue]Operation TTLs[/bold blue]")
                ttl_table = Table()
                ttl_table.add_column("Operation", style="cyan")
                ttl_table.add_column("TTL (seconds)", style="green")

                for operation, ttl in section_data["operation_ttls"].items():
                    ttl_table.add_row(operation, str(ttl))

                console.print(ttl_table)

            # Show backup configuration right after cache
            backup_config = config_data.get("backup", {})
            if backup_config:
                console.print("\n[bold blue]Backup Configuration[/bold blue]")
                backup_table = Table()
                backup_table.add_column("Section", style="cyan")
                backup_table.add_column("Setting", style="green")
                backup_table.add_column("Value", style="yellow")

                # Storage configuration
                storage_config = backup_config.get("storage", {})
                backup_table.add_row(
                    "Storage",
                    "Default Backend",
                    storage_config.get("default_backend", "filesystem"),
                )

                filesystem_config = storage_config.get("filesystem", {})
                backup_table.add_row(
                    "Storage",
                    "Filesystem Path",
                    filesystem_config.get("path", "~/.awsideman/backups"),
                )

                s3_config = storage_config.get("s3", {})
                backup_table.add_row(
                    "Storage", "S3 Bucket", s3_config.get("bucket", "Not configured")
                )
                backup_table.add_row("Storage", "S3 Prefix", s3_config.get("prefix", "backups"))
                backup_table.add_row(
                    "Storage", "S3 Region", s3_config.get("region", "Profile default")
                )

                # Encryption configuration
                encryption_config = backup_config.get("encryption", {})
                backup_table.add_row(
                    "Encryption", "Enabled", str(encryption_config.get("enabled", True))
                )
                backup_table.add_row("Encryption", "Type", encryption_config.get("type", "aes256"))

                # Compression configuration
                compression_config = backup_config.get("compression", {})
                backup_table.add_row(
                    "Compression", "Enabled", str(compression_config.get("enabled", True))
                )
                backup_table.add_row("Compression", "Type", compression_config.get("type", "gzip"))

                # Default settings
                defaults_config = backup_config.get("defaults", {})
                backup_table.add_row(
                    "Defaults", "Backup Type", defaults_config.get("backup_type", "full")
                )
                backup_table.add_row(
                    "Defaults",
                    "Include Inactive Users",
                    str(defaults_config.get("include_inactive_users", False)),
                )
                backup_table.add_row(
                    "Defaults", "Resource Types", defaults_config.get("resource_types", "all")
                )

                # Retention policy
                retention_config = backup_config.get("retention", {})
                backup_table.add_row(
                    "Retention", "Keep Daily", str(retention_config.get("keep_daily", 7))
                )
                backup_table.add_row(
                    "Retention", "Keep Weekly", str(retention_config.get("keep_weekly", 4))
                )
                backup_table.add_row(
                    "Retention", "Keep Monthly", str(retention_config.get("keep_monthly", 12))
                )
                backup_table.add_row(
                    "Retention", "Auto Cleanup", str(retention_config.get("auto_cleanup", True))
                )

                # Performance settings
                performance_config = backup_config.get("performance", {})
                backup_table.add_row(
                    "Performance",
                    "Deduplication Enabled",
                    str(performance_config.get("deduplication_enabled", True)),
                )
                backup_table.add_row(
                    "Performance",
                    "Parallel Processing",
                    str(performance_config.get("parallel_processing_enabled", True)),
                )
                backup_table.add_row(
                    "Performance",
                    "Resource Monitoring",
                    str(performance_config.get("resource_monitoring_enabled", True)),
                )
                backup_table.add_row(
                    "Performance", "Max Workers", str(performance_config.get("max_workers", 8))
                )

                console.print(backup_table)

        else:
            # Generic handling for other sections
            if isinstance(section_data, dict):
                table = Table()
                table.add_column("Key", style="cyan")
                table.add_column("Value", style="green")

                for key, value in section_data.items():
                    table.add_row(key, str(value))

                console.print(table)
            else:
                console.print(f"  {section_data}")


def _parse_config_value(value: str):
    """Parse configuration value string into appropriate Python type."""
    value = value.strip().lower()

    # Boolean values
    if value in ["true", "false", "1", "0", "yes", "no", "on", "off"]:
        return value in ["true", "1", "yes", "on"]

    # Integer values
    try:
        return int(value)
    except ValueError:
        pass

    # Float values
    try:
        return float(value)
    except ValueError:
        pass

    # String values (default)
    return value


def _set_config_value(config: Config, key: str, value):
    """Set a configuration value using dot notation."""
    config_data = config.get_all()

    # Parse dot notation (e.g., "cache.enabled" -> ["cache", "enabled"])
    key_parts = key.split(".")

    if len(key_parts) == 1:
        # Top-level key
        config_data[key] = value
    else:
        # Nested key
        current = config_data
        for part in key_parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[key_parts[-1]] = value

    # Save the configuration
    config.config_data = config_data
    config.save_config()


def _show_single_config_value(config: Config, key: str):
    """Show a single configuration value."""
    config_data = config.get_all()

    # Parse dot notation
    key_parts = key.split(".")
    current = config_data

    try:
        for part in key_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                console.print(f"[yellow]Key '{key}' not found in configuration.[/yellow]")
                return

        # Display the value
        if isinstance(current, dict):
            console.print(f"[blue]Section '{key}':[/blue]")
            table = Table()
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            for k, v in current.items():
                table.add_row(k, str(v))
            console.print(table)
        else:
            console.print(f"[blue]Value:[/blue] {current}")

    except Exception as e:
        console.print(f"[red]Error displaying configuration: {e}[/red]")


def _set_profile_cache_config(config: Config, profile_name: str, key: str, value):
    """Set profile-specific cache configuration."""
    config_data = config.get_all()

    # Ensure cache section exists
    if "cache" not in config_data:
        config_data["cache"] = {}

    # Ensure profiles section exists in cache
    if "profiles" not in config_data["cache"]:
        config_data["cache"]["profiles"] = {}

    # Ensure profile section exists
    if profile_name not in config_data["cache"]["profiles"]:
        config_data["cache"]["profiles"][profile_name] = {}

    # Parse the cache key (e.g., "cache.backend_type" -> "backend_type")
    cache_key = key.replace("cache.", "")

    # Set the profile-specific cache value
    config_data["cache"]["profiles"][profile_name][cache_key] = value

    # Save the configuration
    config.config_data = config_data
    config.save_config()


def _show_profile_cache_config(config: Config, profile_name: str, key: str):
    """Show profile-specific cache configuration."""
    config_data = config.get_all()

    # Parse the cache key
    cache_key = key.replace("cache.", "")

    try:
        # Get the profile-specific cache config
        profile_cache_config = (
            config_data.get("cache", {}).get("profiles", {}).get(profile_name, {})
        )

        if cache_key in profile_cache_config:
            value = profile_cache_config[cache_key]
            console.print(f"[blue]Profile '{profile_name}' cache setting '{cache_key}':[/blue]")
            console.print(f"[green]Value:[/green] {value}")
        else:
            console.print(
                f"[yellow]Cache setting '{cache_key}' not found for profile '{profile_name}'[/yellow]"
            )

        # Show all profile-specific cache settings
        if profile_cache_config:
            console.print(f"\n[blue]All cache settings for profile '{profile_name}':[/blue]")
            table = Table()
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            for k, v in profile_cache_config.items():
                table.add_row(k, str(v))
            console.print(table)
        else:
            console.print(
                f"[yellow]No profile-specific cache settings found for '{profile_name}'[/yellow]"
            )

    except Exception as e:
        console.print(f"[red]Error displaying profile cache configuration: {e}[/red]")


def _show_profile_cache_section(config_data: dict, profile_name: str):
    """Show profile-specific cache configuration section."""
    console.print(f"\n[bold blue]Cache Configuration for Profile: {profile_name}[/bold blue]")
    console.print("=" * 60)

    cache_config = config_data.get("cache", {})
    profile_cache_config = cache_config.get("profiles", {}).get(profile_name, {})

    if not profile_cache_config:
        console.print(
            f"[yellow]No profile-specific cache configuration found for '{profile_name}'[/yellow]"
        )
        console.print("[blue]Using default cache configuration[/blue]")

        # Show default cache config
        default_cache = cache_config.copy()
        if "profiles" in default_cache:
            del default_cache["profiles"]

        if default_cache:
            _display_cache_config_table(default_cache, "Default Cache Configuration")
        return

    # Show profile-specific cache config
    _display_cache_config_table(
        profile_cache_config, f"Profile '{profile_name}' Cache Configuration"
    )

    # Show inheritance information
    console.print("\n[blue]Inheritance from Default Configuration:[/blue]")
    default_cache = cache_config.copy()
    if "profiles" in default_cache:
        del default_cache["profiles"]

    inherited_settings = []
    for key, value in default_cache.items():
        if key not in profile_cache_config:
            inherited_settings.append((key, value))

    if inherited_settings:
        table = Table()
        table.add_column("Setting", style="cyan")
        table.add_column("Value (inherited)", style="yellow")

        for key, value in inherited_settings:
            table.add_row(key, str(value))
        console.print(table)
    else:
        console.print("[dim]All settings are profile-specific (no inheritance)[/dim]")


def _display_cache_config_table(cache_config: dict, title: str):
    """Display cache configuration in table format."""
    console.print(f"\n[bold blue]{title}[/bold blue]")
    console.print("-" * 40)

    table = Table()
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    for key, value in cache_config.items():
        if key == "operation_ttls" and isinstance(value, dict):
            # Show operation TTLs as a sub-table
            table.add_row(key, f"{len(value)} operations configured")
        else:
            table.add_row(key, str(value))

    console.print(table)

    # Show operation TTLs if they exist
    if "operation_ttls" in cache_config and isinstance(cache_config["operation_ttls"], dict):
        console.print("\n[bold blue]Operation TTLs[/bold blue]")
        ttl_table = Table()
        ttl_table.add_column("Operation", style="cyan")
        ttl_table.add_column("TTL (seconds)", style="green")

        for operation, ttl in cache_config["operation_ttls"].items():
            ttl_table.add_row(operation, str(ttl))

        console.print(ttl_table)
