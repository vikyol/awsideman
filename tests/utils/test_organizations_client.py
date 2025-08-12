"""Tests for OrganizationsClient wrapper."""
from datetime import datetime
from unittest.mock import MagicMock

import boto3
import click
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from src.awsideman.aws_clients.manager import AWSClientManager, OrganizationsClient


@pytest.fixture
def mock_client_manager():
    """Create a mock AWSClientManager."""
    mock_manager = MagicMock(spec=AWSClientManager)
    mock_organizations_client = MagicMock()
    mock_manager.get_organizations_client.return_value = mock_organizations_client
    return mock_manager, mock_organizations_client


@pytest.fixture
def organizations_client(mock_client_manager):
    """Create an OrganizationsClient with mocked dependencies."""
    mock_manager, mock_boto_client = mock_client_manager
    client = OrganizationsClient(mock_manager)
    return client, mock_boto_client


@pytest.fixture
def stubbed_organizations_client():
    """Create an OrganizationsClient with stubbed boto3 client."""
    # Create real boto3 client for stubbing
    real_client = boto3.client("organizations", region_name="us-east-1")
    stubber = Stubber(real_client)

    # Create mock client manager that returns the stubbed client
    mock_manager = MagicMock(spec=AWSClientManager)
    mock_manager.get_organizations_client.return_value = real_client

    client = OrganizationsClient(mock_manager)
    return client, stubber


class TestOrganizationsClientBasic:
    """Test basic OrganizationsClient functionality."""

    def test_client_property_lazy_initialization(self, mock_client_manager):
        """Test that client property initializes the boto3 client lazily."""
        mock_manager, mock_boto_client = mock_client_manager
        client = OrganizationsClient(mock_manager)

        # Client should not be initialized yet
        assert client._client is None

        # Accessing client property should initialize it
        actual_client = client.client
        assert actual_client == mock_boto_client
        mock_manager.get_organizations_client.assert_called_once()

        # Second access should not call get_organizations_client again
        actual_client2 = client.client
        assert actual_client2 == mock_boto_client
        mock_manager.get_organizations_client.assert_called_once()


class TestListRoots:
    """Test list_roots method."""

    def test_list_roots_success(self, organizations_client):
        """Test successful list_roots operation."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_roots = [
            {
                "Id": "r-1234567890",
                "Name": "Root",
                "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
                "PolicyTypes": [{"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"}],
            }
        ]
        mock_boto_client.list_roots.return_value = {"Roots": expected_roots}

        # Call method
        result = client.list_roots()

        # Verify result
        assert result == expected_roots
        mock_boto_client.list_roots.assert_called_once()

    def test_list_roots_empty_response(self, organizations_client):
        """Test list_roots with empty response."""
        client, mock_boto_client = organizations_client

        # Mock empty response
        mock_boto_client.list_roots.return_value = {}

        # Call method
        result = client.list_roots()

        # Verify result
        assert result == []
        mock_boto_client.list_roots.assert_called_once()

    def test_list_roots_client_error(self, organizations_client):
        """Test list_roots with ClientError."""
        client, mock_boto_client = organizations_client

        # Mock ClientError
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform this action",
            }
        }
        mock_boto_client.list_roots.side_effect = ClientError(error_response, "ListRoots")

        # Call method and expect exception
        with pytest.raises(
            click.exceptions.Exit
        ):  # handle_aws_error calls typer.Exit which raises click.exceptions.Exit
            client.list_roots()

        mock_boto_client.list_roots.assert_called_once()

    def test_list_roots_with_stubber(self, stubbed_organizations_client):
        """Test list_roots using botocore Stubber."""
        client, stubber = stubbed_organizations_client

        # Set up stubbed response
        expected_response = {
            "Roots": [
                {
                    "Id": "r-1234567890",
                    "Name": "Root",
                    "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
                    "PolicyTypes": [{"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"}],
                }
            ]
        }
        stubber.add_response("list_roots", expected_response)

        with stubber:
            result = client.list_roots()
            assert result == expected_response["Roots"]


class TestListOrganizationalUnitsForParent:
    """Test list_organizational_units_for_parent method."""

    def test_list_organizational_units_for_parent_success(self, organizations_client):
        """Test successful list_organizational_units_for_parent operation."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_ous = [
            {
                "Id": "ou-1234567890-abcdefgh",
                "Name": "Engineering",
                "Arn": "arn:aws:organizations::123456789012:ou/o-1234567890/ou-1234567890-abcdefgh",
            },
            {
                "Id": "ou-1234567890-ijklmnop",
                "Name": "Marketing",
                "Arn": "arn:aws:organizations::123456789012:ou/o-1234567890/ou-1234567890-ijklmnop",
            },
        ]
        mock_boto_client.list_organizational_units_for_parent.return_value = {
            "OrganizationalUnits": expected_ous
        }

        # Call method
        result = client.list_organizational_units_for_parent("r-1234567890")

        # Verify result
        assert result == expected_ous
        mock_boto_client.list_organizational_units_for_parent.assert_called_once_with(
            ParentId="r-1234567890"
        )

    def test_list_organizational_units_for_parent_empty(self, organizations_client):
        """Test list_organizational_units_for_parent with empty response."""
        client, mock_boto_client = organizations_client

        # Mock empty response
        mock_boto_client.list_organizational_units_for_parent.return_value = {}

        # Call method
        result = client.list_organizational_units_for_parent("r-1234567890")

        # Verify result
        assert result == []
        mock_boto_client.list_organizational_units_for_parent.assert_called_once_with(
            ParentId="r-1234567890"
        )

    def test_list_organizational_units_for_parent_client_error(self, organizations_client):
        """Test list_organizational_units_for_parent with ClientError."""
        client, mock_boto_client = organizations_client

        # Mock ClientError
        error_response = {
            "Error": {
                "Code": "ParentNotFoundException",
                "Message": "The specified parent was not found",
            }
        }
        mock_boto_client.list_organizational_units_for_parent.side_effect = ClientError(
            error_response, "ListOrganizationalUnitsForParent"
        )

        # Call method and expect exception
        with pytest.raises(click.exceptions.Exit):
            client.list_organizational_units_for_parent("invalid-parent")

        mock_boto_client.list_organizational_units_for_parent.assert_called_once_with(
            ParentId="invalid-parent"
        )


