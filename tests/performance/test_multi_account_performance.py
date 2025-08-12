"""Performance tests for multi-account operations scalability.

This module contains performance tests to ensure multi-account operations
can handle large-scale deployments efficiently across 100+ accounts.
"""
import asyncio
import os
import time
from typing import List
from unittest.mock import Mock, patch

import pytest

# Optional psutil import for memory testing
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from rich.console import Console

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.utils.bulk.multi_account_batch import MultiAccountBatchProcessor
from src.awsideman.utils.bulk.multi_account_progress import MultiAccountProgressTracker
from src.awsideman.utils.models import AccountInfo, AccountResult


class TestMultiAccountPerformance:
    """Performance tests for multi-account operations scalability."""

    @pytest.fixture
    def console(self):
        """Create a console for testing."""
        import tempfile

        return Console(file=tempfile.NamedTemporaryFile(mode="w", delete=False))

    def mock_progress_tracking(self, batch_processor):
        """Context manager to mock progress tracking and display methods."""
        return patch.multiple(
            batch_processor, _display_dry_run_summary=Mock(), _display_final_summary=Mock()
        )

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create a fast-responding mock AWS client manager for performance testing."""
        manager = Mock(spec=AWSClientManager)

        # Mock Identity Store client with fast responses
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = {
            "Users": [{"UserId": "user-123", "UserName": "testuser"}]
        }
        identity_store_client.list_groups.return_value = {
            "Groups": [{"GroupId": "group-123", "DisplayName": "testgroup"}]
        }
        manager.get_identity_store_client.return_value = identity_store_client

        # Mock SSO Admin client with fast responses
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ins-123/ps-testpermissionset"]
        }
        sso_admin_client.list_account_assignments.return_value = {"AccountAssignments": []}
        sso_admin_client.create_account_assignment.return_value = {
            "AccountAssignmentCreationStatus": {"Status": "SUCCEEDED", "RequestId": "req-123"}
        }
        sso_admin_client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {"Status": "SUCCEEDED", "RequestId": "req-456"}
        }
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Organizations client with fast responses
        organizations_client = Mock()
        organizations_client.list_accounts.return_value = {
            "Accounts": [
                {
                    "Id": f"12345678901{i:02d}",
                    "Name": f"Account-{i}",
                    "Email": f"account{i}@example.com",
                    "Status": "ACTIVE",
                }
                for i in range(200)  # Support up to 200 accounts for testing
            ]
        }
        organizations_client.list_tags_for_resource.return_value = {
            "Tags": [
                {"Key": "Environment", "Value": "Production"},
                {"Key": "Team", "Value": "Engineering"},
            ]
        }
        manager.get_organizations_client.return_value = organizations_client

        return manager

    def create_test_accounts(self, count: int) -> List[AccountInfo]:
        """Create a list of test accounts for performance testing.

        Args:
            count: Number of accounts to create

        Returns:
            List of AccountInfo objects
        """
        accounts = []
        for i in range(count):
            account = AccountInfo(
                account_id=f"12345678901{i:02d}",
                account_name=f"TestAccount-{i}",
                email=f"account{i}@example.com",
                status="ACTIVE",
                tags={
                    "Environment": "Production" if i % 2 == 0 else "Development",
                    "Team": "Engineering" if i % 3 == 0 else "Operations",
                    "CostCenter": f"CC-{i % 10}",
                },
                ou_path=[f"Root/OU-{i % 5}"],
            )
            accounts.append(account)
        return accounts

    @pytest.mark.performance
    def test_large_account_list_processing_100_accounts(self, mock_aws_client_manager, console):
        """Test processing operations across 100+ accounts for scalability."""
        # Create 100 test accounts
        accounts = self.create_test_accounts(100)

        # Create batch processor with optimal batch size
        batch_processor = MultiAccountBatchProcessor(
            aws_client_manager=mock_aws_client_manager, batch_size=20
        )

        # Mock the resource resolver and display methods
        with patch.object(batch_processor, "_resolve_names") as mock_resolve:
            mock_resolve.return_value = None  # Simulate successful resolution

            with patch.object(batch_processor.progress_tracker, "start_multi_account_progress"):
                with patch.object(batch_processor.progress_tracker, "stop_live_display"):
                    with patch.object(batch_processor, "_display_dry_run_summary"):
                        # Mock the single account operation to be fast
                        with patch.object(
                            batch_processor, "_process_single_account_operation"
                        ) as mock_process:
                            mock_process.return_value = AccountResult(
                                account_id="123456789012",
                                account_name="TestAccount",
                                status="success",
                                processing_time=0.1,
                                error_message="Assignment would be created",  # For dry run display
                            )

                            start_time = time.time()

                            # Run the multi-account operation
                            results = asyncio.run(
                                batch_processor.process_multi_account_operation(
                                    accounts=accounts,
                                    permission_set_name="TestPermissionSet",
                                    principal_name="testuser",
                                    principal_type="USER",
                                    operation="assign",
                                    instance_arn="arn:aws:sso:::instance/ins-123",
                                    dry_run=True,  # Use dry run for performance testing
                                    continue_on_error=True,
                                )
                            )

                            processing_time = time.time() - start_time

        # Verify correctness
        assert results.total_accounts == 100
        assert len(results.successful_accounts) == 100
        assert len(results.failed_accounts) == 0

        # Performance assertions
        max_time = 30.0  # Should process 100 accounts in under 30 seconds
        assert (
            processing_time < max_time
        ), f"Processing 100 accounts took {processing_time:.3f}s, expected < {max_time:.3f}s"

        # Throughput should be reasonable
        throughput = 100 / processing_time
        min_throughput = 5.0  # At least 5 accounts per second
        assert (
            throughput >= min_throughput
        ), f"Throughput {throughput:.1f} accounts/sec is below minimum {min_throughput}"

        print(f"100-account processing: {processing_time:.3f}s ({throughput:.1f} accounts/sec)")

    @pytest.mark.performance
    def test_large_account_list_processing_200_accounts(self, mock_aws_client_manager, console):
        """Test processing operations across 200 accounts for extreme scalability."""
        # Create 200 test accounts
        accounts = self.create_test_accounts(200)

        # Create batch processor with larger batch size for better performance
        batch_processor = MultiAccountBatchProcessor(
            aws_client_manager=mock_aws_client_manager, batch_size=25
        )

        # Mock the resource resolver and display methods
        with patch.object(batch_processor, "_resolve_names") as mock_resolve:
            mock_resolve.return_value = None

            with patch.object(batch_processor.progress_tracker, "start_multi_account_progress"):
                with patch.object(batch_processor.progress_tracker, "stop_live_display"):
                    with patch.object(batch_processor, "_display_dry_run_summary"):
                        # Mock the single account operation to be fast
                        with patch.object(
                            batch_processor, "_process_single_account_operation"
                        ) as mock_process:
                            mock_process.return_value = AccountResult(
                                account_id="123456789012",
                                account_name="TestAccount",
                                status="success",
                                processing_time=0.05,
                                error_message="Assignment would be created",
                            )

                            start_time = time.time()

                            # Run the multi-account operation
                            results = asyncio.run(
                                batch_processor.process_multi_account_operation(
                                    accounts=accounts,
                                    permission_set_name="TestPermissionSet",
                                    principal_name="testuser",
                                    principal_type="USER",
                                    operation="assign",
                                    instance_arn="arn:aws:sso:::instance/ins-123",
                                    dry_run=True,
                                    continue_on_error=True,
                                )
                            )

                            processing_time = time.time() - start_time

        # Verify correctness
        assert results.total_accounts == 200
        assert len(results.successful_accounts) == 200
        assert len(results.failed_accounts) == 0

        # Performance assertions for larger scale
        max_time = 60.0  # Should process 200 accounts in under 60 seconds
        assert (
            processing_time < max_time
        ), f"Processing 200 accounts took {processing_time:.3f}s, expected < {max_time:.3f}s"

        # Throughput should scale reasonably
        throughput = 200 / processing_time
        min_throughput = 4.0  # At least 4 accounts per second for larger scale
        assert (
            throughput >= min_throughput
        ), f"Throughput {throughput:.1f} accounts/sec is below minimum {min_throughput}"

        print(f"200-account processing: {processing_time:.3f}s ({throughput:.1f} accounts/sec)")

    @pytest.mark.performance
    def test_batch_size_efficiency_comparison(self, mock_aws_client_manager, console):
        """Test different batch sizes to find optimal processing efficiency."""
        accounts = self.create_test_accounts(50)
        batch_sizes = [5, 10, 15, 20, 25]
        results_by_batch_size = {}

        for batch_size in batch_sizes:
            batch_processor = MultiAccountBatchProcessor(
                aws_client_manager=mock_aws_client_manager, batch_size=batch_size
            )

            # Mock the resource resolver and operations
            with patch.object(batch_processor, "_resolve_names") as mock_resolve:
                mock_resolve.return_value = None

                with patch.object(batch_processor.progress_tracker, "start_multi_account_progress"):
                    with patch.object(batch_processor.progress_tracker, "stop_live_display"):
                        with patch.object(batch_processor, "_display_dry_run_summary"):
                            with patch.object(
                                batch_processor, "_process_single_account_operation"
                            ) as mock_process:
                                mock_process.return_value = AccountResult(
                                    account_id="123456789012",
                                    account_name="TestAccount",
                                    status="success",
                                    processing_time=0.1,
                                    error_message="Assignment would be created",
                                )

                                start_time = time.time()

                                results = asyncio.run(
                                    batch_processor.process_multi_account_operation(
                                        accounts=accounts,
                                        permission_set_name="TestPermissionSet",
                                        principal_name="testuser",
                                        principal_type="USER",
                                        operation="assign",
                                        instance_arn="arn:aws:sso:::instance/ins-123",
                                        dry_run=True,
                                        continue_on_error=True,
                                    )
                                )

                                processing_time = time.time() - start_time
                    throughput = 50 / processing_time

                    results_by_batch_size[batch_size] = {
                        "time": processing_time,
                        "throughput": throughput,
                        "success_count": len(results.successful_accounts),
                    }

        # Verify all batch sizes processed correctly
        for batch_size, result in results_by_batch_size.items():
            assert (
                result["success_count"] == 50
            ), f"Batch size {batch_size} failed to process all accounts"
            assert (
                result["time"] < 20.0
            ), f"Batch size {batch_size} took too long: {result['time']:.3f}s"

        # Find optimal batch size (highest throughput)
        optimal_batch_size = max(
            results_by_batch_size.keys(), key=lambda x: results_by_batch_size[x]["throughput"]
        )

        print("Batch size efficiency results:")
        for batch_size in sorted(batch_sizes):
            result = results_by_batch_size[batch_size]
            marker = " ⭐" if batch_size == optimal_batch_size else ""
            print(
                f"  Batch size {batch_size:2d}: {result['time']:6.3f}s ({result['throughput']:5.1f} accounts/sec){marker}"
            )

        # Verify that larger batch sizes generally perform better (within reason)
        small_batch_throughput = results_by_batch_size[5]["throughput"]
        large_batch_throughput = results_by_batch_size[20]["throughput"]
        assert (
            large_batch_throughput >= small_batch_throughput * 0.8
        ), "Large batch sizes should not be significantly slower than small ones"

    @pytest.mark.performance
    @pytest.mark.skipif(not HAS_PSUTIL, reason="psutil not available for memory testing")
    def test_memory_usage_with_large_account_lists(self, mock_aws_client_manager, console):
        """Test memory usage doesn't grow excessively with large account lists."""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Test with increasingly large account lists
        test_sizes = [50, 100, 150, 200]
        memory_usage_by_size = {}

        for size in test_sizes:
            accounts = self.create_test_accounts(size)

            # Create batch processor
            batch_processor = MultiAccountBatchProcessor(
                aws_client_manager=mock_aws_client_manager, batch_size=20
            )

            # Mock operations for memory testing
            with patch.object(batch_processor, "_resolve_names") as mock_resolve:
                mock_resolve.return_value = None

                with patch.object(batch_processor.progress_tracker, "start_multi_account_progress"):
                    with patch.object(batch_processor.progress_tracker, "stop_live_display"):
                        with patch.object(batch_processor, "_display_dry_run_summary"):
                            with patch.object(
                                batch_processor, "_process_single_account_operation"
                            ) as mock_process:
                                mock_process.return_value = AccountResult(
                                    account_id="123456789012",
                                    account_name="TestAccount",
                                    status="success",
                                    processing_time=0.01,
                                    error_message="Assignment would be created",
                                )

                                # Process accounts and measure memory
                                results = asyncio.run(
                                    batch_processor.process_multi_account_operation(
                                        accounts=accounts,
                                        permission_set_name="TestPermissionSet",
                                        principal_name="testuser",
                                        principal_type="USER",
                                        operation="assign",
                                        instance_arn="arn:aws:sso:::instance/ins-123",
                                        dry_run=True,
                                        continue_on_error=True,
                                    )
                                )

                    # Measure memory after processing
                    current_memory = process.memory_info().rss / 1024 / 1024  # MB
                    memory_increase = current_memory - initial_memory
                    memory_usage_by_size[size] = memory_increase

                    # Verify processing was successful
                    assert results.total_accounts == size
                    assert len(results.successful_accounts) == size

                    # Clean up to free memory
                    del accounts
                    del results
                    del batch_processor

        # Analyze memory usage patterns
        print("Memory usage by account count:")
        for size in sorted(test_sizes):
            memory_mb = memory_usage_by_size[size]
            memory_per_account = memory_mb / size * 1024  # KB per account
            print(
                f"  {size:3d} accounts: {memory_mb:6.1f}MB total ({memory_per_account:5.1f}KB per account)"
            )

        # Memory usage should scale reasonably
        for size in test_sizes:
            memory_increase = memory_usage_by_size[size]
            max_memory_per_account = 0.5  # 500KB per account maximum
            max_memory_increase = size * max_memory_per_account

            assert memory_increase < max_memory_increase, (
                f"Memory increased by {memory_increase:.1f}MB for {size} accounts, "
                f"expected < {max_memory_increase:.1f}MB"
            )

        # Memory usage should not grow exponentially
        if len(test_sizes) >= 2:
            small_size, large_size = test_sizes[0], test_sizes[-1]
            small_memory = memory_usage_by_size[small_size]
            large_memory = memory_usage_by_size[large_size]

            # Memory should scale roughly linearly (allow 2x factor for overhead)
            expected_large_memory = small_memory * (large_size / small_size) * 2
            assert large_memory < expected_large_memory, (
                f"Memory usage grew too much: {large_memory:.1f}MB for {large_size} accounts, "
                f"expected < {expected_large_memory:.1f}MB"
            )

    @pytest.mark.performance
    def test_progress_tracking_performance_validation(self, console):
        """Test that progress tracking doesn't significantly impact performance."""
        # Test with and without progress tracking
        accounts = self.create_test_accounts(100)

        # Test without progress tracking (baseline)
        start_time = time.time()

        # Simulate processing without progress tracking
        results_without_tracking = []
        for i, account in enumerate(accounts):
            # Simulate some processing work
            time.sleep(0.001)  # 1ms per account
            result = AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status="success",
                processing_time=0.001,
            )
            results_without_tracking.append(result)

        baseline_time = time.time() - start_time

        # Test with progress tracking
        progress_tracker = MultiAccountProgressTracker(console)
        progress_tracker.start_multi_account_progress(
            total_accounts=len(accounts),
            operation_type="assign",
            show_live_results=False,  # Disable live display for performance testing
        )

        start_time = time.time()

        results_with_tracking = []
        for i, account in enumerate(accounts):
            # Update progress tracker
            progress_tracker.update_current_account(account.account_name, account.account_id)

            # Simulate some processing work
            time.sleep(0.001)  # 1ms per account

            result = AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status="success",
                processing_time=0.001,
            )
            results_with_tracking.append(result)

            # Record result in progress tracker
            progress_tracker.record_account_result(
                account_id=result.account_id,
                status=result.status,
                account_name=result.account_name,
                processing_time=result.processing_time,
            )

        tracking_time = time.time() - start_time
        progress_tracker.stop_live_display()

        # Calculate overhead
        overhead_time = tracking_time - baseline_time
        overhead_percentage = (overhead_time / baseline_time) * 100

        print("Progress tracking performance:")
        print(f"  Baseline time: {baseline_time:.3f}s")
        print(f"  With tracking: {tracking_time:.3f}s")
        print(f"  Overhead: {overhead_time:.3f}s ({overhead_percentage:.1f}%)")

        # Verify correctness
        assert len(results_without_tracking) == 100
        assert len(results_with_tracking) == 100

        # Progress tracking overhead should be minimal
        max_overhead_percentage = 50.0  # Allow up to 50% overhead for progress tracking
        assert (
            overhead_percentage < max_overhead_percentage
        ), f"Progress tracking overhead {overhead_percentage:.1f}% exceeds maximum {max_overhead_percentage}%"

        # Verify progress tracker recorded all results
        stats = progress_tracker.get_current_stats()
        assert stats["successful"] == 100
        assert stats["failed"] == 0
        assert stats["total_processed"] == 100

    @pytest.mark.performance
    def test_concurrent_account_processing_scalability(self, mock_aws_client_manager, console):
        """Test concurrent processing performance with different concurrency levels."""
        accounts = self.create_test_accounts(60)
        concurrency_levels = [1, 5, 10, 15, 20]
        results_by_concurrency = {}

        for max_concurrent in concurrency_levels:
            batch_processor = MultiAccountBatchProcessor(
                aws_client_manager=mock_aws_client_manager, batch_size=max_concurrent
            )

            # Mock operations with slight delay to test concurrency benefits
            with patch.object(batch_processor, "_resolve_names") as mock_resolve:
                mock_resolve.return_value = None

                with patch.object(batch_processor.progress_tracker, "start_multi_account_progress"):
                    with patch.object(batch_processor.progress_tracker, "stop_live_display"):
                        with patch.object(batch_processor, "_display_dry_run_summary"):

                            def mock_process_account(*args, **kwargs):
                                # Simulate some I/O delay
                                time.sleep(0.01)  # 10ms per account
                                return AccountResult(
                                    account_id="123456789012",
                                    account_name="TestAccount",
                                    status="success",
                                    processing_time=0.01,
                                    error_message="Assignment would be created",
                                )

                            with patch.object(
                                batch_processor,
                                "_process_single_account_operation",
                                side_effect=mock_process_account,
                            ):
                                start_time = time.time()

                                results = asyncio.run(
                                    batch_processor.process_multi_account_operation(
                                        accounts=accounts,
                                        permission_set_name="TestPermissionSet",
                                        principal_name="testuser",
                                        principal_type="USER",
                                        operation="assign",
                                        instance_arn="arn:aws:sso:::instance/ins-123",
                                        dry_run=True,
                                        continue_on_error=True,
                                    )
                                )

                                processing_time = time.time() - start_time
                    throughput = 60 / processing_time

                    results_by_concurrency[max_concurrent] = {
                        "time": processing_time,
                        "throughput": throughput,
                        "success_count": len(results.successful_accounts),
                    }

        # Verify all concurrency levels processed correctly
        for concurrency, result in results_by_concurrency.items():
            assert (
                result["success_count"] == 60
            ), f"Concurrency {concurrency} failed to process all accounts"

        print("Concurrency performance results:")
        for concurrency in sorted(concurrency_levels):
            result = results_by_concurrency[concurrency]
            print(
                f"  Concurrency {concurrency:2d}: {result['time']:6.3f}s ({result['throughput']:5.1f} accounts/sec)"
            )

        # Higher concurrency should generally improve performance
        sequential_time = results_by_concurrency[1]["time"]
        concurrent_time = results_by_concurrency[10]["time"]

        # Concurrent processing should be significantly faster
        improvement_factor = sequential_time / concurrent_time
        min_improvement = 2.0  # At least 2x improvement with concurrency
        assert (
            improvement_factor >= min_improvement
        ), f"Concurrent processing improvement {improvement_factor:.1f}x is below minimum {min_improvement}x"

    @pytest.mark.performance
    def test_error_handling_performance_impact(self, mock_aws_client_manager, console):
        """Test that error handling doesn't significantly impact performance."""
        accounts = self.create_test_accounts(50)

        # Test with all successful operations (baseline)
        batch_processor = MultiAccountBatchProcessor(
            aws_client_manager=mock_aws_client_manager, batch_size=10
        )

        with patch.object(batch_processor, "_resolve_names") as mock_resolve:
            mock_resolve.return_value = None

            with patch.object(batch_processor.progress_tracker, "start_multi_account_progress"):
                with patch.object(batch_processor.progress_tracker, "stop_live_display"):
                    with patch.object(batch_processor, "_display_dry_run_summary"):
                        # All successful operations
                        with patch.object(
                            batch_processor, "_process_single_account_operation"
                        ) as mock_process:
                            mock_process.return_value = AccountResult(
                                account_id="123456789012",
                                account_name="TestAccount",
                                status="success",
                                processing_time=0.01,
                                error_message="Assignment would be created",
                            )

                            start_time = time.time()

                            success_results = asyncio.run(
                                batch_processor.process_multi_account_operation(
                                    accounts=accounts,
                                    permission_set_name="TestPermissionSet",
                                    principal_name="testuser",
                                    principal_type="USER",
                                    operation="assign",
                                    instance_arn="arn:aws:sso:::instance/ins-123",
                                    dry_run=True,
                                    continue_on_error=True,
                                )
                            )

                            success_time = time.time() - start_time

        # Test with mixed success/failure operations
        batch_processor = MultiAccountBatchProcessor(
            aws_client_manager=mock_aws_client_manager, batch_size=10
        )

        with patch.object(batch_processor, "_resolve_names") as mock_resolve:
            mock_resolve.return_value = None

            with patch.object(batch_processor.progress_tracker, "start_multi_account_progress"):
                with patch.object(batch_processor.progress_tracker, "stop_live_display"):
                    with patch.object(batch_processor, "_display_dry_run_summary"):
                        # Mixed success/failure operations
                        def mock_process_with_errors(*args, **kwargs):
                            account_id = args[0].account_id if args else "123456789012"
                            # Fail every 3rd account
                            if int(account_id[-2:]) % 3 == 0:
                                return AccountResult(
                                    account_id=account_id,
                                    account_name="TestAccount",
                                    status="failed",
                                    error_message="Simulated error for testing",
                                    processing_time=0.01,
                                )
                            else:
                                return AccountResult(
                                    account_id=account_id,
                                    account_name="TestAccount",
                                    status="success",
                                    processing_time=0.01,
                                    error_message="Assignment would be created",
                                )

                        with patch.object(
                            batch_processor,
                            "_process_single_account_operation",
                            side_effect=mock_process_with_errors,
                        ):
                            start_time = time.time()

                            mixed_results = asyncio.run(
                                batch_processor.process_multi_account_operation(
                                    accounts=accounts,
                                    permission_set_name="TestPermissionSet",
                                    principal_name="testuser",
                                    principal_type="USER",
                                    operation="assign",
                                    instance_arn="arn:aws:sso:::instance/ins-123",
                                    dry_run=True,
                                    continue_on_error=True,
                                )
                            )

                            mixed_time = time.time() - start_time

        # Calculate error handling overhead
        error_overhead = mixed_time - success_time
        error_overhead_percentage = (error_overhead / success_time) * 100

        print("Error handling performance impact:")
        print(f"  All success: {success_time:.3f}s")
        print(f"  Mixed results: {mixed_time:.3f}s")
        print(f"  Error overhead: {error_overhead:.3f}s ({error_overhead_percentage:.1f}%)")

        # Verify correctness
        assert success_results.total_accounts == 50
        assert len(success_results.successful_accounts) == 50
        assert mixed_results.total_accounts == 50
        assert len(mixed_results.failed_accounts) > 0  # Should have some failures

        # Error handling overhead should be reasonable
        max_error_overhead = 100.0  # Allow up to 100% overhead for error handling
        assert (
            error_overhead_percentage < max_error_overhead
        ), f"Error handling overhead {error_overhead_percentage:.1f}% exceeds maximum {max_error_overhead}%"


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-m", "performance", "--tb=short"])
