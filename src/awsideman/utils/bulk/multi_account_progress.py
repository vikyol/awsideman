"""Multi-account progress tracking for bulk operations.

This module provides enhanced progress tracking specifically designed for
multi-account operations, extending the base ProgressTracker with account-level
progress display and real-time result reporting.

Classes:
    MultiAccountProgressTracker: Enhanced progress tracker for multi-account operations
"""
import time
from typing import Dict, Optional, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live

from .batch import ProgressTracker
from ..models import AccountResult, MultiAccountResults


class MultiAccountProgressTracker(ProgressTracker):
    """Enhanced progress tracker for multi-account operations.
    
    Extends the base ProgressTracker with account-level progress display,
    real-time result reporting, and comprehensive summary statistics.
    """
    
    def __init__(self, console: Console):
        """Initialize multi-account progress tracker.
        
        Args:
            console: Rich console for output
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
    
    def start_multi_account_progress(
        self, 
        total_accounts: int, 
        operation_type: str = "assign",
        show_live_results: bool = True
    ):
        """Start multi-account progress tracking.
        
        Args:
            total_accounts: Total number of accounts to process
            operation_type: Type of operation ('assign' or 'revoke')
            show_live_results: Whether to show live results table
        """
        self.show_live_results = show_live_results
        self.successful_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        
        # Choose between live display and base progress tracking
        if self.show_live_results:
            # Use live display instead of base progress
            self._initialize_live_display()
            self.total_items = total_accounts
        else:
            # Use base progress tracking
            description = f"Processing {operation_type} operations across {total_accounts} accounts"
            self.start_progress(total_accounts, description)
    
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
        elif not self.show_live_results:
            # Update progress description to show current account
            current_description = f"Processing: {account_name} ({account_id})"
            self.update_progress(0, current_description)
    
    def record_account_result(
        self, 
        account_id: str, 
        status: str, 
        account_name: str = "",
        error: Optional[str] = None,
        processing_time: float = 0.0,
        retry_count: int = 0
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
            retry_count=retry_count
        )
        
        # Store result
        self.account_results[account_id] = result
        
        # Update counters
        if status == 'success':
            self.successful_count += 1
        elif status == 'failed':
            self.failed_count += 1
        elif status == 'skipped':
            self.skipped_count += 1
        
        # Update display based on mode
        if self.show_live_results and self.live_display:
            # Update live display
            self._update_live_display()
        else:
            # Update base progress and display immediate result
            self.update_progress(1)
            self._display_account_result(result)
    
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
        panel = Panel(
            progress_text,
            title="Multi-Account Progress",
            border_style="blue"
        )
        
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
        
        # Finish base progress tracking if it was used
        if not self.show_live_results:
            self.finish_progress()
        
        # Create summary table
        summary_table = Table(title="Multi-Account Operation Summary")
        summary_table.add_column("Metric", style="cyan", no_wrap=True)
        summary_table.add_column("Value", style="white")
        summary_table.add_column("Percentage", style="dim")
        
        # Add summary rows
        summary_table.add_row(
            "Total Accounts", 
            str(results.total_accounts), 
            "100.0%"
        )
        summary_table.add_row(
            "✅ Successful", 
            str(len(results.successful_accounts)), 
            f"{results.success_rate:.1f}%",
            style="green"
        )
        summary_table.add_row(
            "❌ Failed", 
            str(len(results.failed_accounts)), 
            f"{results.failure_rate:.1f}%",
            style="red"
        )
        summary_table.add_row(
            "⏭️  Skipped", 
            str(len(results.skipped_accounts)), 
            f"{results.skip_rate:.1f}%",
            style="yellow"
        )
        summary_table.add_row(
            "⏱️  Duration", 
            f"{results.duration:.2f}s", 
            ""
        )
        summary_table.add_row(
            "📊 Batch Size", 
            str(results.batch_size), 
            ""
        )
        
        self.console.print("\n")
        self.console.print(summary_table)
        
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
            self.console.print(
                f"\n✅ [green]Operation completed successfully[/green]"
            )
    
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
            self.results_table, 
            console=self.console, 
            refresh_per_second=2,
            auto_refresh=True
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
                style="blue"
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
                details = result.error_message[:50] + "..." if len(result.error_message) > 50 else result.error_message
            
            style = self._get_status_style(result.status)
            
            self.results_table.add_row(
                result.get_display_name(),
                status_text,
                time_text,
                details,
                style=style
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
                str(result.retry_count)
            )
        
        self.console.print(failed_table)
    
    def _get_status_icon(self, status: str) -> str:
        """Get icon for status.
        
        Args:
            status: Status string
            
        Returns:
            Unicode icon for the status
        """
        icons = {
            'success': '✅',
            'failed': '❌',
            'skipped': '⏭️'
        }
        return icons.get(status, '❓')
    
    def _get_status_style(self, status: str) -> str:
        """Get Rich style for status.
        
        Args:
            status: Status string
            
        Returns:
            Rich style string
        """
        styles = {
            'success': 'green',
            'failed': 'red',
            'skipped': 'yellow'
        }
        return styles.get(status, 'white')
    
    def get_current_stats(self) -> Dict[str, int]:
        """Get current processing statistics.
        
        Returns:
            Dictionary with current counts
        """
        return {
            'successful': self.successful_count,
            'failed': self.failed_count,
            'skipped': self.skipped_count,
            'total_processed': self.successful_count + self.failed_count + self.skipped_count,
            'remaining': self.total_items - (self.successful_count + self.failed_count + self.skipped_count)
        }
    
    def stop_live_display(self):
        """Stop the live display if active."""
        if self.live_display:
            self.live_display.stop()
            self.live_display = None