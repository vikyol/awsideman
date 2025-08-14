"""Tests for the search_accounts function in aws_client.py."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from src.awsideman.aws_clients.manager import (
    _account_matches_ou_filter,
    _account_matches_tag_filter,
    search_accounts,
)
from src.awsideman.utils.models import AccountDetails


@pytest.fixture
def sample_accounts():
    """Sample account details for testing."""
    return [
        AccountDetails(
            id="111111111111",
            name="dev-account",
            email="dev@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc),
            tags={"Environment": "Development", "Team": "Engineering"},
            ou_path=["Root", "Engineering", "Development"],
        ),
        AccountDetails(
            id="222222222222",
            name="prod-account",
            email="prod@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 2, 1, tzinfo=timezone.utc),
            tags={"Environment": "Production", "Team": "Engineering"},
            ou_path=["Root", "Engineering", "Production"],
        ),
        AccountDetails(
            id="333333333333",
            name="test-account",
            email="test@example.com",
            status="ACTIVE",
            joined_timestamp=datetime(2021, 3, 1, tzinfo=timezone.utc),
            tags={"Environment": "Testing", "Team": "QA"},
            ou_path=["Root", "QA"],
        ),
    ]


def test_search_accounts_case_insensitive(sample_accounts):
    """Test that search is case-insensitive."""
    mock_org_client = Mock()

    with (
        patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all,
        patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details,
    ):
        # Mock the account data returned by _get_all_accounts_in_organization
        mock_get_all.return_value = [
            {"Id": "111111111111", "Name": "dev-account"},
            {"Id": "222222222222", "Name": "prod-account"},
            {"Id": "333333333333", "Name": "test-account"},
        ]

        # Mock get_account_details to return our sample accounts
        mock_get_details.side_effect = lambda client, account_id: next(
            acc for acc in sample_accounts if acc.id == account_id
        )

        # Test case-insensitive search
        results = search_accounts(mock_org_client, "DEV")

        assert len(results) == 1
        assert results[0].name == "dev-account"
        assert results[0].id == "111111111111"


def test_search_accounts_partial_match(sample_accounts):
    """Test that search supports partial string matching."""
    mock_org_client = Mock()

    with (
        patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all,
        patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details,
    ):
        mock_get_all.return_value = [
            {"Id": "111111111111", "Name": "dev-account"},
            {"Id": "222222222222", "Name": "prod-account"},
            {"Id": "333333333333", "Name": "test-account"},
        ]

        mock_get_details.side_effect = lambda client, account_id: next(
            acc for acc in sample_accounts if acc.id == account_id
        )

        # Test partial match - should find all accounts containing "account"
        results = search_accounts(mock_org_client, "account")

        assert len(results) == 3
        account_names = [acc.name for acc in results]
        assert "dev-account" in account_names
        assert "prod-account" in account_names
        assert "test-account" in account_names


def test_search_accounts_with_ou_filter(sample_accounts):
    """Test search with OU filter."""
    mock_org_client = Mock()

    with (
        patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all,
        patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details,
    ):
        mock_get_all.return_value = [
            {"Id": "111111111111", "Name": "dev-account"},
            {"Id": "222222222222", "Name": "prod-account"},
            {"Id": "333333333333", "Name": "test-account"},
        ]

        mock_get_details.side_effect = lambda client, account_id: next(
            acc for acc in sample_accounts if acc.id == account_id
        )

        # Test OU filter - should only return accounts in Engineering OU
        results = search_accounts(mock_org_client, "account", ou_filter="Engineering")

        assert len(results) == 2
        account_names = [acc.name for acc in results]
        assert "dev-account" in account_names
        assert "prod-account" in account_names
        assert "test-account" not in account_names


def test_search_accounts_with_tag_filter(sample_accounts):
    """Test search with tag filter."""
    mock_org_client = Mock()

    with (
        patch(
            "src.awsideman.aws_clients.manager._get_all_accounts_in_organization"
        ) as mock_get_all,
        patch("src.awsideman.aws_clients.manager.get_account_details") as mock_get_details,
    ):
        mock_get_all.return_value = [
            {"Id": "111111111111", "Name": "dev-account"},
            {"Id": "222222222222", "Name": "prod-account"},
            {"Id": "333333333333", "Name": "test-account"},
        ]

        mock_get_details.side_effect = lambda client, account_id: next(
            acc for acc in sample_accounts if acc.id == account_id
        )

        # Test tag filter - should only return accounts with Team=Engineering
        results = search_accounts(mock_org_client, "account", tag_filter={"Team": "Engineering"})

        assert len(results) == 2
        account_names = [acc.name for acc in results]
        assert "dev-account" in account_names
        assert "prod-account" in account_names
        assert "test-account" not in account_names


def test_search_accounts_empty_query():
    """Test that empty query raises ValueError."""
    mock_org_client = Mock()

    with pytest.raises(ValueError, match="Search query cannot be empty"):
        search_accounts(mock_org_client, "")

    with pytest.raises(ValueError, match="Search query cannot be empty"):
        search_accounts(mock_org_client, "   ")


def test_account_matches_ou_filter(sample_accounts):
    """Test the OU filter matching function."""
    dev_account = sample_accounts[0]  # Has OU path: ["Root", "Engineering", "Development"]
    qa_account = sample_accounts[2]  # Has OU path: ["Root", "QA"]

    # Test exact OU match
    assert _account_matches_ou_filter(dev_account, "Engineering")
    assert _account_matches_ou_filter(dev_account, "Development")
    assert _account_matches_ou_filter(dev_account, "Root")
    assert not _account_matches_ou_filter(dev_account, "QA")

    assert _account_matches_ou_filter(qa_account, "QA")
    assert not _account_matches_ou_filter(qa_account, "Engineering")


def test_account_matches_tag_filter(sample_accounts):
    """Test the tag filter matching function."""
    dev_account = sample_accounts[
        0
    ]  # Has tags: {"Environment": "Development", "Team": "Engineering"}
    qa_account = sample_accounts[2]  # Has tags: {"Environment": "Testing", "Team": "QA"}

    # Test single tag match
    assert _account_matches_tag_filter(dev_account, {"Environment": "Development"})
    assert _account_matches_tag_filter(dev_account, {"Team": "Engineering"})
    assert not _account_matches_tag_filter(dev_account, {"Environment": "Production"})
    assert not _account_matches_tag_filter(dev_account, {"Team": "QA"})
    assert _account_matches_tag_filter(qa_account, {"Team": "QA"})

    # Test multiple tag match (all must match)
    assert _account_matches_tag_filter(
        dev_account, {"Environment": "Development", "Team": "Engineering"}
    )
    assert not _account_matches_tag_filter(
        dev_account, {"Environment": "Development", "Team": "QA"}
    )

    # Test non-existent tag
    assert not _account_matches_tag_filter(dev_account, {"NonExistent": "Value"})
