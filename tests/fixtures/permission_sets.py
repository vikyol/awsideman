"""Permission set test fixtures and data for awsideman tests."""

from datetime import datetime

import pytest


@pytest.fixture
def sample_permission_set_data():
    """Sample permission set data for testing."""
    return {
        "Name": "TestPermissionSet",
        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        "Description": "Test permission set description",
        "SessionDuration": "PT8H",
        "RelayState": "https://console.aws.amazon.com/",
        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
        "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
    }


@pytest.fixture
def sample_create_response():
    """Sample create permission set response for testing."""
    return {
        "PermissionSet": {
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        }
    }


@pytest.fixture
def sample_managed_policies():
    """Sample managed policies for testing."""
    return [
        {"Name": "AdministratorAccess", "Arn": "arn:aws:iam::aws:policy/AdministratorAccess"},
        {"Name": "ReadOnlyAccess", "Arn": "arn:aws:iam::aws:policy/ReadOnlyAccess"},
        {"Name": "PowerUserAccess", "Arn": "arn:aws:iam::aws:policy/PowerUserAccess"},
    ]


@pytest.fixture
def sample_permission_sets_list():
    """Sample list of permission sets for testing."""
    return [
        {
            "Name": "AdministratorAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            "Description": "Full access to AWS services and resources",
            "SessionDuration": "PT8H",
            "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 1, 0, 0, 0),
        },
        {
            "Name": "ReadOnlyAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-readonly",
            "Description": "Read-only access to AWS services and resources",
            "SessionDuration": "PT4H",
            "CreatedDate": datetime(2023, 1, 2, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
        },
        {
            "Name": "PowerUserAccess",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-poweruser",
            "Description": "Power user access to AWS services and resources",
            "SessionDuration": "PT8H",
            "CreatedDate": datetime(2023, 1, 3, 0, 0, 0),
            "LastModifiedDate": datetime(2023, 1, 3, 0, 0, 0),
        },
    ]


@pytest.fixture
def sample_permission_set_assignments():
    """Sample permission set assignments for testing."""
    return [
        {
            "AccountId": "123456789012",
            "AccountName": "Production",
            "PrincipalId": "user-123",
            "PrincipalName": "john.doe",
            "PrincipalType": "USER",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-admin",
            "PermissionSetName": "AdministratorAccess",
        },
        {
            "AccountId": "098765432109",
            "AccountName": "Development",
            "PrincipalId": "group-456",
            "PrincipalName": "developers",
            "PrincipalType": "GROUP",
            "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-123/ps-readonly",
            "PermissionSetName": "ReadOnlyAccess",
        },
    ]


@pytest.fixture
def permission_set_factory():
    """Factory for creating permission set test data."""

    class PermissionSetFactory:
        @staticmethod
        def create_permission_set(
            name="TestPermissionSet",
            description="Test description",
            session_duration="PT8H",
            relay_state=None,
        ):
            """Create a permission set for testing."""
            return {
                "Name": name,
                "PermissionSetArn": f"arn:aws:sso:::permissionSet/ssoins-123/ps-{name.lower().replace(' ', '-')}",
                "Description": description,
                "SessionDuration": session_duration,
                "RelayState": relay_state,
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                "LastModifiedDate": datetime(2023, 1, 1, 0, 0, 0),
            }

        @staticmethod
        def create_managed_policy(name="TestPolicy", arn=None):
            """Create a managed policy for testing."""
            if arn is None:
                arn = f"arn:aws:iam::aws:policy/{name}"

            return {"Name": name, "Arn": arn}

        @staticmethod
        def create_permission_set_assignment(
            account_id="123456789012",
            account_name="TestAccount",
            principal_id="user-123",
            principal_name="test.user",
            principal_type="USER",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-test",
            permission_set_name="TestPermissionSet",
        ):
            """Create a permission set assignment for testing."""
            return {
                "AccountId": account_id,
                "AccountName": account_name,
                "PrincipalId": principal_id,
                "PrincipalName": principal_name,
                "PrincipalType": principal_type,
                "PermissionSetArn": permission_set_arn,
                "PermissionSetName": permission_set_name,
            }

        @staticmethod
        def create_permission_sets_batch(count=5, base_name="TestPermissionSet"):
            """Create multiple permission sets for testing."""
            permission_sets = []
            for i in range(count):
                name = f"{base_name}{i}"
                permission_sets.append(
                    {
                        "Name": name,
                        "PermissionSetArn": f"arn:aws:sso:::permissionSet/ssoins-123/ps-{name.lower().replace(' ', '-')}",
                        "Description": f"Test permission set {i}",
                        "SessionDuration": "PT8H",
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                        "LastModifiedDate": datetime(2023, 1, 1, 0, 0, 0),
                    }
                )
            return permission_sets

    return PermissionSetFactory()
