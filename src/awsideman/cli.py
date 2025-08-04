#!/usr/bin/env python3
"""
awsideman - AWS Identity Center Manager

A CLI tool for managing AWS Identity Center operations.
"""
import typer
from typing import Optional
from rich.console import Console

try:
    from awsideman import __version__
    from .commands import profile, sso, user, group, permission_set, assignment, org, cache, config
except ImportError:
    # Handle direct script execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from awsideman import __version__
    from awsideman.commands import profile, sso, user, group, permission_set, assignment, org, cache, config

app = typer.Typer(
    help="AWS Identity Center Manager - A CLI tool for managing AWS Identity Center operations including users, groups, and permission sets."
)
console = Console()

# Add subcommands
app.add_typer(config.app, name="config")
app.add_typer(profile.app, name="profile")
app.add_typer(sso.app, name="sso")
app.add_typer(user.app, name="user")
app.add_typer(group.app, name="group")
app.add_typer(permission_set.app, name="permission-set")
app.add_typer(assignment.app, name="assignment")
app.add_typer(org.app, name="org")
app.add_typer(cache.app, name="cache")


@app.callback()
def callback(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show the application version and exit."
    ),
):
    """AWS Identity Center Manager CLI"""
    if version:
        console.print(f"awsideman version: {__version__}")
        raise typer.Exit()


@app.command()
def info():
    """Display information about the current AWS Identity Center configuration."""
    console.print("AWS Identity Center Information")
    console.print("This command will show information about your AWS Identity Center configuration.")
    # This will be implemented later


if __name__ == "__main__":
    app()