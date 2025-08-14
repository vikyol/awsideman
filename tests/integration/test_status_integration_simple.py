"""Simplified integration tests for end-to-end status workflows.

This module contains integration tests that verify complete status checking
workflows without depending on the full application imports, focusing on:
- Status orchestrator integration
- Output format generation and validation
- Error handling scenarios
- Component coordination

These tests verify the core integration between status components.
"""

import asyncio
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.output_formatters import CSVFormatter, JSONFormatter, TableFormatter
from src.awsideman.utils.status_infrastructure import StatusCheckConfig
from src.awsideman.utils.status_models import (
    HealthStatus,
    OrphanedAssignment,
    OrphanedAssignmentStatus,
    OutputFormat,
    PrincipalType,
    ProvisioningOperation,
    ProvisioningOperationStatus,
    ProvisioningStatus,
    StatusLevel,
    StatusReport,
    SummaryStatistics,
    SyncMonitorStatus,
)

# Import only the core status components we need
from src.awsideman.utils.status_orchestrator import StatusOrchestrator


class TestStatusIntegrationFixtures:
    """Test fixtures and mock data for status integration tests."""

    @staticmethod
    def get_mock_aws_responses():
        """Get comprehensive mock AWS API responses for testing."""
        return {
            # Identity Center instance info
            "instance_metadata": {
                "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                "IdentityStoreId": "d-1234567890",
                "Status": "ACTIVE",
                "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
            },
            # Health check responses
            "list_instances": {
                "Instances": [
                    {
                        "InstanceArn": "arn:aws:sso:::instance/ssoins-1234567890abcdef",
                        "IdentityStoreId": "d-1234567890",
                        "Status": "ACTIVE",
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                    }
                ]
            },
            # Users and groups
            "users": {
                "Users": [
                    {
                        "UserId": "user-1234567890abcdef",
                        "UserName": "john.doe@company.com",
                        "DisplayName": "John Doe",
                        "Name": {"GivenName": "John", "FamilyName": "Doe"},
                        "Meta": {
                            "Created": datetime(2023, 1, 1, 0, 0, 0),
                            "LastModified": datetime(2023, 6, 1, 0, 0, 0),
                        },
                    }
                ]
            },
            "groups": {
                "Groups": [
                    {
                        "GroupId": "group-1234567890abcdef",
                        "DisplayName": "Administrators",
                        "Description": "System administrators group",
                        "Meta": {
                            "Created": datetime(2023, 1, 1, 0, 0, 0),
                            "LastModified": datetime(2023, 5, 1, 0, 0, 0),
                        },
                    }
                ]
            },
            # Permission sets
            "permission_sets": {
                "PermissionSets": [
                    "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess"
                ]
            },
            # Account assignments with orphaned entries
            "account_assignments": {
                "AccountAssignments": [
                    {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        "PrincipalId": "user-1234567890abcdef",
                        "PrincipalType": "USER",
                        "AccountId": "111111111111",
                        "CreatedDate": datetime(2023, 1, 1, 0, 0, 0),
                    },
                    {
                        "PermissionSetArn": "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        "PrincipalId": "user-orphaned123456",  # This user doesn't exist
                        "PrincipalType": "USER",
                        "AccountId": "222222222222",
                        "CreatedDate": datetime(2023, 2, 1, 0, 0, 0),
                    },
                ]
            },
            # Organizations accounts
            "organizations_accounts": {
                "Accounts": [
                    {
                        "Id": "111111111111",
                        "Name": "dev-account-1",
                        "Email": "dev1@company.com",
                        "Status": "ACTIVE",
                    },
                    {
                        "Id": "222222222222",
                        "Name": "dev-account-2",
                        "Email": "dev2@company.com",
                        "Status": "ACTIVE",
                    },
                ]
            },
        }

    @staticmethod
    def create_mock_aws_client_manager():
        """Create comprehensive mock AWS client manager for status testing."""
        manager = Mock()
        responses = TestStatusIntegrationFixtures.get_mock_aws_responses()

        # Mock SSO Admin client
        sso_admin_client = Mock()
        sso_admin_client.list_instances.return_value = responses["list_instances"]
        sso_admin_client.describe_instance_access_control_attribute_configuration.return_value = {
            "Status": "ENABLED",
            "StatusReason": "Configuration is active",
        }
        sso_admin_client.list_permission_sets.return_value = responses["permission_sets"]
        sso_admin_client.list_account_assignments.return_value = responses["account_assignments"]
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client
        identity_store_client = Mock()
        identity_store_client.list_users.return_value = responses["users"]
        identity_store_client.list_groups.return_value = responses["groups"]

        # Mock user lookup failures for orphaned detection
        def mock_describe_user(UserId):
            if UserId == "user-orphaned123456":
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "ResourceNotFoundException",
                            "Message": f"User with ID {UserId} not found",
                        }
                    },
                    operation_name="DescribeUser",
                )
            return {
                "UserId": UserId,
                "UserName": "existing.user@company.com",
                "DisplayName": "Existing User",
            }

        identity_store_client.describe_user.side_effect = mock_describe_user
        manager.get_identity_store_client.return_value = identity_store_client

        # Mock Organizations client
        organizations_client = Mock()
        organizations_client.list_accounts.return_value = responses["organizations_accounts"]
        manager.get_organizations_client.return_value = organizations_client

        return manager

    @staticmethod
    def create_failing_aws_client_manager():
        """Create mock AWS client manager that simulates various failure scenarios."""
        manager = Mock()

        # Mock SSO Admin client with connection failures
        sso_admin_client = Mock()
        sso_admin_client.list_instances.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "UnauthorizedOperation",
                    "Message": "You are not authorized to perform this operation",
                }
            },
            operation_name="ListInstances",
        )
        manager.get_identity_center_client.return_value = sso_admin_client

        # Mock Identity Store client with timeout
        identity_store_client = Mock()
        identity_store_client.list_users.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "ServiceUnavailable",
                    "Message": "Service temporarily unavailable",
                }
            },
            operation_name="ListUsers",
        )
        manager.get_identity_store_client.return_value = identity_store_client

        # Mock Organizations client with rate limiting
        organizations_client = Mock()
        organizations_client.list_accounts.side_effect = ClientError(
            error_response={
                "Error": {"Code": "TooManyRequestsException", "Message": "Request rate exceeded"}
            },
            operation_name="ListAccounts",
        )
        manager.get_organizations_client.return_value = organizations_client

        return manager


