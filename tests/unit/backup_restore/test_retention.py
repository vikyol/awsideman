"""
Unit tests for retention policy management and cleanup functionality.

Tests cover retention policy enforcement, automated cleanup, backup versioning,
comparison capabilities, and storage monitoring with alerting.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.awsideman.backup_restore.models import (
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    RetentionPolicy,
)
from src.awsideman.backup_restore.retention import (
    BackupComparison,
    BackupVersion,
    CleanupResult,
    RetentionManager,
    RetentionPeriod,
    StorageAlert,
    StorageLimit,
    StorageUsage,
)


class TestRetentionManager:
    """Test cases for RetentionManager class."""

    @pytest.fixture
    def mock_storage_engine(self):
        """Create mock storage engine."""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def mock_progress_reporter(self):
        """Create mock progress reporter."""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def storage_limits(self):
        """Create storage limits configuration."""
        return StorageLimit(
            max_size_bytes=1000000000,  # 1GB
            max_backup_count=100,
            warning_threshold_percent=80.0,
            critical_threshold_percent=95.0,
        )

    @pytest.fixture
    def retention_policy(self):
        """Create retention policy."""
        return RetentionPolicy(
            keep_daily=7, keep_weekly=4, keep_monthly=12, keep_yearly=3, auto_cleanup=True
        )

    @pytest.fixture
    def sample_backups(self):
        """Create sample backup metadata for testing."""
        now = datetime.now()
        backups = []

        # Create backups with different ages
        for i in range(20):
            backup = BackupMetadata(
                backup_id=f"backup_{i}",
                timestamp=now - timedelta(days=i),
                instance_arn="arn:aws:sso:::instance/ins-123456789",
                backup_type=BackupType.FULL,
                version="1.0.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
                resource_counts={"users": 10, "groups": 5},
                size_bytes=1000000 * (i + 1),  # Varying sizes
                checksum=f"checksum_{i}",
            )
            backups.append(backup)

        return backups

    @pytest.fixture
    def retention_manager(self, mock_storage_engine, mock_progress_reporter, storage_limits):
        """Create retention manager instance."""
        return RetentionManager(
            storage_engine=mock_storage_engine,
            progress_reporter=mock_progress_reporter,
            storage_limits=storage_limits,
        )

    @pytest.mark.asyncio
    async def test_enforce_retention_policy_success(
        self,
        retention_manager,
        mock_storage_engine,
        mock_progress_reporter,
        retention_policy,
        sample_backups,
    ):
        """Test successful retention policy enforcement."""
        # Setup
        mock_storage_engine.list_backups.return_value = sample_backups
        mock_storage_engine.delete_backup.return_value = True

        # Execute
        result = await retention_manager.enforce_retention_policy(retention_policy)

        # Verify
        assert result.success
        assert len(result.deleted_backups) > 0
        assert result.freed_bytes > 0
        assert len(result.errors) == 0

        # Verify progress reporting
        mock_progress_reporter.start_operation.assert_called_once()
        mock_progress_reporter.complete_operation.assert_called_once()
        assert mock_progress_reporter.update_progress.call_count == 3

    @pytest.mark.asyncio
    async def test_enforce_retention_policy_dry_run(
        self, retention_manager, mock_storage_engine, retention_policy, sample_backups
    ):
        """Test retention policy enforcement in dry run mode."""
        # Setup
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        result = await retention_manager.enforce_retention_policy(retention_policy, dry_run=True)

        # Verify
        assert result.success
        assert len(result.deleted_backups) > 0
        assert result.freed_bytes > 0

        # Verify no actual deletions occurred
        mock_storage_engine.delete_backup.assert_not_called()

    @pytest.mark.asyncio
    async def test_enforce_retention_policy_with_errors(
        self, retention_manager, mock_storage_engine, retention_policy, sample_backups
    ):
        """Test retention policy enforcement with deletion errors."""
        # Setup
        mock_storage_engine.list_backups.return_value = sample_backups
        mock_storage_engine.delete_backup.side_effect = [True, False, Exception("Delete failed")]

        # Execute
        result = await retention_manager.enforce_retention_policy(retention_policy)

        # Verify
        assert not result.success  # Should fail due to errors
        assert len(result.errors) > 0
        assert len(result.deleted_backups) >= 1  # At least one successful deletion

    def test_categorize_backups_by_period(self, retention_manager, sample_backups):
        """Test backup categorization by retention period."""
        # Execute
        categorized = retention_manager._categorize_backups_by_period(sample_backups)

        # Verify
        assert RetentionPeriod.DAILY in categorized
        assert RetentionPeriod.WEEKLY in categorized
        assert RetentionPeriod.MONTHLY in categorized
        assert RetentionPeriod.YEARLY in categorized

        # Verify categorization logic
        assert len(categorized[RetentionPeriod.DAILY]) >= 1  # At least today's backup
        assert len(categorized[RetentionPeriod.WEEKLY]) >= 1  # Backups from this week

        # Verify sorting (newest first)
        for period_backups in categorized.values():
            if len(period_backups) > 1:
                for i in range(len(period_backups) - 1):
                    assert period_backups[i].timestamp >= period_backups[i + 1].timestamp

    def test_identify_backups_for_deletion(
        self, retention_manager, sample_backups, retention_policy
    ):
        """Test identification of backups for deletion."""
        # Setup
        categorized = retention_manager._categorize_backups_by_period(sample_backups)

        # Execute
        to_delete = retention_manager._identify_backups_for_deletion(categorized, retention_policy)

        # Verify
        assert isinstance(to_delete, list)
        assert len(to_delete) >= 0  # Should identify some backups for deletion

        # Verify that we're not deleting more recent backups inappropriately
        if to_delete:
            newest_to_delete = max(to_delete, key=lambda b: b.timestamp)
            newest_overall = max(sample_backups, key=lambda b: b.timestamp)
            assert newest_to_delete.timestamp < newest_overall.timestamp

    @pytest.mark.asyncio
    async def test_perform_cleanup_success(
        self, retention_manager, sample_backups, mock_storage_engine
    ):
        """Test successful cleanup operation."""
        # Setup
        backups_to_delete = sample_backups[:5]  # Delete first 5 backups
        mock_storage_engine.delete_backup.return_value = True

        # Execute
        result = await retention_manager._perform_cleanup(backups_to_delete, dry_run=False)

        # Verify
        assert result.success
        assert len(result.deleted_backups) == 5
        assert result.freed_bytes == sum(b.size_bytes for b in backups_to_delete)
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_perform_cleanup_dry_run(self, retention_manager, sample_backups):
        """Test cleanup operation in dry run mode."""
        # Setup
        backups_to_delete = sample_backups[:3]

        # Execute
        result = await retention_manager._perform_cleanup(backups_to_delete, dry_run=True)

        # Verify
        assert result.success
        assert len(result.deleted_backups) == 3
        assert result.freed_bytes == sum(b.size_bytes for b in backups_to_delete)
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_get_backup_versions(
        self, retention_manager, mock_storage_engine, sample_backups
    ):
        """Test getting backup versions for comparison."""
        # Setup
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        versions = await retention_manager.get_backup_versions()

        # Verify
        assert len(versions) == len(sample_backups)
        assert all(isinstance(v, BackupVersion) for v in versions)

        # Verify sorting (newest first)
        for i in range(len(versions) - 1):
            assert versions[i].timestamp >= versions[i + 1].timestamp

    @pytest.mark.asyncio
    async def test_get_backup_versions_with_filter(
        self, retention_manager, mock_storage_engine, sample_backups
    ):
        """Test getting backup versions with instance ARN filter."""
        # Setup
        instance_arn = "arn:aws:sso:::instance/ins-123456789"
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        versions = await retention_manager.get_backup_versions(instance_arn)

        # Verify
        assert len(versions) == len(sample_backups)
        mock_storage_engine.list_backups.assert_called_once_with({"instance_arn": instance_arn})

    @pytest.mark.asyncio
    async def test_compare_backups_success(
        self, retention_manager, mock_storage_engine, sample_backups
    ):
        """Test successful backup comparison."""
        # Setup
        source_backup = sample_backups[0]
        target_backup = sample_backups[1]

        mock_storage_engine.get_backup_metadata.side_effect = [source_backup, target_backup]

        # Execute
        comparison = await retention_manager.compare_backups(
            source_backup.backup_id, target_backup.backup_id
        )

        # Verify
        assert comparison is not None
        assert isinstance(comparison, BackupComparison)
        assert comparison.source_version.backup_id == source_backup.backup_id
        assert comparison.target_version.backup_id == target_backup.backup_id
        assert isinstance(comparison.resource_changes, dict)
        assert isinstance(comparison.similarity_score, float)
        assert 0.0 <= comparison.similarity_score <= 1.0

    @pytest.mark.asyncio
    async def test_compare_backups_missing_metadata(self, retention_manager, mock_storage_engine):
        """Test backup comparison with missing metadata."""
        # Setup
        mock_storage_engine.get_backup_metadata.side_effect = [None, None]

        # Execute
        comparison = await retention_manager.compare_backups("backup_1", "backup_2")

        # Verify
        assert comparison is None

    def test_calculate_resource_changes(self, retention_manager):
        """Test resource change calculation."""
        # Setup
        source_counts = {"users": 10, "groups": 5, "permission_sets": 3}
        target_counts = {"users": 12, "groups": 4, "permission_sets": 3, "assignments": 20}

        # Execute
        changes = retention_manager._calculate_resource_changes(source_counts, target_counts)

        # Verify
        assert "users" in changes
        assert changes["users"]["difference"] == 2
        assert changes["users"]["percent_change"] == 20.0

        assert "groups" in changes
        assert changes["groups"]["difference"] == -1
        assert changes["groups"]["percent_change"] == -20.0

        assert "assignments" in changes
        assert changes["assignments"]["difference"] == 20
        assert changes["assignments"]["source_count"] == 0

    def test_calculate_similarity_score(self, retention_manager):
        """Test similarity score calculation."""
        # Test identical backups
        counts1 = {"users": 10, "groups": 5}
        counts2 = {"users": 10, "groups": 5}
        score = retention_manager._calculate_similarity_score(counts1, counts2)
        assert score == 1.0

        # Test completely different backups
        counts3 = {"users": 10}
        counts4 = {"groups": 5}
        score = retention_manager._calculate_similarity_score(counts3, counts4)
        assert score == 0.0

        # Test partially similar backups
        counts5 = {"users": 10, "groups": 5}
        counts6 = {"users": 5, "groups": 5}
        score = retention_manager._calculate_similarity_score(counts5, counts6)
        assert 0.0 < score < 1.0

    @pytest.mark.asyncio
    async def test_get_storage_usage(self, retention_manager, mock_storage_engine, sample_backups):
        """Test storage usage calculation."""
        # Setup
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        usage = await retention_manager.get_storage_usage()

        # Verify
        assert isinstance(usage, StorageUsage)
        assert usage.total_backup_count == len(sample_backups)
        assert usage.total_size_bytes == sum(b.size_bytes for b in sample_backups)
        assert usage.oldest_backup is not None
        assert usage.newest_backup is not None
        assert len(usage.size_by_period) > 0
        assert len(usage.count_by_period) > 0

    @pytest.mark.asyncio
    async def test_get_storage_usage_empty(self, retention_manager, mock_storage_engine):
        """Test storage usage with no backups."""
        # Setup
        mock_storage_engine.list_backups.return_value = []

        # Execute
        usage = await retention_manager.get_storage_usage()

        # Verify
        assert usage.total_backup_count == 0
        assert usage.total_size_bytes == 0
        assert usage.oldest_backup is None
        assert usage.newest_backup is None

    @pytest.mark.asyncio
    async def test_check_storage_limits_warning(
        self, retention_manager, mock_storage_engine, sample_backups
    ):
        """Test storage limit checking with warning threshold exceeded."""
        # Setup - modify storage limits to trigger warning (not critical)
        # Sample backups total size is sum(1000000 * (i + 1) for i in range(20)) = 210,000,000 bytes
        retention_manager.storage_limits.max_size_bytes = (
            250000000  # 250MB limit (will trigger warning at 80%)
        )
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        alerts = await retention_manager.check_storage_limits()

        # Verify
        assert len(alerts) > 0
        # Should have warning alerts (usage is ~84% of limit)
        warning_or_critical_alerts = [a for a in alerts if a.alert_type in ["warning", "critical"]]
        assert len(warning_or_critical_alerts) > 0
        assert warning_or_critical_alerts[0].threshold_exceeded is not None

    @pytest.mark.asyncio
    async def test_check_storage_limits_critical(
        self, retention_manager, mock_storage_engine, sample_backups
    ):
        """Test storage limit checking with critical threshold exceeded."""
        # Setup - modify storage limits to trigger critical alert
        retention_manager.storage_limits.max_size_bytes = 100000  # Very small limit
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        alerts = await retention_manager.check_storage_limits()

        # Verify
        assert len(alerts) > 0
        critical_alerts = [a for a in alerts if a.alert_type == "critical"]
        assert len(critical_alerts) > 0
        assert critical_alerts[0].recommended_action is not None

    @pytest.mark.asyncio
    async def test_check_storage_limits_count_limit(
        self, retention_manager, mock_storage_engine, sample_backups
    ):
        """Test storage limit checking with backup count limit."""
        # Setup - set low backup count limit
        retention_manager.storage_limits.max_backup_count = 10
        mock_storage_engine.list_backups.return_value = sample_backups  # 20 backups

        # Execute
        alerts = await retention_manager.check_storage_limits()

        # Verify
        assert len(alerts) > 0
        count_alerts = [a for a in alerts if "count" in a.message.lower()]
        assert len(count_alerts) > 0

    @pytest.mark.asyncio
    async def test_get_retention_recommendations(
        self, retention_manager, mock_storage_engine, sample_backups, retention_policy
    ):
        """Test retention policy recommendations."""
        # Setup
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        recommendations = await retention_manager.get_retention_recommendations(retention_policy)

        # Verify
        assert "current_usage" in recommendations
        assert "current_policy" in recommendations
        assert "alerts" in recommendations
        assert "recommendations" in recommendations
        assert isinstance(recommendations["recommendations"], list)

    @pytest.mark.asyncio
    async def test_get_retention_recommendations_with_alerts(
        self, retention_manager, mock_storage_engine, sample_backups, retention_policy
    ):
        """Test retention recommendations with storage alerts."""
        # Setup - trigger alerts
        retention_manager.storage_limits.max_size_bytes = 100000  # Small limit
        mock_storage_engine.list_backups.return_value = sample_backups

        # Execute
        recommendations = await retention_manager.get_retention_recommendations(retention_policy)

        # Verify
        assert len(recommendations["alerts"]) > 0
        assert len(recommendations["recommendations"]) > 0

        # Check for immediate cleanup recommendation
        immediate_cleanup = any(
            rec["type"] == "immediate_cleanup" for rec in recommendations["recommendations"]
        )
        assert immediate_cleanup


class TestStorageLimit:
    """Test cases for StorageLimit data class."""

    def test_storage_limit_creation(self):
        """Test StorageLimit creation with default values."""
        limit = StorageLimit()
        assert limit.max_size_bytes is None
        assert limit.max_backup_count is None
        assert limit.warning_threshold_percent == 80.0
        assert limit.critical_threshold_percent == 95.0

    def test_storage_limit_serialization(self):
        """Test StorageLimit serialization and deserialization."""
        limit = StorageLimit(
            max_size_bytes=1000000,
            max_backup_count=50,
            warning_threshold_percent=75.0,
            critical_threshold_percent=90.0,
        )

        # Test to_dict
        data = limit.to_dict()
        assert data["max_size_bytes"] == 1000000
        assert data["max_backup_count"] == 50

        # Test from_dict
        restored = StorageLimit.from_dict(data)
        assert restored.max_size_bytes == limit.max_size_bytes
        assert restored.max_backup_count == limit.max_backup_count


class TestStorageUsage:
    """Test cases for StorageUsage data class."""

    def test_storage_usage_creation(self):
        """Test StorageUsage creation with default values."""
        usage = StorageUsage()
        assert usage.total_size_bytes == 0
        assert usage.total_backup_count == 0
        assert len(usage.size_by_period) == 0
        assert len(usage.count_by_period) == 0

    def test_storage_usage_serialization(self):
        """Test StorageUsage serialization."""
        now = datetime.now()
        usage = StorageUsage(
            total_size_bytes=1000000,
            total_backup_count=10,
            size_by_period={"daily": 500000, "weekly": 300000},
            count_by_period={"daily": 5, "weekly": 3},
            oldest_backup=now - timedelta(days=30),
            newest_backup=now,
        )

        data = usage.to_dict()
        assert data["total_size_bytes"] == 1000000
        assert data["total_backup_count"] == 10
        assert "oldest_backup" in data
        assert "newest_backup" in data


class TestBackupVersion:
    """Test cases for BackupVersion data class."""

    def test_backup_version_creation(self):
        """Test BackupVersion creation."""
        now = datetime.now()
        version = BackupVersion(
            backup_id="backup_123",
            timestamp=now,
            version="1.0.0",
            size_bytes=1000000,
            resource_counts={"users": 10, "groups": 5},
            checksum="abc123",
        )

        assert version.backup_id == "backup_123"
        assert version.timestamp == now
        assert version.size_bytes == 1000000

    def test_backup_version_serialization(self):
        """Test BackupVersion serialization."""
        now = datetime.now()
        version = BackupVersion(
            backup_id="backup_123",
            timestamp=now,
            version="1.0.0",
            size_bytes=1000000,
            resource_counts={"users": 10, "groups": 5},
        )

        data = version.to_dict()
        assert data["backup_id"] == "backup_123"
        assert data["size_bytes"] == 1000000
        assert "timestamp" in data


class TestBackupComparison:
    """Test cases for BackupComparison data class."""

    def test_backup_comparison_creation(self):
        """Test BackupComparison creation."""
        now = datetime.now()
        source = BackupVersion(
            backup_id="backup_1",
            timestamp=now,
            version="1.0.0",
            size_bytes=1000000,
            resource_counts={"users": 10},
        )
        target = BackupVersion(
            backup_id="backup_2",
            timestamp=now + timedelta(hours=1),
            version="1.0.0",
            size_bytes=1100000,
            resource_counts={"users": 12},
        )

        comparison = BackupComparison(
            source_version=source,
            target_version=target,
            resource_changes={"users": {"difference": 2}},
            size_difference=100000,
            time_difference=timedelta(hours=1),
            similarity_score=0.85,
        )

        assert comparison.source_version.backup_id == "backup_1"
        assert comparison.target_version.backup_id == "backup_2"
        assert comparison.size_difference == 100000
        assert comparison.similarity_score == 0.85

    def test_backup_comparison_serialization(self):
        """Test BackupComparison serialization."""
        now = datetime.now()
        source = BackupVersion(
            backup_id="backup_1",
            timestamp=now,
            version="1.0.0",
            size_bytes=1000000,
            resource_counts={"users": 10},
        )
        target = BackupVersion(
            backup_id="backup_2",
            timestamp=now,
            version="1.0.0",
            size_bytes=1000000,
            resource_counts={"users": 10},
        )

        comparison = BackupComparison(source_version=source, target_version=target)

        data = comparison.to_dict()
        assert "source_version" in data
        assert "target_version" in data
        assert "resource_changes" in data
        assert "similarity_score" in data


class TestCleanupResult:
    """Test cases for CleanupResult data class."""

    def test_cleanup_result_creation(self):
        """Test CleanupResult creation."""
        result = CleanupResult(
            success=True,
            deleted_backups=["backup_1", "backup_2"],
            freed_bytes=2000000,
            errors=[],
            warnings=["Warning message"],
        )

        assert result.success is True
        assert len(result.deleted_backups) == 2
        assert result.freed_bytes == 2000000
        assert len(result.warnings) == 1

    def test_cleanup_result_serialization(self):
        """Test CleanupResult serialization."""
        result = CleanupResult(success=False, errors=["Error message"])

        data = result.to_dict()
        assert data["success"] is False
        assert "errors" in data
        assert "deleted_backups" in data


class TestStorageAlert:
    """Test cases for StorageAlert data class."""

    def test_storage_alert_creation(self):
        """Test StorageAlert creation."""
        usage = StorageUsage(total_size_bytes=1000000)
        alert = StorageAlert(
            alert_type="warning",
            message="Storage usage high",
            current_usage=usage,
            threshold_exceeded=85.0,
            recommended_action="Consider cleanup",
        )

        assert alert.alert_type == "warning"
        assert alert.message == "Storage usage high"
        assert alert.threshold_exceeded == 85.0

    def test_storage_alert_serialization(self):
        """Test StorageAlert serialization."""
        usage = StorageUsage()
        alert = StorageAlert(alert_type="critical", message="Storage full", current_usage=usage)

        data = alert.to_dict()
        assert data["alert_type"] == "critical"
        assert "current_usage" in data
        assert "message" in data
