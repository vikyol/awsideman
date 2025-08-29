"""JSON-based storage for operation records."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .models import OperationRecord


class OperationStore:
    """JSON-based storage for operation records."""

    def __init__(self, storage_directory: Optional[str] = None, profile: Optional[str] = None):
        """Initialize the operation store.

        Args:
            storage_directory: Directory to store operation files.
                             Defaults to ~/.awsideman/operations/
            profile: AWS profile name for isolation.
        """
        if storage_directory:
            self.storage_dir = Path(storage_directory).expanduser()
        else:
            self.storage_dir = Path.home() / ".awsideman" / "operations"

        # Add profile isolation
        if profile:
            self.storage_dir = self.storage_dir / "profiles" / profile

        self.operations_file = self.storage_dir / "operations.json"
        self.rollbacks_file = self.storage_dir / "rollbacks.json"

        # Ensure directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Initialize files if they don't exist
        self._initialize_files()

    def _initialize_files(self) -> None:
        """Initialize storage files if they don't exist."""
        if not self.operations_file.exists():
            self._write_operations_file({"operations": []})

        if not self.rollbacks_file.exists():
            self._write_rollbacks_file({"rollbacks": []})

    def _read_operations_file(self) -> Dict:
        """Read the operations file."""
        try:
            with open(self.operations_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"operations": []}

    def _write_operations_file(self, data: Dict) -> None:
        """Write to the operations file."""
        with open(self.operations_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _read_rollbacks_file(self) -> Dict:
        """Read the rollbacks file."""
        try:
            with open(self.rollbacks_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"rollbacks": []}

    def _write_rollbacks_file(self, data: Dict) -> None:
        """Write to the rollbacks file."""
        with open(self.rollbacks_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def store_operation(self, operation: OperationRecord) -> None:
        """Store an operation record."""
        data = self._read_operations_file()
        data["operations"].append(operation.to_dict())
        self._write_operations_file(data)

    def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        """Get a specific operation by ID."""
        data = self._read_operations_file()
        for op_data in data["operations"]:
            if op_data["operation_id"] == operation_id:
                # Determine the operation type and create the appropriate record
                if "source_entity_id" in op_data and "target_entity_id" in op_data:
                    # This is a permission cloning operation
                    from .models import PermissionCloningOperationRecord

                    return PermissionCloningOperationRecord.from_dict(op_data)
                elif (
                    "source_permission_set_name" in op_data
                    and "target_permission_set_name" in op_data
                ):
                    # This is a permission set cloning operation
                    from .models import PermissionSetCloningOperationRecord

                    return PermissionSetCloningOperationRecord.from_dict(op_data)
                else:
                    # This is a standard operation
                    return OperationRecord.from_dict(op_data)
        return None

    def get_operations(
        self,
        operation_type: Optional[str] = None,
        principal: Optional[str] = None,
        permission_set: Optional[str] = None,
        days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[OperationRecord]:
        """Get operations with optional filtering."""
        data = self._read_operations_file()
        operations = []

        # Calculate date filter if specified
        cutoff_date = None
        if days is not None:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        for op_data in data["operations"]:
            # Determine the operation type and create the appropriate record
            if "source_entity_id" in op_data and "target_entity_id" in op_data:
                # This is a permission cloning operation
                from .models import PermissionCloningOperationRecord

                operation = PermissionCloningOperationRecord.from_dict(op_data)
            elif (
                "source_permission_set_name" in op_data and "target_permission_set_name" in op_data
            ):
                # This is a permission set cloning operation
                from .models import PermissionSetCloningOperationRecord

                operation = PermissionSetCloningOperationRecord.from_dict(op_data)
            else:
                # This is a standard operation
                operation = OperationRecord.from_dict(op_data)

            # Apply filters
            if operation_type and operation.operation_type.value != operation_type:
                continue

            # Handle different operation record types for principal filtering
            if principal:
                principal_match = False
                if hasattr(operation, "principal_name"):
                    principal_match = (
                        principal.lower() in operation.principal_name.lower()
                        or principal in operation.principal_id
                    )
                elif hasattr(operation, "source_entity_name"):
                    # For permission cloning operations, check both source and target
                    principal_match = (
                        principal.lower() in operation.source_entity_name.lower()
                        or principal in operation.source_entity_id
                        or principal.lower() in operation.target_entity_name.lower()
                        or principal in operation.target_entity_id
                    )
                elif hasattr(operation, "source_permission_set_name"):
                    # For permission set cloning operations, check both source and target
                    principal_match = (
                        principal.lower() in operation.source_permission_set_name.lower()
                        or principal.lower() in operation.target_permission_set_name.lower()
                    )

                if not principal_match:
                    continue

            # Handle different operation record types for permission set filtering
            if permission_set:
                permission_set_match = False
                if hasattr(operation, "permission_set_name"):
                    permission_set_match = (
                        permission_set.lower() in operation.permission_set_name.lower()
                        or permission_set in operation.permission_set_arn
                    )
                elif (
                    hasattr(operation, "permission_sets_involved")
                    and operation.permission_sets_involved
                ):
                    # For permission cloning operations, check involved permission sets
                    permission_set_match = any(
                        permission_set.lower() in ps_arn.lower()
                        for ps_arn in operation.permission_sets_involved
                    )
                elif hasattr(operation, "source_permission_set_name"):
                    # For permission set cloning operations, check both source and target
                    permission_set_match = (
                        permission_set.lower() in operation.source_permission_set_name.lower()
                        or permission_set.lower() in operation.target_permission_set_name.lower()
                    )

                if not permission_set_match:
                    continue

            if cutoff_date and operation.timestamp < cutoff_date:
                continue

            operations.append(operation)

        # Sort by timestamp (newest first)
        operations.sort(key=lambda x: x.timestamp, reverse=True)

        # Apply limit
        if limit:
            operations = operations[:limit]

        return operations

    def mark_operation_rolled_back(self, operation_id: str, rollback_operation_id: str) -> bool:
        """Mark an operation as rolled back."""
        data = self._read_operations_file()

        for op_data in data["operations"]:
            if op_data["operation_id"] == operation_id:
                op_data["rolled_back"] = True
                op_data["rollback_operation_id"] = rollback_operation_id
                self._write_operations_file(data)
                return True

        return False

    def store_rollback_record(self, rollback_data: Dict) -> None:
        """Store a rollback operation record."""
        data = self._read_rollbacks_file()
        data["rollbacks"].append(rollback_data)
        self._write_rollbacks_file(data)

    def cleanup_old_operations(self, days: int = 90) -> int:
        """Remove operations older than specified days."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        data = self._read_operations_file()
        original_count = len(data["operations"])

        # Filter out old operations
        data["operations"] = [
            op
            for op in data["operations"]
            if datetime.fromisoformat(op["timestamp"]) >= cutoff_date
        ]

        removed_count = original_count - len(data["operations"])

        if removed_count > 0:
            self._write_operations_file(data)

        return removed_count

    def cleanup_by_count_limit(self, max_operations: int = 10000) -> int:
        """Remove oldest operations to stay within count limit."""
        data = self._read_operations_file()
        original_count = len(data["operations"])

        if original_count <= max_operations:
            return 0

        # Sort by timestamp (newest first) and keep only the newest max_operations
        operations = sorted(
            data["operations"], key=lambda x: datetime.fromisoformat(x["timestamp"]), reverse=True
        )

        data["operations"] = operations[:max_operations]
        removed_count = original_count - len(data["operations"])

        if removed_count > 0:
            self._write_operations_file(data)

        return removed_count

    def cleanup_rollback_records(self, days: int = 90) -> int:
        """Remove rollback records older than specified days."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        data = self._read_rollbacks_file()
        original_count = len(data["rollbacks"])

        # Filter out old rollback records
        data["rollbacks"] = [
            rb for rb in data["rollbacks"] if datetime.fromisoformat(rb["timestamp"]) >= cutoff_date
        ]

        removed_count = original_count - len(data["rollbacks"])

        if removed_count > 0:
            self._write_rollbacks_file(data)

        return removed_count

    def get_file_sizes(self) -> Dict[str, int]:
        """Get file sizes in bytes."""
        return {
            "operations_file": (
                self.operations_file.stat().st_size if self.operations_file.exists() else 0
            ),
            "rollbacks_file": (
                self.rollbacks_file.stat().st_size if self.rollbacks_file.exists() else 0
            ),
        }

    def rotate_files_if_needed(self, max_size_mb: int = 50) -> Dict[str, bool]:
        """Rotate files if they exceed size limit."""
        max_size_bytes = max_size_mb * 1024 * 1024
        rotated = {"operations": False, "rollbacks": False}

        # Check operations file
        if self.operations_file.exists() and self.operations_file.stat().st_size > max_size_bytes:
            self._rotate_operations_file()
            rotated["operations"] = True

        # Check rollbacks file
        if self.rollbacks_file.exists() and self.rollbacks_file.stat().st_size > max_size_bytes:
            self._rotate_rollbacks_file()
            rotated["rollbacks"] = True

        return rotated

    def _rotate_operations_file(self) -> None:
        """Rotate the operations file by creating a backup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.storage_dir / f"operations_{timestamp}.json"

        # Move current file to backup
        if self.operations_file.exists():
            self.operations_file.rename(backup_file)

        # Create new empty file
        self._write_operations_file({"operations": []})

    def _rotate_rollbacks_file(self) -> None:
        """Rotate the rollbacks file by creating a backup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.storage_dir / f"rollbacks_{timestamp}.json"

        # Move current file to backup
        if self.rollbacks_file.exists():
            self.rollbacks_file.rename(backup_file)

        # Create new empty file
        self._write_rollbacks_file({"rollbacks": []})

    def get_storage_stats(self) -> Dict[str, int]:
        """Get storage statistics."""
        operations_data = self._read_operations_file()
        rollbacks_data = self._read_rollbacks_file()

        return {
            "total_operations": len(operations_data["operations"]),
            "total_rollbacks": len(rollbacks_data["rollbacks"]),
            "operations_file_size": (
                self.operations_file.stat().st_size if self.operations_file.exists() else 0
            ),
            "rollbacks_file_size": (
                self.rollbacks_file.stat().st_size if self.rollbacks_file.exists() else 0
            ),
        }
