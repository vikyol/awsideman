"""Tests for multi-account batch processing components."""
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.utils.bulk.multi_account_batch import MultiAccountBatchProcessor
from src.awsideman.utils.models import (
    AccountInfo,
    AccountResult,
    MultiAccountAssignment,
    MultiAccountResults,
)


@pytest.fixture
def mock_aws_client_manager():
    """Create a mock AWS client manager."""
    manager = Mock(spec=AWSClientManager)

    # Mock SSO Admin client
    sso_admin_client = Mock()
    sso_admin_client.list_account_assignments.return_value = {"AccountAssignments": []}
    sso_admin_client.create_account_assignment.return_value = {
        "AccountAssignmentCreationStatus": {"Status": "SUCCEEDED", "RequestId": "test-request-id"}
    }
    sso_admin_client.delete_account_assignment.return_value = {
        "AccountAssignmentDeletionStatus": {"Status": "SUCCEEDED", "RequestId": "test-request-id"}
    }

    # Mock Identity Store client
    identity_store_client = Mock()
    identity_store_client.list_users.return_value = {"Users": [{"UserId": "test-user-id"}]}
    identity_store_client.list_groups.return_value = {"Groups": [{"GroupId": "test-group-id"}]}

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
            tags={"Environment": "Dev", "Team": "Engineering"},
        ),
        AccountInfo(
            account_id="123456789013",
            account_name="Test Account 2",
            email="test2@example.com",
            status="ACTIVE",
            tags={"Environment": "Prod", "Team": "Engineering"},
        ),
        AccountInfo(
            account_id="123456789014",
            account_name="Test Account 3",
            email="test3@example.com",
            status="ACTIVE",
            tags={"Environment": "Dev", "Team": "Marketing"},
        ),
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
            dry_run=False,
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
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock name resolution failure
        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = Exception("Permission set not found")

            result = await multi_account_processor.process_multi_account_operation(
                accounts=sample_accounts,
                permission_set_name="NonExistentPermissionSet",
                principal_name="test-user",
                principal_type="USER",
                operation="assign",
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                dry_run=False,
            )

        assert isinstance(result, MultiAccountResults)
        assert result.total_accounts == 3
        assert len(result.failed_accounts) == 3
        assert len(result.successful_accounts) == 0
        assert len(result.skipped_accounts) == 0

        # Check that all accounts failed with name resolution error
        for failed_account in result.failed_accounts:
            assert "Failed to resolve resource" in failed_account.error_message
            assert "Permission set not found" in failed_account.error_message

    @pytest.mark.asyncio
    async def test_process_multi_account_operation_dry_run_success(
        self, multi_account_processor, sample_accounts
    ):
        """Test successful dry run processing."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock SSO client to return no existing assignments (so all would be created)
            mock_sso_client = (
                multi_account_processor.aws_client_manager.get_identity_center_client()
            )
            mock_sso_client.list_account_assignments.return_value = {"AccountAssignments": []}

            result = await multi_account_processor.process_multi_account_operation(
                accounts=sample_accounts,
                permission_set_name="TestPermissionSet",
                principal_name="test-user",
                principal_type="USER",
                operation="assign",
                instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                dry_run=True,
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
            assert successful_account.status == "success"
            assert successful_account.account_id in ["123456789012", "123456789013", "123456789014"]

    @pytest.mark.asyncio
    async def test_process_multi_account_operation_mixed_results(
        self, multi_account_processor, sample_accounts
    ):
        """Test processing with mixed success/failure results."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker to avoid Rich console conflicts
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock account processing to simulate mixed results
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def side_effect(account, *args, **kwargs):
                        if account.account_id == "123456789012":
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="success",
                                processing_time=0.5,
                            )
                        elif account.account_id == "123456789013":
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="failed",
                                error_message="Access denied",
                                processing_time=0.3,
                            )
                        else:  # 123456789014
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="skipped",
                                error_message="Account not eligible",
                                processing_time=0.1,
                            )

                    mock_process.side_effect = side_effect

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
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
        assert successful_account.status == "success"

        failed_account = result.failed_accounts[0]
        assert failed_account.account_id == "123456789013"
        assert failed_account.status == "failed"
        assert failed_account.error_message == "Access denied"

        skipped_account = result.skipped_accounts[0]
        assert skipped_account.account_id == "123456789014"
        assert skipped_account.status == "skipped"
        assert skipped_account.error_message == "Account not eligible"

    @pytest.mark.asyncio
    async def test_process_multi_account_operation_continue_on_error_false(
        self, multi_account_processor, sample_accounts
    ):
        """Test processing with continue_on_error=False."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker to avoid Rich console conflicts
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock account batch processing to simulate failure in first batch
                with patch.object(multi_account_processor, "_process_account_batch") as mock_batch:
                    mock_batch.return_value = {
                        "successful": [],
                        "failed": [
                            AccountResult(
                                account_id="123456789012",
                                account_name="Test Account 1",
                                status="failed",
                                error_message="Critical error",
                                processing_time=0.5,
                            )
                        ],
                        "skipped": [],
                    }

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                        continue_on_error=False,
                    )

        assert isinstance(result, MultiAccountResults)
        # With continue_on_error=False, processing stops after first batch failure
        # The total_accounts reflects only the accounts that were processed
        assert len(result.failed_accounts) == 1  # First account failed
        assert len(result.successful_accounts) == 0

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
            principal_id="test-user-id",
        )

        # Mock successful assign operation
        with patch.object(multi_account_processor, "_execute_assign_operation") as mock_assign:
            mock_assign.return_value = {"retry_count": 0}

            result = multi_account_processor._process_single_account_operation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )

        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == "success"
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
            principal_id="test-user-id",
        )

        # Mock successful revoke operation
        with patch.object(multi_account_processor, "_execute_revoke_operation") as mock_revoke:
            mock_revoke.return_value = {"retry_count": 1}

            result = multi_account_processor._process_single_account_operation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )

        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == "success"
        assert result.error_message is None
        assert result.retry_count == 0  # Retry count is tracked internally, not from return value
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
        assert result.status == "failed"
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
            principal_id="test-user-id",
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
        assert result.status == "success"
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
            principal_id="test-user-id",
        )

        # Mock execution failure
        with patch.object(multi_account_processor, "_execute_assign_operation") as mock_assign:
            mock_assign.side_effect = Exception("AWS API error")

            result = multi_account_processor._process_single_account_operation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )

        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == "failed"
        assert "AWS API error" in result.error_message  # Error message now includes context
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
            principal_id="test-user-id",
        )

        # Mock successful operation
        with patch.object(
            multi_account_processor, "_process_single_account_operation"
        ) as mock_process:
            expected_result = AccountResult(
                account_id=account.account_id,
                account_name=account.account_name,
                status="success",
                processing_time=0.5,
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
            principal_id="test-user-id",
        )

        # Mock exception in processing
        with patch.object(
            multi_account_processor, "_process_single_account_operation"
        ) as mock_process:
            mock_process.side_effect = Exception("Unexpected error")

            result = multi_account_processor._process_single_account_with_isolation(
                account, multi_assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", False
            )

        assert isinstance(result, AccountResult)
        assert result.account_id == account.account_id
        assert result.account_name == account.account_name
        assert result.status == "failed"
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
            batch_size=5,
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
            batch_size=5,
        )
        multi_account_processor.multi_account_results = test_results

        # Reset
        multi_account_processor.reset_multi_account_results()

        # Should be None again
        assert multi_account_processor.multi_account_results is None
        assert isinstance(
            multi_account_processor.progress_tracker, type(multi_account_processor.progress_tracker)
        )


class TestMultiAccountBatchProcessingSuccess:
    """Test cases for successful multi-account batch processing scenarios."""

    @pytest.mark.asyncio
    async def test_successful_multi_account_assign_all_accounts(
        self, multi_account_processor, sample_accounts
    ):
        """Test successful assignment across all accounts."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker to avoid Rich console conflicts
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock successful account processing
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def success_side_effect(account, *args, **kwargs):
                        return AccountResult(
                            account_id=account.account_id,
                            account_name=account.account_name,
                            status="success",
                            processing_time=0.5,
                            retry_count=0,
                        )

                    mock_process.side_effect = success_side_effect

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                    )

        # Verify all accounts succeeded
        assert isinstance(result, MultiAccountResults)
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 3
        assert len(result.failed_accounts) == 0
        assert len(result.skipped_accounts) == 0
        assert result.operation_type == "assign"
        assert result.success_rate == 100.0
        assert result.is_complete_success()

        # Verify each account result
        expected_account_ids = {acc.account_id for acc in sample_accounts}
        actual_account_ids = {acc.account_id for acc in result.successful_accounts}
        assert actual_account_ids == expected_account_ids

        for successful_account in result.successful_accounts:
            assert successful_account.status == "success"
            assert successful_account.processing_time == 0.5
            assert successful_account.retry_count == 0

    @pytest.mark.asyncio
    async def test_successful_multi_account_revoke_all_accounts(
        self, multi_account_processor, sample_accounts
    ):
        """Test successful revocation across all accounts."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock successful revoke operations with varying processing times
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def revoke_side_effect(account, *args, **kwargs):
                        processing_times = {
                            "123456789012": 0.3,
                            "123456789013": 0.7,
                            "123456789014": 0.5,
                        }
                        return AccountResult(
                            account_id=account.account_id,
                            account_name=account.account_name,
                            status="success",
                            processing_time=processing_times.get(account.account_id, 0.5),
                            retry_count=0,
                        )

                    mock_process.side_effect = revoke_side_effect

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="revoke",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                    )

        # Verify all accounts succeeded
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 3
        assert len(result.failed_accounts) == 0
        assert len(result.skipped_accounts) == 0
        assert result.operation_type == "revoke"
        assert result.success_rate == 100.0

        # Verify processing times are preserved
        processing_times = {
            acc.account_id: acc.processing_time for acc in result.successful_accounts
        }
        assert processing_times["123456789012"] == 0.3
        assert processing_times["123456789013"] == 0.7
        assert processing_times["123456789014"] == 0.5

    @pytest.mark.asyncio
    async def test_successful_batch_processing_with_custom_batch_size(
        self, mock_aws_client_manager, sample_accounts
    ):
        """Test successful processing with custom batch size."""
        # Create processor with smaller batch size
        processor = MultiAccountBatchProcessor(mock_aws_client_manager, batch_size=2)
        processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker
            with patch.object(
                processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(processor.progress_tracker, "stop_live_display"), patch.object(
                processor.progress_tracker, "display_final_summary"
            ):
                # Track batch processing calls
                batch_call_count = 0
                _original_process_batch = processor._process_account_batch

                async def mock_process_batch(batch_accounts, *args, **kwargs):
                    nonlocal batch_call_count
                    batch_call_count += 1

                    # Simulate successful processing for each account in batch
                    successful = []
                    for account in batch_accounts:
                        successful.append(
                            AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="success",
                                processing_time=0.4,
                                retry_count=0,
                            )
                        )

                    return {"successful": successful, "failed": [], "skipped": []}

                with patch.object(processor, "_process_account_batch") as mock_batch:
                    mock_batch.side_effect = mock_process_batch

                    result = await processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                    )

        # Verify batch processing occurred correctly
        # With 3 accounts and batch_size=2, should have 2 batch calls (2 accounts + 1 account)
        assert mock_batch.call_count == 2

        # Verify all accounts succeeded
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 3
        assert len(result.failed_accounts) == 0
        assert result.success_rate == 100.0
        assert result.batch_size == 2

    @pytest.mark.asyncio
    async def test_successful_processing_with_progress_callback(
        self, multi_account_processor, sample_accounts
    ):
        """Test successful processing with progress callback."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Track progress callback calls
        progress_calls = []

        def progress_callback(processed, total):
            progress_calls.append((processed, total))

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock successful account processing
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def success_side_effect(account, *args, **kwargs):
                        return AccountResult(
                            account_id=account.account_id,
                            account_name=account.account_name,
                            status="success",
                            processing_time=0.2,
                            retry_count=0,
                        )

                    mock_process.side_effect = success_side_effect

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                        progress_callback=progress_callback,
                    )

        # Verify progress callback was called correctly
        # Should be called once after processing all accounts in the batch
        assert len(progress_calls) == 1
        assert progress_calls[0] == (3, 3)  # All 3 accounts processed

        # Verify successful processing
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 3
        assert result.success_rate == 100.0


