"""Comprehensive tests for enhanced account filtering features."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import OrganizationsClientWrapper
from src.awsideman.utils.account_filter import AccountFilter, AccountInfo, FilterType


class TestExplicitAccountListFiltering:
    """Comprehensive tests for explicit account list filtering (Requirements 7.1, 7.2)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_explicit_accounts_single_account(self):
        """Test explicit account filtering with single account."""
        account_filter = AccountFilter(
            explicit_accounts=["123456789012"], organizations_client=self.mock_org_client
        )

        assert account_filter.filter_type == FilterType.EXPLICIT
        assert account_filter.explicit_accounts == ["123456789012"]

        # Validate filter
        errors = account_filter.validate_filter()
        assert errors == []

    def test_explicit_accounts_multiple_accounts(self):
        """Test explicit account filtering with multiple accounts."""
        account_list = ["123456789012", "123456789013", "123456789014"]
        account_filter = AccountFilter(
            explicit_accounts=account_list, organizations_client=self.mock_org_client
        )

        assert account_filter.filter_type == FilterType.EXPLICIT
        assert account_filter.explicit_accounts == account_list

        # Validate filter
        errors = account_filter.validate_filter()
        assert errors == []

    def test_explicit_accounts_large_list(self):
        """Test explicit account filtering with large account list."""
        # Create a large list of account IDs (12 digits each)
        account_list = [f"12345678{i:04d}" for i in range(100)]
        account_filter = AccountFilter(
            explicit_accounts=account_list, organizations_client=self.mock_org_client
        )

        assert account_filter.filter_type == FilterType.EXPLICIT
        assert len(account_filter.explicit_accounts) == 100

        # Validate filter
        errors = account_filter.validate_filter()
        assert errors == []

    def test_explicit_accounts_validation_empty_list(self):
        """Test validation fails for empty explicit accounts list."""
        account_filter = AccountFilter(
            explicit_accounts=[], organizations_client=self.mock_org_client
        )

        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Explicit accounts list cannot be empty" in errors[0].message
        assert errors[0].field == "explicit_accounts"

    def test_explicit_accounts_validation_invalid_format(self):
        """Test validation fails for invalid account ID formats."""
        invalid_accounts = [
            "123456789012",  # Valid
            "invalid-id",  # Invalid format
            "12345678901",  # Too short
            "1234567890123",  # Too long
            "",  # Empty
            "   ",  # Whitespace only
            "abcdefghijkl",  # Non-numeric
        ]

        account_filter = AccountFilter(
            explicit_accounts=invalid_accounts, organizations_client=self.mock_org_client
        )

        errors = account_filter.validate_filter()

        # Should have errors for all invalid formats
        assert len(errors) >= 5  # At least 5 invalid accounts

        error_messages = [error.message for error in errors]
        assert any("Invalid account ID format: 'invalid-id'" in msg for msg in error_messages)
        assert any("Invalid account ID format: '12345678901'" in msg for msg in error_messages)
        assert any("Invalid account ID format: '1234567890123'" in msg for msg in error_messages)
        assert any("Account ID cannot be empty" in msg for msg in error_messages)
        assert any("Invalid account ID format: 'abcdefghijkl'" in msg for msg in error_messages)

    def test_explicit_accounts_validation_duplicate_ids(self):
        """Test explicit accounts with duplicate IDs."""
        account_list = ["123456789012", "123456789013", "123456789012"]  # Duplicate
        account_filter = AccountFilter(
            explicit_accounts=account_list, organizations_client=self.mock_org_client
        )

        # Should still be valid (duplicates are allowed, will be handled during resolution)
        errors = account_filter.validate_filter()
        assert errors == []

    def test_explicit_accounts_resolve_success(self):
        """Test successful resolution of explicit accounts."""
        account_list = ["123456789012", "123456789013"]

        # Mock describe_account responses
        def mock_describe_account(account_id):
            if account_id == "123456789012":
                return {
                    "Id": "123456789012",
                    "Name": "Production Account",
                    "Email": "prod@example.com",
                    "Status": "ACTIVE",
                    "Tags": {"Environment": "Production"},
                }
            elif account_id == "123456789013":
                return {
                    "Id": "123456789013",
                    "Name": "Development Account",
                    "Email": "dev@example.com",
                    "Status": "ACTIVE",
                    "Tags": {"Environment": "Development"},
                }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        account_filter = AccountFilter(
            explicit_accounts=account_list, organizations_client=self.mock_org_client
        )

        accounts = account_filter.resolve_accounts()

        assert len(accounts) == 2
        assert accounts[0].account_id == "123456789012"
        assert accounts[0].account_name == "Production Account"
        assert accounts[0].tags == {"Environment": "Production"}
        assert accounts[1].account_id == "123456789013"
        assert accounts[1].account_name == "Development Account"
        assert accounts[1].tags == {"Environment": "Development"}

    def test_explicit_accounts_resolve_account_not_found(self):
        """Test resolution fails when account doesn't exist."""

        def mock_describe_account(account_id):
            raise ClientError(
                error_response={"Error": {"Code": "AccountNotFoundException"}},
                operation_name="DescribeAccount",
            )

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        account_filter = AccountFilter(
            explicit_accounts=["999999999999"], organizations_client=self.mock_org_client
        )

        with pytest.raises(
            ValueError, match="Account ID '999999999999' does not exist or is not accessible"
        ):
            account_filter.resolve_accounts()

    def test_explicit_accounts_resolve_access_denied(self):
        """Test resolution fails when access is denied to account."""

        def mock_describe_account(account_id):
            raise ClientError(
                error_response={"Error": {"Code": "AccessDeniedException"}},
                operation_name="DescribeAccount",
            )

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        account_filter = AccountFilter(
            explicit_accounts=["123456789012"], organizations_client=self.mock_org_client
        )

        with pytest.raises(ValueError, match="Access denied to account ID '123456789012'"):
            account_filter.resolve_accounts()

    def test_explicit_accounts_streaming_resolution(self):
        """Test streaming resolution of explicit accounts."""
        account_list = ["123456789012", "123456789013", "123456789014"]

        # Mock describe_account responses
        def mock_describe_account(account_id):
            return {
                "Id": account_id,
                "Name": f"Account-{account_id}",
                "Email": f"{account_id}@example.com",
                "Status": "ACTIVE",
                "Tags": {},
            }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        account_filter = AccountFilter(
            explicit_accounts=account_list, organizations_client=self.mock_org_client
        )

        # Test streaming resolution
        accounts = list(account_filter.resolve_accounts_streaming(chunk_size=2))

        assert len(accounts) == 3
        for i, account in enumerate(accounts):
            expected_id = account_list[i]
            assert account.account_id == expected_id
            assert account.account_name == f"Account-{expected_id}"

    def test_explicit_accounts_filter_description(self):
        """Test filter description for explicit accounts."""
        # Test short list
        account_filter = AccountFilter(
            explicit_accounts=["123456789012", "123456789013"],
            organizations_client=self.mock_org_client,
        )
        description = account_filter.get_filter_description()
        assert description == "Explicit accounts: 123456789012, 123456789013"

        # Test long list (should truncate)
        long_list = [f"12345678901{i:01d}" for i in range(10)]
        account_filter = AccountFilter(
            explicit_accounts=long_list, organizations_client=self.mock_org_client
        )
        description = account_filter.get_filter_description()
        assert "... (10 total)" in description
        assert "123456789010, 123456789011, 123456789012" in description


