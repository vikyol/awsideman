"""Tests for account metadata retrieval functionality."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients.manager import (
    OrganizationsClient,
    _calculate_ou_path,
    get_account_details,
)
from src.awsideman.utils.models import AccountDetails


class TestAccountMetadataRetrieval:
    """Test cases for account metadata retrieval functionality."""

    def test_get_account_details_success(self):
        """Test successful account details retrieval."""
        # Mock organizations client
        mock_client = Mock(spec=OrganizationsClient)

        # Mock account data
        joined_time = datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        mock_client.describe_account.return_value = {
            "Id": "123456789012",
            "Name": "test-account",
            "Email": "test@example.com",
            "Status": "ACTIVE",
            "JoinedTimestamp": joined_time,
        }

        # Mock tags data
        mock_client.list_tags_for_resource.return_value = [
            {"Key": "Environment", "Value": "Production"},
            {"Key": "Team", "Value": "DevOps"},
        ]

        # Mock OU path calculation
        with patch("src.awsideman.aws_clients.manager._calculate_ou_path") as mock_path:
            mock_path.return_value = ["Root", "Engineering", "Development"]

            # Call the function
            result = get_account_details(mock_client, "123456789012")

            # Verify the result
            assert isinstance(result, AccountDetails)
            assert result.id == "123456789012"
            assert result.name == "test-account"
            assert result.email == "test@example.com"
            assert result.status == "ACTIVE"
            assert result.joined_timestamp == joined_time
            assert result.tags == {"Environment": "Production", "Team": "DevOps"}
            assert result.ou_path == ["Root", "Engineering", "Development"]

            # Verify API calls were made
            mock_client.describe_account.assert_called_once_with("123456789012")
            mock_client.list_tags_for_resource.assert_called_once_with("123456789012")
            mock_path.assert_called_once_with(mock_client, "123456789012")

    def test_get_account_details_no_tags(self):
        """Test account details retrieval when tags API fails."""
        # Mock organizations client
        mock_client = Mock(spec=OrganizationsClient)

        # Mock account data
        joined_time = datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        mock_client.describe_account.return_value = {
            "Id": "123456789012",
            "Name": "test-account",
            "Email": "test@example.com",
            "Status": "ACTIVE",
            "JoinedTimestamp": joined_time,
        }

        # Mock tags API failure
        mock_client.list_tags_for_resource.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListTagsForResource"
        )

        # Mock OU path calculation
        with patch("src.awsideman.aws_clients.manager._calculate_ou_path") as mock_path:
            mock_path.return_value = ["Root"]

            # Call the function
            result = get_account_details(mock_client, "123456789012")

            # Verify the result has empty tags
            assert result.tags == {}
            assert result.id == "123456789012"
            assert result.name == "test-account"

    def test_get_account_details_account_not_found(self):
        """Test account details retrieval when account is not found."""
        # Mock organizations client
        mock_client = Mock(spec=OrganizationsClient)

        # Mock account not found
        mock_client.describe_account.return_value = {}

        # Call the function and expect ValueError
        with pytest.raises(ValueError, match="Account 123456789012 not found"):
            get_account_details(mock_client, "123456789012")

    def test_calculate_ou_path_simple_hierarchy(self):
        """Test OU path calculation for simple hierarchy."""
        # Mock organizations client
        mock_client = Mock(spec=OrganizationsClient)

        # Mock hierarchy: Account -> OU -> Root
        # We need to handle multiple calls to list_parents:
        # 1. Parents of account (returns OU)
        # 2. Parents of OU (returns Root)
        def mock_list_parents(child_id):
            if child_id == "123456789012":  # account
                return [{"Id": "ou-12345", "Type": "ORGANIZATIONAL_UNIT"}]
            elif child_id == "ou-12345":  # OU
                return [{"Id": "r-12345", "Type": "ROOT"}]
            else:
                return []

        mock_client.list_parents.side_effect = mock_list_parents

        # Mock OU details - when looking for OU under root
        mock_client.list_organizational_units_for_parent.return_value = [
            {"Id": "ou-12345", "Name": "Engineering"}
        ]

        # Mock root details
        mock_client.list_roots.return_value = [{"Id": "r-12345", "Name": "MyOrg Root"}]

        # Call the function
        result = _calculate_ou_path(mock_client, "123456789012")

        # Verify the path
        assert result == ["MyOrg Root", "Engineering"]

    def test_calculate_ou_path_direct_under_root(self):
        """Test OU path calculation for account directly under root."""
        # Mock organizations client
        mock_client = Mock(spec=OrganizationsClient)

        # Mock hierarchy: Account -> Root
        mock_client.list_parents.side_effect = [
            # Parents of account
            [{"Id": "r-12345", "Type": "ROOT"}]
        ]

        # Mock root details
        mock_client.list_roots.return_value = [{"Id": "r-12345", "Name": "MyOrg Root"}]

        # Call the function
        result = _calculate_ou_path(mock_client, "123456789012")

        # Verify the path
        assert result == ["MyOrg Root"]

    def test_calculate_ou_path_api_error(self):
        """Test OU path calculation when API calls fail."""
        # Mock organizations client
        mock_client = Mock(spec=OrganizationsClient)

        # Mock API error
        mock_client.list_parents.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListParents"
        )

        # Call the function
        result = _calculate_ou_path(mock_client, "123456789012")

        # Verify empty path is returned
        assert result == []
