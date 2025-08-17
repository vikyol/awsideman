"""
Unit tests for cross-account functionality in the Identity Center collector.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.awsideman.aws_clients import AWSClientManager
from src.awsideman.backup_restore.collector import IdentityCenterCollector
from src.awsideman.backup_restore.models import (
    BackupData,
    BackupOptions,
    BackupType,
    CrossAccountConfig,
    ResourceType,
    ValidationResult,
)


class TestIdentityCenterCollectorCrossAccount:
    """Test cases for cross-account functionality in IdentityCenterCollector."""

    @pytest.fixture
    def client_manager(self):
        """Create a mock AWS client manager."""
        manager = Mock(spec=AWSClientManager)
        manager.region = "us-east-1"
        manager.enable_caching = True
        return manager

    @pytest.fixture
    def collector(self, client_manager):
        """Create an IdentityCenterCollector instance."""
        instance_arn = "arn:aws:sso:::instance/ins-123456789012"
        return IdentityCenterCollector(client_manager, instance_arn)

    @pytest.fixture
    def cross_account_configs(self):
        """Create test cross-account configurations."""
        return [
            CrossAccountConfig(
                target_account_id="123456789012",
                role_arn="arn:aws:iam::123456789012:role/BackupRole",
                external_id="test-external-id-1",
            ),
            CrossAccountConfig(
                target_account_id="210987654321",
                role_arn="arn:aws:iam::210987654321:role/BackupRole",
                external_id="test-external-id-2",
            ),
        ]

    @pytest.fixture
    def backup_options_with_cross_account(self, cross_account_configs):
        """Create backup options with cross-account configurations."""
        return BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            cross_account_configs=cross_account_configs,
            parallel_collection=True,
        )

    @pytest.mark.asyncio
    async def test_validate_cross_account_access_success(self, collector, cross_account_configs):
        """Test successful cross-account access validation."""
        # Mock the cross-account manager validation methods
        mock_boundary_result = ValidationResult(is_valid=True, errors=[], warnings=[])
        mock_permission_result = ValidationResult(is_valid=True, errors=[], warnings=[])

        collector.cross_account_manager.validate_cross_account_boundaries = AsyncMock(
            return_value=mock_boundary_result
        )
        collector.cross_account_manager.validate_cross_account_permissions = AsyncMock(
            return_value=mock_permission_result
        )

        # Test validation
        result = await collector.validate_cross_account_access(cross_account_configs)

        assert result.is_valid
        assert result.details["validated_accounts"] == 2
        assert len(result.details["account_results"]) == 2

        # Verify both accounts were validated
        account_ids = [ar["account_id"] for ar in result.details["account_results"]]
        assert "123456789012" in account_ids
        assert "210987654321" in account_ids

    @pytest.mark.asyncio
    async def test_validate_cross_account_access_with_errors(
        self, collector, cross_account_configs
    ):
        """Test cross-account access validation with errors."""
        # Mock boundary validation success but permission validation failure
        mock_boundary_result = ValidationResult(is_valid=True, errors=[], warnings=[])
        mock_permission_result_1 = ValidationResult(
            is_valid=False, errors=["Access denied to Identity Center"], warnings=[]
        )
        mock_permission_result_2 = ValidationResult(is_valid=True, errors=[], warnings=[])

        collector.cross_account_manager.validate_cross_account_boundaries = AsyncMock(
            return_value=mock_boundary_result
        )
        collector.cross_account_manager.validate_cross_account_permissions = AsyncMock(
            side_effect=[mock_permission_result_1, mock_permission_result_2]
        )

        # Test validation
        result = await collector.validate_cross_account_access(cross_account_configs)

        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("123456789012" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_cross_account_access_empty_configs(self, collector):
        """Test cross-account access validation with empty configurations."""
        result = await collector.validate_cross_account_access([])

        assert result.is_valid
        assert len(result.warnings) > 0
        assert "No cross-account configurations" in result.warnings[0]
        assert result.details["validated_accounts"] == 0

    @pytest.mark.asyncio
    async def test_collect_cross_account_data_success(
        self, collector, backup_options_with_cross_account
    ):
        """Test successful cross-account data collection."""
        # Mock cross-account client manager creation
        mock_cross_account_client_manager = Mock(spec=AWSClientManager)
        mock_cross_account_client_manager.region = "us-east-1"

        collector.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_cross_account_client_manager
        )

        # Mock the _collect_account_data method to return test data
        mock_backup_data_1 = Mock(spec=BackupData)
        mock_backup_data_1.users = []
        mock_backup_data_1.groups = []
        mock_backup_data_1.permission_sets = []
        mock_backup_data_1.assignments = []

        mock_backup_data_2 = Mock(spec=BackupData)
        mock_backup_data_2.users = []
        mock_backup_data_2.groups = []
        mock_backup_data_2.permission_sets = []
        mock_backup_data_2.assignments = []

        collector._collect_account_data = AsyncMock(
            side_effect=[mock_backup_data_1, mock_backup_data_2]
        )

        # Test cross-account data collection
        result = await collector.collect_cross_account_data(backup_options_with_cross_account)

        assert len(result) == 2
        assert "123456789012" in result
        assert "210987654321" in result

        # Verify _collect_account_data was called for each account
        assert collector._collect_account_data.call_count == 2

    @pytest.mark.asyncio
    async def test_collect_cross_account_data_partial_failure(
        self, collector, backup_options_with_cross_account
    ):
        """Test cross-account data collection with partial failures."""
        # Mock cross-account client manager creation - first succeeds, second fails
        mock_cross_account_client_manager = Mock(spec=AWSClientManager)

        async def mock_get_client_manager(config):
            if config.target_account_id == "123456789012":
                return mock_cross_account_client_manager
            else:
                raise Exception("Access denied")

        collector.cross_account_manager.get_cross_account_client_manager = mock_get_client_manager

        # Mock successful data collection for the first account
        mock_backup_data = Mock(spec=BackupData)
        collector._collect_account_data = AsyncMock(return_value=mock_backup_data)

        # Test cross-account data collection
        result = await collector.collect_cross_account_data(backup_options_with_cross_account)

        # Should only have data from the successful account
        assert len(result) == 1
        assert "123456789012" in result
        assert "210987654321" not in result

    @pytest.mark.asyncio
    async def test_collect_cross_account_data_no_configs(self, collector):
        """Test cross-account data collection with no configurations."""
        options = BackupOptions(
            backup_type=BackupType.FULL, resource_types=[ResourceType.ALL], cross_account_configs=[]
        )

        result = await collector.collect_cross_account_data(options)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_collect_account_data_parallel(self, collector):
        """Test account data collection with parallel processing."""
        # Create a mock collector for the target account
        mock_target_collector = Mock(spec=IdentityCenterCollector)
        mock_target_collector.collect_users = AsyncMock(return_value=[])
        mock_target_collector.collect_groups = AsyncMock(return_value=[])
        mock_target_collector.collect_permission_sets = AsyncMock(return_value=[])
        mock_target_collector.collect_assignments = AsyncMock(return_value=[])

        # Mock the _build_relationships method
        collector._build_relationships = Mock(return_value=Mock())

        options = BackupOptions(
            backup_type=BackupType.FULL, resource_types=[ResourceType.ALL], parallel_collection=True
        )

        # Test account data collection
        result = await collector._collect_account_data(
            mock_target_collector, options, "123456789012"
        )

        assert isinstance(result, BackupData)
        assert result.metadata.source_account == "123456789012"

        # Verify all collection methods were called
        mock_target_collector.collect_users.assert_called_once()
        mock_target_collector.collect_groups.assert_called_once()
        mock_target_collector.collect_permission_sets.assert_called_once()
        mock_target_collector.collect_assignments.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_account_data_sequential(self, collector):
        """Test account data collection with sequential processing."""
        # Create a mock collector for the target account
        mock_target_collector = Mock(spec=IdentityCenterCollector)
        mock_target_collector.collect_users = AsyncMock(return_value=[])
        mock_target_collector.collect_groups = AsyncMock(return_value=[])
        mock_target_collector.collect_permission_sets = AsyncMock(return_value=[])
        mock_target_collector.collect_assignments = AsyncMock(return_value=[])

        # Mock the _build_relationships method
        collector._build_relationships = Mock(return_value=Mock())

        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            parallel_collection=False,  # Sequential processing
        )

        # Test account data collection
        result = await collector._collect_account_data(
            mock_target_collector, options, "123456789012"
        )

        assert isinstance(result, BackupData)
        assert result.metadata.source_account == "123456789012"

        # Verify all collection methods were called
        mock_target_collector.collect_users.assert_called_once()
        mock_target_collector.collect_groups.assert_called_once()
        mock_target_collector.collect_permission_sets.assert_called_once()
        mock_target_collector.collect_assignments.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_account_data_selective_resources(self, collector):
        """Test account data collection with selective resource types."""
        # Create a mock collector for the target account
        mock_target_collector = Mock(spec=IdentityCenterCollector)
        mock_target_collector.collect_users = AsyncMock(return_value=[])
        mock_target_collector.collect_groups = AsyncMock(return_value=[])
        mock_target_collector.collect_permission_sets = AsyncMock(return_value=[])
        mock_target_collector.collect_assignments = AsyncMock(return_value=[])

        # Mock the _build_relationships method
        collector._build_relationships = Mock(return_value=Mock())

        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.USERS, ResourceType.GROUPS],  # Only users and groups
            parallel_collection=True,
        )

        # Test account data collection
        result = await collector._collect_account_data(
            mock_target_collector, options, "123456789012"
        )

        assert isinstance(result, BackupData)

        # Verify only selected collection methods were called
        mock_target_collector.collect_users.assert_called_once()
        mock_target_collector.collect_groups.assert_called_once()
        mock_target_collector.collect_permission_sets.assert_not_called()
        mock_target_collector.collect_assignments.assert_not_called()

    @pytest.mark.asyncio
    async def test_collect_account_data_with_exception(self, collector):
        """Test account data collection with exceptions during collection."""
        # Create a mock collector that raises exceptions
        mock_target_collector = Mock(spec=IdentityCenterCollector)
        mock_target_collector.collect_users = AsyncMock(side_effect=Exception("Collection failed"))
        mock_target_collector.collect_groups = AsyncMock(return_value=[])
        mock_target_collector.collect_permission_sets = AsyncMock(return_value=[])
        mock_target_collector.collect_assignments = AsyncMock(return_value=[])

        # Mock the _build_relationships method
        collector._build_relationships = Mock(return_value=Mock())

        options = BackupOptions(
            backup_type=BackupType.FULL, resource_types=[ResourceType.ALL], parallel_collection=True
        )

        # Test account data collection - should handle exceptions gracefully
        result = await collector._collect_account_data(
            mock_target_collector, options, "123456789012"
        )

        assert isinstance(result, BackupData)
        # Users should be empty due to exception, but other resources should be collected
        assert len(result.users) == 0


class TestCrossAccountCollectorIntegration:
    """Integration tests for cross-account collector functionality."""

    @pytest.mark.asyncio
    async def test_full_cross_account_backup_workflow(self):
        """Test complete cross-account backup workflow."""
        # Create mock components
        client_manager = Mock(spec=AWSClientManager)
        client_manager.region = "us-east-1"

        collector = IdentityCenterCollector(client_manager, "arn:aws:sso:::instance/ins-123")

        # Mock cross-account validation
        collector.cross_account_manager.validate_cross_account_boundaries = AsyncMock(
            return_value=ValidationResult(is_valid=True, errors=[], warnings=[])
        )
        collector.cross_account_manager.validate_cross_account_permissions = AsyncMock(
            return_value=ValidationResult(is_valid=True, errors=[], warnings=[])
        )

        # Mock cross-account data collection
        mock_backup_data = Mock(spec=BackupData)
        mock_backup_data.users = []
        mock_backup_data.groups = []
        mock_backup_data.permission_sets = []
        mock_backup_data.assignments = []

        collector._collect_account_data = AsyncMock(return_value=mock_backup_data)
        collector.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=Mock(spec=AWSClientManager)
        )

        # Create backup options with cross-account configs
        cross_account_configs = [
            CrossAccountConfig(
                target_account_id="123456789012",
                role_arn="arn:aws:iam::123456789012:role/BackupRole",
            )
        ]

        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            cross_account_configs=cross_account_configs,
        )

        # Test validation
        validation_result = await collector.validate_cross_account_access(cross_account_configs)
        assert validation_result.is_valid

        # Test data collection
        cross_account_data = await collector.collect_cross_account_data(options)
        assert len(cross_account_data) == 1
        assert "123456789012" in cross_account_data


if __name__ == "__main__":
    pytest.main([__file__])
