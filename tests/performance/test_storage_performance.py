"""Performance tests for optimized storage operations."""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from src.awsideman.rollback.models import (
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
)
from src.awsideman.rollback.optimized_storage import (
    CompressedJSONStorage,
    MemoryOptimizedOperationStore,
)
from src.awsideman.rollback.storage_monitor import StorageAlert, StorageMonitor


class TestCompressedJSONStorage:
    """Test compressed JSON storage functionality."""

    def test_compression_basic(self, tmp_path):
        """Test basic compression functionality."""
        storage_file = tmp_path / "test.json.gz"
        storage = CompressedJSONStorage(storage_file, compression_level=6)

        # Test data
        test_data = {
            "operations": [
                {
                    "id": f"op-{i}",
                    "data": "x" * 1000,  # 1KB of data per operation
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                for i in range(100)
            ]
        }

        # Write compressed data
        start_time = time.time()
        storage.write_data(test_data)
        write_time = time.time() - start_time

        # Read compressed data
        start_time = time.time()
        read_data = storage.read_data()
        read_time = time.time() - start_time

        # Verify data integrity
        assert read_data == test_data
        assert len(read_data["operations"]) == 100

        # Check compression ratio
        compression_ratio = storage.get_compression_ratio()
        assert 0 < compression_ratio < 1.0  # Should be compressed

        # Performance should be reasonable
        assert write_time < 1.0  # Should write in under 1 second
        assert read_time < 1.0  # Should read in under 1 second

        print(f"Compression ratio: {compression_ratio:.3f}")
        print(f"Write time: {write_time:.3f}s, Read time: {read_time:.3f}s")

    def test_compression_vs_uncompressed_size(self, tmp_path):
        """Test compression effectiveness with different data sizes."""
        storage_file = tmp_path / "test.json.gz"
        storage = CompressedJSONStorage(storage_file, compression_level=9)  # Max compression

        # Create data with varying compressibility
        test_cases = [
            ("highly_compressible", {"data": "A" * 10000}),  # Very repetitive
            ("moderately_compressible", {"data": "Hello World! " * 1000}),  # Some repetition
            ("low_compressible", {"data": str(time.time()) * 1000}),  # More random
        ]

        for case_name, data in test_cases:
            storage.write_data(data)
            compression_ratio = storage.get_compression_ratio()
            file_size = storage.get_file_size()

            print(f"{case_name}: ratio={compression_ratio:.3f}, size={file_size} bytes")

            # Highly compressible data should compress well
            if case_name == "highly_compressible":
                assert compression_ratio < 0.1  # Should compress to less than 10%

    def test_append_performance(self, tmp_path):
        """Test append operation performance."""
        storage_file = tmp_path / "test.json.gz"
        storage = CompressedJSONStorage(storage_file, compression_level=6)

        # Initialize with some data
        initial_data = {"operations": []}
        storage.write_data(initial_data)

        # Test appending operations
        batch_size = 100
        num_batches = 10

        total_append_time = 0
        for batch in range(num_batches):
            new_operations = [
                {
                    "id": f"op-{batch}-{i}",
                    "data": f"operation data for batch {batch} item {i}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                for i in range(batch_size)
            ]

            start_time = time.time()
            storage.append_data("operations", new_operations)
            append_time = time.time() - start_time
            total_append_time += append_time

        # Verify final data
        final_data = storage.read_data()
        assert len(final_data["operations"]) == batch_size * num_batches

        avg_append_time = total_append_time / num_batches
        print(f"Average append time per batch ({batch_size} items): {avg_append_time:.3f}s")

        # Should be reasonably fast
        assert avg_append_time < 0.5  # Less than 500ms per batch


class TestMemoryOptimizedOperationStore:
    """Test memory-optimized operation store."""

    @pytest.fixture
    def sample_operations(self) -> List[OperationRecord]:
        """Create sample operations for testing."""
        operations = []
        for i in range(1000):  # 1000 operations
            operation = OperationRecord.create(
                operation_type=OperationType.ASSIGN if i % 2 == 0 else OperationType.REVOKE,
                principal_id=f"user-{i % 100}",  # 100 unique users
                principal_type=PrincipalType.USER,
                principal_name=f"user{i % 100}@example.com",
                permission_set_arn=f"arn:aws:sso:::permissionSet/ssoins-123/ps-{i % 10}",  # 10 permission sets
                permission_set_name=f"PermissionSet{i % 10}",
                account_ids=[f"{(i % 50):012d}"],  # 50 accounts
                account_names=[f"Account{i % 50}"],
                results=[OperationResult(account_id=f"{(i % 50):012d}", success=True)],
            )
            operations.append(operation)
        return operations

    def test_store_performance_compressed(self, tmp_path, sample_operations):
        """Test storage performance with compression."""
        store = MemoryOptimizedOperationStore(
            storage_directory=str(tmp_path),
            compression_enabled=True,
            compression_level=6,
            memory_limit_mb=50,
        )

        # Measure storage time
        start_time = time.time()
        for operation in sample_operations:
            store.store_operation(operation)
        storage_time = time.time() - start_time

        # Measure retrieval time
        start_time = time.time()
        retrieved_operations = store.get_operations(limit=1000)
        retrieval_time = time.time() - start_time

        # Verify data integrity
        assert len(retrieved_operations) == len(sample_operations)

        # Check performance
        avg_storage_time = storage_time / len(sample_operations)
        print(f"Average storage time per operation: {avg_storage_time * 1000:.2f}ms")
        print(
            f"Total retrieval time for {len(sample_operations)} operations: {retrieval_time:.3f}s"
        )

        # Performance should be reasonable
        assert avg_storage_time < 0.01  # Less than 10ms per operation
        assert retrieval_time < 2.0  # Less than 2 seconds for 1000 operations

        # Check storage stats
        stats = store.get_storage_stats()
        assert stats["total_operations"] == len(sample_operations)
        assert stats["compression_enabled"] is True
        assert stats["operations_compression_ratio"] < 1.0

        print(f"Compression ratio: {stats['operations_compression_ratio']:.3f}")
        print(f"Storage size: {stats['operations_file_size']} bytes")

    def test_store_performance_uncompressed(self, tmp_path, sample_operations):
        """Test storage performance without compression."""
        store = MemoryOptimizedOperationStore(
            storage_directory=str(tmp_path),
            compression_enabled=False,
            memory_limit_mb=50,
        )

        # Measure storage time
        start_time = time.time()
        for operation in sample_operations:
            store.store_operation(operation)
        storage_time = time.time() - start_time

        # Measure retrieval time
        start_time = time.time()
        retrieved_operations = store.get_operations(limit=1000)
        retrieval_time = time.time() - start_time

        # Verify data integrity
        assert len(retrieved_operations) == len(sample_operations)

        # Check performance
        avg_storage_time = storage_time / len(sample_operations)
        print(f"Uncompressed - Average storage time per operation: {avg_storage_time * 1000:.2f}ms")
        print(f"Uncompressed - Total retrieval time: {retrieval_time:.3f}s")

        # Uncompressed should be faster for storage but use more space
        assert avg_storage_time < 0.005  # Should be faster than compressed
        assert retrieval_time < 1.0  # Should be faster retrieval

    def test_index_performance(self, tmp_path, sample_operations):
        """Test index-based query performance."""
        store = MemoryOptimizedOperationStore(
            storage_directory=str(tmp_path),
            compression_enabled=True,
        )

        # Store operations
        for operation in sample_operations:
            store.store_operation(operation)

        # Test various query patterns
        query_tests = [
            ("by_operation_type", {"operation_type": "assign"}),
            ("by_principal", {"principal": "user1@example.com"}),
            ("by_permission_set", {"permission_set": "PermissionSet1"}),
            ("by_days", {"days": 1}),
            ("combined", {"operation_type": "assign", "principal": "user1"}),
        ]

        for test_name, filters in query_tests:
            start_time = time.time()
            results = store.get_operations(**filters)
            query_time = time.time() - start_time

            print(f"{test_name}: {len(results)} results in {query_time * 1000:.2f}ms")

            # Index-based queries should be fast
            assert query_time < 0.1  # Less than 100ms
            assert len(results) >= 0  # Should return some results

    def test_cleanup_performance(self, tmp_path, sample_operations):
        """Test cleanup operation performance."""
        store = MemoryOptimizedOperationStore(
            storage_directory=str(tmp_path),
            compression_enabled=True,
            memory_limit_mb=10,  # Low memory limit to test batching
            batch_size=100,
        )

        # Store operations with different timestamps
        for i, operation in enumerate(sample_operations):
            # Make some operations old
            if i < 500:
                operation.timestamp = datetime.now(timezone.utc) - timedelta(days=100)
            store.store_operation(operation)

        # Measure cleanup performance
        start_time = time.time()
        removed_count = store.cleanup_old_operations(days=90)
        cleanup_time = time.time() - start_time

        print(f"Cleanup removed {removed_count} operations in {cleanup_time:.3f}s")

        # Verify cleanup worked
        assert removed_count == 500
        remaining_operations = store.get_operations()
        assert len(remaining_operations) == 500

        # Cleanup should be reasonably fast even with memory limits
        assert cleanup_time < 5.0  # Less than 5 seconds

    def test_memory_usage_optimization(self, tmp_path):
        """Test memory usage optimization with large datasets."""
        store = MemoryOptimizedOperationStore(
            storage_directory=str(tmp_path),
            compression_enabled=True,
            memory_limit_mb=5,  # Very low memory limit
            batch_size=50,
        )

        # Create a large number of operations
        large_operation_count = 5000

        # Monitor memory usage during storage
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        for i in range(large_operation_count):
            operation = OperationRecord.create(
                operation_type=OperationType.ASSIGN,
                principal_id=f"user-{i}",
                principal_type=PrincipalType.USER,
                principal_name=f"user{i}@example.com",
                permission_set_arn=f"arn:aws:sso:::permissionSet/ssoins-123/ps-{i % 10}",
                permission_set_name=f"PermissionSet{i % 10}",
                account_ids=[f"{i:012d}"],
                account_names=[f"Account{i}"],
                results=[OperationResult(account_id=f"{i:012d}", success=True)],
            )
            store.store_operation(operation)

            # Check memory usage periodically
            if i % 1000 == 0:
                current_memory = process.memory_info().rss
                memory_increase = (current_memory - initial_memory) / 1024 / 1024  # MB
                print(f"After {i} operations: Memory increase = {memory_increase:.1f}MB")

        final_memory = process.memory_info().rss
        total_memory_increase = (final_memory - initial_memory) / 1024 / 1024  # MB

        print(
            f"Total memory increase: {total_memory_increase:.1f}MB for {large_operation_count} operations"
        )

        # Memory usage should be reasonable
        assert total_memory_increase < 100  # Less than 100MB increase

        # Verify all operations were stored
        stats = store.get_storage_stats()
        assert stats["total_operations"] == large_operation_count


class TestStorageMonitor:
    """Test storage monitoring functionality."""

    def test_storage_health_check(self, tmp_path):
        """Test storage health checking."""
        monitor = StorageMonitor(
            storage_directory=str(tmp_path),
            monitoring_interval=1,
        )

        # Set low thresholds to trigger alerts
        monitor.set_thresholds(
            max_file_size_mb=1,
            max_total_size_mb=2,
            max_operations=100,
        )

        # Create some test files to trigger alerts
        large_file = tmp_path / "operations.json"
        with open(large_file, "w") as f:
            # Write 2MB of data
            json.dump({"operations": ["x" * 1000] * 2000}, f)

        # Run health check
        alerts = monitor.check_storage_health()

        # Should generate alerts for large file
        assert len(alerts) > 0
        alert_types = [alert.alert_type for alert in alerts]
        assert "large_operations_file" in alert_types

    def test_monitoring_loop(self, tmp_path):
        """Test background monitoring loop."""
        alerts_received = []

        def test_alert_handler(alert: StorageAlert):
            alerts_received.append(alert)

        monitor = StorageMonitor(
            storage_directory=str(tmp_path),
            alert_handlers=[test_alert_handler],
            monitoring_interval=0.1,  # Very short interval for testing
        )

        # Set thresholds to trigger alerts
        monitor.set_thresholds(max_file_size_mb=1)

        # Create a large file
        large_file = tmp_path / "operations.json"
        with open(large_file, "w") as f:
            json.dump({"operations": ["x" * 1000] * 1500}, f)

        # Start monitoring
        monitor.start_monitoring()

        # Wait for monitoring to run
        time.sleep(0.5)

        # Stop monitoring
        monitor.stop_monitoring()

        # Should have received alerts
        assert len(alerts_received) > 0
        assert any(alert.alert_type == "large_operations_file" for alert in alerts_received)

    def test_storage_summary(self, tmp_path):
        """Test storage summary generation."""
        monitor = StorageMonitor(storage_directory=str(tmp_path))

        # Create some test files
        operations_file = tmp_path / "operations.json"
        with open(operations_file, "w") as f:
            json.dump({"operations": [{"id": i} for i in range(100)]}, f)

        index_file = tmp_path / "operation_index.json"
        with open(index_file, "w") as f:
            json.dump({f"op-{i}": {"timestamp": datetime.now().isoformat()} for i in range(100)}, f)

        # Get summary
        summary = monitor.get_storage_summary()

        assert "current_metrics" in summary
        assert "monitoring_active" in summary
        assert "thresholds" in summary
        assert summary["current_metrics"]["total_operations"] == 100

    def test_alert_persistence(self, tmp_path):
        """Test alert storage and retrieval."""
        monitor = StorageMonitor(storage_directory=str(tmp_path))

        # Generate some alerts
        test_alerts = [
            StorageAlert("test_alert_1", "warning", "Test message 1", datetime.now(timezone.utc)),
            StorageAlert("test_alert_2", "error", "Test message 2", datetime.now(timezone.utc)),
        ]

        for alert in test_alerts:
            monitor._emit_alert_object(alert)

        # Retrieve recent alerts
        recent_alerts = monitor.get_recent_alerts(hours=1)

        assert len(recent_alerts) == 2
        assert recent_alerts[0].alert_type in ["test_alert_1", "test_alert_2"]
        assert recent_alerts[1].alert_type in ["test_alert_1", "test_alert_2"]


class TestStorageOptimizationIntegration:
    """Integration tests for storage optimization features."""

    def test_full_optimization_workflow(self, tmp_path):
        """Test complete storage optimization workflow."""
        # Create store with optimization features
        store = MemoryOptimizedOperationStore(
            storage_directory=str(tmp_path),
            compression_enabled=True,
            memory_limit_mb=20,
        )

        # Create monitor
        monitor = StorageMonitor(storage_directory=str(tmp_path))

        # Generate operations over time
        operations = []
        for i in range(2000):
            operation = OperationRecord.create(
                operation_type=OperationType.ASSIGN if i % 2 == 0 else OperationType.REVOKE,
                principal_id=f"user-{i % 100}",
                principal_type=PrincipalType.USER,
                principal_name=f"user{i % 100}@example.com",
                permission_set_arn=f"arn:aws:sso:::permissionSet/ssoins-123/ps-{i % 10}",
                permission_set_name=f"PermissionSet{i % 10}",
                account_ids=[f"{(i % 50):012d}"],
                account_names=[f"Account{i % 50}"],
                results=[OperationResult(account_id=f"{(i % 50):012d}", success=True)],
            )

            # Make some operations old
            if i < 1000:
                operation.timestamp = datetime.now(timezone.utc) - timedelta(days=100)

            operations.append(operation)
            store.store_operation(operation)

        # Check initial state
        initial_stats = store.get_storage_stats()
        print(f"Initial operations: {initial_stats['total_operations']}")
        print(f"Initial file size: {initial_stats['operations_file_size']} bytes")

        # Run health check
        alerts = monitor.check_storage_health()
        print(f"Health check found {len(alerts)} alerts")

        # Perform optimization
        optimization_results = store.optimize_storage()
        print(f"Optimization results: {optimization_results}")

        # Clean up old operations
        removed_count = store.cleanup_old_operations(days=90)
        print(f"Cleaned up {removed_count} old operations")

        # Check final state
        final_stats = store.get_storage_stats()
        print(f"Final operations: {final_stats['total_operations']}")
        print(f"Final file size: {final_stats['operations_file_size']} bytes")

        # Verify optimization worked
        assert final_stats["total_operations"] == 1000  # Only recent operations
        assert removed_count == 1000  # Old operations removed
        assert final_stats["operations_file_size"] < initial_stats["operations_file_size"]

        # Verify data integrity
        remaining_operations = store.get_operations()
        assert len(remaining_operations) == 1000

        # All remaining operations should be recent
        for op in remaining_operations:
            assert op.timestamp > datetime.now(timezone.utc) - timedelta(days=90)
