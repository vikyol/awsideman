"""
Performance optimization utilities for multi-account operations.

This module provides optimized configurations and utilities to dramatically
improve the performance of multi-account operations through intelligent
parallelization, caching, and API optimization.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rich.console import Console

console = Console()


@dataclass
class PerformanceConfig:
    """Configuration for performance optimization."""

    # Parallelization settings
    max_concurrent_accounts: int = 25  # Increased from 10
    batch_size: int = 50  # Increased from 10

    # Rate limiting (reduced for better performance)
    rate_limit_delay: float = 0.05  # Reduced from 0.1s

    # Timeout settings
    account_timeout: int = 60  # Reduced from 300s (5min) to 60s

    # Retry settings
    max_retries: int = 2  # Reduced from 3 for faster failure handling
    retry_delay: float = 0.5  # Reduced from 1.0s

    # API optimization
    use_session_reuse: bool = True  # Reuse HTTP sessions
    connection_pool_size: int = 50  # HTTP connection pool size

    # Progress reporting
    progress_update_interval: float = 0.5  # Update progress every 0.5s


class PerformanceOptimizer:
    """
    Performance optimizer for multi-account operations.

    Provides intelligent performance tuning based on organization size,
    operation type, and system capabilities.
    """

    def __init__(self):
        self.console = console

    def get_optimized_config(
        self,
        account_count: int,
        operation_type: str = "assign",
        system_resources: Optional[Dict[str, Any]] = None,
    ) -> PerformanceConfig:
        """
        Get optimized performance configuration based on operation parameters.

        Args:
            account_count: Number of accounts to process
            operation_type: Type of operation ('assign', 'revoke', etc.)
            system_resources: Optional system resource information

        Returns:
            Optimized PerformanceConfig
        """
        config = PerformanceConfig()

        # Scale parallelization based on account count
        if account_count <= 10:
            # Small organizations - moderate parallelization
            config.max_concurrent_accounts = min(account_count, 15)
            config.batch_size = account_count
            config.rate_limit_delay = 0.1
        elif account_count <= 50:
            # Medium organizations - high parallelization
            config.max_concurrent_accounts = min(account_count, 25)
            config.batch_size = min(account_count, 50)
            config.rate_limit_delay = 0.05
        else:
            # Large organizations - maximum parallelization
            config.max_concurrent_accounts = 30
            config.batch_size = 50
            config.rate_limit_delay = 0.02

        # Adjust for operation type
        if operation_type == "revoke":
            # Revoke operations can be slightly more aggressive
            config.max_concurrent_accounts = min(config.max_concurrent_accounts + 5, 35)
            config.rate_limit_delay *= 0.8

        # Adjust timeouts based on account count
        if account_count > 100:
            config.account_timeout = 45  # Shorter timeout for large orgs
        elif account_count < 10:
            config.account_timeout = 90  # Longer timeout for small orgs

        return config

    def estimate_performance_improvement(
        self, account_count: int, current_config: Optional[PerformanceConfig] = None
    ) -> Dict[str, Any]:
        """
        Estimate performance improvement with optimization.

        Args:
            account_count: Number of accounts
            current_config: Current configuration (if any)

        Returns:
            Performance improvement estimates
        """
        # Default conservative settings (current)
        default_config = PerformanceConfig(
            max_concurrent_accounts=10, batch_size=10, rate_limit_delay=0.1, account_timeout=300
        )

        current = current_config or default_config
        optimized = self.get_optimized_config(account_count)

        # Estimate time improvements
        # Current: sequential batches of 10 with 0.1s delay
        current_batches = (account_count + current.batch_size - 1) // current.batch_size
        current_time = (current_batches * current.rate_limit_delay) + (
            account_count * 2.5
        )  # ~2.5s per account

        # Optimized: larger batches with higher parallelization
        optimized_batches = (account_count + optimized.batch_size - 1) // optimized.batch_size
        optimized_time = (optimized_batches * optimized.rate_limit_delay) + (
            account_count * 1.2
        )  # ~1.2s per account

        improvement_ratio = current_time / optimized_time
        time_saved = current_time - optimized_time

        return {
            "current_estimated_time": round(current_time, 1),
            "optimized_estimated_time": round(optimized_time, 1),
            "improvement_ratio": round(improvement_ratio, 2),
            "time_saved_seconds": round(time_saved, 1),
            "time_saved_percentage": round((time_saved / current_time) * 100, 1),
            "current_config": current,
            "optimized_config": optimized,
        }

    def apply_optimizations(
        self, processor, account_count: int, operation_type: str = "assign"
    ) -> None:
        """
        Apply performance optimizations to a batch processor.

        Args:
            processor: MultiAccountBatchProcessor instance
            account_count: Number of accounts to process
            operation_type: Type of operation
        """
        config = self.get_optimized_config(account_count, operation_type)

        # Apply configuration
        processor.batch_size = config.batch_size
        processor.max_concurrent_accounts = config.max_concurrent_accounts
        processor.rate_limit_delay = config.rate_limit_delay

        # Update retry configuration if available
        if hasattr(processor, "retry_handler"):
            processor.retry_handler.max_retries = config.max_retries
            processor.retry_handler.base_delay = config.retry_delay

        self.console.print("[dim]Performance optimizations applied:[/dim]")
        self.console.print(
            f"[dim]  • Max concurrent accounts: {config.max_concurrent_accounts}[/dim]"
        )
        self.console.print(f"[dim]  • Batch size: {config.batch_size}[/dim]")
        self.console.print(f"[dim]  • Rate limit delay: {config.rate_limit_delay}s[/dim]")
        self.console.print(f"[dim]  • Account timeout: {config.account_timeout}s[/dim]")


class ParallelAccountProcessor:
    """
    High-performance parallel processor for account operations.

    Optimized for maximum throughput while respecting AWS API limits.
    """

    def __init__(self, config: PerformanceConfig):
        self.config = config
        self.console = console

    async def process_accounts_optimized(
        self,
        accounts: List[Any],
        operation_func: callable,
        progress_callback: Optional[callable] = None,
    ) -> List[Any]:
        """
        Process accounts with optimized parallelization.

        Args:
            accounts: List of accounts to process
            operation_func: Function to execute for each account
            progress_callback: Optional progress callback

        Returns:
            List of results
        """
        results = []
        total_accounts = len(accounts)
        processed_count = 0

        # Process in optimized batches
        for i in range(0, total_accounts, self.config.batch_size):
            batch_accounts = accounts[i : i + self.config.batch_size]

            # Process batch with high concurrency
            batch_results = await self._process_batch_parallel(batch_accounts, operation_func)

            results.extend(batch_results)
            processed_count += len(batch_accounts)

            # Update progress
            if progress_callback:
                progress_callback(processed_count, total_accounts)

            # Minimal delay between batches
            if i + self.config.batch_size < total_accounts:
                await asyncio.sleep(self.config.rate_limit_delay)

        return results

    async def _process_batch_parallel(
        self, batch_accounts: List[Any], operation_func: callable
    ) -> List[Any]:
        """Process a batch of accounts in parallel."""

        # Use ThreadPoolExecutor with optimized worker count
        with ThreadPoolExecutor(max_workers=self.config.max_concurrent_accounts) as executor:
            # Submit all accounts in batch
            futures = []
            for account in batch_accounts:
                future = executor.submit(operation_func, account)
                futures.append(future)

            # Collect results with timeout
            results = []
            for future in as_completed(futures, timeout=self.config.account_timeout):
                try:
                    result = future.result(timeout=self.config.account_timeout)
                    results.append(result)
                except Exception as e:
                    # Handle individual account failures
                    error_result = {
                        "status": "failed",
                        "error": str(e),
                        "account": getattr(future, "account", "unknown"),
                    }
                    results.append(error_result)

            return results


def create_performance_optimized_processor(
    aws_client_manager, account_count: int, operation_type: str = "assign"
):
    """
    Factory function to create a performance-optimized batch processor.

    Args:
        aws_client_manager: AWS client manager
        account_count: Number of accounts to process
        operation_type: Type of operation

    Returns:
        Optimized MultiAccountBatchProcessor
    """
    from .multi_account_batch import MultiAccountBatchProcessor

    # Create optimizer and get configuration
    optimizer = PerformanceOptimizer()
    config = optimizer.get_optimized_config(account_count, operation_type)

    # Create processor with optimized batch size
    processor = MultiAccountBatchProcessor(
        aws_client_manager=aws_client_manager, batch_size=config.batch_size
    )

    # Apply optimizations
    optimizer.apply_optimizations(processor, account_count, operation_type)

    return processor, config


def display_performance_recommendations(account_count: int, current_time: Optional[float] = None):
    """
    Display performance recommendations for multi-account operations.

    Args:
        account_count: Number of accounts
        current_time: Current operation time (if available)
    """
    optimizer = PerformanceOptimizer()
    estimates = optimizer.estimate_performance_improvement(account_count)

    console.print("\n[bold blue]Performance Optimization Recommendations[/bold blue]")
    console.print("=" * 50)

    if current_time:
        console.print(f"[yellow]Current operation time:[/yellow] {current_time:.1f} seconds")

    console.print(
        f"[green]Estimated optimized time:[/green] {estimates['optimized_estimated_time']} seconds"
    )
    console.print(f"[green]Expected improvement:[/green] {estimates['improvement_ratio']}x faster")
    console.print(
        f"[green]Time savings:[/green] {estimates['time_saved_seconds']} seconds ({estimates['time_saved_percentage']}%)"
    )

    console.print("\n[bold]Optimization Settings:[/bold]")
    config = estimates["optimized_config"]
    console.print(f"• Max concurrent accounts: {config.max_concurrent_accounts}")
    console.print(f"• Batch size: {config.batch_size}")
    console.print(f"• Rate limit delay: {config.rate_limit_delay}s")
    console.print(f"• Account timeout: {config.account_timeout}s")

    console.print(
        "\n[dim]These optimizations are automatically applied in the latest version.[/dim]"
    )
