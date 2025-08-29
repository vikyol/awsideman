"""AWS client test fixtures and mocks for awsideman tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_aws_client_manager():
    """Mock AWS client manager with all necessary clients."""
    mock_manager = MagicMock()

    # Mock SSO Admin client
    mock_sso_admin = MagicMock()
    mock_manager.get_identity_center_client.return_value = mock_sso_admin

    # Mock Identity Store client
    mock_identity_store = MagicMock()
    mock_manager.get_identity_store_client.return_value = mock_identity_store

    # Mock Organizations client
    mock_organizations = MagicMock()
    mock_manager.get_organizations_client.return_value = mock_organizations

    # Mock IAM client
    mock_iam = MagicMock()
    mock_manager.get_iam_client.return_value = mock_iam

    # Add profile attribute as string (not Mock) to fix OperationStore profile isolation
    mock_manager.profile = "test-profile"

    return mock_manager


@pytest.fixture
def mock_aws_client_manager_with_profile():
    """Mock AWS client manager with a specific profile name."""
    mock_manager = MagicMock()

    # Mock SSO Admin client
    mock_sso_admin = MagicMock()
    mock_manager.get_identity_center_client.return_value = mock_sso_admin

    # Mock Identity Store client
    mock_identity_store = MagicMock()
    mock_manager.get_identity_store_client.return_value = mock_identity_store

    # Mock Organizations client
    mock_organizations = MagicMock()
    mock_manager.get_organizations_client.return_value = mock_organizations

    # Mock IAM client
    mock_iam = MagicMock()
    mock_manager.get_iam_client.return_value = mock_iam

    # Add profile attribute as string (not Mock) to fix OperationStore profile isolation
    mock_manager.profile = "test-profile"

    return mock_manager


@pytest.fixture
def mock_sso_admin_client():
    """Mock SSO Admin client with common operations."""
    mock_client = MagicMock()

    # Mock common SSO Admin operations
    mock_client.list_permission_sets.return_value = {"PermissionSets": []}
    mock_client.describe_permission_set.return_value = {"PermissionSet": {}}
    mock_client.list_account_assignments.return_value = {"AccountAssignments": []}
    mock_client.create_account_assignment.return_value = {}
    mock_client.delete_account_assignment.return_value = {}

    return mock_client


@pytest.fixture
def mock_identity_store_client():
    """Mock Identity Store client with common operations."""
    mock_client = MagicMock()

    # Mock common Identity Store operations
    mock_client.list_users.return_value = {"Users": []}
    mock_client.list_groups.return_value = {"Groups": []}
    mock_client.describe_user.return_value = {"User": {}}
    mock_client.describe_group.return_value = {"Group": {}}

    return mock_client


@pytest.fixture
def mock_organizations_client():
    """Mock Organizations client with common operations."""
    mock_client = MagicMock()

    # Mock common Organizations operations
    mock_client.list_accounts.return_value = {"Accounts": []}
    mock_client.describe_account.return_value = {"Account": {}}
    mock_client.list_organizational_units_for_parent.return_value = {"OrganizationalUnits": []}

    return mock_client


@pytest.fixture
def mock_iam_client():
    """Mock IAM client with common operations."""
    mock_client = MagicMock()

    # Mock common IAM operations
    mock_client.list_policies.return_value = {"Policies": []}
    mock_client.get_policy.return_value = {"Policy": {}}
    mock_client.attach_policy.return_value = {}
    mock_client.detach_policy.return_value = {}

    return mock_client


@pytest.fixture
def aws_client_factory():
    """Factory for creating AWS client mocks with specific configurations."""

    class AWSClientFactory:
        @staticmethod
        def create_sso_admin_client(**kwargs):
            """Create a mock SSO Admin client with custom return values."""
            mock_client = MagicMock()

            # Set default return values
            defaults = {
                "list_permission_sets": {"PermissionSets": []},
                "describe_permission_set": {"PermissionSet": {}},
                "list_account_assignments": {"AccountAssignments": []},
                "create_account_assignment": {},
                "delete_account_assignment": {},
            }

            # Override with custom values
            defaults.update(kwargs)

            for method, return_value in defaults.items():
                getattr(mock_client, method).return_value = return_value

            return mock_client

        @staticmethod
        def create_identity_store_client(**kwargs):
            """Create a mock Identity Store client with custom return values."""
            mock_client = MagicMock()

            # Set default return values
            defaults = {
                "list_users": {"Users": []},
                "list_groups": {"Groups": []},
                "describe_user": {"User": {}},
                "describe_group": {"Group": {}},
            }

            # Override with custom values
            defaults.update(kwargs)

            for method, return_value in defaults.items():
                getattr(mock_client, method).return_value = return_value

            return mock_client

    return AWSClientFactory()


@pytest.fixture
def mock_aws_error():
    """Mock AWS error responses for testing error handling."""

    class AWSErrorFactory:
        @staticmethod
        def access_denied():
            """Create an AccessDenied error response."""
            return MagicMock(
                response={
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": "User is not authorized to perform this operation",
                    }
                }
            )

        @staticmethod
        def throttling_exception():
            """Create a ThrottlingException error response."""
            return MagicMock(
                response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
            )

        @staticmethod
        def resource_not_found():
            """Create a ResourceNotFoundException error response."""
            return MagicMock(
                response={
                    "Error": {
                        "Code": "ResourceNotFoundException",
                        "Message": "The specified resource does not exist",
                    }
                }
            )

    return AWSErrorFactory()
