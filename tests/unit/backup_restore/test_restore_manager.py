"""
Unit tests for RestoreManager and related components.

Tests cover restore operations, conflict resolution, compatibility validation,
and dry-run preview functionality.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupType,
    ConflictInfo,
    ConflictStrategy,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    ResourceType,
    RestoreOptions,
    RetentionPolicy,
    UserData,
    ValidationResult,
)
from src.awsideman.backup_restore.restore_manager import (
    CompatibilityValidator,
    ConflictResolver,
    RestoreManager,
    RestoreProcessor,
)


class TestConflictResolver:
    """Test cases for ConflictResolver."""

    def test_init(self):
        """Test ConflictResolver initialization."""
        resolver = ConflictResolver(ConflictStrategy.OVERWRITE)
        assert resolver.strategy == ConflictStrategy.OVERWRITE
        assert resolver._user_responses == {}

    @pytest.mark.asyncio
    async def test_resolve_conflict_overwrite(self):
        """Test conflict resolution with overwrite strategy."""
        resolver = ConflictResolver(ConflictStrategy.OVERWRITE)

        conflict = ConflictInfo(
            resource_type=ResourceType.USERS,
            resource_id="test-user",
            conflict_type="user_exists",
            existing_value={"name": "old"},
            new_value={"name": "new"},
            suggested_action="overwrite",
        )

        action = await resolver.resolve_conflict(conflict)
        assert action == "overwrite"

    @pytest.mark.asyncio
    async def test_resolve_conflict_skip(self):
        """Test conflict resolution with skip strategy."""
        resolver = ConflictResolver(ConflictStrategy.SKIP)

        conflict = ConflictInfo(
            resource_type=ResourceType.USERS,
            resource_id="test-user",
            conflict_type="user_exists",
            existing_value={"name": "old"},
            new_value={"name": "new"},
            suggested_action="overwrite",
        )

        action = await resolver.resolve_conflict(conflict)
        assert action == "skip"

    @pytest.mark.asyncio
    async def test_resolve_conflict_merge_user(self):
        """Test conflict resolution with merge strategy for users."""
        resolver = ConflictResolver(ConflictStrategy.MERGE)

        # Test case where new email differs - should overwrite
        conflict = ConflictInfo(
            resource_type=ResourceType.USERS,
            resource_id="test-user",
            conflict_type="user_exists",
            existing_value={"email": "old@example.com", "display_name": "Old Name"},
            new_value={"email": "new@example.com", "display_name": "New Name"},
            suggested_action="merge",
        )

        action = await resolver.resolve_conflict(conflict)
        assert action == "overwrite"

        # Test case where email is same - should skip
        conflict.existing_value = {"email": "same@example.com"}
        conflict.new_value = {"email": "same@example.com"}

        action = await resolver.resolve_conflict(conflict)
        assert action == "skip"

    @pytest.mark.asyncio
    async def test_resolve_conflict_merge_group(self):
        """Test conflict resolution with merge strategy for groups."""
        resolver = ConflictResolver(ConflictStrategy.MERGE)

        # Test case where description differs - should overwrite
        conflict = ConflictInfo(
            resource_type=ResourceType.GROUPS,
            resource_id="test-group",
            conflict_type="group_exists",
            existing_value={"description": "Old description"},
            new_value={"description": "New description"},
            suggested_action="merge",
        )

        action = await resolver.resolve_conflict(conflict)
        assert action == "overwrite"

    @pytest.mark.asyncio
    async def test_resolve_conflict_prompt(self):
        """Test conflict resolution with prompt strategy."""
        resolver = ConflictResolver(ConflictStrategy.PROMPT)

        conflict = ConflictInfo(
            resource_type=ResourceType.USERS,
            resource_id="test-user",
            conflict_type="user_exists",
            existing_value={"name": "old"},
            new_value={"name": "new"},
            suggested_action="overwrite",
        )

        action = await resolver.resolve_conflict(conflict)
        assert action == "overwrite"  # Should use suggested action

        # Test caching of user responses
        action2 = await resolver.resolve_conflict(conflict)
        assert action2 == "overwrite"  # Should use cached response


class TestCompatibilityValidator:
    """Test cases for CompatibilityValidator."""

    def setup_method(self):
        """Set up test fixtures."""
        self.identity_center_client = AsyncMock()
        self.identity_store_client = AsyncMock()
        self.validator = CompatibilityValidator(
            self.identity_center_client, self.identity_store_client
        )

    @pytest.mark.asyncio
    async def test_validate_compatibility_success(self):
        """Test successful compatibility validation."""
        # Mock instance access
        self.identity_center_client.describe_instance.return_value = {
            "InstanceArn": "arn:aws:sso:::instance/test",
            "Status": "ACTIVE",
        }

        # Mock permission sets
        self.identity_center_client.list_permission_sets.return_value = {"PermissionSets": []}

        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")],
            permission_sets=[
                PermissionSetData(
                    permission_set_arn="arn:aws:sso:::permissionSet/test",
                    name="TestPS",
                    managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                )
            ],
        )

        result = await self.validator.validate_compatibility(
            backup_data, "arn:aws:sso:::instance/target"
        )

        assert result.is_valid
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_compatibility_instance_access_failure(self):
        """Test compatibility validation with instance access failure."""
        # Mock instance access failure
        self.identity_center_client.describe_instance.side_effect = Exception("Access denied")

        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            )
        )

        result = await self.validator.validate_compatibility(
            backup_data, "arn:aws:sso:::instance/target"
        )

        assert not result.is_valid
        assert len(result.errors) > 0
        assert "Cannot access target instance" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_limits_warnings(self):
        """Test validation warnings for large datasets."""
        # Create backup with large number of resources
        users = [UserData(user_id=f"u{i}", user_name=f"user{i}") for i in range(45000)]
        groups = [GroupData(group_id=f"g{i}", display_name=f"group{i}") for i in range(9000)]
        permission_sets = [
            PermissionSetData(
                permission_set_arn=f"arn:aws:sso:::permissionSet/ps{i}", name=f"PS{i}"
            )
            for i in range(450)
        ]

        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=users,
            groups=groups,
            permission_sets=permission_sets,
        )

        # Mock successful instance access
        self.identity_center_client.describe_instance.return_value = {
            "InstanceArn": "arn:aws:sso:::instance/test"
        }
        self.identity_center_client.list_permission_sets.return_value = {"PermissionSets": []}

        result = await self.validator.validate_compatibility(
            backup_data, "arn:aws:sso:::instance/target"
        )

        assert result.is_valid  # Should still be valid but with warnings
        assert (
            len(result.warnings) >= 3
        )  # Should have warnings for users, groups, and permission sets


class TestRestoreProcessor:
    """Test cases for RestoreProcessor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.identity_center_client = AsyncMock()
        self.identity_store_client = AsyncMock()
        self.conflict_resolver = AsyncMock()
        self.processor = RestoreProcessor(
            self.identity_center_client, self.identity_store_client, self.conflict_resolver
        )

    @pytest.mark.asyncio
    async def test_process_restore_dry_run(self):
        """Test restore processing in dry-run mode."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")],
            groups=[GroupData(group_id="g1", display_name="group1")],
        )

        options = RestoreOptions(target_resources=[ResourceType.ALL], dry_run=True)

        result = await self.processor.process_restore(backup_data, options)

        assert result.success
        assert result.changes_applied["users"] == 1
        assert result.changes_applied["groups"] == 1
        # Should not have called any AWS APIs in dry-run mode
        self.identity_center_client.assert_not_called()
        self.identity_store_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_restore_selective_resources(self):
        """Test restore processing with selective resource types."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")],
            groups=[GroupData(group_id="g1", display_name="group1")],
        )

        options = RestoreOptions(target_resources=[ResourceType.USERS], dry_run=True)  # Only users

        result = await self.processor.process_restore(backup_data, options)

        assert result.success
        assert result.changes_applied["users"] == 1
        assert "groups" not in result.changes_applied

    def test_calculate_total_steps(self):
        """Test calculation of total steps for progress reporting."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")] * 5,
            groups=[GroupData(group_id="g1", display_name="group1")] * 3,
        )

        options = RestoreOptions(target_resources=[ResourceType.ALL])
        total = self.processor._calculate_total_steps(backup_data, options)
        assert total == 8  # 5 users + 3 groups

        options = RestoreOptions(target_resources=[ResourceType.USERS])
        total = self.processor._calculate_total_steps(backup_data, options)
        assert total == 5  # Only users


class TestRestoreManager:
    """Test cases for RestoreManager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.storage_engine = AsyncMock()
        self.identity_center_client = AsyncMock()
        self.identity_store_client = AsyncMock()
        self.progress_reporter = AsyncMock()

        self.restore_manager = RestoreManager(
            self.storage_engine,
            self.identity_center_client,
            self.identity_store_client,
            self.progress_reporter,
        )

    @pytest.mark.asyncio
    async def test_restore_backup_success(self):
        """Test successful backup restoration."""
        # Mock backup data
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")],
        )

        # Mock storage engine
        self.storage_engine.retrieve_backup.return_value = backup_data

        # Mock compatibility validation
        with patch.object(
            self.restore_manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = ValidationResult(is_valid=True)

            options = RestoreOptions(dry_run=True)
            result = await self.restore_manager.restore_backup("test-backup", options)

        assert result.success
        assert len(result.errors) == 0
        self.storage_engine.retrieve_backup.assert_called_once_with("test-backup")

    @pytest.mark.asyncio
    async def test_restore_backup_not_found(self):
        """Test restore operation when backup is not found."""
        self.storage_engine.retrieve_backup.return_value = None

        options = RestoreOptions()
        result = await self.restore_manager.restore_backup("nonexistent-backup", options)

        assert not result.success
        assert "not found" in result.message.lower()
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_restore_backup_integrity_failure(self):
        """Test restore operation when backup integrity check fails."""
        # Mock backup data with failed integrity check
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            )
        )

        # Mock integrity check failure
        with patch.object(backup_data, "verify_integrity", return_value=False):
            self.storage_engine.retrieve_backup.return_value = backup_data

            options = RestoreOptions()
            result = await self.restore_manager.restore_backup("test-backup", options)

        assert not result.success
        assert "integrity" in result.message.lower()

    @pytest.mark.asyncio
    async def test_restore_backup_compatibility_failure(self):
        """Test restore operation when compatibility validation fails."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            )
        )

        self.storage_engine.retrieve_backup.return_value = backup_data

        # Mock compatibility validation failure
        with patch.object(
            self.restore_manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = ValidationResult(
                is_valid=False, errors=["Incompatible instance version"]
            )

            options = RestoreOptions()
            result = await self.restore_manager.restore_backup("test-backup", options)

        assert not result.success
        assert "compatibility" in result.message.lower()
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_restore_backup_skip_validation(self):
        """Test restore operation with validation skipped."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")],
        )

        self.storage_engine.retrieve_backup.return_value = backup_data

        options = RestoreOptions(skip_validation=True, dry_run=True)

        with patch.object(
            self.restore_manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            result = await self.restore_manager.restore_backup("test-backup", options)

            assert result.success
            # Compatibility validation should not have been called
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_preview_restore_success(self):
        """Test successful restore preview generation."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")] * 3,
            groups=[GroupData(group_id="g1", display_name="group1")] * 2,
        )

        self.storage_engine.retrieve_backup.return_value = backup_data

        options = RestoreOptions(target_resources=[ResourceType.ALL])
        preview = await self.restore_manager.preview_restore("test-backup", options)

        assert preview.changes_summary["users"] == 3
        assert preview.changes_summary["groups"] == 2
        assert preview.estimated_duration is not None
        assert preview.estimated_duration.total_seconds() > 0

    @pytest.mark.asyncio
    async def test_preview_restore_selective_resources(self):
        """Test restore preview with selective resource types."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            ),
            users=[UserData(user_id="u1", user_name="user1")] * 3,
            groups=[GroupData(group_id="g1", display_name="group1")] * 2,
        )

        self.storage_engine.retrieve_backup.return_value = backup_data

        options = RestoreOptions(target_resources=[ResourceType.USERS])
        preview = await self.restore_manager.preview_restore("test-backup", options)

        assert preview.changes_summary["users"] == 3
        assert "groups" not in preview.changes_summary

    @pytest.mark.asyncio
    async def test_preview_restore_backup_not_found(self):
        """Test restore preview when backup is not found."""
        self.storage_engine.retrieve_backup.return_value = None

        options = RestoreOptions()
        preview = await self.restore_manager.preview_restore("nonexistent-backup", options)

        assert len(preview.warnings) > 0
        assert "not found" in preview.warnings[0].lower()

    @pytest.mark.asyncio
    async def test_validate_compatibility_success(self):
        """Test successful compatibility validation."""
        backup_data = BackupData(
            metadata=BackupMetadata(
                backup_id="test-backup",
                timestamp=datetime.now(),
                instance_arn="arn:aws:sso:::instance/source",
                backup_type=BackupType.FULL,
                version="1.0",
                source_account="123456789012",
                source_region="us-east-1",
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(),
            )
        )

        self.storage_engine.retrieve_backup.return_value = backup_data

        with patch.object(
            self.restore_manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = ValidationResult(is_valid=True)

            result = await self.restore_manager.validate_compatibility(
                "test-backup", "arn:aws:sso:::instance/target"
            )

        assert result.is_valid
        mock_validate.assert_called_once_with(backup_data, "arn:aws:sso:::instance/target")

    @pytest.mark.asyncio
    async def test_validate_compatibility_backup_not_found(self):
        """Test compatibility validation when backup is not found."""
        self.storage_engine.retrieve_backup.return_value = None

        result = await self.restore_manager.validate_compatibility(
            "nonexistent-backup", "arn:aws:sso:::instance/target"
        )

        assert not result.is_valid
        assert len(result.errors) > 0
        assert "not found" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_analyze_changes_large_datasets(self):
        """Test change analysis with large datasets generates warnings."""
        # Test users
        users = [UserData(user_id=f"u{i}", user_name=f"user{i}") for i in range(150)]
        analysis = await self.restore_manager._analyze_user_changes(users)
        assert analysis["changes"] == 150
        assert len(analysis["warnings"]) > 0
        assert "Large number of users" in analysis["warnings"][0]

        # Test groups
        groups = [GroupData(group_id=f"g{i}", display_name=f"group{i}") for i in range(60)]
        analysis = await self.restore_manager._analyze_group_changes(groups)
        assert analysis["changes"] == 60
        assert len(analysis["warnings"]) > 0
        assert "Large number of groups" in analysis["warnings"][0]

        # Test permission sets
        permission_sets = [
            PermissionSetData(
                permission_set_arn=f"arn:aws:sso:::permissionSet/ps{i}", name=f"PS{i}"
            )
            for i in range(25)
        ]
        analysis = await self.restore_manager._analyze_permission_set_changes(permission_sets)
        assert analysis["changes"] == 25
        assert len(analysis["warnings"]) > 0
        assert "Large number of permission sets" in analysis["warnings"][0]

        # Test assignments
        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn=f"arn:aws:sso:::permissionSet/ps{i}",
                principal_type="USER",
                principal_id=f"user{i}",
            )
            for i in range(1500)
        ]
        analysis = await self.restore_manager._analyze_assignment_changes(assignments)
        assert analysis["changes"] == 1500
        assert len(analysis["warnings"]) > 0
        assert "Large number of assignments" in analysis["warnings"][0]


