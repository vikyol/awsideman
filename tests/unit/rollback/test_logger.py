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
