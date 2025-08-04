"""Configuration management commands for awsideman."""
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from ..utils.config import Config, CONFIG_FILE_YAML, CONFIG_FILE_JSON

app = typer.Typer(help="Manage awsideman configuration settings.")
console = Console()


@app.command("show")
def show_config(
    section: str = typer.Option(None, "--section", "-s", help="Show specific configuration section (profiles, cache, etc.)"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, yaml, json"),
):
    """Show current configuration."""
    config = Config()
    config_data = config.get_all()
    
    if not config_data:
        console.print("[yellow]No configuration found. Use 'awsideman profile add' or 'awsideman cache' commands to configure.[/yellow]")
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
            yaml_output = yaml.dump(config_data, default_flow_style=False, indent=2, sort_keys=False)
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
    force: bool = typer.Option(False, "--force", "-f", help="Force migration even if YAML config exists"),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Create backup of JSON config"),
):
    """Migrate configuration from JSON to YAML format."""
    config = Config()
    
    # Check if migration is needed
    if not CONFIG_FILE_JSON.exists():
        console.print("[yellow]No JSON configuration file found. Nothing to migrate.[/yellow]")
        return
    
    if CONFIG_FILE_YAML.exists() and not force:
        console.print("[yellow]YAML configuration already exists. Use --force to overwrite.[/yellow]")
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
            backup_file = CONFIG_FILE_JSON.with_suffix('.json.backup')
            CONFIG_FILE_JSON.rename(backup_file)
            console.print(f"[green]JSON configuration backed up to: {backup_file}[/green]")
        else:
            CONFIG_FILE_JSON.unlink()
            console.print("[green]JSON configuration file removed[/green]")
        
        console.print(f"[green]✓ Configuration successfully migrated to: {CONFIG_FILE_YAML}[/green]")
        
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
        console.print(f"[green]File exists:[/green] Yes")
        console.print(f"[green]File size:[/green] {config_path.stat().st_size} bytes")
    else:
        console.print(f"[yellow]File exists:[/yellow] No")
    
    # Show migration status
    if config.needs_migration():
        console.print(f"[yellow]Migration needed:[/yellow] Yes (JSON config found)")
        console.print(f"[dim]Run 'awsideman config migrate' to migrate to YAML[/dim]")
    else:
        console.print(f"[green]Migration needed:[/green] No")


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
                    profile_name,
                    profile_info.get("region", ""),
                    sso_instance,
                    display_name
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
            if "operation_ttls" in section_data and isinstance(section_data["operation_ttls"], dict):
                console.print("\n[bold blue]Operation TTLs[/bold blue]")
                ttl_table = Table()
                ttl_table.add_column("Operation", style="cyan")
                ttl_table.add_column("TTL (seconds)", style="green")
                
                for operation, ttl in section_data["operation_ttls"].items():
                    ttl_table.add_row(operation, str(ttl))
                
                console.print(ttl_table)
        
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