"""Backup configuration command for awsideman."""

from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from ...utils.config import Config

console = Console()
config = Config()

# Valid configuration keys and their types
VALID_CONFIG_KEYS = {
    "storage": {
        "default_backend": ["filesystem", "s3"],
        "filesystem": {"path": str},
        "s3": {"bucket": [str, None], "prefix": str, "region": [str, None]},
    },
    "encryption": {"enabled": bool, "type": ["none", "aes256"]},
    "compression": {"enabled": bool, "type": ["none", "gzip", "lz4", "zstd"]},
    "defaults": {
        "backup_type": ["full", "incremental"],
        "include_inactive_users": bool,
        "resource_types": ["all", "users", "groups", "permission_sets", "assignments"],
    },
    "retention": {"keep_daily": int, "keep_weekly": int, "keep_monthly": int, "auto_cleanup": bool},
    "performance": {
        "deduplication_enabled": bool,
        "parallel_processing_enabled": bool,
        "resource_monitoring_enabled": bool,
        "max_workers": int,
    },
}


def validate_config_key(key: str) -> tuple[bool, str, list]:
    """
    Validate a configuration key path.

    Args:
        key: Configuration key path (e.g., "storage.default_backend")

    Returns:
        Tuple of (is_valid, error_message, valid_values)
    """
    key_parts = key.split(".")

    if len(key_parts) < 2:
        return (
            False,
            "Configuration key must have at least 2 parts (e.g., 'storage.default_backend')",
            [],
        )

    current_level = VALID_CONFIG_KEYS
    valid_values = []

    # Navigate through the key path
    for i, part in enumerate(key_parts):
        if part not in current_level:
            valid_keys = list(current_level.keys())
            return (
                False,
                f"Invalid key '{part}' at position {i+1}. Valid keys: {', '.join(valid_keys)}",
                [],
            )

        current_level = current_level[part]

        # If this is the final key, get valid values
        if i == len(key_parts) - 1:
            if isinstance(current_level, list):
                valid_values = current_level
            elif current_level == bool:
                valid_values = ["<boolean>"]
            elif current_level == int:
                valid_values = ["<integer>"]
            elif current_level == str:
                valid_values = ["<string>"]
            elif current_level == [str, None]:
                valid_values = ["<string>", "none"]
            elif current_level == [None, str]:
                valid_values = ["<string>", "none"]
            else:
                valid_values = ["<value>"]

    return True, "", valid_values


def validate_config_value(key: str, value: str, valid_values: list) -> tuple[bool, str, Any]:
    """
    Validate a configuration value.

    Args:
        key: Configuration key
        value: Value to validate
        valid_values: List of valid values

    Returns:
        Tuple of (is_valid, error_message, converted_value)
    """
    # Handle special values
    if value.lower() in ["true", "false"]:
        converted_value = value.lower() == "true"
        # Check if boolean values are allowed
        if "<boolean>" in valid_values or "<value>" in valid_values:
            return True, "", converted_value
        else:
            return False, f"Boolean values not allowed for key '{key}'", None

    if value.lower() in ["none", "null"]:
        converted_value = None
        # Check if None values are allowed
        if "none" in valid_values or "<value>" in valid_values:
            return True, "", converted_value
        else:
            return False, f"None/null values not allowed for key '{key}'", None

    # Handle integers
    if value.isdigit():
        converted_value = int(value)
        # Check if integer values are allowed
        if "<integer>" in valid_values or "<value>" in valid_values:
            return True, "", converted_value
        else:
            return False, f"Integer values not allowed for key '{key}'", None

    # Handle strings
    if "<string>" in valid_values or "<value>" in valid_values:
        return True, "", value

    # Check if value is in valid_values list
    if value in valid_values:
        return True, "", value

    # Handle type-based validation
    if str in valid_values or any(v == str for v in valid_values):
        return True, "", value

    # If we have specific valid values, show them
    if (
        valid_values
        and valid_values != ["<string>"]
        and valid_values != ["<value>"]
        and valid_values != ["<integer>"]
    ):
        return (
            False,
            f"Invalid value '{value}' for key '{key}'. Valid values: {', '.join(str(v) for v in valid_values)}",
            None,
        )

    return True, "", value


