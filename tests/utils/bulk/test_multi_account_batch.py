"""Tests for multi-account batch processing components."""
import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from concurrent.futures import Future

from src.awsideman.utils.bulk.multi_account_batch import MultiAccountBatchProcessor
from src.awsideman.utils.models import AccountInfo, AccountResult, MultiAccountAssignment, MultiAccountResults
from src.awsideman.aws_clients.manager import AWSClientManager


@pytest.fixture
def mock_aws_client_manager():
    """Create a mock AWS client manager."""
    manager = Mock(spec=AWSClientManager)
    
    # Mock SSO Admin client
    sso_admin_client = Mock()
    sso_admin_client.list_account_assignments.return_value = {
        'AccountAssignments': []
    }
    sso_admin_client.create_account_assignment.return_value = {
        'AccountAssignmentCreationStatus': {
            'Status': 'SUCCEEDED',
            'RequestId': 'test-request-id'
        }
    }
    sso_admin_client.delete_account_assignment.return_value = {
        'AccountAssignmentDeletionStatus': {
            'Status': 'SUCCEEDED',
            'RequestId': 'test-request-id'
        }
    }
    
    # Mock Identity Store client
    identity_store_client = Mock()
    identity_store_client.list_users.return_value = {
        'Users': [{'UserId': 'test-user-id'}]
    }
    identity_store_client.list_groups.return_value = {
        'Groups': [{'GroupId': 'test-group-id'}]
    }
    
    # Mock Organizations client
    organizations_client = Mock()
    
    manager.get_identity_center_client.return_value = sso_admin_client
    manager.get_identity_store_client.return_value = identity_store_client
    manager.get_organizations_client.return_value = organizations_client
    
    return manager


@pytest.fixture
def sample_accounts():
    """Create sample account data for testing."""
    return [
        AccountInfo(
            account_id="123456789012",
            account_name="Test Account 1",
            email="test1@example.com",
            status="ACTIVE",
            tags={"Environment": "Dev", "Team": "Engineering"}
        ),
        AccountInfo(
            account_id="123456789013",
            account_name="Test Account 2", 
            email="test2@example.com",
            status="ACTIVE",
            tags={"Environment": "Prod", "Team": "Engineering"}
        ),
        AccountInfo(
            account_id="123456789014",
            account_name="Test Account 3",
            email="test3@example.com", 
            status="ACTIVE",
            tags={"Environment": "Dev", "Team": "Marketing"}
        )
    ]


@pytest.fixture
def multi_account_processor(mock_aws_client_manager):
    """Create a MultiAccountBatchProcessor instance for testing."""
    return MultiAccountBatchProcessor(mock_aws_client_manager, batch_size=5)


