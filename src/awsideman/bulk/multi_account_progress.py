"""Multi-account progress tracking for bulk operations.

This module provides enhanced progress tracking specifically designed for
multi-account operations, extending the base ProgressTracker with account-level
progress display and real-time result reporting.

Classes:
    MultiAccountProgressTracker: Enhanced progress tracker for multi-account operations
    ProgressPersistence: Handles progress persistence for resumable operations
"""

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..utils.models import AccountResult, MultiAccountResults
from .batch import ProgressTracker


@dataclass
class ProgressSnapshot:
    """Snapshot of progress state for persistence."""

    operation_id: str
    operation_type: str
    total_accounts: int
    processed_accounts: int
    successful_count: int
    failed_count: int
    skipped_count: int
    start_time: float
    last_update_time: float
    current_account_id: Optional[str] = None
    current_account_name: Optional[str] = None
    estimated_completion_time: Optional[float] = None
    processing_rate: Optional[float] = None
    batch_size: int = 10

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressSnapshot":
        """Create from dictionary loaded from JSON."""
        return cls(**data)


class ProgressPersistence:
    """Handles progress persistence for resumable operations."""

    def __init__(self, progress_dir: Optional[str] = None):
        """Initialize progress persistence.

        Args:
            progress_dir: Directory to store progress files (defaults to ~/.awsideman/progress)
        """
        if progress_dir is None:
            progress_dir = os.path.expanduser("~/.awsideman/progress")

        self.progress_dir = Path(progress_dir)
        self.progress_dir.mkdir(parents=True, exist_ok=True)

    def save_progress(self, snapshot: ProgressSnapshot) -> None:
        """Save progress snapshot to disk.

        Args:
            snapshot: Progress snapshot to save
        """
        try:
            progress_file = self.progress_dir / f"{snapshot.operation_id}.json"
            with open(progress_file, "w") as f:
                json.dump(snapshot.to_dict(), f, indent=2)
        except Exception:
            # Don't fail the operation if we can't save progress
            pass

    def load_progress(self, operation_id: str) -> Optional[ProgressSnapshot]:
        """Load progress snapshot from disk.

        Args:
            operation_id: ID of the operation to load

        Returns:
            Progress snapshot if found, None otherwise
        """
        try:
            progress_file = self.progress_dir / f"{operation_id}.json"
            if progress_file.exists():
                with open(progress_file, "r") as f:
                    data = json.load(f)
                return ProgressSnapshot.from_dict(data)
        except Exception:
            pass
        return None

    def delete_progress(self, operation_id: str) -> None:
        """Delete progress file after completion.

        Args:
            operation_id: ID of the operation to delete
        """
        try:
            progress_file = self.progress_dir / f"{operation_id}.json"
            if progress_file.exists():
                progress_file.unlink()
        except Exception:
            pass

    def list_active_operations(self) -> List[ProgressSnapshot]:
        """List all active operations with saved progress.

        Returns:
            List of progress snapshots for active operations
        """
        snapshots = []
        try:
            for progress_file in self.progress_dir.glob("*.json"):
                try:
                    with open(progress_file, "r") as f:
                        data = json.load(f)
                    snapshots.append(ProgressSnapshot.from_dict(data))
                except Exception:
                    continue
        except Exception:
            pass
        return snapshots

    def cleanup_old_progress(self, max_age_hours: int = 24) -> None:
        """Clean up old progress files.

        Args:
            max_age_hours: Maximum age in hours before cleanup
        """
        try:
            cutoff_time = time.time() - (max_age_hours * 3600)
            for progress_file in self.progress_dir.glob("*.json"):
                try:
                    if progress_file.stat().st_mtime < cutoff_time:
                        progress_file.unlink()
                except Exception:
                    continue
        except Exception:
            pass