class TestMultiAccountErrorIsolation:
    """Test cases for error isolation between accounts during processing."""

    @pytest.mark.asyncio
    async def test_error_isolation_single_account_failure(
        self, multi_account_processor, sample_accounts
    ):
        """Test that failure in one account doesn't affect others."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock mixed results - second account fails, others succeed
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def mixed_side_effect(account, *args, **kwargs):
                        if account.account_id == "123456789013":  # Second account fails
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="failed",
                                error_message="Access denied for this account",
                                processing_time=0.8,
                                retry_count=3,
                            )
                        else:  # Other accounts succeed
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="success",
                                processing_time=0.5,
                                retry_count=0,
                            )

                    mock_process.side_effect = mixed_side_effect

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                        continue_on_error=True,
                    )

        # Verify error isolation - only one account failed, others succeeded
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 2
        assert len(result.failed_accounts) == 1
        assert len(result.skipped_accounts) == 0
        assert result.success_rate == pytest.approx(66.67, rel=1e-2)
        assert result.failure_rate == pytest.approx(33.33, rel=1e-2)

        # Verify failed account details
        failed_account = result.failed_accounts[0]
        assert failed_account.account_id == "123456789013"
        assert failed_account.status == "failed"
        assert failed_account.error_message == "Access denied for this account"
        assert failed_account.retry_count == 3

        # Verify successful accounts
        successful_ids = [acc.account_id for acc in result.successful_accounts]
        assert "123456789012" in successful_ids
        assert "123456789014" in successful_ids
        assert all(acc.status == "success" for acc in result.successful_accounts)

    @pytest.mark.asyncio
    async def test_error_isolation_multiple_account_failures(
        self, multi_account_processor, sample_accounts
    ):
        """Test error isolation with multiple account failures."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock results - first and third accounts fail, second succeeds
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def failure_side_effect(account, *args, **kwargs):
                        if account.account_id in [
                            "123456789012",
                            "123456789014",
                        ]:  # First and third fail
                            error_messages = {
                                "123456789012": "Permission set not found in account",
                                "123456789014": "Rate limit exceeded",
                            }
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="failed",
                                error_message=error_messages[account.account_id],
                                processing_time=1.2,
                                retry_count=2,
                            )
                        else:  # Second account succeeds
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="success",
                                processing_time=0.6,
                                retry_count=0,
                            )

                    mock_process.side_effect = failure_side_effect

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                        continue_on_error=True,
                    )

        # Verify error isolation with multiple failures
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 1
        assert len(result.failed_accounts) == 2
        assert len(result.skipped_accounts) == 0
        assert result.success_rate == pytest.approx(33.33, rel=1e-2)
        assert result.failure_rate == pytest.approx(66.67, rel=1e-2)

        # Verify successful account
        successful_account = result.successful_accounts[0]
        assert successful_account.account_id == "123456789013"
        assert successful_account.status == "success"
        assert successful_account.processing_time == 0.6

        # Verify failed accounts have different error messages
        failed_ids_to_errors = {acc.account_id: acc.error_message for acc in result.failed_accounts}
        assert failed_ids_to_errors["123456789012"] == "Permission set not found in account"
        assert failed_ids_to_errors["123456789014"] == "Rate limit exceeded"

        # Verify all failed accounts have retry counts
        assert all(acc.retry_count == 2 for acc in result.failed_accounts)

    @pytest.mark.asyncio
    async def test_error_isolation_with_exceptions_in_processing(
        self, multi_account_processor, sample_accounts
    ):
        """Test error isolation when exceptions are thrown during processing."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                # Mock processing with exceptions for some accounts
                with patch.object(
                    multi_account_processor, "_process_single_account_with_isolation"
                ) as mock_process:

                    def exception_side_effect(account, *args, **kwargs):
                        if account.account_id == "123456789012":  # First account throws exception
                            # This should be caught by isolation wrapper
                            raise Exception("Unexpected network error")
                        elif account.account_id == "123456789013":  # Second account succeeds
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="success",
                                processing_time=0.4,
                                retry_count=0,
                            )
                        else:  # Third account fails normally
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="failed",
                                error_message="Normal failure",
                                processing_time=0.7,
                                retry_count=1,
                            )

                    mock_process.side_effect = exception_side_effect

                    result = await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                        continue_on_error=True,
                    )

        # Verify that exception was isolated and didn't stop processing
        assert result.total_accounts == 3
        assert len(result.successful_accounts) == 1
        assert len(result.failed_accounts) == 2  # One from exception, one from normal failure
        assert len(result.skipped_accounts) == 0

        # Verify successful account processed normally
        successful_account = result.successful_accounts[0]
        assert successful_account.account_id == "123456789013"
        assert successful_account.status == "success"

        # Verify both failed accounts are present with different error types
        failed_ids = [acc.account_id for acc in result.failed_accounts]
        assert "123456789012" in failed_ids  # Exception case
        assert "123456789014" in failed_ids  # Normal failure case

    def test_isolation_wrapper_catches_all_exceptions(
        self, multi_account_processor, sample_accounts
    ):
        """Test that the isolation wrapper catches all types of exceptions."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id",
        )

        # Test different types of exceptions
        exception_types = [
            ValueError("Invalid value"),
            RuntimeError("Runtime error"),
            KeyError("Missing key"),
            AttributeError("Missing attribute"),
            Exception("Generic exception"),
        ]

        for exception in exception_types:
            with patch.object(
                multi_account_processor, "_process_single_account_operation"
            ) as mock_process:
                mock_process.side_effect = exception

                result = multi_account_processor._process_single_account_with_isolation(
                    account,
                    multi_assignment,
                    "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    False,
                )

                # Verify exception was caught and converted to failed result
                assert isinstance(result, AccountResult)
                assert result.account_id == account.account_id
                assert result.status == "failed"
                assert f"Isolated processing error: {str(exception)}" in result.error_message
                assert result.processing_time == 0.0