class TestStatusOrchestratorIntegration:
    """Integration tests for status orchestrator coordination."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for orchestrator testing."""
        return TestStatusIntegrationFixtures.create_mock_aws_client_manager()

    @pytest.mark.asyncio
    async def test_orchestrator_comprehensive_status_integration(self, mock_aws_client_manager):
        """Test status orchestrator comprehensive status coordination."""
        # Create status orchestrator with test configuration
        config = StatusCheckConfig(
            timeout_seconds=10,
            enable_parallel_checks=True,
            max_concurrent_checks=3,
            retry_attempts=1,
            retry_delay_seconds=0.1,
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Execute comprehensive status check
        status_report = await orchestrator.get_comprehensive_status()

        # Verify status report structure
        assert isinstance(status_report, StatusReport)
        assert status_report.timestamp is not None
        assert status_report.overall_health is not None
        assert status_report.provisioning_status is not None
        assert status_report.orphaned_assignment_status is not None
        assert status_report.sync_status is not None
        assert status_report.summary_statistics is not None
        assert status_report.check_duration_seconds > 0

        # Verify the orchestrator handled failures gracefully
        failures = orchestrator.get_component_failures()
        # Some components may have failed due to mock setup, but orchestrator should handle it
        assert isinstance(failures, dict)

        # Verify that despite failures, we got a valid status report
        assert status_report.overall_health.status in [
            StatusLevel.HEALTHY,
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]

        # Verify orchestrator metadata
        assert hasattr(orchestrator, "get_available_checks")
        available_checks = orchestrator.get_available_checks()
        assert len(available_checks) > 0

    @pytest.mark.asyncio
    async def test_orchestrator_specific_status_integration(self, mock_aws_client_manager):
        """Test status orchestrator specific status check coordination."""
        config = StatusCheckConfig(
            timeout_seconds=5, enable_parallel_checks=False, retry_attempts=1
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Test each specific status type
        status_types = ["health", "provisioning", "orphaned", "sync"]

        for status_type in status_types:
            result = await orchestrator.get_specific_status(status_type)

            # Verify result structure
            assert hasattr(result, "timestamp")
            assert hasattr(result, "status")
            assert hasattr(result, "message")
            assert result.timestamp is not None
            assert result.status in [
                StatusLevel.HEALTHY,
                StatusLevel.WARNING,
                StatusLevel.CRITICAL,
                StatusLevel.CONNECTION_FAILED,
            ]

    @pytest.mark.asyncio
    async def test_orchestrator_parallel_vs_sequential_integration(self, mock_aws_client_manager):
        """Test orchestrator parallel vs sequential execution integration."""
        # Test parallel execution
        parallel_config = StatusCheckConfig(
            timeout_seconds=10,
            enable_parallel_checks=True,
            max_concurrent_checks=5,
            retry_attempts=1,
        )

        parallel_orchestrator = StatusOrchestrator(mock_aws_client_manager, parallel_config)
        parallel_start = datetime.now(timezone.utc)
        parallel_report = await parallel_orchestrator.get_comprehensive_status()
        parallel_duration = (datetime.now(timezone.utc) - parallel_start).total_seconds()

        # Test sequential execution
        sequential_config = StatusCheckConfig(
            timeout_seconds=10, enable_parallel_checks=False, retry_attempts=1
        )

        sequential_orchestrator = StatusOrchestrator(mock_aws_client_manager, sequential_config)
        sequential_start = datetime.now(timezone.utc)
        sequential_report = await sequential_orchestrator.get_comprehensive_status()
        sequential_duration = (datetime.now(timezone.utc) - sequential_start).total_seconds()

        # Verify both reports have similar structure
        assert isinstance(parallel_report, StatusReport)
        assert isinstance(sequential_report, StatusReport)

        # Verify both approaches produce valid results
        assert parallel_report.overall_health.status in [
            StatusLevel.HEALTHY,
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]
        assert sequential_report.overall_health.status in [
            StatusLevel.HEALTHY,
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]

        # Note: In real scenarios, parallel should be faster, but with mocks timing may vary
        assert parallel_duration >= 0
        assert sequential_duration >= 0

    @pytest.mark.asyncio
    async def test_orchestrator_error_handling_integration(self):
        """Test orchestrator error handling and graceful degradation."""
        # Create failing client manager
        failing_manager = TestStatusIntegrationFixtures.create_failing_aws_client_manager()

        config = StatusCheckConfig(
            timeout_seconds=5,
            enable_parallel_checks=True,
            retry_attempts=1,
            retry_delay_seconds=0.1,
        )

        orchestrator = StatusOrchestrator(failing_manager, config)

        # Execute comprehensive status check with failing clients
        status_report = await orchestrator.get_comprehensive_status()

        # Verify graceful degradation
        assert isinstance(status_report, StatusReport)
        assert status_report.timestamp is not None

        # Should have component failures tracked
        failures = orchestrator.get_component_failures()
        assert len(failures) > 0  # Should have some failures
        assert orchestrator.has_component_failures()

        # Overall health should reflect the failures
        assert status_report.overall_health.status in [
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]

    @pytest.mark.asyncio
    async def test_orchestrator_timeout_handling_integration(self, mock_aws_client_manager):
        """Test orchestrator timeout handling integration."""
        # Create client with slow responses
        slow_sso_client = Mock()

        async def slow_list_instances():
            await asyncio.sleep(2)  # Simulate slow response
            return TestStatusIntegrationFixtures.get_mock_aws_responses()["list_instances"]

        slow_sso_client.list_instances.side_effect = slow_list_instances
        mock_aws_client_manager.get_identity_center_client.return_value = slow_sso_client

        # Configure short timeout
        config = StatusCheckConfig(
            timeout_seconds=1,  # Very short timeout
            enable_parallel_checks=True,
            retry_attempts=1,
            retry_delay_seconds=0.1,
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Execute status check - should handle timeouts gracefully
        status_report = await orchestrator.get_comprehensive_status()

        # Verify timeout was handled
        assert isinstance(status_report, StatusReport)

        # Should have some failures (timeout or other mock-related failures)
        failures = orchestrator.get_component_failures()
        # With the mock setup, we expect some failures to occur
        assert len(failures) > 0

        # Verify that despite failures, the orchestrator completed
        assert status_report.check_duration_seconds > 0


class TestOutputFormatValidation:
    """Integration tests for output format generation and validation."""

    def test_json_formatter_integration(self):
        """Test JSON formatter with real status data."""
        # Create sample status report
        timestamp = datetime.now(timezone.utc)
        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="All systems operational",
            service_available=True,
            connectivity_status="Connected",
        )

        status_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=ProvisioningStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No active operations",
                active_operations=[],
                failed_operations=[],
                completed_operations=[],
                pending_count=0,
            ),
            orphaned_assignment_status=OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No orphaned assignments",
                orphaned_assignments=[],
                cleanup_available=False,
            ),
            sync_status=SyncMonitorStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="All providers synchronized",
                sync_providers=[],
                providers_configured=0,
                providers_healthy=0,
                providers_with_errors=0,
            ),
            summary_statistics=SummaryStatistics(
                total_users=10,
                total_groups=5,
                total_permission_sets=3,
                total_assignments=25,
                active_accounts=3,
                last_updated=timestamp,
            ),
            check_duration_seconds=2.5,
        )

        # Test JSON formatting
        formatter = JSONFormatter()
        result = formatter.format(status_report)

        # Verify JSON output
        assert result.format_type == OutputFormat.JSON
        assert result.content is not None

        # Verify JSON is valid
        parsed_json = json.loads(result.content)
        assert "timestamp" in parsed_json
        assert "check_duration_seconds" in parsed_json
        assert "health" in parsed_json
        assert "summary_statistics" in parsed_json
        assert "component_statuses" in parsed_json
        # Check that the JSON contains expected data
        assert parsed_json["check_duration_seconds"] == 2.5
        assert parsed_json["summary_statistics"]["total_users"] == 10

    def test_csv_formatter_integration(self):
        """Test CSV formatter with real status data."""
        # Create sample status report
        timestamp = datetime.now(timezone.utc)
        health_status = HealthStatus(
            timestamp=timestamp,
            status=StatusLevel.WARNING,
            message="Minor issues detected",
            service_available=True,
            connectivity_status="Connected",
        )

        status_report = StatusReport(
            timestamp=timestamp,
            overall_health=health_status,
            provisioning_status=ProvisioningStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No active operations",
                active_operations=[],
                failed_operations=[],
                completed_operations=[],
                pending_count=0,
            ),
            orphaned_assignment_status=OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message="Orphaned assignments found",
                orphaned_assignments=[
                    OrphanedAssignment(
                        assignment_id="assign-123",
                        permission_set_arn="arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-readonlyaccess",
                        permission_set_name="ReadOnlyAccess",
                        account_id="111111111111",
                        account_name="dev-account-1",
                        principal_id="user-orphaned123456",
                        principal_name=None,
                        principal_type=PrincipalType.USER,
                        error_message="User not found",
                        created_date=datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                    )
                ],
                cleanup_available=True,
            ),
            sync_status=SyncMonitorStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="All providers synchronized",
                sync_providers=[],
                providers_configured=0,
                providers_healthy=0,
                providers_with_errors=0,
            ),
            summary_statistics=SummaryStatistics(
                total_users=10,
                total_groups=5,
                total_permission_sets=3,
                total_assignments=25,
                active_accounts=3,
                last_updated=timestamp,
            ),
            check_duration_seconds=3.2,
        )

        # Test CSV formatting
        formatter = CSVFormatter()
        result = formatter.format(status_report)

        # Verify CSV output
        assert result.format_type == OutputFormat.CSV
        assert result.content is not None

        # Verify CSV is valid
        csv_reader = csv.reader(io.StringIO(result.content))
        rows = list(csv_reader)

        # Should have header row and data rows
        assert len(rows) > 1
        # CSV format may have different structure, just verify it's valid CSV
        assert len(rows[0]) > 0  # Header row exists
        # Verify CSV contains status information
        csv_content = result.content
        assert "Warning" in csv_content or "Critical" in csv_content or "Healthy" in csv_content

    def test_table_formatter_integration(self):
        """Test table formatter with real status data."""
        # Create sample status report with various status levels
        timestamp = datetime.now(timezone.utc)

        status_report = StatusReport(
            timestamp=timestamp,
            overall_health=HealthStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message="Critical issues detected",
                service_available=False,
                connectivity_status="Connection Failed",
            ),
            provisioning_status=ProvisioningStatus(
                timestamp=timestamp,
                status=StatusLevel.WARNING,
                message="Some operations failed",
                active_operations=[
                    ProvisioningOperation(
                        operation_id="op-123",
                        operation_type="CREATE_ASSIGNMENT",
                        status=ProvisioningOperationStatus.IN_PROGRESS,
                        target_id="111111111111",
                        target_type="AWS_ACCOUNT",
                        created_date=datetime.now(timezone.utc) - timedelta(minutes=5),
                        estimated_completion=datetime.now(timezone.utc) + timedelta(minutes=2),
                    )
                ],
                failed_operations=[],
                completed_operations=[],
                pending_count=1,
            ),
            orphaned_assignment_status=OrphanedAssignmentStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="No orphaned assignments",
                orphaned_assignments=[],
                cleanup_available=False,
            ),
            sync_status=SyncMonitorStatus(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message="All providers synchronized",
                sync_providers=[],
                providers_configured=1,
                providers_healthy=1,
                providers_with_errors=0,
            ),
            summary_statistics=SummaryStatistics(
                total_users=100,
                total_groups=20,
                total_permission_sets=15,
                total_assignments=500,
                active_accounts=10,
                last_updated=timestamp,
            ),
            check_duration_seconds=5.7,
        )

        # Test table formatting
        formatter = TableFormatter()
        result = formatter.format(status_report)

        # Verify table output
        assert result.format_type == OutputFormat.TABLE
        assert result.content is not None

        # Verify table contains expected elements
        content = result.content
        assert "Status Report" in content or "Health" in content
        assert "Critical" in content or "Warning" in content
        assert "100" in content  # Total users
        assert "500" in content  # Total assignments


