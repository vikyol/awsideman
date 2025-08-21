"""
Integration tests for the Identity Center data collector with other backup-restore components.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from src.awsideman.aws_clients import AWSClientManager
from src.awsideman.backup_restore import (
    BackupOptions,
    BackupType,
    IdentityCenterCollector,
    ResourceType,
    ValidationResult,
)


class TestIdentityCenterCollectorIntegration:
    """Integration test cases for IdentityCenterCollector with other components."""

    @pytest.fixture
    def mock_client_manager(self):
        """Create a mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)
        manager.region = "us-east-1"
        manager.session = Mock()
        manager.session.get_credentials.return_value = Mock(access_key="test-key")

        # Mock the client methods
        manager.get_identity_center_client.return_value = Mock()
        manager.get_identity_store_client.return_value = Mock()
        manager.get_organizations_client.return_value = Mock()

        return manager

    def test_collector_initialization(self, mock_client_manager):
        """Test that collector initializes correctly with client manager."""
        instance_arn = "arn:aws:sso:::instance/test-instance"

        collector = IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn=instance_arn
        )

        assert collector.client_manager == mock_client_manager
        assert collector.instance_arn == instance_arn
        assert collector._identity_store_id is None
        assert isinstance(collector._collection_stats, dict)

        # Verify stats structure
        expected_resources = ["users", "groups", "permission_sets", "assignments"]
        for resource in expected_resources:
            assert resource in collector._collection_stats
            assert "count" in collector._collection_stats[resource]
            assert "duration" in collector._collection_stats[resource]

    def test_collector_implements_interface(self, mock_client_manager):
        """Test that collector properly implements CollectorInterface."""
        from src.awsideman.backup_restore.interfaces import CollectorInterface

        collector = IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn="arn:aws:sso:::instance/test-instance"
        )

        assert isinstance(collector, CollectorInterface)

        # Verify all interface methods are implemented
        interface_methods = [
            "collect_users",
            "collect_groups",
            "collect_permission_sets",
            "collect_assignments",
            "collect_incremental",
            "validate_connection",
        ]

        for method_name in interface_methods:
            assert hasattr(collector, method_name)
            assert callable(getattr(collector, method_name))

    def test_backup_options_integration(self, mock_client_manager):
        """Test that collector works with BackupOptions model."""
        IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn="arn:aws:sso:::instance/test-instance"
        )

        # Test with different backup options
        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.USERS, ResourceType.GROUPS],
            include_inactive_users=True,
            parallel_collection=False,
            encryption_enabled=True,
            compression_enabled=True,
        )

        # Verify options are properly structured
        assert options.backup_type == BackupType.FULL
        assert ResourceType.USERS in options.resource_types
        assert ResourceType.GROUPS in options.resource_types
        assert options.include_inactive_users is True
        assert options.parallel_collection is False

        # Test incremental options
        incremental_options = BackupOptions(
            backup_type=BackupType.INCREMENTAL,
            resource_types=[ResourceType.ALL],
            since=datetime.now(),
            parallel_collection=True,
        )

        assert incremental_options.backup_type == BackupType.INCREMENTAL
        assert ResourceType.ALL in incremental_options.resource_types
        assert incremental_options.since is not None
        assert incremental_options.parallel_collection is True

    def test_validation_result_integration(self, mock_client_manager):
        """Test that collector returns proper ValidationResult objects."""
        IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn="arn:aws:sso:::instance/test-instance"
        )

        # Create a sample validation result
        result = ValidationResult(
            is_valid=True, errors=[], warnings=["Test warning"], details={"test": "value"}
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0] == "Test warning"
        assert result.details["test"] == "value"

        # Test serialization
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict["is_valid"] is True
        assert result_dict["warnings"] == ["Test warning"]

    def test_resource_type_filtering(self, mock_client_manager):
        """Test that ResourceType enum works correctly for filtering."""
        IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn="arn:aws:sso:::instance/test-instance"
        )

        # Test individual resource types
        assert ResourceType.USERS.value == "users"
        assert ResourceType.GROUPS.value == "groups"
        assert ResourceType.PERMISSION_SETS.value == "permission_sets"
        assert ResourceType.ASSIGNMENTS.value == "assignments"
        assert ResourceType.ALL.value == "all"

        # Test options with specific resource types
        user_only_options = BackupOptions(resource_types=[ResourceType.USERS])
        assert ResourceType.USERS in user_only_options.resource_types
        assert ResourceType.GROUPS not in user_only_options.resource_types

        all_resources_options = BackupOptions(resource_types=[ResourceType.ALL])
        assert ResourceType.ALL in all_resources_options.resource_types

    def test_collection_stats_structure(self, mock_client_manager):
        """Test that collection statistics have the expected structure."""
        collector = IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn="arn:aws:sso:::instance/test-instance"
        )

        # Modify stats to test the structure
        collector._collection_stats["users"]["count"] = 50
        collector._collection_stats["users"]["duration"] = 2.5
        collector._collection_stats["groups"]["count"] = 10
        collector._collection_stats["groups"]["duration"] = 1.2

        stats = collector.get_collection_stats()

        # Verify structure
        assert "users" in stats
        assert "groups" in stats
        assert "permission_sets" in stats
        assert "assignments" in stats

        # Verify data types
        assert isinstance(stats["users"]["count"], int)
        assert isinstance(stats["users"]["duration"], float)
        assert isinstance(stats["groups"]["count"], int)
        assert isinstance(stats["groups"]["duration"], float)

        # Verify values
        assert stats["users"]["count"] == 50
        assert stats["users"]["duration"] == 2.5
        assert stats["groups"]["count"] == 10
        assert stats["groups"]["duration"] == 1.2

    def test_client_property_access(self, mock_client_manager):
        """Test that client properties are properly lazy-loaded."""
        collector = IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn="arn:aws:sso:::instance/test-instance"
        )

        # Initially, clients should be None
        assert collector._identity_center_client is None
        assert collector._identity_store_client is None
        assert collector._organizations_client is None

        # Access properties to trigger lazy loading
        identity_center_client = collector.identity_center_client
        identity_store_client = collector.identity_store_client
        organizations_client = collector.organizations_client

        # Verify clients are now set
        assert collector._identity_center_client is not None
        assert collector._identity_store_client is not None
        assert collector._organizations_client is not None

        # Verify client manager methods were called
        mock_client_manager.get_identity_center_client.assert_called_once()
        mock_client_manager.get_identity_store_client.assert_called_once()
        mock_client_manager.get_organizations_client.assert_called_once()

        # Verify subsequent access returns same clients
        assert collector.identity_center_client is identity_center_client
        assert collector.identity_store_client is identity_store_client
        assert collector.organizations_client is organizations_client

    def test_instance_arn_validation(self, mock_client_manager):
        """Test that instance ARN is properly stored and used."""
        instance_arn = "arn:aws:sso:::instance/ssoins-1234567890abcdef"

        collector = IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn=instance_arn
        )

        assert collector.instance_arn == instance_arn

        # Test with different ARN format
        different_arn = "arn:aws:sso:::instance/test-instance-2"
        collector2 = IdentityCenterCollector(
            client_manager=mock_client_manager, instance_arn=different_arn
        )

        assert collector2.instance_arn == different_arn
        assert collector2.instance_arn != collector.instance_arn
