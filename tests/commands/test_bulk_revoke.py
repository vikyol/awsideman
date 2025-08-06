"""Tests for bulk revoke command."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import csv
import json

from src.awsideman.commands.bulk import bulk_revoke
from src.awsideman.utils.bulk import BatchProcessor, AssignmentResult, BulkOperationResults


class TestBulkRevokeCommand:
    """Test cases for bulk revoke command."""
    
    def test_bulk_revoke_csv_dry_run(self):
        """Test bulk revoke with CSV file in dry-run mode."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(['principal_name', 'permission_set_name', 'account_name', 'principal_type'])
            writer.writerow(['test-user', 'ReadOnlyAccess', 'TestAccount', 'USER'])
            writer.writerow(['test-group', 'PowerUserAccess', 'DevAccount', 'GROUP'])
            csv_file = Path(f.name)
        
        try:
            # Mock the dependencies
            with patch('src.awsideman.commands.bulk.validate_profile') as mock_validate_profile, \
                 patch('src.awsideman.commands.bulk.validate_sso_instance') as mock_validate_sso, \
                 patch('src.awsideman.commands.bulk.AWSClientManager') as mock_client_manager, \
                 patch('src.awsideman.commands.bulk.console') as mock_console:
                
                # Setup mocks
                mock_validate_profile.return_value = ('test-profile', {'sso_start_url': 'test'})
                mock_validate_sso.return_value = ('test-instance-arn', 'test-identity-store-id')
                
                # Mock the file processing and resolution
                with patch('src.awsideman.utils.bulk.processors.FileFormatDetector.get_processor') as mock_processor, \
                     patch('src.awsideman.utils.bulk.resolver.ResourceResolver') as mock_resolver, \
                     patch('src.awsideman.utils.bulk.preview.PreviewGenerator') as mock_preview:
                    
                    # Setup processor mock
                    mock_proc_instance = Mock()
                    mock_proc_instance.validate_format.return_value = []
                    mock_proc_instance.parse_assignments.return_value = [
                        {
                            'principal_name': 'test-user',
                            'permission_set_name': 'ReadOnlyAccess',
                            'account_name': 'TestAccount',
                            'principal_type': 'USER'
                        },
                        {
                            'principal_name': 'test-group',
                            'permission_set_name': 'PowerUserAccess',
                            'account_name': 'DevAccount',
                            'principal_type': 'GROUP'
                        }
                    ]
                    mock_processor.return_value = mock_proc_instance
                    
                    # Setup resolver mock
                    def mock_resolve_assignment(assignment):
                        return {
                            **assignment,
                            'principal_id': f"{assignment['principal_name']}-id",
                            'permission_set_arn': f"arn:aws:sso:::permissionSet/test/{assignment['permission_set_name']}",
                            'account_id': '123456789012' if assignment['account_name'] == 'TestAccount' else '123456789013',
                            'resolution_success': True,
                            'resolution_errors': []
                        }
                    
                    mock_resolver_instance = Mock()
                    mock_resolver_instance.resolve_assignment.side_effect = mock_resolve_assignment
                    mock_resolver.return_value = mock_resolver_instance
                    
                    # Setup preview mock
                    mock_preview_instance = Mock()
                    mock_preview_instance.generate_preview_report.return_value = Mock(
                        total_assignments=2,
                        successful_resolutions=2,
                        failed_resolutions=0
                    )
                    mock_preview.return_value = mock_preview_instance
                    
                    # Test dry-run mode (should exit early)
                    with pytest.raises(SystemExit) as exc_info:
                        bulk_revoke(csv_file, dry_run=True, continue_on_error=True, batch_size=10, force=False, profile=None)
                    
                    # Verify dry-run completed successfully
                    assert exc_info.value.code == 0
                    
                    # Verify preview was generated with revoke operation
                    mock_preview_instance.generate_preview_report.assert_called_once()
                    call_args = mock_preview_instance.generate_preview_report.call_args
                    assert call_args[0][1] == "revoke"  # Second argument should be "revoke"
                    
                    mock_preview_instance.display_dry_run_message.assert_called_once_with("revoke", mock_preview_instance.generate_preview_report.return_value)
        
        finally:
            # Clean up temporary file
            csv_file.unlink()
    
    def test_bulk_revoke_with_force_flag(self):
        """Test bulk revoke with force flag to skip confirmation."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(['principal_name', 'permission_set_name', 'account_name'])
            writer.writerow(['test-user', 'ReadOnlyAccess', 'TestAccount'])
            csv_file = Path(f.name)
        
        try:
            # Mock the dependencies
            with patch('src.awsideman.commands.bulk.validate_profile') as mock_validate_profile, \
                 patch('src.awsideman.commands.bulk.validate_sso_instance') as mock_validate_sso, \
                 patch('src.awsideman.commands.bulk.AWSClientManager') as mock_client_manager, \
                 patch('src.awsideman.commands.bulk.console') as mock_console, \
                 patch('src.awsideman.commands.bulk.asyncio') as mock_asyncio:
                
                # Setup mocks
                mock_validate_profile.return_value = ('test-profile', {'sso_start_url': 'test'})
                mock_validate_sso.return_value = ('test-instance-arn', 'test-identity-store-id')
                
                # Mock the file processing and resolution
                with patch('src.awsideman.utils.bulk.processors.FileFormatDetector.get_processor') as mock_processor, \
                     patch('src.awsideman.utils.bulk.resolver.ResourceResolver') as mock_resolver, \
                     patch('src.awsideman.utils.bulk.preview.PreviewGenerator') as mock_preview, \
                     patch('src.awsideman.utils.bulk.batch.BatchProcessor') as mock_batch_processor, \
                     patch('src.awsideman.utils.bulk.reporting.ReportGenerator') as mock_report_generator:
                    
                    # Setup processor mock
                    mock_proc_instance = Mock()
                    mock_proc_instance.validate_format.return_value = []
                    mock_proc_instance.parse_assignments.return_value = [
                        {
                            'principal_name': 'test-user',
                            'permission_set_name': 'ReadOnlyAccess',
                            'account_name': 'TestAccount',
                            'principal_type': 'USER'
                        }
                    ]
                    mock_processor.return_value = mock_proc_instance
                    
                    # Setup resolver mock
                    mock_resolver_instance = Mock()
                    mock_resolver_instance.resolve_assignment.return_value = {
                        'principal_name': 'test-user',
                        'permission_set_name': 'ReadOnlyAccess',
                        'account_name': 'TestAccount',
                        'principal_type': 'USER',
                        'principal_id': 'test-user-id',
                        'permission_set_arn': 'test-ps-arn',
                        'account_id': '123456789012',
                        'resolution_success': True,
                        'resolution_errors': []
                    }
                    mock_resolver.return_value = mock_resolver_instance
                    
                    # Setup preview mock
                    mock_preview_instance = Mock()
                    mock_preview_instance.generate_preview_report.return_value = Mock(
                        total_assignments=1,
                        successful_resolutions=1,
                        failed_resolutions=0
                    )
                    mock_preview_instance.prompt_user_confirmation.return_value = True
                    mock_preview.return_value = mock_preview_instance
                    
                    # Setup batch processor mock
                    mock_batch_instance = Mock()
                    mock_results = BulkOperationResults(
                        total_processed=1,
                        operation_type='revoke'
                    )
                    mock_results.successful = [
                        AssignmentResult(
                            principal_name='test-user',
                            permission_set_name='ReadOnlyAccess',
                            account_name='TestAccount',
                            principal_type='USER',
                            status='success'
                        )
                    ]
                    mock_results.failed = []
                    mock_results.skipped = []
                    
                    mock_batch_instance.process_assignments.return_value = mock_results
                    mock_batch_processor.return_value = mock_batch_instance
                    mock_asyncio.run.return_value = mock_results
                    
                    # Setup report generator mock
                    mock_report_instance = Mock()
                    mock_report_generator.return_value = mock_report_instance
                    
                    # Test with force flag
                    with pytest.raises(SystemExit) as exc_info:
                        bulk_revoke(csv_file, dry_run=False, continue_on_error=True, batch_size=10, force=True, profile=None)
                    
                    # Verify successful completion
                    assert exc_info.value.code == 0
                    
                    # Verify force flag was passed to confirmation prompt
                    mock_preview_instance.prompt_user_confirmation.assert_called_once_with(
                        "revoke", 
                        mock_preview_instance.generate_preview_report.return_value,
                        force=True
                    )
                    
                    # Verify batch processing was called with revoke operation
                    mock_batch_instance.process_assignments.assert_called_once()
                    call_args = mock_batch_instance.process_assignments.call_args
                    assert call_args[1]['operation'] == 'revoke'
                    assert call_args[1]['dry_run'] is False
        
        finally:
            # Clean up temporary file
            csv_file.unlink()
    
    def test_bulk_revoke_file_not_found(self):
        """Test bulk revoke with non-existent file."""
        non_existent_file = Path('/tmp/non_existent_file.csv')
        
        with pytest.raises(SystemExit) as exc_info:
            bulk_revoke(non_existent_file, dry_run=False, continue_on_error=True, batch_size=10, force=False, profile=None)
        
        # Verify error exit code
        assert exc_info.value.code == 1
    
    def test_bulk_revoke_invalid_batch_size(self):
        """Test bulk revoke with invalid batch size."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(['principal_name', 'permission_set_name', 'account_name'])
            writer.writerow(['test-user', 'ReadOnlyAccess', 'TestAccount'])
            csv_file = Path(f.name)
        
        try:
            with pytest.raises(SystemExit) as exc_info:
                bulk_revoke(csv_file, dry_run=False, continue_on_error=True, batch_size=0, force=False, profile=None)
            
            # Verify error exit code
            assert exc_info.value.code == 1
        
        finally:
            # Clean up temporary file
            csv_file.unlink()