class TestListAccountsForParent:
    """Test list_accounts_for_parent method."""

    def test_list_accounts_for_parent_success(self, organizations_client):
        """Test successful list_accounts_for_parent operation."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_accounts = [
            {
                "Id": "111111111111",
                "Name": "dev-account",
                "Email": "dev@example.com",
                "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/111111111111",
                "Status": "ACTIVE",
                "JoinedTimestamp": datetime(2021, 1, 1),
            },
            {
                "Id": "222222222222",
                "Name": "prod-account",
                "Email": "prod@example.com",
                "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/222222222222",
                "Status": "ACTIVE",
                "JoinedTimestamp": datetime(2021, 2, 1),
            },
        ]
        mock_boto_client.list_accounts_for_parent.return_value = {"Accounts": expected_accounts}

        # Call method
        result = client.list_accounts_for_parent("ou-1234567890-abcdefgh")

        # Verify result
        assert result == expected_accounts
        mock_boto_client.list_accounts_for_parent.assert_called_once_with(
            ParentId="ou-1234567890-abcdefgh"
        )

    def test_list_accounts_for_parent_empty(self, organizations_client):
        """Test list_accounts_for_parent with empty response."""
        client, mock_boto_client = organizations_client

        # Mock empty response
        mock_boto_client.list_accounts_for_parent.return_value = {}

        # Call method
        result = client.list_accounts_for_parent("ou-1234567890-abcdefgh")

        # Verify result
        assert result == []
        mock_boto_client.list_accounts_for_parent.assert_called_once_with(
            ParentId="ou-1234567890-abcdefgh"
        )


class TestDescribeAccount:
    """Test describe_account method."""

    def test_describe_account_success(self, organizations_client):
        """Test successful describe_account operation."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_account = {
            "Id": "111111111111",
            "Name": "dev-account",
            "Email": "dev@example.com",
            "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/111111111111",
            "Status": "ACTIVE",
            "JoinedTimestamp": datetime(2021, 1, 1),
        }
        mock_boto_client.describe_account.return_value = {"Account": expected_account}

        # Call method
        result = client.describe_account("111111111111")

        # Verify result
        assert result == expected_account
        mock_boto_client.describe_account.assert_called_once_with(AccountId="111111111111")

    def test_describe_account_empty_response(self, organizations_client):
        """Test describe_account with empty response."""
        client, mock_boto_client = organizations_client

        # Mock empty response
        mock_boto_client.describe_account.return_value = {}

        # Call method
        result = client.describe_account("111111111111")

        # Verify result
        assert result == {}
        mock_boto_client.describe_account.assert_called_once_with(AccountId="111111111111")

    def test_describe_account_not_found(self, organizations_client):
        """Test describe_account with account not found error."""
        client, mock_boto_client = organizations_client

        # Mock ClientError
        error_response = {
            "Error": {
                "Code": "AccountNotFoundException",
                "Message": "The specified account was not found",
            }
        }
        mock_boto_client.describe_account.side_effect = ClientError(
            error_response, "DescribeAccount"
        )

        # Call method and expect exception
        with pytest.raises(click.exceptions.Exit):
            client.describe_account("999999999999")

        mock_boto_client.describe_account.assert_called_once_with(AccountId="999999999999")


