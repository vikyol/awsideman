"""Rollback operations test fixtures and data for awsideman tests."""

from datetime import datetime, timezone

import pytest

from src.awsideman.rollback.models import (
    AssignmentState,
    OperationRecord,
    OperationResult,
    OperationType,
    PrincipalType,
    RollbackAction,
    RollbackActionType,
    RollbackPlan,
    RollbackValidation,
)


@pytest.fixture
def sample_operation_record():
    """Sample operation record for testing."""
    return OperationRecord(
        operation_id="test-op-123",
        timestamp=datetime.now(timezone.utc),
        operation_type=OperationType.ASSIGN,
        principal_id="user-123",
        principal_type=PrincipalType.USER,
        principal_name="test.user",
        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
        permission_set_name="TestPermissionSet",
        account_ids=["123456789012"],
        account_names=["TestAccount"],
        results=[OperationResult(account_id="123456789012", success=True, duration_ms=500)],
        rolled_back=False,
        rollback_operation_id=None,
    )


@pytest.fixture
def sample_rollback_plan():
    """Sample rollback plan for testing."""
    return RollbackPlan(
        operation_id="test-op-123",
        rollback_type=RollbackActionType.REVOKE,
        actions=[
            RollbackAction(
                principal_id="user-123",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                account_id="123456789012",
                action_type=RollbackActionType.REVOKE,
                current_state=AssignmentState.ASSIGNED,
                principal_type=PrincipalType.USER,
            )
        ],
        estimated_duration=5,
        warnings=[],
    )


@pytest.fixture
def sample_rollback_validation():
    """Sample rollback validation result for testing."""
    return RollbackValidation(valid=True, errors=[], warnings=[])


@pytest.fixture
def sample_rollback_actions():
    """Sample rollback actions for testing."""
    return [
        RollbackAction(
            principal_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            account_id="123456789012",
            action_type=RollbackActionType.REVOKE,
            current_state=AssignmentState.ASSIGNED,
            principal_type=PrincipalType.USER,
        ),
        RollbackAction(
            principal_id="user-456",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-789",
            account_id="098765432109",
            action_type=RollbackActionType.REVOKE,
            current_state=AssignmentState.ASSIGNED,
            principal_type=PrincipalType.USER,
        ),
    ]


@pytest.fixture
def sample_operation_results():
    """Sample operation results for testing."""
    return [
        OperationResult(account_id="123456789012", success=True, duration_ms=500),
        OperationResult(
            account_id="098765432109", success=False, error="Access denied", duration_ms=200
        ),
    ]


@pytest.fixture
def sample_rollback_operation_data():
    """Sample rollback operation data for testing."""
    return {
        "rollback_operation_id": "rollback-123",
        "original_operation_id": "test-op-123",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rollback_type": "revoke",
        "completed_actions": 1,
        "failed_actions": 0,
        "total_actions": 1,
        "principal_id": "user-123",
        "principal_type": "USER",
        "principal_name": "test.user",
        "permission_set_arn": "arn:aws:sso:::permissionSet/ssoins-123/ps-456",
        "permission_set_name": "TestPermissionSet",
        "account_ids": ["123456789012"],
    }


@pytest.fixture
def rollback_operation_factory():
    """Factory for creating rollback operation test data."""

    class RollbackOperationFactory:
        @staticmethod
        def create_operation_record(
            operation_id="test-op-123",
            operation_type=OperationType.ASSIGN,
            principal_id="user-123",
            principal_type=PrincipalType.USER,
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            account_ids=None,
            results=None,
            rolled_back=False,
        ):
            """Create an operation record for testing."""
            if account_ids is None:
                account_ids = ["123456789012"]

            if results is None:
                results = [
                    OperationResult(account_id=account_ids[0], success=True, duration_ms=500)
                ]

            return OperationRecord(
                operation_id=operation_id,
                timestamp=datetime.now(timezone.utc),
                operation_type=operation_type,
                principal_id=principal_id,
                principal_type=principal_type,
                principal_name="test.user",
                permission_set_arn=permission_set_arn,
                permission_set_name="TestPermissionSet",
                account_ids=account_ids,
                account_names=[f"Account-{aid}" for aid in account_ids],
                results=results,
                rolled_back=rolled_back,
                rollback_operation_id=None,
            )

        @staticmethod
        def create_rollback_plan(
            operation_id="test-op-123",
            rollback_type=RollbackActionType.REVOKE,
            actions=None,
            estimated_duration=5,
        ):
            """Create a rollback plan for testing."""
            if actions is None:
                actions = [
                    RollbackAction(
                        principal_id="user-123",
                        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
                        account_id="123456789012",
                        action_type=RollbackActionType.REVOKE,
                        current_state=AssignmentState.ASSIGNED,
                        principal_type=PrincipalType.USER,
                    )
                ]

            return RollbackPlan(
                operation_id=operation_id,
                rollback_type=rollback_type,
                actions=actions,
                estimated_duration=estimated_duration,
                warnings=[],
            )

        @staticmethod
        def create_rollback_action(
            principal_id="user-123",
            permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-456",
            account_id="123456789012",
            action_type=RollbackActionType.REVOKE,
            current_state=AssignmentState.ASSIGNED,
            principal_type=PrincipalType.USER,
        ):
            """Create a rollback action for testing."""
            return RollbackAction(
                principal_id=principal_id,
                permission_set_arn=permission_set_arn,
                account_id=account_id,
                action_type=action_type,
                current_state=current_state,
                principal_type=principal_type,
            )

        @staticmethod
        def create_operation_result(
            account_id="123456789012", success=True, error=None, duration_ms=500
        ):
            """Create an operation result for testing."""
            return OperationResult(
                account_id=account_id, success=success, error=error, duration_ms=duration_ms
            )

    return RollbackOperationFactory()