class TestMultiAccountBatchProcessor:
    """Test cases for MultiAccountBatchProcessor."""
    
    def test_initialization(self, multi_account_processor):
        """Test processor initialization."""
        assert multi_account_processor.batch_size == 5
        assert multi_account_processor.max_concurrent_accounts == 5
        assert multi_account_processor.rate_limit_delay == 0.1
        assert multi_account_processor.resource_resolver is None
        assert multi_account_processor.multi_account_results is None
    
    def test_set_resource_resolver(self, multi_account_processor):
        """Test setting up the resource resolver."""
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"
        identity_store_id = "d-1234567890"
        
        multi_account_processor.set_resource_resolver(instance_arn, identity_store_id)
        
        assert multi_account_processor.resource_resolver is not None
        assert multi_account_processor.resource_resolver.instance_arn == instance_arn
        assert multi_account_processor.resource_resolver.identity_store_id == identity_store_id
    
    def test_configure_rate_limiting(self, multi_account_processor):
        """Test rate limiting configuration."""
        # Test valid configuration
        multi_account_processor.configure_rate_limiting(0.5, 3)
        assert multi_account_processor.rate_limit_delay == 0.5
        assert multi_account_processor.max_concurrent_accounts == 3
        
        # Test boundary conditions
        multi_account_processor.configure_rate_limiting(-1.0, 0)
        assert multi_account_processor.rate_limit_delay == 0.0
        assert multi_account_processor.max_concurrent_accounts == 1
        
        # Test exceeding batch size
        multi_account_processor.configure_rate_limiting(0.1, 20)
        assert multi_account_processor.max_concurrent_accounts == 5  # Limited by batch_size
    
    @pytest.mark.asyncio
    async def test_process_multi_account_operation_validation_failure(
        self, multi_account_processor, sample_accounts
    ):
        """Test processing with validation failures."""
        # Test with empty permission set name
        result = await multi_account_processor.process_multi_account_operation(
            accounts=sample_accounts,
            permission_set_name="",  # Invalid empty name
            principal_name="test-user",
            principal_type="USER",
            operation="assign",
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            dry_run=False
        )
        
        assert isinstance(result, MultiAccountResults)
        assert result.total_accounts == 3
        assert len(result.failed_accounts) == 3
        assert len(result.successful_accounts) == 0
        assert len(result.skipped_accounts) == 0
        assert result.operation_type == "assign"
        
        # Check that all accounts failed with validation error
        for failed_account in result.failed_accounts:
            assert "Validation failed" in failed_account.error_message
            assert "Permission set name cannot be empty" in failed_account.error_message
    
    @pytest.mark.asyncio
    async def test_process_multi_account_operation_name_resolution_failure(
        self, multi_account_processor, sample_accounts
    ):
        """Test processing with name resolution failures."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890"
        )
        
        # Mock name resolution failure
        with patch.object(multi_account_processor, '_resolve_names') as mock_resolve:
            mock_resolve.side_effect = Exception("Permission set not found")
            
            result = await multi_account_processor.process_multi_account_operation(
                accounts=sample_accounts,
                permission_set_name="NonExistentPermissionSet",
                principal_name="test-user",
                principal_type="USER",
                operation="assign",
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                dry_run=False
            )
        
        assert isinstance(result, MultiAccountResults)
        assert result.total_accounts == 3
        assert len(result.failed_accounts) == 3
        assert len(result.successful_accounts) == 0
        assert len(result.skipped_accounts) == 0
        
        # Check that all accounts failed with name resolution error
        for failed_account in result.failed_accounts:
            assert "Name resolution failed" in failed_account.error_message
            assert "Permission set not found" in failed_account.error_message
    
    @pytest.mark.asyncio
    async def test_process_multi_account_operation_dry_run_success(
        self, multi_account_processor, sample_accounts
    ):
        """Test successful dry run processing."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890"
        )
        
        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            assignment.principal_id = "user-1234567890abcdef"
            return None
        
        with patch.object(multi_account_processor, '_resolve_names') as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names
            
            # Mock SSO client to return no existing assignments (so all would be created)
            mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()
            mock_sso_client.list_account_assignments.return_value = {"AccountAssignments": []}
            
            result = await multi_account_processor.process_multi_account_operation(
                accounts=sample_accounts,
                permission_set_name="TestPermissionSet",
                principal_name="test-user",
                principal_type="USER",
                operation="assign",
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                dry_run=True
            )
        
        assert isinstance(result, MultiAccountResults)
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 3
        assert len(result.failed_accounts) == 0
        assert len(result.skipped_accounts) == 0
        assert result.operation_type == "assign"
        assert result.success_rate == 100.0
        
        # Check that all accounts succeeded
        for successful_account in result.successful_accounts:
            assert successful_account.status == 'success'
            assert successful_account.account_id in ["123456789012", "123456789013", "123456789014"]
    
    @pytest.mark.asyncio
    async def test_process_multi_account_operation_mixed_results(
        self, multi_account_processor, sample_accounts
    ):
        """Test processing with mixed success/failure results."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890"
        )
        
        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            assignment.principal_id = "user-1234567890abcdef"
            return None
        
        with patch.object(multi_account_processor, '_resolve_names') as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names
            
            # Mock progress tracker to avoid Rich console conflicts
            with patch.object(multi_account_processor.progress_tracker, 'start_multi_account_progress'), \
                 patch.object(multi_account_processor.progress_tracker, 'stop_live_display'), \
                 patch.object(multi_account_processor.progress_tracker, 'display_final_summary'):
            
                # Mock account processing to simulate mixed results
                with patch.object(multi_account_processor, '_process_single_account_operation') as mock_process:
                    def side_effect(account, *args, **kwargs):
                        if account.account_id == "123456789012":
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status='success',
                                processing_time=0.5
                            )
                        elif account.account_id == "123456789013":
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status='failed',
                                error_message="Access denied",
                                processing_time=0.3
                            )
                        else:  # 123456789014
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status='skipped',
                                error_message="Account not eligible",
                                processing_time=0.1
                            )
                
                    mock_process.side_effect = side_effect
                    
                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False
                    )
        
        assert isinstance(result, MultiAccountResults)
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 1
        assert len(result.failed_accounts) == 1
        assert len(result.skipped_accounts) == 1
        assert result.operation_type == "assign"
        assert result.success_rate == pytest.approx(33.33, rel=1e-2)
        assert result.failure_rate == pytest.approx(33.33, rel=1e-2)
        assert result.skip_rate == pytest.approx(33.33, rel=1e-2)
        
        # Check specific results
        successful_account = result.successful_accounts[0]
        assert successful_account.account_id == "123456789012"
        assert successful_account.status == 'success'
        
        failed_account = result.failed_accounts[0]
        assert failed_account.account_id == "123456789013"
        assert failed_account.status == 'failed'
        assert failed_account.error_message == "Access denied"
        
        skipped_account = result.skipped_accounts[0]
        assert skipped_account.account_id == "123456789014"
        assert skipped_account.status == 'skipped'
        assert skipped_account.error_message == "Account not eligible"
    
    @pytest.mark.asyncio
    async def test_process_multi_account_operation_continue_on_error_false(
        self, multi_account_processor, sample_accounts
    ):
        """Test processing with continue_on_error=False."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef",
            "d-1234567890"
        )
        
        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            assignment.principal_id = "user-1234567890abcdef"
            return None
        
        with patch.object(multi_account_processor, '_resolve_names') as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names
            
            # Mock progress tracker to avoid Rich console conflicts
            with patch.object(multi_account_processor.progress_tracker, 'start_multi_account_progress'), \
                 patch.object(multi_account_processor.progress_tracker, 'stop_live_display'), \
                 patch.object(multi_account_processor.progress_tracker, 'display_final_summary'):
            
                # Mock account batch processing to simulate failure in first batch
                with patch.object(multi_account_processor, '_process_account_batch') as mock_batch:
                    mock_batch.return_value = {
                        'successful': [],
                        'failed': [AccountResult(
                            account_id="123456789012",
                            account_name="Test Account 1",
                            status='failed',
                            error_message="Critical error",
                            processing_time=0.5
                        )],
                        'skipped': []
                    }
                    
                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                        continue_on_error=False
                    )
        
        assert isinstance(result, MultiAccountResults)
        assert result.total_accounts == 3
        assert len(result.failed_accounts) == 1  # First account failed
        assert len(result.skipped_accounts) == 2  # Remaining accounts skipped
        assert len(result.successful_accounts) == 0
        
        # Check that remaining accounts were skipped
        for skipped_account in result.skipped_accounts:
            assert skipped_account.status == 'skipped'
            assert "Skipped due to previous failures" in skipped_account.error_message
    
    def test_process_single_account_operation_assign_success(
        self, multi_account_processor, sample_accounts
    ):
        """Test successful single account assign operation."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id"
        )
        
        # Mock successful assign operation
        with patch.object(multi_account_processor, '_execute_assign_operation') as mock_assign:
            mock_assign.return_value = {'retry_count': 0}
            
            result = multi_account_processor._process_single_account_operation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )
        
        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == 'success'
        assert result.error_message is None
        assert result.retry_count == 0
        assert result.processing_time > 0
    
    def test_process_single_account_operation_revoke_success(
        self, multi_account_processor, sample_accounts
    ):
        """Test successful single account revoke operation."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="revoke",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id"
        )
        
        # Mock successful revoke operation
        with patch.object(multi_account_processor, '_execute_revoke_operation') as mock_revoke:
            mock_revoke.return_value = {'retry_count': 1}
            
            result = multi_account_processor._process_single_account_operation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )
        
        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == 'success'
        assert result.error_message is None
        assert result.retry_count == 1
        assert result.processing_time > 0
    
    def test_process_single_account_operation_unresolved_assignment(
        self, multi_account_processor, sample_accounts
    ):
        """Test single account operation with unresolved assignment."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign"
            # Missing permission_set_arn and principal_id (not resolved)
        )
        
        result = multi_account_processor._process_single_account_operation(
            account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
        )
        
        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == 'failed'
        assert "Assignment not properly resolved" in result.error_message
    
    def test_process_single_account_operation_dry_run(
        self, multi_account_processor, sample_accounts
    ):
        """Test single account operation in dry run mode."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id"
        )
        
        # Mock SSO client to return no existing assignments
        mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()
        mock_sso_client.list_account_assignments.return_value = {"AccountAssignments": []}
        
        result = multi_account_processor._process_single_account_operation(
            account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", True
        )
        
        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == 'success'
        assert "create new assignment" in result.error_message.lower()
        assert result.processing_time > 0
    
    def test_process_single_account_operation_execution_failure(
        self, multi_account_processor, sample_accounts
    ):
        """Test single account operation with execution failure."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id"
        )
        
        # Mock execution failure
        with patch.object(multi_account_processor, '_execute_assign_operation') as mock_assign:
            mock_assign.side_effect = Exception("AWS API error")
            
            result = multi_account_processor._process_single_account_operation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )
        
        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == 'failed'
        assert result.error_message == "AWS API error"
        assert result.processing_time > 0
    
    def test_process_single_account_with_isolation_success(
        self, multi_account_processor, sample_accounts
    ):
        """Test single account processing with isolation wrapper."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id"
        )
        
        # Mock successful operation
        with patch.object(multi_account_processor, '_process_single_account_operation') as mock_process:
            expected_result = AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status='success',
                processing_time=0.5
            )
            mock_process.return_value = expected_result
            
            result = multi_account_processor._process_single_account_with_isolation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )
        
        assert result == expected_result
    
    def test_process_single_account_with_isolation_exception(
        self, multi_account_processor, sample_accounts
    ):
        """Test single account processing with isolation handling exceptions."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id"
        )
        
        # Mock exception in processing
        with patch.object(multi_account_processor, '_process_single_account_operation') as mock_process:
            mock_process.side_effect = Exception("Unexpected error")
            
            result = multi_account_processor._process_single_account_with_isolation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )
        
        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == 'failed'
        assert "Isolated processing error: Unexpected error" in result.error_message
    
    def test_get_multi_account_results(self, multi_account_processor):
        """Test getting multi-account results."""
        # Initially should be None
        assert multi_account_processor.get_multi_account_results() is None
        
        # Set some results
        test_results = MultiAccountResults(
            total_accounts=2,
            successful_accounts=[],
            failed_accounts=[],
            skipped_accounts=[],
            operation_type="assign",
            duration=1.5,
            batch_size=5
        )
        multi_account_processor.multi_account_results = test_results
        
        # Should return the set results
        assert multi_account_processor.get_multi_account_results() == test_results
    
    def test_reset_multi_account_results(self, multi_account_processor):
        """Test resetting multi-account results."""
        # Set some results
        test_results = MultiAccountResults(
            total_accounts=2,
            successful_accounts=[],
            failed_accounts=[],
            skipped_accounts=[],
            operation_type="assign",
            duration=1.5,
            batch_size=5
        )
        multi_account_processor.multi_account_results = test_results
        
        # Reset
        multi_account_processor.reset_multi_account_results()
        
        # Should be None again
        assert multi_account_processor.multi_account_results is None
        assert isinstance(multi_account_processor.progress_tracker, type(multi_account_processor.progress_tracker))


class TestMultiAccountAssignmentValidation:
    """Test cases for MultiAccountAssignment validation."""
    
    def test_valid_assignment(self, sample_accounts):
        """Test validation of a valid assignment."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign"
        )
        
        errors = assignment.validate()
        assert len(errors) == 0
    
    def test_empty_permission_set_name(self, sample_accounts):
        """Test validation with empty permission set name."""
        assignment = MultiAccountAssignment(
            permission_set_name="",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign"
        )
        
        errors = assignment.validate()
        assert len(errors) == 1
        assert "Permission set name cannot be empty" in errors[0]
    
    def test_empty_principal_name(self, sample_accounts):
        """Test validation with empty principal name."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign"
        )
        
        errors = assignment.validate()
        assert len(errors) == 1
        assert "Principal name cannot be empty" in errors[0]
    
    def test_invalid_principal_type(self, sample_accounts):
        """Test validation with invalid principal type."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="INVALID",
            accounts=sample_accounts,
            operation="assign"
        )
        
        errors = assignment.validate()
        assert len(errors) == 1
        assert "Invalid principal type: INVALID" in errors[0]
    
    def test_no_accounts(self):
        """Test validation with no accounts."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[],
            operation="assign"
        )
        
        errors = assignment.validate()
        assert len(errors) == 1
        assert "At least one account must be specified" in errors[0]
    
    def test_invalid_operation(self, sample_accounts):
        """Test validation with invalid operation."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="invalid"
        )
        
        errors = assignment.validate()
        assert len(errors) == 1
        assert "Invalid operation: invalid" in errors[0]
    
    def test_multiple_validation_errors(self):
        """Test validation with multiple errors."""
        assignment = MultiAccountAssignment(
            permission_set_name="",
            principal_name="",
            principal_type="INVALID",
            accounts=[],
            operation="invalid"
        )
        
        errors = assignment.validate()
        assert len(errors) == 5
        assert any("Permission set name cannot be empty" in error for error in errors)
        assert any("Principal name cannot be empty" in error for error in errors)
        assert any("Invalid principal type: INVALID" in error for error in errors)
        assert any("At least one account must be specified" in error for error in errors)
        assert any("Invalid operation: invalid" in error for error in errors)
    
    def test_is_resolved(self, sample_accounts):
        """Test checking if assignment is resolved."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign"
        )
        
        # Initially not resolved
        assert not assignment.is_resolved()
        
        # Set permission set ARN only
        assignment.permission_set_arn = "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        assert not assignment.is_resolved()
        
        # Set principal ID as well
        assignment.principal_id = "test-user-id"
        assert assignment.is_resolved()
    
    def test_get_total_operations(self, sample_accounts):
        """Test getting total operations count."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign"
        )
        
        assert assignment.get_total_operations() == 3  # 3 accounts
    
    def test_get_account_ids(self, sample_accounts):
        """Test getting account IDs."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign"
        )
        
        account_ids = assignment.get_account_ids()
        expected_ids = ["123456789012", "123456789013", "123456789014"]
        assert account_ids == expected_ids