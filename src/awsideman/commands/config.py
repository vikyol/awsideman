"""Configuration management commands for awsideman."""

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from ..utils.config import CONFIG_FILE_JSON, CONFIG_FILE_YAML, Config

app = typer.Typer(help="Manage awsideman configuration settings.")
console = Console()


@app.command("show")
def show_config(
    section: str = typer.Option(
        None, "--section", "-s", help="Show specific configuration section (profiles, cache, etc.)"
    ),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, yaml, json"),
):
    """Show current configuration."""
    config = Config()
    config_data = config.get_all()

    if not config_data:
        console.print(
            "[yellow]No configuration found. Use 'awsideman profile add' or 'awsideman cache' commands to configure.[/yellow]"
        )
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


@app.command("migrate")
def migrate_config(
    force: bool = typer.Option(
        False, "--force", "-f", help="Force migration even if YAML config exists"
    ),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Create backup of JSON config"),
):
    """Migrate configuration from JSON to YAML format."""
    config = Config()

    # Check if migration is needed
    if not CONFIG_FILE_JSON.exists():
        console.print("[yellow]No JSON configuration file found. Nothing to migrate.[/yellow]")
        return

    if CONFIG_FILE_YAML.exists() and not force:
        console.print(
            "[yellow]YAML configuration already exists. Use --force to overwrite.[/yellow]"
        )
        return

    console.print("[blue]Migrating configuration from JSON to YAML...[/blue]")

    try:
        # Load JSON config
        import json

        with open(CONFIG_FILE_JSON, "r") as f:
            json_data = json.load(f)

        # Migrate structure
        yaml_data = config._migrate_json_to_yaml_structure(json_data)

        # Save as YAML
        config.config_data = yaml_data
        config.save_config()

        # Create backup if requested
        if backup:
            backup_file = CONFIG_FILE_JSON.with_suffix(".json.backup")
            CONFIG_FILE_JSON.rename(backup_file)
            console.print(f"[green]JSON configuration backed up to: {backup_file}[/green]")
        else:
            CONFIG_FILE_JSON.unlink()
            console.print("[green]JSON configuration file removed[/green]")

        console.print(
            f"[green]✓ Configuration successfully migrated to: {CONFIG_FILE_YAML}[/green]"
        )

        # Show summary of migrated data
        console.print("\n[bold blue]Migration Summary:[/bold blue]")
        if "profiles" in yaml_data:
            profile_count = len(yaml_data["profiles"])
            console.print(f"  • Migrated {profile_count} profile(s)")

        if "default_profile" in yaml_data:
            console.print(f"  • Default profile: {yaml_data['default_profile']}")

        if "cache" in yaml_data:
            console.print("  • Cache configuration migrated")

    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        raise typer.Exit(1)


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


@app.command("templates")
def manage_template_config(
    action: str = typer.Argument(..., help="Action to perform: show, set, reset"),
    key: str = typer.Option(None, "--key", "-k", help="Configuration key to set"),
    value: str = typer.Option(None, "--value", "-v", help="Value to set for the key"),
):
    """Manage template configuration settings."""
    config = Config()

    if action == "show":
        _show_template_config(config)
    elif action == "set":
        if not key or not value:
            console.print("[red]Error: Both --key and --value are required for 'set' action.[/red]")
            raise typer.Exit(1)
        _set_template_config(config, key, value)
    elif action == "reset":
        _reset_template_config(config)
    else:
        console.print(f"[red]Error: Unknown action '{action}'. Use: show, set, or reset.[/red]")
        raise typer.Exit(1)


def _show_template_config(config: Config):
    """Display current template configuration."""
    template_config = config.get_template_config()

    console.print("[bold blue]Template Configuration[/bold blue]")

    table = Table()
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Default", style="yellow")

    # Show current values with defaults
    table.add_row(
        "Storage Directory",
        template_config.get("storage_directory", "Not set"),
        "~/.awsideman/templates",
    )
    table.add_row("Default Format", template_config.get("default_format", "Not set"), "yaml")

    # Validation settings
    validation = template_config.get("validation", {})
    table.add_row("Strict Mode", str(validation.get("strict_mode", "Not set")), "true")
    table.add_row("Require Metadata", str(validation.get("require_metadata", "Not set")), "false")

    # Execution settings
    execution = template_config.get("execution", {})
    table.add_row("Default Dry Run", str(execution.get("default_dry_run", "Not set")), "false")
    table.add_row("Parallel Execution", str(execution.get("parallel_execution", "Not set")), "true")
    table.add_row("Batch Size", str(execution.get("batch_size", "Not set")), "10")

    console.print(table)

    # Show additional information
    console.print(
        f"\n[blue]Current template directory:[/blue] {template_config.get('storage_directory', '~/.awsideman/templates')}"
    )

    # Check if directory exists and is accessible
    import pathlib

    template_dir = pathlib.Path(
        template_config.get("storage_directory", "~/.awsideman/templates")
    ).expanduser()
    if template_dir.exists():
        console.print("[green]✓ Directory exists and is accessible[/green]")
        try:
            template_count = len(
                list(template_dir.glob("*.yaml")) + list(template_dir.glob("*.json"))
            )
            console.print(f"[blue]Found {template_count} template file(s)[/blue]")
        except Exception:
            console.print("[yellow]Could not count template files[/yellow]")
    else:
        console.print(f"[yellow]Directory does not exist: {template_dir}[/yellow]")
        console.print(
            "[blue]Use 'awsideman config templates set storage_directory <path>' to set it.[/blue]"
        )