class TestOUBasedFiltering:
    """Comprehensive tests for OU-based filtering (Requirement 8.1)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_ou_filter_initialization(self):
        """Test OU filter initialization."""
        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )

        assert account_filter.filter_type == FilterType.OU
        assert account_filter.ou_filter == "Root/Production"

    def test_ou_filter_validation_valid_paths(self):
        """Test validation of valid OU paths."""
        valid_paths = [
            "Root",
            "Root/Production",
            "Root/Production/WebServices",
            "Root/Development/Testing/QA",
            "Root/Shared-Services",
            "Root/Security_Team",
        ]

        for path in valid_paths:
            account_filter = AccountFilter(
                ou_filter=path, organizations_client=self.mock_org_client
            )
            errors = account_filter.validate_filter()
            assert errors == [], f"Valid path '{path}' should not have validation errors"

    def test_ou_filter_validation_invalid_characters(self):
        """Test validation fails for OU paths with invalid characters."""
        invalid_paths = [
            "Root/Production<Invalid>",
            "Root/Production>Invalid",
            "Root/Production|Invalid",
            "Root/Production&Invalid",
            "Root/Production;Invalid",
        ]

        for path in invalid_paths:
            account_filter = AccountFilter(
                ou_filter=path, organizations_client=self.mock_org_client
            )
            errors = account_filter.validate_filter()
            assert len(errors) > 0, f"Invalid path '{path}' should have validation errors"
            assert any("invalid character" in error.message for error in errors)

    def test_ou_filter_validation_empty_path(self):
        """Test validation fails for empty OU path."""
        account_filter = AccountFilter(ou_filter="", organizations_client=self.mock_org_client)
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    def test_ou_filter_account_matching_exact(self):
        """Test account matching with exact OU path."""
        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )

        # Account with exact matching OU path
        account = AccountInfo(
            account_id="123456789012",
            account_name="Prod Account",
            email="prod@example.com",
            status="ACTIVE",
            tags={},
            ou_path=["Root", "Production"],
        )

        assert account_filter._account_matches_ou_filter(account) is True

    def test_ou_filter_account_matching_prefix(self):
        """Test account matching with OU path as prefix."""
        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )

        # Account with OU path that has the filter as prefix
        account = AccountInfo(
            account_id="123456789012",
            account_name="Prod Account",
            email="prod@example.com",
            status="ACTIVE",
            tags={},
            ou_path=["Root", "Production", "WebServices", "Frontend"],
        )

        assert account_filter._account_matches_ou_filter(account) is True

    def test_ou_filter_account_matching_no_match(self):
        """Test account not matching OU filter."""
        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )

        # Account with different OU path
        account = AccountInfo(
            account_id="123456789012",
            account_name="Dev Account",
            email="dev@example.com",
            status="ACTIVE",
            tags={},
            ou_path=["Root", "Development"],
        )

        assert account_filter._account_matches_ou_filter(account) is False

    def test_ou_filter_account_matching_partial_match(self):
        """Test account with partial OU path match (should not match)."""
        account_filter = AccountFilter(
            ou_filter="Root/Production/WebServices", organizations_client=self.mock_org_client
        )

        # Account with shorter OU path (partial match)
        account = AccountInfo(
            account_id="123456789012",
            account_name="Prod Account",
            email="prod@example.com",
            status="ACTIVE",
            tags={},
            ou_path=["Root", "Production"],
        )

        assert account_filter._account_matches_ou_filter(account) is False

    def test_ou_filter_account_matching_empty_ou_path(self):
        """Test account with empty OU path (should not match)."""
        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )

        # Account with empty OU path
        account = AccountInfo(
            account_id="123456789012",
            account_name="Account",
            email="account@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        assert account_filter._account_matches_ou_filter(account) is False

    def test_ou_filter_complex_organizational_structures(self):
        """Test OU filtering with complex organizational structures."""
        test_cases = [
            {"filter": "Root", "account_ou": ["Root"], "should_match": True},
            {"filter": "Root", "account_ou": ["Root", "Production"], "should_match": True},
            {
                "filter": "Root/Production/WebServices",
                "account_ou": ["Root", "Production", "WebServices"],
                "should_match": True,
            },
            {
                "filter": "Root/Production/WebServices",
                "account_ou": ["Root", "Production", "WebServices", "Frontend"],
                "should_match": True,
            },
            {
                "filter": "Root/Production/WebServices",
                "account_ou": ["Root", "Production", "DatabaseServices"],
                "should_match": False,
            },
            {
                "filter": "Root/Shared-Services",
                "account_ou": ["Root", "Shared-Services", "Security"],
                "should_match": True,
            },
            {
                "filter": "Root/Development/Testing",
                "account_ou": ["Root", "Development", "Integration"],
                "should_match": False,
            },
        ]

        for case in test_cases:
            account_filter = AccountFilter(
                ou_filter=case["filter"], organizations_client=self.mock_org_client
            )

            account = AccountInfo(
                account_id="123456789012",
                account_name="Test Account",
                email="test@example.com",
                status="ACTIVE",
                tags={},
                ou_path=case["account_ou"],
            )

            result = account_filter._account_matches_ou_filter(account)
            assert (
                result == case["should_match"]
            ), f"Filter '{case['filter']}' with OU path {case['account_ou']} should {'match' if case['should_match'] else 'not match'}"

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    def test_ou_filter_resolve_accounts(self, mock_optimizer_class):
        """Test resolving accounts with OU filter."""
        # Mock optimizer to return test accounts
        mock_optimizer = Mock()
        mock_optimizer_class.return_value = mock_optimizer

        test_accounts = [
            AccountInfo(
                account_id="123456789012",
                account_name="Prod Account 1",
                email="prod1@example.com",
                status="ACTIVE",
                tags={},
                ou_path=["Root", "Production"],
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="Prod Account 2",
                email="prod2@example.com",
                status="ACTIVE",
                tags={},
                ou_path=["Root", "Production", "WebServices"],
            ),
            AccountInfo(
                account_id="123456789014",
                account_name="Dev Account",
                email="dev@example.com",
                status="ACTIVE",
                tags={},
                ou_path=["Root", "Development"],
            ),
        ]

        mock_optimizer.get_all_accounts_optimized.return_value = test_accounts

        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )

        accounts = account_filter.resolve_accounts()

        # Should return only accounts in Production OU
        assert len(accounts) == 2
        assert accounts[0].account_id == "123456789012"
        assert accounts[1].account_id == "123456789013"

    def test_ou_filter_description(self):
        """Test filter description for OU filter."""
        account_filter = AccountFilter(
            ou_filter="Root/Production/WebServices", organizations_client=self.mock_org_client
        )
        description = account_filter.get_filter_description()
        assert description == "Accounts in organizational unit: Root/Production/WebServices"


class TestRegexPatternFiltering:
    """Comprehensive tests for regex-based account name pattern matching (Requirement 8.2)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_pattern_filter_initialization(self):
        """Test pattern filter initialization."""
        account_filter = AccountFilter(
            account_name_pattern="^prod-.*", organizations_client=self.mock_org_client
        )

        assert account_filter.filter_type == FilterType.PATTERN
        assert account_filter.account_name_pattern == "^prod-.*"

    def test_pattern_filter_validation_valid_patterns(self):
        """Test validation of valid regex patterns."""
        valid_patterns = [
            "^prod-.*",
            ".*-dev$",
            "test-\\d+",
            "[a-z]+-[0-9]+",
            "^(prod|staging|dev)-.*",
            "account-[A-Z]{2,3}-\\d{4}",
            ".*web.*",
            "^[^-]+-service$",
        ]

        for pattern in valid_patterns:
            account_filter = AccountFilter(
                account_name_pattern=pattern, organizations_client=self.mock_org_client
            )
            errors = account_filter.validate_filter()
            assert errors == [], f"Valid pattern '{pattern}' should not have validation errors"

    def test_pattern_filter_validation_invalid_patterns(self):
        """Test validation fails for invalid regex patterns."""
        invalid_patterns = [
            "[invalid",  # Unclosed bracket
            "(?P<invalid",  # Unclosed group
            "*invalid",  # Invalid quantifier
            "(?P<>invalid)",  # Empty group name
            "\\",  # Trailing backslash
            "(?P<123>test)",  # Invalid group name
        ]

        for pattern in invalid_patterns:
            account_filter = AccountFilter(
                account_name_pattern=pattern, organizations_client=self.mock_org_client
            )
            errors = account_filter.validate_filter()
            assert len(errors) > 0, f"Invalid pattern '{pattern}' should have validation errors"
            assert any("Invalid regex pattern" in error.message for error in errors)

    def test_pattern_filter_validation_empty_pattern(self):
        """Test validation fails for empty pattern."""
        account_filter = AccountFilter(
            account_name_pattern="", organizations_client=self.mock_org_client
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    def test_pattern_filter_account_matching_basic_patterns(self):
        """Test account matching with basic regex patterns."""
        test_cases = [
            {"pattern": "^prod-.*", "account_name": "prod-web-server", "should_match": True},
            {"pattern": "^prod-.*", "account_name": "dev-web-server", "should_match": False},
            {"pattern": ".*-dev$", "account_name": "web-server-dev", "should_match": True},
            {"pattern": ".*-dev$", "account_name": "web-server-prod", "should_match": False},
            {"pattern": "test-\\d+", "account_name": "test-123", "should_match": True},
            {"pattern": "test-\\d+", "account_name": "test-abc", "should_match": False},
        ]

        for case in test_cases:
            account_filter = AccountFilter(
                account_name_pattern=case["pattern"], organizations_client=self.mock_org_client
            )

            account = AccountInfo(
                account_id="123456789012",
                account_name=case["account_name"],
                email="test@example.com",
                status="ACTIVE",
                tags={},
                ou_path=[],
            )

            result = account_filter._account_matches_pattern_filter(account)
            assert (
                result == case["should_match"]
            ), f"Pattern '{case['pattern']}' with account name '{case['account_name']}' should {'match' if case['should_match'] else 'not match'}"

    def test_pattern_filter_account_matching_complex_patterns(self):
        """Test account matching with complex regex patterns."""
        test_cases = [
            {
                "pattern": "^(prod|staging|dev)-.*",
                "account_name": "prod-web-server",
                "should_match": True,
            },
            {
                "pattern": "^(prod|staging|dev)-.*",
                "account_name": "staging-api-server",
                "should_match": True,
            },
            {
                "pattern": "^(prod|staging|dev)-.*",
                "account_name": "test-server",
                "should_match": False,
            },
            {
                "pattern": "account-[A-Z]{2,3}-\\d{4}",
                "account_name": "account-US-2024",
                "should_match": True,
            },
            {
                "pattern": "account-[A-Z]{2,3}-\\d{4}",
                "account_name": "account-USA-2024",
                "should_match": True,
            },
            {
                "pattern": "account-[A-Z]{2,3}-\\d{4}",
                "account_name": "account-us-2024",
                "should_match": False,
            },
            {
                "pattern": "account-[A-Z]{2,3}-\\d{4}",
                "account_name": "account-US-24",
                "should_match": False,
            },
            {"pattern": ".*web.*", "account_name": "my-web-server", "should_match": True},
            {"pattern": ".*web.*", "account_name": "web-frontend", "should_match": True},
            {"pattern": ".*web.*", "account_name": "database-server", "should_match": False},
        ]

        for case in test_cases:
            account_filter = AccountFilter(
                account_name_pattern=case["pattern"], organizations_client=self.mock_org_client
            )

            account = AccountInfo(
                account_id="123456789012",
                account_name=case["account_name"],
                email="test@example.com",
                status="ACTIVE",
                tags={},
                ou_path=[],
            )

            result = account_filter._account_matches_pattern_filter(account)
            assert (
                result == case["should_match"]
            ), f"Pattern '{case['pattern']}' with account name '{case['account_name']}' should {'match' if case['should_match'] else 'not match'}"

    def test_pattern_filter_case_sensitivity(self):
        """Test that pattern matching is case sensitive by default."""
        account_filter = AccountFilter(
            account_name_pattern="^Prod-.*", organizations_client=self.mock_org_client
        )

        # Should match exact case
        account_match = AccountInfo(
            account_id="123456789012",
            account_name="Prod-WebServer",
            email="test@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )
        assert account_filter._account_matches_pattern_filter(account_match) is True

        # Should not match different case
        account_no_match = AccountInfo(
            account_id="123456789013",
            account_name="prod-webserver",
            email="test@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )
        assert account_filter._account_matches_pattern_filter(account_no_match) is False

    def test_pattern_filter_case_insensitive_pattern(self):
        """Test case insensitive pattern matching using regex flags."""
        account_filter = AccountFilter(
            account_name_pattern="(?i)^prod-.*",  # Case insensitive flag
            organizations_client=self.mock_org_client,
        )

        test_names = ["Prod-WebServer", "prod-webserver", "PROD-DATABASE"]

        for name in test_names:
            account = AccountInfo(
                account_id="123456789012",
                account_name=name,
                email="test@example.com",
                status="ACTIVE",
                tags={},
                ou_path=[],
            )
            assert (
                account_filter._account_matches_pattern_filter(account) is True
            ), f"Case insensitive pattern should match '{name}'"

    def test_pattern_filter_invalid_regex_handling(self):
        """Test handling of invalid regex during matching."""
        # Create filter with invalid pattern (bypassing validation for testing)
        account_filter = AccountFilter(
            account_name_pattern="valid-pattern", organizations_client=self.mock_org_client
        )
        # Manually set invalid pattern to test runtime handling
        account_filter.account_name_pattern = "[invalid"

        account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        # Should return False for invalid regex (graceful handling)
        result = account_filter._account_matches_pattern_filter(account)
        assert result is False

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    def test_pattern_filter_resolve_accounts(self, mock_optimizer_class):
        """Test resolving accounts with pattern filter."""
        # Mock optimizer to return test accounts
        mock_optimizer = Mock()
        mock_optimizer_class.return_value = mock_optimizer

        test_accounts = [
            AccountInfo(
                account_id="123456789012",
                account_name="prod-web-server",
                email="prod1@example.com",
                status="ACTIVE",
                tags={},
                ou_path=[],
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="prod-api-server",
                email="prod2@example.com",
                status="ACTIVE",
                tags={},
                ou_path=[],
            ),
            AccountInfo(
                account_id="123456789014",
                account_name="dev-web-server",
                email="dev@example.com",
                status="ACTIVE",
                tags={},
                ou_path=[],
            ),
        ]

        mock_optimizer.get_all_accounts_optimized.return_value = test_accounts

        account_filter = AccountFilter(
            account_name_pattern="^prod-.*", organizations_client=self.mock_org_client
        )

        accounts = account_filter.resolve_accounts()

        # Should return only accounts matching the pattern
        assert len(accounts) == 2
        assert accounts[0].account_name == "prod-web-server"
        assert accounts[1].account_name == "prod-api-server"

    def test_pattern_filter_description(self):
        """Test filter description for pattern filter."""
        account_filter = AccountFilter(
            account_name_pattern="^prod-.*-server$", organizations_client=self.mock_org_client
        )
        description = account_filter.get_filter_description()
        assert description == "Accounts matching pattern: ^prod-.*-server$"


class TestBooleanCombinationLogic:
    """Comprehensive tests for boolean combination logic with complex criteria (Requirement 8.3)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_mutually_exclusive_filter_validation(self):
        """Test that mutually exclusive filters are properly validated."""
        # Test explicit accounts + filter expression
        account_filter = AccountFilter(
            filter_expression="*",
            explicit_accounts=["123456789012"],
            organizations_client=self.mock_org_client,
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Cannot specify multiple filter options simultaneously" in errors[0].message

        # Test explicit accounts + OU filter
        account_filter = AccountFilter(
            explicit_accounts=["123456789012"],
            ou_filter="Root/Production",
            organizations_client=self.mock_org_client,
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Cannot specify multiple filter options simultaneously" in errors[0].message

        # Test OU filter + pattern filter
        account_filter = AccountFilter(
            ou_filter="Root/Production",
            account_name_pattern="^prod-.*",
            organizations_client=self.mock_org_client,
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Cannot specify multiple filter options simultaneously" in errors[0].message

    def test_multiple_tag_filter_combination_and_logic(self):
        """Test multiple tag filters with AND logic (all must match)."""
        account_filter = AccountFilter(
            filter_expression="tag:Environment=Production,Team=Backend,Owner=John",
            organizations_client=self.mock_org_client,
        )

        # Account matching all tags
        account_match = AccountInfo(
            account_id="123456789012",
            account_name="Backend Server",
            email="backend@example.com",
            status="ACTIVE",
            tags={
                "Environment": "Production",
                "Team": "Backend",
                "Owner": "John",
                "Project": "WebApp",  # Extra tag is fine
            },
            ou_path=[],
        )
        assert account_filter._account_matches_all_tag_filters(account_match) is True

        # Account missing one tag
        account_no_match = AccountInfo(
            account_id="123456789013",
            account_name="Frontend Server",
            email="frontend@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "Frontend", "Owner": "John"},  # Wrong team
            ou_path=[],
        )
        assert account_filter._account_matches_all_tag_filters(account_no_match) is False

    def test_complex_tag_filter_combinations(self):
        """Test complex tag filter combinations with various scenarios."""
        test_cases = [
            {
                "description": "Two tag filters - both match",
                "filter_expression": "tag:Environment=Production,Team=Backend",
                "account_tags": {"Environment": "Production", "Team": "Backend", "Owner": "Alice"},
                "should_match": True,
            },
            {
                "description": "Two tag filters - one missing",
                "filter_expression": "tag:Environment=Production,Team=Backend",
                "account_tags": {"Environment": "Production", "Owner": "Alice"},
                "should_match": False,
            },
            {
                "description": "Three tag filters - all match",
                "filter_expression": "tag:Environment=Production,Team=Backend,CostCenter=Engineering",
                "account_tags": {
                    "Environment": "Production",
                    "Team": "Backend",
                    "CostCenter": "Engineering",
                    "Owner": "Bob",
                },
                "should_match": True,
            },
            {
                "description": "Three tag filters - one wrong value",
                "filter_expression": "tag:Environment=Production,Team=Backend,CostCenter=Engineering",
                "account_tags": {
                    "Environment": "Production",
                    "Team": "Backend",
                    "CostCenter": "Marketing",  # Wrong value
                },
                "should_match": False,
            },
            {
                "description": "Five tag filters - all match",
                "filter_expression": "tag:Environment=Production,Team=Backend,Owner=John,Project=WebApp,CostCenter=Engineering",
                "account_tags": {
                    "Environment": "Production",
                    "Team": "Backend",
                    "Owner": "John",
                    "Project": "WebApp",
                    "CostCenter": "Engineering",
                    "Region": "us-east-1",  # Extra tag
                },
                "should_match": True,
            },
            {
                "description": "Case sensitive tag matching",
                "filter_expression": "tag:Environment=Production,Team=Backend",
                "account_tags": {"Environment": "production", "Team": "Backend"},  # Wrong case
                "should_match": False,
            },
            {
                "description": "Special characters in tag values",
                "filter_expression": "tag:Environment=Prod-2024,Team=Backend_v2",
                "account_tags": {"Environment": "Prod-2024", "Team": "Backend_v2"},
                "should_match": True,
            },
            {
                "description": "Spaces in tag values",
                "filter_expression": "tag:Environment=Production Environment,Team=Backend Team",
                "account_tags": {"Environment": "Production Environment", "Team": "Backend Team"},
                "should_match": True,
            },
        ]

        for case in test_cases:
            account_filter = AccountFilter(
                filter_expression=case["filter_expression"],
                organizations_client=self.mock_org_client,
            )

            account = AccountInfo(
                account_id="123456789012",
                account_name="Test Account",
                email="test@example.com",
                status="ACTIVE",
                tags=case["account_tags"],
                ou_path=[],
            )

            result = account_filter._account_matches_all_tag_filters(account)
            assert (
                result == case["should_match"]
            ), f"Test case '{case['description']}' failed: expected {case['should_match']}, got {result}"

    def test_filter_type_precedence(self):
        """Test that filter type determination follows correct precedence."""
        # Explicit accounts has highest precedence
        account_filter = AccountFilter(
            filter_expression="*",
            explicit_accounts=["123456789012"],
            ou_filter="Root/Production",
            account_name_pattern="^prod-.*",
            organizations_client=self.mock_org_client,
        )
        # Should fail validation due to multiple filters
        errors = account_filter.validate_filter()
        assert len(errors) > 0

        # Test individual filter types
        # Explicit accounts
        account_filter = AccountFilter(
            explicit_accounts=["123456789012"], organizations_client=self.mock_org_client
        )
        assert account_filter.filter_type == FilterType.EXPLICIT

        # OU filter
        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )
        assert account_filter.filter_type == FilterType.OU

        # Pattern filter
        account_filter = AccountFilter(
            account_name_pattern="^prod-.*", organizations_client=self.mock_org_client
        )
        assert account_filter.filter_type == FilterType.PATTERN

        # Tag filter
        account_filter = AccountFilter(
            filter_expression="tag:Environment=Production",
            organizations_client=self.mock_org_client,
        )
        assert account_filter.filter_type == FilterType.TAG

        # Wildcard filter
        account_filter = AccountFilter(
            filter_expression="*", organizations_client=self.mock_org_client
        )
        assert account_filter.filter_type == FilterType.WILDCARD

    def test_no_filter_specified_validation(self):
        """Test validation fails when no filter is specified."""
        account_filter = AccountFilter(organizations_client=self.mock_org_client)
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    def test_empty_filter_values_validation(self):
        """Test validation of empty filter values."""
        # Empty filter expression
        account_filter = AccountFilter(
            filter_expression="", organizations_client=self.mock_org_client
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

        # Empty OU filter
        account_filter = AccountFilter(ou_filter="", organizations_client=self.mock_org_client)
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

        # Empty pattern filter
        account_filter = AccountFilter(
            account_name_pattern="", organizations_client=self.mock_org_client
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    def test_whitespace_only_filter_values(self):
        """Test handling of whitespace-only filter values."""
        # Whitespace-only filter expression
        account_filter = AccountFilter(
            filter_expression="   ", organizations_client=self.mock_org_client
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

        # Whitespace-only OU filter
        account_filter = AccountFilter(ou_filter="   ", organizations_client=self.mock_org_client)
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

        # Whitespace-only pattern filter
        account_filter = AccountFilter(
            account_name_pattern="   ", organizations_client=self.mock_org_client
        )
        errors = account_filter.validate_filter()
        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    def test_complex_filtering_integration(self, mock_optimizer_class):
        """Test integration of complex filtering scenarios."""
        # Mock optimizer to return diverse test accounts
        mock_optimizer = Mock()
        mock_optimizer_class.return_value = mock_optimizer

        test_accounts = [
            AccountInfo(
                account_id="123456789012",
                account_name="prod-web-server",
                email="prod-web@example.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Team": "Backend", "Service": "Web"},
                ou_path=["Root", "Production", "WebServices"],
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="prod-api-server",
                email="prod-api@example.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Team": "Backend", "Service": "API"},
                ou_path=["Root", "Production", "APIServices"],
            ),
            AccountInfo(
                account_id="123456789014",
                account_name="dev-web-server",
                email="dev-web@example.com",
                status="ACTIVE",
                tags={"Environment": "Development", "Team": "Backend", "Service": "Web"},
                ou_path=["Root", "Development", "WebServices"],
            ),
            AccountInfo(
                account_id="123456789015",
                account_name="prod-database",
                email="prod-db@example.com",
                status="ACTIVE",
                tags={"Environment": "Production", "Team": "Database", "Service": "DB"},
                ou_path=["Root", "Production", "DatabaseServices"],
            ),
        ]

        mock_optimizer.get_all_accounts_optimized.return_value = test_accounts

        # Test complex tag filtering
        account_filter = AccountFilter(
            filter_expression="tag:Environment=Production,Team=Backend",
            organizations_client=self.mock_org_client,
        )
        accounts = account_filter.resolve_accounts()
        assert len(accounts) == 2  # Only prod backend accounts
        assert all(
            acc.tags["Environment"] == "Production" and acc.tags["Team"] == "Backend"
            for acc in accounts
        )

        # Test OU filtering
        account_filter = AccountFilter(
            ou_filter="Root/Production", organizations_client=self.mock_org_client
        )
        accounts = account_filter.resolve_accounts()
        assert len(accounts) == 3  # All production accounts
        assert all("Production" in acc.ou_path for acc in accounts)

        # Test pattern filtering
        account_filter = AccountFilter(
            account_name_pattern="^prod-.*", organizations_client=self.mock_org_client
        )
        accounts = account_filter.resolve_accounts()
        assert len(accounts) == 3  # All accounts starting with "prod-"
        assert all(acc.account_name.startswith("prod-") for acc in accounts)