@pytest.fixture
def sample_backup_data():
    """Fixture providing sample backup data for tests."""
    return BackupData(
        metadata=BackupMetadata(
            backup_id="test-backup-123",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
            backup_type=BackupType.FULL,
            version="1.0.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        ),
        users=[
            UserData(
                user_id="user-1",
                user_name="john.doe",
                display_name="John Doe",
                email="john.doe@example.com",
            ),
            UserData(
                user_id="user-2",
                user_name="jane.smith",
                display_name="Jane Smith",
                email="jane.smith@example.com",
            ),
        ],
        groups=[
            GroupData(
                group_id="group-1",
                display_name="Developers",
                description="Development team",
                members=["user-1", "user-2"],
            )
        ],
        permission_sets=[
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ps-1234567890abcdef",
                name="DeveloperAccess",
                description="Developer access permissions",
                managed_policies=["arn:aws:iam::aws:policy/PowerUserAccess"],
            )
        ],
        assignments=[
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ps-1234567890abcdef",
                principal_type="GROUP",
                principal_id="group-1",
            )
        ],
    )


@pytest.fixture
def sample_restore_options():
    """Fixture providing sample restore options for tests."""
    return RestoreOptions(
        target_resources=[ResourceType.ALL],
        conflict_strategy=ConflictStrategy.PROMPT,
        dry_run=False,
        target_account=None,
        target_region=None,
        target_instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
        resource_mappings={},
        skip_validation=False,
    )