class MultiAccountProgressTracker(ProgressTracker):
    """Enhanced progress tracker for multi-account operations.

    Extends the base ProgressTracker with account-level progress display,
    real-time result reporting, comprehensive summary statistics, and
    progress persistence for resumable operations.
    """

    def __init__(
        self, console: Console, operation_id: Optional[str] = None, enable_persistence: bool = True
    ):
        """Initialize multi-account progress tracker.

        Args:
            console: Rich console for output
            operation_id: Unique identifier for this operation (for persistence)
            enable_persistence: Whether to enable progress persistence
        """
        super().__init__(console)
        self.current_account: Optional[str] = None
        self.current_account_id: Optional[str] = None
        self.account_results: Dict[str, AccountResult] = {}
        self.live_display: Optional[Live] = None
        self.show_live_results: bool = True
        self.results_table: Optional[Table] = None

        # Statistics tracking
        self.successful_count: int = 0
        self.failed_count: int = 0
        self.skipped_count: int = 0

        # Enhanced progress tracking
        self.operation_id: str = operation_id or f"multi_account_{int(time.time())}"
        self.operation_type: str = "assign"
        self.enable_persistence: bool = enable_persistence
        self.progress_persistence: Optional[ProgressPersistence] = None
        self.last_persistence_update: float = 0
        self.persistence_interval: float = 5.0  # Save progress every 5 seconds

        # Enhanced time tracking
        self.operation_start_time: Optional[float] = None
        self.last_rate_calculation: float = 0
        self.processing_rates: List[float] = []  # Rolling window of processing rates
        self.rate_window_size: int = 10  # Keep last 10 rate measurements

        # Detailed progress information
        self.detailed_stats: Dict[str, Any] = {}
        self.milestone_times: Dict[str, float] = {}  # Track milestone completion times

        if self.enable_persistence:
            self.progress_persistence = ProgressPersistence()

    def start_multi_account_progress(
        self,
        total_accounts: int,
        operation_type: str = "assign",
        show_live_results: bool = True,
        batch_size: int = 10,
    ):
        """Start multi-account progress tracking.

        Args:
            total_accounts: Total number of accounts to process
            operation_type: Type of operation ('assign' or 'revoke')
            show_live_results: Whether to show live results table
            batch_size: Batch size for processing
        """
        self.show_live_results = show_live_results
        self.operation_type = operation_type
        self.successful_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.operation_start_time = time.time()
        self.last_rate_calculation = self.operation_start_time
        self.processing_rates = []

        # Initialize detailed stats
        self.detailed_stats = {
            "total_accounts": total_accounts,
            "batch_size": batch_size,
            "operation_type": operation_type,
            "start_time": self.operation_start_time,
            "estimated_duration": None,
            "current_processing_rate": 0.0,
            "average_processing_rate": 0.0,
            "time_per_account": 0.0,
            "accounts_per_minute": 0.0,
            "progress_percentage": 0.0,
        }

        # Set milestones for large operations
        if total_accounts >= 100:
            milestone_percentages = [10, 25, 50, 75, 90]
            for pct in milestone_percentages:
                milestone_accounts = int(total_accounts * pct / 100)
                self.milestone_times[f"{pct}%"] = milestone_accounts

        # Try to load existing progress if resuming
        if self.enable_persistence and self.progress_persistence:
            existing_progress = self.progress_persistence.load_progress(self.operation_id)
            if existing_progress:
                self._restore_from_snapshot(existing_progress)
                self.console.print(
                    f"[yellow]Resuming operation from {existing_progress.processed_accounts}/{total_accounts} accounts[/yellow]"
                )

        # Choose between live display and base progress tracking
        if self.show_live_results:
            # Use live display AND base progress for backward compatibility
            description = f"Processing {operation_type} operations across {total_accounts} accounts"
            self.start_progress(total_accounts, description)
            self._initialize_live_display()
            self.total_items = total_accounts
        else:
            # Use base progress tracking
            description = f"Processing {operation_type} operations across {total_accounts} accounts"
            self.start_progress(total_accounts, description)

        # Save initial progress
        self._save_progress_if_enabled()

    def update_current_account(self, account_name: str, account_id: str):
        """Update the currently processing account.

        Args:
            account_name: Human-readable account name
            account_id: AWS account ID
        """
        self.current_account = account_name
        self.current_account_id = account_id

        # Update display based on mode
        if self.show_live_results and self.live_display:
            # Update live display
            self._update_live_display()

        # Always update base progress for backward compatibility
        current_description = f"Processing: {account_name} ({account_id})"
        self.update_progress(0, current_description)

    def record_account_result(
        self,
        account_id: str,
        status: str,
        account_name: str = "",
        error: Optional[str] = None,
        processing_time: float = 0.0,
        retry_count: int = 0,
    ):
        """Record the result of processing an account.

        Args:
            account_id: AWS account ID
            status: Result status ('success', 'failed', 'skipped')
            account_name: Human-readable account name
            error: Optional error message for failed operations
            processing_time: Time taken to process this account
            retry_count: Number of retries attempted
        """
        # Create account result
        result = AccountResult(
            account_id=account_id,
            account_name=account_name or account_id,
            status=status,
            error_message=error,
            processing_time=processing_time,
            retry_count=retry_count,
        )

        # Store result
        self.account_results[account_id] = result

        # Update counters
        if status == "success":
            self.successful_count += 1
        elif status == "failed":
            self.failed_count += 1
        elif status == "skipped":
            self.skipped_count += 1

        # Update detailed progress statistics
        self._update_detailed_stats()

        # Check for milestones
        self._check_milestones()

        # Update display based on mode
        if self.show_live_results and self.live_display:
            # Update live display
            self._update_live_display()
        else:
            # Update base progress and display immediate result
            self.update_progress(1)
            self._display_account_result(result)

        # Save progress periodically
        self._save_progress_if_enabled()

    def display_account_progress(self):
        """Display current account progress information.

        Shows a summary of current progress including success/failure counts
        and the currently processing account.
        """
        if not self.show_live_results:
            return

        # Create progress summary
        total_processed = self.successful_count + self.failed_count + self.skipped_count

        progress_text = Text()
        progress_text.append(f"Processed: {total_processed}/{self.total_items} accounts\n")
        progress_text.append(f"✅ Successful: {self.successful_count}\n", style="green")
        progress_text.append(f"❌ Failed: {self.failed_count}\n", style="red")
        progress_text.append(f"⏭️  Skipped: {self.skipped_count}\n", style="yellow")

        if self.current_account:
            progress_text.append(f"\n🔄 Currently processing: {self.current_account}")
            if self.current_account_id:
                progress_text.append(f" ({self.current_account_id})")

        # Display in a panel
        panel = Panel(progress_text, title="Multi-Account Progress", border_style="blue")

        self.console.print(panel)

    def display_final_summary(self, results: MultiAccountResults):
        """Display final summary of multi-account operation results.

        Args:
            results: Complete results from multi-account operation
        """
        # Stop any live display
        if self.live_display:
            self.live_display.stop()
            self.live_display = None

        # Always finish base progress tracking for backward compatibility
        self.finish_progress()

        # Get final detailed stats
        final_stats = self.get_detailed_stats()

        # Create summary table
        summary_table = Table(title="Multi-Account Operation Summary")
        summary_table.add_column("Metric", style="cyan", no_wrap=True)
        summary_table.add_column("Value", style="white")
        summary_table.add_column("Additional Info", style="dim")

        # Add summary rows
        summary_table.add_row("Total Accounts", str(results.total_accounts), "100.0%")
        summary_table.add_row(
            "✅ Successful",
            str(len(results.successful_accounts)),
            f"{results.success_rate:.1f}%",
            style="green",
        )
        summary_table.add_row(
            "❌ Failed",
            str(len(results.failed_accounts)),
            f"{results.failure_rate:.1f}%",
            style="red",
        )
        summary_table.add_row(
            "⏭️  Skipped",
            str(len(results.skipped_accounts)),
            f"{results.skip_rate:.1f}%",
            style="yellow",
        )
        summary_table.add_row(
            "⏱️  Total Duration",
            self._format_duration(results.duration),
            f"{results.duration:.2f} seconds",
        )
        summary_table.add_row("📊 Batch Size", str(results.batch_size), "")

        # Add enhanced timing information
        if final_stats.get("accounts_per_minute"):
            summary_table.add_row(
                "⚡ Processing Rate",
                f"{final_stats['accounts_per_minute']:.1f} accounts/min",
                f"{final_stats.get('average_processing_rate', 0):.2f} accounts/sec",
            )

        if final_stats.get("time_per_account"):
            summary_table.add_row(
                "⏲️  Avg Time per Account",
                f"{final_stats['time_per_account']:.2f}s",
                "Including retries and delays",
            )

        # Add milestone information for large operations
        completed_milestones = final_stats.get("completed_milestones", {})
        if completed_milestones:
            milestone_count = len(completed_milestones)
            summary_table.add_row(
                "🎯 Milestones Reached",
                f"{milestone_count} milestones",
                "Progress checkpoints completed",
            )

        self.console.print("\n")
        self.console.print(summary_table)

        # Display milestone details for large operations
        if completed_milestones and results.total_accounts >= 100:
            self._display_milestone_summary(completed_milestones)

        # Display failed accounts if any
        if results.failed_accounts:
            self._display_failed_accounts(results.failed_accounts)

        # Display success message or warning
        if results.is_complete_success():
            self.console.print(
                f"\n🎉 [green]All {results.total_accounts} accounts processed successfully![/green]"
            )
        elif results.has_failures():
            self.console.print(
                f"\n⚠️  [yellow]Operation completed with {len(results.failed_accounts)} failures out of {results.total_accounts} accounts[/yellow]"
            )
        else:
            self.console.print("\n✅ [green]Operation completed successfully[/green]")

        # Clean up progress persistence
        if self.enable_persistence and self.progress_persistence:
            self.progress_persistence.delete_progress(self.operation_id)

    def _display_milestone_summary(self, completed_milestones: Dict[str, Any]):
        """Display milestone completion summary.

        Args:
            completed_milestones: Dictionary of completed milestones
        """
        milestone_table = Table(title="🎯 Milestone Summary")
        milestone_table.add_column("Milestone", style="cyan")
        milestone_table.add_column("Completed At", style="white")
        milestone_table.add_column("Accounts Processed", style="dim")
        milestone_table.add_column("Elapsed Time", style="dim")

        # Sort milestones by completion time
        sorted_milestones = sorted(completed_milestones.items(), key=lambda x: x[1]["completed_at"])

        for milestone_name, info in sorted_milestones:
            import datetime

            completion_time = datetime.datetime.fromtimestamp(info["completed_at"])

            milestone_table.add_row(
                milestone_name,
                completion_time.strftime("%H:%M:%S"),
                str(info["accounts_processed"]),
                self._format_duration(info["elapsed_time"]),
            )

        self.console.print("\n")
        self.console.print(milestone_table)

    def _initialize_live_display(self):
        """Initialize live display for real-time results."""
        if not self.show_live_results:
            return

        # Create initial results table
        self.results_table = Table(title="Account Processing Results")
        self.results_table.add_column("Account", style="cyan", no_wrap=True)
        self.results_table.add_column("Status", style="white")
        self.results_table.add_column("Time", style="dim")
        self.results_table.add_column("Details", style="dim")

        # Start live display
        self.live_display = Live(
            self.results_table, console=self.console, refresh_per_second=2, auto_refresh=True
        )
        self.live_display.start()

    def _update_live_display(self):
        """Update the live display with current results."""
        if not self.live_display or not self.results_table:
            return

        # Clear existing rows
        self.results_table.rows.clear()

        # Add current account being processed
        if self.current_account and self.current_account_id:
            self.results_table.add_row(
                f"{self.current_account} ({self.current_account_id})",
                "🔄 Processing...",
                "",
                "",
                style="blue",
            )

        # Add completed results (show last 10 for performance)
        recent_results = list(self.account_results.values())[-10:]
        for result in recent_results:
            status_icon = self._get_status_icon(result.status)
            status_text = f"{status_icon} {result.status.title()}"

            time_text = f"{result.processing_time:.2f}s"
            if result.retry_count > 0:
                time_text += f" ({result.retry_count} retries)"

            details = ""
            if result.error_message:
                details = (
                    result.error_message[:50] + "..."
                    if len(result.error_message) > 50
                    else result.error_message
                )

            style = self._get_status_style(result.status)

            self.results_table.add_row(
                result.get_display_name(), status_text, time_text, details, style=style
            )

        # Update live display
        self.live_display.update(self.results_table)

    def _display_account_result(self, result: AccountResult):
        """Display immediate result for a completed account.

        Args:
            result: Account result to display
        """
        if self.show_live_results:
            # Live display will handle this
            return

        # Display immediate result for non-live mode
        status_icon = self._get_status_icon(result.status)
        style = self._get_status_style(result.status)

        message = f"{status_icon} {result.get_display_name()}: {result.status}"
        if result.processing_time > 0:
            message += f" ({result.processing_time:.2f}s"
            if result.retry_count > 0:
                message += f", {result.retry_count} retries"
            message += ")"

        if result.error_message:
            message += f" - {result.error_message}"

        self.console.print(message, style=style)

    def _display_failed_accounts(self, failed_accounts: List[AccountResult]):
        """Display detailed information about failed accounts.

        Args:
            failed_accounts: List of failed account results
        """
        if not failed_accounts:
            return

        self.console.print(f"\n❌ [red]Failed Accounts ({len(failed_accounts)}):[/red]")

        failed_table = Table()
        failed_table.add_column("Account", style="cyan")
        failed_table.add_column("Error", style="red")
        failed_table.add_column("Time", style="dim")
        failed_table.add_column("Retries", style="dim")

        for result in failed_accounts:
            failed_table.add_row(
                result.get_display_name(),
                result.error_message or "Unknown error",
                f"{result.processing_time:.2f}s",
                str(result.retry_count),
            )

        self.console.print(failed_table)

    def _get_status_icon(self, status: str) -> str:
        """Get icon for status.

        Args:
            status: Status string

        Returns:
            Unicode icon for the status
        """
        icons = {"success": "✅", "failed": "❌", "skipped": "⏭️"}
        return icons.get(status, "❓")

    def _get_status_style(self, status: str) -> str:
        """Get Rich style for status.

        Args:
            status: Status string

        Returns:
            Rich style string
        """
        styles = {"success": "green", "failed": "red", "skipped": "yellow"}
        return styles.get(status, "white")

    def get_current_stats(self) -> Dict[str, int]:
        """Get current processing statistics.

        Returns:
            Dictionary with current counts
        """
        return {
            "successful": self.successful_count,
            "failed": self.failed_count,
            "skipped": self.skipped_count,
            "total_processed": self.successful_count + self.failed_count + self.skipped_count,
            "remaining": self.total_items
            - (self.successful_count + self.failed_count + self.skipped_count),
        }

    def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed progress statistics for extended operations.

        Returns:
            Dictionary with detailed progress information
        """
        current_time = time.time()
        total_processed = self.successful_count + self.failed_count + self.skipped_count

        # Update detailed stats
        if self.operation_start_time:
            elapsed_time = current_time - self.operation_start_time
            self.detailed_stats.update(
                {
                    "elapsed_time": elapsed_time,
                    "total_processed": total_processed,
                    "remaining_accounts": self.total_items - total_processed,
                    "progress_percentage": (
                        (total_processed / self.total_items * 100) if self.total_items > 0 else 0
                    ),
                    "successful_percentage": (
                        (self.successful_count / total_processed * 100)
                        if total_processed > 0
                        else 0
                    ),
                    "failed_percentage": (
                        (self.failed_count / total_processed * 100) if total_processed > 0 else 0
                    ),
                    "current_time": current_time,
                    "last_update": current_time,
                }
            )

            # Calculate processing rates
            if elapsed_time > 0 and total_processed > 0:
                overall_rate = total_processed / elapsed_time
                self.detailed_stats.update(
                    {
                        "average_processing_rate": overall_rate,
                        "accounts_per_minute": overall_rate * 60,
                        "time_per_account": (
                            elapsed_time / total_processed if total_processed > 0 else 0
                        ),
                    }
                )

                # Estimate remaining time
                remaining_accounts = self.total_items - total_processed
                if remaining_accounts > 0 and overall_rate > 0:
                    estimated_remaining_time = remaining_accounts / overall_rate
                    estimated_completion_time = current_time + estimated_remaining_time
                    self.detailed_stats.update(
                        {
                            "estimated_remaining_time": estimated_remaining_time,
                            "estimated_completion_time": estimated_completion_time,
                            "estimated_completion_timestamp": estimated_completion_time,
                        }
                    )

        return self.detailed_stats.copy()

    def get_estimated_completion_info(self) -> Dict[str, Any]:
        """Get estimated completion information for large operations.

        Returns:
            Dictionary with completion estimates and timing information
        """
        stats = self.get_detailed_stats()

        completion_info = {
            "estimated_remaining_time_seconds": stats.get("estimated_remaining_time"),
            "estimated_completion_timestamp": stats.get("estimated_completion_time"),
            "current_processing_rate": stats.get("current_processing_rate", 0),
            "average_processing_rate": stats.get("average_processing_rate", 0),
            "accounts_per_minute": stats.get("accounts_per_minute", 0),
            "progress_percentage": stats.get("progress_percentage", 0),
            "time_elapsed": stats.get("elapsed_time", 0),
        }

        # Format human-readable estimates
        if completion_info["estimated_remaining_time_seconds"]:
            remaining_seconds = completion_info["estimated_remaining_time_seconds"]
            completion_info["estimated_remaining_time_formatted"] = self._format_duration(
                remaining_seconds
            )

            # Format estimated completion time
            if completion_info["estimated_completion_timestamp"]:
                import datetime

                completion_time = datetime.datetime.fromtimestamp(
                    completion_info["estimated_completion_timestamp"]
                )
                completion_info["estimated_completion_time_formatted"] = completion_time.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

        return completion_info

    def stop_live_display(self):
        """Stop the live display if active."""
        if self.live_display:
            self.live_display.stop()
            self.live_display = None

        # Clean up progress persistence
        if self.enable_persistence and self.progress_persistence:
            self.progress_persistence.delete_progress(self.operation_id)

    def _update_detailed_stats(self):
        """Update detailed progress statistics."""
        current_time = time.time()
        total_processed = self.successful_count + self.failed_count + self.skipped_count

        # Calculate current processing rate
        if current_time - self.last_rate_calculation >= 1.0:  # Update rate every second
            time_diff = current_time - self.last_rate_calculation
            processed_diff = total_processed - self.completed_items

            if time_diff > 0:
                current_rate = processed_diff / time_diff
                self.processing_rates.append(current_rate)

                # Keep only recent rates for rolling average
                if len(self.processing_rates) > self.rate_window_size:
                    self.processing_rates.pop(0)

                # Update detailed stats
                self.detailed_stats["current_processing_rate"] = current_rate
                if self.processing_rates:
                    self.detailed_stats["average_processing_rate"] = sum(
                        self.processing_rates
                    ) / len(self.processing_rates)

            self.last_rate_calculation = current_time
            self.completed_items = total_processed

    def _check_milestones(self):
        """Check if any milestones have been reached."""
        total_processed = self.successful_count + self.failed_count + self.skipped_count

        for milestone_name, milestone_count in self.milestone_times.items():
            if isinstance(milestone_count, int) and total_processed >= milestone_count:
                if milestone_name not in self.detailed_stats.get("completed_milestones", {}):
                    # Record milestone completion
                    if "completed_milestones" not in self.detailed_stats:
                        self.detailed_stats["completed_milestones"] = {}

                    self.detailed_stats["completed_milestones"][milestone_name] = {
                        "completed_at": time.time(),
                        "accounts_processed": total_processed,
                        "elapsed_time": (
                            time.time() - self.operation_start_time
                            if self.operation_start_time
                            else 0
                        ),
                    }

                    # Display milestone if not in live mode
                    if not self.show_live_results:
                        elapsed = self.detailed_stats["completed_milestones"][milestone_name][
                            "elapsed_time"
                        ]
                        self.console.print(
                            f"🎯 [cyan]Milestone reached: {milestone_name} ({total_processed} accounts) in {self._format_duration(elapsed)}[/cyan]"
                        )

    def _save_progress_if_enabled(self):
        """Save progress to disk if persistence is enabled."""
        if not self.enable_persistence or not self.progress_persistence:
            return

        current_time = time.time()
        if current_time - self.last_persistence_update >= self.persistence_interval:
            total_processed = self.successful_count + self.failed_count + self.skipped_count

            # Calculate processing rate for snapshot
            processing_rate = None
            if self.operation_start_time and total_processed > 0:
                elapsed = current_time - self.operation_start_time
                processing_rate = total_processed / elapsed if elapsed > 0 else 0

            # Calculate estimated completion time
            estimated_completion = None
            if processing_rate and processing_rate > 0:
                remaining = self.total_items - total_processed
                if remaining > 0:
                    estimated_completion = current_time + (remaining / processing_rate)

            snapshot = ProgressSnapshot(
                operation_id=self.operation_id,
                operation_type=self.operation_type,
                total_accounts=self.total_items,
                processed_accounts=total_processed,
                successful_count=self.successful_count,
                failed_count=self.failed_count,
                skipped_count=self.skipped_count,
                start_time=self.operation_start_time or current_time,
                last_update_time=current_time,
                current_account_id=self.current_account_id,
                current_account_name=self.current_account,
                estimated_completion_time=estimated_completion,
                processing_rate=processing_rate,
                batch_size=self.detailed_stats.get("batch_size", 10),
            )

            self.progress_persistence.save_progress(snapshot)
            self.last_persistence_update = current_time

    def _restore_from_snapshot(self, snapshot: ProgressSnapshot):
        """Restore progress from a saved snapshot.

        Args:
            snapshot: Progress snapshot to restore from
        """
        self.successful_count = snapshot.successful_count
        self.failed_count = snapshot.failed_count
        self.skipped_count = snapshot.skipped_count
        self.current_account_id = snapshot.current_account_id
        self.current_account = snapshot.current_account_name
        self.operation_start_time = snapshot.start_time
        self.operation_type = snapshot.operation_type

        # Update detailed stats with restored information
        self.detailed_stats.update(
            {
                "batch_size": snapshot.batch_size,
                "restored_from_snapshot": True,
                "snapshot_time": snapshot.last_update_time,
                "estimated_completion_time": snapshot.estimated_completion_time,
                "processing_rate_at_snapshot": snapshot.processing_rate,
            }
        )

    def display_detailed_progress_info(self):
        """Display detailed progress information for extended operations."""
        stats = self.get_detailed_stats()
        completion_info = self.get_estimated_completion_info()

        # Create detailed progress table
        progress_table = Table(title="Detailed Progress Information")
        progress_table.add_column("Metric", style="cyan", no_wrap=True)
        progress_table.add_column("Value", style="white")
        progress_table.add_column("Additional Info", style="dim")

        # Add progress metrics
        progress_table.add_row(
            "Progress",
            f"{stats.get('progress_percentage', 0):.1f}%",
            f"{stats.get('total_processed', 0)}/{self.total_items} accounts",
        )

        if completion_info.get("estimated_remaining_time_formatted"):
            progress_table.add_row(
                "Estimated Time Remaining",
                completion_info["estimated_remaining_time_formatted"],
                f"At current rate: {completion_info.get('accounts_per_minute', 0):.1f} accounts/min",
            )

        if completion_info.get("estimated_completion_time_formatted"):
            progress_table.add_row(
                "Estimated Completion",
                completion_info["estimated_completion_time_formatted"],
                "Based on current processing rate",
            )

        progress_table.add_row(
            "Processing Rate",
            f"{completion_info.get('accounts_per_minute', 0):.1f} accounts/min",
            f"{completion_info.get('average_processing_rate', 0):.2f} accounts/sec",
        )

        if stats.get("time_per_account"):
            progress_table.add_row(
                "Average Time per Account",
                f"{stats['time_per_account']:.2f}s",
                "Including retries and delays",
            )

        # Add success rate information
        if stats.get("total_processed", 0) > 0:
            progress_table.add_row(
                "Success Rate",
                f"{stats.get('successful_percentage', 0):.1f}%",
                f"{self.successful_count} successful, {self.failed_count} failed",
            )

        # Add milestone information
        completed_milestones = stats.get("completed_milestones", {})
        if completed_milestones:
            milestone_info = []
            for milestone, info in completed_milestones.items():
                elapsed = self._format_duration(info["elapsed_time"])
                milestone_info.append(f"{milestone} ({elapsed})")

            progress_table.add_row(
                "Milestones Completed",
                f"{len(completed_milestones)} milestones",
                ", ".join(milestone_info),
            )

        self.console.print("\n")
        self.console.print(progress_table)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        if seconds < 0:
            return "complete"

        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            remaining_seconds = int(seconds % 60)
            return f"{minutes}m {remaining_seconds}s"
        else:
            hours = int(seconds // 3600)
            remaining_minutes = int((seconds % 3600) // 60)
            return f"{hours}h {remaining_minutes}m"
