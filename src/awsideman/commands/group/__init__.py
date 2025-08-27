"""Group management commands for awsideman.

This module provides group management functionality including listing, getting,
creating, updating, and deleting groups in AWS Identity Center.
"""

import typer

# Import all submodules first
from . import create, delete, find, get, helpers, list, members, update

# Import command functions
from .create import create_group
from .delete import delete_group
from .find import find_groups
from .get import get_group
from .list import list_groups
from .members import add_member, list_members, remove_member
from .update import update_group

# Create the main app instance
app = typer.Typer(
    help="Manage groups in AWS Identity Center. Create, list, get, update, and delete groups in AWS Identity Center."
)

# Register commands with the app
app.command("list")(list_groups)
app.command("get")(get_group)
app.command("create")(create_group)
app.command("update")(update_group)
app.command("delete")(delete_group)
app.command("find")(find_groups)
app.command("list-members")(list_members)
app.command("add-member")(add_member)
app.command("remove-member")(remove_member)

# Export the app for backward compatibility
__all__ = ["app", "list", "get", "create", "update", "delete", "find", "members", "helpers"]