class TestListTagsForResource:
    """Test list_tags_for_resource method."""

    def test_list_tags_for_resource_success(self, organizations_client):
        """Test successful list_tags_for_resource operation."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_tags = [
            {"Key": "Environment", "Value": "Development"},
            {"Key": "Team", "Value": "Engineering"},
            {"Key": "Project", "Value": "WebApp"},
        ]
        mock_boto_client.list_tags_for_resource.return_value = {"Tags": expected_tags}

        # Call method
        result = client.list_tags_for_resource("111111111111")

        # Verify result
        assert result == expected_tags
        mock_boto_client.list_tags_for_resource.assert_called_once_with(ResourceId="111111111111")

    def test_list_tags_for_resource_empty(self, organizations_client):
        """Test list_tags_for_resource with empty response."""
        client, mock_boto_client = organizations_client

        # Mock empty response
        mock_boto_client.list_tags_for_resource.return_value = {}

        # Call method
        result = client.list_tags_for_resource("111111111111")

        # Verify result
        assert result == []
        mock_boto_client.list_tags_for_resource.assert_called_once_with(ResourceId="111111111111")

    def test_list_tags_for_resource_access_denied(self, organizations_client):
        """Test list_tags_for_resource with access denied error."""
        client, mock_boto_client = organizations_client

        # Mock ClientError
        error_response = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "User is not authorized to perform this action",
            }
        }
        mock_boto_client.list_tags_for_resource.side_effect = ClientError(
            error_response, "ListTagsForResource"
        )

        # Call method and expect exception
        with pytest.raises(click.exceptions.Exit):
            client.list_tags_for_resource("111111111111")

        mock_boto_client.list_tags_for_resource.assert_called_once_with(ResourceId="111111111111")


class TestListPoliciesForTarget:
    """Test list_policies_for_target method."""

    def test_list_policies_for_target_scp_success(self, organizations_client):
        """Test successful list_policies_for_target for SCPs."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_policies = [
            {
                "Id": "p-1234567890",
                "Name": "FullAWSAccess",
                "Description": "Allows access to all AWS services",
                "Type": "SERVICE_CONTROL_POLICY",
                "AwsManaged": True,
            },
            {
                "Id": "p-0987654321",
                "Name": "DenyHighRiskServices",
                "Description": "Denies access to high-risk AWS services",
                "Type": "SERVICE_CONTROL_POLICY",
                "AwsManaged": False,
            },
        ]
        mock_boto_client.list_policies_for_target.return_value = {"Policies": expected_policies}

        # Call method
        result = client.list_policies_for_target("111111111111", "SERVICE_CONTROL_POLICY")

        # Verify result
        assert result == expected_policies
        mock_boto_client.list_policies_for_target.assert_called_once_with(
            TargetId="111111111111", Filter="SERVICE_CONTROL_POLICY"
        )

    def test_list_policies_for_target_rcp_success(self, organizations_client):
        """Test successful list_policies_for_target for RCPs."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_policies = [
            {
                "Id": "p-rcp123456",
                "Name": "ResourceControlPolicy",
                "Description": "Controls resource access",
                "Type": "RESOURCE_CONTROL_POLICY",
                "AwsManaged": False,
            }
        ]
        mock_boto_client.list_policies_for_target.return_value = {"Policies": expected_policies}

        # Call method
        result = client.list_policies_for_target(
            "ou-1234567890-abcdefgh", "RESOURCE_CONTROL_POLICY"
        )

        # Verify result
        assert result == expected_policies
        mock_boto_client.list_policies_for_target.assert_called_once_with(
            TargetId="ou-1234567890-abcdefgh", Filter="RESOURCE_CONTROL_POLICY"
        )

    def test_list_policies_for_target_empty(self, organizations_client):
        """Test list_policies_for_target with empty response."""
        client, mock_boto_client = organizations_client

        # Mock empty response
        mock_boto_client.list_policies_for_target.return_value = {}

        # Call method
        result = client.list_policies_for_target("111111111111", "SERVICE_CONTROL_POLICY")

        # Verify result
        assert result == []
        mock_boto_client.list_policies_for_target.assert_called_once_with(
            TargetId="111111111111", Filter="SERVICE_CONTROL_POLICY"
        )

    def test_list_policies_for_target_policy_type_not_enabled(self, organizations_client):
        """Test list_policies_for_target with policy type not enabled error."""
        client, mock_boto_client = organizations_client

        # Mock ClientError
        error_response = {
            "Error": {
                "Code": "PolicyTypeNotEnabledException",
                "Message": "The specified policy type is not enabled",
            }
        }
        mock_boto_client.list_policies_for_target.side_effect = ClientError(
            error_response, "ListPoliciesForTarget"
        )

        # Call method and expect exception
        with pytest.raises(click.exceptions.Exit):
            client.list_policies_for_target("111111111111", "RESOURCE_CONTROL_POLICY")

        mock_boto_client.list_policies_for_target.assert_called_once_with(
            TargetId="111111111111", Filter="RESOURCE_CONTROL_POLICY"
        )


class TestListParents:
    """Test list_parents method."""

    def test_list_parents_success(self, organizations_client):
        """Test successful list_parents operation."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_parents = [{"Id": "ou-1234567890-abcdefgh", "Type": "ORGANIZATIONAL_UNIT"}]
        mock_boto_client.list_parents.return_value = {"Parents": expected_parents}

        # Call method
        result = client.list_parents("111111111111")

        # Verify result
        assert result == expected_parents
        mock_boto_client.list_parents.assert_called_once_with(ChildId="111111111111")

    def test_list_parents_root_parent(self, organizations_client):
        """Test list_parents for account with root as parent."""
        client, mock_boto_client = organizations_client

        # Mock successful response
        expected_parents = [{"Id": "r-1234567890", "Type": "ROOT"}]
        mock_boto_client.list_parents.return_value = {"Parents": expected_parents}

        # Call method
        result = client.list_parents("111111111111")

        # Verify result
        assert result == expected_parents
        mock_boto_client.list_parents.assert_called_once_with(ChildId="111111111111")

    def test_list_parents_empty(self, organizations_client):
        """Test list_parents with empty response."""
        client, mock_boto_client = organizations_client

        # Mock empty response
        mock_boto_client.list_parents.return_value = {}

        # Call method
        result = client.list_parents("111111111111")

        # Verify result
        assert result == []
        mock_boto_client.list_parents.assert_called_once_with(ChildId="111111111111")

    def test_list_parents_child_not_found(self, organizations_client):
        """Test list_parents with child not found error."""
        client, mock_boto_client = organizations_client

        # Mock ClientError
        error_response = {
            "Error": {
                "Code": "ChildNotFoundException",
                "Message": "The specified child was not found",
            }
        }
        mock_boto_client.list_parents.side_effect = ClientError(error_response, "ListParents")

        # Call method and expect exception
        with pytest.raises(click.exceptions.Exit):
            client.list_parents("999999999999")

        mock_boto_client.list_parents.assert_called_once_with(ChildId="999999999999")


