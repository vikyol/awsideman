"""Tests for account cache clearing functionality."""

from unittest.mock import Mock

import pytest

from src.awsideman.utils.account_cache_optimizer import AccountCacheOptimizer


class TestAccountCacheClearing:
    """Test cases for account cache clearing."""

    @pytest.fixture
    def mock_cache_manager(self):
        """Create a mock cache manager."""
        cache_manager = Mock()
        cache_manager.get_cache_stats.return_value = {"total_entries": 456}
        cache_manager.invalidate.return_value = None
        return cache_manager

    @pytest.fixture
    def optimizer(self, mock_cache_manager):
        """Create an AccountCacheOptimizer instance."""
        return AccountCacheOptimizer(None, mock_cache_manager, profile="test-profile")

    def test_invalidate_specific_profile(self, optimizer, mock_cache_manager):
        """Test invalidating cache for a specific profile."""
        optimizer.invalidate_cache()

        # Should call invalidate for both org snapshot and account count
        assert mock_cache_manager.invalidate.call_count == 2

        # Check the keys that were invalidated
        call_args = [call[0][0] for call in mock_cache_manager.invalidate.call_args_list]
        assert "org_snapshot_v1_test-profile" in call_args
        assert "org_account_count_v1_test-profile" in call_args

    def test_invalidate_all_profiles(self, mock_cache_manager):
        """Test invalidating cache for all profiles."""
        optimizer = AccountCacheOptimizer(None, mock_cache_manager, profile="*")
        optimizer.invalidate_cache()

        # Should call invalidate multiple times for different patterns
        assert mock_cache_manager.invalidate.call_count > 2

    def test_force_clear_all_account_cache(self, optimizer, mock_cache_manager):
        """Test the aggressive cache clearing method."""
        # Mock cache stats to show entries before and after
        mock_cache_manager.get_cache_stats.side_effect = [
            {"total_entries": 456},  # Initial
            {"total_entries": 400},  # After partial clear
            {"total_entries": 0},  # Final
        ]

        cleared_count = optimizer.force_clear_all_account_cache()

        # Should have attempted to clear many entries
        assert cleared_count > 0
        assert mock_cache_manager.invalidate.call_count > 10

    def test_cache_key_patterns(self, optimizer):
        """Test that cache keys are properly formatted with profile."""
        assert optimizer.org_snapshot_key == "org_snapshot_v1_test-profile"
        assert optimizer.account_count_key == "org_account_count_v1_test-profile"

    def test_wildcard_profile_handling(self, mock_cache_manager):
        """Test handling of wildcard profile for clearing all profiles."""
        optimizer = AccountCacheOptimizer(None, mock_cache_manager, profile="*")

        # Should use wildcard profile
        assert optimizer.profile == "*"

        # Should have different cache keys (though they won't be used for wildcard)
        assert optimizer.org_snapshot_key == "org_snapshot_v1_*"
        assert optimizer.account_count_key == "org_account_count_v1_*"
