"""
Unit tests for cross-account and cross-region backup-restore functionality.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ClientError

from src.awsideman.aws_clients import AWSClientManager
from src.awsideman.backup_restore.cross_account import (
    CrossAccountClientManager,
    CrossAccountPermissionValidator,
    ResourceMapper,
)
from src.awsideman.backup_restore.models import (
    BackupOptions,
    BackupType,
    CrossAccountConfig,
    ResourceMapping,
    ResourceType,
    RestoreOptions,
    ValidationResult,
)


class TestCrossAccountClientManager:
    """Test cases for CrossAccountClientManager."""

    @pytest.fixture
    def base_client_manager(self):
        """Create a mock base client manager."""
        manager = Mock(spec=AWSClientManager)
        manager.region = "us-east-1"
        manager.enable_caching = True
        return manager

    @pytest.fixture
    def cross_account_manager(self, base_client_manager):
        """Create a CrossAccountClientManager instance."""
        return CrossAccountClientManager(base_client_manager)

    @pytest.fixture
    def cross_account_config(self):
        """Create a test cross-account configuration."""
        return CrossAccountConfig(
            target_account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/CrossAccountBackupRole",
            external_id="test-external-id",
            session_name="test-session",
        )

    @pytest.mark.asyncio
    async def test_assume_role_success(self, cross_account_manager, cross_account_config):
        """Test successful role assumption."""
        # Mock STS client and response
        mock_sts_client = Mock()
        mock_credentials = {
            "AccessKeyId": "AKIATEST",
            "SecretAccessKey": "test-secret",
            "SessionToken": "test-token",
            "Expiration": datetime.now() + timedelta(hours=1),
        }
        mock_sts_client.assume_role.return_value = {"Credentials": mock_credentials}

        cross_account_manager.base_client_manager.get_client.return_value = mock_sts_client

        # Test role assumption
        await cross_account_manager.assume_role(cross_account_config)

        # Verify the call was made correctly
        mock_sts_client.assume_role.assert_called_once()
        call_args = mock_sts_client.assume_role.call_args[1]

        assert call_args["RoleArn"] == cross_account_config.role_arn
        assert call_args["RoleSessionName"] == cross_account_config.session_name
        assert call_args["ExternalId"] == cross_account_config.external_id
        assert call_args["DurationSeconds"] == 3600

        # Verify session is cached
        cache_key = f"{cross_account_config.target_account_id}:{cross_account_config.role_arn}"
        assert cache_key in cross_account_manager._assumed_role_sessions

    @pytest.mark.asyncio
    async def test_assume_role_access_denied(self, cross_account_manager, cross_account_config):
        """Test role assumption with access denied error."""
        # Mock STS client to raise AccessDenied
        mock_sts_client = Mock()
        mock_sts_client.assume_role.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "AccessDenied",
                    "Message": "User is not authorized to perform: sts:AssumeRole",
                }
            },
            operation_name="AssumeRole",
        )

        cross_account_manager.base_client_manager.get_client.return_value = mock_sts_client

        # Test that appropriate error is raised
        with pytest.raises(ClientError) as exc_info:
            await cross_account_manager.assume_role(cross_account_config)

        assert exc_info.value.response["Error"]["Code"] == "CrossAccountAccessDenied"

    @pytest.mark.asyncio
    async def test_validate_cross_account_permissions_success(
        self, cross_account_manager, cross_account_config
    ):
        """Test successful cross-account permission validation."""
        # Mock successful role assumption
        mock_session = Mock()
        mock_identity_center_client = Mock()
        mock_identity_store_client = Mock()
        mock_organizations_client = Mock()

        mock_session.client.side_effect = lambda service: {
            "sso-admin": mock_identity_center_client,
            "identitystore": mock_identity_store_client,
            "organizations": mock_organizations_client,
        }[service]

        # Mock successful API calls
        mock_identity_center_client.list_instances.return_value = {"Instances": []}
        mock_identity_store_client.list_users.side_effect = ClientError(
            error_response={"Error": {"Code": "ValidationException"}}, operation_name="ListUsers"
        )  # ValidationException means we have permissions
        mock_organizations_client.list_roots.return_value = {"Roots": []}

        cross_account_manager.assume_role = AsyncMock(return_value=mock_session)

        # Test validation
        result = await cross_account_manager.validate_cross_account_permissions(
            cross_account_config
        )

        assert result.is_valid
        assert result.details["role_assumption"] == "SUCCESS"
        assert result.details["identity_center_access"] == "SUCCESS"
        assert result.details["identity_store_access"] == "SUCCESS"
        assert result.details["organizations_access"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_validate_cross_account_boundaries(self, cross_account_manager):
        """Test cross-account boundary validation."""
        # Mock get_caller_identity
        mock_sts_client = Mock()
        mock_sts_client.get_caller_identity.return_value = {"Account": "111111111111"}
        cross_account_manager.base_client_manager.get_client.return_value = mock_sts_client

        configs = [
            CrossAccountConfig(
                target_account_id="123456789012",
                role_arn="arn:aws:iam::123456789012:role/ValidRole",
            ),
            CrossAccountConfig(
                target_account_id="111111111111",  # Same account
                role_arn="arn:aws:iam::111111111111:role/SameAccountRole",
            ),
            CrossAccountConfig(
                target_account_id="999999999999",
                role_arn="arn:aws:iam::123456789012:role/MismatchedRole",  # Wrong account in ARN
            ),
        ]

        result = await cross_account_manager.validate_cross_account_boundaries(configs)

        # Should have warnings and errors
        assert len(result.warnings) > 0  # Same account warning
        assert len(result.errors) > 0  # Mismatched role ARN
        assert not result.is_valid

    def test_clear_session_cache(self, cross_account_manager):
        """Test clearing session cache."""
        # Add some mock data to cache
        cross_account_manager._assumed_role_sessions["test"] = Mock()
        cross_account_manager._session_expiry["test"] = datetime.now()
        cross_account_manager._role_validation_cache["test"] = Mock()

        # Clear cache
        cross_account_manager.clear_session_cache()

        # Verify cache is empty
        assert len(cross_account_manager._assumed_role_sessions) == 0
        assert len(cross_account_manager._session_expiry) == 0
        assert len(cross_account_manager._role_validation_cache) == 0


class TestResourceMapper:
    """Test cases for ResourceMapper."""

    @pytest.fixture
    def resource_mapper(self):
        """Create a ResourceMapper instance."""
        return ResourceMapper()

    @pytest.fixture
    def resource_mappings(self):
        """Create test resource mappings."""
        return [
            ResourceMapping(
                source_account_id="111111111111",
                target_account_id="222222222222",
                source_region="us-east-1",
                target_region="us-west-2",
                permission_set_name_mappings={"OldPermissionSet": "NewPermissionSet"},
            )
        ]

    def test_map_permission_set_arn(self, resource_mapper, resource_mappings):
        """Test permission set ARN mapping."""
        source_arn = "arn:aws:sso:::permissionSet/ins-123/ps-456"

        # Should return original ARN if no matching mapping
        mapped_arn = resource_mapper.map_permission_set_arn(source_arn, [])
        assert mapped_arn == source_arn

        # Test with account mapping
        source_arn = "arn:aws:sso:us-east-1:111111111111:permissionSet/ins-123/ps-456"
        expected_arn = "arn:aws:sso:us-west-2:222222222222:permissionSet/ins-123/ps-456"

        mapped_arn = resource_mapper.map_permission_set_arn(source_arn, resource_mappings)
        assert mapped_arn == expected_arn

    def test_map_assignment_account(self, resource_mapper, resource_mappings):
        """Test assignment account mapping."""
        # Test mapping
        mapped_account = resource_mapper.map_assignment_account("111111111111", resource_mappings)
        assert mapped_account == "222222222222"

        # Test no mapping
        mapped_account = resource_mapper.map_assignment_account("333333333333", resource_mappings)
        assert mapped_account == "333333333333"

    def test_map_permission_set_name(self, resource_mapper, resource_mappings):
        """Test permission set name mapping."""
        # Test mapping
        mapped_name = resource_mapper.map_permission_set_name("OldPermissionSet", resource_mappings)
        assert mapped_name == "NewPermissionSet"

        # Test no mapping
        mapped_name = resource_mapper.map_permission_set_name(
            "UnmappedPermissionSet", resource_mappings
        )
        assert mapped_name == "UnmappedPermissionSet"

    def test_validate_mappings_success(self, resource_mapper):
        """Test successful mapping validation."""
        valid_mappings = [
            ResourceMapping(
                source_account_id="123456789012",
                target_account_id="210987654321",
                source_region="us-east-1",
                target_region="us-west-2",
            )
        ]

        result = resource_mapper.validate_mappings(valid_mappings)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_mappings_invalid_account_ids(self, resource_mapper):
        """Test mapping validation with invalid account IDs."""
        invalid_mappings = [
            ResourceMapping(source_account_id="invalid-account", target_account_id="123456789012")
        ]

        result = resource_mapper.validate_mappings(invalid_mappings)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_mappings_duplicate_sources(self, resource_mapper):
        """Test mapping validation with duplicate source accounts."""
        duplicate_mappings = [
            ResourceMapping(source_account_id="123456789012", target_account_id="210987654321"),
            ResourceMapping(
                source_account_id="123456789012", target_account_id="333333333333"  # Duplicate
            ),
        ]

        result = resource_mapper.validate_mappings(duplicate_mappings)
        assert not result.is_valid
        assert any("duplicate" in error.lower() for error in result.errors)


class TestCrossAccountPermissionValidator:
    """Test cases for CrossAccountPermissionValidator."""

    @pytest.fixture
    def cross_account_manager(self):
        """Create a mock cross-account manager."""
        return Mock(spec=CrossAccountClientManager)

    @pytest.fixture
    def permission_validator(self, cross_account_manager):
        """Create a CrossAccountPermissionValidator instance."""
        return CrossAccountPermissionValidator(cross_account_manager)

    @pytest.fixture
    def cross_account_configs(self):
        """Create test cross-account configurations."""
        return [
            CrossAccountConfig(
                target_account_id="123456789012",
                role_arn="arn:aws:iam::123456789012:role/BackupRole",
            ),
            CrossAccountConfig(
                target_account_id="210987654321",
                role_arn="arn:aws:iam::210987654321:role/BackupRole",
            ),
        ]

    @pytest.mark.asyncio
    async def test_validate_backup_permissions_success(
        self, permission_validator, cross_account_configs
    ):
        """Test successful backup permission validation."""
        # Mock successful validation for all accounts
        mock_validation_result = ValidationResult(is_valid=True, errors=[], warnings=[])
        permission_validator.cross_account_manager.validate_cross_account_permissions = AsyncMock(
            return_value=mock_validation_result
        )

        # Mock successful client manager creation and API calls
        mock_client_manager = Mock()
        mock_identity_center_client = Mock()
        mock_identity_store_client = Mock()

        mock_client_manager.get_identity_center_client.return_value = mock_identity_center_client
        mock_client_manager.get_identity_store_client.return_value = mock_identity_store_client

        mock_identity_center_client.list_instances.return_value = {"Instances": []}

        permission_validator.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_client_manager
        )

        # Test validation
        result = await permission_validator.validate_backup_permissions(cross_account_configs)

        assert result.is_valid
        assert len(result.details["account_validations"]) == 2

        # Verify all accounts were validated
        for account_validation in result.details["account_validations"]:
            assert account_validation["permissions"]["basic"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_validate_restore_permissions_success(self, permission_validator):
        """Test successful restore permission validation."""
        config = CrossAccountConfig(
            target_account_id="123456789012", role_arn="arn:aws:iam::123456789012:role/RestoreRole"
        )
        target_instance_arn = "arn:aws:sso:::instance/ins-123456789012"

        # Mock successful client manager and API calls
        mock_client_manager = Mock()
        mock_identity_center_client = Mock()
        mock_identity_store_client = Mock()

        mock_client_manager.get_identity_center_client.return_value = mock_identity_center_client
        mock_client_manager.get_identity_store_client.return_value = mock_identity_store_client

        mock_identity_center_client.describe_instance.return_value = {"Instance": {}}
        mock_identity_center_client.list_permission_sets.return_value = {"PermissionSets": []}

        permission_validator.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_client_manager
        )

        # Test validation
        result = await permission_validator.validate_restore_permissions(
            config, target_instance_arn
        )

        assert result.is_valid
        assert result.details["permissions"]["instance_access"] == "SUCCESS"
        assert result.details["permissions"]["permission_set_access"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_validate_restore_permissions_access_denied(self, permission_validator):
        """Test restore permission validation with access denied."""
        config = CrossAccountConfig(
            target_account_id="123456789012", role_arn="arn:aws:iam::123456789012:role/RestoreRole"
        )
        target_instance_arn = "arn:aws:sso:::instance/ins-123456789012"

        # Mock client manager that raises access denied
        mock_client_manager = Mock()
        mock_identity_center_client = Mock()

        mock_client_manager.get_identity_center_client.return_value = mock_identity_center_client
        mock_identity_center_client.describe_instance.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}}, operation_name="DescribeInstance"
        )

        permission_validator.cross_account_manager.get_cross_account_client_manager = AsyncMock(
            return_value=mock_client_manager
        )

        # Test validation
        result = await permission_validator.validate_restore_permissions(
            config, target_instance_arn
        )

        assert not result.is_valid
        assert len(result.errors) > 0
        assert result.details["permissions"]["instance_access"] == "DENIED"


class TestCrossAccountIntegration:
    """Integration tests for cross-account functionality."""

    @pytest.mark.asyncio
    async def test_cross_account_backup_options_serialization(self):
        """Test serialization of backup options with cross-account configs."""
        cross_account_configs = [
            CrossAccountConfig(
                target_account_id="123456789012",
                role_arn="arn:aws:iam::123456789012:role/BackupRole",
                external_id="test-external-id",
            )
        ]

        options = BackupOptions(
            backup_type=BackupType.FULL,
            resource_types=[ResourceType.ALL],
            cross_account_configs=cross_account_configs,
        )

        # Test serialization
        options_dict = options.to_dict()
        assert "cross_account_configs" in options_dict
        assert len(options_dict["cross_account_configs"]) == 1
        assert options_dict["cross_account_configs"][0]["target_account_id"] == "123456789012"

        # Test deserialization
        restored_options = BackupOptions.from_dict(options_dict)
        assert len(restored_options.cross_account_configs) == 1
        assert restored_options.cross_account_configs[0].target_account_id == "123456789012"
        assert (
            restored_options.cross_account_configs[0].role_arn
            == "arn:aws:iam::123456789012:role/BackupRole"
        )

    @pytest.mark.asyncio
    async def test_restore_options_with_resource_mappings(self):
        """Test restore options with resource mappings."""
        resource_mappings = [
            ResourceMapping(
                source_account_id="111111111111",
                target_account_id="222222222222",
                source_region="us-east-1",
                target_region="us-west-2",
            )
        ]

        cross_account_config = CrossAccountConfig(
            target_account_id="222222222222", role_arn="arn:aws:iam::222222222222:role/RestoreRole"
        )

        options = RestoreOptions(
            cross_account_config=cross_account_config, resource_mapping_configs=resource_mappings
        )

        # Test serialization
        options_dict = options.to_dict()
        assert "cross_account_config" in options_dict
        assert "resource_mapping_configs" in options_dict
        assert len(options_dict["resource_mapping_configs"]) == 1

        # Test deserialization
        restored_options = RestoreOptions.from_dict(options_dict)
        assert restored_options.cross_account_config is not None
        assert restored_options.cross_account_config.target_account_id == "222222222222"
        assert len(restored_options.resource_mapping_configs) == 1
        assert restored_options.resource_mapping_configs[0].source_account_id == "111111111111"


if __name__ == "__main__":
    pytest.main([__file__])