class TestMultiAccountProgressTracking:
    """Test cases for progress tracking accuracy across multiple accounts."""

    @pytest.mark.asyncio
    async def test_progress_tracking_accuracy_all_success(
        self, multi_account_processor, sample_accounts
    ):
        """Test progress tracking accuracy with all successful operations."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Track progress tracker calls
        progress_calls = []  # noqa: F841
        result_calls = []

        def mock_record_result(
            account_id, status, account_name=None, error=None, processing_time=0.0, retry_count=0
        ):
            result_calls.append(
                {
                    "account_id": account_id,
                    "status": status,
                    "account_name": account_name,
                    "error": error,
                    "processing_time": processing_time,
                    "retry_count": retry_count,
                }
            )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker methods
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ) as mock_start, patch.object(
                multi_account_processor.progress_tracker, "record_account_result"
            ) as mock_record, patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                mock_record.side_effect = mock_record_result

                # Mock successful account processing
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def success_side_effect(account, *args, **kwargs):
                        return AccountResult(
                            account_id=account.account_id,
                            account_name=account.account_name,
                            status="success",
                            processing_time=0.6,
                            retry_count=0,
                        )

                    mock_process.side_effect = success_side_effect

                    await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                    )

        # Verify progress tracking was started correctly
        mock_start.assert_called_once_with(
            total_accounts=3, operation_type="assign", show_live_results=False
        )

        # Verify all account results were recorded
        assert len(result_calls) == 3

        # Verify each account result was recorded with correct details
        expected_account_ids = ["123456789012", "123456789013", "123456789014"]
        recorded_account_ids = [call["account_id"] for call in result_calls]
        assert set(recorded_account_ids) == set(expected_account_ids)

        # Verify all results were recorded as successful
        assert all(call["status"] == "success" for call in result_calls)
        assert all(call["processing_time"] == 0.6 for call in result_calls)
        assert all(call["retry_count"] == 0 for call in result_calls)
        assert all(call["error"] is None for call in result_calls)

    @pytest.mark.asyncio
    async def test_progress_tracking_accuracy_mixed_results(
        self, multi_account_processor, sample_accounts
    ):
        """Test progress tracking accuracy with mixed success/failure results."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Track progress tracker calls
        result_calls = []

        def mock_record_result(
            account_id, status, account_name=None, error=None, processing_time=0.0, retry_count=0
        ):
            result_calls.append(
                {
                    "account_id": account_id,
                    "status": status,
                    "account_name": account_name,
                    "error": error,
                    "processing_time": processing_time,
                    "retry_count": retry_count,
                }
            )

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker methods
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "record_account_result"
            ) as mock_record, patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                mock_record.side_effect = mock_record_result

                # Mock mixed results
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def mixed_side_effect(account, *args, **kwargs):
                        if account.account_id == "123456789012":  # Success
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="success",
                                processing_time=0.4,
                                retry_count=0,
                            )
                        elif account.account_id == "123456789013":  # Failure
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="failed",
                                error_message="Access denied",
                                processing_time=1.2,
                                retry_count=2,
                            )
                        else:  # Skipped
                            return AccountResult(
                                account_id=account.account_id,
                                account_name=account.account_name,
                                status="skipped",
                                error_message="Account suspended",
                                processing_time=0.1,
                                retry_count=0,
                            )

                    mock_process.side_effect = mixed_side_effect

                    await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                    )

        # Verify all account results were recorded
        assert len(result_calls) == 3

        # Verify each result was recorded with correct status and details
        result_by_account = {call["account_id"]: call for call in result_calls}

        # Check successful account
        success_call = result_by_account["123456789012"]
        assert success_call["status"] == "success"
        assert success_call["processing_time"] == 0.4
        assert success_call["retry_count"] == 0
        assert success_call["error"] is None

        # Check failed account
        failed_call = result_by_account["123456789013"]
        assert failed_call["status"] == "failed"
        assert failed_call["processing_time"] == 1.2
        assert failed_call["retry_count"] == 2
        assert failed_call["error"] == "Access denied"

        # Check skipped account
        skipped_call = result_by_account["123456789014"]
        assert skipped_call["status"] == "skipped"
        assert skipped_call["processing_time"] == 0.1
        assert skipped_call["retry_count"] == 0
        assert skipped_call["error"] == "Account suspended"

    @pytest.mark.asyncio
    async def test_progress_tracking_with_current_account_updates(
        self, multi_account_processor, sample_accounts
    ):
        """Test that current account is updated correctly during processing."""
        # Set up resource resolver
        multi_account_processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )

        # Track current account updates
        current_account_calls = []

        def mock_update_current_account(account_name, account_id):
            current_account_calls.append({"account_name": account_name, "account_id": account_id})

        # Mock successful name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock progress tracker methods
            with patch.object(
                multi_account_processor.progress_tracker, "start_multi_account_progress"
            ), patch.object(
                multi_account_processor.progress_tracker, "update_current_account"
            ) as mock_update, patch.object(
                multi_account_processor.progress_tracker, "record_account_result"
            ), patch.object(
                multi_account_processor.progress_tracker, "stop_live_display"
            ), patch.object(
                multi_account_processor.progress_tracker, "display_final_summary"
            ):
                mock_update.side_effect = mock_update_current_account

                # Mock successful account processing
                with patch.object(
                    multi_account_processor, "_process_single_account_operation"
                ) as mock_process:

                    def success_side_effect(account, *args, **kwargs):
                        return AccountResult(
                            account_id=account.account_id,
                            account_name=account.account_name,
                            status="success",
                            processing_time=0.3,
                            retry_count=0,
                        )

                    mock_process.side_effect = success_side_effect

                    await multi_account_processor.process_multi_account_operation(
                        accounts=sample_accounts,
                        permission_set_name="TestPermissionSet",
                        principal_name="test-user",
                        principal_type="USER",
                        operation="assign",
                        instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        dry_run=False,
                    )

        # Verify current account was updated for each account
        assert len(current_account_calls) == 3

        # Verify the correct account names and IDs were passed
        expected_updates = [
            {"account_name": "Test Account 1", "account_id": "123456789012"},
            {"account_name": "Test Account 2", "account_id": "123456789013"},
            {"account_name": "Test Account 3", "account_id": "123456789014"},
        ]

        # Sort both lists by account_id for comparison
        current_account_calls.sort(key=lambda x: x["account_id"])
        expected_updates.sort(key=lambda x: x["account_id"])

        assert current_account_calls == expected_updates


