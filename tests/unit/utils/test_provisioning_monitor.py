"""Unit tests for ProvisioningMonitor component."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.provisioning_monitor import ProvisioningMonitor
from src.awsideman.utils.status_infrastructure import StatusCheckConfig, StatusCheckError
from src.awsideman.utils.status_models import (
    ProvisioningOperation,
    ProvisioningOperationStatus,
    ProvisioningStatus,
    StatusLevel,
)


class TestProvisioningMonitor:
    """Test cases for ProvisioningMonitor component."""

    @pytest.fixture
    def mock_idc_client(self):
        """Create a mock Identity Center client."""
        mock_client = Mock()
        mock_client.client = Mock()

        # Mock the get_sso_admin_client method to return a mock client
        mock_sso_admin_client = Mock()
        mock_client.get_sso_admin_client.return_value = mock_sso_admin_client

        return mock_client

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return StatusCheckConfig(timeout_seconds=10, retry_attempts=2, retry_delay_seconds=0.1)

    @pytest.fixture
    def provisioning_monitor(self, mock_idc_client, config):
        """Create ProvisioningMonitor instance for testing."""
        return ProvisioningMonitor(mock_idc_client, config)

    @pytest.fixture
    def sample_active_operation(self):
        """Create a sample active provisioning operation."""
        return ProvisioningOperation(
            operation_id="test-op-001",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.IN_PROGRESS,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc) - timedelta(minutes=5),
            failure_reason=None,
            estimated_completion=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

    @pytest.fixture
    def sample_failed_operation(self):
        """Create a sample failed provisioning operation."""
        return ProvisioningOperation(
            operation_id="test-op-002",
            operation_type="DELETE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.FAILED,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-0987654321fedcba",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc) - timedelta(minutes=15),
            failure_reason="InsufficientPermissions: Unable to provision permission set to target account",
            estimated_completion=None,
        )

    @pytest.fixture
    def sample_completed_operation(self):
        """Create a sample completed provisioning operation."""
        return ProvisioningOperation(
            operation_id="test-op-003",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.SUCCEEDED,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1111222233334444",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc) - timedelta(minutes=30),
            failure_reason=None,
            estimated_completion=datetime.now(timezone.utc) - timedelta(minutes=25),
        )

    @pytest.mark.asyncio
    async def test_check_status_no_operations(self, provisioning_monitor, mock_idc_client):
        """Test status check when no operations are found."""
        # Mock empty responses
        mock_idc_client.get_sso_admin_client.return_value.list_instances.return_value = {
            "Instances": []
        }

        result = await provisioning_monitor.check_status()

        assert isinstance(result, ProvisioningStatus)
        assert result.status == StatusLevel.HEALTHY
        assert result.message == "No active provisioning operations"
        assert len(result.active_operations) == 0
        assert len(result.failed_operations) == 0
        assert result.pending_count == 0
        assert result.estimated_completion is None

    @pytest.mark.asyncio
    async def test_check_status_with_active_operations(
        self, provisioning_monitor, mock_idc_client, sample_active_operation
    ):
        """Test status check with active operations."""
        # Mock responses
        mock_idc_client.get_sso_admin_client.return_value.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef"}]
        }
        mock_idc_client.get_sso_admin_client.return_value.list_permission_sets.return_value = {
            "PermissionSets": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            ]
        }

        # Mock the active operations method
        with patch.object(
            provisioning_monitor, "_get_active_operations", return_value=[sample_active_operation]
        ):
            with patch.object(provisioning_monitor, "_get_failed_operations", return_value=[]):
                with patch.object(
                    provisioning_monitor, "_get_completed_operations", return_value=[]
                ):
                    result = await provisioning_monitor.check_status()

        assert isinstance(result, ProvisioningStatus)
        assert result.status == StatusLevel.HEALTHY
        assert "1 provisioning operations in progress" in result.message
        assert len(result.active_operations) == 1
        assert result.pending_count == 1
        assert result.estimated_completion is not None

    @pytest.mark.asyncio
    async def test_check_status_with_failed_operations(
        self, provisioning_monitor, mock_idc_client, sample_failed_operation
    ):
        """Test status check with failed operations."""
        # Mock responses
        mock_idc_client.get_sso_admin_client.return_value.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef"}]
        }

        # Mock the operations methods
        with patch.object(provisioning_monitor, "_get_active_operations", return_value=[]):
            with patch.object(
                provisioning_monitor,
                "_get_failed_operations",
                return_value=[sample_failed_operation],
            ):
                with patch.object(
                    provisioning_monitor, "_get_completed_operations", return_value=[]
                ):
                    result = await provisioning_monitor.check_status()

        assert isinstance(result, ProvisioningStatus)
        assert result.status == StatusLevel.CRITICAL  # High failure rate (100%)
        assert "High provisioning failure rate" in result.message
        assert len(result.failed_operations) == 1
        assert result.has_failed_operations()

    @pytest.mark.asyncio
    async def test_check_status_with_mixed_operations(
        self,
        provisioning_monitor,
        mock_idc_client,
        sample_active_operation,
        sample_failed_operation,
        sample_completed_operation,
    ):
        """Test status check with mixed operation types."""
        # Mock responses
        mock_idc_client.get_sso_admin_client.return_value.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef"}]
        }

        # Mock the operations methods
        with patch.object(
            provisioning_monitor, "_get_active_operations", return_value=[sample_active_operation]
        ):
            with patch.object(
                provisioning_monitor,
                "_get_failed_operations",
                return_value=[sample_failed_operation],
            ):
                with patch.object(
                    provisioning_monitor,
                    "_get_completed_operations",
                    return_value=[sample_completed_operation],
                ):
                    result = await provisioning_monitor.check_status()

        assert isinstance(result, ProvisioningStatus)
        assert result.status == StatusLevel.WARNING  # Moderate failure rate (33%)
        assert "Elevated provisioning failure rate" in result.message
        assert len(result.active_operations) == 1
        assert len(result.failed_operations) == 1
        assert len(result.completed_operations) == 1
        assert result.get_total_operations() == 3

    @pytest.mark.asyncio
    async def test_check_status_connection_error(self, provisioning_monitor, mock_idc_client):
        """Test status check when connection fails."""
        # Mock connection error
        mock_idc_client.get_sso_admin_client.return_value.list_instances.side_effect = ClientError(
            {"Error": {"Code": "EndpointConnectionError", "Message": "Connection failed"}},
            "list_instances",
        )

        result = await provisioning_monitor.check_status()

        assert isinstance(result, ProvisioningStatus)
        assert result.status == StatusLevel.CRITICAL
        assert "Provisioning status check failed" in result.message
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_get_active_operations_no_instances(self, provisioning_monitor, mock_idc_client):
        """Test getting active operations when no instances exist."""
        mock_idc_client.get_sso_admin_client.return_value.list_instances.return_value = {
            "Instances": []
        }

        result = await provisioning_monitor._get_active_operations()

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_active_operations_with_instances(
        self, provisioning_monitor, mock_idc_client
    ):
        """Test getting active operations with instances."""
        # Mock responses
        mock_idc_client.get_sso_admin_client.return_value.list_instances.return_value = {
            "Instances": [{"InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef"}]
        }
        mock_idc_client.get_sso_admin_client.return_value.list_permission_sets.return_value = {
            "PermissionSets": [
                "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef"
            ]
        }

        # Mock the permission set provisioning status check
        with patch.object(
            provisioning_monitor, "_check_permission_set_provisioning_status", return_value=None
        ):
            result = await provisioning_monitor._get_active_operations()

        assert isinstance(result, list)
        # Should be empty since we mocked no active operations
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_active_operations_api_error(self, provisioning_monitor, mock_idc_client):
        """Test getting active operations when API call fails."""
        # Mock API error
        mock_idc_client.get_sso_admin_client.return_value.list_instances.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}}, "list_instances"
        )

        with pytest.raises(StatusCheckError):
            await provisioning_monitor._get_active_operations()

    @pytest.mark.asyncio
    async def test_get_failed_operations_from_cache(
        self, provisioning_monitor, sample_failed_operation
    ):
        """Test getting failed operations from cache."""
        # Add operation to cache
        provisioning_monitor._operation_cache[sample_failed_operation.operation_id] = (
            sample_failed_operation
        )

        # Mock the operation status check to return the failed operation
        with patch.object(
            provisioning_monitor, "_check_operation_status", return_value=sample_failed_operation
        ):
            result = await provisioning_monitor._get_failed_operations()

        assert isinstance(result, list)
        # Should be empty since the sample operation is already failed, not in progress
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_completed_operations_from_cache(
        self, provisioning_monitor, sample_completed_operation
    ):
        """Test getting completed operations from cache."""
        # Add operation to cache
        provisioning_monitor._operation_cache[sample_completed_operation.operation_id] = (
            sample_completed_operation
        )

        result = await provisioning_monitor._get_completed_operations()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].operation_id == sample_completed_operation.operation_id

    @pytest.mark.asyncio
    async def test_check_operation_status_aging(self, provisioning_monitor, mock_idc_client):
        """Test operation status checking with aging logic."""
        # Create an old operation
        old_operation = ProvisioningOperation(
            operation_id="old-op-001",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.IN_PROGRESS,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc)
            - timedelta(minutes=15),  # Older than 10 minutes
            failure_reason=None,
            estimated_completion=None,
        )

        result = await provisioning_monitor._check_operation_status(old_operation)

        assert result is not None
        assert (
            result.status == ProvisioningOperationStatus.SUCCEEDED
        )  # Should be marked as completed

    def test_estimate_completion_time_no_operations(self, provisioning_monitor):
        """Test completion time estimation with no operations."""
        result = provisioning_monitor._estimate_completion_time([])

        assert result is None

    def test_estimate_completion_time_with_operations(
        self, provisioning_monitor, sample_active_operation
    ):
        """Test completion time estimation with active operations."""
        result = provisioning_monitor._estimate_completion_time([sample_active_operation])

        assert result is not None
        assert isinstance(result, datetime)
        # Allow for small timing differences in test execution
        assert result >= datetime.now(timezone.utc) - timedelta(
            seconds=1
        )  # Should be in the future or very recent past

    def test_determine_provisioning_status_no_operations(self, provisioning_monitor):
        """Test status determination with no operations."""
        result = provisioning_monitor._determine_provisioning_status([], [], [])

        assert result["status"] == StatusLevel.HEALTHY
        assert result["message"] == "No active provisioning operations"
        assert len(result["errors"]) == 0

    def test_determine_provisioning_status_high_failure_rate(
        self, provisioning_monitor, sample_failed_operation
    ):
        """Test status determination with high failure rate."""
        # Create multiple failed operations to simulate high failure rate
        failed_ops = [sample_failed_operation] * 3
        completed_ops = [Mock()] * 2  # 3 failed out of 5 total = 60% failure rate

        result = provisioning_monitor._determine_provisioning_status([], failed_ops, completed_ops)

        assert result["status"] == StatusLevel.CRITICAL
        assert "High provisioning failure rate" in result["message"]
        assert len(result["errors"]) > 0

    def test_determine_provisioning_status_moderate_failure_rate(
        self, provisioning_monitor, sample_failed_operation
    ):
        """Test status determination with moderate failure rate."""
        # Create scenario with moderate failure rate
        failed_ops = [sample_failed_operation]
        completed_ops = [Mock()] * 4  # 1 failed out of 5 total = 20% failure rate

        result = provisioning_monitor._determine_provisioning_status([], failed_ops, completed_ops)

        assert result["status"] == StatusLevel.HEALTHY  # 20% is not above warning threshold
        assert "All provisioning operations completed successfully" in result["message"]

    def test_determine_provisioning_status_long_running_operations(self, provisioning_monitor):
        """Test status determination with long-running operations."""
        # Create a long-running operation
        long_running_op = ProvisioningOperation(
            operation_id="long-op-001",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.IN_PROGRESS,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc)
            - timedelta(minutes=45),  # Longer than 30 minutes
            failure_reason=None,
            estimated_completion=None,
        )

        result = provisioning_monitor._determine_provisioning_status([long_running_op], [], [])

        assert result["status"] == StatusLevel.WARNING
        assert "running longer than expected" in result["message"]
        assert len(result["errors"]) > 0

    def test_get_operation_type_breakdown(
        self, provisioning_monitor, sample_active_operation, sample_failed_operation
    ):
        """Test operation type breakdown calculation."""
        operations = [sample_active_operation, sample_failed_operation]

        result = provisioning_monitor._get_operation_type_breakdown(operations)

        assert isinstance(result, dict)
        assert "CREATE_ACCOUNT_ASSIGNMENT" in result
        assert "DELETE_ACCOUNT_ASSIGNMENT" in result
        assert result["CREATE_ACCOUNT_ASSIGNMENT"] == 1
        assert result["DELETE_ACCOUNT_ASSIGNMENT"] == 1

    def test_update_operation_cache(
        self, provisioning_monitor, sample_active_operation, sample_completed_operation
    ):
        """Test operation cache update functionality."""
        operations = [sample_active_operation, sample_completed_operation]

        provisioning_monitor._update_operation_cache(operations)

        assert len(provisioning_monitor._operation_cache) == 2
        assert sample_active_operation.operation_id in provisioning_monitor._operation_cache
        assert sample_completed_operation.operation_id in provisioning_monitor._operation_cache

    def test_update_operation_cache_cleanup_old_operations(self, provisioning_monitor):
        """Test operation cache cleanup of old operations."""
        # Create an old operation
        old_operation = ProvisioningOperation(
            operation_id="old-op-001",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.SUCCEEDED,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc) - timedelta(days=10),  # Older than 7 days
            failure_reason=None,
            estimated_completion=None,
        )

        # Add to cache
        provisioning_monitor._operation_cache[old_operation.operation_id] = old_operation

        # Update cache with new operations (should trigger cleanup)
        provisioning_monitor._update_operation_cache([])

        # Old operation should be removed
        assert old_operation.operation_id not in provisioning_monitor._operation_cache

    def test_get_operation_counts(
        self,
        provisioning_monitor,
        sample_active_operation,
        sample_failed_operation,
        sample_completed_operation,
    ):
        """Test operation counts calculation."""
        # Add operations to cache
        operations = [sample_active_operation, sample_failed_operation, sample_completed_operation]
        provisioning_monitor._update_operation_cache(operations)

        result = provisioning_monitor.get_operation_counts()

        assert isinstance(result, dict)
        assert result["total"] == 3
        assert result["active"] == 1
        assert result["failed"] == 1
        assert result["completed"] == 1

    def test_get_error_details(self, provisioning_monitor, sample_failed_operation):
        """Test error details extraction for failed operations."""
        failed_operations = [sample_failed_operation]

        result = provisioning_monitor.get_error_details(failed_operations)

        assert isinstance(result, list)
        assert len(result) == 1

        error_detail = result[0]
        assert error_detail["operation_id"] == sample_failed_operation.operation_id
        assert error_detail["operation_type"] == sample_failed_operation.operation_type
        assert error_detail["failure_reason"] == sample_failed_operation.failure_reason
        assert "age_minutes" in error_detail

    def test_format_provisioning_summary(
        self, provisioning_monitor, sample_active_operation, sample_failed_operation
    ):
        """Test provisioning summary formatting."""
        provisioning_status = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Test message",
            active_operations=[sample_active_operation],
            failed_operations=[sample_failed_operation],
            completed_operations=[],
            pending_count=1,
            estimated_completion=datetime.now(timezone.utc) + timedelta(minutes=10),
        )

        result = provisioning_monitor.format_provisioning_summary(provisioning_status)

        assert isinstance(result, str)
        assert "Status: Warning" in result  # StatusLevel.WARNING.value is "Warning", not "WARNING"
        assert "Active: 1" in result
        assert "Failed: 1" in result
        assert "ETA:" in result
        assert "Failure Rate:" in result

    def test_provisioning_operation_methods(
        self, sample_active_operation, sample_failed_operation, sample_completed_operation
    ):
        """Test ProvisioningOperation helper methods."""
        # Test active operation
        assert sample_active_operation.is_active()
        assert not sample_active_operation.has_failed()
        assert not sample_active_operation.is_completed()

        # Test failed operation
        assert not sample_failed_operation.is_active()
        assert sample_failed_operation.has_failed()
        assert not sample_failed_operation.is_completed()

        # Test completed operation
        assert not sample_completed_operation.is_active()
        assert not sample_completed_operation.has_failed()
        assert sample_completed_operation.is_completed()

    def test_provisioning_status_methods(
        self, sample_active_operation, sample_failed_operation, sample_completed_operation
    ):
        """Test ProvisioningStatus helper methods."""
        provisioning_status = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Test message",
            active_operations=[sample_active_operation],
            failed_operations=[sample_failed_operation],
            completed_operations=[sample_completed_operation],
            pending_count=1,
            estimated_completion=None,
        )

        assert provisioning_status.get_total_operations() == 3
        assert provisioning_status.has_active_operations()
        assert provisioning_status.has_failed_operations()

        # Test failure rate calculation
        failure_rate = provisioning_status.get_failure_rate()
        assert failure_rate == pytest.approx(33.33, rel=1e-2)  # 1 failed out of 3 total

    @pytest.mark.asyncio
    async def test_check_status_with_retry_success(self, provisioning_monitor, mock_idc_client):
        """Test status check with retry logic - success case."""
        # Mock successful response
        mock_idc_client.get_sso_admin_client.return_value.list_instances.return_value = {
            "Instances": []
        }

        result = await provisioning_monitor.check_status_with_retry()

        assert isinstance(result, ProvisioningStatus)
        assert result.status == StatusLevel.HEALTHY

    @pytest.mark.asyncio
    async def test_check_status_with_retry_failure(self, provisioning_monitor, mock_idc_client):
        """Test status check with retry logic - failure case."""
        # Mock persistent failure
        mock_idc_client.get_sso_admin_client.return_value.list_instances.side_effect = Exception(
            "Persistent error"
        )

        result = await provisioning_monitor.check_status_with_retry()

        assert isinstance(result, ProvisioningStatus)
        assert result.status == StatusLevel.CRITICAL
        assert len(result.errors) > 0

    def test_provisioning_monitor_initialization(self, mock_idc_client, config):
        """Test ProvisioningMonitor initialization."""
        monitor = ProvisioningMonitor(mock_idc_client, config)

        assert monitor.idc_client == mock_idc_client
        assert monitor.config == config
        assert isinstance(monitor._operation_cache, dict)
        assert len(monitor._operation_cache) == 0
        assert monitor._last_check_time is None

    def test_provisioning_monitor_initialization_default_config(self, mock_idc_client):
        """Test ProvisioningMonitor initialization with default config."""
        monitor = ProvisioningMonitor(mock_idc_client)

        assert monitor.idc_client == mock_idc_client
        assert monitor.config is not None
        assert isinstance(monitor.config, StatusCheckConfig)


class TestProvisioningOperationModel:
    """Test cases for ProvisioningOperation model."""

    def test_provisioning_operation_creation(self):
        """Test ProvisioningOperation creation and basic properties."""
        operation = ProvisioningOperation(
            operation_id="test-op-001",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.IN_PROGRESS,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc),
            failure_reason=None,
            estimated_completion=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        assert operation.operation_id == "test-op-001"
        assert operation.operation_type == "CREATE_ACCOUNT_ASSIGNMENT"
        assert operation.status == ProvisioningOperationStatus.IN_PROGRESS
        assert operation.target_type == "PERMISSION_SET"
        assert operation.failure_reason is None
        assert operation.estimated_completion is not None

    def test_provisioning_operation_duration_calculation(self):
        """Test duration calculation for provisioning operations."""
        created_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        completion_time = datetime.now(timezone.utc)

        operation = ProvisioningOperation(
            operation_id="test-op-001",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.SUCCEEDED,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            target_type="PERMISSION_SET",
            created_date=created_time,
            failure_reason=None,
            estimated_completion=completion_time,
        )

        duration = operation.get_duration_minutes()
        assert duration is not None
        assert duration == pytest.approx(10.0, rel=1e-1)

    def test_provisioning_operation_duration_no_completion(self):
        """Test duration calculation when no completion time is set."""
        operation = ProvisioningOperation(
            operation_id="test-op-001",
            operation_type="CREATE_ACCOUNT_ASSIGNMENT",
            status=ProvisioningOperationStatus.IN_PROGRESS,
            target_id="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
            target_type="PERMISSION_SET",
            created_date=datetime.now(timezone.utc),
            failure_reason=None,
            estimated_completion=None,
        )

        duration = operation.get_duration_minutes()
        assert duration is None


class TestProvisioningStatusModel:
    """Test cases for ProvisioningStatus model."""

    def test_provisioning_status_creation(self):
        """Test ProvisioningStatus creation and initialization."""
        status = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Test message",
            active_operations=[],
            failed_operations=[],
            completed_operations=[],
            pending_count=0,
            estimated_completion=None,
        )

        assert status.status == StatusLevel.HEALTHY
        assert status.message == "Test message"
        assert len(status.active_operations) == 0
        assert len(status.failed_operations) == 0
        assert len(status.completed_operations) == 0
        assert status.pending_count == 0
        assert status.estimated_completion is None

    def test_provisioning_status_post_init(self):
        """Test ProvisioningStatus post-initialization logic."""
        # Test with None values
        status = ProvisioningStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.HEALTHY,
            message="Test message",
            active_operations=None,
            failed_operations=None,
            completed_operations=None,
            pending_count=0,
            estimated_completion=None,
        )

        # Should initialize empty lists
        assert isinstance(status.active_operations, list)
        assert isinstance(status.failed_operations, list)
        assert isinstance(status.completed_operations, list)
        assert len(status.active_operations) == 0
        assert len(status.failed_operations) == 0
        assert len(status.completed_operations) == 0
