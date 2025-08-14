"""Tests for bulk resource resolver components."""

from unittest.mock import Mock

import pytest

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.bulk import AssignmentValidator, ResolutionResult, ResourceResolver


class TestResolutionResult:
    """Test ResolutionResult dataclass."""

    def test_success_result(self):
        """Test successful resolution result."""
        result = ResolutionResult(success=True, resolved_value="test-value")
        assert result.success is True
        assert result.resolved_value == "test-value"
        assert result.error_message is None

    def test_error_result(self):
        """Test error resolution result."""
        result = ResolutionResult(success=False, error_message="Test error")
        assert result.success is False
        assert result.resolved_value is None
        assert result.error_message == "Test error"


class TestResourceResolver:
    """Test ResourceResolver class."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)

        # Mock clients
        manager.get_identity_store_client.return_value = Mock()
        manager.get_identity_center_client.return_value = Mock()
        manager.get_organizations_client.return_value = Mock()

        return manager

    @pytest.fixture
    def resource_resolver(self, mock_aws_client_manager):
        """Create ResourceResolver instance for testing."""
        return ResourceResolver(
            aws_client_manager=mock_aws_client_manager,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            identity_store_id="d-1234567890",
        )

    def test_init(self, mock_aws_client_manager):
        """Test ResourceResolver initialization."""
        resolver = ResourceResolver(
            aws_client_manager=mock_aws_client_manager,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            identity_store_id="d-1234567890",
        )

        assert resolver.instance_arn == "arn:aws:sso:::instance/ssoins-1234567890abcdef"
        assert resolver.identity_store_id == "d-1234567890"
        assert resolver._principal_cache == {}
        assert resolver._permission_set_cache == {}
        assert resolver._account_cache == {}

    def test_resolve_user_name_success(self, resource_resolver):
        """Test successful user name resolution."""
        # Mock Identity Store response
        resource_resolver.identity_store_client.list_users.return_value = {
            "Users": [{"UserId": "user-1234567890abcdef", "UserName": "john.doe"}]
        }

        result = resource_resolver.resolve_principal_name("john.doe", "USER")

        assert result.success is True
        assert result.resolved_value == "user-1234567890abcdef"
        assert result.error_message is None

        # Verify API call
        resource_resolver.identity_store_client.list_users.assert_called_once_with(
            IdentityStoreId="d-1234567890",
            Filters=[{"AttributePath": "UserName", "AttributeValue": "john.doe"}],
        )

    def test_resolve_assignment_success(self, resource_resolver):
        """Test successful assignment resolution."""
        # Mock all resolution methods
        resource_resolver.resolve_principal_name = Mock(
            return_value=ResolutionResult(success=True, resolved_value="user-1234567890abcdef")
        )
        resource_resolver.resolve_permission_set_name = Mock(
            return_value=ResolutionResult(
                success=True,
                resolved_value="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            )
        )
        resource_resolver.resolve_account_name = Mock(
            return_value=ResolutionResult(success=True, resolved_value="123456789012")
        )

        assignment = {
            "principal_name": "john.doe",
            "principal_type": "USER",
            "permission_set_name": "ReadOnlyAccess",
            "account_name": "Production",
        }

        result = resource_resolver.resolve_assignment(assignment)

        assert result["resolution_success"] is True
        assert result["resolution_errors"] == []
        assert result["principal_id"] == "user-1234567890abcdef"
        assert (
            result["permission_set_arn"]
            == "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assert result["account_id"] == "123456789012"


class TestAssignmentValidator:
    """Test AssignmentValidator class."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)

        # Mock clients
        manager.get_identity_store_client.return_value = Mock()
        manager.get_identity_center_client.return_value = Mock()
        manager.get_organizations_client.return_value = Mock()

        return manager

    @pytest.fixture
    def assignment_validator(self, mock_aws_client_manager):
        """Create AssignmentValidator instance for testing."""
        return AssignmentValidator(
            aws_client_manager=mock_aws_client_manager,
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            identity_store_id="d-1234567890",
        )

    def test_validate_assignment_success(self, assignment_validator):
        """Test successful assignment validation."""
        # Mock validation methods
        assignment_validator.validate_principal = Mock(return_value=True)
        assignment_validator.validate_permission_set = Mock(return_value=True)
        assignment_validator.validate_account = Mock(return_value=True)

        assignment = {
            "principal_id": "user-1234567890abcdef",
            "permission_set_arn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            "account_id": "123456789012",
            "principal_type": "USER",
            "resolution_errors": [],
        }

        errors = assignment_validator.validate_assignment(assignment)

        assert len(errors) == 0
        assignment_validator.validate_principal.assert_called_once_with(
            "user-1234567890abcdef", "USER"
        )
        assignment_validator.validate_permission_set.assert_called_once_with(
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
        )
        assignment_validator.validate_account.assert_called_once_with("123456789012")
