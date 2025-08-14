"""Profile management commands for awsideman."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..utils.config import Config

app = typer.Typer(help="Manage AWS profiles for Identity Center operations.")
console = Console()
config = Config()


@app.command("list")
def list_profiles():
    """List all configured AWS profiles."""
    profiles = config.get("profiles", {})

    if not profiles:
        console.print("No profiles configured. Use 'awsideman profile add' to add a profile.")
        return

    table = Table(title="AWS Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Region", style="green")
    table.add_column("Default", style="yellow")

    default_profile = config.get("default_profile")

    for name, profile_data in profiles.items():
        is_default = "✓" if name == default_profile else ""
        table.add_row(name, profile_data.get("region", ""), is_default)

    console.print(table)


@app.command("add")
def add_profile(
    name: str = typer.Argument(...),
    region: str = typer.Option(..., "--region", "-r", help="AWS region"),
    set_default: bool = typer.Option(False, "--default", "-d", help="Set as default profile"),
):
    """Add a new AWS profile."""
    profiles = config.get("profiles", {})

    if name in profiles:
        console.print(
            f"[yellow]Profile '{name}' already exists. Use 'awsideman profile update' to modify it.[/yellow]"
        )
        return

    profiles[name] = {
        "region": region,
    }

    config.set("profiles", profiles)

    if set_default or not config.get("default_profile"):
        config.set("default_profile", name)
        console.print(f"[green]Profile '{name}' added and set as default.[/green]")
    else:
        console.print(f"[green]Profile '{name}' added.[/green]")


@app.command("update")
def update_profile(
    name: str = typer.Argument(...),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    set_default: bool = typer.Option(False, "--default", "-d", help="Set as default profile"),
):
    """Update an existing AWS profile."""
    profiles = config.get("profiles", {})

    if name not in profiles:
        console.print(
            f"[red]Profile '{name}' does not exist. Use 'awsideman profile add' to create it.[/red]"
        )
        return

    if region:
        profiles[name]["region"] = region

    config.set("profiles", profiles)

    if set_default:
        config.set("default_profile", name)
        console.print(f"[green]Profile '{name}' updated and set as default.[/green]")
    else:
        console.print(f"[green]Profile '{name}' updated.[/green]")


@app.command("remove")
def remove_profile(
    name: str = typer.Argument(...),
    force: bool = typer.Option(False, "--force", "-f", help="Force removal without confirmation"),
):
    """Remove an AWS profile."""
    profiles = config.get("profiles", {})

    if name not in profiles:
        console.print(f"[red]Profile '{name}' does not exist.[/red]")
        return

    if not force:
        confirm = typer.confirm(f"Are you sure you want to remove profile '{name}'?")
        if not confirm:
            console.print("Operation cancelled.")
            return

    del profiles[name]
    config.set("profiles", profiles)

    default_profile = config.get("default_profile")
    if default_profile == name:
        if profiles:
            new_default = next(iter(profiles.keys()))
            config.set("default_profile", new_default)
            console.print(f"[yellow]Default profile changed to '{new_default}'.[/yellow]")
        else:
            config.delete("default_profile")

    console.print(f"[green]Profile '{name}' removed.[/green]")


@app.command("set-default")
def set_default_profile(
    name: str = typer.Argument(...),
):
    """Set the default AWS profile."""
    profiles = config.get("profiles", {})

    if name not in profiles:
        console.print(
            f"[red]Profile '{name}' does not exist. Use 'awsideman profile add' to create it.[/red]"
        )
        return

    config.set("default_profile", name)
    console.print(f"[green]Default profile set to '{name}'.[/green]")
