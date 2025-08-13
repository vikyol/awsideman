"""Tests for account filtering infrastructure."""
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import OrganizationsClientWrapper
from src.awsideman.utils.account_filter import (
    AccountFilter,
    AccountInfo,
    FilterType,
    create_tag_filter_expression,
    parse_multiple_tag_filters,
)
from src.awsideman.utils.models import AccountDetails, NodeType, OrgNode


class TestAccountInfo:
    """Tests for AccountInfo class."""

    def test_init_with_defaults(self):
        """Test AccountInfo initialization with default values."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        assert account.account_id == "123456789012"
        assert account.account_name == "Test Account"
        assert account.email == "test@example.com"
        assert account.status == "ACTIVE"
        assert account.tags == {}
        assert account.ou_path == []

    def test_init_with_none_collections(self):
        """Test AccountInfo initialization with None collections."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags=None,
            ou_path=None,
        )

        assert account.tags == {}
        assert account.ou_path == []

    def test_matches_tag_filter_success(self):
        """Test successful tag filter matching."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "Backend"},
            ou_path=[],
        )

        assert account.matches_tag_filter("Environment", "Production") is True
        assert account.matches_tag_filter("Team", "Backend") is True

    def test_matches_tag_filter_failure(self):
        """Test tag filter matching failure."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "Backend"},
            ou_path=[],
        )

        assert account.matches_tag_filter("Environment", "Development") is False
        assert account.matches_tag_filter("NonExistent", "Value") is False

    def test_get_display_name(self):
        """Test display name generation."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        assert account.get_display_name() == "Test Account (123456789012)"

    def test_from_account_details(self):
        """Test creation from AccountDetails."""
        from datetime import datetime

        account_details = AccountDetails(
            id="123456789012",
            name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            joined_timestamp=datetime.now(),
            tags={"Environment": "Production"},
            ou_path=["Root", "Production"],
        )

        account_info = AccountInfo.from_account_details(account_details)

        assert account_info.account_id == "123456789012"
        assert account_info.account_name == "Test Account"
        assert account_info.email == "test@example.com"
        assert account_info.status == "ACTIVE"
        assert account_info.tags == {"Environment": "Production"}
        assert account_info.ou_path == ["Root", "Production"]


class TestAccountFilter:
    """Tests for AccountFilter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        # Add client_manager mock for the new functionality
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_init_wildcard_filter(self):
        """Test initialization with wildcard filter."""
        filter_obj = AccountFilter("*", self.mock_org_client)

        assert filter_obj.filter_expression == "*"
        assert filter_obj.filter_type == FilterType.WILDCARD
        assert filter_obj.tag_filters == []

    def test_init_tag_filter(self):
        """Test initialization with tag filter."""
        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)

        assert filter_obj.filter_expression == "tag:Environment=Production"
        assert filter_obj.filter_type == FilterType.TAG
        assert filter_obj.tag_filters == [{"key": "Environment", "value": "Production"}]

    def test_init_multiple_tag_filters(self):
        """Test initialization with multiple tag filters."""
        filter_obj = AccountFilter("tag:Environment=Production,Team=Backend", self.mock_org_client)

        assert filter_obj.filter_type == FilterType.TAG
        expected_filters = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
        ]
        assert filter_obj.tag_filters == expected_filters

    def test_determine_filter_type_wildcard(self):
        """Test filter type determination for wildcard."""
        filter_obj = AccountFilter("*", self.mock_org_client)
        assert filter_obj._determine_filter_type() == FilterType.WILDCARD

    def test_determine_filter_type_tag(self):
        """Test filter type determination for tag filter."""
        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        assert filter_obj._determine_filter_type() == FilterType.TAG

    def test_parse_tag_filters_single(self):
        """Test parsing single tag filter."""
        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        filters = filter_obj._parse_tag_filters()

        expected = [{"key": "Environment", "value": "Production"}]
        assert filters == expected

    def test_parse_tag_filters_multiple(self):
        """Test parsing multiple tag filters."""
        filter_obj = AccountFilter("tag:Environment=Production,Team=Backend", self.mock_org_client)
        filters = filter_obj._parse_tag_filters()

        expected = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
        ]
        assert filters == expected

    def test_parse_tag_filters_invalid_format(self):
        """Test parsing invalid tag filter format."""
        with pytest.raises(ValueError, match="Invalid tag filter format"):
            AccountFilter("tag:InvalidFormat", self.mock_org_client)

    def test_parse_tag_filters_empty_key(self):
        """Test parsing tag filter with empty key."""
        with pytest.raises(ValueError, match="Tag key cannot be empty"):
            AccountFilter("tag:=Value", self.mock_org_client)

    def test_parse_tag_filters_empty_value(self):
        """Test parsing tag filter with empty value."""
        with pytest.raises(ValueError, match="Tag value cannot be empty"):
            AccountFilter("tag:Key=", self.mock_org_client)

    def test_parse_tag_filters_empty_after_prefix(self):
        """Test parsing empty tag filter after prefix."""
        with pytest.raises(ValueError, match="Tag filter expression cannot be empty"):
            AccountFilter("tag:", self.mock_org_client)

    def test_validate_filter_valid_wildcard(self):
        """Test validation of valid wildcard filter."""
        filter_obj = AccountFilter("*", self.mock_org_client)
        errors = filter_obj.validate_filter()

        assert errors == []

    def test_validate_filter_valid_tag(self):
        """Test validation of valid tag filter."""
        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        errors = filter_obj.validate_filter()

        assert errors == []

    def test_validate_filter_empty_expression(self):
        """Test validation of empty filter expression."""
        filter_obj = AccountFilter("", self.mock_org_client)
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    def test_validate_filter_invalid_wildcard(self):
        """Test validation of invalid wildcard filter."""
        filter_obj = AccountFilter("**", self.mock_org_client)
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Invalid wildcard filter" in errors[0].message

    def test_validate_filter_invalid_tag(self):
        """Test validation of invalid tag filter."""
        # Create a filter with invalid format that doesn't fail during init
        # by temporarily bypassing the parsing
        filter_obj = AccountFilter("*", self.mock_org_client)
        filter_obj.filter_expression = "tag:InvalidFormat"
        filter_obj.filter_type = FilterType.TAG

        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Invalid tag filter format" in errors[0].message

    def test_get_filter_description_wildcard(self):
        """Test filter description for wildcard."""
        filter_obj = AccountFilter("*", self.mock_org_client)
        description = filter_obj.get_filter_description()

        assert description == "All accounts in the organization"

    def test_get_filter_description_single_tag(self):
        """Test filter description for single tag."""
        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        description = filter_obj.get_filter_description()

        assert description == "Accounts with tags: Environment=Production"

    def test_get_filter_description_multiple_tags(self):
        """Test filter description for multiple tags."""
        filter_obj = AccountFilter("tag:Environment=Production,Team=Backend", self.mock_org_client)
        description = filter_obj.get_filter_description()

        assert description == "Accounts with tags: Environment=Production, Team=Backend"

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    @patch("src.awsideman.aws_clients.manager.build_organization_hierarchy")
    @patch("src.awsideman.aws_clients.manager.get_account_details")
    def test_resolve_wildcard_accounts(
        self, mock_get_details, mock_build_hierarchy, mock_optimizer_class
    ):
        """Test resolving wildcard accounts."""
        # Mock organization hierarchy
        account_node = OrgNode(
            id="123456789012", name="Test Account", type=NodeType.ACCOUNT, children=[]
        )
        root_node = OrgNode(
            id="r-1234567890", name="Root", type=NodeType.ROOT, children=[account_node]
        )
        mock_build_hierarchy.return_value = [root_node]

        # Mock account details
        from datetime import datetime

        mock_account_details = AccountDetails(
            id="123456789012",
            name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            joined_timestamp=datetime.now(),
            tags={"Environment": "Production"},
            ou_path=["Root"],
        )
        mock_get_details.return_value = mock_account_details

        # Mock describe_account
        self.mock_org_client.describe_account.return_value = {
            "Id": "123456789012",
            "Name": "Test Account",
            "Email": "test@example.com",
            "Status": "ACTIVE",
        }

        # Mock AccountCacheOptimizer to return the expected account
        mock_optimizer = Mock()
        mock_optimizer_class.return_value = mock_optimizer

        # Create AccountInfo object for the mock optimizer to return
        test_account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production"},
            ou_path=["Root"],
        )
        mock_optimizer.get_all_accounts_optimized.return_value = [test_account]

        filter_obj = AccountFilter("*", self.mock_org_client)
        accounts = filter_obj.resolve_accounts()

        assert len(accounts) == 1
        assert accounts[0].account_id == "123456789012"
        assert accounts[0].account_name == "Test Account"

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    @patch("src.awsideman.aws_clients.manager.build_organization_hierarchy")
    @patch("src.awsideman.aws_clients.manager.get_account_details")
    def test_resolve_tag_filtered_accounts(
        self, mock_get_details, mock_build_hierarchy, mock_optimizer_class
    ):
        """Test resolving tag-filtered accounts."""
        # Mock organization hierarchy with two accounts
        account1_node = OrgNode(
            id="123456789012", name="Prod Account", type=NodeType.ACCOUNT, children=[]
        )
        account2_node = OrgNode(
            id="123456789013", name="Dev Account", type=NodeType.ACCOUNT, children=[]
        )
        root_node = OrgNode(
            id="r-1234567890",
            name="Root",
            type=NodeType.ROOT,
            children=[account1_node, account2_node],
        )
        mock_build_hierarchy.return_value = [root_node]

        # Mock account details
        from datetime import datetime

        def mock_get_details_side_effect(client, account_id):
            if account_id == "123456789012":
                return AccountDetails(
                    id="123456789012",
                    name="Prod Account",
                    email="prod@example.com",
                    status="ACTIVE",
                    joined_timestamp=datetime.now(),
                    tags={"Environment": "Production"},
                    ou_path=["Root"],
                )
            elif account_id == "123456789013":
                return AccountDetails(
                    id="123456789013",
                    name="Dev Account",
                    email="dev@example.com",
                    status="ACTIVE",
                    joined_timestamp=datetime.now(),
                    tags={"Environment": "Development"},
                    ou_path=["Root"],
                )

        mock_get_details.side_effect = mock_get_details_side_effect

        # Mock describe_account
        def mock_describe_account_side_effect(account_id):
            if account_id == "123456789012":
                return {
                    "Id": "123456789012",
                    "Name": "Prod Account",
                    "Email": "prod@example.com",
                    "Status": "ACTIVE",
                }
            elif account_id == "123456789013":
                return {
                    "Id": "123456789013",
                    "Name": "Dev Account",
                    "Email": "dev@example.com",
                    "Status": "ACTIVE",
                }

        self.mock_org_client.describe_account.side_effect = mock_describe_account_side_effect

        # Mock AccountCacheOptimizer to return the expected accounts
        mock_optimizer = Mock()
        mock_optimizer_class.return_value = mock_optimizer

        # Create AccountInfo objects for the mock optimizer to return
        prod_account = AccountInfo(
            account_id="123456789012",
            account_name="Prod Account",
            email="prod@example.com",
            status="ACTIVE",
            tags={"Environment": "Production"},
            ou_path=["Root"],
        )
        dev_account = AccountInfo(
            account_id="123456789013",
            account_name="Dev Account",
            email="dev@example.com",
            status="ACTIVE",
            tags={"Environment": "Development"},
            ou_path=["Root"],
        )
        mock_optimizer.get_all_accounts_optimized.return_value = [prod_account, dev_account]

        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        accounts = filter_obj.resolve_accounts()

        assert len(accounts) == 1
        assert accounts[0].account_id == "123456789012"
        assert accounts[0].account_name == "Prod Account"

    def test_resolve_accounts_validation_failure(self):
        """Test resolve_accounts with validation failure."""
        filter_obj = AccountFilter("", self.mock_org_client)

        with pytest.raises(ValueError, match="Filter validation failed"):
            filter_obj.resolve_accounts()

    def test_account_matches_all_tag_filters_success(self):
        """Test account matching all tag filters."""
        filter_obj = AccountFilter("tag:Environment=Production,Team=Backend", self.mock_org_client)

        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "Backend", "Owner": "John"},
            ou_path=[],
        )

        assert filter_obj._account_matches_all_tag_filters(account) is True

    def test_account_matches_all_tag_filters_failure(self):
        """Test account not matching all tag filters."""
        filter_obj = AccountFilter("tag:Environment=Production,Team=Backend", self.mock_org_client)

        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "Frontend"},  # Wrong team
            ou_path=[],
        )

        assert filter_obj._account_matches_all_tag_filters(account) is False

    def test_validation_error_details(self):
        """Test that validation errors contain proper details."""
        # Test empty expression
        filter_obj = AccountFilter("", self.mock_org_client)
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert errors[0].field == "filter_options"
        assert errors[0].value == "no_filters_specified"
        assert "Must specify at least one filter option" in errors[0].message

        # Test invalid wildcard
        filter_obj = AccountFilter("invalid_wildcard", self.mock_org_client)
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert errors[0].field == "filter_expression"
        assert errors[0].value == "invalid_wildcard"


