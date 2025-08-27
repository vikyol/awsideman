"""Permission set management commands for awsideman.

This module provides permission set management functionality including listing, getting,
creating, updating, and deleting permission sets in AWS Identity Center.
"""

import typer

# Import external dependencies for backward compatibility
from ...aws_clients.manager import AWSClientManager
from ...utils.validators import validate_profile, validate_sso_instance

# Import all submodules first
from . import helpers

# Import command functions
from .create import create_permission_set
from .delete import delete_permission_set
from .find import find_permission_sets
from .get import get_permission_set

# Import helper functions for backward compatibility
from .helpers import (
    console,
    resolve_permission_set_identifier,
    validate_aws_managed_policy_arn,
    validate_permission_set_description,
    validate_permission_set_name,
)
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
app.command("find")(find_permission_sets)

# Export the app and functions for backward compatibility
__all__ = [
    "app",
    "list_permission_sets",
    "get_permission_set",
    "create_permission_set",
    "update_permission_set",
    "delete_permission_set",
    "find_permission_sets",
    "console",
    "resolve_permission_set_identifier",
    "validate_aws_managed_policy_arn",
    "validate_permission_set_description",
    "validate_permission_set_name",
    "AWSClientManager",
    "validate_profile",
    "validate_sso_instance",
    "helpers",
]
