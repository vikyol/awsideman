"""Multi-account batch processing components for bulk operations.

This module provides classes for batch processing of multi-account assignments
with progress tracking, error handling, and retry logic specifically designed
for operations across multiple AWS accounts.

Classes:
    MultiAccountBatchProcessor: Handles batch processing of multi-account assignments
"""
import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.exceptions import ClientError
from rich.console import Console

from .batch import BatchProcessor, RetryHandler
from .multi_account_progress import MultiAccountProgressTracker
from .resolver import ResourceResolver
from ..models import AccountInfo, AccountResult, MultiAccountAssignment, MultiAccountResults
from ...aws_clients.manager import AWSClientManager

console = Console()


class MultiAccountBatchProcessor(BatchProcessor):
    """Handles batch processing of multi-account assignments with progress tracking.
    
    Extends the base BatchProcessor to support operations across multiple AWS accounts
    with account-level error isolation, retry logic, and specialized progress tracking.
    """
    
    def __init__(self, aws_client_manager: AWSClientManager, batch_size: int = 10):
        """Initialize multi-account batch processor.
        
        Args:
            aws_client_manager: AWS client manager for API access
            batch_size: Number of accounts to process in parallel
        """
        super().__init__(aws_client_manager, batch_size)
        
        # Multi-account specific components
        self.progress_tracker = MultiAccountProgressTracker(console)
        self.resource_resolver: Optional[ResourceResolver] = None
        
        # Rate limiting configuration
        self.rate_limit_delay = 0.1  # Delay between account operations in seconds
        self.max_concurrent_accounts = min(batch_size, 10)  # Limit concurrent account operations
        
        # Multi-account results tracking
        self.multi_account_results: Optional[MultiAccountResults] = None
    
    def set_resource_resolver(self, instance_arn: str, identity_store_id: str):
        """Set up the resource resolver for name resolution.
        
        Args:
            instance_arn: SSO instance ARN
            identity_store_id: Identity Store ID
        """
        self.resource_resolver = ResourceResolver(
            self.aws_client_manager, 
            instance_arn, 
            identity_store_id
        )
    
    async def process_multi_account_operation(
        self,
        accounts: List[AccountInfo],
        permission_set_name: str,
        principal_name: str,
        principal_type: str,
        operation: str,
        instance_arn: str,
        dry_run: bool = False,
        continue_on_error: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> MultiAccountResults:
        """Process multi-account operation with account-level error isolation.
        
        Args:
            accounts: List of accounts to process
            permission_set_name: Name of the permission set
            principal_name: Name of the principal (user or group)
            principal_type: Type of principal ('USER' or 'GROUP')
            operation: Operation type ('assign' or 'revoke')
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes
            continue_on_error: If True, continue processing on individual failures
            progress_callback: Optional callback for progress updates
            
        Returns:
            MultiAccountResults with processing results
        """
        start_time = time.time()
        
        # Initialize results tracking
        successful_accounts = []
        failed_accounts = []
        skipped_accounts = []
        
        # Set up resource resolver if not already done
        if not self.resource_resolver:
            # Extract identity store ID from instance ARN (simplified approach)
            # In a real implementation, you might need to call describe_instance
            identity_store_id = "d-1234567890"  # This should be resolved properly
            self.set_resource_resolver(instance_arn, identity_store_id)
        
        # Create multi-account assignment for name resolution
        multi_assignment = MultiAccountAssignment(
            permission_set_name=permission_set_name,
            principal_name=principal_name,
            principal_type=principal_type,
            accounts=accounts,
            operation=operation
        )
        
        # Validate assignment configuration
        validation_errors = multi_assignment.validate()
        if validation_errors:
            # Create failed results for all accounts due to validation errors
            for account in accounts:
                failed_accounts.append(AccountResult(
                    account_id=account.account_id,
                    account_name=account.account_name,
                    status='failed',
                    error_message=f"Validation failed: {'; '.join(validation_errors)}",
                    processing_time=0.0
                ))
            
            return MultiAccountResults(
                total_accounts=len(accounts),
                successful_accounts=[],
                failed_accounts=failed_accounts,
                skipped_accounts=[],
                operation_type=operation,
                duration=time.time() - start_time,
                batch_size=self.batch_size
            )
        
        # Resolve names to ARNs/IDs
        try:
            await self._resolve_names(multi_assignment)
        except Exception as e:
            # Name resolution failed - fail all accounts
            error_msg = f"Name resolution failed: {str(e)}"
            for account in accounts:
                failed_accounts.append(AccountResult(
                    account_id=account.account_id,
                    account_name=account.account_name,
                    status='failed',
                    error_message=error_msg,
                    processing_time=0.0
                ))
            
            return MultiAccountResults(
                total_accounts=len(accounts),
                successful_accounts=[],
                failed_accounts=failed_accounts,
                skipped_accounts=[],
                operation_type=operation,
                duration=time.time() - start_time,
                batch_size=self.batch_size
            )
        
        # Start progress tracking (disable live results to avoid display conflicts)
        self.progress_tracker.start_multi_account_progress(
            total_accounts=len(accounts),
            operation_type=operation,
            show_live_results=False
        )
        
        try:
            # Process accounts in batches with error isolation
            processed_count = 0
            
            for i in range(0, len(accounts), self.max_concurrent_accounts):
                batch_accounts = accounts[i:i + self.max_concurrent_accounts]
                
                # Process batch with account-level isolation
                batch_results = await self._process_account_batch(
                    batch_accounts,
                    multi_assignment,
                    instance_arn,
                    dry_run,
                    continue_on_error
                )
                
                # Aggregate results
                successful_accounts.extend(batch_results['successful'])
                failed_accounts.extend(batch_results['failed'])
                skipped_accounts.extend(batch_results['skipped'])
                
                # Update progress
                processed_count += len(batch_accounts)
                
                # Call progress callback if provided
                if progress_callback:
                    progress_callback(processed_count, len(accounts))
                
                # Stop processing if continue_on_error is False and we have failures
                if not continue_on_error and batch_results['failed']:
                    console.print(f"[red]Stopping multi-account processing due to failures (continue_on_error=False)[/red]")
                    
                    # Mark remaining accounts as skipped
                    remaining_accounts = accounts[processed_count:]
                    for account in remaining_accounts:
                        skipped_accounts.append(AccountResult(
                            account_id=account.account_id,
                            account_name=account.account_name,
                            status='skipped',
                            error_message="Skipped due to previous failures",
                            processing_time=0.0
                        ))
                    break
                
                # Rate limiting between batches
                if i + self.max_concurrent_accounts < len(accounts):
                    await asyncio.sleep(self.rate_limit_delay)
            
            # Create final results
            end_time = time.time()
            self.multi_account_results = MultiAccountResults(
                total_accounts=len(accounts),
                successful_accounts=successful_accounts,
                failed_accounts=failed_accounts,
                skipped_accounts=skipped_accounts,
                operation_type=operation,
                duration=end_time - start_time,
                batch_size=self.batch_size
            )
            
            # Display final summary
            if dry_run:
                self._display_dry_run_summary(self.multi_account_results, multi_assignment)
            else:
                self.progress_tracker.display_final_summary(self.multi_account_results)
            
            return self.multi_account_results
            
        finally:
            # Ensure progress tracking is stopped
            self.progress_tracker.stop_live_display()
    
    async def _resolve_names(self, multi_assignment: MultiAccountAssignment):
        """Resolve permission set and principal names to ARNs/IDs.
        
        Args:
            multi_assignment: Multi-account assignment to resolve
            
        Raises:
            Exception: If name resolution fails
        """
        if not self.resource_resolver:
            raise Exception("Resource resolver not initialized")
        
        # Resolve permission set name to ARN
        ps_result = self.resource_resolver.resolve_permission_set_name(
            multi_assignment.permission_set_name
        )
        if not ps_result.success:
            raise Exception(f"Permission set resolution failed: {ps_result.error_message}")
        
        multi_assignment.permission_set_arn = ps_result.resolved_value
        
        # Resolve principal name to ID
        principal_result = self.resource_resolver.resolve_principal_name(
            multi_assignment.principal_name,
            multi_assignment.principal_type
        )
        if not principal_result.success:
            raise Exception(f"Principal resolution failed: {principal_result.error_message}")
        
        multi_assignment.principal_id = principal_result.resolved_value
    
    async def _process_account_batch(
        self,
        batch_accounts: List[AccountInfo],
        multi_assignment: MultiAccountAssignment,
        instance_arn: str,
        dry_run: bool,
        continue_on_error: bool
    ) -> Dict[str, List[AccountResult]]:
        """Process a batch of accounts with complete error isolation.
        
        Args:
            batch_accounts: List of accounts to process in this batch
            multi_assignment: Resolved multi-account assignment
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes
            continue_on_error: If True, continue processing on individual failures
            
        Returns:
            Dictionary with categorized account results
        """
        batch_results = {
            'successful': [],
            'failed': [],
            'skipped': []
        }
        
        # Use ThreadPoolExecutor for parallel processing with proper error isolation
        with ThreadPoolExecutor(max_workers=len(batch_accounts)) as executor:
            # Submit all accounts in the batch
            future_to_account = {}
            
            for account in batch_accounts:
                try:
                    future = executor.submit(
                        self._process_single_account_with_isolation,
                        account,
                        multi_assignment,
                        instance_arn,
                        dry_run
                    )
                    future_to_account[future] = account
                except Exception as e:
                    # Handle submission errors
                    console.print(f"[red]Error submitting account {account.account_id} for processing: {str(e)}[/red]")
                    error_result = AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        status='failed',
                        error_message=f"Submission error: {str(e)}",
                        processing_time=0.0
                    )
                    batch_results['failed'].append(error_result)
                    
                    if not continue_on_error:
                        console.print(f"[red]Account batch processing stopped due to submission error[/red]")
                        break
            
            # Collect results as they complete
            completed_count = 0
            for future in as_completed(future_to_account):
                account = future_to_account[future]
                completed_count += 1
                
                try:
                    result = future.result(timeout=300)  # 5 minute timeout per account
                    
                    # Record result in progress tracker
                    self.progress_tracker.record_account_result(
                        account_id=result.account_id,
                        status=result.status,
                        account_name=result.account_name,
                        error=result.error_message,
                        processing_time=result.processing_time,
                        retry_count=result.retry_count
                    )
                    
                    # Categorize result
                    if result.status == 'success':
                        batch_results['successful'].append(result)
                    elif result.status == 'failed':
                        batch_results['failed'].append(result)
                    else:
                        batch_results['skipped'].append(result)
                
                except TimeoutError:
                    # Handle timeout errors
                    error_msg = "Account processing timed out after 5 minutes"
                    console.print(f"[red]{error_msg} for account: {account.account_id}[/red]")
                    error_result = AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        status='failed',
                        error_message=error_msg,
                        processing_time=300.0
                    )
                    batch_results['failed'].append(error_result)
                    
                    # Record in progress tracker
                    self.progress_tracker.record_account_result(
                        account_id=error_result.account_id,
                        status=error_result.status,
                        account_name=error_result.account_name,
                        error=error_result.error_message,
                        processing_time=error_result.processing_time
                    )
                    
                    if not continue_on_error:
                        console.print(f"[red]Account batch processing stopped due to timeout[/red]")
                        break
                
                except Exception as e:
                    # Handle unexpected errors with detailed logging
                    error_msg = f"Unexpected error processing account: {str(e)}"
                    console.print(f"[red]{error_msg}[/red]")
                    console.print(f"[dim]Account context: {account.account_id} ({account.account_name})[/dim]")
                    
                    error_result = AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        status='failed',
                        error_message=error_msg,
                        processing_time=0.0
                    )
                    batch_results['failed'].append(error_result)
                    
                    # Record in progress tracker
                    self.progress_tracker.record_account_result(
                        account_id=error_result.account_id,
                        status=error_result.status,
                        account_name=error_result.account_name,
                        error=error_result.error_message,
                        processing_time=error_result.processing_time
                    )
                    
                    if not continue_on_error:
                        console.print(f"[red]Account batch processing stopped due to error (processed {completed_count}/{len(future_to_account)})[/red]")
                        break
        
        return batch_results
    
    def _process_single_account_with_isolation(
        self,
        account: AccountInfo,
        multi_assignment: MultiAccountAssignment,
        instance_arn: str,
        dry_run: bool
    ) -> AccountResult:
        """Process a single account with complete error isolation.
        
        This method wraps _process_single_account_operation with additional error handling
        to ensure that errors in one account don't affect others.
        
        Args:
            account: Account to process
            multi_assignment: Resolved multi-account assignment
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes
            
        Returns:
            AccountResult with operation result
        """
        try:
            # Update progress tracker with current account
            self.progress_tracker.update_current_account(
                account.account_name, 
                account.account_id
            )
            
            return self._process_single_account_operation(
                account, 
                multi_assignment, 
                instance_arn, 
                dry_run
            )
        except Exception as e:
            # Ensure complete isolation - any error is caught and converted to a failed result
            console.print(f"[red]Isolated error processing account {account.account_id}: {str(e)}[/red]")
            
            return AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status='failed',
                error_message=f"Isolated processing error: {str(e)}",
                processing_time=0.0
            )
    
    def _process_single_account_operation(
        self,
        account: AccountInfo,
        multi_assignment: MultiAccountAssignment,
        instance_arn: str,
        dry_run: bool
    ) -> AccountResult:
        """Process a single account operation.
        
        Args:
            account: Account to process
            multi_assignment: Resolved multi-account assignment
            instance_arn: SSO instance ARN
            dry_run: If True, validate without making changes
            
        Returns:
            AccountResult with operation result
        """
        start_time = time.time()
        
        # Validate that assignment is resolved
        if not multi_assignment.is_resolved():
            return AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status='failed',
                error_message="Assignment not properly resolved",
                processing_time=time.time() - start_time
            )
        
        # If dry run, simulate the operation and return preview result
        if dry_run:
            return self._simulate_account_operation(
                account, 
                multi_assignment, 
                instance_arn, 
                start_time
            )
        
        # Execute the actual operation with retry logic
        try:
            if multi_assignment.operation == 'assign':
                result = self._execute_assign_operation(
                    multi_assignment.principal_id,
                    multi_assignment.permission_set_arn,
                    account.account_id,
                    multi_assignment.principal_type,
                    instance_arn
                )
            elif multi_assignment.operation == 'revoke':
                result = self._execute_revoke_operation(
                    multi_assignment.principal_id,
                    multi_assignment.permission_set_arn,
                    account.account_id,
                    multi_assignment.principal_type,
                    instance_arn
                )
            else:
                raise ValueError(f"Unknown operation: {multi_assignment.operation}")
            
            return AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status='success',
                processing_time=time.time() - start_time,
                retry_count=result.get('retry_count', 0)
            )
            
        except Exception as e:
            return AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status='failed',
                error_message=str(e),
                processing_time=time.time() - start_time
            )
    
    def get_multi_account_results(self) -> Optional[MultiAccountResults]:
        """Get current multi-account processing results.
        
        Returns:
            MultiAccountResults with current state or None if no processing done
        """
        return self.multi_account_results
    
    def reset_multi_account_results(self):
        """Reset multi-account processing results."""
        self.multi_account_results = None
        self.progress_tracker = MultiAccountProgressTracker(console)
    
    def _simulate_account_operation(
        self,
        account: AccountInfo,
        multi_assignment: MultiAccountAssignment,
        instance_arn: str,
        start_time: float
    ) -> AccountResult:
        """Simulate an account operation for dry-run mode.
        
        This method checks if the assignment already exists and simulates
        what would happen during the actual operation.
        
        Args:
            account: Account to simulate operation for
            multi_assignment: Resolved multi-account assignment
            instance_arn: SSO instance ARN
            start_time: Operation start time
            
        Returns:
            AccountResult with simulation result
        """
        try:
            # Get SSO admin client for checking existing assignments
            sso_admin_client = self.aws_client_manager.get_identity_center_client()
            
            # Check if assignment currently exists
            list_params = {
                "InstanceArn": instance_arn,
                "AccountId": account.account_id,
                "PermissionSetArn": multi_assignment.permission_set_arn,
                "PrincipalId": multi_assignment.principal_id,
                "PrincipalType": multi_assignment.principal_type
            }
            
            response = sso_admin_client.list_account_assignments(**list_params)
            existing_assignments = response.get("AccountAssignments", [])
            assignment_exists = len(existing_assignments) > 0
            
            # Simulate operation based on current state and requested operation
            if multi_assignment.operation == 'assign':
                if assignment_exists:
                    # Assignment already exists - would be skipped
                    return AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        status='skipped',
                        error_message="Assignment already exists",
                        processing_time=time.time() - start_time
                    )
                else:
                    # Assignment would be created
                    return AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        status='success',
                        error_message="Would create new assignment",
                        processing_time=time.time() - start_time
                    )
            
            elif multi_assignment.operation == 'revoke':
                if assignment_exists:
                    # Assignment would be revoked
                    return AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        status='success',
                        error_message="Would revoke existing assignment",
                        processing_time=time.time() - start_time
                    )
                else:
                    # No assignment to revoke - would be skipped
                    return AccountResult(
                        account_id=account.account_id,
                        account_name=account.account_name,
                        status='skipped',
                        error_message="No assignment to revoke",
                        processing_time=time.time() - start_time
                    )
            
            else:
                return AccountResult(
                    account_id=account.account_id,
                    account_name=account.account_name,
                    status='failed',
                    error_message=f"Unknown operation: {multi_assignment.operation}",
                    processing_time=time.time() - start_time
                )
                
        except Exception as e:
            # If we can't check the current state, assume the operation would succeed
            # This ensures dry-run doesn't fail due to temporary API issues
            return AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status='success',
                error_message=f"Would attempt {multi_assignment.operation} (unable to verify current state: {str(e)})",
                processing_time=time.time() - start_time
            )
    
    def _display_dry_run_summary(
        self, 
        results: MultiAccountResults, 
        multi_assignment: MultiAccountAssignment
    ):
        """Display comprehensive dry-run summary with resolved information.
        
        Args:
            results: Multi-account operation results
            multi_assignment: Resolved multi-account assignment
        """
        from rich.panel import Panel
        from rich.table import Table
        
        # Display resolved assignment information
        console.print("\n[bold blue]🔍 Dry-Run Preview[/bold blue]")
        console.print()
        
        # Create assignment details panel
        assignment_details = []
        assignment_details.append(f"[bold]Operation:[/bold] {multi_assignment.operation.upper()}")
        assignment_details.append(f"[bold]Permission Set:[/bold] [green]{multi_assignment.permission_set_name}[/green]")
        assignment_details.append(f"[bold]Permission Set ARN:[/bold] [dim]{multi_assignment.permission_set_arn}[/dim]")
        assignment_details.append(f"[bold]Principal:[/bold] [cyan]{multi_assignment.principal_name}[/cyan] ({multi_assignment.principal_type})")
        assignment_details.append(f"[bold]Principal ID:[/bold] [dim]{multi_assignment.principal_id}[/dim]")
        assignment_details.append(f"[bold]Total Accounts:[/bold] {results.total_accounts}")
        
        assignment_panel = Panel(
            "\n".join(assignment_details),
            title="[bold]Resolved Assignment Details[/bold]",
            title_align="left",
            border_style="blue",
            padding=(1, 2)
        )
        console.print(assignment_panel)
        
        # Create accounts preview table
        console.print("\n[bold]Accounts Preview:[/bold]")
        
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Account", style="yellow", width=25)
        table.add_column("Account ID", style="dim", width=15)
        table.add_column("Predicted Action", style="green", width=20)
        table.add_column("Reason", style="cyan", width=30)
        
        # Combine all results for display
        all_results = (
            results.successful_accounts + 
            results.failed_accounts + 
            results.skipped_accounts
        )
        
        # Sort by account name for consistent display
        all_results.sort(key=lambda x: x.account_name)
        
        # Add rows to table (limit to first 20 for readability)
        display_limit = 20
        for i, result in enumerate(all_results[:display_limit]):
            if result.status == 'success':
                if multi_assignment.operation == 'assign':
                    action = "✓ CREATE" if "create" in result.error_message.lower() else "✓ ASSIGN"
                else:
                    action = "✓ REVOKE"
                reason = result.error_message or "Operation would succeed"
            elif result.status == 'skipped':
                action = "⊝ SKIP"
                reason = result.error_message or "No action needed"
            else:
                action = "✗ FAIL"
                reason = result.error_message or "Operation would fail"
            
            table.add_row(
                result.account_name,
                result.account_id,
                action,
                reason
            )
        
        console.print(table)
        
        # Show truncation message if needed
        if len(all_results) > display_limit:
            console.print(f"[dim]... and {len(all_results) - display_limit} more accounts[/dim]")
        
        # Display summary statistics
        console.print(f"\n[bold]Preview Summary:[/bold]")
        stats = results.get_summary_stats()
        
        console.print(f"  Total Accounts: {stats['total_accounts']}")
        console.print(f"  Would Succeed: [green]{stats['successful_count']}[/green] ({stats['success_rate']:.1f}%)")
        
        if stats['failed_count'] > 0:
            console.print(f"  Would Fail: [red]{stats['failed_count']}[/red] ({stats['failure_rate']:.1f}%)")
        
        if stats['skipped_count'] > 0:
            console.print(f"  Would Skip: [yellow]{stats['skipped_count']}[/yellow] ({stats['skip_rate']:.1f}%)")
        
        console.print(f"  Preview Duration: {stats['duration_seconds']:.2f} seconds")
        
        # Show action guidance
        console.print(f"\n[bold yellow]💡 Next Steps:[/bold yellow]")
        if multi_assignment.operation == 'assign':
            console.print("  • Remove [blue]--dry-run[/blue] flag to execute the assignment operation")
            console.print("  • Review accounts marked as 'SKIP' - they already have the assignment")
        else:
            console.print("  • Remove [blue]--dry-run[/blue] flag to execute the revocation operation")
            console.print("  • Review accounts marked as 'SKIP' - they don't have the assignment to revoke")
        
        if stats['failed_count'] > 0:
            console.print("  • Review accounts marked as 'FAIL' and resolve issues before executing")
        
        console.print("  • Use [blue]--continue-on-error[/blue] to proceed despite individual account failures")
    
    def configure_rate_limiting(self, delay: float, max_concurrent: int):
        """Configure rate limiting parameters.
        
        Args:
            delay: Delay between batch operations in seconds
            max_concurrent: Maximum number of concurrent account operations
        """
        self.rate_limit_delay = max(0.0, delay)
        self.max_concurrent_accounts = max(1, min(max_concurrent, self.batch_size))
        
        console.print(f"[dim]Rate limiting configured: {self.rate_limit_delay}s delay, {self.max_concurrent_accounts} max concurrent[/dim]")