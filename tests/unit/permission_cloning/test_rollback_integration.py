"""
Unit tests for the PermissionCloningRollbackIntegration class.

Tests rollback functionality for permission cloning operations.
"""

from unittest.mock import Mock

import pytest

from src.awsideman.aws_clients.manager import AWSClientManager
from src.awsideman.permission_cloning.models import (
    CloneResult,
    CopyResult,
    CustomerManagedPolicy,
    EntityReference,
    EntityType,
    PermissionAssignment,
    PermissionSetConfig,
)
from src.awsideman.permission_cloning.rollback_integration import (
    PermissionCloningRollbackIntegration,
)
from src.awsideman.rollback.models import (
    OperationType,
    PermissionCloningOperationRecord,
    PermissionSetCloningOperationRecord,
    PrincipalType,
)


class TestPermissionCloningRollbackIntegration:
    """Test cases for PermissionCloningRollbackIntegration class."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        return Mock(spec=AWSClientManager)

    @pytest.fixture
    def mock_rollback_processor(self):
        """Create a mock rollback processor."""
        return Mock()

    @pytest.fixture
    def mock_rollback_store(self):
        """Create a mock rollback store."""
        return Mock()

    @pytest.fixture
    def mock_sso_admin_client(self):
        """Create a mock SSO Admin client."""
        return Mock()

    @pytest.fixture
    def sample_assignments(self):
        """Create sample permission assignments."""
        return [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/test/ps-123",
                permission_set_name="TestPermissionSet",
                account_id="123456789012",
                account_name="Test Account",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/test/ps-456",
                permission_set_name="AnotherPermissionSet",
                account_id="123456789012",
                account_name="Test Account",
            ),
        ]

    @pytest.fixture
    def sample_permission_set_config(self):
        """Create a sample permission set configuration."""
        return PermissionSetConfig(
            name="TargetPermissionSet",
            description="Target Description",
            session_duration="PT2H",
            relay_state_url="https://example.com",
            aws_managed_policies=["arn:aws:iam::aws:policy/AdministratorAccess"],
            customer_managed_policies=[CustomerManagedPolicy(name="CustomPolicy", path="/")],
            inline_policy='{"Version": "2012-10-17", "Statement": []}',
        )

    @pytest.fixture
    def rollback_integration(self, mock_client_manager, mock_rollback_processor):
        """Create a PermissionCloningRollbackIntegration instance."""
        mock_rollback_processor.store = Mock()
        return PermissionCloningRollbackIntegration(mock_client_manager, mock_rollback_processor)

    def test_init(self, rollback_integration, mock_client_manager, mock_rollback_processor):
        """Test PermissionCloningRollbackIntegration initialization."""
        assert rollback_integration.client_manager == mock_client_manager
        assert rollback_integration.rollback_processor == mock_rollback_processor

    def test_track_assignment_copy_operation_success(
        self, rollback_integration, sample_assignments
    ):
        """Test successful tracking of assignment copy operation."""
        source_entity = EntityReference(EntityType.USER, "user-123", "Source User")
        target_entity = EntityReference(EntityType.USER, "user-456", "Target User")

        copy_result = CopyResult(
            source=source_entity,
            target=target_entity,
            assignments_copied=sample_assignments,
            assignments_skipped=[],
            success=True,
        )

        # Mock the store operation
        rollback_integration.rollback_processor.store.store_operation = Mock()

        operation_id = rollback_integration.track_assignment_copy_operation(
            source_entity, target_entity, sample_assignments, copy_result
        )

        assert operation_id is not None
        rollback_integration.rollback_processor.store.store_operation.assert_called_once()

        # Verify the stored operation record
        stored_operation = rollback_integration.rollback_processor.store.store_operation.call_args[
            0
        ][0]
        assert stored_operation.operation_type == OperationType.COPY_ASSIGNMENTS
        assert stored_operation.source_entity_id == "user-123"
        assert stored_operation.target_entity_id == "user-456"
        assert len(stored_operation.assignments_copied) == 2
        assert len(stored_operation.accounts_affected) == 1
        assert len(stored_operation.permission_sets_involved) == 2

    def test_track_permission_set_clone_operation_success(
        self, rollback_integration, sample_permission_set_config
    ):
        """Test successful tracking of permission set clone operation."""
        clone_result = CloneResult(
            source_name="SourcePermissionSet",
            target_name="TargetPermissionSet",
            cloned_config=sample_permission_set_config,
            rollback_id=None,
            success=True,
            error_message=None,
        )

        # Mock the store operation
        rollback_integration.rollback_processor.store.store_operation = Mock()

        operation_id = rollback_integration.track_permission_set_clone_operation(
            "SourcePermissionSet",
            "arn:aws:sso:::permissionSet/test/ps-source",
            "TargetPermissionSet",
            "arn:aws:sso:::permissionSet/test/ps-target",
            clone_result,
        )

        assert operation_id is not None
        rollback_integration.rollback_processor.store.store_operation.assert_called_once()

        # Verify the stored operation record
        stored_operation = rollback_integration.rollback_processor.store.store_operation.call_args[
            0
        ][0]
        assert stored_operation.source_permission_set_name == "SourcePermissionSet"
        assert stored_operation.target_permission_set_name == "TargetPermissionSet"
        assert "aws_managed" in stored_operation.policies_copied
        assert "customer_managed" in stored_operation.policies_copied
        assert "inline" in stored_operation.policies_copied

    def test_rollback_assignment_copy_operation_success(self, rollback_integration):
        """Test successful rollback of assignment copy operation."""
        # Create a mock operation record
        mock_operation_record = Mock(spec=PermissionCloningOperationRecord)
        mock_operation_record.rolled_back = False
        mock_operation_record.assignments_copied = [
            "arn:aws:sso:::permissionSet/test/ps-123:123456789012:user-456",
            "arn:aws:sso:::permissionSet/test/ps-456:123456789012:user-456",
        ]
        mock_operation_record.target_entity_type = PrincipalType.USER

        # Mock the store operations
        rollback_integration.rollback_processor.store.get_operation.return_value = (
            mock_operation_record
        )
        rollback_integration.rollback_processor.store.store_operation = Mock()

        # Mock the SSO admin client
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }

        result = rollback_integration.rollback_assignment_copy_operation("test-operation-id")

        assert result["success"] is True
        assert result["success_count"] == 2
        assert result["failure_count"] == 0
        assert result["total_actions"] == 2

        # Verify that delete_account_assignment was called for each assignment
        assert mock_sso_client.delete_account_assignment.call_count == 2

        # Verify the operation was marked as rolled back
        mock_operation_record.rolled_back = True
        rollback_integration.rollback_processor.store.store_operation.assert_called()

    def test_rollback_assignment_copy_operation_already_rolled_back(self, rollback_integration):
        """Test rollback of already rolled back operation."""
        # Create a mock operation record that's already rolled back
        mock_operation_record = Mock(spec=PermissionCloningOperationRecord)
        mock_operation_record.rolled_back = True

        rollback_integration.rollback_processor.store.get_operation.return_value = (
            mock_operation_record
        )

        with pytest.raises(ValueError, match="already been rolled back"):
            rollback_integration.rollback_assignment_copy_operation("test-operation-id")

    def test_rollback_assignment_copy_operation_not_found(self, rollback_integration):
        """Test rollback of non-existent operation."""
        rollback_integration.rollback_processor.store.get_operation.return_value = None

        with pytest.raises(ValueError, match="not found"):
            rollback_integration.rollback_assignment_copy_operation("non-existent-id")

    def test_rollback_permission_set_clone_operation_success(self, rollback_integration):
        """Test successful rollback of permission set clone operation."""
        # Create a mock operation record
        mock_operation_record = Mock(spec=PermissionSetCloningOperationRecord)
        mock_operation_record.rolled_back = False
        mock_operation_record.target_permission_set_name = "TargetPermissionSet"
        mock_operation_record.target_permission_set_arn = (
            "arn:aws:sso:::permissionSet/test/ps-target"
        )

        # Mock the store operations
        rollback_integration.rollback_processor.store.get_operation.return_value = (
            mock_operation_record
        )
        rollback_integration.rollback_processor.store.store_operation = Mock()

        # Mock the SSO admin client
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }
        mock_sso_client.list_managed_policies_in_permission_set.return_value = {
            "AttachedManagedPolicies": []
        }

        result = rollback_integration.rollback_permission_set_clone_operation("test-operation-id")

        assert result["success"] is True
        assert result["permission_set_deleted"] == "TargetPermissionSet"

        # Verify that delete_permission_set was called
        mock_sso_client.delete_permission_set.assert_called_once()

        # Verify the operation was marked as rolled back
        mock_operation_record.rolled_back = True
        rollback_integration.rollback_processor.store.store_operation.assert_called()

    def test_rollback_permission_set_clone_operation_with_policies(self, rollback_integration):
        """Test rollback of permission set clone operation with attached policies."""
        # Create a mock operation record
        mock_operation_record = Mock(spec=PermissionSetCloningOperationRecord)
        mock_operation_record.rolled_back = False
        mock_operation_record.target_permission_set_name = "TargetPermissionSet"
        mock_operation_record.target_permission_set_arn = (
            "arn:aws:sso:::permissionSet/test/ps-target"
        )

        # Mock the store operations
        rollback_integration.rollback_processor.store.get_operation.return_value = (
            mock_operation_record
        )
        rollback_integration.rollback_processor.store.store_operation = Mock()

        # Mock the SSO admin client
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }
        mock_sso_client.list_managed_policies_in_permission_set.return_value = {
            "AttachedManagedPolicies": [{"Arn": "arn:aws:iam::aws:policy/AdministratorAccess"}]
        }

        result = rollback_integration.rollback_permission_set_clone_operation("test-operation-id")

        assert result["success"] is True

        # Verify that policies were detached before deletion
        mock_sso_client.detach_managed_policy_from_permission_set.assert_called_once()
        mock_sso_client.delete_permission_set.assert_called_once()

    def test_get_rollbackable_operations(self, rollback_integration):
        """Test getting list of rollbackable operations."""
        # Create mock operations
        mock_operation1 = Mock()
        mock_operation1.rolled_back = False
        mock_operation1.source_entity_id = "user-123"
        mock_operation1.to_dict.return_value = {"id": "op1", "source_entity_id": "user-123"}

        mock_operation2 = Mock()
        mock_operation2.rolled_back = False
        mock_operation2.target_entity_id = "user-456"
        mock_operation2.to_dict.return_value = {"id": "op2", "target_entity_id": "user-456"}

        mock_operation3 = Mock()
        mock_operation3.rolled_back = True  # Already rolled back
        mock_operation3.to_dict.return_value = {"id": "op3"}

        # Mock the store operations
        rollback_integration.rollback_processor.store.get_operations.return_value = [
            mock_operation1,
            mock_operation2,
            mock_operation3,
        ]

        # Test getting all rollbackable operations
        operations = rollback_integration.get_rollbackable_operations()
        assert len(operations) == 2

        # Test filtering by entity ID
        operations = rollback_integration.get_rollbackable_operations(entity_id="user-123")
        assert len(operations) == 1
        assert operations[0]["id"] == "op1"

        # Test filtering by operation type
        operations = rollback_integration.get_rollbackable_operations(
            operation_type=OperationType.COPY_ASSIGNMENTS
        )
        assert len(operations) == 2  # Both non-rolled-back operations

    def test_get_instance_arn_success(self, rollback_integration):
        """Test successful retrieval of SSO instance ARN."""
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }

        instance_arn = rollback_integration._get_instance_arn()
        assert instance_arn == "arn:aws:sso:::instance/test"

    def test_get_instance_arn_no_instances(self, rollback_integration):
        """Test getting instance ARN when no instances exist."""
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {"InstanceList": []}

        with pytest.raises(ValueError, match="No SSO instances found"):
            rollback_integration._get_instance_arn()

    def test_revoke_assignment_user(self, rollback_integration):
        """Test revoking assignment from a user."""
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }

        rollback_integration._revoke_assignment(
            "user-123",
            "arn:aws:sso:::permissionSet/test/ps-123",
            "123456789012",
            PrincipalType.USER,
        )

        mock_sso_client.delete_account_assignment.assert_called_once()
        call_args = mock_sso_client.delete_account_assignment.call_args
        assert call_args[1]["PrincipalType"] == "USER"
        assert call_args[1]["PrincipalId"] == "user-123"

    def test_revoke_assignment_group(self, rollback_integration):
        """Test revoking assignment from a group."""
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }

        rollback_integration._revoke_assignment(
            "group-123",
            "arn:aws:sso:::permissionSet/test/ps-123",
            "123456789012",
            PrincipalType.GROUP,
        )

        mock_sso_client.delete_account_assignment.assert_called_once()
        call_args = mock_sso_client.delete_account_assignment.call_args
        assert call_args[1]["PrincipalType"] == "GROUP"
        assert call_args[1]["PrincipalId"] == "group-123"

    def test_delete_permission_set_success(self, rollback_integration):
        """Test successful deletion of permission set."""
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }
        mock_sso_client.list_managed_policies_in_permission_set.return_value = {
            "AttachedManagedPolicies": []
        }

        rollback_integration._delete_permission_set("arn:aws:sso:::permissionSet/test/ps-123")

        mock_sso_client.delete_permission_set.assert_called_once()

    def test_delete_permission_set_with_policies(self, rollback_integration):
        """Test deletion of permission set with attached policies."""
        mock_sso_client = Mock()
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        rollback_integration.client_manager.get_sso_admin_client.return_value = mock_sso_client
        mock_sso_client.list_instances.return_value = {
            "InstanceList": [{"InstanceArn": "arn:aws:sso:::instance/test"}]
        }
        mock_sso_client.list_managed_policies_in_permission_set.return_value = {
            "AttachedManagedPolicies": [{"Arn": "arn:aws:iam::aws:policy/AdministratorAccess"}]
        }

        rollback_integration._delete_permission_set("arn:aws:sso:::permissionSet/test/ps-123")

        # Verify policies were detached before deletion
        mock_sso_client.detach_managed_policy_from_permission_set.assert_called_once()
        mock_sso_client.delete_permission_set.assert_called_once()