# Create the app
app = typer.Typer(help="Configure backup settings")


@app.command("show")
def show_backup_config(
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, yaml, json"),
):
    """Show current backup configuration."""
    backup_config = config.get("backup", {})

    if format.lower() == "json":

        console.print_json(data=backup_config)
    elif format.lower() == "yaml":
        import yaml

        console.print(yaml.dump(backup_config, default_flow_style=False, indent=2))
    else:
        _display_backup_config_table(backup_config)


@app.command("set")
def set_backup_config(
    key: str = typer.Argument(..., help="Configuration key (e.g., storage.default_backend)"),
    value: str = typer.Argument(..., help="Configuration value"),
):
    """Set a backup configuration value."""
    try:
        # Parse the key path (e.g., "storage.default_backend" -> ["storage", "default_backend"])
        key_parts = key.split(".")

        # Get current backup config
        backup_config = config.get("backup", {})

        # Navigate to the parent of the target key
        current = backup_config
        for part in key_parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # Set the value
        target_key = key_parts[-1]

        # Validate key
        is_valid, error_msg, valid_values = validate_config_key(key)
        if not is_valid:
            console.print(f"[red]Error: Invalid key '{key}'. {error_msg}[/red]")
            raise typer.Exit(1)

        # Validate value
        is_valid, error_msg, converted_value = validate_config_value(key, value, valid_values)
        if not is_valid:
            console.print(f"[red]Error: {error_msg}[/red]")
            raise typer.Exit(1)

        current[target_key] = converted_value

        # Save the updated configuration
        config.set("backup", backup_config)

        console.print(f"[green]✓ Set {key} = {converted_value}[/green]")

    except Exception as e:
        console.print(f"[red]Error setting configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command("get")
def get_backup_config(
    key: str = typer.Argument(..., help="Configuration key (e.g., storage.default_backend)"),
):
    """Get a backup configuration value."""
    try:
        backup_config = config.get("backup", {})

        # Parse the key path
        key_parts = key.split(".")
        current = backup_config

        for part in key_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                console.print(f"[red]Error: Key '{key}' not found in backup configuration.[/red]")
                raise typer.Exit(1)

        console.print(f"[blue]{key}: {current}[/blue]")

    except Exception as e:
        console.print(f"[red]Error getting configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command("reset")
def reset_backup_config(
    section: Optional[str] = typer.Option(
        None, "--section", "-s", help="Reset specific section (e.g., storage, encryption)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Force reset without confirmation"),
):
    """Reset backup configuration to defaults."""
    from ...utils.config import DEFAULT_BACKUP_CONFIG

    if section:
        # Reset specific section
        if not force:
            confirm = typer.confirm(f"Are you sure you want to reset the '{section}' section?")
            if not confirm:
                console.print("[yellow]Reset cancelled.[/yellow]")
                return

        backup_config = config.get("backup", {})
        if section in DEFAULT_BACKUP_CONFIG:
            backup_config[section] = DEFAULT_BACKUP_CONFIG[section].copy()
            config.set("backup", backup_config)
            console.print(f"[green]✓ Reset '{section}' section to defaults[/green]")
        else:
            console.print(f"[red]Error: Unknown section '{section}'[/red]")
            raise typer.Exit(1)
    else:
        # Reset entire backup config
        if not force:
            confirm = typer.confirm(
                "Are you sure you want to reset all backup configuration to defaults?"
            )
            if not confirm:
                console.print("[yellow]Reset cancelled.[/yellow]")
                return

        config.set("backup", DEFAULT_BACKUP_CONFIG.copy())
        console.print("[green]✓ Reset all backup configuration to defaults[/green]")


@app.command("test")
def test_backup_config():
    """Test backup configuration by validating settings."""
    backup_config = config.get("backup", {})
    errors = []
    warnings = []

    # Check storage configuration
    storage_config = backup_config.get("storage", {})
    default_backend = storage_config.get("default_backend", "filesystem")

    if default_backend == "s3":
        s3_config = storage_config.get("s3", {})
        if not s3_config.get("bucket"):
            errors.append("S3 backend selected but no bucket configured")
        else:
            console.print(f"[green]✓ S3 bucket configured: {s3_config['bucket']}[/green]")
    elif default_backend == "filesystem":
        filesystem_path = storage_config.get("filesystem", {}).get("path", "~/.awsideman/backups")
        console.print(f"[green]✓ Filesystem path configured: {filesystem_path}[/green]")
    else:
        errors.append(f"Invalid storage backend: {default_backend}")

    # Check encryption configuration
    encryption_config = backup_config.get("encryption", {})
    if encryption_config.get("enabled", True):
        encryption_type = encryption_config.get("type", "aes256")
        if encryption_type not in ["none", "aes256"]:
            errors.append(f"Invalid encryption type: {encryption_type}")
        else:
            console.print(f"[green]✓ Encryption configured: {encryption_type}[/green]")
    else:
        warnings.append("Encryption is disabled (not recommended for production)")

    # Check compression configuration
    compression_config = backup_config.get("compression", {})
    if compression_config.get("enabled", True):
        compression_type = compression_config.get("type", "gzip")
        if compression_type not in ["none", "gzip", "lz4", "zstd"]:
            errors.append(f"Invalid compression type: {compression_type}")
        else:
            console.print(f"[green]✓ Compression configured: {compression_type}[/green]")

    # Display results
    if errors:
        console.print("\n[red]Configuration Errors:[/red]")
        for error in errors:
            console.print(f"  • {error}")

    if warnings:
        console.print("\n[yellow]Configuration Warnings:[/yellow]")
        for warning in warnings:
            console.print(f"  • {warning}")

    if not errors and not warnings:
        console.print("\n[green]✓ All backup configuration is valid![/green]")
    elif not errors:
        console.print("\n[yellow]Configuration has warnings but is usable.[/yellow]")
    else:
        console.print("\n[red]Configuration has errors and needs to be fixed.[/red]")
        raise typer.Exit(1)


@app.command("list-keys")
def list_config_keys(
    section: Optional[str] = typer.Option(
        None, "--section", "-s", help="Show keys for specific section only"
    ),
):
    """List all valid configuration keys and their expected values."""
    if section:
        if section not in VALID_CONFIG_KEYS:
            console.print(f"[red]Error: Unknown section '{section}'[/red]")
            console.print(f"Valid sections: {', '.join(VALID_CONFIG_KEYS.keys())}")
            raise typer.Exit(1)

        console.print(f"[bold blue]Valid configuration keys for section '{section}':[/bold blue]")
        _display_section_keys(section, VALID_CONFIG_KEYS[section], "")
    else:
        console.print("[bold blue]All valid backup configuration keys:[/bold blue]")
        for section_name, section_keys in VALID_CONFIG_KEYS.items():
            console.print(f"\n[bold cyan]{section_name}:[/bold cyan]")
            _display_section_keys(section_name, section_keys, "")


def _display_section_keys(section: str, keys: dict, prefix: str):
    """Display configuration keys for a section."""
    for key, value_type in keys.items():
        if prefix:
            full_key = f"{prefix}.{key}"
        else:
            full_key = f"{section}.{key}"

        if isinstance(value_type, dict):
            console.print(f"  {full_key}:")
            _display_section_keys(key, value_type, full_key)
        else:
            if isinstance(value_type, list):
                if None in value_type:
                    valid_values = []
                    for v in value_type:
                        if v is None:
                            valid_values.append("none")
                        elif v == str:
                            valid_values.append("<string>")
                        elif v == bool:
                            valid_values.append("<boolean>")
                        elif v == int:
                            valid_values.append("<integer>")
                        else:
                            valid_values.append(str(v))
                else:
                    valid_values = [str(v) for v in value_type]
                value_desc = f"Values: {', '.join(valid_values)}"
            elif value_type == bool:
                value_desc = "Values: true, false"
            elif value_type == int:
                value_desc = "Values: <integer>"
            elif value_type == str:
                value_desc = "Values: <string>"
            elif value_type == [str, None] or value_type == [None, str]:
                value_desc = "Values: <string>, none"
            else:
                value_desc = "Values: <value>"

            console.print(f"    {full_key} - {value_desc}")


def _display_backup_config_table(backup_config: dict):
    """Display backup configuration in a formatted table."""
    table = Table(title="Backup Configuration", show_header=True, header_style="bold magenta")
    table.add_column("Section", style="cyan")
    table.add_column("Key", style="green")
    table.add_column("Value", style="yellow")

    # Storage configuration
    storage_config = backup_config.get("storage", {})
    table.add_row("Storage", "Default Backend", storage_config.get("default_backend", "filesystem"))

    filesystem_config = storage_config.get("filesystem", {})
    table.add_row(
        "Storage", "Filesystem Path", filesystem_config.get("path", "~/.awsideman/backups")
    )

    s3_config = storage_config.get("s3", {})
    table.add_row("Storage", "S3 Bucket", s3_config.get("bucket", "Not configured"))
    table.add_row("Storage", "S3 Prefix", s3_config.get("prefix", "backups"))
    table.add_row("Storage", "S3 Region", s3_config.get("region", "Profile default"))

    # Encryption configuration
    encryption_config = backup_config.get("encryption", {})
    table.add_row("Encryption", "Enabled", str(encryption_config.get("enabled", True)))
    table.add_row("Encryption", "Type", encryption_config.get("type", "aes256"))

    # Compression configuration
    compression_config = backup_config.get("compression", {})
    table.add_row("Compression", "Enabled", str(compression_config.get("enabled", True)))
    table.add_row("Compression", "Type", compression_config.get("type", "gzip"))

    # Default settings
    defaults_config = backup_config.get("defaults", {})
    table.add_row("Defaults", "Backup Type", defaults_config.get("backup_type", "full"))
    table.add_row(
        "Defaults",
        "Include Inactive Users",
        str(defaults_config.get("include_inactive_users", False)),
    )
    table.add_row("Defaults", "Resource Types", defaults_config.get("resource_types", "all"))

    # Retention policy
    retention_config = backup_config.get("retention", {})
    table.add_row("Retention", "Keep Daily", str(retention_config.get("keep_daily", 7)))
    table.add_row("Retention", "Keep Weekly", str(retention_config.get("keep_weekly", 4)))
    table.add_row("Retention", "Keep Monthly", str(retention_config.get("keep_monthly", 12)))
    table.add_row("Retention", "Auto Cleanup", str(retention_config.get("auto_cleanup", True)))

    # Performance settings
    performance_config = backup_config.get("performance", {})
    table.add_row(
        "Performance",
        "Deduplication Enabled",
        str(performance_config.get("deduplication_enabled", True)),
    )
    table.add_row(
        "Performance",
        "Parallel Processing",
        str(performance_config.get("parallel_processing_enabled", True)),
    )
    table.add_row(
        "Performance",
        "Resource Monitoring",
        str(performance_config.get("resource_monitoring_enabled", True)),
    )
    table.add_row("Performance", "Max Workers", str(performance_config.get("max_workers", 8)))

    console.print(table)


# Register commands
app.command("show")(show_backup_config)
app.command("set")(set_backup_config)
app.command("get")(get_backup_config)
app.command("reset")(reset_backup_config)
app.command("test")(test_backup_config)
app.command("list-keys")(list_config_keys)
