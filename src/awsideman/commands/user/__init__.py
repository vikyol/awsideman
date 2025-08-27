"""User management commands for awsideman.

This module provides user management functionality including listing, getting,
creating, updating, and deleting users in AWS Identity Center.
"""

import typer

# Import all submodules first
from . import create, delete, find, get, helpers, list, update

# Import command functions
from .create import create_user
from .delete import delete_user
from .find import find_users
from .get import get_user
from .list import list_users
from .update import update_user

# Create the main app instance
app = typer.Typer(
    help="Manage users in AWS Identity Center. Create, list, update, and delete users in the Identity Store."
)

# Register commands with the app
app.command("list")(list_users)
app.command("get")(get_user)
app.command("create")(create_user)
app.command("update")(update_user)
app.command("delete")(delete_user)
app.command("find")(find_users)

# Export the app for backward compatibility
__all__ = ["app", "list", "get", "create", "update", "delete", "find", "helpers"]
