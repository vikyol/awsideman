"""Tests for enhanced dry-run functionality in multi-account operations."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.bulk.multi_account_batch import MultiAccountBatchProcessor
from src.awsideman.utils.models import AccountInfo, MultiAccountAssignment, MultiAccountResults


class TestDryRunFunctionality:
    """Test cases for enhanced dry-run functionality."""

    @pytest.fixture
    def mock_aws_client(self):
        """Create a mock AWS client manager."""
        mock_client = Mock()
        mock_sso_client = Mock()
        mock_client.get_identity_center_client.return_value = mock_sso_client
        return mock_client

    @pytest.fixture
    def sample_accounts(self):
        """Create sample account data for testing."""
        return [
            AccountInfo(
                account_id="123456789012",
                account_name="Production Account",
                email="prod@example.com",
                status="ACTIVE",
                tags={"Environment": "Production"},
                ou_path=["root", "production"],
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="Development Account",
                email="dev@example.com",
                status="ACTIVE",
                tags={"Environment": "Development"},
                ou_path=["root", "development"],
            ),
        ]

    @pytest.fixture
    def multi_account_processor(self, mock_aws_client):
        """Create a MultiAccountBatchProcessor for testing."""
        processor = MultiAccountBatchProcessor(mock_aws_client, batch_size=5)
        processor.set_resource_resolver(
            "arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890"
        )
        return processor

    def test_simulate_account_operation_assign_new(self, multi_account_processor, sample_accounts):
        """Test simulating assignment operation when assignment doesn't exist."""
        # Mock SSO client to return no existing assignments
        mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()
        mock_sso_client.list_account_assignments.return_value = {"AccountAssignments": []}

        # Create test assignment
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )
        assignment.permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assignment.principal_id = "user-1234567890abcdef"

        # Test simulation
        result = multi_account_processor._simulate_account_operation(
            sample_accounts[0], assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", 0.0
        )

        assert result.status == "success"
        assert result.account_id == "123456789012"
        assert result.account_name == "Production Account"
        assert "create new assignment" in result.error_message.lower()

    def test_simulate_account_operation_assign_existing(
        self, multi_account_processor, sample_accounts
    ):
        """Test simulating assignment operation when assignment already exists."""
        # Mock SSO client to return existing assignment
        mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()
        mock_sso_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                    "PrincipalId": "user-1234567890abcdef",
                    "PrincipalType": "USER",
                    "AccountId": "123456789012",
                }
            ]
        }

        # Create test assignment
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )
        assignment.permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assignment.principal_id = "user-1234567890abcdef"

        # Test simulation
        result = multi_account_processor._simulate_account_operation(
            sample_accounts[0], assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", 0.0
        )

        assert result.status == "skipped"
        assert result.account_id == "123456789012"
        assert result.account_name == "Production Account"
        assert "already exists" in result.error_message.lower()

    def test_simulate_account_operation_revoke_existing(
        self, multi_account_processor, sample_accounts
    ):
        """Test simulating revoke operation when assignment exists."""
        # Mock SSO client to return existing assignment
        mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()
        mock_sso_client.list_account_assignments.return_value = {
            "AccountAssignments": [
                {
                    "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                    "PrincipalId": "user-1234567890abcdef",
                    "PrincipalType": "USER",
                    "AccountId": "123456789012",
                }
            ]
        }

        # Create test assignment
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="revoke",
        )
        assignment.permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assignment.principal_id = "user-1234567890abcdef"

        # Test simulation
        result = multi_account_processor._simulate_account_operation(
            sample_accounts[0], assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", 0.0
        )

        assert result.status == "success"
        assert result.account_id == "123456789012"
        assert result.account_name == "Production Account"
        assert "revoke existing assignment" in result.error_message.lower()

    def test_simulate_account_operation_revoke_nonexistent(
        self, multi_account_processor, sample_accounts
    ):
        """Test simulating revoke operation when assignment doesn't exist."""
        # Mock SSO client to return no existing assignments
        mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()
        mock_sso_client.list_account_assignments.return_value = {"AccountAssignments": []}

        # Create test assignment
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="revoke",
        )
        assignment.permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assignment.principal_id = "user-1234567890abcdef"

        # Test simulation
        result = multi_account_processor._simulate_account_operation(
            sample_accounts[0], assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", 0.0
        )

        assert result.status == "skipped"
        assert result.account_id == "123456789012"
        assert result.account_name == "Production Account"
        assert "no assignment to revoke" in result.error_message.lower()

    def test_simulate_account_operation_api_error(self, multi_account_processor, sample_accounts):
        """Test simulating operation when API call fails."""
        # Mock SSO client to raise an exception
        mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()
        mock_sso_client.list_account_assignments.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            operation_name="ListAccountAssignments",
        )

        # Create test assignment
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )
        assignment.permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assignment.principal_id = "user-1234567890abcdef"

        # Test simulation - should handle error gracefully
        result = multi_account_processor._simulate_account_operation(
            sample_accounts[0], assignment, "arn:aws:sso:::instance/ssoins-1234567890abcdef", 0.0
        )

        assert result.status == "success"
        assert result.account_id == "123456789012"
        assert result.account_name == "Production Account"
        assert "would attempt assign" in result.error_message.lower()
        assert "unable to verify current state" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_dry_run_with_enhanced_display(self, multi_account_processor, sample_accounts):
        """Test dry-run operation with enhanced display functionality."""
        # Mock SSO client responses for different scenarios
        mock_sso_client = multi_account_processor.aws_client_manager.get_identity_center_client()

        def mock_list_assignments(**kwargs):
            account_id = kwargs.get("AccountId")
            if account_id == "123456789012":
                # First account has existing assignment
                return {"AccountAssignments": [{"PermissionSetArn": "test-arn"}]}
            else:
                # Second account has no assignment
                return {"AccountAssignments": []}

        mock_sso_client.list_account_assignments.side_effect = mock_list_assignments

        # Mock name resolution
        def mock_resolve_names(assignment):
            assignment.permission_set_arn = (
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            )
            assignment.principal_id = "user-1234567890abcdef"
            return None

        with patch.object(multi_account_processor, "_resolve_names") as mock_resolve:
            mock_resolve.side_effect = mock_resolve_names

            # Mock display method to verify it's called
            with patch.object(multi_account_processor, "_display_dry_run_summary") as mock_display:
                result = await multi_account_processor.process_multi_account_operation(
                    accounts=sample_accounts,
                    permission_set_name="TestPermissionSet",
                    principal_name="test-user",
                    principal_type="USER",
                    operation="assign",
                    instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
                    dry_run=True,
                )

                # Verify dry-run summary was displayed
                mock_display.assert_called_once()

                # Verify results structure
                assert isinstance(result, MultiAccountResults)
                assert result.total_accounts == 2
                # In dry run mode, both accounts are processed successfully
                assert len(result.successful_accounts) == 2  # Both accounts processed in dry run
                assert len(result.skipped_accounts) == 0  # No accounts skipped in dry run
                assert len(result.failed_accounts) == 0

    def test_display_dry_run_summary(self, multi_account_processor, sample_accounts):
        """Test the dry-run summary display functionality."""
        from src.awsideman.utils.models import AccountResult

        # Create test results
        successful_result = AccountResult(
            account_id="123456789012",
            account_name="Production Account",
            status="success",
            error_message="Would create new assignment",
        )

        skipped_result = AccountResult(
            account_id="123456789013",
            account_name="Development Account",
            status="skipped",
            error_message="Assignment already exists",
        )

        results = MultiAccountResults(
            total_accounts=2,
            successful_accounts=[successful_result],
            failed_accounts=[],
            skipped_accounts=[skipped_result],
            operation_type="assign",
            duration=1.5,
            batch_size=5,
        )

        # Create test assignment
        assignment = MultiAccountAssignment(
            permission_set_name="TestPermissionSet",
            principal_name="test-user",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )
        assignment.permission_set_arn = (
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assignment.principal_id = "user-1234567890abcdef"

        # Test that display method runs without error
        # (We can't easily test the actual output without mocking console)
        try:
            multi_account_processor._display_dry_run_summary(results, assignment)
            # If we get here without exception, the method worked
            assert True
        except Exception as e:
            pytest.fail(f"Dry-run summary display failed: {str(e)}")