class TestAccountFilterAdvancedFiltering:
    """Tests for advanced filtering options (OU and pattern filtering)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        # Add client_manager mock for the new functionality
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_init_ou_filter(self):
        """Test initialization with OU filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production",
        )

        assert filter_obj.ou_filter == "Root/Production"
        assert filter_obj.filter_type == FilterType.OU

    def test_init_pattern_filter(self):
        """Test initialization with pattern filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="^prod-.*",
        )

        assert filter_obj.account_name_pattern == "^prod-.*"
        assert filter_obj.filter_type == FilterType.PATTERN

    def test_validate_ou_filter_valid(self):
        """Test validation of valid OU filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production/SubOU",
        )
        errors = filter_obj.validate_filter()

        assert errors == []

    def test_validate_ou_filter_empty(self):
        """Test validation of empty OU filter."""
        filter_obj = AccountFilter(
            filter_expression=None, organizations_client=self.mock_org_client, ou_filter=""
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    def test_validate_ou_filter_invalid_chars(self):
        """Test validation of OU filter with invalid characters."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production<Invalid>",
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 2  # One for each invalid character
        assert any("invalid character: '<'" in error.message for error in errors)
        assert any("invalid character: '>'" in error.message for error in errors)

    def test_validate_pattern_filter_valid(self):
        """Test validation of valid pattern filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="^prod-.*$",
        )
        errors = filter_obj.validate_filter()

        assert errors == []

    def test_validate_pattern_filter_empty(self):
        """Test validation of empty pattern filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="",
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Must specify at least one filter option" in errors[0].message

    def test_validate_pattern_filter_invalid_regex(self):
        """Test validation of invalid regex pattern."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="[invalid",
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Invalid regex pattern" in errors[0].message

    def test_validate_mutually_exclusive_filters(self):
        """Test validation of mutually exclusive filter options."""
        filter_obj = AccountFilter(
            filter_expression="*",
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production",
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Cannot specify multiple filter options simultaneously" in errors[0].message

    def test_get_filter_description_ou(self):
        """Test filter description for OU filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production",
        )
        description = filter_obj.get_filter_description()

        assert description == "Accounts in organizational unit: Root/Production"

    def test_get_filter_description_pattern(self):
        """Test filter description for pattern filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="^prod-.*",
        )
        description = filter_obj.get_filter_description()

        assert description == "Accounts matching pattern: ^prod-.*"

    def test_account_matches_ou_filter_exact(self):
        """Test account matching OU filter exactly."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production",
        )

        account = AccountInfo(
            account_id="123456789012",
            account_name="Prod Account",
            email="prod@example.com",
            status="ACTIVE",
            tags={},
            ou_path=["Root", "Production"],
        )

        assert filter_obj._account_matches_ou_filter(account) is True

    def test_account_matches_ou_filter_prefix(self):
        """Test account matching OU filter as prefix."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production",
        )

        account = AccountInfo(
            account_id="123456789012",
            account_name="Prod Account",
            email="prod@example.com",
            status="ACTIVE",
            tags={},
            ou_path=["Root", "Production", "SubOU"],
        )

        assert filter_obj._account_matches_ou_filter(account) is True

    def test_account_matches_ou_filter_no_match(self):
        """Test account not matching OU filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            ou_filter="Root/Production",
        )

        account = AccountInfo(
            account_id="123456789012",
            account_name="Dev Account",
            email="dev@example.com",
            status="ACTIVE",
            tags={},
            ou_path=["Root", "Development"],
        )

        assert filter_obj._account_matches_ou_filter(account) is False

    def test_account_matches_pattern_filter_match(self):
        """Test account matching pattern filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="^prod-.*",
        )

        account = AccountInfo(
            account_id="123456789012",
            account_name="prod-web-server",
            email="prod@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        assert filter_obj._account_matches_pattern_filter(account) is True

    def test_account_matches_pattern_filter_no_match(self):
        """Test account not matching pattern filter."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="^prod-.*",
        )

        account = AccountInfo(
            account_id="123456789012",
            account_name="dev-web-server",
            email="dev@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        assert filter_obj._account_matches_pattern_filter(account) is False

    def test_account_matches_pattern_filter_invalid_regex(self):
        """Test account matching with invalid regex pattern."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            account_name_pattern="[invalid",
        )

        account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        # Should return False for invalid regex
        assert filter_obj._account_matches_pattern_filter(account) is False


class TestAccountFilterEdgeCases:
    """Tests for edge cases and additional scenarios in account filtering."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        # Add client_manager mock for the new functionality
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_filter_expression_with_whitespace(self):
        """Test filter expressions with leading/trailing whitespace."""
        # Test wildcard with whitespace
        filter_obj = AccountFilter("  *  ", self.mock_org_client)
        assert filter_obj.filter_expression == "*"
        assert filter_obj.filter_type == FilterType.WILDCARD

        # Test tag filter with whitespace
        filter_obj = AccountFilter("  tag:Environment=Production  ", self.mock_org_client)
        assert filter_obj.filter_expression == "tag:Environment=Production"
        assert filter_obj.filter_type == FilterType.TAG

    def test_tag_filter_with_special_characters(self):
        """Test tag filters with special characters in values."""
        filter_obj = AccountFilter(
            "tag:Environment=Prod-2024,Team=Backend_v2", self.mock_org_client
        )

        expected_filters = [
            {"key": "Environment", "value": "Prod-2024"},
            {"key": "Team", "value": "Backend_v2"},
        ]
        assert filter_obj.tag_filters == expected_filters

    def test_tag_filter_with_spaces_in_values(self):
        """Test tag filters with spaces in tag values."""
        filter_obj = AccountFilter(
            "tag:Environment=Production Environment,Team=Backend Team", self.mock_org_client
        )

        expected_filters = [
            {"key": "Environment", "value": "Production Environment"},
            {"key": "Team", "value": "Backend Team"},
        ]
        assert filter_obj.tag_filters == expected_filters

    def test_tag_filter_case_sensitivity(self):
        """Test that tag filters are case sensitive."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "environment": "development"},
            ou_path=[],
        )

        # Should match exact case
        assert account.matches_tag_filter("Environment", "Production") is True
        assert account.matches_tag_filter("environment", "development") is True

        # Should not match different case
        assert account.matches_tag_filter("Environment", "production") is False
        assert account.matches_tag_filter("ENVIRONMENT", "Production") is False

    def test_multiple_equals_in_tag_value(self):
        """Test tag filters where the value contains equals signs."""
        filter_obj = AccountFilter("tag:Config=key=value", self.mock_org_client)

        expected_filters = [{"key": "Config", "value": "key=value"}]
        assert filter_obj.tag_filters == expected_filters

    def test_empty_tag_list_handling(self):
        """Test handling of accounts with empty tag lists."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={},
            ou_path=[],
        )

        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        assert filter_obj._account_matches_all_tag_filters(account) is False

    def test_none_tag_list_handling(self):
        """Test handling of accounts with None tag lists."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags=None,
            ou_path=[],
        )

        # Should be converted to empty dict in __post_init__
        assert account.tags == {}

        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        assert filter_obj._account_matches_all_tag_filters(account) is False

    def test_complex_tag_combinations(self):
        """Test complex tag filter combinations."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="Test Account",
            email="test@example.com",
            status="ACTIVE",
            tags={
                "Environment": "Production",
                "Team": "Backend",
                "Owner": "John",
                "Project": "WebApp",
                "CostCenter": "Engineering",
            },
            ou_path=[],
        )

        # Test 3-tag filter - should match
        filter_obj = AccountFilter(
            "tag:Environment=Production,Team=Backend,Owner=John", self.mock_org_client
        )
        assert filter_obj._account_matches_all_tag_filters(account) is True

        # Test 3-tag filter with one mismatch - should not match
        filter_obj = AccountFilter(
            "tag:Environment=Production,Team=Backend,Owner=Jane", self.mock_org_client
        )
        assert filter_obj._account_matches_all_tag_filters(account) is False

        # Test 5-tag filter matching all tags - should match
        filter_obj = AccountFilter(
            "tag:Environment=Production,Team=Backend,Owner=John,Project=WebApp,CostCenter=Engineering",
            self.mock_org_client,
        )
        assert filter_obj._account_matches_all_tag_filters(account) is True

    def test_filter_type_determination_edge_cases(self):
        """Test filter type determination for edge cases."""
        # Test string that starts with 'tag' but isn't a tag filter
        filter_obj = AccountFilter("tagnotafilter", self.mock_org_client)
        assert filter_obj.filter_type == FilterType.WILDCARD  # Default fallback

        # Test empty string after tag prefix
        with pytest.raises(ValueError):
            AccountFilter("tag:", self.mock_org_client)


class TestAccountFilterExplicitAccounts:
    """Tests for explicit accounts filtering functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        # Add client_manager mock for the new functionality
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = None

    def test_init_explicit_accounts(self):
        """Test initialization with explicit accounts."""
        account_list = ["123456789012", "123456789013"]
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=account_list,
        )

        assert filter_obj.explicit_accounts == account_list
        assert filter_obj.filter_type == FilterType.EXPLICIT

    def test_validate_explicit_accounts_valid(self):
        """Test validation of valid explicit accounts."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=["123456789012", "123456789013"],
        )
        errors = filter_obj.validate_filter()

        assert errors == []

    def test_validate_explicit_accounts_empty_list(self):
        """Test validation of empty explicit accounts list."""
        filter_obj = AccountFilter(
            filter_expression=None, organizations_client=self.mock_org_client, explicit_accounts=[]
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 1
        assert "Explicit accounts list cannot be empty" in errors[0].message

    def test_validate_explicit_accounts_invalid_format(self):
        """Test validation of invalid account ID format."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=["123456789012", "invalid-account", "12345678901"],  # Too short
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 2
        assert any(
            "Invalid account ID format: 'invalid-account'" in error.message for error in errors
        )
        assert any("Invalid account ID format: '12345678901'" in error.message for error in errors)

    def test_validate_explicit_accounts_empty_id(self):
        """Test validation of empty account ID."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=["123456789012", "", "  "],
        )
        errors = filter_obj.validate_filter()

        assert len(errors) == 2
        assert any("Account ID cannot be empty" in error.message for error in errors)

    def test_get_filter_description_explicit_few(self):
        """Test filter description for few explicit accounts."""
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=["123456789012", "123456789013"],
        )
        description = filter_obj.get_filter_description()

        assert description == "Explicit accounts: 123456789012, 123456789013"

    def test_get_filter_description_explicit_many(self):
        """Test filter description for many explicit accounts."""
        account_list = [f"12345678901{i}" for i in range(5)]
        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=account_list,
        )
        description = filter_obj.get_filter_description()

        assert "Explicit accounts:" in description
        assert "... (5 total)" in description

    def test_resolve_explicit_accounts_success(self):
        """Test resolving explicit accounts successfully."""
        account_list = ["123456789012", "123456789013"]

        def mock_describe_account(account_id):
            if account_id == "123456789012":
                return {
                    "Id": "123456789012",
                    "Name": "Account 1",
                    "Email": "account1@example.com",
                    "Status": "ACTIVE",
                    "Tags": {"Environment": "Production"},
                }
            elif account_id == "123456789013":
                return {
                    "Id": "123456789013",
                    "Name": "Account 2",
                    "Email": "account2@example.com",
                    "Status": "ACTIVE",
                    "Tags": {"Environment": "Development"},
                }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=account_list,
        )

        accounts = filter_obj.resolve_accounts()

        assert len(accounts) == 2
        assert accounts[0].account_id == "123456789012"
        assert accounts[0].account_name == "Account 1"
        assert accounts[1].account_id == "123456789013"
        assert accounts[1].account_name == "Account 2"

    def test_resolve_explicit_accounts_not_found(self):
        """Test resolving explicit accounts with account not found."""

        def mock_describe_account(account_id):
            if account_id == "123456789012":
                raise Exception("AccountNotFoundException: Account does not exist")

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=["123456789012"],
        )

        with pytest.raises(
            ValueError, match="Account ID '123456789012' does not exist or is not accessible"
        ):
            filter_obj.resolve_accounts()

    def test_resolve_explicit_accounts_access_denied(self):
        """Test resolving explicit accounts with access denied."""

        def mock_describe_account(account_id):
            if account_id == "123456789012":
                raise Exception("AccessDenied: Unauthorized operation")

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        filter_obj = AccountFilter(
            filter_expression=None,
            organizations_client=self.mock_org_client,
            explicit_accounts=["123456789012"],
        )

        with pytest.raises(ValueError, match="Access denied to account ID '123456789012'"):
            filter_obj.resolve_accounts()


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_parse_multiple_tag_filters_single(self):
        """Test parsing single tag filter expression."""
        expressions = ["Environment=Production"]
        filters = parse_multiple_tag_filters(expressions)

        expected = [{"key": "Environment", "value": "Production"}]
        assert filters == expected

    def test_parse_multiple_tag_filters_multiple_expressions(self):
        """Test parsing multiple tag filter expressions."""
        expressions = ["Environment=Production", "Team=Backend"]
        filters = parse_multiple_tag_filters(expressions)

        expected = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
        ]
        assert filters == expected

    def test_parse_multiple_tag_filters_comma_separated(self):
        """Test parsing comma-separated tag filters in single expression."""
        expressions = ["Environment=Production,Team=Backend"]
        filters = parse_multiple_tag_filters(expressions)

        expected = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
        ]
        assert filters == expected

    def test_parse_multiple_tag_filters_mixed(self):
        """Test parsing mixed format tag filters."""
        expressions = ["Environment=Production,Team=Backend", "Owner=John"]
        filters = parse_multiple_tag_filters(expressions)

        expected = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
            {"key": "Owner", "value": "John"},
        ]
        assert filters == expected

    def test_parse_multiple_tag_filters_empty_expressions(self):
        """Test parsing with empty expressions."""
        expressions = ["", "Environment=Production", ""]
        filters = parse_multiple_tag_filters(expressions)

        expected = [{"key": "Environment", "value": "Production"}]
        assert filters == expected

    def test_parse_multiple_tag_filters_invalid_format(self):
        """Test parsing invalid tag filter format."""
        expressions = ["InvalidFormat"]

        with pytest.raises(ValueError, match="Invalid tag filter format"):
            parse_multiple_tag_filters(expressions)

    def test_parse_multiple_tag_filters_empty_key(self):
        """Test parsing tag filter with empty key."""
        expressions = ["=Value"]

        with pytest.raises(ValueError, match="Tag key cannot be empty"):
            parse_multiple_tag_filters(expressions)

    def test_parse_multiple_tag_filters_empty_value(self):
        """Test parsing tag filter with empty value."""
        expressions = ["Key="]

        with pytest.raises(ValueError, match="Tag value cannot be empty"):
            parse_multiple_tag_filters(expressions)

    def test_create_tag_filter_expression_single(self):
        """Test creating tag filter expression from single filter."""
        filters = [{"key": "Environment", "value": "Production"}]
        expression = create_tag_filter_expression(filters)

        assert expression == "tag:Environment=Production"

    def test_create_tag_filter_expression_multiple(self):
        """Test creating tag filter expression from multiple filters."""
        filters = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
        ]
        expression = create_tag_filter_expression(filters)

        assert expression == "tag:Environment=Production,Team=Backend"

    def test_create_tag_filter_expression_empty(self):
        """Test creating tag filter expression from empty list."""
        filters = []
        expression = create_tag_filter_expression(filters)

        assert expression == ""

    def test_parse_multiple_tag_filters_whitespace_handling(self):
        """Test parsing tag filters with various whitespace scenarios."""
        expressions = ["  Environment=Production  ", "  Team=Backend,Owner=John  "]
        filters = parse_multiple_tag_filters(expressions)

        expected = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
            {"key": "Owner", "value": "John"},
        ]
        assert filters == expected

    def test_parse_multiple_tag_filters_special_characters(self):
        """Test parsing tag filters with special characters."""
        expressions = ["Environment=Prod-2024_v1", "Team=Backend/Frontend"]
        filters = parse_multiple_tag_filters(expressions)

        expected = [
            {"key": "Environment", "value": "Prod-2024_v1"},
            {"key": "Team", "value": "Backend/Frontend"},
        ]
        assert filters == expected

    def test_parse_multiple_tag_filters_equals_in_value(self):
        """Test parsing tag filters where values contain equals signs."""
        expressions = ["Config=key=value=test"]
        filters = parse_multiple_tag_filters(expressions)

        expected = [{"key": "Config", "value": "key=value=test"}]
        assert filters == expected

    def test_create_tag_filter_expression_special_characters(self):
        """Test creating tag filter expressions with special characters."""
        filters = [
            {"key": "Environment", "value": "Prod-2024_v1"},
            {"key": "Config", "value": "key=value"},
        ]
        expression = create_tag_filter_expression(filters)

        assert expression == "tag:Environment=Prod-2024_v1,Config=key=value"


class TestAccountFilterStreaming:
    """Tests for streaming account resolution functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)
        self.mock_org_client.client_manager = Mock()
        self.mock_org_client.client_manager.profile = "test-profile"

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    @patch("src.awsideman.aws_clients.manager.build_organization_hierarchy")
    def test_resolve_accounts_streaming_wildcard(self, mock_build_hierarchy, mock_optimizer_class):
        """Test streaming account resolution for wildcard filter."""
        # Setup mock organization hierarchy
        mock_account_node = Mock()
        mock_account_node.is_account.return_value = True
        mock_account_node.id = "123456789012"
        mock_account_node.children = []
        mock_account_node.ou_path = ["root", "ou-1"]

        mock_root = Mock()
        mock_root.is_account.return_value = False
        mock_root.children = [mock_account_node]

        mock_build_hierarchy.return_value = [mock_root]

        # Setup mock account data
        self.mock_org_client.describe_account.return_value = {
            "Id": "123456789012",
            "Name": "Test Account",
            "Email": "test@example.com",
            "Status": "ACTIVE",
            "Tags": {"Environment": "Production"},
        }

        # Create filter and test streaming
        account_filter = AccountFilter(
            filter_expression="*", organizations_client=self.mock_org_client
        )

        # Convert generator to list for testing
        accounts = list(account_filter.resolve_accounts_streaming())

        assert len(accounts) == 1
        assert accounts[0].account_id == "123456789012"
        assert accounts[0].account_name == "Test Account"
        assert accounts[0].email == "test@example.com"
        assert accounts[0].status == "ACTIVE"
        assert accounts[0].tags == {"Environment": "Production"}
        assert accounts[0].ou_path == ["root", "ou-1"]

    @patch("src.awsideman.utils.account_cache_optimizer.AccountCacheOptimizer")
    @patch("src.awsideman.aws_clients.manager.build_organization_hierarchy")
    def test_resolve_accounts_streaming_tag_filter(
        self, mock_build_hierarchy, mock_optimizer_class
    ):
        """Test streaming account resolution for tag-based filter."""
        # Setup mock organization hierarchy with multiple accounts
        mock_account1 = Mock()
        mock_account1.is_account.return_value = True
        mock_account1.id = "123456789012"
        mock_account1.children = []
        mock_account1.ou_path = ["root", "ou-1"]

        mock_account2 = Mock()
        mock_account2.is_account.return_value = True
        mock_account2.id = "123456789013"
        mock_account2.children = []
        mock_account2.ou_path = ["root", "ou-2"]

        mock_root = Mock()
        mock_root.is_account.return_value = False
        mock_root.children = [mock_account1, mock_account2]

        mock_build_hierarchy.return_value = [mock_root]

        # Setup mock account data - only first account matches tag filter
        def mock_describe_account(account_id):
            if account_id == "123456789012":
                return {
                    "Id": "123456789012",
                    "Name": "Production Account",
                    "Email": "prod@example.com",
                    "Status": "ACTIVE",
                    "Tags": {"Environment": "Production"},
                }
            else:
                return {
                    "Id": "123456789013",
                    "Name": "Development Account",
                    "Email": "dev@example.com",
                    "Status": "ACTIVE",
                    "Tags": {"Environment": "Development"},
                }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        # Create filter and test streaming
        account_filter = AccountFilter(
            filter_expression="tag:Environment=Production",
            organizations_client=self.mock_org_client,
        )

        # Convert generator to list for testing
        accounts = list(account_filter.resolve_accounts_streaming())

        # Should only return the production account
        assert len(accounts) == 1
        assert accounts[0].account_id == "123456789012"
        assert accounts[0].account_name == "Production Account"
        assert accounts[0].tags == {"Environment": "Production"}

    def test_resolve_accounts_streaming_explicit_accounts(self):
        """Test streaming account resolution for explicit account list."""

        # Setup mock account data
        def mock_describe_account(account_id):
            return {
                "Id": account_id,
                "Name": f"Account-{account_id}",
                "Email": f"{account_id}@example.com",
                "Status": "ACTIVE",
                "Tags": {},
            }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        # Create filter with explicit accounts
        explicit_accounts = ["123456789012", "123456789013", "123456789014"]
        account_filter = AccountFilter(
            explicit_accounts=explicit_accounts, organizations_client=self.mock_org_client
        )

        # Convert generator to list for testing
        accounts = list(account_filter.resolve_accounts_streaming())

        assert len(accounts) == 3
        for i, account in enumerate(accounts):
            expected_id = explicit_accounts[i]
            assert account.account_id == expected_id
            assert account.account_name == f"Account-{expected_id}"
            assert account.email == f"{expected_id}@example.com"

    def test_resolve_accounts_streaming_chunked_processing(self):
        """Test streaming account resolution with chunked processing."""
        # Setup mock account data for large number of accounts
        explicit_accounts = [f"12345678901{i}" for i in range(10)]  # 10 accounts

        def mock_describe_account(account_id):
            return {
                "Id": account_id,
                "Name": f"Account-{account_id}",
                "Email": f"{account_id}@example.com",
                "Status": "ACTIVE",
                "Tags": {},
            }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        # Create filter with explicit accounts
        account_filter = AccountFilter(
            explicit_accounts=explicit_accounts, organizations_client=self.mock_org_client
        )

        # Test with small chunk size
        chunk_size = 3
        accounts = list(account_filter.resolve_accounts_streaming(chunk_size=chunk_size))

        assert len(accounts) == 10
        # Verify all accounts are returned correctly
        for i, account in enumerate(accounts):
            expected_id = explicit_accounts[i]
            assert account.account_id == expected_id

    def test_resolve_accounts_streaming_memory_efficiency(self):
        """Test that streaming resolution is memory efficient (doesn't load all at once)."""
        # Setup mock account data
        explicit_accounts = ["123456789012", "123456789013"]

        call_count = 0

        def mock_describe_account(account_id):
            nonlocal call_count
            call_count += 1
            return {
                "Id": account_id,
                "Name": f"Account-{account_id}",
                "Email": f"{account_id}@example.com",
                "Status": "ACTIVE",
                "Tags": {},
            }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        # Create filter with explicit accounts
        account_filter = AccountFilter(
            explicit_accounts=explicit_accounts, organizations_client=self.mock_org_client
        )

        # Get generator but don't consume it yet
        account_generator = account_filter.resolve_accounts_streaming()

        # At this point, no API calls should have been made (lazy evaluation)
        assert call_count == 0

        # Consume first account
        first_account = next(account_generator)
        assert call_count == 1
        assert first_account.account_id == "123456789012"

        # Consume second account
        second_account = next(account_generator)
        assert call_count == 2
        assert second_account.account_id == "123456789013"

        # Generator should be exhausted
        with pytest.raises(StopIteration):
            next(account_generator)

    def test_resolve_accounts_streaming_validation_error(self):
        """Test that streaming resolution validates filters before processing."""
        # Create filter with invalid expression
        account_filter = AccountFilter(
            filter_expression="invalid-filter", organizations_client=self.mock_org_client
        )

        # Should raise validation error when trying to stream
        with pytest.raises(ValueError, match="Filter validation failed"):
            list(account_filter.resolve_accounts_streaming())

    def test_resolve_accounts_streaming_explicit_account_error(self):
        """Test streaming resolution handles account access errors."""

        # Setup mock to raise error for specific account
        def mock_describe_account(account_id):
            if account_id == "123456789012":
                return {
                    "Id": account_id,
                    "Name": f"Account-{account_id}",
                    "Email": f"{account_id}@example.com",
                    "Status": "ACTIVE",
                    "Tags": {},
                }
            else:
                raise ClientError(
                    error_response={"Error": {"Code": "AccountNotFoundException"}},
                    operation_name="DescribeAccount",
                )

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        # Create filter with explicit accounts including invalid one
        account_filter = AccountFilter(
            explicit_accounts=["123456789012", "999999999999"],
            organizations_client=self.mock_org_client,
        )

        # Should raise error when encountering invalid account
        with pytest.raises(ValueError, match="Account ID '999999999999' does not exist"):
            list(account_filter.resolve_accounts_streaming())

    @patch("src.awsideman.aws_clients.manager.build_organization_hierarchy")
    def test_get_all_accounts_streaming(self, mock_build_hierarchy):
        """Test the internal _get_all_accounts_streaming method."""
        # Setup mock organization hierarchy
        mock_account1 = Mock()
        mock_account1.is_account.return_value = True
        mock_account1.id = "123456789012"
        mock_account1.children = []
        mock_account1.ou_path = ["root", "ou-1"]

        mock_account2 = Mock()
        mock_account2.is_account.return_value = True
        mock_account2.id = "123456789013"
        mock_account2.children = []
        mock_account2.ou_path = ["root", "ou-2"]

        mock_ou = Mock()
        mock_ou.is_account.return_value = False
        mock_ou.children = [mock_account2]

        mock_root = Mock()
        mock_root.is_account.return_value = False
        mock_root.children = [mock_account1, mock_ou]

        mock_build_hierarchy.return_value = [mock_root]

        # Setup mock account data
        def mock_describe_account(account_id):
            return {
                "Id": account_id,
                "Name": f"Account-{account_id}",
                "Email": f"{account_id}@example.com",
                "Status": "ACTIVE",
                "Tags": {},
            }

        self.mock_org_client.describe_account.side_effect = mock_describe_account

        # Create filter and test internal streaming method
        account_filter = AccountFilter(
            filter_expression="*", organizations_client=self.mock_org_client
        )

        # Convert generator to list for testing
        accounts = list(account_filter._get_all_accounts_streaming())

        assert len(accounts) == 2
        account_ids = [account.account_id for account in accounts]
        assert "123456789012" in account_ids
        assert "123456789013" in account_ids
