"""Data models for rollback operations."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class OperationType(str, Enum):
    """Types of operations that can be tracked."""

    ASSIGN = "assign"
    REVOKE = "revoke"


class PrincipalType(str, Enum):
    """Types of principals that can have assignments."""

    USER = "USER"
    GROUP = "GROUP"


class RollbackActionType(str, Enum):
    """Types of rollback actions."""

    ASSIGN = "assign"
    REVOKE = "revoke"


class AssignmentState(str, Enum):
    """Current state of an assignment."""

    ASSIGNED = "assigned"
    NOT_ASSIGNED = "not_assigned"
    UNKNOWN = "unknown"


@dataclass
class OperationResult:
    """Result of a single operation on an account."""

    account_id: str
    success: bool
    error: Optional[str] = None
    duration_ms: Optional[int] = None


@dataclass
class OperationRecord:
    """Record of a permission set operation."""

    operation_id: str
    timestamp: datetime
    operation_type: OperationType
    principal_id: str
    principal_type: PrincipalType
    principal_name: str
    permission_set_arn: str
    permission_set_name: str
    account_ids: List[str]
    account_names: List[str]
    results: List[OperationResult]
    metadata: Dict[str, Any] = field(default_factory=dict)
    rolled_back: bool = False
    rollback_operation_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        operation_type: OperationType,
        principal_id: str,
        principal_type: PrincipalType,
        principal_name: str,
        permission_set_arn: str,
        permission_set_name: str,
        account_ids: List[str],
        account_names: List[str],
        results: List[OperationResult],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "OperationRecord":
        """Create a new operation record with generated ID and timestamp."""
        return cls(
            operation_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            operation_type=operation_type,
            principal_id=principal_id,
            principal_type=principal_type,
            principal_name=principal_name,
            permission_set_arn=permission_set_arn,
            permission_set_name=permission_set_name,
            account_ids=account_ids,
            account_names=account_names,
            results=results,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "operation_id": self.operation_id,
            "timestamp": self.timestamp.isoformat(),
            "operation_type": self.operation_type.value,
            "principal_id": self.principal_id,
            "principal_type": self.principal_type.value,
            "principal_name": self.principal_name,
            "permission_set_arn": self.permission_set_arn,
            "permission_set_name": self.permission_set_name,
            "account_ids": self.account_ids,
            "account_names": self.account_names,
            "results": [
                {
                    "account_id": r.account_id,
                    "success": r.success,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                }
                for r in self.results
            ],
            "metadata": self.metadata,
            "rolled_back": self.rolled_back,
            "rollback_operation_id": self.rollback_operation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OperationRecord":
        """Create from dictionary loaded from JSON."""
        return cls(
            operation_id=data["operation_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            operation_type=OperationType(data["operation_type"]),
            principal_id=data["principal_id"],
            principal_type=PrincipalType(data["principal_type"]),
            principal_name=data["principal_name"],
            permission_set_arn=data["permission_set_arn"],
            permission_set_name=data["permission_set_name"],
            account_ids=data["account_ids"],
            account_names=data["account_names"],
            results=[
                OperationResult(
                    account_id=r["account_id"],
                    success=r["success"],
                    error=r.get("error"),
                    duration_ms=r.get("duration_ms"),
                )
                for r in data["results"]
            ],
            metadata=data.get("metadata", {}),
            rolled_back=data.get("rolled_back", False),
            rollback_operation_id=data.get("rollback_operation_id"),
        )


@dataclass
class RollbackAction:
    """A single action to be performed during rollback."""

    principal_id: str
    permission_set_arn: str
    account_id: str
    action_type: RollbackActionType
    current_state: AssignmentState
    principal_type: PrincipalType


@dataclass
class RollbackPlan:
    """Plan for rolling back an operation."""

    operation_id: str
    rollback_type: RollbackActionType
    actions: List[RollbackAction]
    estimated_duration: int
    warnings: List[str] = field(default_factory=list)


@dataclass
class RollbackValidation:
    """Result of rollback validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class RollbackResult:
    """Result of a rollback operation."""

    rollback_operation_id: str
    success: bool
    completed_actions: int
    failed_actions: int
    errors: List[str] = field(default_factory=list)
    duration_ms: Optional[int] = None


@dataclass
class RollbackVerification:
    """Result of rollback verification."""

    verified: bool
    mismatches: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
