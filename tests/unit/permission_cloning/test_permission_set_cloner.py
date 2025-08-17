"""
Unit tests for the PermissionSetCloner class.

Tests core functionality for cloning permission sets.
"""

from unittest.mock import Mock, patch

import pytest

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.permission_cloning.models import (
    CloneResult,
    CustomerManagedPolicy,
    PermissionSetConfig,
)
from src.awsideman.permission_cloning.permission_set_cloner import PermissionSetCloner


class TestPermissionSetCloner:
    """Test cases for PermissionSetCloner class."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        return Mock(spec=AWSClientManager)

    @pytest.fixture
    def mock_sso_client(self):
        """Create a mock SSO Admin client."""
        return Mock()

    @pytest.fixture
    def mock_sts_client(self):
        """Create a mock STS client."""
        return Mock()

    @pytest.fixture
    def sample_permission_set_config(self):
        """Create a sample permission set configuration."""
        return PermissionSetConfig(
            name="SourcePermissionSet",
            description="Source Description",
            session_duration="PT2H",
            relay_state_url="https://example.com",
            aws_managed_policies=["arn:aws:iam::aws:policy/AdministratorAccess"],
            customer_managed_policies=[CustomerManagedPolicy(name="CustomPolicy", path="/")],
            inline_policy='{"Version": "2012-10-17", "Statement": []}',
        )

    @pytest.fixture
    def permission_set_cloner(self, mock_client_manager):
        """Create a PermissionSetCloner instance."""
        mock_client_manager.get_sso_admin_client.return_value = Mock()
        mock_client_manager.get_client.return_value = Mock()

        # Create the cloner and then mock its permission set retriever
        cloner = PermissionSetCloner(mock_client_manager, "arn:aws:sso:::instance/test")
        cloner.permission_set_retriever = Mock()

        return cloner

    def test_init(self, permission_set_cloner, mock_client_manager):
        """Test PermissionSetCloner initialization."""
        assert permission_set_cloner.client_manager == mock_client_manager
        assert permission_set_cloner.instance_arn == "arn:aws:sso:::instance/test"
        assert permission_set_cloner.permission_set_retriever is not None

    def test_sso_admin_client_property(self, permission_set_cloner, mock_client_manager):
        """Test sso_admin_client property."""
        mock_sso_client = Mock()
        mock_client_manager.get_sso_admin_client.return_value = mock_sso_client

        client = permission_set_cloner.sso_admin_client

        assert client == mock_sso_client
        mock_client_manager.get_sso_admin_client.assert_called_once()

    def test_validate_clone_request_success(self, permission_set_cloner):
        """Test successful clone request validation."""
        # Mock that target permission set doesn't exist
        permission_set_cloner.permission_set_retriever.get_permission_set_by_name.return_value = (
            None
        )

        result = permission_set_cloner.validate_clone_request("SourceName", "TargetName")

        assert result.result_type.value == "SUCCESS"
        assert len(result.messages) == 0

    def test_validate_clone_request_empty_source(self, permission_set_cloner):
        """Test validation with empty source name."""
        result = permission_set_cloner.validate_clone_request("", "TargetName")

        assert result.result_type.value == "ERROR"
        assert "Source permission set name cannot be empty" in result.messages

    def test_validate_clone_request_empty_target(self, permission_set_cloner):
        """Test validation with empty target name."""
        result = permission_set_cloner.validate_clone_request("SourceName", "")

        assert result.result_type.value == "ERROR"
        assert "Target permission set name cannot be empty" in result.messages

    def test_validate_clone_request_same_names(self, permission_set_cloner):
        """Test validation with same source and target names."""
        result = permission_set_cloner.validate_clone_request("SameName", "SameName")

        assert result.result_type.value == "ERROR"
        assert "Source and target permission set names cannot be the same" in result.messages

    def test_validate_clone_request_target_exists(self, permission_set_cloner):
        """Test validation when target permission set already exists."""
        permission_set_cloner.permission_set_retriever.get_permission_set_by_name.return_value = (
            "existing-arn"
        )

        result = permission_set_cloner.validate_clone_request("SourceName", "ExistingName")

        assert result.result_type.value == "ERROR"
        assert "already exists" in result.messages[0]

    def test_validate_clone_request_invalid_target_name(self, permission_set_cloner):
        """Test validation with invalid target name characters."""
        permission_set_cloner.permission_set_retriever.get_permission_set_by_name.return_value = (
            None
        )

        result = permission_set_cloner.validate_clone_request("SourceName", "Invalid@Name")

        assert result.result_type.value == "ERROR"
        assert "invalid characters" in result.messages[0]

    def test_clone_permission_set_preview_mode(
        self, permission_set_cloner, sample_permission_set_config
    ):
        """Test permission set cloning in preview mode."""

        # Mock permission set retrieval - source exists, target doesn't
        def mock_get_permission_set_by_name(name):
            if name == "SourceName":
                return "source-arn"
            elif name == "TargetName":
                return None
            return None

        permission_set_cloner.permission_set_retriever.get_permission_set_by_name.side_effect = (
            mock_get_permission_set_by_name
        )
        permission_set_cloner.permission_set_retriever.get_permission_set_config.return_value = (
            sample_permission_set_config
        )

        result = permission_set_cloner.clone_permission_set(
            "SourceName", "TargetName", preview=True
        )

        assert result.success is True
        assert result.cloned_config == sample_permission_set_config
        assert result.rollback_id is None

    def test_clone_permission_set_validation_failure(self, permission_set_cloner):
        """Test permission set cloning with validation failure."""
        # Mock validation to fail
        with patch.object(permission_set_cloner, "validate_clone_request") as mock_validate:
            mock_validate.return_value = Mock(has_errors=True, messages=["Validation error"])

            result = permission_set_cloner.clone_permission_set("SourceName", "TargetName")

            assert result.success is False
            assert "Validation error" in result.error_message

    def test_clone_permission_set_source_not_found(self, permission_set_cloner):
        """Test permission set cloning when source is not found."""
        permission_set_cloner.permission_set_retriever.get_permission_set_by_name.return_value = (
            None
        )

        result = permission_set_cloner.clone_permission_set("SourceName", "TargetName")

        assert result.success is False
        assert "not found" in result.error_message

    def test_create_permission_set(self, permission_set_cloner, sample_permission_set_config):
        """Test creating a new permission set."""
        mock_sso_client = Mock()
        permission_set_cloner.client_manager.get_sso_admin_client.return_value = mock_sso_client

        mock_sso_client.create_permission_set.return_value = {
            "PermissionSet": {"PermissionSetArn": "new-arn"}
        }

        arn = permission_set_cloner._create_permission_set(
            "NewName", "New Description", sample_permission_set_config
        )

        assert arn == "new-arn"
        mock_sso_client.create_permission_set.assert_called_once()

    def test_copy_policies_to_permission_set(
        self, permission_set_cloner, sample_permission_set_config
    ):
        """Test copying policies to a permission set."""
        mock_sso_client = Mock()
        permission_set_cloner.client_manager.get_sso_admin_client.return_value = mock_sso_client

        # Mock STS client for account ID
        mock_sts_client = Mock()
        mock_sts_client.get_caller_identity.return_value = {"Account": "123456789012"}
        permission_set_cloner.client_manager.get_client.return_value = mock_sts_client

        permission_set_cloner._copy_policies_to_permission_set(
            "target-arn", sample_permission_set_config
        )

        # Verify AWS managed policy attachment
        mock_sso_client.attach_managed_policy_to_permission_set.assert_called()

        # Verify inline policy attachment
        mock_sso_client.put_inline_policy_to_permission_set.assert_called_once()

    def test_get_account_id_success(self, permission_set_cloner):
        """Test getting AWS account ID successfully."""
        mock_sts_client = Mock()
        mock_sts_client.get_caller_identity.return_value = {"Account": "123456789012"}
        permission_set_cloner.client_manager.get_client.return_value = mock_sts_client

        account_id = permission_set_cloner._get_account_id()

        assert account_id == "123456789012"

    def test_get_account_id_fallback(self, permission_set_cloner):
        """Test getting AWS account ID with fallback."""
        mock_sts_client = Mock()
        mock_sts_client.get_caller_identity.side_effect = Exception("STS error")
        permission_set_cloner.client_manager.get_client.return_value = mock_sts_client

        account_id = permission_set_cloner._get_account_id()

        assert account_id == "123456789012"  # Default fallback

    def test_is_valid_permission_set_name(self, permission_set_cloner):
        """Test permission set name validation."""
        # Valid names
        assert permission_set_cloner._is_valid_permission_set_name("ValidName") is True
        assert permission_set_cloner._is_valid_permission_set_name("valid-name") is True
        assert permission_set_cloner._is_valid_permission_set_name("valid_name") is True
        assert permission_set_cloner._is_valid_permission_set_name("Valid123") is True

        # Invalid names
        assert permission_set_cloner._is_valid_permission_set_name("Invalid@Name") is False
        assert permission_set_cloner._is_valid_permission_set_name("Invalid Name") is False
        assert permission_set_cloner._is_valid_permission_set_name("Invalid.Name") is False

    def test_get_clone_summary_success(self, permission_set_cloner, sample_permission_set_config):
        """Test getting clone summary for successful operation."""
        result = CloneResult(
            source_name="SourceName",
            target_name="TargetName",
            cloned_config=sample_permission_set_config,
            rollback_id="rollback-123",
            success=True,
            error_message=None,
        )

        summary = permission_set_cloner.get_clone_summary(result)

        assert "Successfully cloned" in summary
        assert "AWS managed policies: 1" in summary
        assert "Customer managed policies: 1" in summary
        assert "Inline policy: Yes" in summary
        assert "Session duration: PT2H" in summary

    def test_get_clone_summary_failure(self, permission_set_cloner):
        """Test getting clone summary for failed operation."""
        result = CloneResult(
            source_name="SourceName",
            target_name="TargetName",
            cloned_config=None,
            rollback_id=None,
            success=False,
            error_message="Clone failed",
        )

        summary = permission_set_cloner.get_clone_summary(result)

        assert "Clone operation failed" in summary
        assert "Clone failed" in summary

    def test_get_clone_summary_preview(self, permission_set_cloner, sample_permission_set_config):
        """Test getting clone summary for preview mode."""
        result = CloneResult(
            source_name="SourceName",
            target_name="TargetName",
            cloned_config=sample_permission_set_config,
            rollback_id=None,
            success=True,
            error_message=None,
        )

        # Set preview mode by setting cloned_config to None (simulating preview)
        result.cloned_config = None

        summary = permission_set_cloner.get_clone_summary(result)

        assert "Preview" in summary
        assert "Would clone" in summary