class TestRestoreManagerIntegration:
    """Integration tests for RestoreManager with sample data."""

    def setup_method(self):
        """Set up test fixtures."""
        self.storage_engine = AsyncMock()
        self.identity_center_client = AsyncMock()
        self.identity_store_client = AsyncMock()

        self.restore_manager = RestoreManager(
            self.storage_engine, self.identity_center_client, self.identity_store_client
        )

    @pytest.mark.asyncio
    async def test_full_restore_workflow(self, sample_backup_data, sample_restore_options):
        """Test complete restore workflow with sample data."""
        # Mock storage engine to return sample backup
        self.storage_engine.retrieve_backup.return_value = sample_backup_data

        # Mock compatibility validation
        with patch.object(
            self.restore_manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = ValidationResult(is_valid=True)

            # Set dry run to avoid actual AWS API calls
            sample_restore_options.dry_run = True

            result = await self.restore_manager.restore_backup(
                sample_backup_data.metadata.backup_id, sample_restore_options
            )

        assert result.success
        assert result.changes_applied["users"] == 2
        assert result.changes_applied["groups"] == 1
        assert result.changes_applied["permission_sets"] == 1
        assert result.changes_applied["assignments"] == 1
        assert result.duration is not None

    @pytest.mark.asyncio
    async def test_preview_with_conflicts(self, sample_backup_data):
        """Test restore preview that identifies potential conflicts."""
        self.storage_engine.retrieve_backup.return_value = sample_backup_data

        options = RestoreOptions(target_resources=[ResourceType.ALL])
        preview = await self.restore_manager.preview_restore(
            sample_backup_data.metadata.backup_id, options
        )

        assert preview.changes_summary["users"] == 2
        assert preview.changes_summary["groups"] == 1
        assert preview.changes_summary["permission_sets"] == 1
        assert preview.changes_summary["assignments"] == 1
        assert preview.estimated_duration.total_seconds() > 0

    @pytest.mark.asyncio
    async def test_selective_restore_users_only(self, sample_backup_data):
        """Test selective restore of only users."""
        self.storage_engine.retrieve_backup.return_value = sample_backup_data

        with patch.object(
            self.restore_manager.compatibility_validator, "validate_compatibility"
        ) as mock_validate:
            mock_validate.return_value = ValidationResult(is_valid=True)

            options = RestoreOptions(target_resources=[ResourceType.USERS], dry_run=True)

            result = await self.restore_manager.restore_backup(
                sample_backup_data.metadata.backup_id, options
            )

        assert result.success
        assert result.changes_applied["users"] == 2
        assert "groups" not in result.changes_applied
        assert "permission_sets" not in result.changes_applied
        assert "assignments" not in result.changes_applied
