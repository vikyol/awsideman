"""Status monitoring commands for awsideman."""

import typer

# Import and register subcommands
from .check import check_status
from .cleanup import cleanup_orphaned
from .inspect import inspect_resource
from .monitor import monitor_config

# Create the main status app
app = typer.Typer(
    help="Monitor AWS Identity Center status and health. Check overall system health, provisioning operations, orphaned assignments, and sync status."
)

# Register commands with the app
app.command("check")(check_status)
app.command("inspect")(inspect_resource)
app.command("cleanup")(cleanup_orphaned)
app.command("monitor")(monitor_config)

# Export the app for backward compatibility
__all__ = ["app"]