class TestMultiAccountRetryLogic:
    """Test cases for retry logic when individual account operations fail."""

    def test_retry_logic_with_retryable_error(self, multi_account_processor, sample_accounts):
        """Test retry logic with retryable errors."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id",
        )

        # Mock retryable error (throttling)
        from botocore.exceptions import ClientError

        throttling_error = ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            operation_name="CreateAccountAssignment",
        )

        call_count = 0

        def mock_execute_assign(
            principal_id, permission_set_arn, account_id, principal_type, instance_arn
        ):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first 2 attempts
                raise throttling_error
            else:  # Succeed on 3rd attempt
                return {"retry_count": call_count - 1}

        with patch.object(multi_account_processor, "_execute_assign_operation") as mock_assign:
            mock_assign.side_effect = mock_execute_assign

            # Mock retry logic functions
            with patch(
                "src.awsideman.utils.bulk.multi_account_errors.should_retry_error"
            ) as mock_should_retry, patch(
                "src.awsideman.utils.bulk.multi_account_errors.calculate_retry_delay"
            ) as mock_delay, patch(
                "time.sleep"
            ) as mock_sleep:  # Mock sleep to speed up test
                # Configure retry logic
                mock_should_retry.side_effect = (
                    lambda error, retry_count, max_retries: retry_count < max_retries
                )
                mock_delay.return_value = 0.1  # Short delay for testing

                result = multi_account_processor._process_single_account_operation(
                    account,
                    multi_assignment,
                    "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    False,
                )
                # Verify retry delay was calculated and sleep was called
                assert mock_delay.call_count == 2  # Called for each retry
                assert mock_sleep.call_count == 2  # Sleep called for each retry

        # Verify retry logic worked
        assert call_count == 3  # Should have retried twice and succeeded on 3rd attempt
        assert result.status == "success"
        assert result.retry_count == 2  # 2 retries before success
        assert result.account_id == account.account_id

    def test_retry_logic_with_non_retryable_error(self, multi_account_processor, sample_accounts):
        """Test retry logic with non-retryable errors."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id",
        )

        # Mock non-retryable error (validation error)
        from botocore.exceptions import ClientError

        validation_error = ClientError(
            error_response={
                "Error": {"Code": "ValidationException", "Message": "Invalid permission set ARN"}
            },
            operation_name="CreateAccountAssignment",
        )

        call_count = 0

        def mock_execute_assign(
            principal_id, permission_set_arn, account_id, principal_type, instance_arn
        ):
            nonlocal call_count
            call_count += 1
            raise validation_error

        with patch.object(multi_account_processor, "_execute_assign_operation") as mock_assign:
            mock_assign.side_effect = mock_execute_assign

            # Mock retry logic functions
            with patch(
                "src.awsideman.utils.bulk.multi_account_errors.should_retry_error"
            ) as mock_should_retry:
                # Configure retry logic - validation errors should not be retried
                mock_should_retry.return_value = False

                result = multi_account_processor._process_single_account_operation(
                    account,
                    multi_assignment,
                    "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    False,
                )

        # Verify no retries occurred
        assert call_count == 1  # Should have been called only once
        assert result.status == "failed"
        assert result.retry_count == 0  # No retries
        assert "Invalid permission set ARN" in result.error_message

    def test_retry_logic_max_retries_exceeded(self, multi_account_processor, sample_accounts):
        """Test retry logic when max retries are exceeded."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id",
        )

        # Mock retryable error that keeps failing
        from botocore.exceptions import ClientError

        throttling_error = ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            operation_name="CreateAccountAssignment",
        )

        call_count = 0

        def mock_execute_assign(
            principal_id, permission_set_arn, account_id, principal_type, instance_arn
        ):
            nonlocal call_count
            call_count += 1
            raise throttling_error  # Always fail

        with patch.object(multi_account_processor, "_execute_assign_operation") as mock_assign:
            mock_assign.side_effect = mock_execute_assign

            # Mock retry logic functions
            with patch(
                "src.awsideman.utils.bulk.multi_account_errors.should_retry_error"
            ) as mock_should_retry, patch(
                "src.awsideman.utils.bulk.multi_account_errors.calculate_retry_delay"
            ) as mock_delay, patch(
                "time.sleep"
            ) as mock_sleep:
                # Configure retry logic - allow retries up to max_retries (3)
                def should_retry_side_effect(error, retry_count, max_retries):
                    return retry_count < max_retries

                mock_should_retry.side_effect = should_retry_side_effect
                mock_delay.return_value = 0.1

                result = multi_account_processor._process_single_account_operation(
                    account,
                    multi_assignment,
                    "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    False,
                )

        # Verify max retries were attempted
        assert call_count == 4  # Initial attempt + 3 retries
        assert result.status == "failed"
        assert result.retry_count == 3  # 3 retries attempted
        assert "Rate exceeded" in result.error_message

        # Verify retry delays were calculated
        assert mock_delay.call_count == 3  # Called for each retry
        assert mock_sleep.call_count == 3  # Sleep called for each retry

    def test_retry_logic_with_revoke_operation(self, multi_account_processor, sample_accounts):
        """Test retry logic with revoke operations."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="revoke",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id",
        )

        # Mock retryable error for revoke operation
        from botocore.exceptions import ClientError

        throttling_error = ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            operation_name="DeleteAccountAssignment",
        )

        call_count = 0

        def mock_execute_revoke(
            principal_id, permission_set_arn, account_id, principal_type, instance_arn
        ):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Fail first attempt
                raise throttling_error
            else:  # Succeed on 2nd attempt
                return {"retry_count": call_count - 1}

        with patch.object(multi_account_processor, "_execute_revoke_operation") as mock_revoke:
            mock_revoke.side_effect = mock_execute_revoke

            # Mock retry logic functions
            with patch(
                "src.awsideman.utils.bulk.multi_account_errors.should_retry_error"
            ) as mock_should_retry, patch(
                "src.awsideman.utils.bulk.multi_account_errors.calculate_retry_delay"
            ) as mock_delay:
                mock_should_retry.side_effect = (
                    lambda error, retry_count, max_retries: retry_count < max_retries
                )
                mock_delay.return_value = 0.1

                result = multi_account_processor._process_single_account_operation(
                    account,
                    multi_assignment,
                    "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    False,
                )

        # Verify retry logic worked for revoke operation
        assert call_count == 2  # Should have retried once and succeeded
        assert result.status == "success"
        assert result.retry_count == 1  # 1 retry before success
        assert result.account_id == account.account_id

    def test_retry_logic_with_different_error_types(self, multi_account_processor, sample_accounts):
        """Test retry logic with different types of errors."""
        account = sample_accounts[0]
        multi_assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[account],
            operation="assign",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            principal_id="test-user-id",
        )

        # Test different error scenarios
        error_scenarios = [
            {
                "error": ClientError(
                    error_response={
                        "Error": {
                            "Code": "ServiceUnavailableException",
                            "Message": "Service unavailable",
                        }
                    },
                    operation_name="CreateAccountAssignment",
                ),
                "should_retry": True,
                "expected_retries": 2,
            },
            {
                "error": ClientError(
                    error_response={
                        "Error": {"Code": "AccessDeniedException", "Message": "Access denied"}
                    },
                    operation_name="CreateAccountAssignment",
                ),
                "should_retry": False,
                "expected_retries": 0,
            },
            {"error": Exception("Network timeout"), "should_retry": True, "expected_retries": 1},
        ]

        for scenario in error_scenarios:
            call_count = 0

            def mock_execute_assign(
                principal_id, permission_set_arn, account_id, principal_type, instance_arn
            ):
                nonlocal call_count
                call_count += 1
                if scenario["should_retry"] and call_count <= scenario["expected_retries"]:
                    raise scenario["error"]
                elif not scenario["should_retry"]:
                    # Always fail for non-retryable errors
                    raise scenario["error"]
                else:
                    return {"retry_count": call_count - 1}

            with patch.object(multi_account_processor, "_execute_assign_operation") as mock_assign:
                mock_assign.side_effect = mock_execute_assign

                # Mock retry logic functions
                with patch(
                    "src.awsideman.utils.bulk.multi_account_errors.should_retry_error"
                ) as mock_should_retry, patch(
                    "src.awsideman.utils.bulk.multi_account_errors.calculate_retry_delay"
                ) as mock_delay:
                    mock_should_retry.return_value = scenario["should_retry"]
                    mock_delay.return_value = 0.1

                    result = multi_account_processor._process_single_account_operation(
                        account,
                        multi_assignment,
                        "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        False,
                    )

            if scenario["should_retry"] and scenario["expected_retries"] > 0:
                # Should succeed after retries
                assert result.status == "success"
                assert result.retry_count == scenario["expected_retries"]
            else:
                # Should fail without retries
                assert result.status == "failed"
                assert result.retry_count == 0


