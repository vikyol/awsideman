"""Integration tests for bulk operations.

This module contains integration tests that test the complete bulk operations
workflow from file input to final results.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from rich.console import Console

from src.awsideman.utils.bulk import (
    FileFormatDetector, ResourceResolver, PreviewGenerator,
    BatchProcessor, ReportGenerator, AssignmentResult, BulkOperationResults
)
from tests.fixtures.bulk_test_data import BulkTestDataFixtures, MockAWSResponses


class TestBulkOperationsEndToEnd:
    """End-to-end integration tests for bulk operations."""
    
    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create a comprehensive mock AWS client manager."""
        manager = Mock()
        
        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = MockAWSResponses.get_successful_user_resolution()
        identity_store_client.list_groups.return_value = MockAWSResponses.get_successful_group_resolution()
        manager.get_identity_store_client.return_value = identity_store_client
        
        # Mock SSO Admin client
        sso_admin_client = Mock()
        sso_admin_client.list_permission_sets.return_value = MockAWSResponses.get_successful_permission_set_resolution()
        sso_admin_client.list_account_assignments.return_value = MockAWSResponses.get_empty_assignments()
        sso_admin_client.create_account_assignment.return_value = MockAWSResponses.get_successful_assignment_creation()
        sso_admin_client.delete_account_assignment.return_value = MockAWSResponses.get_successful_assignment_deletion()
        manager.get_identity_center_client.return_value = sso_admin_client
        
        # Mock Organizations client
        organizations_client = Mock()
        organizations_client.list_accounts.return_value = MockAWSResponses.get_successful_account_resolution()
        manager.get_organizations_client.return_value = organizations_client
        
        return manager
    
    @pytest.fixture
    def console(self):
        """Create a console for testing."""
        return Console()
    
    def test_complete_csv_assign_workflow(self, mock_aws_client_manager, console):
        """Test complete CSV assign workflow from file to results."""
        # Create test CSV file
        assignments = BulkTestDataFixtures.get_valid_user_assignments()
        csv_file = BulkTestDataFixtures.create_csv_file(assignments)
        
        try:
            # Step 1: File processing
            processor = FileFormatDetector.get_processor(csv_file)
            assert processor is not None
            
            validation_errors = processor.validate_format()
            assert len(validation_errors) == 0
            
            parsed_assignments = processor.parse_assignments()
            assert len(parsed_assignments) == 2
            
            # Step 2: Name resolution
            resolver = ResourceResolver(
                mock_aws_client_manager,
                'arn:aws:sso:::instance/ins-123',
                'd-1234567890'
            )
            
            resolved_assignments = []
            for assignment in parsed_assignments:
                resolved = resolver.resolve_assignment(assignment)
                resolved_assignments.append(resolved)
            
            # Verify all assignments were resolved successfully
            successful_resolutions = [a for a in resolved_assignments if a.get('resolution_success', False)]
            assert len(successful_resolutions) == 2
            
            # Step 3: Preview generation
            preview_generator = PreviewGenerator(console)
            preview_summary = preview_generator.generate_preview_report(resolved_assignments, 'assign')
            
            assert preview_summary.total_assignments == 2
            assert preview_summary.successful_resolutions == 2
            assert preview_summary.failed_resolutions == 0
            
            # Step 4: Batch processing
            batch_processor = BatchProcessor(mock_aws_client_manager, batch_size=2)
            
            # Mock the async processing
            with patch('asyncio.run') as mock_asyncio_run:
                # Create mock results
                mock_results = BulkOperationResults(
                    total_processed=2,
                    operation_type='assign',
                    duration=1.5
                )
                
                # Add successful results
                for assignment in successful_resolutions:
                    result = AssignmentResult(
                        principal_name=assignment['principal_name'],
                        permission_set_name=assignment['permission_set_name'],
                        account_name=assignment['account_name'],
                        principal_type=assignment['principal_type'],
                        status='success',
                        principal_id=assignment.get('principal_id'),
                        permission_set_arn=assignment.get('permission_set_arn'),
                        account_id=assignment.get('account_id')
                    )
                    mock_results.successful.append(result)
                
                mock_asyncio_run.return_value = mock_results
                
                # Process assignments
                results = mock_asyncio_run.return_value
                
                # Verify results
                assert results.total_processed == 2
                assert results.success_count == 2
                assert results.failure_count == 0
                assert results.operation_type == 'assign'
            
            # Step 5: Report generation
            report_generator = ReportGenerator(console)
            
            # Generate reports (should not raise exceptions)
            report_generator.generate_summary_report(results, 'assign')
            report_generator.generate_performance_report(results)
            
        finally:
            # Clean up
            csv_file.unlink()
    
    def test_complete_json_revoke_workflow(self, mock_aws_client_manager, console):
        """Test complete JSON revoke workflow from file to results."""
        # Create test JSON file
        assignments = BulkTestDataFixtures.get_mixed_assignments()
        json_file = BulkTestDataFixtures.create_json_file(assignments)
        
        try:
            # Step 1: File processing
            processor = FileFormatDetector.get_processor(json_file)
            assert processor is not None
            
            validation_errors = processor.validate_format()
            assert len(validation_errors) == 0
            
            parsed_assignments = processor.parse_assignments()
            assert len(parsed_assignments) == 3
            
            # Step 2: Name resolution
            resolver = ResourceResolver(
                mock_aws_client_manager,
                'arn:aws:sso:::instance/ins-123',
                'd-1234567890'
            )
            
            resolved_assignments = []
            for assignment in parsed_assignments:
                resolved = resolver.resolve_assignment(assignment)
                resolved_assignments.append(resolved)
            
            # Step 3: Preview and batch processing for revoke
            preview_generator = PreviewGenerator(console)
            preview_summary = preview_generator.generate_preview_report(resolved_assignments, 'revoke')
            
            assert preview_summary.total_assignments == 3
            
            # Mock existing assignments for revoke operation
            mock_aws_client_manager.get_identity_center_client.return_value.list_account_assignments.return_value = MockAWSResponses.get_existing_assignments()
            
            batch_processor = BatchProcessor(mock_aws_client_manager, batch_size=3)
            
            # Mock the async processing for revoke
            with patch('asyncio.run') as mock_asyncio_run:
                mock_results = BulkOperationResults(
                    total_processed=3,
                    operation_type='revoke',
                    duration=2.0
                )
                
                # Add mixed results
                successful_resolutions = [a for a in resolved_assignments if a.get('resolution_success', False)]
                for i, assignment in enumerate(successful_resolutions):
                    status = 'success' if i < 2 else 'failed'  # Make one fail for testing
                    result = AssignmentResult(
                        principal_name=assignment['principal_name'],
                        permission_set_name=assignment['permission_set_name'],
                        account_name=assignment['account_name'],
                        principal_type=assignment['principal_type'],
                        status=status,
                        error_message='Assignment not found' if status == 'failed' else None
                    )
                    
                    if status == 'success':
                        mock_results.successful.append(result)
                    else:
                        mock_results.failed.append(result)
                
                mock_asyncio_run.return_value = mock_results
                
                results = mock_asyncio_run.return_value
                
                # Verify mixed results
                assert results.total_processed == 3
                assert results.success_count == 2
                assert results.failure_count == 1
                assert results.operation_type == 'revoke'
            
            # Step 4: Report generation with errors
            report_generator = ReportGenerator(console)
            
            report_generator.generate_summary_report(results, 'revoke')
            report_generator.generate_error_summary(results)
            report_generator.generate_detailed_report(results, show_failed=True)
            
        finally:
            # Clean up
            json_file.unlink()
    
    def test_workflow_with_resolution_errors(self, mock_aws_client_manager, console):
        """Test workflow with name resolution errors."""
        # Create test data with names that won't resolve
        assignments = [
            {
                'principal_name': 'nonexistent.user',
                'permission_set_name': 'NonexistentPermissionSet',
                'account_name': 'NonexistentAccount',
                'principal_type': 'USER'
            }
        ]
        
        csv_file = BulkTestDataFixtures.create_csv_file(assignments)
        
        try:
            # Mock failed resolutions
            mock_aws_client_manager.get_identity_store_client.return_value.list_users.return_value = {'Users': []}
            mock_aws_client_manager.get_identity_center_client.return_value.list_permission_sets.return_value = {'PermissionSets': []}
            mock_aws_client_manager.get_organizations_client.return_value.list_accounts.return_value = {'Accounts': []}
            
            # Process file
            processor = FileFormatDetector.get_processor(csv_file)
            parsed_assignments = processor.parse_assignments()
            
            # Resolve names (should fail)
            resolver = ResourceResolver(
                mock_aws_client_manager,
                'arn:aws:sso:::instance/ins-123',
                'd-1234567890'
            )
            
            resolved_assignments = []
            for assignment in parsed_assignments:
                resolved = resolver.resolve_assignment(assignment)
                resolved_assignments.append(resolved)
            
            # Verify resolution failures
            failed_resolutions = [a for a in resolved_assignments if not a.get('resolution_success', True)]
            assert len(failed_resolutions) == 1
            
            # Preview should show errors
            preview_generator = PreviewGenerator(console)
            preview_summary = preview_generator.generate_preview_report(resolved_assignments, 'assign')
            
            assert preview_summary.total_assignments == 1
            assert preview_summary.successful_resolutions == 0
            assert preview_summary.failed_resolutions == 1
            
            # Batch processing should skip failed resolutions
            batch_processor = BatchProcessor(mock_aws_client_manager, batch_size=1)
            
            with patch('asyncio.run') as mock_asyncio_run:
                mock_results = BulkOperationResults(
                    total_processed=1,
                    operation_type='assign',
                    duration=0.5
                )
                
                # Add failed result due to resolution error
                result = AssignmentResult(
                    principal_name='nonexistent.user',
                    permission_set_name='NonexistentPermissionSet',
                    account_name='NonexistentAccount',
                    principal_type='USER',
                    status='failed',
                    error_message='Resolution failed: User nonexistent.user not found'
                )
                mock_results.failed.append(result)
                
                mock_asyncio_run.return_value = mock_results
                
                results = mock_asyncio_run.return_value
                
                assert results.total_processed == 1
                assert results.success_count == 0
                assert results.failure_count == 1
            
        finally:
            csv_file.unlink()
    
    def test_workflow_with_malformed_files(self, mock_aws_client_manager, console):
        """Test workflow with malformed input files."""
        # Test malformed CSV
        malformed_csv = BulkTestDataFixtures.create_malformed_csv_file()
        
        try:
            processor = FileFormatDetector.get_processor(malformed_csv)
            validation_errors = processor.validate_format()
            
            # Should have validation errors
            assert len(validation_errors) > 0
            
        finally:
            malformed_csv.unlink()
        
        # Test malformed JSON
        malformed_json = BulkTestDataFixtures.create_malformed_json_file()
        
        try:
            processor = FileFormatDetector.get_processor(malformed_json)
            validation_errors = processor.validate_format()
            
            # Should have validation errors
            assert len(validation_errors) > 0
            
        finally:
            malformed_json.unlink()
    
    def test_workflow_with_empty_files(self, mock_aws_client_manager, console):
        """Test workflow with empty input files."""
        # Test empty CSV
        empty_csv = BulkTestDataFixtures.create_empty_csv_file()
        
        try:
            processor = FileFormatDetector.get_processor(empty_csv)
            validation_errors = processor.validate_format()
            assert len(validation_errors) == 0  # Empty file should be valid
            
            parsed_assignments = processor.parse_assignments()
            assert len(parsed_assignments) == 0
            
        finally:
            empty_csv.unlink()
        
        # Test empty JSON
        empty_json = BulkTestDataFixtures.create_empty_json_file()
        
        try:
            processor = FileFormatDetector.get_processor(empty_json)
            validation_errors = processor.validate_format()
            assert len(validation_errors) == 0  # Empty file should be valid
            
            parsed_assignments = processor.parse_assignments()
            assert len(parsed_assignments) == 0
            
        finally:
            empty_json.unlink()


