"""Restore commands module for awsideman.

This module provides comprehensive restore functionality for AWS Identity Center
configurations including restore operations, preview, and compatibility validation.

Commands:
    restore: Restore from a backup with various options
    preview: Preview restore changes without applying them
    validate: Validate backup compatibility with target environment
"""

import typer

# Import all submodules first
from . import preview, restore, validate
from .preview import preview_restore

# Import command functions
from .restore import restore_backup
from .validate import validate_restore

# Create the main restore app
app = typer.Typer(help="Restore AWS Identity Center configurations from backups")

# Register commands with the app
app.command("apply")(restore_backup)
app.command("preview")(preview_restore)
app.command("validate")(validate_restore)

# Export the app for backward compatibility
__all__ = ["app", "restore", "preview", "validate"]
