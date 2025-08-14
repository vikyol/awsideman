"""Tests for rollback data models."""

from datetime import datetime

from src.awsideman.rollback.models import (
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
)


class TestOperationResult:
    """Tests for OperationResult model."""

    def test_create_operation_result(self):
        """Test creating an operation result."""
        result = OperationResult(
            account_id="123456789012",
            success=True,
            error=None,
            duration_ms=1500,
        )

        assert result.account_id == "123456789012"
        assert result.success is True
        assert result.error is None
        assert result.duration_ms == 1500

    def test_create_failed_operation_result(self):
        """Test creating a failed operation result."""
        result = OperationResult(
            account_id="123456789012",
            success=False,
            error="Permission denied",
        )

        assert result.account_id == "123456789012"
        assert result.success is False
        assert result.error == "Permission denied"
        assert result.duration_ms is None


class TestOperationRecord:
    """Tests for OperationRecord model."""

    def test_create_operation_record(self):
        """Test creating an operation record."""
        results = [
            OperationResult(account_id="123456789012", success=True),
            OperationResult(account_id="123456789013", success=False, error="Failed"),
        ]

        operation = OperationRecord.create(
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            principal_name="john.doe",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-123",
            permission_set_name="ReadOnlyAccess",
            account_ids=["123456789012", "123456789013"],
            account_names=["Production", "Staging"],
            results=results,
            metadata={"source": "bulk_assign"},
        )

        assert operation.operation_id is not None
        assert isinstance(operation.timestamp, datetime)
        assert operation.operation_type == OperationType.ASSIGN
        assert operation.principal_id == "user-123"
        assert operation.principal_type == PrincipalType.USER
        assert operation.principal_name == "john.doe"
        assert operation.permission_set_arn == "arn:aws:sso:::permissionSet/ps-123"
        assert operation.permission_set_name == "ReadOnlyAccess"
        assert operation.account_ids == ["123456789012", "123456789013"]
        assert operation.account_names == ["Production", "Staging"]
        assert len(operation.results) == 2
        assert operation.metadata == {"source": "bulk_assign"}
        assert operation.rolled_back is False
        assert operation.rollback_operation_id is None

    def test_operation_record_serialization(self):
        """Test operation record to_dict and from_dict."""
        results = [OperationResult(account_id="123456789012", success=True)]

        original = OperationRecord.create(
            operation_type=OperationType.REVOKE,
            principal_id="group-456",
            principal_type=PrincipalType.GROUP,
            principal_name="developers",
            permission_set_arn="arn:aws:sso:::permissionSet/ps-456",
            permission_set_name="DeveloperAccess",
            account_ids=["123456789012"],
            account_names=["Development"],
            results=results,
        )

        # Convert to dict and back
        data = original.to_dict()
        restored = OperationRecord.from_dict(data)

        assert restored.operation_id == original.operation_id
        assert restored.timestamp == original.timestamp
        assert restored.operation_type == original.operation_type
        assert restored.principal_id == original.principal_id
        assert restored.principal_type == original.principal_type
        assert restored.principal_name == original.principal_name
        assert restored.permission_set_arn == original.permission_set_arn
        assert restored.permission_set_name == original.permission_set_name
        assert restored.account_ids == original.account_ids
        assert restored.account_names == original.account_names
        assert len(restored.results) == len(original.results)
        assert restored.results[0].account_id == original.results[0].account_id
        assert restored.results[0].success == original.results[0].success
        assert restored.metadata == original.metadata
        assert restored.rolled_back == original.rolled_back
        assert restored.rollback_operation_id == original.rollback_operation_id
