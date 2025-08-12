"""Integration tests for account filtering with Organizations API."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import OrganizationsClientWrapper
from src.awsideman.utils.account_filter import AccountFilter
from src.awsideman.utils.models import AccountDetails, NodeType, OrgNode


class TestAccountFilterIntegration:
    """Integration tests for AccountFilter with real Organizations API patterns."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_org_client = Mock(spec=OrganizationsClientWrapper)

    def test_wildcard_filter_with_complex_organization(self):
        """Test wildcard filtering with a complex organization structure."""
        # Mock a complex organization hierarchy
        with patch(
            "src.awsideman.aws_clients.manager.build_organization_hierarchy"
        ) as mock_build_hierarchy, patch(
            "src.awsideman.aws_clients.manager.get_account_details"
        ) as mock_get_details:
            # Create a complex organization structure
            prod_account = OrgNode(
                id="111111111111", name="Production Account", type=NodeType.ACCOUNT, children=[]
            )
            dev_account = OrgNode(
                id="222222222222", name="Development Account", type=NodeType.ACCOUNT, children=[]
            )
            test_account = OrgNode(
                id="333333333333", name="Test Account", type=NodeType.ACCOUNT, children=[]
            )

            prod_ou = OrgNode(
                id="ou-prod123", name="Production OU", type=NodeType.OU, children=[prod_account]
            )
            dev_ou = OrgNode(
                id="ou-dev123",
                name="Development OU",
                type=NodeType.OU,
                children=[dev_account, test_account],
            )

            root_node = OrgNode(
                id="r-1234567890", name="Root", type=NodeType.ROOT, children=[prod_ou, dev_ou]
            )

            mock_build_hierarchy.return_value = [root_node]

            # Mock account details for each account
            from datetime import datetime

            def mock_get_details_side_effect(client, account_id):
                account_data = {
                    "111111111111": AccountDetails(
                        id="111111111111",
                        name="Production Account",
                        email="prod@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime.now(),
                        tags={"Environment": "Production", "Team": "Platform"},
                        ou_path=["Root", "Production OU"],
                    ),
                    "222222222222": AccountDetails(
                        id="222222222222",
                        name="Development Account",
                        email="dev@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime.now(),
                        tags={"Environment": "Development", "Team": "Backend"},
                        ou_path=["Root", "Development OU"],
                    ),
                    "333333333333": AccountDetails(
                        id="333333333333",
                        name="Test Account",
                        email="test@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime.now(),
                        tags={"Environment": "Test", "Team": "QA"},
                        ou_path=["Root", "Development OU"],
                    ),
                }
                return account_data[account_id]

            mock_get_details.side_effect = mock_get_details_side_effect

            # Mock describe_account calls
            def mock_describe_account_side_effect(account_id):
                account_data = {
                    "111111111111": {
                        "Id": "111111111111",
                        "Name": "Production Account",
                        "Email": "prod@example.com",
                        "Status": "ACTIVE",
                    },
                    "222222222222": {
                        "Id": "222222222222",
                        "Name": "Development Account",
                        "Email": "dev@example.com",
                        "Status": "ACTIVE",
                    },
                    "333333333333": {
                        "Id": "333333333333",
                        "Name": "Test Account",
                        "Email": "test@example.com",
                        "Status": "ACTIVE",
                    },
                }
                return account_data[account_id]

            self.mock_org_client.describe_account.side_effect = mock_describe_account_side_effect

            # Test wildcard filter
            filter_obj = AccountFilter("*", self.mock_org_client)
            accounts = filter_obj.resolve_accounts()

            # Should return all 3 accounts
            assert len(accounts) == 3
            account_ids = {account.account_id for account in accounts}
            assert account_ids == {"111111111111", "222222222222", "333333333333"}

    def test_tag_filter_with_multiple_criteria(self):
        """Test tag filtering with multiple criteria."""
        with patch(
            "src.awsideman.aws_clients.manager.build_organization_hierarchy"
        ) as mock_build_hierarchy, patch(
            "src.awsideman.aws_clients.manager.get_account_details"
        ) as mock_get_details:
            # Create accounts with different tag combinations
            account1 = OrgNode(
                id="111111111111", name="Backend Prod", type=NodeType.ACCOUNT, children=[]
            )
            account2 = OrgNode(
                id="222222222222", name="Frontend Prod", type=NodeType.ACCOUNT, children=[]
            )
            account3 = OrgNode(
                id="333333333333", name="Backend Dev", type=NodeType.ACCOUNT, children=[]
            )

            root_node = OrgNode(
                id="r-1234567890",
                name="Root",
                type=NodeType.ROOT,
                children=[account1, account2, account3],
            )

            mock_build_hierarchy.return_value = [root_node]

            # Mock account details with different tag combinations
            from datetime import datetime

            def mock_get_details_side_effect(client, account_id):
                account_data = {
                    "111111111111": AccountDetails(
                        id="111111111111",
                        name="Backend Prod",
                        email="backend-prod@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime.now(),
                        tags={"Environment": "Production", "Team": "Backend"},
                        ou_path=["Root"],
                    ),
                    "222222222222": AccountDetails(
                        id="222222222222",
                        name="Frontend Prod",
                        email="frontend-prod@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime.now(),
                        tags={"Environment": "Production", "Team": "Frontend"},
                        ou_path=["Root"],
                    ),
                    "333333333333": AccountDetails(
                        id="333333333333",
                        name="Backend Dev",
                        email="backend-dev@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime.now(),
                        tags={"Environment": "Development", "Team": "Backend"},
                        ou_path=["Root"],
                    ),
                }
                return account_data[account_id]

            mock_get_details.side_effect = mock_get_details_side_effect

            # Mock describe_account calls
            def mock_describe_account_side_effect(account_id):
                account_data = {
                    "111111111111": {
                        "Id": "111111111111",
                        "Name": "Backend Prod",
                        "Email": "backend-prod@example.com",
                        "Status": "ACTIVE",
                    },
                    "222222222222": {
                        "Id": "222222222222",
                        "Name": "Frontend Prod",
                        "Email": "frontend-prod@example.com",
                        "Status": "ACTIVE",
                    },
                    "333333333333": {
                        "Id": "333333333333",
                        "Name": "Backend Dev",
                        "Email": "backend-dev@example.com",
                        "Status": "ACTIVE",
                    },
                }
                return account_data[account_id]

            self.mock_org_client.describe_account.side_effect = mock_describe_account_side_effect

            # Test single tag filter - should get both production accounts
            filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
            accounts = filter_obj.resolve_accounts()

            assert len(accounts) == 2
            account_ids = {account.account_id for account in accounts}
            assert account_ids == {"111111111111", "222222222222"}

            # Test multiple tag filter - should get only backend production account
            filter_obj = AccountFilter(
                "tag:Environment=Production,Team=Backend", self.mock_org_client
            )
            accounts = filter_obj.resolve_accounts()

            assert len(accounts) == 1
            assert accounts[0].account_id == "111111111111"
            assert accounts[0].account_name == "Backend Prod"

    def test_error_handling_during_account_resolution(self):
        """Test error handling when some accounts fail to resolve."""
        with patch(
            "src.awsideman.aws_clients.manager.build_organization_hierarchy"
        ) as mock_build_hierarchy, patch(
            "src.awsideman.aws_clients.manager.get_account_details"
        ) as mock_get_details:
            # Create accounts where one will fail
            account1 = OrgNode(
                id="111111111111", name="Good Account", type=NodeType.ACCOUNT, children=[]
            )
            account2 = OrgNode(
                id="222222222222", name="Bad Account", type=NodeType.ACCOUNT, children=[]
            )

            root_node = OrgNode(
                id="r-1234567890", name="Root", type=NodeType.ROOT, children=[account1, account2]
            )

            mock_build_hierarchy.return_value = [root_node]

            # Mock account details where one account fails
            from datetime import datetime

            def mock_get_details_side_effect(client, account_id):
                if account_id == "111111111111":
                    return AccountDetails(
                        id="111111111111",
                        name="Good Account",
                        email="good@example.com",
                        status="ACTIVE",
                        joined_timestamp=datetime.now(),
                        tags={"Environment": "Production"},
                        ou_path=["Root"],
                    )
                elif account_id == "222222222222":
                    raise ClientError(
                        error_response={
                            "Error": {"Code": "AccessDenied", "Message": "Access denied"}
                        },
                        operation_name="DescribeAccount",
                    )

            mock_get_details.side_effect = mock_get_details_side_effect

            # Mock describe_account calls
            def mock_describe_account_side_effect(account_id):
                if account_id == "111111111111":
                    return {
                        "Id": "111111111111",
                        "Name": "Good Account",
                        "Email": "good@example.com",
                        "Status": "ACTIVE",
                    }
                elif account_id == "222222222222":
                    return {
                        "Id": "222222222222",
                        "Name": "Bad Account",
                        "Email": "bad@example.com",
                        "Status": "ACTIVE",
                    }

            self.mock_org_client.describe_account.side_effect = mock_describe_account_side_effect

            # Test that filtering continues despite errors
            filter_obj = AccountFilter("*", self.mock_org_client)
            accounts = filter_obj.resolve_accounts()

            # Should return only the good account
            assert len(accounts) == 1
            assert accounts[0].account_id == "111111111111"
            assert accounts[0].account_name == "Good Account"

    def test_empty_organization_handling(self):
        """Test handling of empty organization."""
        with patch(
            "src.awsideman.aws_clients.manager.build_organization_hierarchy"
        ) as mock_build_hierarchy:
            # Mock empty organization
            root_node = OrgNode(id="r-1234567890", name="Root", type=NodeType.ROOT, children=[])

            mock_build_hierarchy.return_value = [root_node]

            # Test wildcard filter with empty organization
            filter_obj = AccountFilter("*", self.mock_org_client)
            accounts = filter_obj.resolve_accounts()

            # Should return empty list
            assert len(accounts) == 0

    def test_tag_filter_no_matches(self):
        """Test tag filter that matches no accounts."""
        with patch(
            "src.awsideman.aws_clients.manager.build_organization_hierarchy"
        ) as mock_build_hierarchy, patch(
            "src.awsideman.aws_clients.manager.get_account_details"
        ) as mock_get_details:
            # Create account with different tags
            account1 = OrgNode(
                id="111111111111", name="Test Account", type=NodeType.ACCOUNT, children=[]
            )

            root_node = OrgNode(
                id="r-1234567890", name="Root", type=NodeType.ROOT, children=[account1]
            )

            mock_build_hierarchy.return_value = [root_node]

            # Mock account details
            from datetime import datetime

            mock_get_details.return_value = AccountDetails(
                id="111111111111",
                name="Test Account",
                email="test@example.com",
                status="ACTIVE",
                joined_timestamp=datetime.now(),
                tags={"Environment": "Development"},
                ou_path=["Root"],
            )

            self.mock_org_client.describe_account.return_value = {
                "Id": "111111111111",
                "Name": "Test Account",
                "Email": "test@example.com",
                "Status": "ACTIVE",
            }

            # Test tag filter that doesn't match
            filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
            accounts = filter_obj.resolve_accounts()

            # Should return empty list
            assert len(accounts) == 0

    def test_filter_description_accuracy(self):
        """Test that filter descriptions accurately reflect the filter."""
        # Test wildcard description
        filter_obj = AccountFilter("*", self.mock_org_client)
        description = filter_obj.get_filter_description()
        assert description == "All accounts in the organization"

        # Test single tag description
        filter_obj = AccountFilter("tag:Environment=Production", self.mock_org_client)
        description = filter_obj.get_filter_description()
        assert description == "Accounts with tags: Environment=Production"

        # Test multiple tag description
        filter_obj = AccountFilter(
            "tag:Environment=Production,Team=Backend,Owner=John", self.mock_org_client
        )
        description = filter_obj.get_filter_description()
        expected = "Accounts with tags: Environment=Production, Team=Backend, Owner=John"
        assert description == expected