def _set_template_config(config: Config, key: str, value: str):
    """Set a template configuration value."""
    valid_keys = [
        "storage_directory",
        "default_format",
        "strict_mode",
        "require_metadata",
        "default_dry_run",
        "parallel_execution",
        "batch_size",
    ]

    if key not in valid_keys:
        console.print(f"[red]Error: Invalid key '{key}'.[/red]")
        console.print(f"Valid keys: {', '.join(valid_keys)}")
        raise typer.Exit(1)

    # Validate value based on key
    if key == "default_format":
        if value not in ["yaml", "json"]:
            console.print(
                f"[red]Error: '{value}' is not a valid format. Use 'yaml' or 'json'.[/red]"
            )
            raise typer.Exit(1)
    elif key in ["strict_mode", "require_metadata", "default_dry_run", "parallel_execution"]:
        if value.lower() not in ["true", "false", "1", "0"]:
            console.print(
                f"[red]Error: '{value}' is not a valid boolean value. Use 'true' or 'false'.[/red]"
            )
            raise typer.Exit(1)
        # Convert to boolean
        value = value.lower() in ["true", "1"]
    elif key == "batch_size":
        try:
            batch_size = int(value)
            if batch_size < 1 or batch_size > 1000:
                console.print("[red]Error: Batch size must be between 1 and 1000.[/red]")
                raise typer.Exit(1)
            value = batch_size
        except ValueError:
            console.print(f"[red]Error: '{value}' is not a valid integer.[/red]")
            raise typer.Exit(1)
    elif key == "storage_directory":
        # Validate directory path
        import pathlib

        try:
            dir_path = pathlib.Path(value).expanduser()
            if dir_path.exists() and not dir_path.is_dir():
                console.print(f"[red]Error: '{value}' exists but is not a directory.[/red]")
                raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error: Invalid directory path '{value}': {e}[/red]")
            raise typer.Exit(1)

    # Get current template config
    current_config = config.get_template_config()

    # Update the appropriate section
    if key in ["strict_mode", "require_metadata"]:
        if "validation" not in current_config:
            current_config["validation"] = {}
        current_config["validation"][key] = value
    elif key in ["default_dry_run", "parallel_execution", "batch_size"]:
        if "execution" not in current_config:
            current_config["execution"] = {}
        current_config["execution"][key] = value
    else:
        current_config[key] = value

    # Set the configuration
    try:
        config.set_template_config(current_config)
        console.print(f"[green]✓ Template configuration '{key}' set to '{value}'[/green]")

        # Show updated configuration
        console.print("\n[blue]Updated template configuration:[/blue]")
        _show_template_config(config)

    except Exception as e:
        console.print(f"[red]Error setting template configuration: {e}[/red]")
        raise typer.Exit(1)


def _reset_template_config(config: Config):
    """Reset template configuration to defaults."""
    try:
        from ..utils.config import DEFAULT_TEMPLATE_CONFIG

        config.set_template_config(DEFAULT_TEMPLATE_CONFIG)

        console.print("[green]✓ Template configuration reset to defaults[/green]")

        # Show updated configuration
        console.print("\n[blue]Current template configuration:[/blue]")
        _show_template_config(config)

    except Exception as e:
        console.print(f"[red]Error resetting template configuration: {e}[/red]")
        raise typer.Exit(1)


def _display_config_table(config_data: dict):
    """Display configuration data in table format."""
    for section_name, section_data in config_data.items():
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

        elif section_name == "templates" and isinstance(section_data, dict):
            # Special handling for template config
            table = Table()
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            table.add_column("Default", style="yellow")

            # Show template settings with defaults
            defaults = {
                "storage_directory": "~/.awsideman/templates",
                "default_format": "yaml",
                "strict_mode": "true",
                "require_metadata": "false",
                "default_dry_run": "false",
                "parallel_execution": "true",
                "batch_size": "10",
            }

            # Show top-level settings
            for key in ["storage_directory", "default_format"]:
                if key in section_data:
                    table.add_row(key, str(section_data[key]), defaults.get(key, "Not set"))

            # Show validation settings
            if "validation" in section_data and isinstance(section_data["validation"], dict):
                validation = section_data["validation"]
                for key in ["strict_mode", "require_metadata"]:
                    if key in validation:
                        table.add_row(
                            f"validation.{key}", str(validation[key]), defaults.get(key, "Not set")
                        )

            # Show execution settings
            if "execution" in section_data and isinstance(section_data["execution"], dict):
                execution = section_data["execution"]
                for key in ["default_dry_run", "parallel_execution", "batch_size"]:
                    if key in execution:
                        table.add_row(
                            f"execution.{key}", str(execution[key]), defaults.get(key, "Not set")
                        )

            console.print(table)

            # Show template directory status
            if "storage_directory" in section_data:
                import pathlib

                template_dir = pathlib.Path(section_data["storage_directory"]).expanduser()
                if template_dir.exists():
                    try:
                        template_count = len(
                            list(template_dir.glob("*.yaml")) + list(template_dir.glob("*.json"))
                        )
                        console.print(f"\n[blue]Template directory: {template_dir}[/blue]")
                        console.print(f"[green]Found {template_count} template file(s)[/green]")
                    except Exception:
                        console.print(f"\n[blue]Template directory: {template_dir}[/blue]")
                        console.print("[yellow]Could not count template files[/yellow]")
                else:
                    console.print(f"\n[blue]Template directory: {template_dir}[/blue]")
                    console.print("[yellow]Directory does not exist[/yellow]")

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
