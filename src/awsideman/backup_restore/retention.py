"""
Retention policy management and automated cleanup for backup operations.

This module provides comprehensive retention policy enforcement, automated cleanup,
backup versioning, comparison capabilities, and storage monitoring with alerting.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from .interfaces import ProgressReporterInterface, StorageEngineInterface
from .models import BackupMetadata, RetentionPolicy


class RetentionPeriod(Enum):
    """Retention period categories."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


@dataclass
class StorageLimit:
    """Storage limit configuration."""

    max_size_bytes: Optional[int] = None
    max_backup_count: Optional[int] = None
    warning_threshold_percent: float = 80.0
    critical_threshold_percent: float = 95.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "max_size_bytes": self.max_size_bytes,
            "max_backup_count": self.max_backup_count,
            "warning_threshold_percent": self.warning_threshold_percent,
            "critical_threshold_percent": self.critical_threshold_percent,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StorageLimit":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class StorageUsage:
    """Current storage usage information."""

    total_size_bytes: int = 0
    total_backup_count: int = 0
    size_by_period: Dict[str, int] = field(default_factory=dict)
    count_by_period: Dict[str, int] = field(default_factory=dict)
    oldest_backup: Optional[datetime] = None
    newest_backup: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_size_bytes": self.total_size_bytes,
            "total_backup_count": self.total_backup_count,
            "size_by_period": self.size_by_period,
            "count_by_period": self.count_by_period,
            "oldest_backup": self.oldest_backup.isoformat() if self.oldest_backup else None,
            "newest_backup": self.newest_backup.isoformat() if self.newest_backup else None,
        }


@dataclass
class BackupVersion:
    """Backup version information for comparison."""

    backup_id: str
    timestamp: datetime
    version: str
    size_bytes: int
    resource_counts: Dict[str, int]
    checksum: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "backup_id": self.backup_id,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "size_bytes": self.size_bytes,
            "resource_counts": self.resource_counts,
            "checksum": self.checksum,
        }


@dataclass
class BackupComparison:
    """Comparison between two backup versions."""

    source_version: BackupVersion
    target_version: BackupVersion
    resource_changes: Dict[str, Dict[str, int]] = field(default_factory=dict)
    size_difference: int = 0
    time_difference: timedelta = field(default_factory=timedelta)
    similarity_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_version": self.source_version.to_dict(),
            "target_version": self.target_version.to_dict(),
            "resource_changes": self.resource_changes,
            "size_difference": self.size_difference,
            "time_difference": self.time_difference.total_seconds(),
            "similarity_score": self.similarity_score,
        }


@dataclass
class CleanupResult:
    """Result of cleanup operation."""

    success: bool
    deleted_backups: List[str] = field(default_factory=list)
    freed_bytes: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "deleted_backups": self.deleted_backups,
            "freed_bytes": self.freed_bytes,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class StorageAlert:
    """Storage monitoring alert."""

    alert_type: str  # warning, critical, info
    message: str
    current_usage: StorageUsage
    threshold_exceeded: Optional[float] = None
    recommended_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_type": self.alert_type,
            "message": self.message,
            "current_usage": self.current_usage.to_dict(),
            "threshold_exceeded": self.threshold_exceeded,
            "recommended_action": self.recommended_action,
        }


