"""Tests for operation logger functionality."""

import shutil
import tempfile

from src.awsideman.rollback.logger import OperationLogger


class TestOperationLogger:
    """Tests for OperationLogger."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.logger = OperationLogger(self.temp_dir)

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    def test_log_operation(self):
        """Test logging an operation."""
        results = [
            {"account_id": "123456789012", "success": True, "duration_ms": 1500},
            {"account_id": "123456789013", "success": False, "error": "Permission denied"},
        ]

        operation_id = self.logger.log_operation(
            operation_type="assign",
            principal_id="user-123",
            principal_type="USER",
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012", "123456789013"],
            account_names=["Production", "Staging"],
            results=results,
            metadata={"source": "bulk_assign", "batch_size": 10},
        )

        assert operation_id is not None

        # Retrieve and verify the operation
        operation = self.logger.get_operation(operation_id)
        assert operation is not None
        assert operation.operation_type.value == "assign"
        assert operation.principal_name == "john.doe"
        assert operation.permission_set_name == "ReadOnlyAccess"
        assert len(operation.results) == 2
        assert operation.results[0].success is True
        assert operation.results[1].success is False
        assert operation.metadata["source"] == "bulk_assign"

    def test_get_operations_with_filters(self):
        """Test retrieving operations with various filters."""
        # Log multiple operations
        results1 = [{"account_id": "123456789012", "success": True}]
        results2 = [{"account_id": "123456789013", "success": True}]

        op1_id = self.logger.log_operation(
            operation_type="assign",
            principal_id="user-123",
            principal_type="USER",
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results1,
        )

        _op2_id = self.logger.log_operation(
            operation_type="revoke",
            principal_id="group-456",
            principal_type="GROUP",
            principal_name="developers",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-456",
            permission_set_name="DeveloperAccess",
            account_ids=["123456789013"],
            account_names=["Staging"],
            results=results2,
        )

        # Test filtering by operation type
        assign_ops = self.logger.get_operations(operation_type="assign")
        assert len(assign_ops) == 1
        assert assign_ops[0].operation_id == op1_id

        # Test filtering by principal
        user_ops = self.logger.get_operations(principal="john")
        assert len(user_ops) == 1
        assert user_ops[0].principal_name == "john.doe"

        # Test filtering by permission set
        readonly_ops = self.logger.get_operations(permission_set="ReadOnly")
        assert len(readonly_ops) == 1
        assert readonly_ops[0].permission_set_name == "ReadOnlyAccess"

        # Test limit
        limited_ops = self.logger.get_operations(limit=1)
        assert len(limited_ops) == 1

    def test_mark_rolled_back(self):
        """Test marking an operation as rolled back."""
        results = [{"account_id": "123456789012", "success": True}]

        operation_id = self.logger.log_operation(
            operation_type="assign",
            principal_id="user-123",
            principal_type="USER",
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )

        # Mark as rolled back
        rollback_id = "rollback-123"
        success = self.logger.mark_rolled_back(operation_id, rollback_id)
        assert success is True

        # Verify it's marked as rolled back
        operation = self.logger.get_operation(operation_id)
        assert operation.rolled_back is True
        assert operation.rollback_operation_id == rollback_id

    def test_cleanup_old_operations(self):
        """Test cleaning up old operations."""
        results = [{"account_id": "123456789012", "success": True}]

        # Log an operation
        self.logger.log_operation(
            operation_type="assign",
            principal_id="user-123",
            principal_type="USER",
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012"],
            account_names=["Production"],
            results=results,
        )

        # Verify operation exists
        ops_before = self.logger.get_operations()
        assert len(ops_before) == 1

        # Clean up operations older than 30 days (should not remove recent operation)
        removed_count = self.logger.cleanup_old_operations(days=30)
        assert removed_count == 0

        # Verify operation still exists
        ops_after = self.logger.get_operations()
        assert len(ops_after) == 1

    def test_get_storage_stats(self):
        """Test getting storage statistics."""
        stats = self.logger.get_storage_stats()

        assert "total_operations" in stats
        assert "total_rollbacks" in stats
        assert stats["total_operations"] == 0
