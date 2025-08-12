"""Integration tests for multi-account data models working together."""
import pytest

from src.awsideman.utils.models import (
    AccountInfo,
    AccountResult,
    MultiAccountAssignment,
    MultiAccountResults,
)


class TestMultiAccountModelsIntegration:
    """Test multi-account models working together."""

    def test_complete_multi_account_workflow(self):
        """Test a complete multi-account workflow using all models."""
        # Step 1: Create account information
        accounts = [
            AccountInfo(
                account_id="123456789012",
                account_name="prod-account",
                email="prod@example.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Team": "DevOps"},
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="dev-account",
                email="dev@example.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Team": "DevOps"},
            ),
            AccountInfo(
                account_id="123456789014",
                account_name="test-account",
                email="test@example.com",
                status="ACTIVE",
                tags={"Environment": "Test", "Team": "QA"},
            ),
        ]

        # Step 2: Create multi-account assignment
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@example.com",
            principal_type="USER",
            accounts=accounts,
            operation="assign",
        )

        # Validate assignment
        errors = assignment.validate()
        assert len(errors) == 0
        assert assignment.get_total_operations() == 3

        # Simulate name resolution
        assignment.permission_set_arn = "arn:aws:sso:::permissionSet/ins-123/ps-456"
        assignment.principal_id = "user-123"
        assert assignment.is_resolved() is True

        # Step 3: Simulate operation results
        successful_results = [
            AccountResult(
                account_id="123456789012",
                account_name="prod-account",
                status="success",
                processing_time=1.2,
            ),
            AccountResult(
                account_id="123456789013",
                account_name="dev-account",
                status="success",
                processing_time=0.8,
            ),
        ]

        failed_results = [
            AccountResult(
                account_id="123456789014",
                account_name="test-account",
                status="failed",
                error_message="Insufficient permissions",
                processing_time=0.5,
                retry_count=2,
            )
        ]

        # Step 4: Aggregate results
        results = MultiAccountResults(
            total_accounts=3,
            successful_accounts=successful_results,
            failed_accounts=failed_results,
            skipped_accounts=[],
            operation_type="assign",
            duration=5.2,
            batch_size=2,
        )

        # Verify results
        assert results.success_rate == pytest.approx(66.67, rel=1e-2)
        assert results.failure_rate == pytest.approx(33.33, rel=1e-2)
        assert results.skip_rate == 0.0
        assert results.has_failures() is True
        assert results.is_complete_success() is False

        # Verify summary stats
        stats = results.get_summary_stats()
        assert stats["total_accounts"] == 3
        assert stats["successful_count"] == 2
        assert stats["failed_count"] == 1
        assert stats["skipped_count"] == 0

        # Verify account ID extraction
        successful_ids = results.get_successful_account_ids()
        failed_ids = results.get_failed_account_ids()

        assert successful_ids == ["123456789012", "123456789013"]
        assert failed_ids == ["123456789014"]

        # Verify assignment account IDs match
        assignment_ids = assignment.get_account_ids()
        all_result_ids = successful_ids + failed_ids
        assert set(assignment_ids) == set(all_result_ids)

    def test_tag_filtering_workflow(self):
        """Test tag-based filtering workflow."""
        # Create accounts with different tags
        accounts = [
            AccountInfo(
                account_id="123456789012",
                account_name="prod-web",
                email="prod-web@example.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Service": "Web"},
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="prod-db",
                email="prod-db@example.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Service": "Database"},
            ),
            AccountInfo(
                account_id="123456789014",
                account_name="dev-web",
                email="dev-web@example.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Service": "Web"},
            ),
        ]

        # Test filtering by Environment tag
        prod_accounts = [
            acc for acc in accounts if acc.matches_tag_filter("Environment", "Production")
        ]
        assert len(prod_accounts) == 2
        assert all(acc.has_tag("Environment", "Production") for acc in prod_accounts)

        # Test filtering by Service tag
        web_accounts = [acc for acc in accounts if acc.matches_tag_filter("Service", "Web")]
        assert len(web_accounts) == 2
        assert all(acc.has_tag("Service", "Web") for acc in web_accounts)

        # Test combined filtering (Production Web accounts)
        prod_web_accounts = [
            acc
            for acc in accounts
            if acc.matches_tag_filter("Environment", "Production")
            and acc.matches_tag_filter("Service", "Web")
        ]
        assert len(prod_web_accounts) == 1
        assert prod_web_accounts[0].account_id == "123456789012"

    def test_error_handling_workflow(self):
        """Test error handling across models."""
        # Create assignment with validation errors
        invalid_assignment = MultiAccountAssignment(
            permission_set_name="",  # Invalid
            principal_name="john.doe@example.com",
            principal_type="INVALID",  # Invalid
            accounts=[],  # Invalid
            operation="invalid",  # Invalid
        )

        errors = invalid_assignment.validate()
        assert len(errors) >= 4  # Multiple validation errors

        # Create results with all failures
        failed_results = [
            AccountResult(
                account_id="123456789012",
                account_name="account-1",
                status="failed",
                error_message="Permission denied",
            ),
            AccountResult(
                account_id="123456789013",
                account_name="account-2",
                status="failed",
                error_message="Network timeout",
            ),
        ]

        results = MultiAccountResults(
            total_accounts=2,
            successful_accounts=[],
            failed_accounts=failed_results,
            skipped_accounts=[],
            operation_type="assign",
            duration=2.0,
            batch_size=1,
        )

        # Verify failure handling
        assert results.success_rate == 0.0
        assert results.failure_rate == 100.0
        assert results.has_failures() is True
        assert results.is_complete_success() is False

        # Verify error summaries
        for result in failed_results:
            assert result.get_error_summary() in ["Permission denied", "Network timeout"]
            assert not result.is_successful()

    def test_display_name_consistency(self):
        """Test display name consistency across models."""
        account_info = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE",
        )

        account_result = AccountResult(
            account_id="123456789012", account_name="test-account", status="success"
        )

        # Both should generate the same display name
        assert account_info.get_display_name() == account_result.get_display_name()
        assert account_info.get_display_name() == "test-account (123456789012)"
