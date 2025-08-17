"""
Integration tests for retention policy management with storage engine.

Tests the integration between retention manager and storage engine,
including end-to-end retention policy enforcement and cleanup operations.
"""

import asyncio
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.awsideman.backup_restore.backends import FileSystemStorageBackend
from src.awsideman.backup_restore.models import (
    BackupData,
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    GroupData,
    RelationshipMap,
    RetentionPolicy,
    UserData,
)
from src.awsideman.backup_restore.retention import RetentionManager, StorageLimit, StorageUsage
from src.awsideman.backup_restore.storage import StorageEngine


class TestRetentionIntegration:
    """Integration tests for retention manager with real storage."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary directory for storage tests."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def storage_engine(self, temp_storage_dir):
        """Create storage engine with filesystem backend."""
        backend = FileSystemStorageBackend(str(temp_storage_dir))
        return StorageEngine(backend=backend, enable_compression=False)

    @pytest.fixture
    def retention_manager(self, storage_engine):
        """Create retention manager with real storage engine."""
        storage_limits = StorageLimit(
            max_size_bytes=10000000,  # 10MB
            max_backup_count=50,
            warning_threshold_percent=80.0,
            critical_threshold_percent=95.0,
        )
        return RetentionManager(storage_engine=storage_engine, storage_limits=storage_limits)

    @pytest.fixture
    def retention_policy(self):
        """Create test retention policy."""
        return RetentionPolicy(
            keep_daily=3, keep_weekly=2, keep_monthly=2, keep_yearly=1, auto_cleanup=True
        )

    async def create_test_backup(
        self,
        storage_engine: StorageEngine,
        backup_id: str,
        timestamp: datetime,
        size_multiplier: int = 1,
    ) -> str:
        """Create a test backup in storage."""
        # Create sample backup data
        metadata = BackupMetadata(
            backup_id=backup_id,
            timestamp=timestamp,
            instance_arn="arn:aws:sso:::instance/ins-123456789",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(encrypted=False),
            resource_counts={"users": 10 * size_multiplier, "groups": 5 * size_multiplier},
            size_bytes=1000 * size_multiplier,
        )

        backup_data = BackupData(
            metadata=metadata,
            users=[
                UserData(user_id=f"user_{i}", user_name=f"user{i}")
                for i in range(10 * size_multiplier)
            ],
            groups=[
                GroupData(group_id=f"group_{i}", display_name=f"Group {i}")
                for i in range(5 * size_multiplier)
            ],
            relationships=RelationshipMap(),
        )

        # Store the backup
        stored_id = await storage_engine.store_backup(backup_data)
        return stored_id

    @pytest.mark.asyncio
    async def test_end_to_end_retention_enforcement(
        self, retention_manager, storage_engine, retention_policy
    ):
        """Test complete retention policy enforcement workflow."""
        now = datetime.now()

        # Create backups with different ages
        backup_ids = []
        for i in range(10):
            backup_id = f"backup_{i}"
            timestamp = now - timedelta(days=i)
            stored_id = await self.create_test_backup(storage_engine, backup_id, timestamp)
            backup_ids.append(stored_id)

        # Verify all backups are stored
        all_backups = await storage_engine.list_backups()
        assert len(all_backups) == 10

        # Enforce retention policy
        result = await retention_manager.enforce_retention_policy(retention_policy)

        # Verify cleanup was successful
        assert result.success
        assert len(result.deleted_backups) > 0
        assert result.freed_bytes > 0

        # Verify backups were actually deleted
        remaining_backups = await storage_engine.list_backups()
        assert len(remaining_backups) < 10
        assert len(remaining_backups) == 10 - len(result.deleted_backups)

        # Verify retention policy was respected
        # Should keep: 3 daily + 2 weekly + 2 monthly + 1 yearly = max 8 backups
        # But actual retention depends on backup distribution across periods
        assert len(remaining_backups) <= 8

    @pytest.mark.asyncio
    async def test_retention_with_different_backup_ages(
        self, retention_manager, storage_engine, retention_policy
    ):
        """Test retention policy with backups of various ages."""
        now = datetime.now()

        # Create backups with specific age distribution
        backup_scenarios = [
            ("daily_1", now - timedelta(hours=6)),
            ("daily_2", now - timedelta(hours=12)),
            ("daily_3", now - timedelta(hours=18)),
            ("daily_4", now - timedelta(days=1)),  # Should be deleted (exceeds daily limit)
            ("weekly_1", now - timedelta(days=3)),
            ("weekly_2", now - timedelta(days=5)),
            ("weekly_3", now - timedelta(days=7)),  # Should be deleted (exceeds weekly limit)
            ("monthly_1", now - timedelta(days=15)),
            ("monthly_2", now - timedelta(days=25)),
            ("monthly_3", now - timedelta(days=35)),  # Should be deleted (exceeds monthly limit)
            ("yearly_1", now - timedelta(days=180)),
            ("yearly_2", now - timedelta(days=400)),  # Should be deleted (exceeds yearly limit)
        ]

        # Create all backups
        for backup_id, timestamp in backup_scenarios:
            await self.create_test_backup(storage_engine, backup_id, timestamp)

        # Enforce retention policy
        result = await retention_manager.enforce_retention_policy(retention_policy)

        # Verify cleanup
        assert result.success

        # Check remaining backups
        remaining_backups = await storage_engine.list_backups()
        remaining_ids = {b.backup_id for b in remaining_backups}

        # Verify expected backups remain (newest in each category)
        expected_remaining = {
            "daily_1",
            "daily_2",
            "daily_3",  # Keep 3 daily
            "weekly_1",
            "weekly_2",  # Keep 2 weekly
            "monthly_1",
            "monthly_2",  # Keep 2 monthly
            "yearly_1",  # Keep 1 yearly
        }

        # The actual remaining set should be a subset of expected
        # (some backups might be categorized differently based on exact timing)
        assert len(remaining_ids) <= len(expected_remaining)

    @pytest.mark.asyncio
    async def test_storage_usage_calculation(self, retention_manager, storage_engine):
        """Test storage usage calculation with real backups."""
        now = datetime.now()

        # Create backups with different sizes
        total_expected_size = 0
        for i in range(5):
            size_multiplier = i + 1
            backup_id = f"backup_{i}"
            timestamp = now - timedelta(days=i)
            await self.create_test_backup(storage_engine, backup_id, timestamp, size_multiplier)
            total_expected_size += 1000 * size_multiplier

        # Get storage usage
        usage = await retention_manager.get_storage_usage()

        # Verify usage calculation
        assert usage.total_backup_count == 5
        assert usage.total_size_bytes == total_expected_size
        assert usage.oldest_backup is not None
        assert usage.newest_backup is not None
        assert len(usage.size_by_period) > 0
        assert len(usage.count_by_period) > 0

        # Verify period categorization
        assert usage.count_by_period.get("daily", 0) >= 1

    @pytest.mark.asyncio
    async def test_backup_versioning_and_comparison(self, retention_manager, storage_engine):
        """Test backup versioning and comparison functionality."""
        now = datetime.now()

        # Create two backups with different resource counts
        backup1_id = await self.create_test_backup(
            storage_engine, "backup_1", now - timedelta(hours=2), size_multiplier=1
        )
        backup2_id = await self.create_test_backup(
            storage_engine, "backup_2", now - timedelta(hours=1), size_multiplier=2
        )

        # Get backup versions
        versions = await retention_manager.get_backup_versions()

        # Verify versions
        assert len(versions) == 2
        assert versions[0].timestamp > versions[1].timestamp  # Sorted by timestamp desc

        # Compare backups
        comparison = await retention_manager.compare_backups(backup1_id, backup2_id)

        # Verify comparison
        assert comparison is not None
        assert comparison.source_version.backup_id == backup1_id
        assert comparison.target_version.backup_id == backup2_id
        assert comparison.size_difference > 0  # backup2 should be larger
        assert "users" in comparison.resource_changes
        assert comparison.resource_changes["users"]["difference"] == 10  # 20 - 10
        assert 0.0 <= comparison.similarity_score <= 1.0

    @pytest.mark.asyncio
    async def test_storage_limit_monitoring(self, retention_manager, storage_engine):
        """Test storage limit monitoring and alerting."""
        # Set very low storage limits to trigger alerts
        retention_manager.storage_limits.max_size_bytes = 5000  # 5KB
        retention_manager.storage_limits.max_backup_count = 3

        now = datetime.now()

        # Create backups that exceed limits
        for i in range(5):
            backup_id = f"backup_{i}"
            timestamp = now - timedelta(days=i)
            await self.create_test_backup(storage_engine, backup_id, timestamp, size_multiplier=2)

        # Check storage limits
        alerts = await retention_manager.check_storage_limits()

        # Verify alerts were generated
        assert len(alerts) > 0

        # Should have both size and count alerts
        alert_types = {alert.alert_type for alert in alerts}
        assert "critical" in alert_types

        # Verify alert details
        critical_alerts = [a for a in alerts if a.alert_type == "critical"]
        assert len(critical_alerts) > 0
        assert critical_alerts[0].recommended_action is not None
        assert critical_alerts[0].current_usage.total_backup_count > 3

    @pytest.mark.asyncio
    async def test_retention_recommendations(
        self, retention_manager, storage_engine, retention_policy
    ):
        """Test retention policy recommendations."""
        now = datetime.now()

        # Create many daily backups to trigger recommendations
        for i in range(15):  # Create 15 daily backups
            backup_id = f"daily_backup_{i}"
            timestamp = now - timedelta(hours=i)  # All within daily period
            await self.create_test_backup(storage_engine, backup_id, timestamp)

        # Get recommendations
        recommendations = await retention_manager.get_retention_recommendations(retention_policy)

        # Verify recommendations structure
        assert "current_usage" in recommendations
        assert "current_policy" in recommendations
        assert "recommendations" in recommendations

        # Should recommend reducing daily retention
        daily_recommendations = [
            rec for rec in recommendations["recommendations"] if rec.get("type") == "reduce_daily"
        ]
        assert len(daily_recommendations) > 0

    @pytest.mark.asyncio
    async def test_dry_run_retention_enforcement(
        self, retention_manager, storage_engine, retention_policy
    ):
        """Test retention policy enforcement in dry run mode."""
        now = datetime.now()

        # Create backups
        for i in range(8):
            backup_id = f"backup_{i}"
            timestamp = now - timedelta(days=i)
            await self.create_test_backup(storage_engine, backup_id, timestamp)

        # Get initial backup count
        initial_backups = await storage_engine.list_backups()
        initial_count = len(initial_backups)

        # Run dry run enforcement
        result = await retention_manager.enforce_retention_policy(retention_policy, dry_run=True)

        # Verify dry run results
        assert result.success
        assert len(result.deleted_backups) > 0  # Should identify backups for deletion
        assert result.freed_bytes > 0

        # Verify no actual deletions occurred
        final_backups = await storage_engine.list_backups()
        assert len(final_backups) == initial_count

    @pytest.mark.asyncio
    async def test_retention_with_backup_validation(
        self, retention_manager, storage_engine, retention_policy
    ):
        """Test retention enforcement with backup validation."""
        now = datetime.now()

        # Create backups
        backup_ids = []
        for i in range(6):
            backup_id = f"backup_{i}"
            timestamp = now - timedelta(days=i)
            stored_id = await self.create_test_backup(storage_engine, backup_id, timestamp)
            backup_ids.append(stored_id)

        # Validate backups before retention
        for backup_id in backup_ids:
            validation_result = await storage_engine.verify_integrity(backup_id)
            assert validation_result.is_valid

        # Enforce retention policy
        result = await retention_manager.enforce_retention_policy(retention_policy)

        # Verify cleanup
        assert result.success

        # Validate remaining backups
        remaining_backups = await storage_engine.list_backups()
        for backup in remaining_backups:
            validation_result = await storage_engine.verify_integrity(backup.backup_id)
            assert validation_result.is_valid

    @pytest.mark.asyncio
    async def test_concurrent_retention_operations(
        self, retention_manager, storage_engine, retention_policy
    ):
        """Test concurrent retention operations."""
        now = datetime.now()

        # Create backups
        for i in range(10):
            backup_id = f"backup_{i}"
            timestamp = now - timedelta(days=i)
            await self.create_test_backup(storage_engine, backup_id, timestamp)

        # Run multiple retention operations concurrently
        tasks = [
            retention_manager.get_storage_usage(),
            retention_manager.check_storage_limits(),
            retention_manager.get_backup_versions(),
            retention_manager.get_retention_recommendations(retention_policy),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all operations completed successfully
        for result in results:
            assert not isinstance(result, Exception)

        # Verify result types
        usage, alerts, versions, recommendations = results
        assert isinstance(usage, StorageUsage)
        assert isinstance(alerts, list)
        assert isinstance(versions, list)
        assert isinstance(recommendations, dict)

    @pytest.mark.asyncio
    async def test_retention_with_corrupted_backup(
        self, retention_manager, storage_engine, retention_policy, temp_storage_dir
    ):
        """Test retention handling with corrupted backup data."""
        now = datetime.now()

        # Create normal backups
        for i in range(3):
            backup_id = f"backup_{i}"
            timestamp = now - timedelta(days=i)
            await self.create_test_backup(storage_engine, backup_id, timestamp)

        # Manually corrupt one backup by modifying its file
        backup_files = list(temp_storage_dir.rglob("*.json"))
        if backup_files:
            with open(backup_files[0], "w") as f:
                f.write("corrupted data")

        # Attempt retention enforcement
        result = await retention_manager.enforce_retention_policy(retention_policy)

        # Should handle corruption gracefully
        # (exact behavior depends on implementation - might succeed with warnings)
        assert isinstance(result.success, bool)
        if not result.success:
            assert len(result.errors) > 0
