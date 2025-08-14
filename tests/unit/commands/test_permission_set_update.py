"""Optimized unit tests for permission set update command - Fast and focused."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from botocore.exceptions import ClientError

from src.awsideman.commands.permission_set import update_permission_set


def test_update_permission_set_successful_basic_attributes():
    """Test successful update_permission_set operation with basic attributes."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.update_permission_set.return_value = {}
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet", "Description": "Updated description"}
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [{"Name": "AdministratorAccess"}]
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
        result = update_permission_set(
            identifier="TestPermissionSet",
            description="Updated test permission set description",
            session_duration="PT4H",
            relay_state="https://console.aws.amazon.com/",
            add_managed_policy=None,
            remove_managed_policy=None,
            profile=None,
        )

        assert "PermissionSet" in result
        assert "AttachedManagedPolicies" in result
        mock_sso_admin.update_permission_set.assert_called_once()


def test_update_permission_set_successful_add_managed_policies():
    """Test successful update_permission_set operation with adding managed policies."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [{"Name": "AdministratorAccess"}]
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
        result = update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=["arn:aws:iam::aws:policy/PowerUserAccess"],
            remove_managed_policy=None,
            profile=None,
        )

        assert len(result["AttachedPolicies"]) == 1
        mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_once()


def test_update_permission_set_successful_remove_managed_policies():
    """Test successful update_permission_set operation with removing managed policies."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.detach_managed_policy_from_permission_set.return_value = {}
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [{"Name": "AdministratorAccess"}]
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
        result = update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=None,
            remove_managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
            profile=None,
        )

        assert result["AttachedPolicies"] == []
        assert len(result["DetachedPolicies"]) == 1
        mock_sso_admin.detach_managed_policy_from_permission_set.assert_called_once()


def test_update_permission_set_successful_combined_operations():
    """Test successful update_permission_set operation with combined attribute and policy updates."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.update_permission_set.return_value = {}
    mock_sso_admin.attach_managed_policy_to_permission_set.return_value = {}
    mock_sso_admin.detach_managed_policy_from_permission_set.return_value = {}
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [{"Name": "AdministratorAccess"}]
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
        result = update_permission_set(
            identifier="TestPermissionSet",
            description="Updated description",
            session_duration="PT2H",
            relay_state=None,
            add_managed_policy=["arn:aws:iam::aws:policy/PowerUserAccess"],
            remove_managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
            profile=None,
        )

        assert len(result["AttachedPolicies"]) == 1
        assert len(result["DetachedPolicies"]) == 1
        mock_sso_admin.update_permission_set.assert_called_once()
        mock_sso_admin.attach_managed_policy_to_permission_set.assert_called_once()
        mock_sso_admin.detach_managed_policy_from_permission_set.assert_called_once()


def test_update_permission_set_policy_attachment_partial_failure():
    """Test update_permission_set with partial policy attachment failure."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = [
        {},  # First policy succeeds
        ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "AttachManagedPolicyToPermissionSet"
        ),  # Second policy fails
    ]
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [{"Name": "AdministratorAccess"}]
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
        result = update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=[
                "arn:aws:iam::aws:policy/PowerUserAccess",
                "arn:aws:iam::aws:policy/NonExistentPolicy",
            ],
            remove_managed_policy=None,
            profile=None,
        )

        assert len(result["AttachedPolicies"]) == 1
        assert mock_sso_admin.attach_managed_policy_to_permission_set.call_count == 2


def test_update_permission_set_conflict_exception_policy_attachment():
    """Test update_permission_set with ConflictException during policy attachment."""
    mock_sso_admin = MagicMock()
    mock_sso_admin.attach_managed_policy_to_permission_set.side_effect = ClientError(
        {"Error": {"Code": "ConflictException", "Message": "Policy is already attached"}},
        "AttachManagedPolicyToPermissionSet",
    )
    mock_sso_admin.describe_permission_set.return_value = {
        "PermissionSet": {"Name": "TestPermissionSet"}
    }
    mock_sso_admin.list_managed_policies_in_permission_set.return_value = {
        "AttachedManagedPolicies": [{"Name": "AdministratorAccess"}]
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
        result = update_permission_set(
            identifier="TestPermissionSet",
            description=None,
            session_duration=None,
            relay_state=None,
            add_managed_policy=["arn:aws:iam::aws:policy/AdministratorAccess"],
            remove_managed_policy=None,
            profile=None,
        )

        assert len(result["AttachedPolicies"]) == 0


def test_update_permission_set_invalid_identifier():
    """Test update_permission_set with invalid identifier."""
    with patch(
        "src.awsideman.commands.permission_set.resolve_permission_set_identifier",
        side_effect=typer.Exit(1),
    ):
        with pytest.raises(typer.Exit):
            update_permission_set(
                identifier="InvalidIdentifier",
                description=None,
                session_duration=None,
                relay_state=None,
                add_managed_policy=None,
                remove_managed_policy=None,
                profile=None,
            )