class TestRetryBehavior:
    """Test retry behavior for all methods."""

    def test_throttling_error_handling(self, organizations_client):
        """Test that throttling errors are handled appropriately."""
        client, mock_boto_client = organizations_client

        # Mock throttling error
        throttling_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "ListRoots"
        )
        mock_boto_client.list_roots.side_effect = throttling_error

        # Call method and expect exception
        with pytest.raises(click.exceptions.Exit):
            client.list_roots()

        # Verify the method was called once (no retries due to immediate error handling)
        mock_boto_client.list_roots.assert_called_once()


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_various_client_errors(self, organizations_client):
        """Test handling of various AWS client errors."""
        client, mock_boto_client = organizations_client

        error_scenarios = [
            ("AccessDeniedException", "User is not authorized to perform this action"),
            ("InvalidParameterException", "Invalid parameter value"),
            ("ServiceException", "Internal service error"),
            ("TooManyRequestsException", "Too many requests"),
        ]

        for error_code, error_message in error_scenarios:
            mock_boto_client.list_roots.side_effect = ClientError(
                {"Error": {"Code": error_code, "Message": error_message}}, "ListRoots"
            )

            with pytest.raises(click.exceptions.Exit):
                client.list_roots()

            mock_boto_client.list_roots.reset_mock()

    def test_unexpected_exception(self, organizations_client):
        """Test handling of unexpected exceptions."""
        client, mock_boto_client = organizations_client

        # Mock unexpected exception
        mock_boto_client.list_roots.side_effect = ValueError("Unexpected error")

        # Call method and expect the exception to propagate
        with pytest.raises(ValueError):
            client.list_roots()

        mock_boto_client.list_roots.assert_called_once()


