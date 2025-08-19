"""
CLI commands for managing backup performance optimizations.

This module provides commands to:
- Enable/disable performance optimizations
- View performance statistics
- Configure optimization settings
- Run performance benchmarks
"""

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...backup_restore.performance import PerformanceOptimizer
from ...utils.config import Config

app = typer.Typer(help="Manage backup performance optimizations")
console = Console()


@app.command("enable")
def enable_optimizations(
    compression: bool = typer.Option(
        True, "--compression/--no-compression", help="Enable compression"
    ),
    deduplication: bool = typer.Option(
        True, "--deduplication/--no-deduplication", help="Enable deduplication"
    ),
    parallel_processing: bool = typer.Option(
        True, "--parallel/--no-parallel", help="Enable parallel processing"
    ),
    resource_monitoring: bool = typer.Option(
        True, "--monitoring/--no-monitoring", help="Enable resource monitoring"
    ),
    max_workers: int = typer.Option(8, "--max-workers", help="Maximum parallel workers"),
    compression_algorithm: str = typer.Option(
        "lz4", "--algorithm", help="Compression algorithm (lz4, gzip, zlib)"
    ),
):
    """Enable performance optimizations for backup operations."""
    try:
        # Create performance optimizer with specified settings
        PerformanceOptimizer(
            enable_compression=compression,
            enable_deduplication=deduplication,
            enable_parallel_processing=parallel_processing,
            enable_resource_monitoring=resource_monitoring,
            max_workers=max_workers,
            compression_algorithm=compression_algorithm,
        )

        # Save configuration (this would typically go to a config file)
        config = Config()
        config.set(
            "backup.performance",
            {
                "compression_enabled": compression,
                "deduplication_enabled": deduplication,
                "parallel_processing_enabled": parallel_processing,
                "resource_monitoring_enabled": resource_monitoring,
                "max_workers": max_workers,
                "compression_algorithm": compression_algorithm,
            },
        )

        # Display configuration
        table = Table(title="Performance Optimization Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Compression", "✅ Enabled" if compression else "❌ Disabled")
        table.add_row("Deduplication", "✅ Enabled" if deduplication else "❌ Disabled")
        table.add_row("Parallel Processing", "✅ Enabled" if parallel_processing else "❌ Disabled")
        table.add_row("Resource Monitoring", "✅ Enabled" if resource_monitoring else "❌ Disabled")
        table.add_row("Max Workers", str(max_workers))
        table.add_row("Compression Algorithm", compression_algorithm)

        console.print(table)
        console.print("\n✅ Performance optimizations configured successfully!")

    except Exception as e:
        console.print(f"[red]❌ Failed to configure performance optimizations: {e}[/red]")
        raise typer.Exit(1)


@app.command("disable")
def disable_optimizations():
    """Disable all performance optimizations."""
    try:
        # Create performance optimizer with all optimizations disabled
        PerformanceOptimizer(
            enable_compression=False,
            enable_deduplication=False,
            enable_parallel_processing=False,
            enable_resource_monitoring=False,
        )

        # Save configuration
        config = Config()
        config.set(
            "backup.performance",
            {
                "compression_enabled": False,
                "deduplication_enabled": False,
                "parallel_processing_enabled": False,
                "resource_monitoring_enabled": False,
                "max_workers": 1,
                "compression_algorithm": "none",
            },
        )

        console.print("✅ All performance optimizations disabled successfully!")
        console.print("Backup operations will run without optimization.")

    except Exception as e:
        console.print(f"[red]❌ Failed to disable performance optimizations: {e}[/red]")
        raise typer.Exit(1)


