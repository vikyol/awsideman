"""Tests for user get command."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.commands.user.get import _get_user_group_memberships, get_user


def test_get_user_module_import():
    """Test that the get_user module can be imported."""
    try:
        from src.awsideman.commands.user.get import get_user

        assert get_user is not None
        assert callable(get_user)
    except ImportError as e:
        pytest.fail(f"Failed to import get_user: {e}")


def test_get_user_function_signature():
    """Test that the get_user function has the expected signature."""
    import inspect

    from src.awsideman.commands.user.get import get_user

    # Check that the function exists and is callable
    assert callable(get_user)

    # Check that it has the expected parameters
    sig = inspect.signature(get_user)
    expected_params = {"identifier", "profile"}

    actual_params = set(sig.parameters.keys())
    assert expected_params.issubset(
        actual_params
    ), f"Missing parameters: {expected_params - actual_params}"


def test_get_user_help_text():
    """Test that the get_user function has help text."""
    from src.awsideman.commands.user.get import get_user

    # Check that the function has a docstring
    assert get_user.__doc__ is not None
    assert len(get_user.__doc__.strip()) > 0

    # Check that the docstring contains expected content
    doc = get_user.__doc__.lower()
    assert "get" in doc
    assert "user" in doc
    assert "information" in doc


def test_get_user_typer_integration():
    """Test that the get_user function is properly integrated with Typer."""
    from src.awsideman.commands.user.get import get_user

    # Check that the function has the expected type hints
    assert hasattr(get_user, "__annotations__")

    annotations = get_user.__annotations__
    assert "identifier" in annotations
    assert "profile" in annotations


def test_get_user_parameter_types():
    """Test that the get_user function has correct parameter types."""
    import inspect

    from src.awsideman.commands.user.get import get_user

    sig = inspect.signature(get_user)

    # Check that identifier is a string
    assert sig.parameters["identifier"].annotation == str

    # Check that profile is optional string
    profile_param = sig.parameters["profile"]
    assert profile_param.annotation == str or "Optional" in str(profile_param.annotation)


class TestGetUserGroupMemberships:
    """Test the _get_user_group_memberships function."""

    def test_get_user_groups_success(self):
        """Test successfully getting user groups."""
        mock_identity_store = Mock()

        # Mock paginator for list_groups
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {
                "Groups": [
                    {"GroupId": "group-1", "DisplayName": "Group 1", "Description": "Desc 1"},
                    {"GroupId": "group-2", "DisplayName": "Group 2", "Description": "Desc 2"},
                ]
            }
        ]
        mock_identity_store.get_paginator.return_value = mock_paginator

        # Mock list_group_memberships responses
        mock_identity_store.list_group_memberships.side_effect = [
            {"GroupMemberships": [{"MemberId": {"UserId": "user-123"}, "MembershipId": "mem-1"}]},
            {"GroupMemberships": []},  # User not in second group
        ]

        result = _get_user_group_memberships(mock_identity_store, "store-123", "user-123")

        assert len(result) == 1
        assert result[0]["GroupId"] == "group-1"
        assert result[0]["DisplayName"] == "Group 1"
        assert result[0]["MembershipId"] == "mem-1"

    def test_get_user_groups_empty(self):
        """Test when user is not in any groups."""
        mock_identity_store = Mock()
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {"Groups": [{"GroupId": "group-1", "DisplayName": "Group 1"}]}
        ]
        mock_identity_store.get_paginator.return_value = mock_paginator
        mock_identity_store.list_group_memberships.return_value = {"GroupMemberships": []}

        result = _get_user_group_memberships(mock_identity_store, "store-123", "user-123")
        assert result == []

    def test_get_user_groups_api_error(self):
        """Test handling of API errors."""
        mock_identity_store = Mock()
        mock_identity_store.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "ListGroups"
        )

        result = _get_user_group_memberships(mock_identity_store, "store-123", "user-123")
        assert result == []


class TestGetUserIntegration:
    """Test the get_user command with group memberships integration."""

    @patch("src.awsideman.commands.user.get.validate_profile")
    @patch("src.awsideman.commands.user.get.validate_sso_instance")
    @patch("src.awsideman.commands.user.get.AWSClientManager")
    def test_get_user_with_groups(self, mock_aws_manager, mock_validate_sso, mock_validate_profile):
        """Test get_user command with group memberships."""
        # Mock profile validation
        mock_validate_profile.return_value = ("test-profile", {"region": "us-east-1"})
        mock_validate_sso.return_value = ("instance-arn", "store-123")

        # Mock AWS client manager
        mock_aws_client = Mock()
        mock_identity_store = Mock()
        mock_aws_client.get_identity_store_client.return_value = mock_identity_store
        mock_aws_manager.return_value = mock_aws_client

        # Mock user search
        mock_identity_store.list_users.return_value = {
            "Users": [{"UserId": "user-123", "UserName": "testuser"}]
        }

        # Mock user details
        mock_identity_store.describe_user.return_value = {
            "UserId": "user-123",
            "UserName": "testuser",
            "DisplayName": "Test User",
            "Name": {"GivenName": "Test", "FamilyName": "User"},
            "Emails": [{"Value": "test@example.com", "Primary": True}],
            "Status": "ENABLED",
        }

        # Mock group memberships
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {"Groups": [{"GroupId": "group-1", "DisplayName": "Group 1", "Description": "Desc 1"}]}
        ]
        mock_identity_store.get_paginator.return_value = mock_paginator
        mock_identity_store.list_group_memberships.return_value = {
            "GroupMemberships": [{"MemberId": {"UserId": "user-123"}, "MembershipId": "mem-1"}]
        }

        # This should not raise an exception
        try:
            result = get_user("testuser")
            assert result is not None
        except Exception as e:
            pytest.fail(f"get_user should not raise an exception: {e}")
