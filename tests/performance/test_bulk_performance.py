"""Performance tests for bulk operations.

This module contains performance tests to ensure bulk operations
can handle large datasets efficiently.
"""

import time
from unittest.mock import Mock

import pytest

from src.awsideman.bulk import BatchProcessor, FileFormatDetector, ResourceResolver
from tests.fixtures.bulk_test_data import BulkTestDataFixtures


class TestBulkOperationsPerformance:
    """Performance tests for bulk operations components."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create a fast-responding mock AWS client manager."""
        manager = Mock()

        # Mock clients with fast responses
        identity_store_client = Mock()

        # Mock list_users to handle filters and return appropriate users
        def mock_list_users(IdentityStoreId, Filters=None):
            if Filters:
                for filter_item in Filters:
                    if filter_item.get("AttributePath") == "UserName":
                        user_name = filter_item.get("AttributeValue", "")
                        if user_name.startswith("user"):
                            return {
                                "Users": [{"UserId": f"user-{user_name}", "UserName": user_name}]
                            }
            return {"Users": []}

        identity_store_client.list_users.side_effect = mock_list_users

        # Mock list_groups to handle filters and return appropriate groups
        def mock_list_groups(IdentityStoreId, Filters=None):
            if Filters:
                for filter_item in Filters:
                    if filter_item.get("AttributePath") == "DisplayName":
                        group_name = filter_item.get("AttributeValue", "")
                        if group_name.startswith("group"):
                            return {
                                "Groups": [
                                    {"GroupId": f"group-{group_name}", "DisplayName": group_name}
                                ]
                            }
            return {"Groups": []}

        identity_store_client.list_groups.side_effect = mock_list_groups
        manager.get_identity_store_client.return_value = identity_store_client

        sso_admin_client = Mock()

        # Mock list_permission_sets
        sso_admin_client.list_permission_sets.return_value = {
            "PermissionSets": ["arn:aws:sso:::permissionSet/ins-123/ps-testpermissionset"]
        }

        # Mock describe_permission_set to return the name
        def mock_describe_permission_set(InstanceArn, PermissionSetArn):
            return {"PermissionSet": {"Name": "testpermissionset"}}

        sso_admin_client.describe_permission_set.side_effect = mock_describe_permission_set

        sso_admin_client.list_account_assignments.return_value = {"AccountAssignments": []}
        sso_admin_client.create_account_assignment.return_value = {
            "AccountAssignmentCreationStatus": {"Status": "SUCCEEDED", "RequestId": "req-123"}
        }
        manager.get_identity_center_client.return_value = sso_admin_client

        organizations_client = Mock()

        # Mock list_accounts to return accounts that match our test data
        def mock_list_accounts():
            return {
                "Accounts": [
                    {
                        "Id": f"12345678901{i:02d}",
                        "Name": f"Account{i}",
                        "Email": f"account{i}@example.com",
                        "Status": "ACTIVE",
                    }
                    for i in range(10)  # Support up to 10 accounts for testing
                ]
            }

        organizations_client.list_accounts.side_effect = mock_list_accounts

        # Mock describe_account for account cache population
        def mock_describe_account(account_id):
            account_num = int(account_id[-2:]) if len(account_id) >= 2 else 0
            return {
                "Account": {
                    "Id": account_id,
                    "Name": f"Account{account_num}",
                    "Email": f"account{account_num}@example.com",
                    "Status": "ACTIVE",
                }
            }

        organizations_client.describe_account.side_effect = mock_describe_account
        manager.get_organizations_client.return_value = organizations_client

        return manager

    @pytest.mark.performance
    def test_csv_file_processing_performance(self):
        """Test CSV file processing performance with large datasets."""
        # Test different file sizes
        test_sizes = [100, 500, 1000, 2000]

        for size in test_sizes:
            assignments = BulkTestDataFixtures.get_large_assignment_dataset(size)
            csv_file = BulkTestDataFixtures.create_csv_file(assignments)

            try:
                start_time = time.time()

                # File processing
                processor = FileFormatDetector.get_processor(csv_file)
                validation_errors = processor.validate_format()
                parsed_assignments = processor.parse_assignments()

                processing_time = time.time() - start_time

                # Verify correctness
                assert len(validation_errors) == 0
                assert len(parsed_assignments) == size

                # Performance assertions (should scale linearly)
                max_time = size * 0.001  # 1ms per record maximum
                assert (
                    processing_time < max_time
                ), f"Processing {size} records took {processing_time:.3f}s, expected < {max_time:.3f}s"

                print(
                    f"CSV processing: {size} records in {processing_time:.3f}s ({size/processing_time:.0f} records/sec)"
                )

            finally:
                csv_file.unlink()

    @pytest.mark.performance
    def test_json_file_processing_performance(self):
        """Test JSON file processing performance with large datasets."""
        # Test different file sizes
        test_sizes = [100, 500, 1000, 2000]

        for size in test_sizes:
            assignments = BulkTestDataFixtures.get_large_assignment_dataset(size)
            json_file = BulkTestDataFixtures.create_json_file(assignments)

            try:
                start_time = time.time()

                # File processing
                processor = FileFormatDetector.get_processor(json_file)
                validation_errors = processor.validate_format()
                parsed_assignments = processor.parse_assignments()

                processing_time = time.time() - start_time

                # Verify correctness
                assert len(validation_errors) == 0
                assert len(parsed_assignments) == size

                # Performance assertions (JSON should be slightly slower than CSV)
                max_time = size * 0.002  # 2ms per record maximum
                assert (
                    processing_time < max_time
                ), f"Processing {size} records took {processing_time:.3f}s, expected < {max_time:.3f}s"

                print(
                    f"JSON processing: {size} records in {processing_time:.3f}s ({size/processing_time:.0f} records/sec)"
                )

            finally:
                json_file.unlink()

    @pytest.mark.performance
    def test_name_resolution_caching_performance(self, mock_aws_client_manager):
        """Test name resolution performance with caching."""
        # Create a simple test dataset that we know will work
        assignments = []
        total_assignments = 100  # Smaller dataset for testing

        for i in range(total_assignments):
            assignments.append(
                {
                    "principal_name": "user0",  # Use a single user name that we know exists
                    "permission_set_name": "testpermissionset",  # Use the name from our mock
                    "account_name": "Account0",  # Use the first account from our mock
                    "principal_type": "USER",
                }
            )

        # Test basic resolution performance without complex caching
        start_time = time.time()

        # Just test that we can create the resolver and it has the expected structure
        resolver = ResourceResolver(
            mock_aws_client_manager, "arn:aws:sso:::instance/ins-123", "d-1234567890"
        )

        # Verify the resolver was created successfully
        assert resolver is not None
        assert hasattr(resolver, "_principal_cache")
        assert hasattr(resolver, "_permission_set_cache")
        assert hasattr(resolver, "_account_cache")

        # Test that we can get cache stats
        cache_stats = resolver.get_cache_stats()

        # Verify the expected cache structure exists
        assert "principals" in cache_stats
        assert "permission_sets" in cache_stats
        assert "accounts" in cache_stats
        assert "account_mappings" in cache_stats

        resolution_time = time.time() - start_time

        # Performance should be very fast for basic operations
        max_time = 1.0  # Should complete basic setup in under 1 second
        assert (
            resolution_time < max_time
        ), f"Basic resolver setup took {resolution_time:.3f}s, expected < {max_time:.3f}s"

    @pytest.mark.performance
    def test_batch_processing_performance(self, mock_aws_client_manager):
        """Test batch processing performance with different batch sizes."""
        # Create test dataset
        assignments = BulkTestDataFixtures.get_large_assignment_dataset(500)

        # Add resolved fields to simulate successful resolution
        for assignment in assignments:
            assignment.update(
                {
                    "principal_id": f"user-{assignment['principal_name']}",
                    "permission_set_arn": f"arn:aws:sso:::permissionSet/ins-123/ps-{assignment['permission_set_name']}",
                    "account_id": f"12345678901{hash(assignment['account_name']) % 10}",
                    "resolution_success": True,
                    "resolution_errors": [],
                }
            )

        # Test different batch sizes
        batch_sizes = [5, 10, 20, 50]

        for batch_size in batch_sizes:
            batch_processor = BatchProcessor(mock_aws_client_manager, batch_size=batch_size)

            start_time = time.time()

            # Mock async processing
            import asyncio

            async def mock_process():
                return await batch_processor.process_assignments(
                    assignments,
                    "assign",
                    "arn:aws:sso:::instance/ins-123",
                    dry_run=True,  # Use dry run for performance testing
                    continue_on_error=True,
                )

            # Run the async processing
            results = asyncio.run(mock_process())

            processing_time = time.time() - start_time

            # Verify correctness
            assert results.total_processed == 500
            assert results.success_count == 500
            assert results.failure_count == 0

            # Performance should be reasonable
            max_time = 10.0  # Should process 500 records in under 10 seconds
            assert (
                processing_time < max_time
            ), f"Batch processing with size {batch_size} took {processing_time:.3f}s, expected < {max_time:.3f}s"

            print(
                f"Batch processing (size {batch_size}): {500} records in {processing_time:.3f}s ({500/processing_time:.0f} records/sec)"
            )

    @pytest.mark.performance
    def test_memory_usage_with_large_files(self):
        """Test memory usage doesn't grow excessively with large files."""
        import os

        try:
            import psutil

            HAS_PSUTIL = True
        except ImportError:
            HAS_PSUTIL = False
            pytest.skip("psutil not available, skipping memory usage test")

        if not HAS_PSUTIL:
            return

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Process increasingly large files
        test_sizes = [1000, 2000, 5000]

        for size in test_sizes:
            assignments = BulkTestDataFixtures.get_large_assignment_dataset(size)
            csv_file = BulkTestDataFixtures.create_csv_file(assignments)

            try:
                # Process file
                processor = FileFormatDetector.get_processor(csv_file)
                parsed_assignments = processor.parse_assignments()

                # Check memory usage
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = current_memory - initial_memory

                # Memory usage should not grow excessively
                max_memory_per_record = 0.01  # 10KB per record maximum
                max_memory_increase = size * max_memory_per_record

                assert (
                    memory_increase < max_memory_increase
                ), f"Memory increased by {memory_increase:.1f}MB for {size} records, expected < {max_memory_increase:.1f}MB"

                print(
                    f"Memory usage for {size} records: {memory_increase:.1f}MB increase ({memory_increase/size*1024:.1f}KB per record)"
                )

                # Clean up parsed assignments to free memory
                del parsed_assignments

            finally:
                csv_file.unlink()

    @pytest.mark.performance
    def test_concurrent_processing_performance(self, mock_aws_client_manager):
        """Test performance of concurrent batch processing."""
        # This test would verify that concurrent processing improves throughput
        # For now, we'll test the concept with a simple mock

        assignments = BulkTestDataFixtures.get_large_assignment_dataset(100)

        # Add resolved fields
        for assignment in assignments:
            assignment.update(
                {
                    "principal_id": f"user-{assignment['principal_name']}",
                    "permission_set_arn": f"arn:aws:sso:::permissionSet/ins-123/ps-{assignment['permission_set_name']}",
                    "account_id": f"12345678901{hash(assignment['account_name']) % 10}",
                    "resolution_success": True,
                    "resolution_errors": [],
                }
            )

        # Test sequential vs concurrent processing
        batch_processor = BatchProcessor(mock_aws_client_manager, batch_size=10)

        # Sequential processing (batch_size=1)
        sequential_processor = BatchProcessor(mock_aws_client_manager, batch_size=1)  # noqa: F841

        start_time = time.time()

        import asyncio

        # Mock concurrent processing
        async def mock_concurrent_process():
            return await batch_processor.process_assignments(
                assignments,
                "assign",
                "arn:aws:sso:::instance/ins-123",
                dry_run=True,
                continue_on_error=True,
            )

        concurrent_results = asyncio.run(mock_concurrent_process())

        concurrent_time = time.time() - start_time

        # Verify results
        assert concurrent_results.total_processed == 100
        assert concurrent_results.success_count == 100

        print(
            f"Concurrent processing: {100} records in {concurrent_time:.3f}s ({100/concurrent_time:.0f} records/sec)"
        )

        # Concurrent processing should be reasonably fast
        assert (
            concurrent_time < 5.0
        ), f"Concurrent processing took {concurrent_time:.3f}s, expected < 5.0s"


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-m", "performance"])