@app.command("status")
def show_optimization_status():
    """Show current performance optimization status."""
    try:
        config = Config()
        perf_config = config.get("backup.performance", {})

        if not perf_config:
            console.print("[yellow]⚠️  No performance configuration found. Using defaults.[/yellow]")
            perf_config = {
                "compression_enabled": True,
                "deduplication_enabled": True,
                "parallel_processing_enabled": True,
                "resource_monitoring_enabled": True,
                "max_workers": 8,
                "compression_algorithm": "lz4",
            }

        # Create optimizer to get current stats
        optimizer = PerformanceOptimizer(
            enable_compression=perf_config.get("compression_enabled", True),
            enable_deduplication=perf_config.get("deduplication_enabled", True),
            enable_parallel_processing=perf_config.get("parallel_processing_enabled", True),
            enable_resource_monitoring=perf_config.get("resource_monitoring_enabled", True),
            max_workers=perf_config.get("max_workers", 8),
            compression_algorithm=perf_config.get("compression_algorithm", "lz4"),
        )

        # Display configuration
        table = Table(title="Performance Optimization Status")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        table.add_column("Status", style="yellow")

        table.add_row(
            "Compression",
            perf_config.get("compression_algorithm", "lz4"),
            "✅ Enabled" if perf_config.get("compression_enabled", True) else "❌ Disabled",
        )
        table.add_row(
            "Deduplication",
            "Block-based (4KB)",
            "✅ Enabled" if perf_config.get("deduplication_enabled", True) else "❌ Disabled",
        )
        table.add_row(
            "Parallel Processing",
            f"{perf_config.get('max_workers', 8)} workers",
            "✅ Enabled" if perf_config.get("parallel_processing_enabled", True) else "❌ Disabled",
        )
        table.add_row(
            "Resource Monitoring",
            "Real-time",
            "✅ Enabled" if perf_config.get("resource_monitoring_enabled", True) else "❌ Disabled",
        )

        console.print(table)

        # Show optimization statistics if available
        stats = optimizer.get_optimization_stats()
        if stats.get("compression") or stats.get("deduplication"):
            console.print("\n[bold]Optimization Statistics:[/bold]")

            if stats.get("compression"):
                comp_stats = stats["compression"]
                console.print(f"  Compression: {comp_stats.get('total_operations', 0)} operations")

            if stats.get("deduplication"):
                dedup_stats = stats["deduplication"]
                console.print(
                    f"  Deduplication: {dedup_stats.get('total_operations', 0)} operations"
                )

    except Exception as e:
        console.print(f"[red]❌ Failed to get optimization status: {e}[/red]")
        raise typer.Exit(1)


@app.command("stats")
def show_performance_stats():
    """Show detailed performance statistics."""
    try:
        # Create optimizer to get statistics
        optimizer = PerformanceOptimizer(enable_resource_monitoring=True)

        # Get resource usage
        resource_usage = optimizer.get_resource_usage()

        if resource_usage:
            console.print("[bold]Resource Usage Statistics:[/bold]")

            if resource_usage.get("current"):
                current = resource_usage["current"]
                table = Table(title="Current Resource Usage")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")

                table.add_row("CPU Usage", f"{current.get('cpu_percent', 0):.1f}%")
                table.add_row("Memory Usage", f"{current.get('memory_rss_mb', 0):.1f} MB")
                table.add_row("Thread Count", str(current.get("thread_count", 0)))
                table.add_row("File Descriptors", str(current.get("file_descriptors", 0)))

                console.print(table)

            if resource_usage.get("peak"):
                peak = resource_usage["peak"]
                table = Table(title="Peak Resource Usage")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")

                table.add_row("Peak CPU", f"{peak.get('peak_cpu_percent', 0):.1f}%")
                table.add_row("Peak Memory", f"{peak.get('peak_memory_rss_mb', 0):.1f} MB")
                table.add_row("Peak Threads", str(peak.get("peak_thread_count", 0)))
                table.add_row("Peak File Descriptors", str(peak.get("peak_file_descriptors", 0)))

                console.print(table)
        else:
            console.print("[yellow]⚠️  No resource monitoring data available.[/yellow]")

        # Get optimization statistics
        stats = optimizer.get_optimization_stats()
        if stats.get("compression") or stats.get("deduplication"):
            console.print("\n[bold]Optimization Statistics:[/bold]")

            if stats.get("compression"):
                comp_stats = stats["compression"]
                for algo, algo_stats in comp_stats.items():
                    if isinstance(algo_stats, dict):
                        console.print(f"\n[cyan]Compression Algorithm: {algo.upper()}[/cyan]")
                        table = Table()
                        table.add_column("Metric", style="cyan")
                        table.add_column("Value", style="green")

                        table.add_row(
                            "Total Operations", str(algo_stats.get("total_operations", 0))
                        )
                        table.add_row(
                            "Total Original Size",
                            f"{algo_stats.get('total_original_size', 0) / 1024 / 1024:.2f} MB",
                        )
                        table.add_row(
                            "Total Compressed Size",
                            f"{algo_stats.get('total_compressed_size', 0) / 1024 / 1024:.2f} MB",
                        )
                        table.add_row(
                            "Average Ratio", f"{algo_stats.get('average_ratio', 1.0):.2f}x"
                        )
                        table.add_row("Total Time", f"{algo_stats.get('total_time', 0):.2f}s")

                        console.print(table)

            if stats.get("deduplication"):
                dedup_stats = stats["deduplication"]
                console.print("\n[cyan]Deduplication Statistics[/cyan]")
                table = Table()
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")

                table.add_row("Total Operations", str(dedup_stats.get("total_operations", 0)))
                table.add_row(
                    "Total Blocks Processed", str(dedup_stats.get("total_blocks_processed", 0))
                )
                table.add_row(
                    "Duplicate Blocks Found", str(dedup_stats.get("duplicate_blocks_found", 0))
                )
                table.add_row("Cache Hits", str(dedup_stats.get("cache_hits", 0)))
                table.add_row("Cache Size", str(dedup_stats.get("cache_size", 0)))

                console.print(table)

        optimizer.shutdown()

    except Exception as e:
        console.print(f"[red]❌ Failed to get performance statistics: {e}[/red]")
        raise typer.Exit(1)