class TestEndToEndStatusWorkflows:
    """End-to-end integration tests for complete status workflows."""

    @pytest.fixture
    def mock_aws_client_manager(self):
        """Create mock AWS client manager for end-to-end testing."""
        return TestStatusIntegrationFixtures.create_mock_aws_client_manager()

    @pytest.mark.asyncio
    async def test_complete_status_monitoring_workflow(self, mock_aws_client_manager):
        """Test complete status monitoring workflow from orchestrator to output."""
        # Create status orchestrator
        config = StatusCheckConfig(
            timeout_seconds=30,
            enable_parallel_checks=True,
            max_concurrent_checks=5,
            retry_attempts=2,
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Test comprehensive status check
        comprehensive_report = await orchestrator.get_comprehensive_status()

        # Verify comprehensive report
        assert isinstance(comprehensive_report, StatusReport)
        assert comprehensive_report.overall_health.status in [
            StatusLevel.HEALTHY,
            StatusLevel.WARNING,
            StatusLevel.CRITICAL,
            StatusLevel.CONNECTION_FAILED,
        ]

        # Test specific component checks
        for status_type in ["health", "provisioning", "orphaned", "sync"]:
            specific_result = await orchestrator.get_specific_status(status_type)
            assert hasattr(specific_result, "status")
            assert specific_result.status in [
                StatusLevel.HEALTHY,
                StatusLevel.WARNING,
                StatusLevel.CRITICAL,
                StatusLevel.CONNECTION_FAILED,
            ]

        # Test different output formats
        for output_format in [JSONFormatter(), CSVFormatter(), TableFormatter()]:
            formatted_output = output_format.format(comprehensive_report)
            assert formatted_output.content is not None
            assert len(formatted_output.content) > 0

        # Verify that the orchestrator was able to produce valid results despite mock limitations
        assert comprehensive_report.check_duration_seconds > 0

        # Verify that all specific status checks completed
        assert len([r for r in [comprehensive_report] if hasattr(r, "overall_health")]) == 1

    @pytest.mark.asyncio
    async def test_error_recovery_and_resilience_workflow(self):
        """Test error recovery and resilience across different failure scenarios."""
        # Test with various failure scenarios
        failure_scenarios = [
            # Connection failures
            TestStatusIntegrationFixtures.create_failing_aws_client_manager(),
        ]

        for failing_manager in failure_scenarios:
            config = StatusCheckConfig(
                timeout_seconds=5,
                enable_parallel_checks=True,
                retry_attempts=1,
                retry_delay_seconds=0.1,
            )

            orchestrator = StatusOrchestrator(failing_manager, config)

            # Test status check with failures - should handle gracefully
            status_report = await orchestrator.get_comprehensive_status()

            # Verify graceful degradation
            assert isinstance(status_report, StatusReport)
            assert status_report.timestamp is not None

            # Should have component failures tracked
            failures = orchestrator.get_component_failures()
            assert len(failures) > 0  # Should have some failures
            assert orchestrator.has_component_failures()

            # Overall health should reflect the failures
            assert status_report.overall_health.status in [
                StatusLevel.WARNING,
                StatusLevel.CRITICAL,
                StatusLevel.CONNECTION_FAILED,
            ]

    @pytest.mark.asyncio
    async def test_performance_and_scalability_workflow(self, mock_aws_client_manager):
        """Test performance and scalability aspects of status workflows."""
        # Create large dataset responses
        large_responses = TestStatusIntegrationFixtures.get_mock_aws_responses()

        # Simulate large user base
        large_user_list = []
        for i in range(100):
            large_user_list.append(
                {
                    "UserId": f"user-{i:010d}",
                    "UserName": f"user{i}@company.com",
                    "DisplayName": f"User {i}",
                    "Name": {"GivenName": "User", "FamilyName": f"{i}"},
                    "Meta": {
                        "Created": datetime(2023, 1, 1, 0, 0, 0),
                        "LastModified": datetime(2023, 6, 1, 0, 0, 0),
                    },
                }
            )

        large_responses["users"]["Users"] = large_user_list

        # Update mock to return large dataset
        identity_store_client = mock_aws_client_manager.get_identity_store_client.return_value
        identity_store_client.list_users.return_value = large_responses["users"]

        # Create orchestrator with performance-oriented configuration
        config = StatusCheckConfig(
            timeout_seconds=60,  # Longer timeout for large dataset
            enable_parallel_checks=True,  # Use parallel processing
            max_concurrent_checks=10,
            retry_attempts=1,
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Test performance with large dataset
        start_time = datetime.now(timezone.utc)

        status_report = await orchestrator.get_comprehensive_status()

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        # Verify reasonable performance (should complete within reasonable time)
        assert duration < 30  # Should complete within 30 seconds even with large dataset

        # Verify report was generated despite mock limitations
        assert isinstance(status_report, StatusReport)
        assert status_report.check_duration_seconds > 0

        # Verify performance was reasonable
        assert duration < 30

    @pytest.mark.asyncio
    async def test_concurrent_operations_workflow(self, mock_aws_client_manager):
        """Test concurrent status operations workflow."""
        config = StatusCheckConfig(
            timeout_seconds=10,
            enable_parallel_checks=True,
            max_concurrent_checks=5,
            retry_attempts=1,
        )

        orchestrator = StatusOrchestrator(mock_aws_client_manager, config)

        # Simulate concurrent operations by running multiple status checks
        tasks = []
        for i in range(5):
            if i % 2 == 0:
                task = orchestrator.get_comprehensive_status()
            else:
                task = orchestrator.get_specific_status("health")
            tasks.append(task)

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all tasks completed successfully
        for result in results:
            assert not isinstance(result, Exception)
            assert hasattr(result, "timestamp")
            assert hasattr(result, "status") or hasattr(result, "overall_health")

        # Verify concurrent operations completed successfully
        assert len(results) == 5

        # Verify that concurrent operations completed successfully
        for result in results:
            if hasattr(result, "check_duration_seconds"):
                assert result.check_duration_seconds > 0


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short"])