class TestMultiAccountAssignmentValidation:
    """Test cases for MultiAccountAssignment validation."""

    def test_valid_assignment(self, sample_accounts):
        """Test validation of a valid assignment."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
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
            operation="assign",
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
            operation="assign",
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
            operation="assign",
        )

        errors = assignment.validate()
        assert len(errors) == 1
        assert "Invalid principal type: INVALID" in errors[0]

    def test_invalid_operation(self, sample_accounts):
        """Test validation with invalid operation."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="invalid_operation",
        )

        errors = assignment.validate()
        assert len(errors) == 1
        assert "Invalid operation: invalid_operation" in errors[0]

    def test_empty_accounts_list(self):
        """Test validation with empty accounts list."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[],
            operation="assign",
        )

        errors = assignment.validate()
        assert len(errors) == 1
        assert "At least one account must be specified" in errors[0]

    def test_multiple_validation_errors(self):
        """Test validation with multiple errors."""
        assignment = MultiAccountAssignment(
            permission_set_name="",
            principal_name="",
            principal_type="INVALID",
            accounts=[],
            operation="invalid_operation",
        )

        errors = assignment.validate()
        assert len(errors) == 5
        assert "Permission set name cannot be empty" in errors
        assert "Principal name cannot be empty" in errors
        assert "Invalid principal type: INVALID" in errors
        assert "At least one account must be specified" in errors
        assert "Invalid operation: invalid_operation" in errors

    def test_no_accounts(self):
        """Test validation with no accounts."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=[],
            operation="assign",
        )

        errors = assignment.validate()
        assert len(errors) == 1
        assert "At least one account must be specified" in errors[0]

    def test_multiple_validation_errors_comprehensive(self):
        """Test validation with multiple errors."""
        assignment = MultiAccountAssignment(
            permission_set_name="",
            principal_name="",
            principal_type="INVALID",
            accounts=[],
            operation="invalid",
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
            operation="assign",
        )

        # Initially not resolved
        assert not assignment.is_resolved()

        # Set permission set ARN only
        assignment.permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
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
            operation="assign",
        )

        assert assignment.get_total_operations() == 3  # 3 accounts

    def test_get_account_ids(self, sample_accounts):
        """Test getting account IDs."""
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )

        account_ids = assignment.get_account_ids()
        expected_ids = ["123456789012", "123456789013", "123456789014"]
        assert account_ids == expected_ids
