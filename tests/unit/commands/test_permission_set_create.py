"""Optimized unit tests for permission set create command - Fast and focused."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.permission_set import create_permission_set


def test_create_permission_set_successful_basic():
    """Test successful create_permission_set operation with basic parameters."""
    # Simple mock setup - only what's needed
    mock_sso_admin = MagicMock()
    mock_sso_admin.create_permission_set.return_value = {
        "PermissionSet": {"PermissionSetArn": "arn:aws:sso:::permissionSet/test"}
    }
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Test description"}
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": []
    }

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_permission_set_name=MagicMock(return_value=True),
        validate_permission_set_description=MagicMock(return_value=True),
        validate_aws_managed_policy_arn=MagicMock(return_value=True),
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
    ):
        result = create_permission_set(
            name="TestPermissionSet",
            description="Test description",
            session_duration="PT1H",
            relay_state=None,
            managed_policy=None,
            profile=None,
        )

        assert result["Name"] == "TestPermissionSet"
        mock_sso_admin.create_permission_set.assert_called_once()


def test_create_permission_set_with_managed_policies():
    """Test successful create_permission_set operation with managed policies."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.create_permission_set.return_value = {
        "PermissionSet": {"PermissionSetArn": "arn:aws:sso:::permissionSet/test"}
    }
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [{"Name": "AdministratorAccess"}]
    }

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_permission_set_name=MagicMock(return_value=True),
        validate_permission_set_description=MagicMock(return_value=True),
        validate_aws_managed_policy_arn=MagicMock(return_value=True),
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
    ):
        result = create_permission_set(
            name="TestPermissionSet",
            description="Test description",
            session_duration="PT1H",
            relay_state=None,
            managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
            profile=None,
        )

        assert len(result["AttachedManagedPolicies"]) == 1
        mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_once()


def test_create_permission_set_policy_attachment_failure():
    """Test create_permission_set with policy attachment failure."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.create_permission_set.return_value = {
        "PermissionSet": {"PermissionSetArn": "arn:aws:sso:::permissionSet/test"}
    }
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException"}}, "AttachManagedPolicyToPermissionSet"
    )
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": []
    }

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_permission_set_name=MagicMock(return_value=True),
        validate_permission_set_description=MagicMock(return_value=True),
        validate_aws_managed_policy_arn=MagicMock(return_value=True),
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
    ):
        result = create_permission_set(
            name="TestPermissionSet",
            description=None,
            session_duration="PT1H",
            relay_state=None,
            managed_policy=["arn:aws:iam::aws:policy/NonExistentPolicy"],
            profile=None,
        )

        # Should still succeed despite policy attachment failure
        assert result["Name"] == "TestPermissionSet"
        assert len(result["AttachedManagedPolicies"]) == 0


def test_create_permission_set_invalid_name():
    """Test create_permission_set with invalid name validation."""
    with patch(
        "src.awsideman.commands.permission_set.validate_permission_set_name", return_value=False
    ):
        with pytest.raises(typer.Exit):
            create_permission_set(
                name="",
                description=None,
                session_duration="PT1H",
                relay_state=None,
                managed_policy=None,
                profile=None,
            )


def test_create_permission_set_api_error():
    """Test create_permission_set with API error."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.create_permission_set.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException"}}, "CreatePermissionSet"
    )

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_permission_set_name=MagicMock(return_value=True),
        validate_permission_set_description=MagicMock(return_value=True),
        validate_aws_managed_policy_arn=MagicMock(return_value=True),
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(return_value=("arn:aws:sso:::instance/test", "d-test")),
        AWSClientManager=MagicMock(
            return_value=MagicMock(get_client=MagicMock(return_value=mock_sso_admin))
        ),
        console=MagicMock(),
    ):
        with pytest.raises(typer.Exit):
            create_permission_set(
                name="TestPermissionSet",
                description=None,
                session_duration="PT1H",
                relay_state=None,
                managed_policy=None,
                profile=None,
            )
