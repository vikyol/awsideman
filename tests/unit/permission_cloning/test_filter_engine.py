"""
Unit tests for the FilterEngine class.

Tests filtering functionality including:
- Permission set name filtering
- Account ID filtering
- Combinable include/exclude logic
- Filter validation
- Edge cases and error scenarios
"""

import pytest

from src.awsideman.permission_cloning.filter_engine import FilterEngine
from src.awsideman.permission_cloning.models import (
    CopyFilters,
    PermissionAssignment,
    ValidationResultType,
)


class TestFilterEngine:
    """Test cases for FilterEngine class."""

    @pytest.fixture
    def filter_engine(self):
        """Create a FilterEngine instance."""
        return FilterEngine()

    @pytest.fixture
    def sample_assignments(self):
        """Create sample permission assignments for testing."""
        return [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                permission_set_name="AdministratorAccess",
                account_id="123456789012",
                account_name="Production",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-readonly",
                permission_set_name="ReadOnlyAccess",
                account_id="098765432109",
                account_name="Development",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-developer",
                permission_set_name="DeveloperAccess",
                account_id="555555555555",
                account_name="Staging",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
                permission_set_name="AdministratorAccess",
                account_id="111111111111",
                account_name="Testing",
            ),
        ]

    def test_init(self, filter_engine):
        """Test FilterEngine initialization."""
        assert filter_engine is not None

    def test_apply_filters_no_filters(self, filter_engine, sample_assignments):
        """Test applying no filters returns all assignments."""
        filters = CopyFilters()

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 4
        assert result == sample_assignments

    def test_apply_filters_none_filters(self, filter_engine, sample_assignments):
        """Test applying None filters returns all assignments."""
        result = filter_engine.apply_filters(sample_assignments, None)

        assert len(result) == 4
        assert result == sample_assignments

    def test_apply_filters_exclude_permission_sets(self, filter_engine, sample_assignments):
        """Test filtering by excluding specific permission sets."""
        filters = CopyFilters(exclude_permission_sets=["DeveloperAccess"])

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 3
        # Should exclude DeveloperAccess
        permission_set_names = [assignment.permission_set_name for assignment in result]
        assert "AdministratorAccess" in permission_set_names
        assert "ReadOnlyAccess" in permission_set_names
        assert "DeveloperAccess" not in permission_set_names

    def test_apply_filters_include_permission_sets_alternative(
        self, filter_engine, sample_assignments
    ):
        """Test filtering by including specific permission sets (alternative approach)."""
        # Since CopyFilters doesn't support include_permission_sets, we test the opposite
        # by excluding the ones we don't want
        filters = CopyFilters(exclude_permission_sets=["DeveloperAccess"])

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 3
        # Should include both AdministratorAccess assignments and ReadOnlyAccess
        permission_set_names = [assignment.permission_set_name for assignment in result]
        assert "AdministratorAccess" in permission_set_names
        assert "ReadOnlyAccess" in permission_set_names
        assert "DeveloperAccess" not in permission_set_names

    def test_apply_filters_include_accounts(self, filter_engine, sample_assignments):
        """Test filtering by including specific accounts."""
        filters = CopyFilters(include_accounts=["123456789012", "098765432109"])

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 2
        # Should only include assignments from specified accounts
        account_ids = [assignment.account_id for assignment in result]
        assert "123456789012" in account_ids
        assert "098765432109" in account_ids
        assert "555555555555" not in account_ids
        assert "111111111111" not in account_ids

    def test_apply_filters_exclude_accounts(self, filter_engine, sample_assignments):
        """Test filtering by excluding specific accounts."""
        filters = CopyFilters(exclude_accounts=["555555555555", "111111111111"])

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 2
        # Should exclude assignments from specified accounts
        account_ids = [assignment.account_id for assignment in result]
        assert "555555555555" not in account_ids
        assert "111111111111" not in account_ids
        assert "123456789012" in account_ids
        assert "098765432109" in account_ids

    def test_apply_filters_combined_include_exclude(self, filter_engine, sample_assignments):
        """Test combining include and exclude filters."""
        filters = CopyFilters(
            exclude_permission_sets=["DeveloperAccess"],
            exclude_accounts=["111111111111"],
        )

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 2
        # Should include AdministratorAccess and ReadOnlyAccess, but exclude account 111111111111
        permission_set_names = [assignment.permission_set_name for assignment in result]
        account_ids = [assignment.account_id for assignment in result]

        assert "AdministratorAccess" in permission_set_names
        assert "ReadOnlyAccess" in permission_set_names
        assert "DeveloperAccess" not in permission_set_names
        assert "111111111111" not in account_ids

    def test_apply_filters_complex_combination(self, filter_engine, sample_assignments):
        """Test complex filter combination."""
        filters = CopyFilters(
            exclude_permission_sets=["DeveloperAccess", "ReadOnlyAccess"],
            include_accounts=["123456789012"],
            exclude_accounts=["111111111111"],
        )

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 1
        # Should only include AdministratorAccess from account 123456789012
        assignment = result[0]
        assert assignment.permission_set_name == "AdministratorAccess"
        assert assignment.account_id == "123456789012"

    def test_apply_filters_empty_result(self, filter_engine, sample_assignments):
        """Test filtering that results in no matches."""
        filters = CopyFilters(
            exclude_permission_sets=["AdministratorAccess", "ReadOnlyAccess", "DeveloperAccess"]
        )

        result = filter_engine.apply_filters(sample_assignments, filters)

        assert len(result) == 0

    def test_validate_filters_no_filters(self, filter_engine):
        """Test validation of empty filters."""
        filters = CopyFilters()

        result = filter_engine.validate_filters(filters)

        assert result.has_warnings
        assert result.result_type == ValidationResultType.WARNING
        assert "No active filters specified" in result.messages[0]

    def test_validate_filters_none_filters(self, filter_engine):
        """Test validation of None filters."""
        result = filter_engine.validate_filters(None)

        assert result.has_warnings
        assert result.result_type == ValidationResultType.WARNING
        assert "No filters specified" in result.messages[0]

    def test_validate_filters_overlapping_permission_sets(self, filter_engine):
        """Test validation with overlapping permission set filters."""
        # Since CopyFilters no longer supports include_permission_sets,
        # we test overlapping accounts instead
        filters = CopyFilters(
            include_accounts=["123456789012", "098765432109"],
            exclude_accounts=["098765432109", "555555555555"],
        )

        result = filter_engine.validate_filters(filters)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "Accounts cannot be both included and excluded" in result.messages[0]
        assert "098765432109" in result.messages[0]

    def test_validate_filters_overlapping_accounts(self, filter_engine):
        """Test validation with overlapping account filters."""
        filters = CopyFilters(
            include_accounts=["123456789012", "098765432109"],
            exclude_accounts=["098765432109", "555555555555"],
        )

        result = filter_engine.validate_filters(filters)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "Accounts cannot be both included and excluded" in result.messages[0]
        assert "098765432109" in result.messages[0]

    def test_validate_filters_empty_permission_set_names(self, filter_engine):
        """Test validation with empty permission set names."""
        filters = CopyFilters(
            exclude_permission_sets=["Admin", ""], exclude_accounts=["", "Developer"]
        )

        result = filter_engine.validate_filters(filters)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        # The empty string in exclude_permission_sets triggers the empty name validation error
        assert "Exclude permission set names cannot be empty" in result.messages[0]
        assert "" in result.messages[0]

    def test_validate_filters_invalid_account_ids(self, filter_engine):
        """Test validation with invalid account IDs."""
        filters = CopyFilters(
            include_accounts=["123456789012", "invalid-id"],
            exclude_accounts=["098765432109", "123"],
        )

        result = filter_engine.validate_filters(filters)

        assert result.has_errors
        assert result.result_type == ValidationResultType.ERROR
        assert "Invalid account ID in include filter: invalid-id" in result.messages[0]
        assert "Invalid account ID in exclude filter: 123" in result.messages[1]

    def test_validate_filters_valid_filters(self, filter_engine):
        """Test validation of valid filters."""
        filters = CopyFilters(
            exclude_permission_sets=["Developer"], exclude_accounts=["555555555555"]
        )

        result = filter_engine.validate_filters(filters)

        assert result.is_valid
        assert result.result_type == ValidationResultType.SUCCESS
        assert len(result.messages) == 0

    def test_get_filter_summary_no_filters(self, filter_engine):
        """Test filter summary with no filters."""
        filters = CopyFilters()

        summary = filter_engine.get_filter_summary(filters)

        assert summary == "No filters applied"

    def test_get_filter_summary_none_filters(self, filter_engine):
        """Test filter summary with None filters."""
        summary = filter_engine.get_filter_summary(None)

        assert summary == "No filters applied"

    def test_get_filter_summary_with_filters(self, filter_engine):
        """Test filter summary with active filters."""
        filters = CopyFilters(
            exclude_permission_sets=["Developer"],
            include_accounts=["123456789012"],
            exclude_accounts=["555555555555"],
        )

        summary = filter_engine.get_filter_summary(filters)

        assert "Exclude permission sets: Developer" in summary
        assert "Include accounts: 123456789012" in summary
        assert "Exclude accounts: 555555555555" in summary

    def test_get_filter_stats(self, filter_engine):
        """Test filter statistics calculation."""
        original_count = 100
        filtered_count = 75

        stats = filter_engine.get_filter_stats(original_count, filtered_count)

        assert stats["original_count"] == 100
        assert stats["filtered_count"] == 75
        assert stats["excluded_count"] == 25
        assert stats["exclusion_rate_percent"] == 25.0

    def test_get_filter_stats_zero_original(self, filter_engine):
        """Test filter statistics with zero original count."""
        stats = filter_engine.get_filter_stats(0, 0)

        assert stats["original_count"] == 0
        assert stats["filtered_count"] == 0
        assert stats["excluded_count"] == 0
        assert stats["exclusion_rate_percent"] == 0.0

    def test_get_filter_stats_perfect_match(self, filter_engine):
        """Test filter statistics with perfect match."""
        stats = filter_engine.get_filter_stats(50, 50)

        assert stats["original_count"] == 50
        assert stats["filtered_count"] == 50
        assert stats["excluded_count"] == 0
        assert stats["exclusion_rate_percent"] == 0.0

    def test_has_active_filters_no_filters(self, filter_engine):
        """Test checking for active filters with no filters."""
        filters = CopyFilters()

        result = filter_engine._has_active_filters(filters)

        assert result is False

    def test_has_active_filters_none_filters(self, filter_engine):
        """Test checking for active filters with None filters."""
        result = filter_engine._has_active_filters(None)

        assert result is False

    def test_has_active_filters_with_filters(self, filter_engine):
        """Test checking for active filters with active filters."""
        filters = CopyFilters(exclude_permission_sets=["Admin"])

        result = filter_engine._has_active_filters(filters)

        assert result is True

    def test_is_valid_account_id_valid(self, filter_engine):
        """Test account ID validation with valid IDs."""
        valid_ids = ["123456789012", "098765432109", "555555555555"]

        for account_id in valid_ids:
            assert filter_engine._is_valid_account_id(account_id) is True

    def test_is_valid_account_id_invalid(self, filter_engine):
        """Test account ID validation with invalid IDs."""
        invalid_ids = [
            "",  # Empty
            "   ",  # Whitespace only
            "12345678901",  # Too short
            "1234567890123",  # Too long
            "12345678901a",  # Contains non-digit
            "abc123def456",  # Contains letters
            "123-456-789",  # Contains hyphens
        ]

        for account_id in invalid_ids:
            assert filter_engine._is_valid_account_id(account_id) is False

    def test_permission_set_matches_filters_include_only(self, filter_engine):
        """Test permission set filtering with include filter only."""
        # Since CopyFilters no longer supports include_permission_sets,
        # we test with exclude_permission_sets instead
        filters = CopyFilters(exclude_permission_sets=["Developer", "Testing"])

        # Should match (not excluded)
        assert filter_engine._permission_set_matches_filters("Admin", filters) is True
        assert filter_engine._permission_set_matches_filters("ReadOnly", filters) is True

        # Should not match (excluded)
        assert filter_engine._permission_set_matches_filters("Developer", filters) is False

    def test_permission_set_matches_filters_exclude_only(self, filter_engine):
        """Test permission set filtering with exclude filter only."""
        filters = CopyFilters(exclude_permission_sets=["Developer", "Testing"])

        # Should match (not excluded)
        assert filter_engine._permission_set_matches_filters("Admin", filters) is True
        assert filter_engine._permission_set_matches_filters("ReadOnly", filters) is True

        # Should not match (excluded)
        assert filter_engine._permission_set_matches_filters("Developer", filters) is False
        assert filter_engine._permission_set_matches_filters("Testing", filters) is False

    def test_permission_set_matches_filters_combined(self, filter_engine):
        """Test permission set filtering with exclude filters only."""
        filters = CopyFilters(exclude_permission_sets=["Testing", "Developer"])

        # Should match (not excluded)
        assert filter_engine._permission_set_matches_filters("Admin", filters) is True
        assert filter_engine._permission_set_matches_filters("ReadOnly", filters) is True

        # Should not match (excluded)
        assert filter_engine._permission_set_matches_filters("Testing", filters) is False
        assert filter_engine._permission_set_matches_filters("Developer", filters) is False

    def test_account_matches_filters_include_only(self, filter_engine):
        """Test account filtering with include filter only."""
        filters = CopyFilters(include_accounts=["123456789012", "098765432109"])

        # Should match
        assert filter_engine._account_matches_filters("123456789012", filters) is True
        assert filter_engine._account_matches_filters("098765432109", filters) is True

        # Should not match
        assert filter_engine._account_matches_filters("555555555555", filters) is False

    def test_account_matches_filters_exclude_only(self, filter_engine):
        """Test account filtering with exclude filter only."""
        filters = CopyFilters(exclude_accounts=["555555555555", "111111111111"])

        # Should match (not excluded)
        assert filter_engine._account_matches_filters("123456789012", filters) is True
        assert filter_engine._account_matches_filters("098765432109", filters) is True

        # Should not match (excluded)
        assert filter_engine._account_matches_filters("555555555555", filters) is False
        assert filter_engine._account_matches_filters("111111111111", filters) is False

    def test_account_matches_filters_combined(self, filter_engine):
        """Test account filtering with both include and exclude filters."""
        filters = CopyFilters(
            include_accounts=["123456789012", "098765432109"], exclude_accounts=["111111111111"]
        )

        # Should match (included and not excluded)
        assert filter_engine._account_matches_filters("123456789012", filters) is True
        assert filter_engine._account_matches_filters("098765432109", filters) is True

        # Should not match (excluded)
        assert filter_engine._account_matches_filters("111111111111", filters) is False

        # Should not match (not included)
        assert filter_engine._account_matches_filters("555555555555", filters) is False

    def test_assignment_matches_filters_complex(self, filter_engine):
        """Test complex assignment filtering."""
        filters = CopyFilters(
            exclude_permission_sets=["Testing", "Developer"],
            include_accounts=["123456789012"],
            exclude_accounts=["111111111111"],
        )

        # Create test assignments
        matching_assignment = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            permission_set_name="Admin",
            account_id="123456789012",
            account_name="Production",
        )

        non_matching_permission_set = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-developer",
            permission_set_name="Developer",
            account_id="123456789012",
            account_name="Production",
        )

        non_matching_account = PermissionAssignment(
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            permission_set_name="Admin",
            account_id="555555555555",
            account_name="Staging",
        )

        # Test matching assignment
        assert filter_engine._assignment_matches_filters(matching_assignment, filters) is True

        # Test non-matching permission set
        assert (
            filter_engine._assignment_matches_filters(non_matching_permission_set, filters) is False
        )

        # Test non-matching account
        assert filter_engine._assignment_matches_filters(non_matching_account, filters) is False
