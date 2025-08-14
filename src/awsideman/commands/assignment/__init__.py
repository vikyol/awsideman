"""Assignment management commands for awsideman.

This module provides commands for managing permission set assignments in AWS Identity Center.
Assignments link permission sets to principals (users or groups) for specific AWS accounts.

Commands:
    list: List all assignments in the Identity Center
    get: Get detailed information about a specific assignment
    assign: Assign a permission set to a principal for a specific account
    revoke: Revoke a permission set assignment from a principal

Examples:
    # List all assignments
    $ awsideman assignment list

    # List assignments for a specific account
    $ awsideman assignment list --account-id 123456789012

    # Get details for a specific assignment
    $ awsideman assignment get arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef user-1234567890abcdef 123456789012

    # Assign a permission set to a user
    $ awsideman assignment assign arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef user-1234567890abcdef 123456789012

    # Revoke a permission set assignment
    $ awsideman assignment revoke arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef user-1234567890abcdef 123456789012
"""

import typer

# Import all external dependencies first
from ...aws_clients.manager import AWSClientManager
from ...bulk.resolver import ResourceResolver
from ...commands.permission_set.helpers import resolve_permission_set_identifier
from ...utils.error_handler import handle_aws_error
from ...utils.validators import validate_profile, validate_sso_instance

# Import command functions
from .assign import (
    assign_multi_account_advanced,
    assign_multi_account_explicit,
    assign_permission_set,
    assign_single_account,
)
from .get import get_assignment
from .helpers import console, resolve_permission_set_info, resolve_principal_info
from .list import list_assignments
from .revoke import revoke_permission_set

# Import all submodules first


# Create the main app instance
app = typer.Typer(
    help="Manage permission set assignments in AWS Identity Center. List, get, assign, and revoke permission set assignments."
)

# Register commands with the app
app.command("assign")(assign_permission_set)
app.command("revoke")(revoke_permission_set)
app.command("list")(list_assignments)
app.command("get")(get_assignment)

# Export functions and app for backward compatibility
__all__ = [
    "app",
    "assign_permission_set",
    "assign_single_account",
    "assign_multi_account_advanced",
    "assign_multi_account_explicit",
    "revoke_permission_set",
    "list_assignments",
    "get_assignment",
    "resolve_permission_set_info",
    "resolve_principal_info",
    "AWSClientManager",
    "ResourceResolver",
    "resolve_permission_set_identifier",
    "validate_profile",
    "validate_sso_instance",
    "handle_aws_error",
    "console",
]
