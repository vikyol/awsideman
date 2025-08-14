"""Optimized unit tests for permission set list command - Fast and focused."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError, ConnectionError

from src.awsideman.commands.permission_set import (
    _list_permission_sets_internal as list_permission_sets,
)


def test_list_permission_sets_successful():
    """Test successful list_permission_sets operation."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": [
            "arn:aws:sso:::permissionSet/ssoins-test/ps-1",
            "arn:aws:sso:::permissionSet/ssoins-test/ps-2",
        ],
        "NextToken": None,
    }
    mock_sso_admin.describe_permission_set.side_effect = [
        {"PermissionSet": {"Name": "AdminAccess", "Description": "Admin access"}},
        {"PermissionSet": {"Name": "ReadOnlyAccess", "Description": "Read-only access"}},
    ]

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
        get_single_key=MagicMock(),
    ):
        result, next_token = list_permission_sets()

        assert len(result) == 2
        assert result[0]["Name"] == "AdminAccess"
        assert result[1]["Name"] == "ReadOnlyAccess"
        assert next_token is None
        mock_sso_admin.list_permission_sets.assert_called_once()


def test_list_permission_sets_with_filter():
    """Test list_permission_sets with filter."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": [
            "arn:aws:sso:::permissionSet/ssoins-test/ps-1",
            "arn:aws:sso:::permissionSet/ssoins-test/ps-2",
        ],
        "NextToken": None,
    }
    mock_sso_admin.describe_permission_set.side_effect = [
        {"PermissionSet": {"Name": "AdminAccess", "Description": "Admin access"}},
        {"PermissionSet": {"Name": "ReadOnlyAccess", "Description": "Read-only access"}},
    ]

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        validate_filter=MagicMock(return_value=True),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
        get_single_key=MagicMock(),
    ):
        result, next_token = list_permission_sets(filter="name=Admin")

        assert len(result) == 1
        assert result[0]["Name"] == "AdminAccess"
        assert next_token is None


def test_list_permission_sets_with_pagination():
    """Test list_permission_sets with pagination."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-test/ps-1"],
        "NextToken": "next-page-token",
    }
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "AdminAccess", "Description": "Admin access"}
    }

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
        get_single_key=MagicMock(return_value="q"),
    ):
        result, next_token = list_permission_sets()

        assert len(result) == 1
        assert result[0]["Name"] == "AdminAccess"
        assert next_token == "next-page-token"


def test_list_permission_sets_with_next_token():
    """Test list_permission_sets with next_token parameter."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-test/ps-2"],
        "NextToken": None,
    }
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "ReadOnlyAccess", "Description": "Read-only access"}
    }

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
        get_single_key=MagicMock(),
    ):
        result, next_token = list_permission_sets(next_token="provided-token")

        assert len(result) == 1
        assert result[0]["Name"] == "ReadOnlyAccess"
        assert next_token is None
        mock_sso_admin.list_permission_sets.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/test", NextToken="provided-token"
        )


def test_list_permission_sets_with_limit():
    """Test list_permission_sets with limit."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-test/ps-1"],
        "NextToken": None,
    }
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "AdminAccess", "Description": "Admin access"}
    }

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        validate_limit=MagicMock(return_value=True),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
        get_single_key=MagicMock(),
    ):
        result, next_token = list_permission_sets(limit=1)

        assert len(result) == 1
        assert result[0]["Name"] == "AdminAccess"
        assert next_token is None
        mock_sso_admin.list_permission_sets.assert_called_once_with(
            InstanceArn="arn:aws:sso:::instance/test", MaxResults=1
        )


def test_list_permission_sets_empty_result():
    """Test list_permission_sets with empty result."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.return_value = {"PermissionSets": [], "NextToken": None}

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
        get_single_key=MagicMock(),
    ):
        result, next_token = list_permission_sets()

        assert result == []
        assert next_token is None
        mock_sso_admin.list_permission_sets.assert_called_once()


def test_list_permission_sets_invalid_filter_format():
    """Test list_permission_sets with invalid filter format."""
    with patch("src.awsideman.commands.permission_set.validate_filter", return_value=False):
        with pytest.raises(typer.Exit):
            list_permission_sets(filter="invalid-filter")


def test_list_permission_sets_api_error():
    """Test list_permission_sets with API error."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "User is not authorized"}},
        "ListPermissionSets",
    )

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
    ):
        with pytest.raises(typer.Exit):
            list_permission_sets()

        mock_sso_admin.list_permission_sets.assert_called_once()


def test_list_permission_sets_permission_set_details_error():
    """Test list_permission_sets with error retrieving permission set details."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.return_value = {
        "PermissionSets": ["arn:aws:sso:::permissionSet/ssoins-test/ps-1"],
        "NextToken": None,
    }
    mock_sso_admin.describe_permission_set.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "User is not authorized"}},
        "DescribePermissionSet",
    )

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
        get_single_key=MagicMock(),
    ):
        result, next_token = list_permission_sets()

        assert len(result) == 0
        assert next_token is None


def test_list_permission_sets_network_error():
    """Test list_permission_sets with network error."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.list_permission_sets.side_effect = ConnectionError(
        error="Failed to connect to AWS"
    )

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
    ):
        with pytest.raises(typer.Exit):
            list_permission_sets()

        mock_sso_admin.list_permission_sets.assert_called_once()


def test_list_permission_sets_profile_validation_failure():
    """Test list_permission_sets with profile validation failure."""
    with patch("src.awsideman.commands.permission_set.validate_profile", side_effect=typer.Exit(1)):
        with pytest.raises(typer.Exit):
            list_permission_sets(profile="non-existent-profile")


def test_list_permission_sets_sso_instance_validation_failure():
    """Test list_permission_sets with SSO instance validation failure."""
    with patch(
        "src.awsideman.commands.permission_set.validate_sso_instance", side_effect=typer.Exit(1)
    ):
        with pytest.raises(typer.Exit):
            list_permission_sets()


def test_list_permission_sets_invalid_limit_validation():
    """Test list_permission_sets with invalid limit validation."""
    with patch("src.awsideman.commands.permission_set.validate_limit", return_value=False):
        with pytest.raises(typer.Exit):
            list_permission_sets(limit=-1)
