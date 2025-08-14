"""Optimized unit tests for permission set delete command - Fast and focused."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.permission_set import delete_permission_set


def test_delete_permission_set_successful_by_name():
    """Test successful delete_permission_set operation by name."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test description"}
    }
    mock_sso_admin.delete_permission_set.return_value = {}

    with (
        patch.multiple(
            "src.awsideman.commands.permission_set",
            validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
            validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
            resolve_permission_set_identifier=MagicMock(
                return_value="arn:aws:sso:::permissionSet/test"
            ),
            AWSClientManager=MagicMock(
                return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
            ),
            console=MagicMock(),
        ),
        patch("typer.confirm", return_value=True),
    ):
        result = delete_permission_set(identifier="TestPermissionSet", profile=None)

        assert result is None
        mock_sso_admin.describe_permission_set.assert_called_once()
        mock_sso_admin.delete_permission_set.assert_called_once()


def test_delete_permission_set_successful_by_arn():
    """Test successful delete_permission_set operation by ARN."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test description"}
    }
    mock_sso_admin.delete_permission_set.return_value = {}

    with (
        patch.multiple(
            "src.awsideman.commands.permission_set",
            validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
            validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
            resolve_permission_set_identifier=MagicMock(
                return_value="arn:aws:sso:::permissionSet/test"
            ),
            AWSClientManager=MagicMock(
                return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
            ),
            console=MagicMock(),
        ),
        patch("typer.confirm", return_value=True),
    ):
        result = delete_permission_set(
            identifier="arn:aws:sso:::permissionSet/test",
            profile=None,
        )

        assert result is None
        mock_sso_admin.describe_permission_set.assert_called_once()
        mock_sso_admin.delete_permission_set.assert_called_once()


def test_delete_permission_set_successful_with_profile():
    """Test successful delete_permission_set operation with specific profile."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test description"}
    }
    mock_sso_admin.delete_permission_set.return_value = {}

    with (
        patch.multiple(
            "src.awsideman.commands.permission_set",
            validate_profile=MagicMock(return_value=("test-profile", {"region": "us-west-2"})),
            validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
            resolve_permission_set_identifier=MagicMock(
                return_value="arn:aws:sso:::permissionSet/test"
            ),
            AWSClientManager=MagicMock(
                return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
            ),
            console=MagicMock(),
        ),
        patch("typer.confirm", return_value=True),
    ):
        result = delete_permission_set(identifier="TestPermissionSet", profile="test-profile")

        assert result is None
        mock_sso_admin.describe_permission_set.assert_called_once()
        mock_sso_admin.delete_permission_set.assert_called_once()


def test_delete_permission_set_cancelled_by_user():
    """Test delete_permission_set operation cancelled by user."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test description"}
    }

    with (
        patch.multiple(
            "src.awsideman.commands.permission_set",
            validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
            validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
            resolve_permission_set_identifier=MagicMock(
                return_value="arn:aws:sso:::permissionSet/test"
            ),
            AWSClientManager=MagicMock(
                return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
            ),
            console=MagicMock(),
        ),
        patch("typer.confirm", return_value=False),
    ):
        result = delete_permission_set(identifier="TestPermissionSet", profile=None)

        assert result is None
        mock_sso_admin.describe_permission_set.assert_called_once()
        mock_sso_admin.delete_permission_set.assert_not_called()


def test_delete_permission_set_describe_failure_before_deletion():
    """Test delete_permission_set when describe fails before deletion."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Permission set not found"}},
        "DescribePermissionSet",
    )

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        resolve_permission_set_identifier=MagicMock(
            return_value="arn:aws:sso:::permissionSet/test"
        ),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
    ):
        with pytest.raises(typer.Exit) as exc_info:
            delete_permission_set(identifier="NonExistentPermissionSet", profile=None)

        assert exc_info.value.exit_code == 1
        mock_sso_admin.describe_permission_set.assert_called_once()
        mock_sso_admin.delete_permission_set.assert_not_called()


def test_delete_permission_set_identifier_resolution_failure():
    """Test delete_permission_set when identifier resolution fails."""
    with patch(
        "src.awsideman.commands.permission_set.resolve_permission_set_identifier",
        side_effect=typer.Exit(1),
    ):
        with pytest.raises(typer.Exit) as exc_info:
            delete_permission_set(identifier="NonExistentPermissionSet", profile=None)

        assert exc_info.value.exit_code == 1


def test_delete_permission_set_profile_validation_failure():
    """Test delete_permission_set with profile validation failure."""
    with patch("src.awsideman.commands.permission_set.validate_profile", side_effect=typer.Exit(1)):
        with pytest.raises(typer.Exit) as exc_info:
            delete_permission_set(identifier="TestPermissionSet", profile="non-existent-profile")

        assert exc_info.value.exit_code == 1


def test_delete_permission_set_sso_instance_validation_failure():
    """Test delete_permission_set with SSO instance validation failure."""
    with patch(
        "src.awsideman.commands.permission_set.validate_sso_instance", side_effect=typer.Exit(1)
    ):
        with pytest.raises(typer.Exit) as exc_info:
            delete_permission_set(identifier="TestPermissionSet", profile=None)

        assert exc_info.value.exit_code == 1
