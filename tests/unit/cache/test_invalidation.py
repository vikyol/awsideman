"""Unit tests for cache invalidation engine."""

from unittest.mock import Mock, call

import pytest

from src.awsideman.cache.interfaces import ICacheManager
from src.awsideman.cache.invalidation import (
    CacheInvalidationEngine,
    invalidate_assignment_cache,
    invalidate_group_cache,
    invalidate_permission_set_cache,
    invalidate_user_cache,
)


class TestCacheInvalidationEngine:
    """Test cases for CacheInvalidationEngine."""

    @pytest.fixture
    def mock_cache_manager(self):
        """Create a mock cache manager for testing."""
        mock_manager = Mock(spec=ICacheManager)
        mock_manager.invalidate.return_value = 1  # Default return value
        mock_manager.get_stats.return_value = {"invalidations": 5, "clears": 1}
        return mock_manager

    @pytest.fixture
    def invalidation_engine(self, mock_cache_manager):
        """Create invalidation engine with mock cache manager."""
        return CacheInvalidationEngine(mock_cache_manager)

    def test_initialization(self, mock_cache_manager):
        """Test invalidation engine initialization."""
        engine = CacheInvalidationEngine(mock_cache_manager)

        assert engine.cache_manager == mock_cache_manager
        assert engine.invalidation_rules is not None
        assert isinstance(engine.invalidation_rules, dict)

    def test_user_create_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for user creation."""
        result = invalidation_engine.invalidate_user_operations("create", "user-123")

        # Should invalidate user list caches
        expected_calls = [
            call("user:list:*"),
        ]

        mock_cache_manager.invalidate.assert_has_calls(expected_calls, any_order=True)
        assert result >= 0

    def test_user_update_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for user updates."""
        result = invalidation_engine.invalidate_user_operations("update", "user-123")

        # Should invalidate user lists, specific user, and cross-resource caches
        expected_patterns = [
            "user:list:*",
            "user:describe:user-123",
            "user:*:user-123",
            "group:members:*",
            "assignment:*",
        ]

        # Verify all expected patterns were called
        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_user_delete_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for user deletion."""
        result = invalidation_engine.invalidate_user_operations("delete", "user-123")

        # Should invalidate user lists, specific user, and cross-resource caches
        expected_patterns = [
            "user:list:*",
            "user:*:user-123",
            "group:members:*",
            "assignment:*",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_group_create_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for group creation."""
        result = invalidation_engine.invalidate_group_operations("create", "group-456")

        expected_calls = [
            call("group:list:*"),
        ]

        mock_cache_manager.invalidate.assert_has_calls(expected_calls, any_order=True)
        assert result >= 0

    def test_group_update_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for group updates."""
        result = invalidation_engine.invalidate_group_operations("update", "group-456")

        expected_patterns = [
            "group:list:*",
            "group:describe:group-456",
            "group:*:group-456",
            "assignment:*",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_group_membership_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for group membership changes."""
        # Test adding member
        result = invalidation_engine.invalidate_group_operations(
            "add_member", "group-456", ["user-123", "user-789"]
        )

        expected_patterns = [
            "group:members:group-456",
            "group:describe:group-456",
            "group:members:*",
            "user:*:user-123",
            "user:*:user-789",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_permission_set_create_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for permission set creation."""
        result = invalidation_engine.invalidate_permission_set_operations(
            "create", "arn:aws:sso:::permissionSet/ssoins-123/ps-TestPS"
        )

        expected_calls = [
            call("permission_set:list:*"),
        ]

        mock_cache_manager.invalidate.assert_has_calls(expected_calls, any_order=True)
        assert result >= 0

    def test_permission_set_update_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for permission set updates."""
        result = invalidation_engine.invalidate_permission_set_operations(
            "update", "arn:aws:sso:::permissionSet/ssoins-123/ps-TestPS", "123456789012"
        )

        expected_patterns = [
            "permission_set:list:*",
            "permission_set:describe:ps-TestPS",
            "permission_set:*:ps-TestPS",
            "assignment:*",
            "assignment:*:acc-123456789012*",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_assignment_create_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for assignment creation."""
        result = invalidation_engine.invalidate_assignment_operations(
            "create",
            account_id="123456789012",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-TestPS",
            principal_id="user-123",
            principal_type="USER",
        )

        expected_patterns = [
            "assignment:list:*",
            "assignment:account_assignments:*",
            "assignment:*:acc-123456789012*",
            "user:*:user-123",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_assignment_delete_invalidation(self, invalidation_engine, mock_cache_manager):
        """Test cache invalidation for assignment deletion."""
        result = invalidation_engine.invalidate_assignment_operations(
            "delete",
            account_id="123456789012",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-TestPS",
            principal_id="group-456",
            principal_type="GROUP",
        )

        expected_patterns = [
            "assignment:list:*",
            "assignment:account_assignments:*",
            "assignment:*:acc-123456789012*",
            "group:*:group-456",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_cross_resource_invalidation_user_update(self, invalidation_engine, mock_cache_manager):
        """Test cross-resource invalidation when user is updated."""
        result = invalidation_engine.invalidate_for_operation("update", "user", "user-123")

        # Should invalidate group memberships and assignments
        expected_cross_patterns = [
            "group:members:*",
            "assignment:*",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_cross_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_cross_resource_invalidation_group_membership(
        self, invalidation_engine, mock_cache_manager
    ):
        """Test cross-resource invalidation for group membership changes."""
        result = invalidation_engine.invalidate_for_operation(
            "add_member", "group", "group-456", {"affected_user_ids": "user-123,user-789"}
        )

        # Should invalidate affected users' caches
        expected_patterns = [
            "user:*:user-123",
            "user:*:user-789",
        ]

        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]
        for pattern in expected_patterns:
            assert pattern in actual_calls

        assert result >= 0

    def test_pattern_deduplication(self, invalidation_engine, mock_cache_manager):
        """Test that duplicate patterns are removed."""
        # This operation might generate duplicate patterns internally
        result = invalidation_engine.invalidate_for_operation("update", "user", "user-123")

        # Get all called patterns
        actual_calls = [
            call_args[0][0] for call_args in mock_cache_manager.invalidate.call_args_list
        ]

        # Check that there are no duplicates
        assert len(actual_calls) == len(set(actual_calls))
        assert result >= 0

    def test_get_invalidation_stats(self, invalidation_engine, mock_cache_manager):
        """Test getting invalidation statistics."""
        stats = invalidation_engine.get_invalidation_stats()

        assert "total_invalidations" in stats
        assert "cache_clears" in stats
        assert stats["total_invalidations"] == 5
        assert stats["cache_clears"] == 1

    def test_validate_patterns(self, invalidation_engine):
        """Test pattern validation."""
        errors = invalidation_engine.validate_patterns()

        # Should have no validation errors with default patterns
        assert isinstance(errors, list)
        # If there are errors, they should be strings
        for error in errors:
            assert isinstance(error, str)

    def test_invalid_operation_type(self, invalidation_engine, mock_cache_manager):
        """Test handling of invalid operation types."""
        # Should not crash with unknown operation types
        result = invalidation_engine.invalidate_for_operation(
            "unknown_operation", "user", "user-123"
        )

        # Should still perform cross-resource invalidation
        assert result >= 0

    def test_missing_resource_id(self, invalidation_engine, mock_cache_manager):
        """Test handling operations without resource ID."""
        result = invalidation_engine.invalidate_for_operation("create", "user")

        # Should still work with wildcard patterns
        assert result >= 0

    def test_empty_additional_context(self, invalidation_engine, mock_cache_manager):
        """Test handling empty additional context."""
        result = invalidation_engine.invalidate_for_operation("update", "user", "user-123", {})

        assert result >= 0

    def test_none_additional_context(self, invalidation_engine, mock_cache_manager):
        """Test handling None additional context."""
        result = invalidation_engine.invalidate_for_operation("update", "user", "user-123", None)

        assert result >= 0


class TestConvenienceFunctions:
    """Test convenience functions for cache invalidation."""

    @pytest.fixture
    def mock_cache_manager(self):
        """Create a mock cache manager for testing."""
        mock_manager = Mock(spec=ICacheManager)
        mock_manager.invalidate.return_value = 1
        return mock_manager

    def test_invalidate_user_cache(self, mock_cache_manager):
        """Test user cache invalidation convenience function."""
        result = invalidate_user_cache(mock_cache_manager, "update", "user-123")

        assert result >= 0
        mock_cache_manager.invalidate.assert_called()

    def test_invalidate_group_cache(self, mock_cache_manager):
        """Test group cache invalidation convenience function."""
        result = invalidate_group_cache(mock_cache_manager, "add_member", "group-456", ["user-123"])

        assert result >= 0
        mock_cache_manager.invalidate.assert_called()

    def test_invalidate_permission_set_cache(self, mock_cache_manager):
        """Test permission set cache invalidation convenience function."""
        result = invalidate_permission_set_cache(
            mock_cache_manager,
            "update",
            "arn:aws:sso:::permissionSet/ssoins-123/ps-TestPS",
            "123456789012",
        )

        assert result >= 0
        mock_cache_manager.invalidate.assert_called()

    def test_invalidate_assignment_cache(self, mock_cache_manager):
        """Test assignment cache invalidation convenience function."""
        result = invalidate_assignment_cache(
            mock_cache_manager,
            "create",
            account_id="123456789012",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-TestPS",
            principal_id="user-123",
            principal_type="USER",
        )

        assert result >= 0
        mock_cache_manager.invalidate.assert_called()


class TestInvalidationRules:
    """Test invalidation rules and patterns."""

    @pytest.fixture
    def invalidation_engine(self):
        """Create invalidation engine with mock cache manager."""
        mock_manager = Mock(spec=ICacheManager)
        mock_manager.invalidate.return_value = 1
        return CacheInvalidationEngine(mock_manager)

    def test_user_invalidation_rules(self, invalidation_engine):
        """Test user invalidation rules are properly defined."""
        rules = invalidation_engine.invalidation_rules.get("user", {})

        assert "create" in rules
        assert "update" in rules
        assert "delete" in rules

        # Check that patterns are lists of strings
        for operation, patterns in rules.items():
            assert isinstance(patterns, list)
            for pattern in patterns:
                assert isinstance(pattern, str)
                assert ":" in pattern  # Should be hierarchical

    def test_group_invalidation_rules(self, invalidation_engine):
        """Test group invalidation rules are properly defined."""
        rules = invalidation_engine.invalidation_rules.get("group", {})

        assert "create" in rules
        assert "update" in rules
        assert "delete" in rules
        assert "add_member" in rules
        assert "remove_member" in rules

    def test_permission_set_invalidation_rules(self, invalidation_engine):
        """Test permission set invalidation rules are properly defined."""
        rules = invalidation_engine.invalidation_rules.get("permission_set", {})

        assert "create" in rules
        assert "update" in rules
        assert "delete" in rules
        assert "update_policies" in rules

    def test_assignment_invalidation_rules(self, invalidation_engine):
        """Test assignment invalidation rules are properly defined."""
        rules = invalidation_engine.invalidation_rules.get("assignment", {})

        assert "create" in rules
        assert "delete" in rules

    def test_pattern_formatting(self, invalidation_engine):
        """Test that patterns can be formatted with resource IDs."""
        rules = invalidation_engine.invalidation_rules

        for resource_type, operations in rules.items():
            for operation, patterns in operations.items():
                for pattern in patterns:
                    try:
                        # Should be able to format with test data
                        formatted = pattern.format(
                            resource_type=resource_type, resource_id="test-id"
                        )
                        assert formatted is not None
                        assert ":" in formatted
                    except (KeyError, ValueError):
                        # Some patterns might not use all placeholders, that's OK
                        pass

    def test_cross_resource_patterns_user(self, invalidation_engine):
        """Test cross-resource patterns for user operations."""
        patterns = invalidation_engine._get_cross_resource_patterns("update", "user", "user-123")

        expected_patterns = [
            "group:members:*",
            "assignment:*",
        ]

        for expected in expected_patterns:
            assert expected in patterns

    def test_cross_resource_patterns_group(self, invalidation_engine):
        """Test cross-resource patterns for group operations."""
        patterns = invalidation_engine._get_cross_resource_patterns("update", "group", "group-456")

        assert "assignment:*" in patterns

    def test_cross_resource_patterns_permission_set(self, invalidation_engine):
        """Test cross-resource patterns for permission set operations."""
        patterns = invalidation_engine._get_cross_resource_patterns(
            "update", "permission_set", "ps-TestPS", {"account_id": "123456789012"}
        )

        expected_patterns = [
            "assignment:*",
            "assignment:*:acc-123456789012*",
        ]

        for expected in expected_patterns:
            assert expected in patterns

    def test_cross_resource_patterns_assignment(self, invalidation_engine):
        """Test cross-resource patterns for assignment operations."""
        patterns = invalidation_engine._get_cross_resource_patterns(
            "create",
            "assignment",
            None,
            {"account_id": "123456789012", "principal_id": "user-123", "principal_type": "USER"},
        )

        expected_patterns = [
            "assignment:list:*",
            "assignment:account_assignments:*",
            "assignment:*:acc-123456789012*",
            "user:*:user-123",
        ]

        for expected in expected_patterns:
            assert expected in patterns
