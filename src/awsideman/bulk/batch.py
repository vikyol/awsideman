"""Batch processing components for bulk operations.

This module provides classes for batch processing of assignments with progress tracking,
error handling, and retry logic for AWS API operations.

Classes:
    BatchProcessor: Handles batch processing of assignments with parallel execution
    ProgressTracker: Manages progress display for bulk operations
    RetryHandler: Implements exponential backoff and retry logic for AWS API calls
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)

from ..aws_clients.manager import AWSClientManager
from ..rollback.logger import OperationLogger

console = Console()


@dataclass
class AssignmentResult:
    """Result of a single assignment operation."""

    principal_name: str
    permission_set_name: str
    account_name: str
    principal_type: str
    status: str  # 'success', 'failed', 'skipped'
    error_message: Optional[str] = None
    principal_id: Optional[str] = None
    permission_set_arn: Optional[str] = None
    account_id: Optional[str] = None
    processing_time: float = 0.0
    retry_count: int = 0
    row_number: Optional[int] = None
    assignment_index: Optional[int] = None
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()


@dataclass
class BulkOperationResults:
    """Results of a bulk operation."""

    total_processed: int
    successful: List[AssignmentResult] = field(default_factory=list)
    failed: List[AssignmentResult] = field(default_factory=list)
    skipped: List[AssignmentResult] = field(default_factory=list)
    operation_type: str = "assign"  # 'assign' or 'revoke'
    duration: float = 0.0
    batch_size: int = 10
    continue_on_error: bool = True
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    @property
    def success_count(self) -> int:
        """Number of successful operations."""
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        """Number of failed operations."""
        return len(self.failed)

    @property
    def skip_count(self) -> int:
        """Number of skipped operations."""
        return len(self.skipped)

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage."""
        if self.total_processed == 0:
            return 0.0
        return (self.success_count / self.total_processed) * 100

    def add_result(self, result: AssignmentResult):
        """Add a result to the appropriate category."""
        if result.status == "success":
            self.successful.append(result)
        elif result.status == "failed":
            self.failed.append(result)
        elif result.status == "skipped":
            self.skipped.append(result)
        else:
            raise ValueError(f"Invalid status: {result.status}")

    def get_all_results(self) -> List[AssignmentResult]:
        """Get all results in a single list."""
        return self.successful + self.failed + self.skipped


class RetryHandler:
    """Implements exponential backoff and retry logic for AWS API calls."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        """Initialize retry handler.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds between retries
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def should_retry(self, error: Exception) -> bool:
        """Determine if an error should trigger a retry.

        Args:
            error: Exception that occurred

        Returns:
            True if the error is retryable, False otherwise
        """
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "")

            # Retryable AWS errors
            retryable_codes = {
                "Throttling",
                "ThrottlingException",
                "TooManyRequestsException",
                "ServiceUnavailable",
                "InternalServerError",
                "RequestTimeout",
                "RequestTimeoutException",
                "PriorRequestNotComplete",
                "ConnectionError",
                "HTTPSConnectionPool",
                "RequestTimeTooSkewed",
                "ServiceTemporarilyUnavailable",
                "SlowDown",
                "BandwidthLimitExceeded",
            }

            return error_code in retryable_codes

        # Network-related errors are generally retryable
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True

        # Handle specific network-related exceptions that might be wrapped
        error_str = str(error).lower()
        network_error_indicators = [
            "connection",
            "timeout",
            "network",
            "dns",
            "socket",
            "ssl",
            "certificate",
            "handshake",
            "read timed out",
            "connection reset",
            "connection refused",
            "name resolution failed",
        ]

        for indicator in network_error_indicators:
            if indicator in error_str:
                return True

        return False

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        delay = self.base_delay * (2**attempt)
        return min(delay, self.max_delay)

    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function call

        Raises:
            Exception: The last exception if all retries are exhausted
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt == self.max_retries or not self.should_retry(e):
                    break

                delay = self.calculate_delay(attempt)
                console.print(
                    f"[yellow]Retry attempt {attempt + 1}/{self.max_retries} after {delay:.1f}s: {str(e)}[/yellow]"
                )
                await asyncio.sleep(delay)

        raise last_exception


