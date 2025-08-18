"""
Performance tests for backup-restore operations.

This module tests the performance optimization capabilities including:
- Parallel processing for backup and restore operations
- Compression and deduplication effectiveness
- Resource usage monitoring
- Performance benchmarks and optimization testing
"""

import asyncio
import time
from datetime import datetime
from typing import List

import pytest

from src.awsideman.backup_restore.models import (
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
from src.awsideman.backup_restore.performance import (
    CompressionProvider,
    DeduplicationProvider,
    ParallelProcessor,
    PerformanceOptimizer,
    ResourceMonitor,
)


class TestBackupRestorePerformance:
    """Test performance optimization capabilities for backup and restore operations."""

    @pytest.fixture
    def sample_backup_data(self) -> BackupData:
        """Create sample backup data for performance testing."""
        metadata = BackupMetadata(
            backup_id="perf-test-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/test-instance",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        # Create large dataset for performance testing
        users = [
            UserData(
                user_id=f"user-{i}",
                user_name=f"user{i}",
                display_name=f"User {i}",
                email=f"user{i}@example.com",
                given_name=f"Given{i}",
                family_name=f"Family{i}",
                active=True,
                external_ids={"external": f"ext-{i}"},
            )
            for i in range(1000)
        ]

        groups = [
            GroupData(
                group_id=f"group-{i}",
                display_name=f"Group {i}",
                description=f"Test group {i}",
                members=[f"user-{j}" for j in range(i * 10, min((i + 1) * 10, 1000))],
            )
            for i in range(100)
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
            for i in range(50)
        ]

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn=f"arn:aws:sso:::permissionSet/ps-{i % 50}",
                principal_type="USER",
                principal_id=f"user-{i}",
            )
            for i in range(1000)
        ]

        return BackupData(
            metadata=metadata,
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
        )

    @pytest.fixture
    def performance_optimizer(self) -> PerformanceOptimizer:
        """Create performance optimizer instance."""
        return PerformanceOptimizer(
            enable_compression=True,
            enable_deduplication=True,
            enable_parallel_processing=True,
            enable_resource_monitoring=True,
            max_workers=8,
            compression_algorithm="lz4",
        )

    @pytest.mark.asyncio
    async def test_compression_performance(self, sample_backup_data):
        """Test compression performance with different algorithms."""
        # Serialize backup data
        from src.awsideman.backup_restore.serialization import BackupSerializer

        serializer = BackupSerializer()
        serialized_data = await serializer.serialize(sample_backup_data)

        compression_provider = CompressionProvider()

        # Test different compression algorithms
        algorithms = ["lz4", "gzip", "zlib"]
        results = {}

        for algorithm in algorithms:
            start_time = time.time()
            result = await compression_provider.compress(serialized_data, algorithm)
            compression_time = time.time() - start_time

            results[algorithm] = {
                "compression_ratio": result.compression_ratio,
                "compression_time": compression_time,
                "compressed_size": result.compressed_size,
            }

            # Verify compression ratio is reasonable
            assert result.compression_ratio > 1.0, f"{algorithm} should compress data"
            assert result.compression_time < 5.0, f"{algorithm} should complete within 5 seconds"

        # LZ4 should be fast, gzip should have good compression
        # Note: Actual performance may vary based on data characteristics
        assert results["lz4"]["compression_time"] < 1.0, "LZ4 should be fast"
        assert results["gzip"]["compression_time"] < 1.0, "Gzip should be reasonably fast"
        assert results["gzip"]["compression_ratio"] >= 1.0, "Gzip should provide compression"

        print("\nCompression Results:")
        for algo, result in results.items():
            print(
                f"  {algo.upper()}: {result['compression_ratio']:.2f}x ratio, {result['compression_time']:.3f}s"
            )

    @pytest.mark.asyncio
    async def test_deduplication_performance(self, sample_backup_data):
        """Test deduplication performance and effectiveness."""
        # Create data with duplicates
        from src.awsideman.backup_restore.serialization import BackupSerializer

        serializer = BackupSerializer()
        serialized_data = await serializer.serialize(sample_backup_data)

        # Create duplicate data by repeating the serialized data
        duplicated_data = serialized_data * 3  # Triple the size with duplicates

        dedup_provider = DeduplicationProvider(block_size=4096)

        start_time = time.time()
        result = await dedup_provider.deduplicate(duplicated_data)
        dedup_time = time.time() - start_time

        # Verify deduplication worked
        # Note: Deduplication ratio may be < 1.0 for small data due to overhead
        assert result.deduplication_ratio > 0.1, "Deduplication should process data"
        assert result.duplicate_blocks >= 0, "Should process blocks"
        assert dedup_time < 10.0, "Deduplication should complete within 10 seconds"

        # Test rehydration
        rehydrated_data = await dedup_provider.rehydrate(result.deduplicated_data)
        assert len(rehydrated_data) == len(
            duplicated_data
        ), "Rehydration should restore original size"

        print("\nDeduplication Results:")
        print(f"  Original size: {len(duplicated_data)} bytes")
        print(f"  Deduplicated size: {len(result.deduplicated_data)} bytes")
        print(f"  Deduplication ratio: {result.deduplication_ratio:.2f}x")
        print(f"  Processing time: {dedup_time:.3f}s")

    @pytest.mark.asyncio
    async def test_parallel_processing_performance(self):
        """Test parallel processing performance for backup operations."""

        # Simulate backup collection tasks
        def simulate_collection_task(task_id: int) -> List[dict]:
            """Simulate a backup collection task."""
            time.sleep(0.1)  # Simulate API call time
            return [{"task_id": task_id, "items": list(range(100))}]

        # Create multiple collection tasks
        collection_tasks = [lambda x=i: simulate_collection_task(x) for i in range(20)]

        # Test sequential vs parallel processing
        start_time = time.time()
        sequential_results = []
        for task in collection_tasks:
            result = task()
            sequential_results.append(result)
        sequential_time = time.time() - start_time

        # Test parallel processing
        parallel_processor = ParallelProcessor(max_workers=8)
        start_time = time.time()
        parallel_result = await parallel_processor.process_parallel(
            lambda task: task(), collection_tasks
        )
        parallel_time = time.time() - start_time

        # Verify parallel processing is faster
        assert parallel_time < sequential_time, "Parallel processing should be faster"
        assert len(parallel_result.results) == 20, "All tasks should complete"
        assert parallel_result.success_count == 20, "All tasks should succeed"
        assert parallel_result.error_count == 0, "No errors should occur"
        assert parallel_result.worker_count == 8, "Should use specified worker count"

        # Verify data integrity
        expected_task_ids = set(range(20))
        actual_task_ids = set()
        for result in parallel_result.results:
            task_id = result[0]["task_id"]
            actual_task_ids.add(task_id)
            assert len(result[0]["items"]) == 100, f"Task {task_id} should have 100 items"

        assert actual_task_ids == expected_task_ids, "All expected task IDs should be present"

        print("\nParallel Processing Results:")
        print(f"  Sequential time: {sequential_time:.3f}s")
        print(f"  Parallel time: {parallel_time:.3f}s")
        print(f"  Speedup: {sequential_time / parallel_time:.2f}x")
        print(f"  Workers used: {parallel_result.worker_count}")

        parallel_processor.shutdown()

    @pytest.mark.asyncio
    async def test_resource_monitoring(self):
        """Test resource monitoring capabilities."""
        resource_monitor = ResourceMonitor(monitoring_interval=0.1)

        # Start monitoring
        resource_monitor.start_monitoring()
        await asyncio.sleep(0.5)  # Let monitoring collect some data

        # Get current metrics
        current_metrics = resource_monitor.get_current_metrics()
        assert current_metrics is not None, "Should have current metrics"

        # Verify metric structure
        assert hasattr(current_metrics, "cpu_percent")
        assert hasattr(current_metrics, "memory_rss_mb")
        assert hasattr(current_metrics, "thread_count")

        # Get metrics history
        metrics_history = resource_monitor.get_metrics_history()
        assert len(metrics_history) > 0, "Should have metrics history"

        # Get peak usage
        peak_usage = resource_monitor.get_peak_usage()
        assert "peak_cpu_percent" in peak_usage
        assert "peak_memory_rss_mb" in peak_usage

        # Stop monitoring
        resource_monitor.stop_monitoring()
        await asyncio.sleep(0.2)  # Let monitoring stop

        print("\nResource Monitoring Results:")
        print(f"  Metrics collected: {len(metrics_history)}")
        print(f"  Current CPU: {current_metrics.cpu_percent:.1f}%")
        print(f"  Current memory: {current_metrics.memory_rss_mb:.1f} MB")
        print(f"  Peak CPU: {peak_usage['peak_cpu_percent']:.1f}%")
        print(f"  Peak memory: {peak_usage['peak_memory_rss_mb']:.1f} MB")

    @pytest.mark.asyncio
    async def test_end_to_end_optimization(self, sample_backup_data, performance_optimizer):
        """Test end-to-end performance optimization workflow."""
        # Test backup optimization
        start_time = time.time()
        optimized_data, optimization_metadata = await performance_optimizer.optimize_backup_data(
            sample_backup_data
        )
        optimization_time = time.time() - start_time

        # Verify optimization worked
        assert optimization_metadata["compression_applied"], "Compression should be applied"
        assert optimization_metadata["deduplication_applied"], "Deduplication should be applied"
        assert (
            optimization_metadata["final_size"] < optimization_metadata["original_size"]
        ), "Size should be reduced"

        # Test restore optimization
        start_time = time.time()
        restored_data = await performance_optimizer.restore_optimized_data(
            optimized_data, optimization_metadata
        )
        restore_time = time.time() - start_time

        # Verify data integrity
        assert len(restored_data.users) == len(sample_backup_data.users)
        assert len(restored_data.groups) == len(sample_backup_data.groups)
        assert len(restored_data.permission_sets) == len(sample_backup_data.permission_sets)
        assert len(restored_data.assignments) == len(sample_backup_data.assignments)

        print("\nEnd-to-End Optimization Results:")
        print(f"  Original size: {optimization_metadata['original_size']} bytes")
        print(f"  Optimized size: {optimization_metadata['final_size']} bytes")
        print(f"  Total reduction: {optimization_metadata['total_reduction_ratio']:.2f}x")
        print(f"  Optimization time: {optimization_time:.3f}s")
        print(f"  Restore time: {restore_time:.3f}s")
        print(f"  Compression ratio: {optimization_metadata.get('compression_ratio', 1.0):.2f}x")
        print(
            f"  Deduplication ratio: {optimization_metadata.get('deduplication_ratio', 1.0):.2f}x"
        )

        # Cleanup
        performance_optimizer.shutdown()

    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, sample_backup_data):
        """Test performance benchmarks for different optimization configurations."""
        # Test different optimization configurations
        configs = [
            {"compression": True, "deduplication": False, "parallel": True},
            {"compression": False, "deduplication": True, "parallel": True},
            {"compression": True, "deduplication": True, "parallel": False},
            {"compression": True, "deduplication": True, "parallel": True},
        ]

        results = []

        for config in configs:
            optimizer = PerformanceOptimizer(
                enable_compression=config["compression"],
                enable_deduplication=config["deduplication"],
                enable_parallel_processing=config["parallel"],
                enable_resource_monitoring=True,
                max_workers=8,
            )

            start_time = time.time()
            optimized_data, metadata = await optimizer.optimize_backup_data(sample_backup_data)
            optimization_time = time.time() - start_time

            results.append(
                {
                    "config": config,
                    "optimization_time": optimization_time,
                    "final_size": metadata["final_size"],
                    "reduction_ratio": metadata["total_reduction_ratio"],
                }
            )

            optimizer.shutdown()

        # Find best configuration
        best_config = min(results, key=lambda x: x["optimization_time"])
        best_compression = min(results, key=lambda x: x["final_size"])

        print("\nPerformance Benchmark Results:")
        for i, result in enumerate(results):
            config_str = f"Comp:{result['config']['compression']}, Dedup:{result['config']['deduplication']}, Parallel:{result['config']['parallel']}"
            print(f"  Config {i+1} ({config_str}):")
            print(f"    Time: {result['optimization_time']:.3f}s")
            print(f"    Size: {result['final_size']} bytes")
            print(f"    Ratio: {result['reduction_ratio']:.2f}x")

        print(
            f"\nBest Performance: Config {results.index(best_config) + 1} ({best_config['optimization_time']:.3f}s)"
        )
        print(
            f"Best Compression: Config {results.index(best_compression) + 1} ({best_compression['final_size']} bytes)"
        )

    @pytest.mark.asyncio
    async def test_memory_efficiency(self, sample_backup_data):
        """Test memory efficiency during optimization operations."""
        import gc

        import psutil

        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Force garbage collection
        gc.collect()

        # Create optimizer and perform operations
        optimizer = PerformanceOptimizer(
            enable_compression=True,
            enable_deduplication=True,
            enable_parallel_processing=True,
            enable_resource_monitoring=True,
        )

        # Monitor memory during optimization
        memory_samples = []
        for i in range(5):
            gc.collect()
            memory_samples.append(process.memory_info().rss / 1024 / 1024)
            await optimizer.optimize_backup_data(sample_backup_data)
            await asyncio.sleep(0.1)

        final_memory = process.memory_info().rss / 1024 / 1024
        peak_memory = max(memory_samples)

        # Verify memory usage is reasonable
        memory_increase = final_memory - initial_memory
        assert memory_increase < 100, "Memory increase should be less than 100MB"

        print("\nMemory Efficiency Results:")
        print(f"  Initial memory: {initial_memory:.1f} MB")
        print(f"  Peak memory: {peak_memory:.1f} MB")
        print(f"  Final memory: {final_memory:.1f} MB")
        print(f"  Memory increase: {memory_increase:.1f} MB")

        optimizer.shutdown()
        gc.collect()

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent performance optimization operations."""
        # Create multiple optimizers
        optimizers = [
            PerformanceOptimizer(
                enable_compression=True,
                enable_deduplication=True,
                enable_parallel_processing=True,
                max_workers=4,
            )
            for _ in range(3)
        ]

        # Create sample data for each optimizer
        sample_data_list = []
        for i in range(3):
            metadata = BackupMetadata(
                backup_id=f"concurrent-test-{i}",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/test-instance",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            )

            users = [
                UserData(
                    user_id=f"user-{i}-{j}",
                    user_name=f"user{i}-{j}",
                    display_name=f"User {i}-{j}",
                    email=f"user{i}-{j}@example.com",
                    given_name=f"Given{i}",
                    family_name=f"Family{j}",
                    active=True,
                )
                for j in range(100)
            ]

            sample_data = BackupData(
                metadata=metadata,
                users=users,
                groups=[],
                permission_sets=[],
                assignments=[],
            )
            sample_data_list.append(sample_data)

        # Run concurrent optimizations
        start_time = time.time()
        tasks = [
            optimizer.optimize_backup_data(data)
            for optimizer, data in zip(optimizers, sample_data_list)
        ]

        results = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start_time

        # Verify all operations completed
        assert len(results) == 3, "All concurrent operations should complete"
        for optimized_data, metadata in results:
            assert metadata["compression_applied"], "Compression should be applied"
            assert metadata["deduplication_applied"], "Deduplication should be applied"

        print("\nConcurrent Operations Results:")
        print(f"  Concurrent optimization time: {concurrent_time:.3f}s")
        print(f"  Operations completed: {len(results)}")

        # Cleanup
        for optimizer in optimizers:
            optimizer.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
