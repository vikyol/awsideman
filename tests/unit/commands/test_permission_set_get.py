"""Optimized unit tests for permission set get command - Fast and focused."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.permission_set import get_permission_set


def test_get_permission_set_by_name_successful():
    """Test successful get_permission_set operation by name."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {
            "Name": "AdminAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/test",
            "Description": "Admin access",
            "SessionDuration": "PT8H",
            "RelayState": "https://console.aws.amazon.com/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        }
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [
            {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"}
        ]
    }

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
        result = get_permission_set("AdminAccess")

        assert result["Name"] == "AdminAccess"
        assert result["Description"] == "Admin access"
        mock_sso_admin.describe_permission_set.assert_called_once()


def test_get_permission_set_by_arn_successful():
    """Test successful get_permission_set operation by ARN."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {
            "Name": "AdminAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/test",
            "Description": "Admin access",
            "SessionDuration": "PT8H",
            "RelayState": "https://console.aws.amazon.com/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        }
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [
            {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"}
        ]
    }

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
        result = get_permission_set("arn:aws:sso:::permissionSet/test")

        assert result["Name"] == "AdminAccess"
        assert result["PermissionSetArn"] == "arn:aws:sso:::permissionSet/test"
        mock_sso_admin.describe_permission_set.assert_called_once()


def test_get_permission_set_with_profile():
    """Test successful get_permission_set operation with specific profile."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {
            "Name": "AdminAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/test",
            "Description": "Admin access",
            "SessionDuration": "PT8H",
            "RelayState": "https://console.aws.amazon.com/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        }
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [
            {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"}
        ]
    }

    with patch.multiple(
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
    ):
        result = get_permission_set("AdminAccess", profile="test-profile")

        assert result["Name"] == "AdminAccess"
        mock_sso_admin.describe_permission_set.assert_called_once()


def test_get_permission_set_resource_not_found_exception():
    """Test get_permission_set with ResourceNotFoundException."""
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
        with pytest.raises(typer.Exit):
            get_permission_set("NonExistentPermissionSet")

        mock_sso_admin.describe_permission_set.assert_called_once()


def test_get_permission_set_invalid_identifier_scenarios():
    """Test get_permission_set with invalid identifier scenarios."""
    with patch(
        "src.awsideman.commands.permission_set.resolve_permission_set_identifier",
        side_effect=typer.Exit(1),
    ):
        with pytest.raises(typer.Exit):
            get_permission_set("InvalidIdentifier")


def test_get_permission_set_profile_validation_failure():
    """Test get_permission_set with profile validation failure."""
    with patch("src.awsideman.commands.permission_set.validate_profile", side_effect=typer.Exit(1)):
        with pytest.raises(typer.Exit):
            get_permission_set("AdminAccess", profile="non-existent-profile")


def test_get_permission_set_sso_instance_validation_failure():
    """Test get_permission_set with SSO instance validation failure."""
    with patch(
        "src.awsideman.commands.permission_set.validate_sso_instance", side_effect=typer.Exit(1)
    ):
        with pytest.raises(typer.Exit):
            get_permission_set("AdminAccess")


def test_get_permission_set_empty_managed_policies():
    """Test get_permission_set with no managed policies attached."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {
            "Name": "AdminAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/test",
            "Description": "Admin access",
            "SessionDuration": "PT8H",
            "RelayState": "https://console.aws.amazon.com/",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        }
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": []
    }

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
        result = get_permission_set("AdminAccess")

        assert result["Name"] == "AdminAccess"
        assert result["PermissionSetArn"] == "arn:aws:sso:::permissionSet/test"
        # The result should contain the permission set data, not the managed policies
        assert "Name" in result
        assert "PermissionSetArn" in result
