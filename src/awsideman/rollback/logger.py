"""Operation logger for tracking permission set operations."""

from typing import Any, Dict, List, Optional

from .models import OperationRecord, OperationResult, OperationType, PrincipalType
from .storage import OperationStore


class OperationLogger:
    """Logger for tracking permission set operations."""

    def __init__(self, storage_directory: Optional[str] = None, profile: Optional[str] = None):
        """Initialize the operation logger.

        Args:
            storage_directory: Directory to store operation files.
            profile: AWS profile name for isolation.
        """
        self.profile = profile

        # Load configuration to get rollback settings
        try:
            from ..utils.config import Config

            config = Config()
            rollback_config = config.get_rollback_config()

            # Always use configured storage directory if available and rollback is enabled
            if rollback_config.get("enabled", True):
                configured_storage = rollback_config.get("storage_directory")
                if configured_storage:
                    storage_directory = configured_storage

        except Exception:
            # If config loading fails, continue with provided storage_directory
            pass

        self.store = OperationStore(storage_directory, profile)

    def log_operation(
        self,
        operation_type: str,
        principal_id: str,
        principal_type: str,
        principal_name: str,
        permission_set_arn: str,
        permission_set_name: str,
        account_ids: List[str],
        account_names: List[str],
        results: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log a permission set operation.

        Args:
            operation_type: Type of operation ("assign" or "revoke")
            principal_id: ID of the principal (user or group)
            principal_type: Type of principal ("USER" or "GROUP")
            principal_name: Display name of the principal
            permission_set_arn: ARN of the permission set
            permission_set_name: Name of the permission set
            account_ids: List of account IDs affected
            account_names: List of account names affected
            results: List of operation results per account
            metadata: Additional metadata about the operation

        Returns:
            The operation ID of the logged operation
        """
        # Convert string enums to proper enum types
        op_type = OperationType(operation_type.lower())
        principal_type_enum = PrincipalType(principal_type.upper())

        # Convert results to OperationResult objects
        operation_results = [
            OperationResult(
                account_id=result["account_id"],
                success=result["success"],
                error=result.get("error"),
                duration_ms=result.get("duration_ms"),
            )
            for result in results
        ]

        # Create operation record
        operation = OperationRecord.create(
            operation_type=op_type,
            principal_id=principal_id,
            principal_type=principal_type_enum,
            principal_name=principal_name,
            permission_set_arn=permission_set_arn,
            permission_set_name=permission_set_name,
            account_ids=account_ids,
            account_names=account_names,
            results=operation_results,
            metadata=metadata,
        )

        # Store the operation
        self.store.store_operation(operation)

        return operation.operation_id

    def get_operations(
        self,
        operation_type: Optional[str] = None,
        principal: Optional[str] = None,
        permission_set: Optional[str] = None,
        days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[OperationRecord]:
        """Get operations with optional filtering.

        Args:
            operation_type: Filter by operation type ("assign" or "revoke")
            principal: Filter by principal name or ID (partial match)
            permission_set: Filter by permission set name or ARN (partial match)
            days: Only return operations from the last N days
            limit: Maximum number of operations to return

        Returns:
            List of operation records matching the filters
        """
        return self.store.get_operations(
            operation_type=operation_type,
            principal=principal,
            permission_set=permission_set,
            days=days,
            limit=limit,
        )

    def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        """Get a specific operation by ID.

        Args:
            operation_id: The operation ID to retrieve

        Returns:
            The operation record if found, None otherwise
        """
        return self.store.get_operation(operation_id)

    def mark_rolled_back(self, operation_id: str, rollback_operation_id: str) -> bool:
        """Mark an operation as rolled back.

        Args:
            operation_id: The original operation ID
            rollback_operation_id: The ID of the rollback operation

        Returns:
            True if the operation was found and marked, False otherwise
        """
        return self.store.mark_operation_rolled_back(operation_id, rollback_operation_id)

    def cleanup_old_operations(self, days: int = 90) -> int:
        """Remove operations older than specified days.

        Args:
            days: Number of days to retain operations

        Returns:
            Number of operations removed
        """
        return self.store.cleanup_old_operations(days)

    def cleanup_by_count_limit(self, max_operations: int = 10000) -> int:
        """Remove oldest operations to stay within count limit.

        Args:
            max_operations: Maximum number of operations to keep

        Returns:
            Number of operations removed
        """
        return self.store.cleanup_by_count_limit(max_operations)

    def cleanup_rollback_records(self, days: int = 90) -> int:
        """Remove rollback records older than specified days.

        Args:
            days: Number of days to retain rollback records

        Returns:
            Number of rollback records removed
        """
        return self.store.cleanup_rollback_records(days)

    def rotate_files_if_needed(self, max_size_mb: int = 50) -> Dict[str, bool]:
        """Rotate files if they exceed size limit.

        Args:
            max_size_mb: Maximum file size in MB before rotation

        Returns:
            Dictionary indicating which files were rotated
        """
        return self.store.rotate_files_if_needed(max_size_mb)

    def perform_maintenance(
        self, retention_days: int = 90, max_operations: int = 10000, max_file_size_mb: int = 50
    ) -> Dict[str, Any]:
        """Perform comprehensive maintenance on operation storage.

        Args:
            retention_days: Number of days to retain operations
            max_operations: Maximum number of operations to keep
            max_file_size_mb: Maximum file size in MB before rotation

        Returns:
            Dictionary with maintenance results
        """
        results = {
            "operations_removed_by_age": 0,
            "operations_removed_by_count": 0,
            "rollbacks_removed": 0,
            "files_rotated": {"operations": False, "rollbacks": False},
            "storage_stats_before": self.get_storage_stats(),
            "storage_stats_after": {},
        }

        # Clean up old operations by age
        results["operations_removed_by_age"] = self.cleanup_old_operations(retention_days)

        # Clean up operations by count limit
        results["operations_removed_by_count"] = self.cleanup_by_count_limit(max_operations)

        # Clean up old rollback records
        results["rollbacks_removed"] = self.cleanup_rollback_records(retention_days)

        # Rotate files if needed
        results["files_rotated"] = self.rotate_files_if_needed(max_file_size_mb)

        # Get final storage stats
        results["storage_stats_after"] = self.get_storage_stats()

        return results

    def get_storage_stats(self) -> Dict[str, int]:
        """Get storage statistics.

        Returns:
            Dictionary with storage statistics
        """
        return self.store.get_storage_stats()