class TestIntegrationWithStubber:
    """Integration tests using botocore Stubber for more realistic testing."""

    def test_complete_workflow_with_stubber(self, stubbed_organizations_client):
        """Test a complete workflow using stubbed responses."""
        client, stubber = stubbed_organizations_client

        # Set up stubbed responses for a complete workflow

        # 1. List roots
        stubber.add_response(
            "list_roots",
            {
                "Roots": [
                    {
                        "Id": "r-1234567890",
                        "Name": "Root",
                        "Arn": "arn:aws:organizations::123456789012:root/o-1234567890/r-1234567890",
                        "PolicyTypes": [{"Type": "SERVICE_CONTROL_POLICY", "Status": "ENABLED"}],
                    }
                ]
            },
        )

        # 2. List OUs for root
        stubber.add_response(
            "list_organizational_units_for_parent",
            {
                "OrganizationalUnits": [
                    {
                        "Id": "ou-1234567890-abcdefgh",
                        "Name": "Engineering",
                        "Arn": "arn:aws:organizations::123456789012:ou/o-1234567890/ou-1234567890-abcdefgh",
                    }
                ]
            },
            {"ParentId": "r-1234567890"},
        )

        # 3. List accounts for OU
        stubber.add_response(
            "list_accounts_for_parent",
            {
                "Accounts": [
                    {
                        "Id": "111111111111",
                        "Name": "dev-account",
                        "Email": "dev@example.com",
                        "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/111111111111",
                        "Status": "ACTIVE",
                        "JoinedTimestamp": datetime(2021, 1, 1),
                    }
                ]
            },
            {"ParentId": "ou-1234567890-abcdefgh"},
        )

        # 4. Describe account
        stubber.add_response(
            "describe_account",
            {
                "Account": {
                    "Id": "111111111111",
                    "Name": "dev-account",
                    "Email": "dev@example.com",
                    "Arn": "arn:aws:organizations::123456789012:account/o-1234567890/111111111111",
                    "Status": "ACTIVE",
                    "JoinedTimestamp": datetime(2021, 1, 1),
                }
            },
            {"AccountId": "111111111111"},
        )

        # 5. List tags for account
        stubber.add_response(
            "list_tags_for_resource",
            {
                "Tags": [
                    {"Key": "Environment", "Value": "Development"},
                    {"Key": "Team", "Value": "Engineering"},
                ]
            },
            {"ResourceId": "111111111111"},
        )

        # 6. List policies for account
        stubber.add_response(
            "list_policies_for_target",
            {
                "Policies": [
                    {
                        "Id": "p-1234567890",
                        "Name": "FullAWSAccess",
                        "Description": "Allows access to all AWS services",
                        "Type": "SERVICE_CONTROL_POLICY",
                        "AwsManaged": True,
                    }
                ]
            },
            {"TargetId": "111111111111", "Filter": "SERVICE_CONTROL_POLICY"},
        )

        # 7. List parents for account
        stubber.add_response(
            "list_parents",
            {"Parents": [{"Id": "ou-1234567890-abcdefgh", "Type": "ORGANIZATIONAL_UNIT"}]},
            {"ChildId": "111111111111"},
        )

        with stubber:
            # Execute the workflow
            roots = client.list_roots()
            assert len(roots) == 1
            assert roots[0]["Id"] == "r-1234567890"

            ous = client.list_organizational_units_for_parent("r-1234567890")
            assert len(ous) == 1
            assert ous[0]["Name"] == "Engineering"

            accounts = client.list_accounts_for_parent("ou-1234567890-abcdefgh")
            assert len(accounts) == 1
            assert accounts[0]["Id"] == "111111111111"

            account = client.describe_account("111111111111")
            assert account["Name"] == "dev-account"

            tags = client.list_tags_for_resource("111111111111")
            assert len(tags) == 2
            assert tags[0]["Key"] == "Environment"

            policies = client.list_policies_for_target("111111111111", "SERVICE_CONTROL_POLICY")
            assert len(policies) == 1
            assert policies[0]["Name"] == "FullAWSAccess"

            parents = client.list_parents("111111111111")
            assert len(parents) == 1
            assert parents[0]["Type"] == "ORGANIZATIONAL_UNIT"
