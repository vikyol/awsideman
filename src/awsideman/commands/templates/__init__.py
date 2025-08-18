"""Template management commands for awsideman.

This module provides template management functionality including creating, validating,
previewing, applying, listing, and showing templates for AWS Identity Center.
"""

import typer

# Import all submodules first
from . import apply, create, delete, list, preview, show, validate
from .apply import apply_template

# Import command functions
from .create import create_template
from .delete import delete_template
from .list import list_templates
from .preview import preview_template
from .show import show_template
from .validate import validate_template

# Create the main app instance
app = typer.Typer(
    help="Manage templates for AWS Identity Center. Create, validate, preview, apply, list, and show permission assignment templates."
)

# Register commands with the app
app.command("create")(create_template)
app.command("validate")(validate_template)
app.command("preview")(preview_template)
app.command("apply")(apply_template)
app.command("list")(list_templates)
app.command("show")(show_template)
app.command("delete")(delete_template)

# Export the app for backward compatibility
__all__ = ["app", "create", "validate", "preview", "apply", "list", "show", "delete"]
