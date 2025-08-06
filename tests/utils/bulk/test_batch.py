"""Tests for batch processing components.

This module contains unit tests for the batch processing functionality,
including BatchProcessor, ProgressTracker, and RetryHandler classes.
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError
from rich.console import Console

from src.awsideman.utils.bulk.batch import (
    BatchProcessor,
    ProgressTracker,
    RetryHandler,
    AssignmentResult,
    BulkOperationResults
)
from src.awsideman.aws_clients.manager import AWSClientManager


class TestAssignmentResult:
    """Test AssignmentResult dataclass."""
    
    def test_assignment_result_creation(self):
        """Test creating an AssignmentResult."""
        result = AssignmentResult(
            principal_name="john.doe",
            permission_set_name="ReadOnlyAccess",
            account_name="Production",
            principal_type="USER",
            status="success",
            principal_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-456",
            account_id="123456789012",
            processing_time=1.5,
            retry_count=1,
            row_number=2
        )
        
        assert result.principal_name == "john.doe"
        assert result.permission_set_name == "ReadOnlyAccess"
        assert result.account_name == "Production"
        assert result.principal_type == "USER"
        assert result.status == "success"
        assert result.principal_id == "user-123"
        assert result.permission_set_arn == "arn:aws:sso:::permissionSet/ins-123/ps-456"
        assert result.account_id == "123456789012"
        assert result.processing_time == 1.5
        assert result.retry_count == 1
        assert result.row_number == 2
    
    def test_assignment_result_defaults(self):
        """Test AssignmentResult with default values."""
        result = AssignmentResult(
            principal_name="jane.doe",
            permission_set_name="PowerUserAccess",
            account_name="Development",
            principal_type="USER",
            status="failed"
        )
        
        assert result.error_message is None
        assert result.principal_id is None
        assert result.permission_set_arn is None
        assert result.account_id is None
        assert result.processing_time == 0.0
        assert result.retry_count == 0
        assert result.row_number is None
        assert result.assignment_index is None


class TestBulkOperationResults:
    """Test BulkOperationResults dataclass."""
    
    def test_bulk_operation_results_creation(self):
        """Test creating BulkOperationResults."""
        successful_result = AssignmentResult(
            principal_name="john.doe",
            permission_set_name="ReadOnlyAccess",
            account_name="Production",
            principal_type="USER",
            status="success"
        )
        
        failed_result = AssignmentResult(
            principal_name="jane.doe",
            permission_set_name="PowerUserAccess",
            account_name="Development",
            principal_type="USER",
            status="failed",
            error_message="Permission set not found"
        )
        
        results = BulkOperationResults(
            total_processed=2,
            successful=[successful_result],
            failed=[failed_result],
            operation_type="assign",
            duration=5.0,
            batch_size=10,
            continue_on_error=True
        )
        
        assert results.total_processed == 2
        assert len(results.successful) == 1
        assert len(results.failed) == 1
        assert len(results.skipped) == 0
        assert results.operation_type == "assign"
        assert results.duration == 5.0
        assert results.batch_size == 10
        assert results.continue_on_error is True
    
    def test_bulk_operation_results_properties(self):
        """Test BulkOperationResults computed properties."""
        successful_result = AssignmentResult(
            principal_name="john.doe",
            permission_set_name="ReadOnlyAccess",
            account_name="Production",
            principal_type="USER",
            status="success"
        )
        
        failed_result = AssignmentResult(
            principal_name="jane.doe",
            permission_set_name="PowerUserAccess",
            account_name="Development",
            principal_type="USER",
            status="failed"
        )
        
        skipped_result = AssignmentResult(
            principal_name="bob.smith",
            permission_set_name="AdminAccess",
            account_name="Staging",
            principal_type="USER",
            status="skipped"
        )
        
        results = BulkOperationResults(
            total_processed=3,
            successful=[successful_result],
            failed=[failed_result],
            skipped=[skipped_result]
        )
        
        assert results.success_count == 1
        assert results.failure_count == 1
        assert results.skip_count == 1
        assert results.success_rate == pytest.approx(33.33, rel=1e-2)
    
    def test_bulk_operation_results_empty(self):
        """Test BulkOperationResults with no results."""
        results = BulkOperationResults(total_processed=0)
        
        assert results.success_count == 0
        assert results.failure_count == 0
        assert results.skip_count == 0
        assert results.success_rate == 0.0


class TestRetryHandler:
    """Test RetryHandler class."""
    
    def test_retry_handler_creation(self):
        """Test creating a RetryHandler."""
        handler = RetryHandler(max_retries=5, base_delay=2.0, max_delay=120.0)
        
        assert handler.max_retries == 5
        assert handler.base_delay == 2.0
        assert handler.max_delay == 120.0
    
    def test_retry_handler_defaults(self):
        """Test RetryHandler with default values."""
        handler = RetryHandler()
        
        assert handler.max_retries == 3
        assert handler.base_delay == 1.0
        assert handler.max_delay == 60.0
    
    def test_should_retry_client_errors(self):
        """Test should_retry with various ClientError codes."""
        handler = RetryHandler()
        
        # Retryable errors
        retryable_codes = [
            'Throttling',
            'ThrottlingException',
            'TooManyRequestsException',
            'ServiceUnavailable',
            'InternalServerError',
            'RequestTimeout',
            'RequestTimeoutException',
            'PriorRequestNotComplete'
        ]
        
        for code in retryable_codes:
            error = ClientError(
                error_response={'Error': {'Code': code, 'Message': 'Test error'}},
                operation_name='TestOperation'
            )
            assert handler.should_retry(error), f"Should retry {code}"
        
        # Non-retryable errors
        non_retryable_codes = [
            'ValidationException',
            'ResourceNotFoundException',
            'ConflictException',
            'AccessDeniedException'
        ]
        
        for code in non_retryable_codes:
            error = ClientError(
                error_response={'Error': {'Code': code, 'Message': 'Test error'}},
                operation_name='TestOperation'
            )
            assert not handler.should_retry(error), f"Should not retry {code}"
    
    def test_should_retry_network_errors(self):
        """Test should_retry with network errors."""
        handler = RetryHandler()
        
        # Retryable network errors
        assert handler.should_retry(ConnectionError("Connection failed"))
        assert handler.should_retry(TimeoutError("Request timed out"))
        
        # Test network error detection by string content
        class CustomError(Exception):
            pass
        
        assert handler.should_retry(CustomError("connection reset by peer"))
        assert handler.should_retry(CustomError("DNS resolution failed"))
        assert handler.should_retry(CustomError("SSL handshake failed"))
        assert handler.should_retry(CustomError("socket timeout"))
        assert handler.should_retry(CustomError("read timed out"))
        
        # Non-retryable errors
        assert not handler.should_retry(ValueError("Invalid value"))
        assert not handler.should_retry(KeyError("Missing key"))
        assert not handler.should_retry(CustomError("business logic error"))
    
    def test_calculate_delay(self):
        """Test delay calculation for exponential backoff."""
        handler = RetryHandler(base_delay=1.0, max_delay=10.0)
        
        # Test exponential backoff
        assert handler.calculate_delay(0) == 1.0  # 1.0 * 2^0
        assert handler.calculate_delay(1) == 2.0  # 1.0 * 2^1
        assert handler.calculate_delay(2) == 4.0  # 1.0 * 2^2
        assert handler.calculate_delay(3) == 8.0  # 1.0 * 2^3
        
        # Test max delay cap
        assert handler.calculate_delay(4) == 10.0  # Capped at max_delay
        assert handler.calculate_delay(10) == 10.0  # Capped at max_delay
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self):
        """Test successful execution without retries."""
        handler = RetryHandler()
        
        def successful_func():
            return "success"
        
        result = await handler.execute_with_retry(successful_func)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_eventual_success(self):
        """Test successful execution after retries."""
        handler = RetryHandler(max_retries=3, base_delay=0.01)  # Fast retries for testing
        
        call_count = 0
        
        def eventually_successful_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientError(
                    error_response={'Error': {'Code': 'Throttling', 'Message': 'Rate exceeded'}},
                    operation_name='TestOperation'
                )
            return "success"
        
        result = await handler.execute_with_retry(eventually_successful_func)
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_max_retries_exceeded(self):
        """Test failure after max retries exceeded."""
        handler = RetryHandler(max_retries=2, base_delay=0.01)  # Fast retries for testing
        
        def always_failing_func():
            raise ClientError(
                error_response={'Error': {'Code': 'Throttling', 'Message': 'Rate exceeded'}},
                operation_name='TestOperation'
            )
        
        with pytest.raises(ClientError):
            await handler.execute_with_retry(always_failing_func)
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_non_retryable_error(self):
        """Test immediate failure for non-retryable errors."""
        handler = RetryHandler()
        
        def non_retryable_error_func():
            raise ClientError(
                error_response={'Error': {'Code': 'ValidationException', 'Message': 'Invalid input'}},
                operation_name='TestOperation'
            )
        
        with pytest.raises(ClientError):
            await handler.execute_with_retry(non_retryable_error_func)


class TestProgressTracker:
    """Test ProgressTracker class."""
    
    def test_progress_tracker_creation(self):
        """Test creating a ProgressTracker."""
        console = Console()
        tracker = ProgressTracker(console)
        
        assert tracker.console == console
        assert tracker.progress is None
        assert tracker.task_id is None
        assert tracker.start_time is None
    
    @patch('src.awsideman.utils.bulk.batch.Progress')
    def test_start_progress(self, mock_progress_class):
        """Test starting progress tracking."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Mock the Progress instance
        mock_progress_instance = Mock()
        mock_progress_class.return_value = mock_progress_instance
        mock_progress_instance.add_task.return_value = "task-123"
        
        tracker.start_progress(100, "Test progress")
        
        # Verify Progress was created with correct parameters
        mock_progress_class.assert_called_once()
        
        # Verify progress was started and task was added
        mock_progress_instance.start.assert_called_once()
        mock_progress_instance.add_task.assert_called_once_with("Test progress", total=100, eta="calculating...")
        
        assert tracker.task_id == "task-123"
        assert tracker.start_time is not None
        assert tracker.total_items == 100
        assert tracker.completed_items == 0
    
    def test_update_progress(self):
        """Test updating progress."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Mock progress and task_id
        mock_progress = Mock()
        tracker.progress = mock_progress
        tracker.task_id = "task-123"
        tracker.total_items = 100
        tracker.completed_items = 0
        
        tracker.update_progress(5, "Updated description")
        
        # Check that update was called with advance, eta, and description
        assert mock_progress.update.call_count == 2
        # First call should include advance and eta
        first_call = mock_progress.update.call_args_list[0]
        assert first_call[0] == ("task-123",)
        assert first_call[1]["advance"] == 5
        assert "eta" in first_call[1]
        
        # Second call should include description
        second_call = mock_progress.update.call_args_list[1]
        assert second_call[0] == ("task-123",)
        assert second_call[1]["description"] == "Updated description"
        
        assert tracker.completed_items == 5
    
    def test_set_progress(self):
        """Test setting absolute progress."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Mock progress and task_id
        mock_progress = Mock()
        tracker.progress = mock_progress
        tracker.task_id = "task-123"
        tracker.total_items = 100
        tracker.completed_items = 0
        
        tracker.set_progress(50, "Half complete")
        
        # Check that update was called with completed, eta, and description
        assert mock_progress.update.call_count == 2
        # First call should include completed and eta
        first_call = mock_progress.update.call_args_list[0]
        assert first_call[0] == ("task-123",)
        assert first_call[1]["completed"] == 50
        assert "eta" in first_call[1]
        
        # Second call should include description
        second_call = mock_progress.update.call_args_list[1]
        assert second_call[0] == ("task-123",)
        assert second_call[1]["description"] == "Half complete"
        
        assert tracker.completed_items == 50
    
    def test_finish_progress(self):
        """Test finishing progress tracking."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Mock progress
        mock_progress = Mock()
        tracker.progress = mock_progress
        tracker.task_id = "task-123"
        
        tracker.finish_progress()
        
        mock_progress.stop.assert_called_once()
        assert tracker.progress is None
        assert tracker.task_id is None
    
    def test_get_elapsed_time(self):
        """Test getting elapsed time."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Test with no start time
        assert tracker.get_elapsed_time() == 0.0
        
        # Test with start time
        start_time = time.time()
        tracker.start_time = start_time
        
        # Sleep briefly to ensure elapsed time > 0
        time.sleep(0.01)
        elapsed = tracker.get_elapsed_time()
        assert elapsed > 0.0
        assert elapsed < 1.0  # Should be very small
    
    def test_calculate_eta(self):
        """Test ETA calculation."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Test with no start time
        assert tracker._calculate_eta() == "calculating..."
        
        # Test with start time but no completed items
        tracker.start_time = time.time()
        tracker.total_items = 100
        tracker.completed_items = 0
        assert tracker._calculate_eta() == "calculating..."
        
        # Test with completed items
        tracker.start_time = time.time() - 10  # 10 seconds ago
        tracker.completed_items = 50
        eta = tracker._calculate_eta()
        assert eta != "calculating..."
        assert "s" in eta or "m" in eta or "h" in eta
    
    def test_format_duration(self):
        """Test duration formatting."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Test seconds
        assert tracker._format_duration(30) == "30s"
        assert tracker._format_duration(59) == "59s"
        
        # Test minutes
        assert tracker._format_duration(60) == "1m 0s"
        assert tracker._format_duration(90) == "1m 30s"
        assert tracker._format_duration(3599) == "59m 59s"
        
        # Test hours
        assert tracker._format_duration(3600) == "1h 0m"
        assert tracker._format_duration(3660) == "1h 1m"
        assert tracker._format_duration(7200) == "2h 0m"
        
        # Test negative/complete
        assert tracker._format_duration(-1) == "complete"
        assert tracker._format_duration(0) == "0s"
    
    def test_get_progress_stats(self):
        """Test getting progress statistics."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Initialize tracker
        tracker.total_items = 100
        tracker.completed_items = 25
        tracker.start_time = time.time() - 10  # 10 seconds ago
        
        stats = tracker.get_progress_stats()
        
        assert stats['total_items'] == 100
        assert stats['completed_items'] == 25
        assert stats['remaining_items'] == 75
        assert stats['elapsed_time'] > 9  # Should be around 10 seconds
        assert stats['completion_percentage'] == 25.0
        assert stats['items_per_second'] > 0
        assert stats['estimated_remaining_time'] is not None
        assert stats['estimated_completion_time'] is not None
    
    def test_get_progress_stats_no_progress(self):
        """Test getting progress statistics with no progress."""
        console = Console()
        tracker = ProgressTracker(console)
        
        # Initialize tracker with no progress
        tracker.total_items = 100
        tracker.completed_items = 0
        tracker.start_time = time.time()
        
        stats = tracker.get_progress_stats()
        
        assert stats['total_items'] == 100
        assert stats['completed_items'] == 0
        assert stats['remaining_items'] == 100
        assert stats['completion_percentage'] == 0.0
        assert stats['items_per_second'] == 0
        assert stats['estimated_remaining_time'] is None
        assert stats['estimated_completion_time'] is None


class TestBatchProcessor:
    """Test BatchProcessor class."""
    
    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create a mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)
        
        # Mock SSO Admin client
        sso_admin_client = Mock()
        manager.get_identity_center_client.return_value = sso_admin_client
        
        # Mock Identity Store client
        identity_store_client = Mock()
        manager.get_identity_store_client.return_value = identity_store_client
        
        return manager
    
    def test_batch_processor_creation(self, mock_aws_client_manager):
        """Test creating a BatchProcessor."""
        processor = BatchProcessor(mock_aws_client_manager, batch_size=20)
        
        assert processor.aws_client_manager == mock_aws_client_manager
        assert processor.batch_size == 20
        assert processor.retry_handler is not None
        assert processor.results.total_processed == 0
        assert processor.results.batch_size == 20
    
    def test_batch_processor_defaults(self, mock_aws_client_manager):
        """Test BatchProcessor with default values."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        assert processor.batch_size == 10
        assert processor.results.batch_size == 10
    
    @pytest.mark.asyncio
    async def test_process_assignments_dry_run(self, mock_aws_client_manager):
        """Test processing assignments in dry run mode."""
        processor = BatchProcessor(mock_aws_client_manager, batch_size=2)
        
        assignments = [
            {
                'principal_name': 'john.doe',
                'permission_set_name': 'ReadOnlyAccess',
                'account_name': 'Production',
                'principal_type': 'USER',
                'principal_id': 'user-123',
                'permission_set_arn': 'arn:aws:sso:::permissionSet/ins-123/ps-456',
                'account_id': '123456789012',
                'resolution_success': True,
                'resolution_errors': []
            },
            {
                'principal_name': 'jane.doe',
                'permission_set_name': 'PowerUserAccess',
                'account_name': 'Development',
                'principal_type': 'USER',
                'principal_id': 'user-456',
                'permission_set_arn': 'arn:aws:sso:::permissionSet/ins-123/ps-789',
                'account_id': '123456789013',
                'resolution_success': True,
                'resolution_errors': []
            }
        ]
        
        results = await processor.process_assignments(
            assignments=assignments,
            operation='assign',
            instance_arn='arn:aws:sso:::instance/ins-123',
            dry_run=True,
            continue_on_error=True
        )
        
        assert results.total_processed == 2
        assert results.success_count == 2
        assert results.failure_count == 0
        assert results.skip_count == 0
        assert results.operation_type == 'assign'
        assert results.duration > 0
    
    @pytest.mark.asyncio
    async def test_process_assignments_resolution_failures(self, mock_aws_client_manager):
        """Test processing assignments with resolution failures."""
        processor = BatchProcessor(mock_aws_client_manager, batch_size=2)
        
        assignments = [
            {
                'principal_name': 'john.doe',
                'permission_set_name': 'ReadOnlyAccess',
                'account_name': 'Production',
                'principal_type': 'USER',
                'resolution_success': False,
                'resolution_errors': ['User not found', 'Permission set not found']
            },
            {
                'principal_name': 'jane.doe',
                'permission_set_name': 'PowerUserAccess',
                'account_name': 'Development',
                'principal_type': 'USER',
                'principal_id': 'user-456',
                'permission_set_arn': 'arn:aws:sso:::permissionSet/ins-123/ps-789',
                'account_id': '123456789013',
                'resolution_success': True,
                'resolution_errors': []
            }
        ]
        
        results = await processor.process_assignments(
            assignments=assignments,
            operation='assign',
            instance_arn='arn:aws:sso:::instance/ins-123',
            dry_run=True,
            continue_on_error=True
        )
        
        assert results.total_processed == 2
        assert results.success_count == 1
        assert results.failure_count == 1
        assert results.skip_count == 0
        
        # Check the failed result
        failed_result = results.failed[0]
        assert failed_result.principal_name == 'john.doe'
        assert failed_result.status == 'failed'
        assert 'Resolution failed' in failed_result.error_message
    
    def test_process_single_assignment_missing_fields(self, mock_aws_client_manager):
        """Test processing assignment with missing resolved fields."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        assignment = {
            'principal_name': 'john.doe',
            'permission_set_name': 'ReadOnlyAccess',
            'account_name': 'Production',
            'principal_type': 'USER',
            'resolution_success': True,
            'resolution_errors': [],
            # Missing principal_id, permission_set_arn, account_id
        }
        
        result = processor._process_single_assignment(
            assignment=assignment,
            operation='assign',
            instance_arn='arn:aws:sso:::instance/ins-123',
            dry_run=False
        )
        
        assert result.status == 'failed'
        assert 'Missing resolved fields' in result.error_message
        assert 'principal_id' in result.error_message
        assert 'permission_set_arn' in result.error_message
        assert 'account_id' in result.error_message
    
    def test_execute_assign_operation_success(self, mock_aws_client_manager):
        """Test successful assign operation."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        # Mock the SSO admin client response
        mock_response = {'AccountAssignmentCreationStatus': {'Status': 'SUCCEEDED'}}
        processor.sso_admin_client.create_account_assignment.return_value = mock_response
        
        result = processor._execute_assign_operation(
            principal_id='user-123',
            permission_set_arn='arn:aws:sso:::permissionSet/ins-123/ps-456',
            account_id='123456789012',
            principal_type='USER',
            instance_arn='arn:aws:sso:::instance/ins-123'
        )
        
        assert result['status'] == 'success'
        assert result['retry_count'] == 0
        assert 'response' in result
        
        processor.sso_admin_client.create_account_assignment.assert_called_once_with(
            InstanceArn='arn:aws:sso:::instance/ins-123',
            TargetId='123456789012',
            TargetType='AWS_ACCOUNT',
            PermissionSetArn='arn:aws:sso:::permissionSet/ins-123/ps-456',
            PrincipalType='USER',
            PrincipalId='user-123'
        )
    
    def test_execute_assign_operation_conflict(self, mock_aws_client_manager):
        """Test assign operation with conflict (assignment already exists)."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        # Mock the SSO admin client to raise ConflictException
        conflict_error = ClientError(
            error_response={'Error': {'Code': 'ConflictException', 'Message': 'Assignment already exists'}},
            operation_name='CreateAccountAssignment'
        )
        processor.sso_admin_client.create_account_assignment.side_effect = conflict_error
        
        result = processor._execute_assign_operation(
            principal_id='user-123',
            permission_set_arn='arn:aws:sso:::permissionSet/ins-123/ps-456',
            account_id='123456789012',
            principal_type='USER',
            instance_arn='arn:aws:sso:::instance/ins-123'
        )
        
        assert result['status'] == 'success'
        assert 'response' in result
    
    def test_execute_revoke_operation_success(self, mock_aws_client_manager):
        """Test successful revoke operation."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        # Mock the SSO admin client response
        mock_response = {'AccountAssignmentDeletionStatus': {'Status': 'SUCCEEDED'}}
        processor.sso_admin_client.delete_account_assignment.return_value = mock_response
        
        result = processor._execute_revoke_operation(
            principal_id='user-123',
            permission_set_arn='arn:aws:sso:::permissionSet/ins-123/ps-456',
            account_id='123456789012',
            principal_type='USER',
            instance_arn='arn:aws:sso:::instance/ins-123'
        )
        
        assert result['status'] == 'success'
        assert result['retry_count'] == 0
        assert 'response' in result
        
        processor.sso_admin_client.delete_account_assignment.assert_called_once_with(
            InstanceArn='arn:aws:sso:::instance/ins-123',
            TargetId='123456789012',
            TargetType='AWS_ACCOUNT',
            PermissionSetArn='arn:aws:sso:::permissionSet/ins-123/ps-456',
            PrincipalType='USER',
            PrincipalId='user-123'
        )
    
    def test_execute_revoke_operation_not_found(self, mock_aws_client_manager):
        """Test revoke operation with not found (assignment doesn't exist)."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        # Mock the SSO admin client to raise ResourceNotFoundException
        not_found_error = ClientError(
            error_response={'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Assignment not found'}},
            operation_name='DeleteAccountAssignment'
        )
        processor.sso_admin_client.delete_account_assignment.side_effect = not_found_error
        
        result = processor._execute_revoke_operation(
            principal_id='user-123',
            permission_set_arn='arn:aws:sso:::permissionSet/ins-123/ps-456',
            account_id='123456789012',
            principal_type='USER',
            instance_arn='arn:aws:sso:::instance/ins-123'
        )
        
        assert result['status'] == 'success'
        assert 'response' in result
    
    def test_create_error_result(self, mock_aws_client_manager):
        """Test creating an error result."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        assignment = {
            'principal_name': 'john.doe',
            'permission_set_name': 'ReadOnlyAccess',
            'account_name': 'Production',
            'principal_type': 'USER',
            'principal_id': 'user-123',
            'permission_set_arn': 'arn:aws:sso:::permissionSet/ins-123/ps-456',
            'account_id': '123456789012',
            '_row_number': 5
        }
        
        result = processor._create_error_result(assignment, "Test error message")
        
        assert result.principal_name == 'john.doe'
        assert result.permission_set_name == 'ReadOnlyAccess'
        assert result.account_name == 'Production'
        assert result.principal_type == 'USER'
        assert result.principal_id == 'user-123'
        assert result.permission_set_arn == 'arn:aws:sso:::permissionSet/ins-123/ps-456'
        assert result.account_id == '123456789012'
        assert result.status == 'failed'
        assert result.error_message == 'Test error message'
        assert result.row_number == 5
    
    def test_get_results(self, mock_aws_client_manager):
        """Test getting current results."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        # Initially empty results
        results = processor.get_results()
        assert results.total_processed == 0
        assert results.success_count == 0
        assert results.failure_count == 0
        assert results.skip_count == 0
    
    def test_reset_results(self, mock_aws_client_manager):
        """Test resetting results."""
        processor = BatchProcessor(mock_aws_client_manager, batch_size=20)
        
        # Modify results
        processor.results.total_processed = 10
        processor.results.successful.append(
            AssignmentResult(
                principal_name="test",
                permission_set_name="test",
                account_name="test",
                principal_type="USER",
                status="success"
            )
        )
        
        # Reset results
        processor.reset_results()
        
        results = processor.get_results()
        assert results.total_processed == 0
        assert results.success_count == 0
        assert results.failure_count == 0
        assert results.skip_count == 0
        assert results.batch_size == 20  # Should preserve batch_size
    
    def test_format_aws_error(self, mock_aws_client_manager):
        """Test AWS error formatting."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        # Test AccessDeniedException
        access_denied_error = ClientError(
            error_response={'Error': {'Code': 'AccessDeniedException', 'Message': 'Access denied'}},
            operation_name='CreateAccountAssignment'
        )
        formatted = processor._format_aws_error(access_denied_error, 'assign')
        assert 'Access denied for assign operation' in formatted
        assert 'AWS permissions' in formatted
        
        # Test ValidationException
        validation_error = ClientError(
            error_response={'Error': {'Code': 'ValidationException', 'Message': 'Invalid input'}},
            operation_name='CreateAccountAssignment'
        )
        formatted = processor._format_aws_error(validation_error, 'assign')
        assert 'Invalid request for assign operation' in formatted
        assert 'Invalid input' in formatted
        
        # Test ThrottlingException
        throttling_error = ClientError(
            error_response={'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            operation_name='CreateAccountAssignment'
        )
        formatted = processor._format_aws_error(throttling_error, 'assign')
        assert 'Rate limit exceeded' in formatted
        assert 'retry automatically' in formatted
        
        # Test network error
        network_error = ConnectionError("Connection failed")
        formatted = processor._format_aws_error(network_error, 'assign')
        assert 'Network error during assign operation' in formatted
        assert 'retry automatically' in formatted
        
        # Test generic error
        generic_error = ValueError("Some error")
        formatted = processor._format_aws_error(generic_error, 'assign')
        assert 'Error during assign operation' in formatted
        assert 'Some error' in formatted
    
    def test_process_single_assignment_with_isolation(self, mock_aws_client_manager):
        """Test isolated assignment processing."""
        processor = BatchProcessor(mock_aws_client_manager)
        
        assignment = {
            'principal_name': 'john.doe',
            'permission_set_name': 'ReadOnlyAccess',
            'account_name': 'Production',
            'principal_type': 'USER',
            'principal_id': 'user-123',
            'permission_set_arn': 'arn:aws:sso:::permissionSet/ins-123/ps-456',
            'account_id': '123456789012',
            'resolution_success': True,
            'resolution_errors': []
        }
        
        # Mock successful response
        mock_response = {'AccountAssignmentCreationStatus': {'Status': 'SUCCEEDED'}}
        processor.sso_admin_client.create_account_assignment.return_value = mock_response
        
        result = processor._process_single_assignment_with_isolation(
            assignment=assignment,
            operation='assign',
            instance_arn='arn:aws:sso:::instance/ins-123',
            dry_run=False
        )
        
        assert result.status == 'success'
        assert result.principal_name == 'john.doe'
        assert result.permission_set_name == 'ReadOnlyAccess'
        assert result.account_name == 'Production'


if __name__ == '__main__':
    pytest.main([__file__])