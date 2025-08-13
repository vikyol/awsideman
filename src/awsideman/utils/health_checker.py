"""Health checking component for AWS Identity Center status monitoring."""

import time
from datetime import datetime, timezone
from typing import Any, Dict

from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from .error_handler import handle_status_error
from .logging_config import get_status_logger
from .status_infrastructure import BaseStatusChecker, ConnectionError, PermissionError
from .status_models import HealthStatus, StatusLevel
from .timeout_handler import get_timeout_handler


class HealthChecker(BaseStatusChecker):
    """
    Health checker component for AWS Identity Center.

    Tests Identity Center connectivity and service availability,
    providing detailed health status with colored indicators and
    comprehensive error reporting.
    """

    def __init__(self, idc_client, config=None):
        """
        Initialize the health checker.

        Args:
            idc_client: AWS Identity Center client wrapper
            config: Status check configuration
        """
        super().__init__(idc_client, config)
        self.logger = get_status_logger("health_checker")
        self.timeout_handler = get_timeout_handler()

    async def check_status(self) -> HealthStatus:
        """
        Perform comprehensive health check of Identity Center instance.

        Returns:
            HealthStatus: Health check results with status level and details
        """
        self.logger.info("Starting comprehensive health check")
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)

        try:
            # Execute health check with timeout handling
            timeout_result = await self.timeout_handler.execute_with_timeout(
                self._perform_health_check,
                "health_check",
                timeout_seconds=30.0,
                context={"component": "HealthChecker"},
            )

            if timeout_result.success:
                health_status = timeout_result.result
                health_status.add_detail(
                    "check_duration_ms", timeout_result.duration_seconds * 1000
                )

                self.logger.info(
                    f"Health check completed: {health_status.status.value} in {timeout_result.duration_seconds:.2f}s",
                    extra={
                        "status": health_status.status.value,
                        "duration_ms": timeout_result.duration_seconds * 1000,
                        "service_available": health_status.service_available,
                    },
                )

                return health_status
            else:
                # Timeout or other error occurred
                error = timeout_result.error

                health_status = HealthStatus(
                    timestamp=timestamp,
                    status=StatusLevel.CRITICAL,
                    message=error.get_user_message() if error else "Health check failed",
                    service_available=False,
                    connectivity_status="Error",
                    response_time_ms=timeout_result.duration_seconds * 1000,
                    last_successful_check=None,
                )

                if error:
                    health_status.add_error(error.message)
                    health_status.add_detail("error_details", error.get_technical_details())

                health_status.add_detail("timeout_occurred", timeout_result.timeout_occurred)
                health_status.add_detail("retry_count", timeout_result.retry_count)

                return health_status

        except Exception as e:
            # Handle unexpected errors in timeout handling
            duration = time.time() - start_time

            status_error = handle_status_error(e, "HealthChecker", "check_status")

            self.logger.error(
                f"Critical error in health check: {str(e)}",
                extra={"error_type": type(e).__name__, "duration_seconds": duration},
            )

            health_status = HealthStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=status_error.get_user_message(),
                service_available=False,
                connectivity_status="Error",
                response_time_ms=duration * 1000,
                last_successful_check=None,
            )

            health_status.add_error(status_error.message)
            health_status.add_detail("error_details", status_error.get_technical_details())
            health_status.add_detail("component", "HealthChecker")

            return health_status

    async def _perform_health_check(self) -> HealthStatus:
        """
        Perform the actual health check operations.

        Returns:
            HealthStatus: Health check results
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)

        # Test basic connectivity with timeout
        connectivity_result = await self.timeout_handler.execute_with_timeout(
            self._check_connectivity, "connectivity_check", timeout_seconds=15.0
        )

        # Test service availability with timeout
        service_result = await self.timeout_handler.execute_with_timeout(
            self._check_service_availability, "service_availability_check", timeout_seconds=20.0
        )

        # Process results
        connectivity_data = (
            connectivity_result.result
            if connectivity_result.success
            else {
                "status": "Error",
                "available": False,
                "errors": (
                    [connectivity_result.error.message]
                    if connectivity_result.error
                    else ["Connectivity check failed"]
                ),
            }
        )

        service_data = (
            service_result.result
            if service_result.success
            else {
                "available": False,
                "status": "Error",
                "errors": (
                    [service_result.error.message]
                    if service_result.error
                    else ["Service check failed"]
                ),
            }
        )

        # Calculate response time
        response_time_ms = (time.time() - start_time) * 1000

        # Determine overall health status
        overall_status = self._determine_health_status(connectivity_data, service_data)

        # Create health status result
        health_status = HealthStatus(
            timestamp=timestamp,
            status=overall_status["status"],
            message=overall_status["message"],
            service_available=service_data["available"],
            connectivity_status=connectivity_data["status"],
            response_time_ms=response_time_ms,
            last_successful_check=(
                timestamp if overall_status["status"] == StatusLevel.HEALTHY else None
            ),
        )

        # Add detailed information
        health_status.add_detail("connectivity_details", connectivity_data)
        health_status.add_detail("service_details", service_data)
        health_status.add_detail("response_time_ms", response_time_ms)

        # Add timeout information
        health_status.add_detail(
            "connectivity_timeout_occurred", connectivity_result.timeout_occurred
        )
        health_status.add_detail("service_timeout_occurred", service_result.timeout_occurred)

        # Add any errors encountered
        if connectivity_data.get("errors"):
            health_status.errors.extend(connectivity_data["errors"])
        if service_data.get("errors"):
            health_status.errors.extend(service_data["errors"])

        return health_status

    async def _check_connectivity(self) -> Dict[str, Any]:
        """
        Test basic connectivity to Identity Center service.

        Returns:
            Dict containing connectivity status and details
        """
        self.logger.debug("Starting connectivity check")

        try:
            # Attempt to get the Identity Center client
            client = self.idc_client.get_sso_admin_client()

            # Test basic connectivity with a lightweight operation
            # List instances is a good connectivity test as it requires minimal permissions
            response = client.list_instances()

            if response and "Instances" in response:
                instances_count = len(response["Instances"])

                self.logger.debug(
                    f"Connectivity check successful: {instances_count} instances found"
                )

                if instances_count > 0:
                    return {
                        "status": "Connected",
                        "available": True,
                        "instances_found": instances_count,
                        "errors": [],
                    }
                else:
                    self.logger.warning("Connected to Identity Center but no instances found")
                    return {
                        "status": "Connected but no instances",
                        "available": True,
                        "instances_found": 0,
                        "errors": ["No Identity Center instances found"],
                    }
            else:
                self.logger.warning("Unexpected response format from list_instances")
                return {
                    "status": "Connected but no instances",
                    "available": True,
                    "instances_found": 0,
                    "errors": ["No Identity Center instances found"],
                }

        except Exception as e:
            # Use centralized error handling

            status_error = handle_status_error(e, "HealthChecker", "connectivity_check")

            self.logger.error(
                f"Connectivity check failed: {str(e)}",
                extra={"error_type": type(e).__name__, "error_code": status_error.get_error_code()},
            )

            # Map error categories to connectivity status
            if isinstance(e, NoCredentialsError):
                status = "Authentication Failed"
            elif isinstance(e, EndpointConnectionError):
                status = "Connection Failed"
            elif isinstance(e, ClientError):
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if error_code in ["AccessDenied", "UnauthorizedOperation"]:
                    status = "Permission Denied"
                else:
                    status = "API Error"
            else:
                status = "Unknown Error"

            return {
                "status": status,
                "available": False,
                "error_type": type(e).__name__,
                "error_code": status_error.get_error_code(),
                "errors": [status_error.get_user_message()],
                "remediation_steps": [
                    step.description for step in status_error.remediation_steps[:2]
                ],
            }

    async def _check_service_availability(self) -> Dict[str, Any]:
        """
        Test Identity Center service availability and basic functionality.

        Returns:
            Dict containing service availability status and details
        """
        self.logger.debug("Starting service availability check")

        try:
            client = self.idc_client.get_sso_admin_client()

            # Test multiple service endpoints to verify availability
            checks = []

            # Check 1: List instances (basic service availability)
            try:
                self.logger.debug("Testing list_instances endpoint")
                instances_response = client.list_instances()
                instances_count = len(instances_response.get("Instances", []))

                checks.append(
                    {
                        "check": "list_instances",
                        "status": "success",
                        "instances_count": instances_count,
                    }
                )

                self.logger.debug(f"list_instances check successful: {instances_count} instances")

            except Exception as e:
                status_error = handle_status_error(e, "HealthChecker", "list_instances_check")

                checks.append(
                    {
                        "check": "list_instances",
                        "status": "failed",
                        "error": status_error.get_user_message(),
                        "error_code": status_error.get_error_code(),
                    }
                )

                self.logger.warning(f"list_instances check failed: {str(e)}")

            # Check 2: If we have instances, test permission set listing
            if (
                checks
                and checks[0]["status"] == "success"
                and checks[0].get("instances_count", 0) > 0
            ):
                try:
                    # Get the first instance ARN for further testing
                    instance_arn = instances_response["Instances"][0]["InstanceArn"]

                    self.logger.debug(
                        f"Testing list_permission_sets endpoint for instance {instance_arn}"
                    )

                    # Test permission set listing (common operation)
                    client.list_permission_sets(InstanceArn=instance_arn, MaxResults=1)

                    checks.append(
                        {
                            "check": "list_permission_sets",
                            "status": "success",
                            "instance_arn": instance_arn,
                            "permission_sets_accessible": True,
                        }
                    )

                    self.logger.debug("list_permission_sets check successful")

                except Exception as e:
                    status_error = handle_status_error(
                        e, "HealthChecker", "list_permission_sets_check"
                    )

                    checks.append(
                        {
                            "check": "list_permission_sets",
                            "status": "failed",
                            "error_code": status_error.get_error_code(),
                            "error": status_error.get_user_message(),
                        }
                    )

                    self.logger.warning(f"list_permission_sets check failed: {str(e)}")

            # Analyze check results
            successful_checks = [c for c in checks if c["status"] == "success"]
            failed_checks = [c for c in checks if c["status"] == "failed"]

            self.logger.debug(
                f"Service availability check completed: {len(successful_checks)}/{len(checks)} checks successful"
            )

            if len(successful_checks) == len(checks):
                return {
                    "available": True,
                    "status": "Fully Available",
                    "checks_performed": len(checks),
                    "successful_checks": len(successful_checks),
                    "check_details": checks,
                    "errors": [],
                }
            elif len(successful_checks) > 0:
                return {
                    "available": True,
                    "status": "Partially Available",
                    "checks_performed": len(checks),
                    "successful_checks": len(successful_checks),
                    "failed_checks": len(failed_checks),
                    "check_details": checks,
                    "errors": [
                        f"Some service checks failed: {len(failed_checks)} of {len(checks)}"
                    ],
                }
            else:
                return {
                    "available": False,
                    "status": "Service Unavailable",
                    "checks_performed": len(checks),
                    "successful_checks": 0,
                    "failed_checks": len(failed_checks),
                    "check_details": checks,
                    "errors": ["All service availability checks failed"],
                }

        except Exception as e:
            # Handle unexpected errors in service availability check

            status_error = handle_status_error(e, "HealthChecker", "service_availability_check")

            self.logger.error(f"Service availability check failed with unexpected error: {str(e)}")

            return {
                "available": False,
                "status": "Service Check Failed",
                "error_type": type(e).__name__,
                "error_code": status_error.get_error_code(),
                "errors": [status_error.get_user_message()],
                "remediation_steps": [
                    step.description for step in status_error.remediation_steps[:2]
                ],
            }

    def _determine_health_status(
        self, connectivity_result: Dict[str, Any], service_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Determine overall health status based on connectivity and service checks.

        Args:
            connectivity_result: Results from connectivity check
            service_result: Results from service availability check

        Returns:
            Dict containing overall status and message
        """
        # Connection failure takes precedence
        if not connectivity_result.get("available", False):
            if connectivity_result.get("error_type") == "NoCredentialsError":
                return {
                    "status": StatusLevel.CONNECTION_FAILED,
                    "message": "AWS credentials not configured or invalid",
                }
            elif connectivity_result.get("error_type") == "EndpointConnectionError":
                return {
                    "status": StatusLevel.CONNECTION_FAILED,
                    "message": "Cannot connect to AWS Identity Center service",
                }
            elif connectivity_result.get("error_type") == "PermissionError":
                return {
                    "status": StatusLevel.CONNECTION_FAILED,
                    "message": "Insufficient permissions to access Identity Center",
                }
            else:
                return {
                    "status": StatusLevel.CONNECTION_FAILED,
                    "message": f"Connection failed: {connectivity_result.get('status', 'Unknown error')}",
                }

        # Service availability issues
        if not service_result.get("available", False):
            return {
                "status": StatusLevel.CRITICAL,
                "message": "Identity Center service is not available",
            }

        # Partial service availability
        if service_result.get("status") == "Partially Available":
            failed_checks = service_result.get("failed_checks", 0)
            total_checks = service_result.get("checks_performed", 0)
            return {
                "status": StatusLevel.WARNING,
                "message": f"Identity Center partially available ({failed_checks}/{total_checks} checks failed)",
            }

        # Check for warnings
        warnings = []
        if connectivity_result.get("instances_found", 0) == 0:
            warnings.append("No Identity Center instances found")

        if service_result.get("errors"):
            warnings.extend(service_result["errors"])

        if warnings:
            return {
                "status": StatusLevel.WARNING,
                "message": f'Identity Center healthy with warnings: {"; ".join(warnings)}',
            }

        # All checks passed
        return {
            "status": StatusLevel.HEALTHY,
            "message": "Identity Center is healthy and fully operational",
        }

    def _create_health_error_result(self, error, timestamp: datetime) -> HealthStatus:
        """
        Create a health status result for error conditions.

        Args:
            error: The error that occurred
            timestamp: Timestamp of the check

        Returns:
            HealthStatus: Error health status result
        """
        if isinstance(error, ConnectionError):
            status = StatusLevel.CONNECTION_FAILED
            connectivity_status = "Connection Failed"
            service_available = False
        elif isinstance(error, PermissionError):
            status = StatusLevel.CONNECTION_FAILED
            connectivity_status = "Permission Denied"
            service_available = False
        else:
            status = StatusLevel.CRITICAL
            connectivity_status = "Error"
            service_available = False

        health_status = HealthStatus(
            timestamp=timestamp,
            status=status,
            message=str(error),
            service_available=service_available,
            connectivity_status=connectivity_status,
            response_time_ms=None,
            last_successful_check=None,
        )

        health_status.add_error(str(error))
        health_status.add_detail("error_type", type(error).__name__)
        health_status.add_detail("component", "HealthChecker")

        return health_status

    def get_colored_status_indicator(self, status: StatusLevel) -> str:
        """
        Get a colored status indicator for display.

        Args:
            status: Status level

        Returns:
            str: Colored status indicator
        """
        indicators = {
            StatusLevel.HEALTHY: "🟢 HEALTHY",
            StatusLevel.WARNING: "🟡 WARNING",
            StatusLevel.CRITICAL: "🔴 CRITICAL",
            StatusLevel.CONNECTION_FAILED: "⚫ CONNECTION FAILED",
        }
        return indicators.get(status, "❓ UNKNOWN")

    def format_health_summary(self, health_status: HealthStatus) -> str:
        """
        Format a concise health summary for display.

        Args:
            health_status: Health status to format

        Returns:
            str: Formatted health summary
        """
        indicator = self.get_colored_status_indicator(health_status.status)

        summary_parts = [f"Status: {indicator}", f"Message: {health_status.message}"]

        if health_status.response_time_ms is not None:
            summary_parts.append(f"Response Time: {health_status.response_time_ms:.2f}ms")

        if health_status.connectivity_status:
            summary_parts.append(f"Connectivity: {health_status.connectivity_status}")

        if health_status.errors:
            summary_parts.append(f"Errors: {len(health_status.errors)}")

        return " | ".join(summary_parts)
