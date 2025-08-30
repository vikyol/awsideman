"""Backup commands module for awsideman.

This module provides comprehensive backup functionality for AWS Identity Center
configurations including creation, listing, validation, deletion, scheduling,
export/import, and monitoring.

Commands:
    create: Create a new backup (full or incremental)
    list: List available backups with filtering
    validate: Validate backup integrity
    delete: Delete a backup with confirmation
    schedule: Manage backup schedules
    export: Export backup data to various formats
    import: Import backup data from external sources
    validate-import: Validate import data format
    status: Show system status
    health: Check system health
    monitor: Monitor backup operations and system health
"""

import typer

# Import all submodules first
from . import (
    config,
    create,
    delete,
    diff,
    export,
    health,
    monitor,
    performance,
    schedule,
    status,
    validate,
    validate_import,
)

# Import command functions
from .create import create_backup
from .delete import delete_backup
from .diff import diff_backups
from .export import export_backup
from .health import check_backup_health
from .import_backup import import_backup
from .list import list_backups
from .monitor import monitor_backups
from .schedule import (
    create_schedule,
    delete_schedule,
    get_schedule_status,
    list_schedules,
    run_schedule,
    update_schedule,
)
from .status import show_backup_status
from .validate import validate_backup
from .validate_import import validate_import_data

# Create the main backup app
app = typer.Typer(help="Create, manage, and validate AWS Identity Center backups")

# Register commands with the app
app.command("create")(create_backup)
app.command("list")(list_backups)
app.command("validate")(validate_backup)
app.command("delete")(delete_backup)
app.command("diff")(diff_backups)

# Schedule subcommands
schedule_app = typer.Typer(help="Manage backup schedules")
schedule_app.command("create")(create_schedule)
schedule_app.command("update")(update_schedule)
schedule_app.command("delete")(delete_schedule)
schedule_app.command("list")(list_schedules)
schedule_app.command("run")(run_schedule)
schedule_app.command("status")(get_schedule_status)
app.add_typer(schedule_app, name="schedule")

# Performance subcommands
performance_app = typer.Typer(help="Manage backup performance optimizations")
performance_app.command("enable")(performance.enable_optimizations)
performance_app.command("disable")(performance.disable_optimizations)
performance_app.command("status")(performance.show_optimization_status)
performance_app.command("stats")(performance.show_performance_stats)
performance_app.command("benchmark")(performance.run_performance_benchmark)
performance_app.command("clear")(performance.clear_optimization_caches)
app.add_typer(performance_app, name="performance")

# Configuration subcommands
app.add_typer(config.app, name="config")

# Export/Import commands
app.command("export")(export_backup)
app.command("import")(import_backup)
app.command("validate-import")(validate_import_data)

# Status and monitoring commands
app.command("status")(show_backup_status)
app.command("health")(check_backup_health)
app.command("monitor")(monitor_backups)

# Export the app for backward compatibility
__all__ = [
    "app",
    "create",
    "validate",
    "delete",
    "diff",
    "schedule",
    "export",
    "import",
    "validate_import",
    "status",
    "health",
    "monitor",
    "performance",
]