@app.command("benchmark")
def run_performance_benchmark(
    data_size: str = typer.Option("medium", "--size", help="Data size: small, medium, large"),
    iterations: int = typer.Option(3, "--iterations", help="Number of benchmark iterations"),
):
    """Run performance benchmarks to test optimization effectiveness."""
    import asyncio

    async def _run_benchmark():
        try:
            console.print(
                f"[bold]Running Performance Benchmark ({data_size} data, {iterations} iterations)[/bold]"
            )

            # Create sample data based on size
            if data_size == "small":
                user_count = 100
                group_count = 10
                ps_count = 5
            elif data_size == "medium":
                user_count = 1000
                group_count = 100
                ps_count = 50
            else:  # large
                user_count = 5000
                group_count = 500
                ps_count = 200

            # Create sample backup data
            from datetime import datetime

            from ...backup_restore.models import (
                AssignmentData,
                BackupData,
                BackupMetadata,
                BackupType,
                EncryptionMetadata,
                GroupData,
                PermissionSetData,
                RetentionPolicy,
                UserData,
            )

            metadata = BackupMetadata(
                backup_id="benchmark-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/benchmark",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            )

            users = [
                UserData(
                    user_id=f"user-{i}",
                    user_name=f"user{i}",
                    display_name=f"User {i}",
                    email=f"user{i}@example.com",
                    given_name=f"Given{i}",
                    family_name=f"Family{i}",
                    active=True,
                )
                for i in range(user_count)
            ]

            groups = [
                GroupData(
                    group_id=f"group-{i}",
                    display_name=f"Group {i}",
                    description=f"Test group {i}",
                    members=[f"user-{j}" for j in range(i * 10, min((i + 1) * 10, user_count))],
                )
                for i in range(group_count)
            ]

            permission_sets = [
                PermissionSetData(
                    permission_set_arn=f"arn:aws:sso:::permissionSet/ps-{i}",
                    name=f"PermissionSet{i}",
                    description=f"Test permission set {i}",
                    session_duration=3600,
                    relay_state="",
                    inline_policy="{}",
                    managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                    customer_managed_policies=[],
                    permissions_boundary="",
                )
                for i in range(ps_count)
            ]

            assignments = [
                AssignmentData(
                    account_id="123456789012",
                    permission_set_arn=f"arn:aws:sso:::permissionSet/ps-{i % ps_count}",
                    principal_type="USER",
                    principal_id=f"user-{i}",
                )
                for i in range(user_count)
            ]

            backup_data = BackupData(
                metadata=metadata,
                users=users,
                groups=groups,
                permission_sets=permission_sets,
                assignments=assignments,
            )

            # Test different optimization configurations
            configs = [
                {
                    "name": "No Optimization",
                    "compression": False,
                    "deduplication": False,
                    "parallel": False,
                },
                {
                    "name": "Compression Only",
                    "compression": True,
                    "deduplication": False,
                    "parallel": False,
                },
                {
                    "name": "Deduplication Only",
                    "compression": False,
                    "deduplication": True,
                    "parallel": False,
                },
                {
                    "name": "Parallel Only",
                    "compression": False,
                    "deduplication": False,
                    "parallel": True,
                },
                {
                    "name": "Full Optimization",
                    "compression": True,
                    "deduplication": True,
                    "parallel": True,
                },
            ]

            results = []

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                for config in configs:
                    task = progress.add_task(f"Testing {config['name']}...", total=iterations)

                    config_times = []
                    config_sizes = []

                    for i in range(iterations):
                        optimizer = PerformanceOptimizer(
                            enable_compression=config["compression"],
                            enable_deduplication=config["deduplication"],
                            enable_parallel_processing=config["parallel"],
                            enable_resource_monitoring=False,  # Disable for benchmark
                            max_workers=8,
                        )

                        import time

                        start_time = time.time()

                        try:
                            optimized_data, metadata = await optimizer.optimize_backup_data(
                                backup_data
                            )
                            optimization_time = time.time() - start_time

                            config_times.append(optimization_time)
                            config_sizes.append(len(optimized_data))

                        except Exception as e:
                            console.print(f"[red]Benchmark failed for {config['name']}: {e}[/red]")
                            config_times.append(0)
                            config_sizes.append(0)

                        finally:
                            optimizer.shutdown()

                        progress.advance(task)

                    # Calculate averages
                    avg_time = sum(config_times) / len(config_times) if config_times else 0
                    avg_size = sum(config_sizes) / len(config_sizes) if config_sizes else 0

                    results.append(
                        {
                            "name": config["name"],
                            "avg_time": avg_time,
                            "avg_size": avg_size,
                            "compression_ratio": (
                                len(backup_data.to_dict()) / avg_size if avg_size > 0 else 1.0
                            ),
                        }
                    )

            # Display benchmark results
            console.print("\n[bold]Benchmark Results:[/bold]")

            table = Table(title=f"Performance Benchmark ({data_size} data)")
            table.add_column("Configuration", style="cyan")
            table.add_column("Avg Time (s)", style="green")
            table.add_column("Avg Size (bytes)", style="yellow")
            table.add_column("Compression Ratio", style="blue")

            for result in results:
                table.add_row(
                    result["name"],
                    f"{result['avg_time']:.3f}",
                    f"{result['avg_size']:,}",
                    f"{result['compression_ratio']:.2f}x",
                )

            console.print(table)

            # Find best configurations
            fastest = min(results, key=lambda x: x["avg_time"])
            smallest = min(results, key=lambda x: x["avg_size"])

            console.print(f"\n🏆 Fastest: {fastest['name']} ({fastest['avg_time']:.3f}s)")
            console.print(
                f"🏆 Best Compression: {smallest['name']} ({smallest['compression_ratio']:.2f}x)"
            )

        except Exception as e:
            console.print(f"[red]❌ Benchmark failed: {e}[/red]")
            raise typer.Exit(1)

    # Run the async benchmark function
    asyncio.run(_run_benchmark())


@app.command("clear")
def clear_optimization_caches():
    """Clear all optimization caches and statistics."""
    try:
        optimizer = PerformanceOptimizer()
        optimizer.clear_caches()

        console.print("✅ Optimization caches cleared successfully!")
        console.print("All performance statistics have been reset.")

    except Exception as e:
        console.print(f"[red]❌ Failed to clear caches: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
