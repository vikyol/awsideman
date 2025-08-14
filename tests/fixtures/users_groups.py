"""Users and groups test fixtures and data for awsideman tests."""

from datetime import datetime

import pytest


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "UserId": "user-1234567890abcdef",
        "UserName": "john.doe",
        "DisplayName": "John Doe",
        "Emails": [{"Value": "john.doe@company.com", "Primary": True}],
        "Active": True,
        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
        "ModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
    }


@pytest.fixture
def sample_group_data():
    """Sample group data for testing."""
    return {
        "GroupId": "group-1234567890abcdef",
        "DisplayName": "Developers",
        "Description": "Software development team",
        "Active": True,
        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
        "ModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
    }


@pytest.fixture
def sample_users_list():
    """Sample list of users for testing."""
    return [
        {
            "UserId": "user-1234567890abcdef",
            "UserName": "john.doe",
            "DisplayName": "John Doe",
            "Emails": [{"Value": "john.doe@company.com", "Primary": True}],
            "Active": True,
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "ModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        },
        {
            "UserId": "user-0987654321fedcba",
            "UserName": "jane.smith",
            "DisplayName": "Jane Smith",
            "Emails": [{"Value": "jane.smith@company.com", "Primary": True}],
            "Active": True,
            "CreatedDate": datetime(2023, 1, 3, 0, 0, 0),
            "ModifiedDate": datetime(2023, 1, 4, 0, 0, 0),
        },
        {
            "UserId": "user-abcdef1234567890",
            "UserName": "bob.wilson",
            "DisplayName": "Bob Wilson",
            "Emails": [{"Value": "bob.wilson@company.com", "Primary": True}],
            "Active": False,
            "CreatedDate": datetime(2023, 1, 5, 0, 0, 0),
            "ModifiedDate": datetime(2023, 1, 6, 0, 0, 0),
        },
    ]


@pytest.fixture
def sample_groups_list():
    """Sample list of groups for testing."""
    return [
        {
            "GroupId": "group-1234567890abcdef",
            "DisplayName": "Developers",
            "Description": "Software development team",
            "Active": True,
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "ModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        },
        {
            "GroupId": "group-0987654321fedcba",
            "DisplayName": "Operations",
            "Description": "IT operations team",
            "Active": True,
            "CreatedDate": datetime(2023, 1, 3, 0, 0, 0),
            "ModifiedDate": datetime(2023, 1, 4, 0, 0, 0),
        },
        {
            "GroupId": "group-abcdef1234567890",
            "DisplayName": "Managers",
            "Description": "Management team",
            "Active": True,
            "CreatedDate": datetime(2023, 1, 5, 0, 0, 0),
            "ModifiedDate": datetime(2023, 1, 6, 0, 0, 0),
        },
    ]


@pytest.fixture
def sample_group_members():
    """Sample group members for testing."""
    return [
        {
            "GroupId": "group-1234567890abcdef",
            "MemberId": "user-1234567890abcdef",
            "MemberType": "USER",
            "UserName": "john.doe",
            "DisplayName": "John Doe",
        },
        {
            "GroupId": "group-1234567890abcdef",
            "MemberId": "user-0987654321fedcba",
            "MemberType": "USER",
            "UserName": "jane.smith",
            "DisplayName": "Jane Smith",
        },
    ]


@pytest.fixture
def sample_user_assignments():
    """Sample user assignments for testing."""
    return [
        {
            "UserId": "user-1234567890abcdef",
            "UserName": "john.doe",
            "DisplayName": "John Doe",
            "AccountId": "123456789012",
            "AccountName": "Production",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            "PermissionSetName": "AdministratorAccess",
        },
        {
            "UserId": "user-0987654321fedcba",
            "UserName": "jane.smith",
            "DisplayName": "Jane Smith",
            "AccountId": "098765432109",
            "AccountName": "Development",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-readonly",
            "PermissionSetName": "ReadOnlyAccess",
        },
    ]


@pytest.fixture
def users_groups_factory():
    """Factory for creating users and groups test data."""

    class UsersGroupsFactory:
        @staticmethod
        def create_user(
            user_id="user-123",
            username="test.user",
            display_name="Test User",
            email="test.user@company.com",
            active=True,
        ):
            """Create a user for testing."""
            return {
                "UserId": user_id,
                "UserName": username,
                "DisplayName": display_name,
                "Emails": [{"Value": email, "Primary": True}],
                "Active": active,
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                "ModifiedDate": datetime(2023, 1, 1, 0, 0, 0),
            }

        @staticmethod
        def create_group(
            group_id="group-123", display_name="TestGroup", description="Test group", active=True
        ):
            """Create a group for testing."""
            return {
                "GroupId": group_id,
                "DisplayName": display_name,
                "Description": description,
                "Active": active,
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                "ModifiedDate": datetime(2023, 1, 1, 0, 0, 0),
            }

        @staticmethod
        def create_group_member(
            group_id="group-123",
            member_id="user-123",
            member_type="USER",
            username="test.user",
            display_name="Test User",
        ):
            """Create a group member for testing."""
            return {
                "GroupId": group_id,
                "MemberId": member_id,
                "MemberType": member_type,
                "UserName": username,
                "DisplayName": display_name,
            }

        @staticmethod
        def create_user_assignment(
            user_id="user-123",
            username="test.user",
            display_name="Test User",
            account_id="123456789012",
            account_name="TestAccount",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-test",
            permission_set_name="TestPermissionSet",
        ):
            """Create a user assignment for testing."""
            return {
                "UserId": user_id,
                "UserName": username,
                "DisplayName": display_name,
                "AccountId": account_id,
                "AccountName": account_name,
                "PermissionSetArn": permission_set_arn,
                "PermissionSetName": permission_set_name,
            }

        @staticmethod
        def create_users_batch(count=5, base_username="test.user"):
            """Create multiple users for testing."""
            users = []
            for i in range(count):
                username = f"{base_username}{i}"
                users.append(
                    {
                        "UserId": f"user-{i}",
                        "UserName": username,
                        "DisplayName": f"Test User {i}",
                        "Emails": [{"Value": f"{username}@company.com", "Primary": True}],
                        "Active": True,
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                        "ModifiedDate": datetime(2023, 1, 1, 0, 0, 0),
                    }
                )
            return users

        @staticmethod
        def create_groups_batch(count=5, base_name="TestGroup"):
            """Create multiple groups for testing."""
            groups = []
            for i in range(count):
                name = f"{base_name}{i}"
                groups.append(
                    {
                        "GroupId": f"group-{i}",
                        "DisplayName": name,
                        "Description": f"Test group {i}",
                        "Active": True,
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                        "ModifiedDate": datetime(2023, 1, 1, 0, 0, 0),
                    }
                )
            return groups

    return UsersGroupsFactory()
