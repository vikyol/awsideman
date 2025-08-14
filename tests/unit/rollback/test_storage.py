"""Tests for rollback storage functionality."""

import shutil
import tempfile
from datetime import datetime, timedelta, timezone

from src.awsideman.rollback.models import (
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
)
from src.awsideman.rollback.storage import OperationStore


class TestOperationStore:
    """Tests for OperationStore."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = OperationStore(self.temp_dir)

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    def test_store_initialization(self):
        """Test that store initializes correctly."""
        assert self.store.storage_dir.exists()
        assert self.store.operations_file.exists()
        assert self.store.rollbacks_file.exists()

    def test_store_and_retrieve_operation(self):
        """Test storing and retrieving an operation."""
        results = [OperationResult(account_id="123456789012", success=True)]

        operation = OperationRecord.create(
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )

        # Store the operation
        self.store.store_operation(operation)

        # Retrieve the operation
        retrieved = self.store.get_operation(operation.operation_id)

        assert retrieved is not None
        assert retrieved.operation_id == operation.operation_id
        assert retrieved.operation_type == operation.operation_type
        assert retrieved.principal_name == operation.principal_name

    def test_get_operations_with_filters(self):
        """Test retrieving operations with filters."""
        # Create test operations
        results = [OperationResult(account_id="123456789012", success=True)]

        op1 = OperationRecord.create(
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )

        op2 = OperationRecord.create(
            operation_type=OperationType.REVOKE,
            principal_id="group-456",
            principal_type=PrincipalType.GROUP,
            principal_name="developers",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-456",
            permission_set_name="DeveloperAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )

        # Store operations
        self.store.store_operation(op1)
        self.store.store_operation(op2)

        # Test filtering by operation type
        assign_ops = self.store.get_operations(operation_type="assign")
        assert len(assign_ops) == 1
        assert assign_ops[0].operation_type == OperationType.ASSIGN

        revoke_ops = self.store.get_operations(operation_type="revoke")
        assert len(revoke_ops) == 1
        assert revoke_ops[0].operation_type == OperationType.REVOKE

        # Test filtering by principal
        user_ops = self.store.get_operations(principal="john")
        assert len(user_ops) == 1
        assert user_ops[0].principal_name == "john.doe"

        # Test filtering by permission set
        readonly_ops = self.store.get_operations(permission_set="ReadOnly")
        assert len(readonly_ops) == 1
        assert readonly_ops[0].permission_set_name == "ReadOnlyAccess"

    def test_mark_operation_rolled_back(self):
        """Test marking an operation as rolled back."""
        results = [OperationResult(account_id="123456789012", success=True)]

        operation = OperationRecord.create(
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )

        # Store the operation
        self.store.store_operation(operation)

        # Mark as rolled back
        rollback_id = "rollback-123"
        success = self.store.mark_operation_rolled_back(operation.operation_id, rollback_id)
        assert success is True

        # Verify it's marked as rolled back
        retrieved = self.store.get_operation(operation.operation_id)
        assert retrieved.rolled_back is True
        assert retrieved.rollback_operation_id == rollback_id

    def test_cleanup_old_operations(self):
        """Test cleaning up old operations."""
        results = [OperationResult(account_id="123456789012", success=True)]

        # Create an old operation (manually set timestamp)
        old_operation = OperationRecord.create(
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )
        # Set timestamp to 100 days ago
        old_operation.timestamp = datetime.now(timezone.utc) - timedelta(days=100)

        # Create a recent operation
        recent_operation = OperationRecord.create(
            operation_type=OperationType.REVOKE,
            principal_id="user-456",
            principal_type=PrincipalType.USER,
            principal_name="jane.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-456",
            permission_set_name="DeveloperAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )

        # Store both operations
        self.store.store_operation(old_operation)
        self.store.store_operation(recent_operation)

        # Verify both are stored
        all_ops = self.store.get_operations()
        assert len(all_ops) == 2

        # Clean up operations older than 30 days
        removed_count = self.store.cleanup_old_operations(days=30)
        assert removed_count == 1

        # Verify only recent operation remains
        remaining_ops = self.store.get_operations()
        assert len(remaining_ops) == 1
        assert remaining_ops[0].operation_id == recent_operation.operation_id

    def test_get_storage_stats(self):
        """Test getting storage statistics."""
        stats = self.store.get_storage_stats()

        assert "total_operations" in stats
        assert "total_rollbacks" in stats
        assert "operations_file_size" in stats
        assert "rollbacks_file_size" in stats
        assert stats["total_operations"] == 0
        assert stats["total_rollbacks"] == 0
