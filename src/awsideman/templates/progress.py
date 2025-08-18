"""Progress reporting and user feedback utilities for template operations."""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text


class OperationType(Enum):
    """Types of template operations."""

    VALIDATION = "validation"
    PREVIEW = "preview"
    EXECUTION = "execution"
    STORAGE = "storage"
    PARSING = "parsing"


@dataclass
class ProgressContext:
    """Context for progress tracking."""

    operation_type: OperationType
    total_items: int
    current_item: int = 0
    start_time: Optional[float] = None
    description: str = ""

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = time.time()

    def update(self, current_item: int, description: str = ""):
        """Update progress context."""
        self.current_item = current_item
        if description:
            self.description = description

    def get_progress_percentage(self) -> float:
        """Get progress as percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.current_item / self.total_items) * 100

    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def get_estimated_remaining(self) -> Optional[float]:
        """Get estimated remaining time in seconds."""
        if self.current_item == 0:
            return None

        elapsed = self.get_elapsed_time()
        if elapsed == 0:
            return None

        rate = self.current_item / elapsed
        remaining_items = self.total_items - self.current_item

        return remaining_items / rate if rate > 0 else None


class TemplateProgressReporter:
    """Reports progress for template operations."""

    def __init__(self, console: Optional[Console] = None, verbose: bool = False):
        self.console = console or Console()
        self.verbose = verbose
        self.progress_contexts: Dict[str, ProgressContext] = {}

    def start_operation(
        self,
        operation_id: str,
        operation_type: OperationType,
        total_items: int,
        description: str = "",
    ) -> str:
        """Start tracking an operation."""
        context = ProgressContext(
            operation_type=operation_type, total_items=total_items, description=description
        )
        self.progress_contexts[operation_id] = context

        if self.verbose:
            self.console.print(f"[blue]Starting {operation_type.value}: {description}[/blue]")
            self.console.print(f"[blue]Total items: {total_items}[/blue]")

        return operation_id

    def update_progress(self, operation_id: str, current_item: int, description: str = ""):
        """Update progress for an operation."""
        if operation_id not in self.progress_contexts:
            return

        context = self.progress_contexts[operation_id]
        context.update(current_item, description)

        if self.verbose:
            percentage = context.get_progress_percentage()
            remaining = context.get_estimated_remaining()

            status_line = f"[blue]{context.operation_type.value.title()}: {percentage:.1f}% ({current_item}/{context.total_items})[/blue]"
            if remaining:
                status_line += f" [dim]ETA: {remaining:.1f}s[/dim]"

            self.console.print(status_line)

    def complete_operation(self, operation_id: str, success: bool = True, message: str = ""):
        """Mark an operation as complete."""
        if operation_id not in self.progress_contexts:
            return

        context = self.progress_contexts[operation_id]
        elapsed = context.get_elapsed_time()

        if success:
            status = "[green]✓ Completed[/green]"
        else:
            status = "[red]✗ Failed[/red]"

        completion_message = f"{status} {context.operation_type.value.title()}"
        if message:
            completion_message += f": {message}"
        completion_message += f" [dim]({elapsed:.2f}s)[/dim]"

        self.console.print(completion_message)

        # Remove completed context
        del self.progress_contexts[operation_id]

    def show_summary(self, operation_results: Dict[str, Any]):
        """Show operation summary."""
        summary_table = Table(
            title="Operation Summary", show_header=True, header_style="bold magenta"
        )
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        for key, value in operation_results.items():
            if isinstance(value, (int, float)):
                summary_table.add_row(key.replace("_", " ").title(), str(value))
            elif isinstance(value, bool):
                status = "[green]✓ Yes[/green]" if value else "[red]✗ No[/red]"
                summary_table.add_row(key.replace("_", " ").title(), status)
            else:
                summary_table.add_row(key.replace("_", " ").title(), str(value))

        self.console.print(summary_table)


class TemplateProgressBar:
    """Progress bar for template operations."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    @contextmanager
    def create_progress(self, description: str, total: int):
        """Create a progress bar context."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description, total=total)
            yield task

    @contextmanager
    def create_spinner(self, description: str):
        """Create a spinner context for indeterminate operations."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(description, total=None)
            yield task


