"""
Unit tests for format conversion functionality.

This module tests the detailed format conversion capabilities including
edge cases, error handling, and data integrity validation.
"""

import json
from datetime import datetime

import pytest

from src.awsideman.backup_restore.export_import import ExportImportError, FormatConverter
from src.awsideman.backup_restore.models import (
    AssignmentData,
    BackupData,
    BackupMetadata,
    BackupType,
    EncryptionMetadata,
    GroupData,
    PermissionSetData,
    RelationshipMap,
    RetentionPolicy,
    UserData,
)

# YAML availability check removed as it's not used in this test file


class TestFormatConversionEdgeCases:
    """Test edge cases and error conditions in format conversion."""

    @pytest.fixture
    def format_converter(self):
        """Create format converter instance."""
        return FormatConverter()

    @pytest.fixture
    def minimal_backup_data(self):
        """Create minimal backup data for testing."""
        metadata = BackupMetadata(
            backup_id="minimal-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        return BackupData(
            metadata=metadata,
            users=[],
            groups=[],
            permission_sets=[],
            assignments=[],
            relationships=RelationshipMap(),
        )

    @pytest.fixture
    def complex_backup_data(self):
        """Create complex backup data with all resource types."""
        metadata = BackupMetadata(
            backup_id="complex-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        users = [
            UserData(
                user_id="user-1",
                user_name="user1",
                display_name="User One",
                email="user1@example.com",
                given_name="User",
                family_name="One",
                active=True,
                external_ids={"external": "ext-1", "another": "ext-2"},
            ),
            UserData(
                user_id="user-2",
                user_name="user2",
                display_name=None,  # Test None values
                email=None,
                given_name=None,
                family_name=None,
                active=False,
                external_ids={},
            ),
        ]

        groups = [
            GroupData(
                group_id="group-1",
                display_name="Group One",
                description="First test group",
                members=["user-1", "user-2"],
            ),
            GroupData(
                group_id="group-2",
                display_name="Group Two",
                description=None,  # Test None description
                members=[],
            ),
        ]

        permission_sets = [
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-1",
                name="PermissionSet1",
                description="First permission set",
                session_duration="PT2H",
                relay_state="https://example.com",
                inline_policy='{"Version": "2012-10-17", "Statement": []}',
                managed_policies=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                customer_managed_policies=[{"Name": "CustomPolicy", "Path": "/"}],
                permissions_boundary={"Type": "CustomerManagedPolicy", "Name": "BoundaryPolicy"},
            ),
            PermissionSetData(
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-2",
                name="PermissionSet2",
                description=None,
                session_duration=None,
                relay_state=None,
                inline_policy=None,
                managed_policies=[],
                customer_managed_policies=[],
                permissions_boundary=None,
            ),
        ]

        assignments = [
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-1",
                principal_type="USER",
                principal_id="user-1",
            ),
            AssignmentData(
                account_id="123456789012",
                permission_set_arn="arn:aws:sso:::permissionSet/ssoins-123/ps-1",
                principal_type="GROUP",
                principal_id="group-1",
            ),
        ]

        relationships = RelationshipMap(
            user_groups={"user-1": ["group-1"], "user-2": ["group-1"]},
            group_members={"group-1": ["user-1", "user-2"], "group-2": []},
            permission_set_assignments={
                "arn:aws:sso:::permissionSet/ssoins-123/ps-1": ["assignment-1", "assignment-2"]
            },
        )

        return BackupData(
            metadata=metadata,
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
            relationships=relationships,
        )

    @pytest.mark.asyncio
    async def test_json_conversion_with_none_values(self, format_converter, complex_backup_data):
        """Test JSON conversion handles None values correctly."""
        json_result = await format_converter.convert_to_json(complex_backup_data)

        # Parse back to verify None values are handled
        parsed_data = json.loads(json_result)

        # Check that None values are preserved as null in JSON
        user_2 = parsed_data["users"][1]
        assert user_2["display_name"] is None
        assert user_2["email"] is None

        # Convert back and verify
        restored_data = await format_converter.convert_from_json(json_result)
        assert restored_data.users[1].display_name is None
        assert restored_data.users[1].email is None

    @pytest.mark.asyncio
    async def test_json_conversion_with_empty_collections(
        self, format_converter, minimal_backup_data
    ):
        """Test JSON conversion with empty collections."""
        json_result = await format_converter.convert_to_json(minimal_backup_data)
        parsed_data = json.loads(json_result)

        assert parsed_data["users"] == []
        assert parsed_data["groups"] == []
        assert parsed_data["permission_sets"] == []
        assert parsed_data["assignments"] == []

        # Convert back and verify
        restored_data = await format_converter.convert_from_json(json_result)
        assert len(restored_data.users) == 0
        assert len(restored_data.groups) == 0

    @pytest.mark.asyncio
    async def test_csv_conversion_with_special_characters(self, format_converter):
        """Test CSV conversion handles special characters correctly."""
        metadata = BackupMetadata(
            backup_id="special-chars-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        users = [
            UserData(
                user_id="user-1",
                user_name="user,with,commas",
                display_name='User "with quotes"',
                email="user@example.com",
                given_name="User\nwith\nnewlines",
                family_name="User\twith\ttabs",
            )
        ]

        backup_data = BackupData(
            metadata=metadata, users=users, groups=[], permission_sets=[], assignments=[]
        )

        csv_result = await format_converter.convert_to_csv(backup_data)

        # Verify CSV escaping
        users_csv = csv_result["users"]
        assert '"user,with,commas"' in users_csv or "user,with,commas" in users_csv
        assert '"User ""with quotes"""' in users_csv or 'User "with quotes"' in users_csv

        # Convert back and verify data integrity
        restored_data = await format_converter.convert_from_csv(csv_result)
        assert restored_data.users[0].user_name == "user,with,commas"
        assert restored_data.users[0].display_name == 'User "with quotes"'

    @pytest.mark.asyncio
    async def test_csv_conversion_with_json_fields(self, format_converter, complex_backup_data):
        """Test CSV conversion handles JSON fields correctly."""
        csv_result = await format_converter.convert_to_csv(complex_backup_data)

        # Verify JSON fields are properly serialized (may be CSV-escaped)
        users_csv = csv_result["users"]
        assert "ext-1" in users_csv and "ext-2" in users_csv

        permission_sets_csv = csv_result["permission_sets"]
        assert "arn:aws:iam::aws:policy/ReadOnlyAccess" in permission_sets_csv

        # Convert back and verify
        restored_data = await format_converter.convert_from_csv(csv_result)
        assert restored_data.users[0].external_ids == {"external": "ext-1", "another": "ext-2"}
        assert restored_data.permission_sets[0].managed_policies == [
            "arn:aws:iam::aws:policy/ReadOnlyAccess"
        ]

    @pytest.mark.asyncio
    async def test_csv_conversion_malformed_json_fields(self, format_converter):
        """Test CSV conversion handles malformed JSON fields gracefully."""
        csv_data = {
            "users": "user_id,user_name,display_name,email,given_name,family_name,active,external_ids\nuser-1,testuser,Test User,test@example.com,Test,User,True,{malformed json}",
            "groups": "group_id,display_name,description,members\n",
            "permission_sets": "permission_set_arn,name,description,session_duration,relay_state,inline_policy,managed_policies,customer_managed_policies,permissions_boundary\n",
            "assignments": "account_id,permission_set_arn,principal_type,principal_id\n",
            "metadata": "key,value\nbackup_id,test-backup\ntimestamp,2023-01-01T00:00:00\ninstance_arn,arn:aws:sso:::instance/ssoins-123\nbackup_type,full\nversion,1.0\nsource_account,123456789012\nsource_region,us-east-1\nretention_policy,{}\nencryption_info,{}\nresource_counts,{}\nsize_bytes,0\nchecksum,abc123",
        }

        # Should not raise exception, but external_ids should be empty
        restored_data = await format_converter.convert_from_csv(csv_data)
        assert restored_data.users[0].external_ids == {}

    @pytest.mark.asyncio
    async def test_json_conversion_with_datetime_serialization(
        self, format_converter, complex_backup_data
    ):
        """Test JSON conversion properly serializes datetime objects."""
        json_result = await format_converter.convert_to_json(complex_backup_data)
        parsed_data = json.loads(json_result)

        # Verify timestamp is serialized as ISO format string
        timestamp_str = parsed_data["metadata"]["timestamp"]
        assert isinstance(timestamp_str, str)
        assert "T" in timestamp_str  # ISO format contains 'T'

        # Verify it can be parsed back
        restored_data = await format_converter.convert_from_json(json_result)
        assert isinstance(restored_data.metadata.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_yaml_conversion_with_unicode(self, format_converter):
        """Test YAML conversion handles Unicode characters correctly."""
        metadata = BackupMetadata(
            backup_id="unicode-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        users = [
            UserData(
                user_id="user-1",
                user_name="用户",  # Chinese characters
                display_name="Пользователь",  # Cyrillic characters
                email="user@例え.テスト",  # Japanese domain
                given_name="José",  # Accented characters
                family_name="Müller",  # German umlaut
            )
        ]

        backup_data = BackupData(
            metadata=metadata, users=users, groups=[], permission_sets=[], assignments=[]
        )

        yaml_result = await format_converter.convert_to_yaml(backup_data)

        # Verify Unicode characters are preserved
        assert "用户" in yaml_result
        assert "Пользователь" in yaml_result
        assert "José" in yaml_result
        assert "Müller" in yaml_result

        # Convert back and verify
        restored_data = await format_converter.convert_from_yaml(yaml_result)
        assert restored_data.users[0].user_name == "用户"
        assert restored_data.users[0].display_name == "Пользователь"
        assert restored_data.users[0].given_name == "José"
        assert restored_data.users[0].family_name == "Müller"

    @pytest.mark.asyncio
    async def test_json_conversion_large_data(self, format_converter):
        """Test JSON conversion with large datasets."""
        metadata = BackupMetadata(
            backup_id="large-backup",
            timestamp=datetime.now(),
            instance_arn="arn:aws:sso:::instance/ssoins-123456789",
            backup_type=BackupType.FULL,
            version="1.0",
            source_account="123456789012",
            source_region="us-east-1",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        # Create large dataset
        users = [
            UserData(
                user_id=f"user-{i}",
                user_name=f"user{i}",
                display_name=f"User {i}",
                email=f"user{i}@example.com",
            )
            for i in range(1000)
        ]

        backup_data = BackupData(
            metadata=metadata, users=users, groups=[], permission_sets=[], assignments=[]
        )

        # Should handle large datasets without issues
        json_result = await format_converter.convert_to_json(backup_data)
        assert len(json_result) > 0

        # Verify data integrity
        restored_data = await format_converter.convert_from_json(json_result)
        assert len(restored_data.users) == 1000
        assert restored_data.users[999].user_name == "user999"

    @pytest.mark.asyncio
    async def test_csv_metadata_conversion_complex_types(
        self, format_converter, complex_backup_data
    ):
        """Test CSV metadata conversion with complex nested types."""
        csv_result = await format_converter.convert_to_csv(complex_backup_data)
        metadata_csv = csv_result["metadata"]

        # Verify complex types are JSON-serialized in metadata CSV
        assert "retention_policy" in metadata_csv
        assert "encryption_info" in metadata_csv

        # Convert back and verify
        restored_data = await format_converter.convert_from_csv(csv_result)
        assert isinstance(restored_data.metadata.retention_policy, RetentionPolicy)
        assert isinstance(restored_data.metadata.encryption_info, EncryptionMetadata)

    @pytest.mark.asyncio
    async def test_format_conversion_round_trip_integrity(
        self, format_converter, complex_backup_data
    ):
        """Test that round-trip conversion preserves data integrity."""
        # JSON round-trip
        json_result = await format_converter.convert_to_json(complex_backup_data)
        json_restored = await format_converter.convert_from_json(json_result)

        assert json_restored.metadata.backup_id == complex_backup_data.metadata.backup_id
        assert len(json_restored.users) == len(complex_backup_data.users)
        assert json_restored.users[0].user_name == complex_backup_data.users[0].user_name

        # CSV round-trip
        csv_result = await format_converter.convert_to_csv(complex_backup_data)
        csv_restored = await format_converter.convert_from_csv(csv_result)

        assert csv_restored.metadata.backup_id == complex_backup_data.metadata.backup_id
        assert len(csv_restored.users) == len(complex_backup_data.users)
        assert csv_restored.users[0].user_name == complex_backup_data.users[0].user_name

        # YAML round-trip
        yaml_result = await format_converter.convert_to_yaml(complex_backup_data)
        yaml_restored = await format_converter.convert_from_yaml(yaml_result)

        assert yaml_restored.metadata.backup_id == complex_backup_data.metadata.backup_id
        assert len(yaml_restored.users) == len(complex_backup_data.users)
        assert yaml_restored.users[0].user_name == complex_backup_data.users[0].user_name


class TestFormatValidation:
    """Test format validation and error handling."""

    @pytest.fixture
    def format_converter(self):
        """Create format converter instance."""
        return FormatConverter()

    @pytest.mark.asyncio
    async def test_invalid_json_structure(self, format_converter):
        """Test handling of JSON with invalid structure."""
        invalid_json = '{"metadata": "not an object"}'

        with pytest.raises(Exception):  # Should raise some kind of validation error
            await format_converter.convert_from_json(invalid_json)

    @pytest.mark.asyncio
    async def test_incomplete_csv_data(self, format_converter):
        """Test handling of incomplete CSV data."""
        incomplete_csv = {
            "metadata": "key,value\nbackup_id,test-backup",  # Missing required fields
            "users": "user_id\nuser-1",  # Missing required columns
        }

        with pytest.raises(Exception):  # Should raise validation error
            await format_converter.convert_from_csv(incomplete_csv)

    @pytest.mark.asyncio
    async def test_invalid_yaml_syntax(self, format_converter):
        """Test handling of invalid YAML syntax."""
        invalid_yaml = """
        metadata:
          backup_id: test
        users:
          - user_id: user-1
            user_name: test
          - invalid: yaml: syntax:
        """

        with pytest.raises(ExportImportError, match="Invalid YAML format"):
            await format_converter.convert_from_yaml(invalid_yaml)

    @pytest.mark.asyncio
    async def test_empty_csv_files(self, format_converter):
        """Test handling of empty CSV files."""
        empty_csv = {
            "metadata": "key,value\nbackup_id,test-backup\ntimestamp,2023-01-01T00:00:00\ninstance_arn,arn:aws:sso:::instance/ssoins-123\nbackup_type,full\nversion,1.0\nsource_account,123456789012\nsource_region,us-east-1\nretention_policy,{}\nencryption_info,{}\nresource_counts,{}\nsize_bytes,0\nchecksum,abc123",
            "users": "user_id,user_name,display_name,email,given_name,family_name,active,external_ids",  # Header only
            "groups": "group_id,display_name,description,members",
            "permission_sets": "permission_set_arn,name,description,session_duration,relay_state,inline_policy,managed_policies,customer_managed_policies,permissions_boundary",
            "assignments": "account_id,permission_set_arn,principal_type,principal_id",
        }

        # Should handle empty CSV files gracefully
        restored_data = await format_converter.convert_from_csv(empty_csv)
        assert len(restored_data.users) == 0
        assert len(restored_data.groups) == 0
        assert len(restored_data.permission_sets) == 0
        assert len(restored_data.assignments) == 0


if __name__ == "__main__":
    pytest.main([__file__])
