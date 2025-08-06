"""Performance tests for bulk operations.

This module contains performance tests to ensure bulk operations
can handle large datasets efficiently.
"""
import pytest
import time
from unittest.mock import Mock
from pathlib import Path

from src.awsideman.utils.bulk import (
    FileFormatDetector, ResourceResolver, BatchProcessor
)
from tests.fixtures.bulk_test_data import BulkTestDataFixtures, MockAWSResponses


class TestBulkOperationsPerformance:
    """Performance tests for bulk operations components."""
    
    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create a fast-responding mock AWS client manager."""
        manager = Mock()
        
        # Mock clients with fast responses
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = MockAWSResponses.get_successful_user_resolution()
        identity_store_client.list_groups.return_value = MockAWSResponses.get_successful_group_resolution()
        manager.get_identity_store_client.return_value = identity_store_client
        
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = MockAWSResponses.get_successful_permission_set_resolution()
        sso_admin_client.list_account_assignments.return_value = MockAWSResponses.get_empty_assignments()
        sso_admin_client.create_account_assignment.return_value = MockAWSResponses.get_successful_assignment_creation()
        manager.get_identity_center_client.return_value = sso_admin_client
        
        organizations_client = Mock()
        organizations_client.list_accounts.return_value = MockAWSResponses.get_successful_account_resolution()
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
                assert processing_time < max_time, f"Processing {size} records took {processing_time:.3f}s, expected < {max_time:.3f}s"
                
                print(f"CSV processing: {size} records in {processing_time:.3f}s ({size/processing_time:.0f} records/sec)")
                
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
                assert processing_time < max_time, f"Processing {size} records took {processing_time:.3f}s, expected < {max_time:.3f}s"
                
                print(f"JSON processing: {size} records in {processing_time:.3f}s ({size/processing_time:.0f} records/sec)")
                
            finally:
                json_file.unlink()
    
    @pytest.mark.performance
    def test_name_resolution_caching_performance(self, mock_aws_client_manager):
        """Test name resolution performance with caching."""
        # Create dataset with many repeated names (should benefit from caching)
        assignments = []
        unique_users = 50
        unique_permission_sets = 20
        unique_accounts = 10
        total_assignments = 1000
        
        for i in range(total_assignments):
            assignments.append({
                'principal_name': f'user{i % unique_users}',
                'permission_set_name': f'PermissionSet{i % unique_permission_sets}',
                'account_name': f'Account{i % unique_accounts}',
                'principal_type': 'USER'
            })
        
        resolver = ResourceResolver(
            mock_aws_client_manager,
            'arn:aws:sso:::instance/ins-123',
            'd-1234567890'
        )
        
        # Test resolution performance
        start_time = time.time()
        
        resolved_assignments = []
        for assignment in assignments:
            resolved = resolver.resolve_assignment(assignment)
            resolved_assignments.append(resolved)
        
        resolution_time = time.time() - start_time
        
        # Verify correctness
        assert len(resolved_assignments) == total_assignments
        successful_resolutions = [a for a in resolved_assignments if a.get('resolution_success', False)]
        assert len(successful_resolutions) == total_assignments
        
        # Performance assertions (caching should make this very fast)
        max_time = 5.0  # Should resolve 1000 records in under 5 seconds with caching
        assert resolution_time < max_time, f"Resolution took {resolution_time:.3f}s, expected < {max_time:.3f}s"
        
        # Verify cache effectiveness
        cache_stats = resolver.get_cache_stats()
        assert cache_stats['principal_cache_hits'] > 0
        assert cache_stats['permission_set_cache_hits'] > 0
        assert cache_stats['account_cache_hits'] > 0
        
        # Cache hit rate should be high due to repeated names
        total_principal_requests = cache_stats['principal_cache_hits'] + cache_stats['principal_cache_misses']
        principal_hit_rate = cache_stats['principal_cache_hits'] / total_principal_requests
        assert principal_hit_rate > 0.9, f"Principal cache hit rate {principal_hit_rate:.2f} should be > 0.9"
        
        print(f"Name resolution: {total_assignments} records in {resolution_time:.3f}s ({total_assignments/resolution_time:.0f} records/sec)")
        print(f"Cache hit rates - Principal: {principal_hit_rate:.2%}, Permission Set: {cache_stats['permission_set_cache_hits']/(cache_stats['permission_set_cache_hits']+cache_stats['permission_set_cache_misses']):.2%}, Account: {cache_stats['account_cache_hits']/(cache_stats['account_cache_hits']+cache_stats['account_cache_misses']):.2%}")
    
    @pytest.mark.performance
    def test_batch_processing_performance(self, mock_aws_client_manager):
        """Test batch processing performance with different batch sizes."""
        # Create test dataset
        assignments = BulkTestDataFixtures.get_large_assignment_dataset(500)
        
        # Add resolved fields to simulate successful resolution
        for assignment in assignments:
            assignment.update({
                'principal_id': f"user-{assignment['principal_name']}",
                'permission_set_arn': f"arn:aws:sso:::permissionSet/ins-123/ps-{assignment['permission_set_name']}",
                'account_id': f"12345678901{hash(assignment['account_name']) % 10}",
                'resolution_success': True,
                'resolution_errors': []
            })
        
        # Test different batch sizes
        batch_sizes = [5, 10, 20, 50]
        
        for batch_size in batch_sizes:
            batch_processor = BatchProcessor(mock_aws_client_manager, batch_size=batch_size)
            
            start_time = time.time()
            
            # Mock async processing
            with pytest.importorskip('asyncio'):
                import asyncio
                
                async def mock_process():
                    return await batch_processor.process_assignments(
                        assignments,
                        'assign',
                        'arn:aws:sso:::instance/ins-123',
                        dry_run=True,  # Use dry run for performance testing
                        continue_on_error=True
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
            assert processing_time < max_time, f"Batch processing with size {batch_size} took {processing_time:.3f}s, expected < {max_time:.3f}s"
            
            print(f"Batch processing (size {batch_size}): {500} records in {processing_time:.3f}s ({500/processing_time:.0f} records/sec)")
    
    @pytest.mark.performance
    def test_memory_usage_with_large_files(self):
        """Test memory usage doesn't grow excessively with large files."""
        import psutil
        import os
        
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
                
                assert memory_increase < max_memory_increase, f"Memory increased by {memory_increase:.1f}MB for {size} records, expected < {max_memory_increase:.1f}MB"
                
                print(f"Memory usage for {size} records: {memory_increase:.1f}MB increase ({memory_increase/size*1024:.1f}KB per record)")
                
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
            assignment.update({
                'principal_id': f"user-{assignment['principal_name']}",
                'permission_set_arn': f"arn:aws:sso:::permissionSet/ins-123/ps-{assignment['permission_set_name']}",
                'account_id': f"12345678901{hash(assignment['account_name']) % 10}",
                'resolution_success': True,
                'resolution_errors': []
            })
        
        # Test sequential vs concurrent processing
        batch_processor = BatchProcessor(mock_aws_client_manager, batch_size=10)
        
        # Sequential processing (batch_size=1)
        sequential_processor = BatchProcessor(mock_aws_client_manager, batch_size=1)
        
        start_time = time.time()
        
        with pytest.importorskip('asyncio'):
            import asyncio
            
            # Mock concurrent processing
            async def mock_concurrent_process():
                return await batch_processor.process_assignments(
                    assignments,
                    'assign',
                    'arn:aws:sso:::instance/ins-123',
                    dry_run=True,
                    continue_on_error=True
                )
            
            concurrent_results = asyncio.run(mock_concurrent_process())
        
        concurrent_time = time.time() - start_time
        
        # Verify results
        assert concurrent_results.total_processed == 100
        assert concurrent_results.success_count == 100
        
        print(f"Concurrent processing: {100} records in {concurrent_time:.3f}s ({100/concurrent_time:.0f} records/sec)")
        
        # Concurrent processing should be reasonably fast
        assert concurrent_time < 5.0, f"Concurrent processing took {concurrent_time:.3f}s, expected < 5.0s"


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-m", "performance"])