"""Permission set management commands for awsideman.

This module provides permission set management functionality including listing, getting,
creating, updating, and deleting permission sets in AWS Identity Center.
"""

import typer

# Import all submodules first
from . import create, delete, get, helpers, list, update

# Import command functions
from .create import create_permission_set
from .delete import delete_permission_set
from .get import get_permission_set
from .list import list_permission_sets
from .update import update_permission_set

# Create the main app instance
app = typer.Typer(
    help="Manage permission sets in AWS Identity Center. Create, list, get, update, and delete permission sets."
)


# Register commands with the app
app.command("list")(list_permission_sets)
app.command("get")(get_permission_set)
app.command("create")(create_permission_set)
app.command("update")(update_permission_set)
app.command("delete")(delete_permission_set)

# Export the app for backward compatibility
__all__ = ["app", "list", "get", "create", "update", "delete", "helpers"]