class ProgressTracker:
    """Manages progress display for bulk operations."""

    def __init__(self, console: Console):
        """Initialize progress tracker.

        Args:
            console: Rich console for output
        """
        self.console = console
        self.progress: Optional[Progress] = None
        self.task_id: Optional[TaskID] = None
        self.start_time: Optional[float] = None
        self.total_items: int = 0
        self.completed_items: int = 0

    def start_progress(self, total: int, description: str = "Processing assignments"):
        """Start progress tracking.

        Args:
            total: Total number of items to process
            description: Description for the progress bar
        """
        self.total_items = total
        self.completed_items = 0

        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeRemainingColumn(),
            TextColumn("[dim]ETA: {task.fields[eta]}[/dim]"),
            console=self.console,
        )

        self.progress.start()
        self.task_id = self.progress.add_task(description, total=total, eta="calculating...")
        self.start_time = time.time()

    def update_progress(self, completed: int = 1, description: Optional[str] = None):
        """Update progress counter.

        Args:
            completed: Number of items completed (increment)
            description: Optional new description
        """
        if self.progress and self.task_id is not None:
            self.completed_items += completed
            eta = self._calculate_eta()

            self.progress.update(self.task_id, advance=completed, eta=eta)
            if description:
                self.progress.update(self.task_id, description=description)

    def set_progress(self, completed: int, description: Optional[str] = None):
        """Set absolute progress value.

        Args:
            completed: Absolute number of items completed
            description: Optional new description
        """
        if self.progress and self.task_id is not None:
            self.completed_items = completed
            eta = self._calculate_eta()

            self.progress.update(self.task_id, completed=completed, eta=eta)
            if description:
                self.progress.update(self.task_id, description=description)

    def finish_progress(self):
        """Complete progress tracking."""
        if self.progress:
            self.progress.stop()
            self.progress = None
            self.task_id = None

    def get_elapsed_time(self) -> float:
        """Get elapsed time since progress started.

        Returns:
            Elapsed time in seconds
        """
        if self.start_time:
            return time.time() - self.start_time
        return 0.0

    def _calculate_eta(self) -> str:
        """Calculate estimated time of arrival (completion).

        Returns:
            Formatted ETA string
        """
        if not self.start_time or self.completed_items == 0:
            return "calculating..."

        elapsed_time = self.get_elapsed_time()

        # Avoid division by zero
        if self.completed_items == 0:
            return "calculating..."

        # Calculate rate of completion
        rate = self.completed_items / elapsed_time  # items per second

        if rate == 0:
            return "calculating..."

        # Calculate remaining items and time
        remaining_items = self.total_items - self.completed_items

        if remaining_items <= 0:
            return "complete"

        estimated_remaining_seconds = remaining_items / rate

        # Format the ETA
        return self._format_duration(estimated_remaining_seconds)

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

    def get_progress_stats(self) -> Dict[str, Any]:
        """Get current progress statistics.

        Returns:
            Dictionary with progress statistics
        """
        elapsed = self.get_elapsed_time()

        stats = {
            "total_items": self.total_items,
            "completed_items": self.completed_items,
            "remaining_items": self.total_items - self.completed_items,
            "elapsed_time": elapsed,
            "completion_percentage": (
                (self.completed_items / self.total_items * 100) if self.total_items > 0 else 0
            ),
        }

        # Calculate rate and ETA
        if elapsed > 0 and self.completed_items > 0:
            rate = self.completed_items / elapsed
            stats["items_per_second"] = rate

            if rate > 0:
                remaining_time = (self.total_items - self.completed_items) / rate
                stats["estimated_remaining_time"] = remaining_time
                stats["estimated_completion_time"] = time.time() + remaining_time
            else:
                stats["estimated_remaining_time"] = None
                stats["estimated_completion_time"] = None
        else:
            stats["items_per_second"] = 0
            stats["estimated_remaining_time"] = None
            stats["estimated_completion_time"] = None

        return stats


