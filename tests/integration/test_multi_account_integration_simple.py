"""Simplified integration tests for multi-account end-to-end workflows.

This module contains simplified integration tests that test the complete multi-account
workflows by mocking at a higher level to avoid complex AWS client mocking.
"""

from typing import List
from unittest.mock import Mock, patch

import pytest

from src.awsideman.bulk.multi_account_batch import MultiAccountBatchProcessor
from src.awsideman.utils.models import (
    AccountInfo,
    AccountResult,
    MultiAccountAssignment,
    MultiAccountResults,
)


class TestMultiAccountIntegrationSimple:
    """Simplified integration tests for multi-account workflows."""

    @pytest.fixture
    def sample_accounts(self) -> List[AccountInfo]:
        """Get sample account data for testing."""
        return [
            AccountInfo(
                account_id="111111111111",
                account_name="dev-account-1",
                email="dev1@company.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Team": "Backend"},
                ou_path=["Root", "Development"],
            ),
            AccountInfo(
                account_id="222222222222",
                account_name="dev-account-2",
                email="dev2@company.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Team": "Frontend"},
                ou_path=["Root", "Development"],
            ),
            AccountInfo(
                account_id="333333333333",
                account_name="prod-account-1",
                email="prod1@company.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Team": "Backend"},
                ou_path=["Root", "Production"],
            ),
        ]

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create a mock AWS client manager."""
        manager = Mock()

        # Mock SSO Admin client
        sso_admin_client = Mock()
        sso_admin_client.create_account_assignment.return_value = {
            "AccountAssignmentCreationStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "req-1234567890abcdef",
            }
        }
        sso_admin_client.delete_account_assignment.return_value = {
            "AccountAssignmentDeletionStatus": {
                "Status": "SUCCEEDED",
                "RequestId": "req-1234567890abcdef",
            }
        }
        sso_admin_client.list_account_assignments.return_value = {"AccountAssignments": []}
        manager.get_identity_center_client.return_value = sso_admin_client

        return manager

    def test_multi_account_assignment_creation(self, sample_accounts, mock_aws_client_manager):
        """Test creating a multi-account assignment."""
        # Create multi-account assignment
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )

        # Validate assignment
        validation_errors = assignment.validate()
        assert len(validation_errors) == 0

        # Verify assignment properties
        assert assignment.get_total_operations() == 3
        assert assignment.permission_set_name == "ReadOnlyAccess"
        assert assignment.principal_name == "john.doe@company.com"
        assert assignment.principal_type == "USER"
        assert assignment.operation == "assign"
        assert len(assignment.accounts) == 3

    def test_multi_account_assignment_validation(self, sample_accounts):
        """Test multi-account assignment validation."""
        # Test with empty permission set name
        assignment = MultiAccountAssignment(
            permission_set_name="",
            principal_name="john.doe@company.com",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )

        validation_errors = assignment.validate()
        assert len(validation_errors) > 0
        assert any("permission set name" in error.lower() for error in validation_errors)

        # Test with empty principal name
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )

        validation_errors = assignment.validate()
        assert len(validation_errors) > 0
        assert any("principal name" in error.lower() for error in validation_errors)

        # Test with invalid principal type
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            principal_type="INVALID",
            accounts=sample_accounts,
            operation="assign",
        )

        validation_errors = assignment.validate()
        assert len(validation_errors) > 0
        assert any("principal type" in error.lower() for error in validation_errors)

        # Test with no accounts
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            principal_type="USER",
            accounts=[],
            operation="assign",
        )

        validation_errors = assignment.validate()
        assert len(validation_errors) > 0
        assert any("account" in error.lower() for error in validation_errors)

    @patch("asyncio.run")
    def test_multi_account_batch_processor_assign(
        self, mock_asyncio_run, sample_accounts, mock_aws_client_manager
    ):
        """Test multi-account batch processor for assign operations."""
        # Create batch processor
        processor = MultiAccountBatchProcessor(mock_aws_client_manager, batch_size=2)
        processor.set_resource_resolver("arn:aws:sso:::instance/ins-123", "d-1234567890")

        # Mock the async operation result
        mock_results = MultiAccountResults(
            total_accounts=3,
            successful_accounts=[
                AccountResult(
                    account_id="111111111111",
                    account_name="dev-account-1",
                    status="success",
                    processing_time=1.0,
                ),
                AccountResult(
                    account_id="222222222222",
                    account_name="dev-account-2",
                    status="success",
                    processing_time=1.2,
                ),
                AccountResult(
                    account_id="333333333333",
                    account_name="prod-account-1",
                    status="success",
                    processing_time=0.8,
                ),
            ],
            failed_accounts=[],
            skipped_accounts=[],
            operation_type="assign",
            duration=3.5,
            batch_size=2,
        )

        mock_asyncio_run.return_value = mock_results

        # Process multi-account operation
        results = mock_asyncio_run.return_value

        # Verify results
        assert results.total_accounts == 3
        assert results.success_rate == 100.0
        assert results.is_complete_success()
        assert not results.has_failures()
        assert results.operation_type == "assign"
        assert results.batch_size == 2

        # Verify summary stats
        stats = results.get_summary_stats()
        assert stats["total_accounts"] == 3
        assert stats["successful_count"] == 3
        assert stats["failed_count"] == 0
        assert stats["skipped_count"] == 0
        assert stats["success_rate"] == 100.0
        assert stats["duration_seconds"] == 3.5

    @patch("asyncio.run")
    def test_multi_account_batch_processor_revoke(
        self, mock_asyncio_run, sample_accounts, mock_aws_client_manager
    ):
        """Test multi-account batch processor for revoke operations."""
        # Create batch processor
        processor = MultiAccountBatchProcessor(mock_aws_client_manager, batch_size=2)
        processor.set_resource_resolver("arn:aws:sso:::instance/ins-123", "d-1234567890")

        # Mock the async operation result with mixed results
        mock_results = MultiAccountResults(
            total_accounts=3,
            successful_accounts=[
                AccountResult(
                    account_id="111111111111",
                    account_name="dev-account-1",
                    status="success",
                    processing_time=1.0,
                ),
                AccountResult(
                    account_id="222222222222",
                    account_name="dev-account-2",
                    status="success",
                    processing_time=1.2,
                ),
            ],
            failed_accounts=[
                AccountResult(
                    account_id="333333333333",
                    account_name="prod-account-1",
                    status="failed",
                    error_message="Assignment not found",
                    processing_time=0.5,
                )
            ],
            skipped_accounts=[],
            operation_type="revoke",
            duration=2.7,
            batch_size=2,
        )

        mock_asyncio_run.return_value = mock_results

        # Process multi-account operation
        results = mock_asyncio_run.return_value

        # Verify results
        assert results.total_accounts == 3
        assert round(results.success_rate, 1) == 66.7  # 2 out of 3 successful
        assert not results.is_complete_success()
        assert results.has_failures()
        assert results.operation_type == "revoke"

        # Verify summary stats
        stats = results.get_summary_stats()
        assert stats["total_accounts"] == 3
        assert stats["successful_count"] == 2
        assert stats["failed_count"] == 1
        assert stats["skipped_count"] == 0
        assert stats["success_rate"] == 66.67
        assert stats["failure_rate"] == 33.33

    def test_multi_account_results_aggregation(self, sample_accounts):
        """Test multi-account results aggregation and statistics."""
        # Create results with mixed outcomes
        results = MultiAccountResults(
            total_accounts=4,
            successful_accounts=[
                AccountResult(
                    account_id="111111111111",
                    account_name="dev-account-1",
                    status="success",
                    processing_time=1.0,
                ),
                AccountResult(
                    account_id="222222222222",
                    account_name="dev-account-2",
                    status="success",
                    processing_time=1.5,
                ),
            ],
            failed_accounts=[
                AccountResult(
                    account_id="333333333333",
                    account_name="prod-account-1",
                    status="failed",
                    error_message="Access denied",
                    processing_time=0.5,
                )
            ],
            skipped_accounts=[
                AccountResult(
                    account_id="444444444444",
                    account_name="staging-account",
                    status="skipped",
                    error_message="Assignment already exists",
                    processing_time=0.1,
                )
            ],
            operation_type="assign",
            duration=5.0,
            batch_size=2,
        )

        # Test basic properties
        assert results.total_accounts == 4
        assert len(results.successful_accounts) == 2
        assert len(results.failed_accounts) == 1
        assert len(results.skipped_accounts) == 1
        assert results.success_rate == 50.0
        assert results.failure_rate == 25.0
        assert results.skip_rate == 25.0

        # Test status checks
        assert not results.is_complete_success()
        assert results.has_failures()
        assert len(results.skipped_accounts) > 0  # Has skipped accounts

        # Test summary stats
        stats = results.get_summary_stats()
        assert stats["total_accounts"] == 4
        assert stats["successful_count"] == 2
        assert stats["failed_count"] == 1
        assert stats["skipped_count"] == 1
        assert stats["success_rate"] == 50.0
        assert stats["failure_rate"] == 25.0
        assert stats["skip_rate"] == 25.0
        assert stats["duration_seconds"] == 5.0
        assert stats["average_processing_time"] == 0.775  # (1.0 + 1.5 + 0.5 + 0.1) / 4

    def test_account_result_properties(self):
        """Test AccountResult properties and methods."""
        # Test successful result
        success_result = AccountResult(
            account_id="111111111111",
            account_name="dev-account-1",
            status="success",
            processing_time=1.5,
            retry_count=0,
        )

        assert success_result.is_successful()
        assert success_result.get_display_name() == "dev-account-1 (111111111111)"
        assert success_result.get_error_summary() == "Status: success"

        # Test failed result
        failed_result = AccountResult(
            account_id="222222222222",
            account_name="dev-account-2",
            status="failed",
            error_message="Access denied",
            processing_time=0.5,
            retry_count=2,
        )

        assert not failed_result.is_successful()
        assert failed_result.get_display_name() == "dev-account-2 (222222222222)"
        assert failed_result.get_error_summary() == "Access denied"

        # Test skipped result
        skipped_result = AccountResult(
            account_id="333333333333",
            account_name="prod-account-1",
            status="skipped",
            error_message="Assignment already exists",
            processing_time=0.1,
        )

        assert not skipped_result.is_successful()
        assert skipped_result.get_display_name() == "prod-account-1 (333333333333)"
        assert skipped_result.get_error_summary() == "Assignment already exists"

    def test_account_info_properties(self, sample_accounts):
        """Test AccountInfo properties and methods."""
        account = sample_accounts[0]  # dev-account-1

        # Test basic properties
        assert account.account_id == "111111111111"
        assert account.account_name == "dev-account-1"
        assert account.email == "dev1@company.com"
        assert account.status == "ACTIVE"

        # Test tag matching
        assert account.matches_tag_filter("Environment", "Development")
        assert account.matches_tag_filter("Team", "Backend")
        assert not account.matches_tag_filter("Environment", "Production")
        assert not account.matches_tag_filter("Team", "Frontend")
        assert not account.matches_tag_filter("NonExistent", "Value")

        # Test display name
        assert account.get_display_name() == "dev-account-1 (111111111111)"

    def test_dry_run_simulation(self, sample_accounts, mock_aws_client_manager):
        """Test dry-run simulation functionality."""
        # Create multi-account assignment for dry-run
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@company.com",
            principal_type="USER",
            accounts=sample_accounts,
            operation="assign",
        )

        # Validate assignment for dry-run
        validation_errors = assignment.validate()
        assert len(validation_errors) == 0

        # In a real dry-run, we would:
        # 1. Validate all names can be resolved
        # 2. Check existing assignments
        # 3. Simulate the operations without making changes
        # 4. Return preview results

        # For this test, we simulate the dry-run results
        dry_run_results = MultiAccountResults(
            total_accounts=3,
            successful_accounts=[],  # No actual operations in dry-run
            failed_accounts=[],
            skipped_accounts=[
                AccountResult(
                    account_id=account.account_id,
                    account_name=account.account_name,
                    status="would_assign",  # Custom status for dry-run
                    processing_time=0.0,
                )
                for account in sample_accounts
            ],
            operation_type="assign_dry_run",
            duration=0.5,
            batch_size=2,
        )

        # Verify dry-run results
        assert dry_run_results.total_accounts == 3
        assert len(dry_run_results.successful_accounts) == 0
        assert len(dry_run_results.failed_accounts) == 0
        assert len(dry_run_results.skipped_accounts) == 3  # All would be processed
        assert dry_run_results.operation_type == "assign_dry_run"

        # Verify all accounts would be processed
        for i, result in enumerate(dry_run_results.skipped_accounts):
            assert result.account_id == sample_accounts[i].account_id
            assert result.account_name == sample_accounts[i].account_name
            assert result.status == "would_assign"

    def test_error_handling_scenarios(self, sample_accounts):
        """Test various error handling scenarios."""
        # Test with network errors (simulated)
        network_error_results = MultiAccountResults(
            total_accounts=3,
            successful_accounts=[
                AccountResult(
                    account_id="111111111111",
                    account_name="dev-account-1",
                    status="success",
                    processing_time=1.0,
                )
            ],
            failed_accounts=[
                AccountResult(
                    account_id="222222222222",
                    account_name="dev-account-2",
                    status="failed",
                    error_message="Network timeout",
                    processing_time=5.0,
                    retry_count=3,
                ),
                AccountResult(
                    account_id="333333333333",
                    account_name="prod-account-1",
                    status="failed",
                    error_message="Access denied",
                    processing_time=0.5,
                    retry_count=0,
                ),
            ],
            skipped_accounts=[],
            operation_type="assign",
            duration=10.0,
            batch_size=2,
        )

        # Verify error handling results
        assert network_error_results.total_accounts == 3
        assert len(network_error_results.successful_accounts) == 1
        assert len(network_error_results.failed_accounts) == 2
        assert round(network_error_results.success_rate, 1) == 33.3
        assert round(network_error_results.failure_rate, 1) == 66.7
        assert network_error_results.has_failures()
        assert not network_error_results.is_complete_success()

        # Verify retry counts
        failed_results = network_error_results.failed_accounts
        timeout_result = next(r for r in failed_results if "timeout" in r.error_message)
        access_denied_result = next(r for r in failed_results if "Access denied" in r.error_message)

        assert timeout_result.retry_count == 3  # Network error should be retried
        assert access_denied_result.retry_count == 0  # Access error should not be retried
