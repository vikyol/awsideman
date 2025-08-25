"""Cache management commands for awsideman.

This module provides cache management functionality including clearing, status,
warming, encryption management, account operations, and inspection capabilities.
"""

import typer

# Import all submodules first
from . import accounts, clear, encryption, helpers, inspect, status, warm

# Import command functions
from .accounts import account_cache_status
from .clear import clear_cache
from .encryption import encryption_management
from .inspect import inspect_cache
from .status import cache_status
from .warm import warm_cache

# Create the main app instance
app = typer.Typer(help="Manage internal data storage for AWS Identity Center operations.")

# Register commands with the app
app.command("clear")(clear_cache)
app.command("status")(cache_status)
app.command("warm")(warm_cache)
app.command("encryption")(encryption_management)
app.command("accounts")(account_cache_status)
app.command("inspect")(inspect_cache)

# Export the app for backward compatibility
__all__ = ["app", "clear", "status", "warm", "encryption", "accounts", "inspect", "helpers"]