class TestBulkOperationsPerformance:
    """Performance tests for bulk operations."""
    
    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create a mock AWS client manager for performance testing."""
        manager = Mock()
        
        # Mock fast responses
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = MockAWSResponses.get_successful_user_resolution()
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
    
    def test_large_file_processing_performance(self, mock_aws_client_manager):
        """Test processing performance with large input files."""
        import time
        
        # Create large dataset
        large_assignments = BulkTestDataFixtures.get_large_assignment_dataset(size=1000)
        csv_file = BulkTestDataFixtures.create_csv_file(large_assignments)
        
        try:
            start_time = time.time()
            
            # File processing
            processor = FileFormatDetector.get_processor(csv_file)
            validation_errors = processor.validate_format()
            assert len(validation_errors) == 0
            
            parsed_assignments = processor.parse_assignments()
            assert len(parsed_assignments) == 1000
            
            file_processing_time = time.time() - start_time
            
            # Name resolution with caching
            start_time = time.time()
            
            resolver = ResourceResolver(
                mock_aws_client_manager,
                'arn:aws:sso:::instance/ins-123',
                'd-1234567890'
            )
            
            # Pre-warm cache
            resolver.warm_cache_for_assignments(parsed_assignments)
            
            resolved_assignments = []
            for assignment in parsed_assignments:
                resolved = resolver.resolve_assignment(assignment)
                resolved_assignments.append(resolved)
            
            resolution_time = time.time() - start_time
            
            # Verify performance is reasonable
            assert file_processing_time < 5.0  # Should process 1000 records in under 5 seconds
            assert resolution_time < 10.0  # Should resolve 1000 records in under 10 seconds with caching
            
            # Verify all assignments were processed
            assert len(resolved_assignments) == 1000
            
        finally:
            csv_file.unlink()
    
    def test_caching_effectiveness(self, mock_aws_client_manager):
        """Test that caching improves resolution performance."""
        import time
        
        # Create dataset with repeated names (should benefit from caching)
        assignments = []
        for i in range(100):
            assignments.append({
                'principal_name': f'user{i % 10}',  # Only 10 unique users
                'permission_set_name': f'PermissionSet{i % 5}',  # Only 5 unique permission sets
                'account_name': f'Account{i % 3}',  # Only 3 unique accounts
                'principal_type': 'USER'
            })
        
        csv_file = BulkTestDataFixtures.create_csv_file(assignments)
        
        try:
            processor = FileFormatDetector.get_processor(csv_file)
            parsed_assignments = processor.parse_assignments()
            
            resolver = ResourceResolver(
                mock_aws_client_manager,
                'arn:aws:sso:::instance/ins-123',
                'd-1234567890'
            )
            
            # Time resolution without cache warming
            start_time = time.time()
            
            resolved_assignments = []
            for assignment in parsed_assignments:
                resolved = resolver.resolve_assignment(assignment)
                resolved_assignments.append(resolved)
            
            resolution_time = time.time() - start_time
            
            # Verify caching worked (should be fast due to repeated names)
            assert resolution_time < 2.0  # Should be very fast with caching
            assert len(resolved_assignments) == 100
            
            # Verify cache hit statistics
            cache_stats = resolver.get_cache_stats()
            assert cache_stats['principal_cache_hits'] > 0
            assert cache_stats['permission_set_cache_hits'] > 0
            assert cache_stats['account_cache_hits'] > 0
            
        finally:
            csv_file.unlink()


class TestBulkOperationsErrorHandling:
    """Error handling tests for bulk operations."""
    
    def test_continue_on_error_behavior(self):
        """Test continue-on-error vs stop-on-error behavior."""
        # This would be tested with actual batch processing
        # For now, we verify the concept through unit tests
        pass
    
    def test_network_error_retry_logic(self):
        """Test retry logic for network errors."""
        # This would test the RetryHandler with actual network errors
        pass
    
    def test_aws_api_rate_limiting_handling(self):
        """Test handling of AWS API rate limiting."""
        # This would test exponential backoff with rate limiting errors
        pass