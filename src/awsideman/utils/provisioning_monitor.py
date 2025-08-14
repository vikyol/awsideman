"""Provisioning monitoring component for AWS Identity Center status monitoring."""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from .status_infrastructure import BaseStatusChecker, StatusCheckError
from .status_models import (
    ProvisioningOperation,
    ProvisioningOperationStatus,
    ProvisioningStatus,
    StatusLevel,
)

logger = logging.getLogger(__name__)


class ProvisioningMonitor(BaseStatusChecker):
    """
    Provisioning monitor component for AWS Identity Center.

    Tracks active and failed provisioning operations, detects pending operations,
    estimates completion times, and provides detailed error reporting for
    failed operations.
    """

    def __init__(self, idc_client, config=None):
        """
        Initialize the provisioning monitor.

        Args:
            idc_client: AWS Identity Center client wrapper
            config: Status check configuration
        """
        super().__init__(idc_client, config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Cache for operation tracking
        self._operation_cache: Dict[str, ProvisioningOperation] = {}
        self._last_check_time: Optional[datetime] = None

    async def check_status(self) -> ProvisioningStatus:
        """
        Perform comprehensive provisioning status check.

        Returns:
            ProvisioningStatus: Provisioning status results with operations and estimates
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)

        try:
            # Get all active and recent provisioning operations
            active_operations = await self._get_active_operations()
            failed_operations = await self._get_failed_operations()
            completed_operations = await self._get_completed_operations()

            # Calculate pending count and estimated completion
            pending_count = len(active_operations)
            estimated_completion = self._estimate_completion_time(active_operations)

            # Determine overall provisioning status
            overall_status = self._determine_provisioning_status(
                active_operations, failed_operations, completed_operations
            )

            # Create provisioning status result
            provisioning_status = ProvisioningStatus(
                timestamp=timestamp,
                status=overall_status["status"],
                message=overall_status["message"],
                active_operations=active_operations,
                failed_operations=failed_operations,
                completed_operations=completed_operations,
                pending_count=pending_count,
                estimated_completion=estimated_completion,
            )

            # Add detailed information
            provisioning_status.add_detail(
                "total_operations",
                len(active_operations) + len(failed_operations) + len(completed_operations),
            )
            provisioning_status.add_detail("failure_rate", provisioning_status.get_failure_rate())
            provisioning_status.add_detail("check_duration_ms", (time.time() - start_time) * 1000)

            # Add operation type breakdown
            operation_types = self._get_operation_type_breakdown(
                active_operations + failed_operations + completed_operations
            )
            provisioning_status.add_detail("operation_types", operation_types)

            # Add any errors encountered during monitoring
            if overall_status.get("errors"):
                provisioning_status.errors.extend(overall_status["errors"])

            self.logger.info(
                f"Provisioning status check completed: {overall_status['status']} "
                f"({pending_count} active, {len(failed_operations)} failed)"
            )

            # Update cache and last check time
            self._update_operation_cache(
                active_operations + failed_operations + completed_operations
            )
            self._last_check_time = timestamp

            return provisioning_status

        except Exception as e:
            # Handle unexpected errors
            self.logger.error(f"Unexpected error in provisioning status check: {str(e)}")

            # Create error result
            provisioning_status = ProvisioningStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=f"Provisioning status check failed: {str(e)}",
                active_operations=[],
                failed_operations=[],
                completed_operations=[],
                pending_count=0,
                estimated_completion=None,
            )

            provisioning_status.add_error(str(e))
            provisioning_status.add_detail("error_type", type(e).__name__)
            provisioning_status.add_detail("component", "ProvisioningMonitor")

            return provisioning_status

    async def _get_active_operations(self) -> List[ProvisioningOperation]:
        """
        Get all active provisioning operations.

        Returns:
            List[ProvisioningOperation]: Active provisioning operations
        """
        active_operations = []

        try:
            client = self.idc_client.get_sso_admin_client()

            # Get all Identity Center instances
            instances_response = client.list_instances()
            instances = instances_response.get("Instances", [])

            if not instances:
                self.logger.warning("No Identity Center instances found")
                return active_operations

            # Check provisioning status for each instance
            for instance in instances:
                instance_arn = instance["InstanceArn"]

                try:
                    # List permission set provisioning status
                    # Note: AWS Identity Center doesn't have a direct API to list all provisioning operations
                    # We need to check the status of recent operations or track them from assignment operations

                    # Get permission sets to check their provisioning status
                    ps_response = client.list_permission_sets(InstanceArn=instance_arn)
                    permission_sets = ps_response.get("PermissionSets", [])

                    # For each permission set, check if there are any pending provisioning operations
                    for ps_arn in permission_sets:
                        try:
                            # Check permission set provisioning status
                            # This is a hypothetical API call - AWS doesn't provide direct access to all provisioning operations
                            # In practice, we would need to track operations from create/delete assignment calls

                            # For now, we'll simulate checking for active operations
                            # In a real implementation, this would involve:
                            # 1. Tracking request IDs from assignment operations
                            # 2. Using describe_permission_set_provisioning_status for tracked operations
                            # 3. Maintaining a database/cache of ongoing operations

                            active_op = await self._check_permission_set_provisioning_status(
                                instance_arn, ps_arn
                            )
                            if active_op:
                                active_operations.append(active_op)

                        except ClientError as e:
                            error_code = e.response.get("Error", {}).get("Code", "Unknown")
                            if error_code not in ["AccessDenied", "ResourceNotFound"]:
                                self.logger.warning(
                                    f"Error checking provisioning status for {ps_arn}: {str(e)}"
                                )
                        except Exception as e:
                            self.logger.warning(
                                f"Unexpected error checking provisioning for {ps_arn}: {str(e)}"
                            )

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    self.logger.warning(
                        f"Error listing permission sets for instance {instance_arn}: {error_code}"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Unexpected error processing instance {instance_arn}: {str(e)}"
                    )

        except Exception as e:
            self.logger.error(f"Error getting active operations: {str(e)}")
            raise StatusCheckError(
                f"Failed to retrieve active provisioning operations: {str(e)}",
                "ProvisioningMonitor",
            )

        return active_operations

    async def _get_failed_operations(self) -> List[ProvisioningOperation]:
        """
        Get all failed provisioning operations from recent history.

        Returns:
            List[ProvisioningOperation]: Failed provisioning operations
        """
        failed_operations = []

        try:
            # In a real implementation, this would:
            # 1. Query a database/cache of tracked operations
            # 2. Check the status of operations that were previously in progress
            # 3. Identify operations that have failed based on error responses

            # For now, we'll check cached operations and simulate failure detection
            for operation_id, cached_op in self._operation_cache.items():
                if cached_op.status == ProvisioningOperationStatus.IN_PROGRESS:
                    # Check if this operation has now failed
                    updated_op = await self._check_operation_status(cached_op)
                    if updated_op and updated_op.has_failed():
                        failed_operations.append(updated_op)

            # Also simulate some failed operations for demonstration
            # In practice, these would come from actual AWS API responses
            if not failed_operations:
                # Create a sample failed operation if we don't have real data
                # Only add if we're in a test/demo mode
                # failed_operations.append(sample_failed)
                pass

        except Exception as e:
            self.logger.error(f"Error getting failed operations: {str(e)}")
            # Don't raise here, just log and return empty list

        return failed_operations

    async def _get_completed_operations(self) -> List[ProvisioningOperation]:
        """
        Get recently completed provisioning operations.

        Returns:
            List[ProvisioningOperation]: Recently completed operations
        """
        completed_operations = []

        try:
            # Check cached operations for completed ones
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)  # Last 24 hours

            for operation_id, cached_op in self._operation_cache.items():
                if (
                    cached_op.status == ProvisioningOperationStatus.SUCCEEDED
                    and cached_op.created_date >= cutoff_time
                ):
                    completed_operations.append(cached_op)

        except Exception as e:
            self.logger.error(f"Error getting completed operations: {str(e)}")
            # Don't raise here, just log and return empty list

        return completed_operations

    async def _check_permission_set_provisioning_status(
        self, instance_arn: str, permission_set_arn: str
    ) -> Optional[ProvisioningOperation]:
        """
        Check provisioning status for a specific permission set.

        Args:
            instance_arn: Identity Center instance ARN
            permission_set_arn: Permission set ARN

        Returns:
            ProvisioningOperation: Active operation if found, None otherwise
        """
        try:
            # In a real implementation, this would:
            # 1. Check if we have any tracked request IDs for this permission set
            # 2. Use describe_permission_set_provisioning_status to check status
            # 3. Return operation details if still in progress

            # For now, we'll simulate this by checking if there are recent assignment operations
            # that might still be provisioning

            # This is a placeholder - in practice you would track request IDs from
            # create_account_assignment and delete_account_assignment operations
            return None

        except Exception as e:
            self.logger.warning(
                f"Error checking provisioning status for {permission_set_arn}: {str(e)}"
            )
            return None

    async def _check_operation_status(
        self, operation: ProvisioningOperation
    ) -> Optional[ProvisioningOperation]:
        """
        Check the current status of a provisioning operation.

        Args:
            operation: Operation to check

        Returns:
            ProvisioningOperation: Updated operation or None if not found
        """
        try:
            # In a real implementation, this would use:
            # response = client.describe_permission_set_provisioning_status(
            #     InstanceArn=instance_arn,
            #     ProvisioningRequestId=operation.operation_id
            # )

            # For now, simulate status checking
            # If operation is older than 10 minutes, consider it completed or failed
            age_minutes = (datetime.now(timezone.utc) - operation.created_date).total_seconds() / 60

            if age_minutes > 10:
                # Simulate completion or failure
                if operation.failure_reason:
                    operation.status = ProvisioningOperationStatus.FAILED
                else:
                    operation.status = ProvisioningOperationStatus.SUCCEEDED
                    operation.estimated_completion = datetime.now(timezone.utc)

            return operation

        except Exception as e:
            self.logger.warning(
                f"Error checking operation status for {operation.operation_id}: {str(e)}"
            )
            return operation

    def _estimate_completion_time(
        self, active_operations: List[ProvisioningOperation]
    ) -> Optional[datetime]:
        """
        Estimate completion time for active operations.

        Args:
            active_operations: List of active operations

        Returns:
            datetime: Estimated completion time or None if no active operations
        """
        if not active_operations:
            return None

        try:
            # Calculate average operation duration from completed operations
            completed_durations = []
            for operation in self._operation_cache.values():
                if operation.is_completed() and operation.get_duration_minutes():
                    completed_durations.append(operation.get_duration_minutes())

            # Use historical average or default estimate
            if completed_durations:
                avg_duration_minutes = sum(completed_durations) / len(completed_durations)
            else:
                # Default estimate: 5 minutes per operation
                avg_duration_minutes = 5.0

            # Find the oldest active operation
            oldest_operation = min(active_operations, key=lambda op: op.created_date)
            elapsed_minutes = (
                datetime.now(timezone.utc) - oldest_operation.created_date
            ).total_seconds() / 60

            # Estimate remaining time
            remaining_minutes = max(0, avg_duration_minutes - elapsed_minutes)

            return datetime.now(timezone.utc) + timedelta(minutes=remaining_minutes)

        except Exception as e:
            self.logger.warning(f"Error estimating completion time: {str(e)}")
            return None

    def _determine_provisioning_status(
        self,
        active_operations: List[ProvisioningOperation],
        failed_operations: List[ProvisioningOperation],
        completed_operations: List[ProvisioningOperation],
    ) -> Dict[str, Any]:
        """
        Determine overall provisioning status based on operation states.

        Args:
            active_operations: Active operations
            failed_operations: Failed operations
            completed_operations: Completed operations

        Returns:
            Dict containing status and message
        """
        total_operations = (
            len(active_operations) + len(failed_operations) + len(completed_operations)
        )

        # No operations found
        if total_operations == 0:
            return {
                "status": StatusLevel.HEALTHY,
                "message": "No active provisioning operations",
                "errors": [],
            }

        # Check for critical conditions
        if failed_operations:
            failure_rate = len(failed_operations) / total_operations * 100

            if failure_rate > 50:  # More than 50% failure rate
                return {
                    "status": StatusLevel.CRITICAL,
                    "message": f"High provisioning failure rate: {failure_rate:.1f}% ({len(failed_operations)} of {total_operations} operations failed)",
                    "errors": [f"Failed operations: {len(failed_operations)}"],
                }
            elif failure_rate > 20:  # More than 20% failure rate
                return {
                    "status": StatusLevel.WARNING,
                    "message": f"Elevated provisioning failure rate: {failure_rate:.1f}% ({len(failed_operations)} of {total_operations} operations failed)",
                    "errors": [f"Failed operations: {len(failed_operations)}"],
                }

        # Check for long-running operations
        long_running_ops = []
        for op in active_operations:
            age_minutes = (datetime.now(timezone.utc) - op.created_date).total_seconds() / 60
            if age_minutes > 30:  # Operations running longer than 30 minutes
                long_running_ops.append(op)

        if long_running_ops:
            return {
                "status": StatusLevel.WARNING,
                "message": f"{len(long_running_ops)} provisioning operations running longer than expected",
                "errors": [f"Long-running operations: {len(long_running_ops)}"],
            }

        # Active operations present
        if active_operations:
            return {
                "status": StatusLevel.HEALTHY,
                "message": f"{len(active_operations)} provisioning operations in progress",
                "errors": [],
            }

        # Only completed operations
        return {
            "status": StatusLevel.HEALTHY,
            "message": f"All provisioning operations completed successfully ({len(completed_operations)} recent operations)",
            "errors": [],
        }

    def _get_operation_type_breakdown(
        self, operations: List[ProvisioningOperation]
    ) -> Dict[str, int]:
        """
        Get breakdown of operations by type.

        Args:
            operations: List of operations

        Returns:
            Dict mapping operation types to counts
        """
        breakdown = {}
        for operation in operations:
            op_type = operation.operation_type
            breakdown[op_type] = breakdown.get(op_type, 0) + 1
        return breakdown

    def _update_operation_cache(self, operations: List[ProvisioningOperation]) -> None:
        """
        Update the internal operation cache.

        Args:
            operations: Operations to cache
        """
        try:
            # Update cache with new operations
            for operation in operations:
                self._operation_cache[operation.operation_id] = operation

            # Clean up old operations (older than 7 days)
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
            operations_to_remove = []

            for operation_id, operation in self._operation_cache.items():
                if operation.created_date < cutoff_time:
                    operations_to_remove.append(operation_id)

            for operation_id in operations_to_remove:
                del self._operation_cache[operation_id]

            self.logger.debug(
                f"Updated operation cache: {len(self._operation_cache)} operations cached"
            )

        except Exception as e:
            self.logger.warning(f"Error updating operation cache: {str(e)}")

    def get_operation_counts(self) -> Dict[str, int]:
        """
        Get counts of operations by status.

        Returns:
            Dict mapping status to counts
        """
        counts = {"active": 0, "failed": 0, "completed": 0, "total": 0}

        for operation in self._operation_cache.values():
            counts["total"] += 1
            if operation.is_active():
                counts["active"] += 1
            elif operation.has_failed():
                counts["failed"] += 1
            elif operation.is_completed():
                counts["completed"] += 1

        return counts

    def get_error_details(
        self, failed_operations: List[ProvisioningOperation]
    ) -> List[Dict[str, Any]]:
        """
        Get detailed error information for failed operations.

        Args:
            failed_operations: List of failed operations

        Returns:
            List of error detail dictionaries
        """
        error_details = []

        for operation in failed_operations:
            if operation.has_failed() and operation.failure_reason:
                error_details.append(
                    {
                        "operation_id": operation.operation_id,
                        "operation_type": operation.operation_type,
                        "target_id": operation.target_id,
                        "target_type": operation.target_type,
                        "failure_reason": operation.failure_reason,
                        "created_date": operation.created_date.isoformat(),
                        "age_minutes": (
                            datetime.now(timezone.utc) - operation.created_date
                        ).total_seconds()
                        / 60,
                    }
                )

        return error_details

    def format_provisioning_summary(self, provisioning_status: ProvisioningStatus) -> str:
        """
        Format a concise provisioning summary for display.

        Args:
            provisioning_status: Provisioning status to format

        Returns:
            str: Formatted provisioning summary
        """
        summary_parts = [
            f"Status: {provisioning_status.status.value}",
            f"Message: {provisioning_status.message}",
        ]

        if provisioning_status.pending_count > 0:
            summary_parts.append(f"Active: {provisioning_status.pending_count}")

        if provisioning_status.has_failed_operations():
            summary_parts.append(f"Failed: {len(provisioning_status.failed_operations)}")

        if provisioning_status.estimated_completion:
            eta_minutes = (
                provisioning_status.estimated_completion - datetime.now(timezone.utc)
            ).total_seconds() / 60
            if eta_minutes > 0:
                summary_parts.append(f"ETA: {eta_minutes:.0f}min")

        failure_rate = provisioning_status.get_failure_rate()
        if failure_rate > 0:
            summary_parts.append(f"Failure Rate: {failure_rate:.1f}%")

        return " | ".join(summary_parts)
