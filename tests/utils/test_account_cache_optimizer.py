"""Tests for the account cache optimizer."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from src.awsideman.utils.account_cache_optimizer import AccountCacheOptimizer
from src.awsideman.utils.account_filter import AccountInfo


class TestAccountCacheOptimizer:
    """Test cases for AccountCacheOptimizer."""

    @pytest.fixture
    def mock_organizations_client(self):
        """Create a mock organizations client."""
        return Mock()

    @pytest.fixture
    def mock_cache_manager(self):
        """Create a mock cache manager."""
        return Mock()

    @pytest.fixture
    def optimizer(self, mock_organizations_client, mock_cache_manager):
        """Create an AccountCacheOptimizer instance."""
        return AccountCacheOptimizer(mock_organizations_client, mock_cache_manager)

    @pytest.fixture
    def sample_accounts(self):
        """Create sample account data for testing."""
        return [
            AccountInfo(
                account_id="123456789012",
                account_name="Production",
                email="prod@example.com",
                status="ACTIVE",
                tags={"Environment": "Production"},
                ou_path=["r-1234", "ou-prod"],
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="Development",
                email="dev@example.com",
                status="ACTIVE",
                tags={"Environment": "Development"},
                ou_path=["r-1234", "ou-dev"],
            ),
        ]

    def test_cache_org_snapshot(self, optimizer, sample_accounts):
        """Test caching organization snapshot."""
        optimizer._cache_org_snapshot(sample_accounts)

        # Verify cache manager was called with correct data
        optimizer.cache_manager.set.assert_called_once()
        call_args = optimizer.cache_manager.set.call_args

        assert call_args[0][0] == optimizer.org_snapshot_key
        assert call_args[1]["ttl"] == AccountCacheOptimizer.ORG_SNAPSHOT_TTL
        assert call_args[1]["operation"] == "org_snapshot"

        # Check the cached data structure
        cached_data = call_args[0][1]
        assert cached_data["total_count"] == 2
        assert len(cached_data["accounts"]) == 2
        assert cached_data["accounts"][0]["account_id"] == "123456789012"

    def test_get_cached_org_snapshot_valid(self, optimizer, sample_accounts):
        """Test retrieving valid cached organization snapshot."""
        # Mock cached data
        cached_data = {
            "accounts": [
                {
                    "account_id": "123456789012",
                    "account_name": "Production",
                    "email": "prod@example.com",
                    "status": "ACTIVE",
                    "tags": {"Environment": "Production"},
                    "ou_path": ["r-1234", "ou-prod"],
                }
            ],
            "total_count": 1,
            "cached_at": datetime.now().isoformat(),
        }

        optimizer.cache_manager.get.return_value = cached_data

        result = optimizer._get_cached_org_snapshot()

        assert result is not None
        assert len(result.accounts) == 1
        assert result.accounts[0].account_id == "123456789012"
        assert result.total_count == 1

    def test_get_cached_org_snapshot_invalid(self, optimizer):
        """Test retrieving invalid cached organization snapshot."""
        # Mock invalid cached data
        optimizer.cache_manager.get.return_value = {"invalid": "data"}

        result = optimizer._get_cached_org_snapshot()

        assert result is None

    def test_get_cached_org_snapshot_missing(self, optimizer):
        """Test retrieving missing cached organization snapshot."""
        optimizer.cache_manager.get.return_value = None

        result = optimizer._get_cached_org_snapshot()

        assert result is None

    def test_cache_account_count(self, optimizer):
        """Test caching account count."""
        optimizer._cache_account_count(29)

        optimizer.cache_manager.set.assert_called_once_with(
            optimizer.account_count_key,
            29,
            ttl=AccountCacheOptimizer.ACCOUNT_COUNT_TTL,
            operation="account_count",
        )

    def test_get_cached_account_count(self, optimizer):
        """Test retrieving cached account count."""
        optimizer.cache_manager.get.return_value = 29

        result = optimizer._get_cached_account_count()

        assert result == 29
        optimizer.cache_manager.get.assert_called_once_with(optimizer.account_count_key)

    @patch("src.awsideman.aws_clients.manager.build_organization_hierarchy")
    def test_get_current_account_count(self, mock_build_hierarchy, optimizer):
        """Test getting current account count."""
        # Mock organization tree with accounts
        mock_account_node1 = Mock()
        mock_account_node1.is_account.return_value = True
        mock_account_node1.children = []

        mock_account_node2 = Mock()
        mock_account_node2.is_account.return_value = True
        mock_account_node2.children = []

        mock_ou_node = Mock()
        mock_ou_node.is_account.return_value = False
        mock_ou_node.children = [mock_account_node1, mock_account_node2]

        mock_root_node = Mock()
        mock_root_node.is_account.return_value = False
        mock_root_node.children = [mock_ou_node]

        mock_build_hierarchy.return_value = [mock_root_node]

        result = optimizer._get_current_account_count()

        assert result == 2

    def test_invalidate_cache(self, optimizer):
        """Test cache invalidation."""
        optimizer.invalidate_cache()

        # Verify both cache keys were deleted
        expected_calls = [((optimizer.org_snapshot_key,), {}), ((optimizer.account_count_key,), {})]

        assert optimizer.cache_manager.delete.call_count == 2
        actual_calls = optimizer.cache_manager.delete.call_args_list

        for expected_call in expected_calls:
            assert expected_call in actual_calls

    def test_get_cache_stats(self, optimizer):
        """Test getting cache statistics."""
        # Mock cached snapshot
        cached_data = {
            "accounts": [],
            "total_count": 0,
            "cached_at": (datetime.now() - timedelta(hours=2)).isoformat(),
        }
        optimizer.cache_manager.get.side_effect = [cached_data, 29]

        stats = optimizer.get_cache_stats()

        assert stats["org_snapshot_cached"] is True
        assert stats["account_count_cached"] is True
        assert stats["org_snapshot_age_seconds"] is not None
        assert stats["org_snapshot_age_seconds"] > 7000  # About 2 hours

    def test_get_all_accounts_optimized_with_cache(self, optimizer, sample_accounts):
        """Test optimized account retrieval with valid cache."""
        # Mock cached snapshot
        cached_data = {
            "accounts": [
                {
                    "account_id": "123456789012",
                    "account_name": "Production",
                    "email": "prod@example.com",
                    "status": "ACTIVE",
                    "tags": {"Environment": "Production"},
                    "ou_path": ["r-1234", "ou-prod"],
                }
            ],
            "total_count": 1,
            "cached_at": datetime.now().isoformat(),
        }

        optimizer.cache_manager.get.return_value = cached_data

        result = optimizer.get_all_accounts_optimized()

        assert len(result) == 1
        assert result[0].account_id == "123456789012"

        # Should not call fresh fetch methods
        optimizer.cache_manager.get.assert_called_once()

    def test_get_all_accounts_optimized_fresh_fetch(self, optimizer):
        """Test optimized account retrieval with fresh fetch."""
        # Mock no cached data - return None for all cache lookups
        optimizer.cache_manager.get.return_value = None

        # Mock the _fetch_all_accounts_fresh method to return sample data
        sample_account = AccountInfo(
            account_id="123456789012",
            account_name="Production",
            email="prod@example.com",
            status="ACTIVE",
            tags={"Environment": "Production"},
            ou_path=["r-1234", "ou-prod"],
        )

        optimizer._fetch_all_accounts_fresh = Mock(return_value=[sample_account])

        result = optimizer.get_all_accounts_optimized()

        assert len(result) == 1
        assert result[0].account_id == "123456789012"

        # Should have called fresh fetch method
        optimizer._fetch_all_accounts_fresh.assert_called_once()

        # Should have cached the results
        assert optimizer.cache_manager.set.call_count >= 1  # At least the org snapshot