class TemplateUserFeedback:
    """Provides user feedback and confirmation prompts."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def show_info(self, message: str, title: str = "Information"):
        """Show informational message."""
        panel = Panel(Text(message, style="blue"), title=title, border_style="blue")
        self.console.print(panel)

    def show_warning(self, message: str, title: str = "Warning"):
        """Show warning message."""
        panel = Panel(Text(message, style="yellow"), title=title, border_style="yellow")
        self.console.print(panel)

    def show_error(self, message: str, title: str = "Error"):
        """Show error message."""
        panel = Panel(Text(message, style="red"), title=title, border_style="red")
        self.console.print(panel)

    def show_success(self, message: str, title: str = "Success"):
        """Show success message."""
        panel = Panel(Text(message, style="green"), title=title, border_style="green")
        self.console.print(panel)

    def show_operation_preview(
        self, operation_type: str, items: List[Dict[str, Any]], title: str = "Operation Preview"
    ):
        """Show preview of what will be done."""
        if not items:
            self.show_info("No operations to perform.", title)
            return

        table = Table(title=title, show_header=True, header_style="bold magenta")

        # Determine columns based on operation type
        if operation_type == "validation":
            table.add_column("Item", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Status", style="yellow")

            for item in items:
                table.add_row(
                    item.get("name", "Unknown"),
                    item.get("type", "Unknown"),
                    item.get("status", "Unknown"),
                )

        elif operation_type == "execution":
            table.add_column("Entity", style="cyan")
            table.add_column("Permission Set", style="green")
            table.add_column("Account", style="yellow")
            table.add_column("Action", style="magenta")

            for item in items:
                table.add_row(
                    item.get("entity", "Unknown"),
                    item.get("permission_set", "Unknown"),
                    item.get("account", "Unknown"),
                    item.get("action", "Unknown"),
                )

        else:
            # Generic table
            if items:
                for key in items[0].keys():
                    table.add_column(key.replace("_", " ").title(), style="cyan")

                for item in items:
                    table.add_row(*[str(item.get(key, "")) for key in items[0].keys()])

        self.console.print(table)

    def show_confirmation_prompt(self, message: str, default: bool = False) -> bool:
        """Show confirmation prompt and return user choice."""
        import typer

        if default:
            prompt = f"{message} [Y/n]: "
        else:
            prompt = f"{message} [y/N]: "

        return typer.confirm(prompt, default=default)

    def show_destructive_operation_warning(self, operation: str, items_count):
        """Show warning for destructive operations."""
        # Handle both integer counts and descriptive text
        if isinstance(items_count, int):
            if items_count >= 0:
                items_text = f"{items_count} item(s)"
            else:
                items_text = "multiple items (exact count depends on account resolution)"
        else:
            items_text = str(items_count)

        warning_message = f"""
⚠️  WARNING: This operation will {operation}

This will affect {items_text} and cannot be easily undone.

Please review the operation details above and confirm that you want to proceed.
        """.strip()

        self.show_warning(warning_message, title="Destructive Operation Warning")

    def show_operation_status(self, operation: str, status: str, details: str = ""):
        """Show operation status."""
        status_colors = {
            "pending": "yellow",
            "in_progress": "blue",
            "completed": "green",
            "failed": "red",
            "skipped": "dim",
        }

        color = status_colors.get(status.lower(), "white")
        status_text = f"[{color}]{status.upper()}[/{color}]"

        message = f"{operation}: {status_text}"
        if details:
            message += f" - {details}"

        self.console.print(message)


class TemplateLiveDisplay:
    """Provides live updating display for template operations."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    @contextmanager
    def create_live_display(self, refresh_per_second: float = 4):
        """Create a live updating display context."""
        with Live(console=self.console, refresh_per_second=refresh_per_second) as live:
            yield live

    def update_display(self, live: Live, content: Any):
        """Update the live display content."""
        live.update(content)

    def create_status_layout(self) -> Layout:
        """Create a layout for status display."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )

        layout["header"].update(Panel("Template Operation Status", style="blue"))
        layout["footer"].update(Panel("Press Ctrl+C to cancel", style="dim"))

        return layout