class RetentionManager:
    """
    Manages backup retention policies, automated cleanup, versioning, and storage monitoring.

    This class provides comprehensive retention policy enforcement with automated cleanup
    based on configurable rules, backup versioning and comparison capabilities, and
    storage limit monitoring with alerting.
    """

    def __init__(
        self,
        storage_engine: StorageEngineInterface,
        progress_reporter: Optional[ProgressReporterInterface] = None,
        storage_limits: Optional[StorageLimit] = None,
    ):
        """
        Initialize the retention manager.

        Args:
            storage_engine: Storage engine for backup operations
            progress_reporter: Optional progress reporter for long-running operations
            storage_limits: Optional storage limit configuration
        """
        self.storage_engine = storage_engine
        self.progress_reporter = progress_reporter
        self.storage_limits = storage_limits or StorageLimit()
        self.logger = logging.getLogger(__name__)

    async def enforce_retention_policy(
        self, retention_policy: RetentionPolicy, dry_run: bool = False
    ) -> CleanupResult:
        """
        Enforce retention policy by cleaning up old backups.

        Args:
            retention_policy: Retention policy to enforce
            dry_run: If True, only simulate cleanup without deleting

        Returns:
            CleanupResult containing cleanup operation details
        """
        operation_id = f"retention_cleanup_{datetime.now().isoformat()}"

        try:
            if self.progress_reporter:
                await self.progress_reporter.start_operation(
                    operation_id, 4, "Enforcing retention policy"
                )

            # Step 1: Get all backups
            all_backups = await self.storage_engine.list_backups()
            if self.progress_reporter:
                await self.progress_reporter.update_progress(
                    operation_id, 1, f"Found {len(all_backups)} backups"
                )

            # Step 2: Categorize backups by retention period
            categorized_backups = self._categorize_backups_by_period(all_backups)
            if self.progress_reporter:
                await self.progress_reporter.update_progress(
                    operation_id, 2, "Categorized backups by retention period"
                )

            # Step 3: Identify backups to delete
            backups_to_delete = self._identify_backups_for_deletion(
                categorized_backups, retention_policy
            )
            if self.progress_reporter:
                await self.progress_reporter.update_progress(
                    operation_id, 3, f"Identified {len(backups_to_delete)} backups for deletion"
                )

            # Step 4: Perform cleanup
            cleanup_result = await self._perform_cleanup(backups_to_delete, dry_run)
            if self.progress_reporter:
                await self.progress_reporter.complete_operation(
                    operation_id,
                    cleanup_result.success,
                    f"Cleanup completed: {len(cleanup_result.deleted_backups)} backups deleted",
                )

            return cleanup_result

        except Exception as e:
            self.logger.error(f"Error enforcing retention policy: {e}")
            if self.progress_reporter:
                await self.progress_reporter.complete_operation(
                    operation_id, False, f"Cleanup failed: {e}"
                )
            return CleanupResult(
                success=False, errors=[f"Retention policy enforcement failed: {e}"]
            )

    def _categorize_backups_by_period(
        self, backups: List[BackupMetadata]
    ) -> Dict[RetentionPeriod, List[BackupMetadata]]:
        """
        Categorize backups by retention period based on their age.

        Args:
            backups: List of backup metadata to categorize

        Returns:
            Dictionary mapping retention periods to backup lists
        """
        now = datetime.now()
        categorized = {period: [] for period in RetentionPeriod}

        for backup in backups:
            age = now - backup.timestamp

            if age <= timedelta(days=1):
                categorized[RetentionPeriod.DAILY].append(backup)
            elif age <= timedelta(weeks=1):
                categorized[RetentionPeriod.WEEKLY].append(backup)
            elif age <= timedelta(days=30):
                categorized[RetentionPeriod.MONTHLY].append(backup)
            else:
                categorized[RetentionPeriod.YEARLY].append(backup)

        # Sort each category by timestamp (newest first)
        for period in categorized:
            categorized[period].sort(key=lambda b: b.timestamp, reverse=True)

        return categorized

    def _identify_backups_for_deletion(
        self,
        categorized_backups: Dict[RetentionPeriod, List[BackupMetadata]],
        retention_policy: RetentionPolicy,
    ) -> List[BackupMetadata]:
        """
        Identify backups that should be deleted based on retention policy.

        Args:
            categorized_backups: Backups categorized by retention period
            retention_policy: Retention policy to apply

        Returns:
            List of backups to delete
        """
        backups_to_delete = []

        # Apply retention limits for each period
        retention_limits = {
            RetentionPeriod.DAILY: retention_policy.keep_daily,
            RetentionPeriod.WEEKLY: retention_policy.keep_weekly,
            RetentionPeriod.MONTHLY: retention_policy.keep_monthly,
            RetentionPeriod.YEARLY: retention_policy.keep_yearly,
        }

        for period, limit in retention_limits.items():
            backups_in_period = categorized_backups[period]
            if len(backups_in_period) > limit:
                # Keep the newest 'limit' backups, delete the rest
                backups_to_delete.extend(backups_in_period[limit:])

        return backups_to_delete

    async def _perform_cleanup(
        self, backups_to_delete: List[BackupMetadata], dry_run: bool
    ) -> CleanupResult:
        """
        Perform the actual cleanup of identified backups.

        Args:
            backups_to_delete: List of backups to delete
            dry_run: If True, only simulate deletion

        Returns:
            CleanupResult containing operation details
        """
        deleted_backups = []
        freed_bytes = 0
        errors = []
        warnings = []

        for backup in backups_to_delete:
            try:
                if dry_run:
                    self.logger.info(f"Would delete backup: {backup.backup_id}")
                    deleted_backups.append(backup.backup_id)
                    freed_bytes += backup.size_bytes
                else:
                    success = await self.storage_engine.delete_backup(backup.backup_id)
                    if success:
                        deleted_backups.append(backup.backup_id)
                        freed_bytes += backup.size_bytes
                        self.logger.info(f"Deleted backup: {backup.backup_id}")
                    else:
                        errors.append(f"Failed to delete backup: {backup.backup_id}")

            except Exception as e:
                error_msg = f"Error deleting backup {backup.backup_id}: {e}"
                errors.append(error_msg)
                self.logger.error(error_msg)

        return CleanupResult(
            success=len(errors) == 0,
            deleted_backups=deleted_backups,
            freed_bytes=freed_bytes,
            errors=errors,
            warnings=warnings,
        )

    async def get_backup_versions(self, instance_arn: Optional[str] = None) -> List[BackupVersion]:
        """
        Get versioned list of backups for comparison.

        Args:
            instance_arn: Optional filter by instance ARN

        Returns:
            List of backup versions sorted by timestamp
        """
        try:
            filters = {}
            if instance_arn:
                filters["instance_arn"] = instance_arn

            backups = await self.storage_engine.list_backups(filters)

            versions = []
            for backup in backups:
                version = BackupVersion(
                    backup_id=backup.backup_id,
                    timestamp=backup.timestamp,
                    version=backup.version,
                    size_bytes=backup.size_bytes,
                    resource_counts=backup.resource_counts,
                    checksum=backup.checksum,
                )
                versions.append(version)

            # Sort by timestamp (newest first)
            versions.sort(key=lambda v: v.timestamp, reverse=True)
            return versions

        except Exception as e:
            self.logger.error(f"Error getting backup versions: {e}")
            return []

    async def compare_backups(
        self, source_backup_id: str, target_backup_id: str
    ) -> Optional[BackupComparison]:
        """
        Compare two backup versions and analyze differences.

        Args:
            source_backup_id: ID of the source backup
            target_backup_id: ID of the target backup

        Returns:
            BackupComparison object with detailed comparison, or None if error
        """
        try:
            # Get backup metadata
            source_metadata = await self.storage_engine.get_backup_metadata(source_backup_id)
            target_metadata = await self.storage_engine.get_backup_metadata(target_backup_id)

            if not source_metadata or not target_metadata:
                self.logger.error("Could not retrieve metadata for one or both backups")
                return None

            # Create backup versions
            source_version = BackupVersion(
                backup_id=source_metadata.backup_id,
                timestamp=source_metadata.timestamp,
                version=source_metadata.version,
                size_bytes=source_metadata.size_bytes,
                resource_counts=source_metadata.resource_counts,
                checksum=source_metadata.checksum,
            )

            target_version = BackupVersion(
                backup_id=target_metadata.backup_id,
                timestamp=target_metadata.timestamp,
                version=target_metadata.version,
                size_bytes=target_metadata.size_bytes,
                resource_counts=target_metadata.resource_counts,
                checksum=target_metadata.checksum,
            )

            # Calculate differences
            resource_changes = self._calculate_resource_changes(
                source_metadata.resource_counts, target_metadata.resource_counts
            )

            size_difference = target_metadata.size_bytes - source_metadata.size_bytes
            time_difference = abs(target_metadata.timestamp - source_metadata.timestamp)
            similarity_score = self._calculate_similarity_score(
                source_metadata.resource_counts, target_metadata.resource_counts
            )

            return BackupComparison(
                source_version=source_version,
                target_version=target_version,
                resource_changes=resource_changes,
                size_difference=size_difference,
                time_difference=time_difference,
                similarity_score=similarity_score,
            )

        except Exception as e:
            self.logger.error(f"Error comparing backups: {e}")
            return None

    def _calculate_resource_changes(
        self, source_counts: Dict[str, int], target_counts: Dict[str, int]
    ) -> Dict[str, Dict[str, int]]:
        """
        Calculate changes in resource counts between two backups.

        Args:
            source_counts: Resource counts from source backup
            target_counts: Resource counts from target backup

        Returns:
            Dictionary with resource changes
        """
        changes = {}
        all_resources = set(source_counts.keys()) | set(target_counts.keys())

        for resource in all_resources:
            source_count = source_counts.get(resource, 0)
            target_count = target_counts.get(resource, 0)
            difference = target_count - source_count

            changes[resource] = {
                "source_count": source_count,
                "target_count": target_count,
                "difference": difference,
                "percent_change": (difference / source_count * 100) if source_count > 0 else 0,
            }

        return changes

    def _calculate_similarity_score(
        self, source_counts: Dict[str, int], target_counts: Dict[str, int]
    ) -> float:
        """
        Calculate similarity score between two backups based on resource counts.

        Args:
            source_counts: Resource counts from source backup
            target_counts: Resource counts from target backup

        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not source_counts and not target_counts:
            return 1.0

        all_resources = set(source_counts.keys()) | set(target_counts.keys())
        if not all_resources:
            return 1.0

        total_similarity = 0.0
        for resource in all_resources:
            source_count = source_counts.get(resource, 0)
            target_count = target_counts.get(resource, 0)

            if source_count == 0 and target_count == 0:
                similarity = 1.0
            elif source_count == 0 or target_count == 0:
                similarity = 0.0
            else:
                similarity = min(source_count, target_count) / max(source_count, target_count)

            total_similarity += similarity

        return total_similarity / len(all_resources)

    async def get_storage_usage(self) -> StorageUsage:
        """
        Get current storage usage information.

        Returns:
            StorageUsage object with current usage statistics
        """
        try:
            backups = await self.storage_engine.list_backups()

            usage = StorageUsage()
            usage.total_backup_count = len(backups)

            if not backups:
                return usage

            # Calculate totals and categorize by period
            now = datetime.now()
            for backup in backups:
                usage.total_size_bytes += backup.size_bytes

                # Update oldest/newest timestamps
                if usage.oldest_backup is None or backup.timestamp < usage.oldest_backup:
                    usage.oldest_backup = backup.timestamp
                if usage.newest_backup is None or backup.timestamp > usage.newest_backup:
                    usage.newest_backup = backup.timestamp

                # Categorize by age
                age = now - backup.timestamp
                if age <= timedelta(days=1):
                    period = "daily"
                elif age <= timedelta(weeks=1):
                    period = "weekly"
                elif age <= timedelta(days=30):
                    period = "monthly"
                else:
                    period = "yearly"

                usage.size_by_period[period] = (
                    usage.size_by_period.get(period, 0) + backup.size_bytes
                )
                usage.count_by_period[period] = usage.count_by_period.get(period, 0) + 1

            return usage

        except Exception as e:
            self.logger.error(f"Error getting storage usage: {e}")
            return StorageUsage()

    async def check_storage_limits(self) -> List[StorageAlert]:
        """
        Check current storage usage against configured limits and generate alerts.

        Returns:
            List of storage alerts if limits are exceeded
        """
        alerts = []

        try:
            usage = await self.get_storage_usage()

            # Check size limits
            if self.storage_limits.max_size_bytes:
                usage_percent = (usage.total_size_bytes / self.storage_limits.max_size_bytes) * 100

                if usage_percent >= self.storage_limits.critical_threshold_percent:
                    alerts.append(
                        StorageAlert(
                            alert_type="critical",
                            message=f"Storage usage critical: {usage_percent:.1f}% of limit",
                            current_usage=usage,
                            threshold_exceeded=usage_percent,
                            recommended_action="Immediate cleanup required - consider reducing retention periods",
                        )
                    )
                elif usage_percent >= self.storage_limits.warning_threshold_percent:
                    alerts.append(
                        StorageAlert(
                            alert_type="warning",
                            message=f"Storage usage warning: {usage_percent:.1f}% of limit",
                            current_usage=usage,
                            threshold_exceeded=usage_percent,
                            recommended_action="Consider running cleanup or adjusting retention policy",
                        )
                    )

            # Check count limits
            if self.storage_limits.max_backup_count:
                if usage.total_backup_count >= self.storage_limits.max_backup_count:
                    alerts.append(
                        StorageAlert(
                            alert_type="critical",
                            message=f"Backup count limit reached: {usage.total_backup_count}",
                            current_usage=usage,
                            recommended_action="Delete old backups or increase backup count limit",
                        )
                    )
                elif usage.total_backup_count >= (self.storage_limits.max_backup_count * 0.9):
                    alerts.append(
                        StorageAlert(
                            alert_type="warning",
                            message=f"Approaching backup count limit: {usage.total_backup_count}",
                            current_usage=usage,
                            recommended_action="Monitor backup count and consider cleanup",
                        )
                    )

            return alerts

        except Exception as e:
            self.logger.error(f"Error checking storage limits: {e}")
            return [
                StorageAlert(
                    alert_type="critical",
                    message=f"Failed to check storage limits: {e}",
                    current_usage=StorageUsage(),
                    recommended_action="Check system logs and storage configuration",
                )
            ]

    async def get_retention_recommendations(
        self, current_policy: RetentionPolicy
    ) -> Dict[str, Any]:
        """
        Analyze current storage usage and provide retention policy recommendations.

        Args:
            current_policy: Current retention policy

        Returns:
            Dictionary with recommendations and analysis
        """
        try:
            usage = await self.get_storage_usage()
            alerts = await self.check_storage_limits()

            recommendations = {
                "current_usage": usage.to_dict(),
                "current_policy": current_policy.to_dict(),
                "alerts": [alert.to_dict() for alert in alerts],
                "recommendations": [],
            }

            # Analyze usage patterns and provide recommendations
            if usage.total_backup_count > 0:
                avg_backup_size = usage.total_size_bytes / usage.total_backup_count

                # Check if we have too many daily backups
                daily_count = usage.count_by_period.get("daily", 0)
                if daily_count > current_policy.keep_daily * 1.5:
                    recommendations["recommendations"].append(
                        {
                            "type": "reduce_daily",
                            "message": f"Consider reducing daily retention from {current_policy.keep_daily} to {max(1, daily_count // 2)}",
                            "impact": f"Would free approximately {(daily_count - max(1, daily_count // 2)) * avg_backup_size / 1024 / 1024:.1f} MB",
                        }
                    )

                # Check storage efficiency
                if len(alerts) > 0:
                    critical_alerts = [a for a in alerts if a.alert_type == "critical"]
                    if critical_alerts:
                        recommendations["recommendations"].append(
                            {
                                "type": "immediate_cleanup",
                                "message": "Immediate cleanup required due to critical storage alerts",
                                "impact": "Essential to prevent storage issues",
                            }
                        )

                # Suggest optimization based on backup frequency
                if usage.count_by_period.get("yearly", 0) > current_policy.keep_yearly * 2:
                    recommendations["recommendations"].append(
                        {
                            "type": "optimize_yearly",
                            "message": "Consider archiving very old backups to cheaper storage",
                            "impact": "Reduce primary storage costs",
                        }
                    )

            return recommendations

        except Exception as e:
            self.logger.error(f"Error generating retention recommendations: {e}")
            return {"error": f"Failed to generate recommendations: {e}", "recommendations": []}