class BatchProcessor:
    """Handles batch processing of assignments with progress tracking."""

    def __init__(self, aws_client_manager: AWSClientManager, batch_size: int = 10):
        """Initialize batch processor.

        Args:
            aws_client_manager: AWS client manager for API access
            batch_size: Number of assignments to process in parallel
        """
        self.aws_client_manager = aws_client_manager
        self.batch_size = batch_size
        self.retry_handler = RetryHandler()

        # Initialize AWS clients
        self.sso_admin_client = aws_client_manager.get_identity_center_client()
        self.identity_store_client = aws_client_manager.get_identity_store_client()

        # Initialize operation logger with profile isolation
        profile_name = getattr(aws_client_manager, "profile", None)
        # Only use profile if it's a string (not a Mock object in tests)
        if isinstance(profile_name, str):
            self.operation_logger = OperationLogger(profile=profile_name)
        else:
            # For tests or when profile is not a string, don't use profile isolation
            self.operation_logger = OperationLogger(profile=None)

        # Results tracking
        self.results = BulkOperationResults(total_processed=0, batch_size=batch_size)

    async def process_assignments(
        self,
        assignments: List[Dict[str, Any]],
        operation: str,
        instance_arn: str,
        dry_run: bool = False,
        continue_on_error: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> BulkOperationResults:
        """Process assignments in batches with progress tracking.

        Args:
            assignments: List of resolved assignment dictionaries
            operation: Operation type ('assign' or 'revoke')
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes
            continue_on_error: If True, continue processing on individual failures
            progress_callback: Optional callback for progress updates

        Returns:
            BulkOperationResults with processing results
        """
        start_time = time.time()

        # Initialize results
        self.results = BulkOperationResults(
            total_processed=len(assignments),
            operation_type=operation,
            batch_size=self.batch_size,
            continue_on_error=continue_on_error,
            start_time=start_time,
        )

        # Initialize progress tracker
        progress_tracker = ProgressTracker(console)
        progress_tracker.start_progress(
            total=len(assignments),
            description=f"{'Validating' if dry_run else 'Processing'} {operation} operations",
        )

        try:
            # Process assignments in batches
            processed_count = 0

            for i in range(0, len(assignments), self.batch_size):
                batch = assignments[i : i + self.batch_size]

                # Process batch
                batch_results = await self._process_batch(
                    batch, operation, instance_arn, dry_run, continue_on_error
                )

                # Update results
                self.results.successful.extend(batch_results["successful"])
                self.results.failed.extend(batch_results["failed"])
                self.results.skipped.extend(batch_results["skipped"])

                # Update progress
                processed_count += len(batch)
                progress_tracker.set_progress(processed_count)

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(processed_count, len(assignments))

                # Stop processing if continue_on_error is False and we have failures
                if not continue_on_error and batch_results["failed"]:
                    console.print(
                        "[red]Stopping processing due to failures (continue_on_error=False)[/red]"
                    )
                    break

            # Calculate final duration and set end time
            end_time = time.time()
            self.results.duration = end_time - start_time
            self.results.end_time = end_time

            # Log successful operations (only if not dry run)
            if not dry_run and self.results.successful:
                self._log_bulk_operations(self.results.successful, operation, assignments)

        finally:
            progress_tracker.finish_progress()

        return self.results

    async def _process_batch(
        self,
        batch: List[Dict[str, Any]],
        operation: str,
        instance_arn: str,
        dry_run: bool,
        continue_on_error: bool,
    ) -> Dict[str, List[AssignmentResult]]:
        """Process a single batch of assignments.

        Args:
            batch: List of assignments to process
            operation: Operation type ('assign' or 'revoke')
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes
            continue_on_error: If True, continue processing on individual failures

        Returns:
            Dictionary with categorized results
        """
        batch_results = {"successful": [], "failed": [], "skipped": []}

        # Use ThreadPoolExecutor for parallel processing with proper error isolation
        with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
            # Submit all assignments in the batch
            future_to_assignment = {}

            for assignment in batch:
                try:
                    future = executor.submit(
                        self._process_single_assignment_with_isolation,
                        assignment,
                        operation,
                        instance_arn,
                        dry_run,
                    )
                    future_to_assignment[future] = assignment
                except Exception as e:
                    # Handle submission errors
                    console.print(
                        f"[red]Error submitting assignment for processing: {str(e)}[/red]"
                    )
                    error_result = self._create_error_result(
                        assignment, f"Submission error: {str(e)}"
                    )
                    batch_results["failed"].append(error_result)

                    if not continue_on_error:
                        console.print("[red]Batch processing stopped due to submission error[/red]")
                        break

            # Collect results as they complete
            completed_count = 0
            for future in as_completed(future_to_assignment):
                assignment = future_to_assignment[future]
                completed_count += 1

                try:
                    result = future.result(timeout=300)  # 5 minute timeout per assignment

                    # Categorize result
                    if result.status == "success":
                        batch_results["successful"].append(result)
                    elif result.status == "failed":
                        batch_results["failed"].append(result)
                    else:
                        batch_results["skipped"].append(result)

                except TimeoutError:
                    # Handle timeout errors
                    error_msg = "Assignment processing timed out after 5 minutes"
                    console.print(
                        f"[red]{error_msg} for assignment: {assignment.get('principal_name', 'unknown')}[/red]"
                    )
                    error_result = self._create_error_result(assignment, error_msg)
                    batch_results["failed"].append(error_result)

                    if not continue_on_error:
                        console.print("[red]Batch processing stopped due to timeout[/red]")
                        break

                except Exception as e:
                    # Handle unexpected errors with detailed logging
                    error_msg = f"Unexpected error processing assignment: {str(e)}"
                    console.print(f"[red]{error_msg}[/red]")

                    # Log additional context for debugging
                    principal_name = assignment.get("principal_name", "unknown")
                    permission_set_name = assignment.get("permission_set_name", "unknown")
                    account_name = assignment.get("account_name", "unknown")
                    console.print(
                        f"[dim]Assignment context: {principal_name} -> {permission_set_name} @ {account_name}[/dim]"
                    )

                    error_result = self._create_error_result(assignment, error_msg)
                    batch_results["failed"].append(error_result)

                    if not continue_on_error:
                        console.print(
                            f"[red]Batch processing stopped due to error (processed {completed_count}/{len(future_to_assignment)})[/red]"
                        )
                        break

        return batch_results

    def _process_single_assignment_with_isolation(
        self, assignment: Dict[str, Any], operation: str, instance_arn: str, dry_run: bool
    ) -> AssignmentResult:
        """Process a single assignment with complete error isolation.

        This method wraps _process_single_assignment with additional error handling
        to ensure that errors in one assignment don't affect others.

        Args:
            assignment: Assignment dictionary with resolved IDs/ARNs
            operation: Operation type ('assign' or 'revoke')
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes

        Returns:
            AssignmentResult with operation result
        """
        try:
            return self._process_single_assignment(assignment, operation, instance_arn, dry_run)
        except Exception as e:
            # Ensure complete isolation - any error is caught and converted to a failed result
            principal_name = assignment.get("principal_name", "unknown")
            console.print(f"[red]Isolated error processing {principal_name}: {str(e)}[/red]")

            return AssignmentResult(
                principal_name=assignment.get("principal_name", ""),
                permission_set_name=assignment.get("permission_set_name", ""),
                account_name=assignment.get("account_name", ""),
                principal_type=assignment.get("principal_type", "USER"),
                principal_id=assignment.get("principal_id"),
                permission_set_arn=assignment.get("permission_set_arn"),
                account_id=assignment.get("account_id"),
                status="failed",
                error_message=f"Isolated processing error: {str(e)}",
                row_number=assignment.get("_row_number"),
                assignment_index=assignment.get("_assignment_index"),
            )

    def _process_single_assignment(
        self, assignment: Dict[str, Any], operation: str, instance_arn: str, dry_run: bool
    ) -> AssignmentResult:
        """Process a single assignment.

        Args:
            assignment: Assignment dictionary with resolved IDs/ARNs
            operation: Operation type ('assign' or 'revoke')
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes

        Returns:
            AssignmentResult with operation result
        """
        start_time = time.time()

        # Extract assignment data
        principal_name = assignment.get("principal_name", "")
        permission_set_name = assignment.get("permission_set_name", "")
        account_name = assignment.get("account_name", "")
        principal_type = assignment.get("principal_type", "USER")
        principal_id = assignment.get("principal_id")
        permission_set_arn = assignment.get("permission_set_arn")
        account_id = assignment.get("account_id")

        # Get row/index information for error reporting
        row_number = assignment.get("_row_number")
        assignment_index = assignment.get("_assignment_index")

        # Check if assignment was resolved successfully
        if not assignment.get("resolution_success", False):
            resolution_errors = assignment.get("resolution_errors", [])
            error_message = (
                "; ".join(resolution_errors) if resolution_errors else "Resolution failed"
            )

            return AssignmentResult(
                principal_name=principal_name,
                permission_set_name=permission_set_name,
                account_name=account_name,
                principal_type=principal_type,
                status="failed",
                error_message=f"Resolution failed: {error_message}",
                processing_time=time.time() - start_time,
                row_number=row_number,
                assignment_index=assignment_index,
            )

        # Validate required resolved fields
        if not all([principal_id, permission_set_arn, account_id]):
            missing_fields = []
            if not principal_id:
                missing_fields.append("principal_id")
            if not permission_set_arn:
                missing_fields.append("permission_set_arn")
            if not account_id:
                missing_fields.append("account_id")

            return AssignmentResult(
                principal_name=principal_name,
                permission_set_name=permission_set_name,
                account_name=account_name,
                principal_type=principal_type,
                status="failed",
                error_message=f"Missing resolved fields: {', '.join(missing_fields)}",
                processing_time=time.time() - start_time,
                row_number=row_number,
                assignment_index=assignment_index,
            )

        # If dry run, just validate and return success
        if dry_run:
            return AssignmentResult(
                principal_name=principal_name,
                permission_set_name=permission_set_name,
                account_name=account_name,
                principal_type=principal_type,
                principal_id=principal_id,
                permission_set_arn=permission_set_arn,
                account_id=account_id,
                status="success",
                processing_time=time.time() - start_time,
                row_number=row_number,
                assignment_index=assignment_index,
            )

        # Execute the actual operation
        try:
            if operation == "assign":
                result = self._execute_assign_operation(
                    principal_id, permission_set_arn, account_id, principal_type, instance_arn
                )
            elif operation == "revoke":
                result = self._execute_revoke_operation(
                    principal_id, permission_set_arn, account_id, principal_type, instance_arn
                )
            else:
                raise ValueError(f"Unknown operation: {operation}")

            return AssignmentResult(
                principal_name=principal_name,
                permission_set_name=permission_set_name,
                account_name=account_name,
                principal_type=principal_type,
                principal_id=principal_id,
                permission_set_arn=permission_set_arn,
                account_id=account_id,
                status="success",
                processing_time=time.time() - start_time,
                retry_count=result.get("retry_count", 0),
                row_number=row_number,
                assignment_index=assignment_index,
            )

        except Exception as e:
            return AssignmentResult(
                principal_name=principal_name,
                permission_set_name=permission_set_name,
                account_name=account_name,
                principal_type=principal_type,
                principal_id=principal_id,
                permission_set_arn=permission_set_arn,
                account_id=account_id,
                status="failed",
                error_message=str(e),
                processing_time=time.time() - start_time,
                row_number=row_number,
                assignment_index=assignment_index,
            )

    def _create_error_result(
        self, assignment: Dict[str, Any], error_message: str
    ) -> AssignmentResult:
        """Create an error result for an assignment.

        Args:
            assignment: Assignment dictionary
            error_message: Error message

        Returns:
            AssignmentResult with error status
        """
        return AssignmentResult(
            principal_name=assignment.get("principal_name", ""),
            permission_set_name=assignment.get("permission_set_name", ""),
            account_name=assignment.get("account_name", ""),
            principal_type=assignment.get("principal_type", "USER"),
            principal_id=assignment.get("principal_id"),
            permission_set_arn=assignment.get("permission_set_arn"),
            account_id=assignment.get("account_id"),
            status="failed",
            error_message=error_message,
            row_number=assignment.get("_row_number"),
            assignment_index=assignment.get("_assignment_index"),
        )

    def get_results(self) -> BulkOperationResults:
        """Get current processing results.

        Returns:
            BulkOperationResults with current state
        """
        return self.results

    def reset_results(self):
        """Reset processing results."""
        self.results = BulkOperationResults(total_processed=0, batch_size=self.batch_size)

    def _format_aws_error(self, error: Exception, operation: str = "operation") -> str:
        """Format AWS error for user-friendly display.

        Args:
            error: Exception that occurred
            operation: Operation being performed ('assign' or 'revoke')

        Returns:
            Formatted error message
        """
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            error_message = error.response.get("Error", {}).get("Message", str(error))

            # Provide context-specific error messages
            if error_code == "AccessDeniedException":
                return f"Access denied for {operation} operation. Check your AWS permissions for Identity Center operations."
            elif error_code == "ValidationException":
                return f"Invalid request for {operation} operation: {error_message}"
            elif error_code == "ResourceNotFoundException":
                return f"Resource not found during {operation} operation: {error_message}"
            elif error_code == "ConflictException":
                return f"Conflict during {operation} operation: {error_message}"
            elif error_code in ["Throttling", "ThrottlingException", "TooManyRequestsException"]:
                return (
                    f"Rate limit exceeded during {operation} operation. Will retry automatically."
                )
            elif error_code in ["ServiceUnavailable", "InternalServerError"]:
                return f"AWS service temporarily unavailable during {operation} operation. Will retry automatically."
            else:
                return f"AWS error during {operation} operation ({error_code}): {error_message}"

        # Handle network errors
        error_str = str(error).lower()
        if any(indicator in error_str for indicator in ["connection", "timeout", "network"]):
            return f"Network error during {operation} operation: {str(error)}. Will retry automatically."

        # Generic error
        return f"Error during {operation} operation: {str(error)}"

    def _execute_assign_operation(
        self,
        principal_id: str,
        permission_set_arn: str,
        account_id: str,
        principal_type: str,
        instance_arn: str,
    ) -> Dict[str, Any]:
        """Execute assignment operation with retry logic.

        Args:
            principal_id: Principal ID
            permission_set_arn: Permission set ARN
            account_id: Account ID
            principal_type: Principal type ('USER' or 'GROUP')
            instance_arn: SSO instance ARN

        Returns:
            Dictionary with operation result and retry count

        Raises:
            Exception: If assignment operation fails after retries
        """
        retry_count = 0
        last_exception = None

        for attempt in range(self.retry_handler.max_retries + 1):
            try:
                # Check if assignment already exists
                list_params = {
                    "InstanceArn": instance_arn,
                    "AccountId": account_id,
                    "PermissionSetArn": permission_set_arn,
                }

                existing_response = self.sso_admin_client.list_account_assignments(**list_params)
                existing_assignments = existing_response.get("AccountAssignments", [])

                # Filter assignments to find the specific principal
                matching_assignments = [
                    assignment
                    for assignment in existing_assignments
                    if assignment.get("PrincipalId") == principal_id
                    and assignment.get("PrincipalType") == principal_type
                ]

                if matching_assignments:
                    # Assignment already exists - this should be skipped, not counted as success
                    return {
                        "status": "skipped",
                        "message": "Assignment already exists",
                        "retry_count": retry_count,
                    }

                # Create the assignment
                create_params = {
                    "InstanceArn": instance_arn,
                    "TargetId": account_id,
                    "TargetType": "AWS_ACCOUNT",
                    "PermissionSetArn": permission_set_arn,
                    "PrincipalType": principal_type,
                    "PrincipalId": principal_id,
                }

                response = self.sso_admin_client.create_account_assignment(**create_params)

                # Check if the operation was successful
                if response.get("AccountAssignmentCreationStatus", {}).get("Status") == "SUCCEEDED":
                    return {
                        "status": "success",
                        "message": "Assignment created successfully",
                        "retry_count": retry_count,
                        "request_id": response.get("AccountAssignmentCreationStatus", {}).get(
                            "RequestId"
                        ),
                    }
                elif (
                    response.get("AccountAssignmentCreationStatus", {}).get("Status")
                    == "IN_PROGRESS"
                ):
                    # For IN_PROGRESS status, we consider it successful as the operation was accepted
                    return {
                        "status": "success",
                        "message": "Assignment creation in progress",
                        "retry_count": retry_count,
                        "request_id": response.get("AccountAssignmentCreationStatus", {}).get(
                            "RequestId"
                        ),
                    }
                else:
                    # Handle failed status
                    failure_reason = response.get("AccountAssignmentCreationStatus", {}).get(
                        "FailureReason", "Unknown failure"
                    )
                    raise Exception(f"Assignment creation failed: {failure_reason}")

            except ClientError as e:
                last_exception = e
                error_code = e.response.get("Error", {}).get("Code", "")

                # Handle specific error cases
                if error_code == "ConflictException":
                    # Assignment might already exist due to race condition
                    return {
                        "status": "skipped",
                        "message": "Assignment already exists (conflict resolved)",
                        "retry_count": retry_count,
                    }

                # Check if this is a retryable error
                if attempt < self.retry_handler.max_retries and self.retry_handler.should_retry(e):
                    retry_count += 1
                    delay = self.retry_handler.calculate_delay(attempt)
                    console.print(
                        f"[yellow]Retrying assign operation (attempt {attempt + 1}/{self.retry_handler.max_retries + 1}) after {delay:.1f}s: {str(e)}[/yellow]"
                    )
                    import time

                    time.sleep(delay)
                    continue

                # Not retryable or max retries exceeded
                raise e

            except Exception as e:
                last_exception = e

                # Check if this is a retryable error
                if attempt < self.retry_handler.max_retries and self.retry_handler.should_retry(e):
                    retry_count += 1
                    delay = self.retry_handler.calculate_delay(attempt)
                    console.print(
                        f"[yellow]Retrying assign operation (attempt {attempt + 1}/{self.retry_handler.max_retries + 1}) after {delay:.1f}s: {str(e)}[/yellow]"
                    )
                    import time

                    time.sleep(delay)
                    continue

                # Not retryable or max retries exceeded
                raise e

        # This should not be reached, but just in case
        if last_exception:
            raise last_exception

    def _execute_revoke_operation(
        self,
        principal_id: str,
        permission_set_arn: str,
        account_id: str,
        principal_type: str,
        instance_arn: str,
    ) -> Dict[str, Any]:
        """Execute revoke operation with retry logic.

        Args:
            principal_id: Principal ID
            permission_set_arn: Permission set ARN
            account_id: Account ID
            principal_type: Principal type ('USER' or 'GROUP')
            instance_arn: SSO instance ARN

        Returns:
            Dictionary with operation result and retry count

        Raises:
            Exception: If revoke operation fails after retries
        """
        retry_count = 0
        last_exception = None

        for attempt in range(self.retry_handler.max_retries + 1):
            try:
                # Check if assignment exists
                list_params = {
                    "InstanceArn": instance_arn,
                    "AccountId": account_id,
                    "PermissionSetArn": permission_set_arn,
                }

                existing_response = self.sso_admin_client.list_account_assignments(**list_params)
                existing_assignments = existing_response.get("AccountAssignments", [])

                # Filter assignments to find the specific principal
                matching_assignments = [
                    assignment
                    for assignment in existing_assignments
                    if assignment.get("PrincipalId") == principal_id
                    and assignment.get("PrincipalType") == principal_type
                ]

                if not matching_assignments:
                    # Assignment doesn't exist - this should be skipped, not counted as success
                    return {
                        "status": "skipped",
                        "message": "Assignment does not exist (already revoked)",
                        "retry_count": retry_count,
                    }

                # Delete the assignment
                delete_params = {
                    "InstanceArn": instance_arn,
                    "TargetId": account_id,
                    "TargetType": "AWS_ACCOUNT",
                    "PermissionSetArn": permission_set_arn,
                    "PrincipalType": principal_type,
                    "PrincipalId": principal_id,
                }

                response = self.sso_admin_client.delete_account_assignment(**delete_params)

                # Check if the operation was successful
                if response.get("AccountAssignmentDeletionStatus", {}).get("Status") == "SUCCEEDED":
                    return {
                        "status": "success",
                        "message": "Assignment revoked successfully",
                        "retry_count": retry_count,
                        "request_id": response.get("AccountAssignmentDeletionStatus", {}).get(
                            "RequestId"
                        ),
                    }
                elif (
                    response.get("AccountAssignmentDeletionStatus", {}).get("Status")
                    == "IN_PROGRESS"
                ):
                    # For IN_PROGRESS status, we consider it successful as the operation was accepted
                    return {
                        "status": "success",
                        "message": "Assignment revocation in progress",
                        "retry_count": retry_count,
                        "request_id": response.get("AccountAssignmentDeletionStatus", {}).get(
                            "RequestId"
                        ),
                    }
                else:
                    # Handle failed status
                    failure_reason = response.get("AccountAssignmentDeletionStatus", {}).get(
                        "FailureReason", "Unknown failure"
                    )
                    raise Exception(f"Assignment revocation failed: {failure_reason}")

            except ClientError as e:
                last_exception = e
                error_code = e.response.get("Error", {}).get("Code", "")

                # Handle specific error cases
                if error_code == "ResourceNotFoundException":
                    # Assignment doesn't exist - should be skipped, not counted as success
                    return {
                        "status": "skipped",
                        "message": "Assignment does not exist (already revoked)",
                        "retry_count": retry_count,
                    }

                # Check if this is a retryable error
                if attempt < self.retry_handler.max_retries and self.retry_handler.should_retry(e):
                    retry_count += 1
                    delay = self.retry_handler.calculate_delay(attempt)
                    console.print(
                        f"[yellow]Retrying revoke operation (attempt {attempt + 1}/{self.retry_handler.max_retries + 1}) after {delay:.1f}s: {str(e)}[/yellow]"
                    )
                    import time

                    time.sleep(delay)
                    continue

                # Not retryable or max retries exceeded
                raise e

            except Exception as e:
                last_exception = e

                # Check if this is a retryable error
                if attempt < self.retry_handler.max_retries and self.retry_handler.should_retry(e):
                    retry_count += 1
                    delay = self.retry_handler.calculate_delay(attempt)
                    console.print(
                        f"[yellow]Retrying revoke operation (attempt {attempt + 1}/{self.retry_handler.max_retries + 1}) after {delay:.1f}s: {str(e)}[/yellow]"
                    )
                    import time

                    time.sleep(delay)
                    continue

                # Not retryable or max retries exceeded
                raise e

        # This should not be reached, but just in case
        if last_exception:
            raise last_exception

    def _log_bulk_operations(
        self,
        successful_results: List[AssignmentResult],
        operation: str,
        original_assignments: List[Dict[str, Any]],
    ) -> None:
        """Log successful bulk operations for rollback tracking.

        Args:
            successful_results: List of successful assignment results
            operation: Operation type ('assign' or 'revoke')
            original_assignments: Original assignment data for metadata
        """
        try:
            # Group successful results by principal and permission set
            # This allows us to log one operation per unique combination
            operation_groups = {}

            for result in successful_results:
                # Create a key for grouping
                key = (result.principal_id, result.principal_type, result.permission_set_arn)

                if key not in operation_groups:
                    operation_groups[key] = {
                        "principal_id": result.principal_id,
                        "principal_type": result.principal_type,
                        "principal_name": result.principal_name,
                        "permission_set_arn": result.permission_set_arn,
                        "permission_set_name": result.permission_set_name,
                        "account_ids": [],
                        "account_names": [],
                        "results": [],
                    }

                # Add account information
                operation_groups[key]["account_ids"].append(result.account_id)
                operation_groups[key]["account_names"].append(result.account_name)
                operation_groups[key]["results"].append(
                    {
                        "account_id": result.account_id,
                        "success": True,
                        "error": None,
                        "duration_ms": int((result.processing_time or 0) * 1000),
                    }
                )

            # Extract metadata from original assignments
            metadata = self._extract_bulk_metadata(original_assignments)

            # Log each operation group
            for group_data in operation_groups.values():
                try:
                    operation_id = self.operation_logger.log_operation(
                        operation_type=operation,
                        principal_id=group_data["principal_id"],
                        principal_type=group_data["principal_type"],
                        principal_name=group_data["principal_name"],
                        permission_set_arn=group_data["permission_set_arn"],
                        permission_set_name=group_data["permission_set_name"],
                        account_ids=group_data["account_ids"],
                        account_names=group_data["account_names"],
                        results=group_data["results"],
                        metadata=metadata,
                    )

                    console.print(f"[dim]Logged {operation} operation: {operation_id}[/dim]")

                except Exception as e:
                    # Don't fail the entire operation if logging fails
                    console.print(
                        f"[yellow]Warning: Failed to log operation for {group_data['principal_name']}: {str(e)}[/yellow]"
                    )

        except Exception as e:
            # Don't fail the entire operation if logging fails
            console.print(f"[yellow]Warning: Failed to log bulk operations: {str(e)}[/yellow]")

    def _extract_bulk_metadata(self, original_assignments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract metadata from original assignments for operation logging.

        Args:
            original_assignments: Original assignment data

        Returns:
            Dictionary with metadata for operation logging
        """
        metadata = {
            "source": "bulk_operation",
            "batch_size": self.batch_size,
            "total_assignments": len(original_assignments),
        }

        # Try to extract input file information if available
        if original_assignments:
            first_assignment = original_assignments[0]
            if "_input_file" in first_assignment:
                metadata["input_file"] = first_assignment["_input_file"]
            if "_file_format" in first_assignment:
                metadata["file_format"] = first_assignment["_file_format"]

        return metadata
