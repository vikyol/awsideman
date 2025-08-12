"""Integration tests for account filter optimization."""

from unittest.mock import Mock, patch

import pytest

from src.awsideman.utils.account_filter import AccountFilter, AccountInfo


class TestAccountFilterOptimization:
    """Test cases for account filter optimization integration."""

    @pytest.fixture
    def mock_organizations_client(self):
        """Create a mock organizations client."""
        return Mock()

    @pytest.fixture
    def sample_accounts(self):
        """Create sample account data for testing."""
        return [
            AccountInfo(
                account_id="123456789012",
                account_name="Production",
                email="prod@example.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Team": "Backend"},
                ou_path=["r-1234", "ou-prod"],
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="Development",
                email="dev@example.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Team": "Backend"},
                ou_path=["r-1234", "ou-dev"],
            ),
            AccountInfo(
                account_id="123456789014",
                account_name="Staging",
                email="staging@example.com",
                status="ACTIVE",
                tags={"Environment": "Staging", "Team": "Frontend"},
                ou_path=["r-1234", "ou-staging"],
            ),
        ]

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    def test_wildcard_filter_uses_optimizer(
        self, mock_optimizer_class, mock_organizations_client, sample_accounts
    ):
        """Test that wildcard filter uses the account cache optimizer."""
        # Setup mock optimizer
        mock_optimizer = Mock()
        mock_optimizer.get_all_accounts_optimized.return_value = sample_accounts
        mock_optimizer_class.return_value = mock_optimizer

        # Create filter and resolve accounts
        account_filter = AccountFilter("*", mock_organizations_client)
        result = account_filter.resolve_accounts()

        # Verify optimizer was created and used
        mock_optimizer_class.assert_called_once_with(mock_organizations_client)
        mock_optimizer.get_all_accounts_optimized.assert_called_once()

        # Verify results
        assert len(result) == 3
        assert result[0].account_id == "123456789012"
        assert result[1].account_id == "123456789013"
        assert result[2].account_id == "123456789014"

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    def test_tag_filter_uses_optimizer(
        self, mock_optimizer_class, mock_organizations_client, sample_accounts
    ):
        """Test that tag filter uses the account cache optimizer for base data."""
        # Setup mock optimizer
        mock_optimizer = Mock()
        mock_optimizer.get_all_accounts_optimized.return_value = sample_accounts
        mock_optimizer_class.return_value = mock_optimizer

        # Create tag filter and resolve accounts
        account_filter = AccountFilter("tag:Environment=Production", mock_organizations_client)
        result = account_filter.resolve_accounts()

        # Verify optimizer was used to get base account data
        mock_optimizer_class.assert_called_once_with(mock_organizations_client)
        mock_optimizer.get_all_accounts_optimized.assert_called_once()

        # Verify tag filtering worked correctly
        assert len(result) == 1
        assert result[0].account_id == "123456789012"
        assert result[0].tags["Environment"] == "Production"

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    def test_multiple_tag_filter(
        self, mock_optimizer_class, mock_organizations_client, sample_accounts
    ):
        """Test tag filter with multiple criteria."""
        # Setup mock optimizer
        mock_optimizer = Mock()
        mock_optimizer.get_all_accounts_optimized.return_value = sample_accounts
        mock_optimizer_class.return_value = mock_optimizer

        # Create multi-tag filter
        account_filter = AccountFilter(
            "tag:Environment=Development,Team=Backend", mock_organizations_client
        )
        result = account_filter.resolve_accounts()

        # Verify results - should match account with both tags
        assert len(result) == 1
        assert result[0].account_id == "123456789013"
        assert result[0].tags["Environment"] == "Development"
        assert result[0].tags["Team"] == "Backend"

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    def test_no_matching_tags(
        self, mock_optimizer_class, mock_organizations_client, sample_accounts
    ):
        """Test tag filter with no matching accounts."""
        # Setup mock optimizer
        mock_optimizer = Mock()
        mock_optimizer.get_all_accounts_optimized.return_value = sample_accounts
        mock_optimizer_class.return_value = mock_optimizer

        # Create filter for non-existent tag value
        account_filter = AccountFilter("tag:Environment=NonExistent", mock_organizations_client)
        result = account_filter.resolve_accounts()

        # Should return empty list
        assert len(result) == 0

    def test_filter_description_wildcard(self, mock_organizations_client):
        """Test filter description for wildcard filter."""
        account_filter = AccountFilter("*", mock_organizations_client)
        description = account_filter.get_filter_description()

        assert description == "All accounts in the organization"

    def test_filter_description_tag(self, mock_organizations_client):
        """Test filter description for tag filter."""
        account_filter = AccountFilter("tag:Environment=Production", mock_organizations_client)
        description = account_filter.get_filter_description()

        assert description == "Accounts with tags: Environment=Production"

    def test_filter_description_multiple_tags(self, mock_organizations_client):
        """Test filter description for multiple tag filter."""
        account_filter = AccountFilter(
            "tag:Environment=Production,Team=Backend", mock_organizations_client
        )
        description = account_filter.get_filter_description()

        assert "Environment=Production" in description
        assert "Team=Backend" in description

    def test_validation_empty_filter(self, mock_organizations_client):
        """Test validation of empty filter."""
        account_filter = AccountFilter("", mock_organizations_client)
        errors = account_filter.validate_filter()

        assert len(errors) == 1
        assert "cannot be empty" in errors[0].message

    def test_validation_invalid_tag_format(self, mock_organizations_client):
        """Test validation of invalid tag format."""
        # The AccountFilter constructor will raise ValueError for invalid format
        # So we need to catch it during validation, not construction
        try:
            account_filter = AccountFilter("tag:InvalidFormat", mock_organizations_client)
            errors = account_filter.validate_filter()
            # If we get here, validation should have caught the error
            assert len(errors) == 1
            assert "Expected format: Key=Value" in errors[0].message
        except ValueError as e:
            # This is expected - the constructor validates and raises immediately
            assert "Expected format: Key=Value" in str(e)

    def test_validation_valid_wildcard(self, mock_organizations_client):
        """Test validation of valid wildcard filter."""
        account_filter = AccountFilter("*", mock_organizations_client)
        errors = account_filter.validate_filter()

        assert len(errors) == 0

    def test_validation_valid_tag(self, mock_organizations_client):
        """Test validation of valid tag filter."""
        account_filter = AccountFilter("tag:Environment=Production", mock_organizations_client)
        errors = account_filter.validate_filter()

        assert len(errors) == 0
