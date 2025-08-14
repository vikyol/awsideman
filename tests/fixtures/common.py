"""Common test fixtures and configuration shared across all awsideman tests."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_validation_functions():
    """Mock all validation functions in one fixture to reduce repetitive patching."""
    with patch.multiple(
        "src.awsideman.commands.permission_set",
        validate_permission_set_name=MagicMock(return_value=True),
        validate_permission_set_description=MagicMock(return_value=True),
        validate_aws_managed_policy_arn=MagicMock(return_value=True),
        validate_profile=MagicMock(return_value=("default", {"region": "us-east-1"})),
        validate_sso_instance=MagicMock(
            return_value=("arn:aws:sso:::instance/ssoins-1234567890abcdef", "d-1234567890")
        ),
        resolve_permission_set_identifier=MagicMock(
            return_value=("arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef")
        ),
    ) as mocks:
        # Reset all mocks before each test
        for mock in mocks.values():
            if hasattr(mock, "reset_mock"):
                mock.reset_mock()
        yield mocks


@pytest.fixture
def mock_aws_infrastructure():
    """Mock AWS client infrastructure."""
    # Create fresh mocks for each test
    mock_client = MagicMock()
    mock_sso_admin = MagicMock()
    mock_client.get_client.return_value = mock_sso_admin

    with patch.multiple(
        "src.awsideman.commands.permission_set",
        AWSClientManager=MagicMock(return_value=mock_client),
        console=MagicMock(),
    ) as mocks:
        # Reset mocks before each test
        mock_client.reset_mock()
        mock_sso_admin.reset_mock()
        mock_client.get_client.return_value = mock_sso_admin

        mocks["mock_client"] = mock_client
        mocks["mock_sso_admin"] = mock_sso_admin
        yield mocks


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
    ]


class PermissionSetMockFactory:
    """Factory for creating permission set test mocks."""

    @staticmethod
    def create_aws_client_mock():
        """Create a mock AWS client with SSO Admin client."""
        mock = MagicMock()
        mock_sso_admin = MagicMock()
        mock.get_client.return_value = mock_sso_admin
        return mock, mock_sso_admin

    @staticmethod
    def create_permission_set_response(name="TestPermissionSet", description="Test description"):
        """Create a sample permission set response."""
        return {
            "PermissionSet": {
                "Name": name,
                "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
                "Description": description,
                "SessionDuration": "PT8H",
                "RelayState": "https://console.aws.amazon.com/",
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                "LastModifiedDate": datetime(2023, 1, 2, 0, 0, 0),
            }
        }

    @staticmethod
    def create_managed_policies_response(policies=None):
        """Create a sample managed policies response."""
        if policies is None:
            policies = [
                {
                    "Name": "AdministratorAccess",
                    "Arn": "arn:aws:iam::aws:policy/AdministratorAccess",
                }
            ]
        return {"AttachedManagedPolicies": policies}
