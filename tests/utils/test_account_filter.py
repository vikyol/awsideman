"""Tests for account filtering infrastructure."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError

from src.awsideman.utils.account_filter import (
    AccountFilter,
    AccountInfo,
    FilterType,
    ValidationError,
    parse_multiple_tag_filters,
    create_tag_filter_expression
)
from src.awsideman.utils.models import AccountDetails, NodeType, OrgNode
from src.awsideman.aws_clients.manager import OrganizationsClientWrapper


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
            ou_path=[]
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
            ou_path=None
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
            ou_path=[]
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
            ou_path=[]
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
            ou_path=[]
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
            ou_path=["Root", "Production"]
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
            {"key": "Team", "value": "Backend"}
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
            {"key": "Team", "value": "Backend"}
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
        assert "Filter expression cannot be empty" in errors[0].message
    
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
    
    @patch('src.awsideman.aws_clients.manager.build_organization_hierarchy')
    @patch('src.awsideman.aws_clients.manager.get_account_details')
    def test_resolve_wildcard_accounts(self, mock_get_details, mock_build_hierarchy):
        """Test resolving wildcard accounts."""
        # Mock organization hierarchy
        account_node = OrgNode(
            id="123456789012",
            name="Test Account",
            type=NodeType.ACCOUNT,
            children=[]
        )
        root_node = OrgNode(
            id="r-1234567890",
            name="Root",
            type=NodeType.ROOT,
            children=[account_node]
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
            ou_path=["Root"]
        )
        mock_get_details.return_value = mock_account_details
        
        # Mock describe_account
        self.mock_org_client.describe_account.return_value = {
            'Id': '123456789012',
            'Name': 'Test Account',
            'Email': 'test@example.com',
            'Status': 'ACTIVE'
        }
        
        filter_obj = AccountFilter("*", self.mock_org_client)
        accounts = filter_obj.resolve_accounts()
        
        assert len(accounts) == 1
        assert accounts[0].account_id == "123456789012"
        assert accounts[0].account_name == "Test Account"
    
    @patch('src.awsideman.aws_clients.manager.build_organization_hierarchy')
    @patch('src.awsideman.aws_clients.manager.get_account_details')
    def test_resolve_tag_filtered_accounts(self, mock_get_details, mock_build_hierarchy):
        """Test resolving tag-filtered accounts."""
        # Mock organization hierarchy with two accounts
        account1_node = OrgNode(
            id="123456789012",
            name="Prod Account",
            type=NodeType.ACCOUNT,
            children=[]
        )
        account2_node = OrgNode(
            id="123456789013",
            name="Dev Account",
            type=NodeType.ACCOUNT,
            children=[]
        )
        root_node = OrgNode(
            id="r-1234567890",
            name="Root",
            type=NodeType.ROOT,
            children=[account1_node, account2_node]
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
                    ou_path=["Root"]
                )
            elif account_id == "123456789013":
                return AccountDetails(
                    id="123456789013",
                    name="Dev Account",
                    email="dev@example.com",
                    status="ACTIVE",
                    joined_timestamp=datetime.now(),
                    tags={"Environment": "Development"},
                    ou_path=["Root"]
                )
        
        mock_get_details.side_effect = mock_get_details_side_effect
        
        # Mock describe_account
        def mock_describe_account_side_effect(account_id):
            if account_id == "123456789012":
                return {
                    'Id': '123456789012',
                    'Name': 'Prod Account',
                    'Email': 'prod@example.com',
                    'Status': 'ACTIVE'
                }
            elif account_id == "123456789013":
                return {
                    'Id': '123456789013',
                    'Name': 'Dev Account',
                    'Email': 'dev@example.com',
                    'Status': 'ACTIVE'
                }
        
        self.mock_org_client.describe_account.side_effect = mock_describe_account_side_effect
        
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
            ou_path=[]
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
            ou_path=[]
        )
        
        assert filter_obj._account_matches_all_tag_filters(account) is False


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
            {"key": "Team", "value": "Backend"}
        ]
        assert filters == expected
    
    def test_parse_multiple_tag_filters_comma_separated(self):
        """Test parsing comma-separated tag filters in single expression."""
        expressions = ["Environment=Production,Team=Backend"]
        filters = parse_multiple_tag_filters(expressions)
        
        expected = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"}
        ]
        assert filters == expected
    
    def test_parse_multiple_tag_filters_mixed(self):
        """Test parsing mixed format tag filters."""
        expressions = ["Environment=Production,Team=Backend", "Owner=John"]
        filters = parse_multiple_tag_filters(expressions)
        
        expected = [
            {"key": "Environment", "value": "Production"},
            {"key": "Team", "value": "Backend"},
            {"key": "Owner", "value": "John"}
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
            {"key": "Team", "value": "Backend"}
        ]
        expression = create_tag_filter_expression(filters)
        
        assert expression == "tag:Environment=Production,Team=Backend"
    
    def test_create_tag_filter_expression_empty(self):
        """Test creating tag filter expression from empty list."""
        filters = []
        expression = create_tag_filter_expression(filters)
        
        assert expression == ""