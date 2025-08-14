"""Sync monitoring component for AWS Identity Center status monitoring."""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from .status_infrastructure import BaseStatusChecker, StatusCheckError
from .status_models import StatusLevel, SyncMonitorStatus, SyncProviderType, SyncStatus

logger = logging.getLogger(__name__)


class SyncMonitor(BaseStatusChecker):
    """
    Sync monitor component for AWS Identity Center.

    Tracks external identity provider synchronization status, checks last sync times,
    detects overdue synchronization, and provides error detection with remediation
    suggestions for failed synchronization.
    """

    def __init__(self, idc_client, config=None):
        """
        Initialize the sync monitor.

        Args:
            idc_client: AWS Identity Center client wrapper
            config: Status check configuration
        """
        super().__init__(idc_client, config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Configuration for sync monitoring
        self.sync_overdue_threshold_hours = 24  # Default threshold for overdue sync
        self.sync_warning_threshold_hours = 12  # Warning threshold

        # Cache for sync status tracking
        self._sync_cache: Dict[str, SyncStatus] = {}
        self._last_check_time: Optional[datetime] = None

    async def check_status(self) -> SyncMonitorStatus:
        """
        Perform comprehensive sync status check.

        Returns:
            SyncMonitorStatus: Sync monitoring results with provider status and health
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)

        try:
            # Get all configured identity providers
            sync_providers = await self._get_sync_providers()

            # Check sync status for each provider
            provider_statuses = []
            for provider in sync_providers:
                try:
                    sync_status = await self._check_provider_sync_status(provider)
                    if sync_status:
                        provider_statuses.append(sync_status)
                except Exception as e:
                    self.logger.warning(
                        f"Error checking sync status for provider {provider.get('name', 'unknown')}: {str(e)}"
                    )
                    # Create error status for this provider
                    error_status = self._create_provider_error_status(provider, str(e))
                    provider_statuses.append(error_status)

            # Determine overall sync monitoring status
            overall_status = self._determine_sync_status(provider_statuses)

            # Calculate provider health metrics
            providers_configured = len(provider_statuses)
            providers_healthy = len([p for p in provider_statuses if p.is_healthy()])
            providers_with_errors = len([p for p in provider_statuses if p.has_sync_errors()])

            # Create sync monitor status result
            sync_monitor_status = SyncMonitorStatus(
                timestamp=timestamp,
                status=overall_status["status"],
                message=overall_status["message"],
                sync_providers=provider_statuses,
                providers_configured=providers_configured,
                providers_healthy=providers_healthy,
                providers_with_errors=providers_with_errors,
            )

            # Add detailed information
            sync_monitor_status.add_detail("check_duration_ms", (time.time() - start_time) * 1000)
            sync_monitor_status.add_detail(
                "overdue_threshold_hours", self.sync_overdue_threshold_hours
            )
            sync_monitor_status.add_detail(
                "warning_threshold_hours", self.sync_warning_threshold_hours
            )

            # Add provider type breakdown
            provider_types = self._get_provider_type_breakdown(provider_statuses)
            sync_monitor_status.add_detail("provider_types", provider_types)

            # Add overdue and error provider details
            overdue_providers = sync_monitor_status.get_overdue_providers()
            error_providers = sync_monitor_status.get_error_providers()

            if overdue_providers:
                sync_monitor_status.add_detail(
                    "overdue_providers", [p.provider_name for p in overdue_providers]
                )

            if error_providers:
                sync_monitor_status.add_detail(
                    "error_providers", [p.provider_name for p in error_providers]
                )

            # Add any errors encountered during monitoring
            if overall_status.get("errors"):
                sync_monitor_status.errors.extend(overall_status["errors"])

            self.logger.info(
                f"Sync status check completed: {overall_status['status']} "
                f"({providers_configured} providers, {providers_healthy} healthy)"
            )

            # Update cache and last check time
            self._update_sync_cache(provider_statuses)
            self._last_check_time = timestamp

            return sync_monitor_status

        except Exception as e:
            # Handle unexpected errors
            self.logger.error(f"Unexpected error in sync status check: {str(e)}")

            # Create error result
            sync_monitor_status = SyncMonitorStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=f"Sync status check failed: {str(e)}",
                sync_providers=[],
                providers_configured=0,
                providers_healthy=0,
                providers_with_errors=0,
            )

            sync_monitor_status.add_error(str(e))
            sync_monitor_status.add_detail("error_type", type(e).__name__)
            sync_monitor_status.add_detail("component", "SyncMonitor")

            return sync_monitor_status

    async def _get_sync_providers(self) -> List[Dict[str, Any]]:
        """
        Get all configured external identity providers.

        Returns:
            List[Dict]: List of configured identity providers
        """
        providers = []

        try:
            client = self.idc_client.get_sso_admin_client()

            # Get all Identity Center instances
            instances_response = client.list_instances()
            instances = instances_response.get("Instances", [])

            if not instances:
                self.logger.warning("No Identity Center instances found")
                return providers

            # Check each instance for external identity providers
            for instance in instances:
                instance_arn = instance["InstanceArn"]

                try:
                    # Check if external identity source is configured
                    # Note: AWS Identity Center API doesn't have a direct method to list all identity sources
                    # We need to infer this from the instance configuration

                    # Get instance details to check identity source
                    instance_details = await self._get_instance_identity_source(instance_arn)

                    if instance_details and instance_details.get("external_providers"):
                        providers.extend(instance_details["external_providers"])

                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    self.logger.warning(
                        f"Error checking identity sources for instance {instance_arn}: {error_code}"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Unexpected error checking instance {instance_arn}: {str(e)}"
                    )

        except Exception as e:
            self.logger.error(f"Error getting sync providers: {str(e)}")
            raise StatusCheckError(
                f"Failed to retrieve identity providers: {str(e)}", "SyncMonitor"
            )

        return providers

    async def _get_instance_identity_source(self, instance_arn: str) -> Optional[Dict[str, Any]]:
        """
        Get identity source configuration for an instance.

        Args:
            instance_arn: Identity Center instance ARN

        Returns:
            Dict containing identity source information
        """
        try:
            identity_store_client = self.idc_client.get_identity_store_client()

            # In AWS Identity Center, external identity sources are configured at the instance level
            # However, there's no direct API to list identity sources
            # We need to infer this from other indicators

            # Check if there are any external groups or users that indicate external sync
            external_providers = []

            # Method 1: Check for external groups (groups not created directly in IDC)
            try:
                groups_response = identity_store_client.list_groups(
                    IdentityStoreId=instance_arn.replace("sso", "identitystore")
                )
                groups = groups_response.get("Groups", [])

                # Look for groups that might be externally synced
                external_groups = []
                for group in groups:
                    # External groups often have specific naming patterns or metadata
                    if self._is_external_group(group):
                        external_groups.append(group)

                if external_groups:
                    # Infer provider type from group characteristics
                    provider_type = self._infer_provider_type_from_groups(external_groups)

                    external_providers.append(
                        {
                            "name": f"External Provider ({provider_type})",
                            "type": provider_type,
                            "instance_arn": instance_arn,
                            "detected_from": "groups",
                            "external_objects_count": len(external_groups),
                        }
                    )

            except ClientError as e:
                # If we can't access the identity store, we might still be able to detect external sync
                # through other means
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                self.logger.debug(f"Cannot access identity store for {instance_arn}: {error_code}")

            # Method 2: Check for external users
            try:
                users_response = identity_store_client.list_users(
                    IdentityStoreId=instance_arn.replace("sso", "identitystore")
                )
                users = users_response.get("Users", [])

                # Look for users that might be externally synced
                external_users = []
                for user in users:
                    if self._is_external_user(user):
                        external_users.append(user)

                if external_users and not external_providers:
                    # Only add if we haven't already detected from groups
                    provider_type = self._infer_provider_type_from_users(external_users)

                    external_providers.append(
                        {
                            "name": f"External Provider ({provider_type})",
                            "type": provider_type,
                            "instance_arn": instance_arn,
                            "detected_from": "users",
                            "external_objects_count": len(external_users),
                        }
                    )

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                self.logger.debug(f"Cannot access users for {instance_arn}: {error_code}")

            # If no external providers detected, check if this is a standalone instance
            if not external_providers:
                # This might be a standalone Identity Center instance with no external sync
                return {
                    "instance_arn": instance_arn,
                    "external_providers": [],
                    "sync_type": "standalone",
                }

            return {
                "instance_arn": instance_arn,
                "external_providers": external_providers,
                "sync_type": "external",
            }

        except Exception as e:
            self.logger.warning(f"Error getting identity source for {instance_arn}: {str(e)}")
            return None

    def _is_external_group(self, group: Dict[str, Any]) -> bool:
        """
        Determine if a group is externally synced.

        Args:
            group: Group information from AWS API

        Returns:
            bool: True if group appears to be externally synced
        """
        # Check for indicators that suggest external sync
        group_name = group.get("DisplayName", "").lower()

        # Common patterns for externally synced groups
        external_indicators = [
            "\\",  # Active Directory format (any domain\group)
            "@",  # Email domain format
            "cn=",  # LDAP format
            "ou=",  # Organizational Unit format
        ]

        for indicator in external_indicators:
            if indicator in group_name:
                return True

        # Check for external ID or source attributes
        external_ids = group.get("ExternalIds", [])
        if external_ids:
            return True

        # Check metadata for sync indicators
        meta = group.get("Meta", {})
        if meta.get("ResourceType") and "external" in meta.get("ResourceType", "").lower():
            return True

        return False

    def _is_external_user(self, user: Dict[str, Any]) -> bool:
        """
        Determine if a user is externally synced.

        Args:
            user: User information from AWS API

        Returns:
            bool: True if user appears to be externally synced
        """
        # Check for external ID or source attributes
        external_ids = user.get("ExternalIds", [])
        if external_ids:
            return True

        # Check username format for external patterns
        username = user.get("UserName", "").lower()

        # Common patterns for externally synced users
        external_indicators = [
            "\\",  # Active Directory format (any domain\user)
            "@",  # Email format (common for external sync)
        ]

        for indicator in external_indicators:
            if indicator in username:
                return True

        # Check for specific attributes that indicate external sync
        attributes = user.get("Attributes", {})
        if attributes.get("employeeId") or attributes.get("department"):
            # These are often populated by external directory sync
            return True

        return False

    def _infer_provider_type_from_groups(self, groups: List[Dict[str, Any]]) -> SyncProviderType:
        """
        Infer the identity provider type from group characteristics.

        Args:
            groups: List of external groups

        Returns:
            SyncProviderType: Inferred provider type
        """
        # Analyze group names and attributes to infer provider type
        for group in groups:
            group_name = group.get("DisplayName", "").lower()

            # Active Directory indicators
            if "\\" in group_name or "cn=" in group_name or "ou=" in group_name:
                return SyncProviderType.ACTIVE_DIRECTORY

            # Azure AD indicators
            if any(term in group_name for term in ["azure", "aad", "office365", "o365"]):
                return SyncProviderType.AZURE_AD

        # Default to external SAML if we can't determine specific type
        return SyncProviderType.EXTERNAL_SAML

    def _infer_provider_type_from_users(self, users: List[Dict[str, Any]]) -> SyncProviderType:
        """
        Infer the identity provider type from user characteristics.

        Args:
            users: List of external users

        Returns:
            SyncProviderType: Inferred provider type
        """
        # Analyze user names and attributes to infer provider type
        for user in users:
            username = user.get("UserName", "").lower()

            # Active Directory indicators
            if "\\" in username:
                return SyncProviderType.ACTIVE_DIRECTORY

            # Azure AD indicators (often uses email format)
            emails = user.get("Emails", [])
            for email in emails:
                email_value = email.get("Value", "").lower()
                if any(
                    domain in email_value for domain in ["outlook.com", "hotmail.com", "live.com"]
                ):
                    return SyncProviderType.AZURE_AD

        # Default to external SAML
        return SyncProviderType.EXTERNAL_SAML

    async def _check_provider_sync_status(self, provider: Dict[str, Any]) -> Optional[SyncStatus]:
        """
        Check synchronization status for a specific provider.

        Args:
            provider: Provider configuration

        Returns:
            SyncStatus: Sync status for the provider
        """
        try:
            provider_name = provider.get("name", "Unknown Provider")
            provider_type = SyncProviderType(provider.get("type", SyncProviderType.EXTERNAL_SAML))

            # Get last sync information
            # Note: AWS Identity Center doesn't provide direct sync status APIs
            # We need to infer sync status from other indicators

            sync_info = await self._get_provider_sync_info(provider)

            # Create sync status
            sync_status = SyncStatus(
                provider_name=provider_name,
                provider_type=provider_type,
                last_sync_time=sync_info.get("last_sync_time"),
                sync_status=sync_info.get("sync_status", "Unknown"),
                next_sync_time=sync_info.get("next_sync_time"),
                error_message=sync_info.get("error_message"),
                sync_duration_minutes=sync_info.get("sync_duration_minutes"),
                objects_synced=sync_info.get("objects_synced"),
            )

            return sync_status

        except Exception as e:
            self.logger.error(
                f"Error checking sync status for provider {provider.get('name', 'unknown')}: {str(e)}"
            )
            return None

    async def _get_provider_sync_info(self, provider: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get sync information for a provider.

        Args:
            provider: Provider configuration

        Returns:
            Dict containing sync information
        """
        try:
            # Since AWS doesn't provide direct sync status APIs, we need to infer
            # sync status from available information

            instance_arn = provider.get("instance_arn")
            detected_from = provider.get("detected_from")

            # Method 1: Check object modification times to infer last sync
            last_sync_time = await self._infer_last_sync_time(instance_arn, detected_from)

            # Method 2: Check for sync errors in CloudTrail or other logs
            # This would require additional permissions and setup
            error_message = None

            # Method 3: Estimate sync status based on object freshness
            sync_status = "Active" if last_sync_time else "Unknown"

            # Check if sync appears overdue
            if last_sync_time:
                # Ensure both datetimes are naive for comparison
                current_time = datetime.now(timezone.utc)
                if last_sync_time.tzinfo is not None:
                    last_sync_time = last_sync_time.replace(tzinfo=None)
                age_hours = (current_time - last_sync_time).total_seconds() / 3600
                if age_hours > self.sync_overdue_threshold_hours:
                    sync_status = "Overdue"
                    error_message = f"Last sync was {age_hours:.1f} hours ago (threshold: {self.sync_overdue_threshold_hours}h)"
                elif age_hours > self.sync_warning_threshold_hours:
                    sync_status = "Warning"

            # Estimate objects synced
            objects_synced = provider.get("external_objects_count", 0)

            return {
                "last_sync_time": last_sync_time,
                "sync_status": sync_status,
                "next_sync_time": None,  # AWS doesn't provide scheduled sync info
                "error_message": error_message,
                "sync_duration_minutes": None,  # Cannot determine without direct API
                "objects_synced": objects_synced,
            }

        except Exception as e:
            self.logger.warning(f"Error getting sync info for provider: {str(e)}")
            return {
                "last_sync_time": None,
                "sync_status": "Error",
                "error_message": f"Failed to retrieve sync information: {str(e)}",
            }

    async def _infer_last_sync_time(
        self, instance_arn: str, detected_from: str
    ) -> Optional[datetime]:
        """
        Infer the last sync time from object modification times.

        Args:
            instance_arn: Identity Center instance ARN
            detected_from: How external objects were detected ('groups' or 'users')

        Returns:
            datetime: Estimated last sync time or None
        """

        def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
            """Parse timestamp string to naive datetime."""
            try:
                if timestamp_str.endswith("Z"):
                    # Handle UTC timezone
                    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                else:
                    dt = datetime.fromisoformat(timestamp_str)

                # Convert to naive UTC for comparison
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)

                return dt
            except (ValueError, AttributeError):
                return None

        try:
            identity_store_client = self.idc_client.get_identity_store_client()
            identity_store_id = instance_arn.replace("sso", "identitystore")

            latest_modification = None

            if detected_from == "groups":
                # Check group modification times
                try:
                    groups_response = identity_store_client.list_groups(
                        IdentityStoreId=identity_store_id
                    )
                    groups = groups_response.get("Groups", [])

                    for group in groups:
                        if self._is_external_group(group):
                            meta = group.get("Meta", {})
                            last_modified = meta.get("LastModified")
                            if last_modified:
                                if isinstance(last_modified, str):
                                    modified_time = parse_timestamp(last_modified)
                                    if modified_time and (
                                        not latest_modification
                                        or modified_time > latest_modification
                                    ):
                                        latest_modification = modified_time
                                elif isinstance(last_modified, datetime):
                                    # Ensure datetime is naive for comparison
                                    if last_modified.tzinfo is not None:
                                        last_modified = last_modified.replace(tzinfo=None)
                                    if (
                                        not latest_modification
                                        or last_modified > latest_modification
                                    ):
                                        latest_modification = last_modified

                except ClientError:
                    pass  # Ignore access errors

            elif detected_from == "users":
                # Check user modification times
                try:
                    users_response = identity_store_client.list_users(
                        IdentityStoreId=identity_store_id
                    )
                    users = users_response.get("Users", [])

                    for user in users:
                        if self._is_external_user(user):
                            meta = user.get("Meta", {})
                            last_modified = meta.get("LastModified")
                            if last_modified:
                                if isinstance(last_modified, str):
                                    modified_time = parse_timestamp(last_modified)
                                    if modified_time and (
                                        not latest_modification
                                        or modified_time > latest_modification
                                    ):
                                        latest_modification = modified_time
                                elif isinstance(last_modified, datetime):
                                    # Ensure datetime is naive for comparison
                                    if last_modified.tzinfo is not None:
                                        last_modified = last_modified.replace(tzinfo=None)
                                    if (
                                        not latest_modification
                                        or last_modified > latest_modification
                                    ):
                                        latest_modification = last_modified

                except ClientError:
                    pass  # Ignore access errors

            return latest_modification

        except Exception as e:
            self.logger.warning(f"Error inferring last sync time: {str(e)}")
            return None

    def _create_provider_error_status(
        self, provider: Dict[str, Any], error_message: str
    ) -> SyncStatus:
        """
        Create an error sync status for a provider.

        Args:
            provider: Provider configuration
            error_message: Error message

        Returns:
            SyncStatus: Error status for the provider
        """
        provider_name = provider.get("name", "Unknown Provider")
        provider_type = SyncProviderType(provider.get("type", SyncProviderType.EXTERNAL_SAML))

        return SyncStatus(
            provider_name=provider_name,
            provider_type=provider_type,
            last_sync_time=None,
            sync_status="Error",
            next_sync_time=None,
            error_message=error_message,
            sync_duration_minutes=None,
            objects_synced=None,
        )

    def _determine_sync_status(self, provider_statuses: List[SyncStatus]) -> Dict[str, Any]:
        """
        Determine overall sync monitoring status based on provider states.

        Args:
            provider_statuses: List of provider sync statuses

        Returns:
            Dict containing overall status and message
        """
        if not provider_statuses:
            return {
                "status": StatusLevel.HEALTHY,
                "message": "No external identity providers configured",
                "errors": [],
            }

        # Count providers by status
        healthy_providers = [p for p in provider_statuses if p.is_healthy()]
        error_providers = [p for p in provider_statuses if p.has_sync_errors()]
        overdue_providers = [
            p for p in provider_statuses if p.is_sync_overdue(self.sync_overdue_threshold_hours)
        ]
        warning_providers = [
            p
            for p in provider_statuses
            if p.is_sync_overdue(self.sync_warning_threshold_hours)
            and not p.is_sync_overdue(self.sync_overdue_threshold_hours)
        ]

        total_providers = len(provider_statuses)

        # Determine status level
        if error_providers:
            error_rate = len(error_providers) / total_providers * 100

            # Only consider it critical if we have multiple providers and most are failing
            if (
                total_providers > 1 and error_rate > 50
            ):  # More than 50% have errors with multiple providers
                return {
                    "status": StatusLevel.CRITICAL,
                    "message": f"High sync error rate: {error_rate:.1f}% ({len(error_providers)} of {total_providers} providers have errors)",
                    "errors": [f"Providers with errors: {len(error_providers)}"],
                }
            else:
                return {
                    "status": StatusLevel.WARNING,
                    "message": f"Some sync providers have errors: {len(error_providers)} of {total_providers} providers",
                    "errors": [f"Providers with errors: {len(error_providers)}"],
                }

        # Check for overdue synchronization
        if overdue_providers:
            return {
                "status": StatusLevel.WARNING,
                "message": f"Overdue synchronization detected: {len(overdue_providers)} of {total_providers} providers overdue",
                "errors": [f"Overdue providers: {len(overdue_providers)}"],
            }

        # Check for warning-level delays
        if warning_providers:
            return {
                "status": StatusLevel.WARNING,
                "message": f"Sync delays detected: {len(warning_providers)} of {total_providers} providers approaching sync threshold",
                "errors": [],
            }

        # All providers healthy
        if len(healthy_providers) == total_providers:
            return {
                "status": StatusLevel.HEALTHY,
                "message": f"All identity providers synchronized successfully ({total_providers} providers)",
                "errors": [],
            }

        # Mixed status
        return {
            "status": StatusLevel.WARNING,
            "message": f"Mixed sync status: {len(healthy_providers)} healthy, {total_providers - len(healthy_providers)} with issues",
            "errors": [],
        }

    def _get_provider_type_breakdown(self, provider_statuses: List[SyncStatus]) -> Dict[str, int]:
        """
        Get breakdown of providers by type.

        Args:
            provider_statuses: List of provider statuses

        Returns:
            Dict mapping provider types to counts
        """
        breakdown = {}
        for provider in provider_statuses:
            provider_type = provider.provider_type.value
            breakdown[provider_type] = breakdown.get(provider_type, 0) + 1
        return breakdown

    def _update_sync_cache(self, provider_statuses: List[SyncStatus]) -> None:
        """
        Update the internal sync status cache.

        Args:
            provider_statuses: Provider statuses to cache
        """
        try:
            # Update cache with new statuses
            for provider_status in provider_statuses:
                self._sync_cache[provider_status.provider_name] = provider_status

            # Clean up old entries (older than 7 days)
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=7)
            providers_to_remove = []

            for provider_name, status in self._sync_cache.items():
                if status.last_sync_time and status.last_sync_time < cutoff_time:
                    providers_to_remove.append(provider_name)

            for provider_name in providers_to_remove:
                del self._sync_cache[provider_name]

            self.logger.debug(f"Updated sync cache: {len(self._sync_cache)} providers cached")

        except Exception as e:
            self.logger.warning(f"Error updating sync cache: {str(e)}")

    def get_sync_health_summary(self, sync_status: SyncMonitorStatus) -> str:
        """
        Get a concise sync health summary for display.

        Args:
            sync_status: Sync monitor status to format

        Returns:
            str: Formatted sync health summary
        """
        if not sync_status.has_providers_configured():
            return "No external identity providers configured"

        summary_parts = [
            f"Status: {sync_status.status.value}",
            f"Providers: {sync_status.providers_configured}",
            f"Healthy: {sync_status.providers_healthy}",
        ]

        if sync_status.providers_with_errors > 0:
            summary_parts.append(f"Errors: {sync_status.providers_with_errors}")

        overdue_count = len(sync_status.get_overdue_providers())
        if overdue_count > 0:
            summary_parts.append(f"Overdue: {overdue_count}")

        health_percentage = sync_status.get_health_percentage()
        summary_parts.append(f"Health: {health_percentage:.1f}%")

        return " | ".join(summary_parts)

    def get_remediation_suggestions(self, sync_status: SyncMonitorStatus) -> List[str]:
        """
        Get remediation suggestions for sync issues.

        Args:
            sync_status: Sync monitor status

        Returns:
            List of remediation suggestions
        """
        suggestions = []

        if not sync_status.has_providers_configured():
            suggestions.append(
                "Consider configuring external identity providers for centralized user management"
            )
            return suggestions

        # Suggestions for error providers
        error_providers = sync_status.get_error_providers()
        if error_providers:
            suggestions.append("Check identity provider connectivity and credentials")
            suggestions.append("Verify network connectivity to external identity sources")
            suggestions.append("Review Identity Center logs for detailed error information")

            for provider in error_providers:
                if provider.error_message:
                    if "permission" in provider.error_message.lower():
                        suggestions.append(
                            f"Check permissions for {provider.provider_name} identity source"
                        )
                    elif "connection" in provider.error_message.lower():
                        suggestions.append(
                            f"Verify network connectivity to {provider.provider_name}"
                        )

        # Suggestions for overdue providers
        overdue_providers = sync_status.get_overdue_providers()
        if overdue_providers:
            suggestions.append("Check if scheduled synchronization is properly configured")
            suggestions.append("Verify that identity provider sync schedules are active")

            for provider in overdue_providers:
                age_hours = provider.get_sync_age_hours()
                if age_hours and age_hours > 48:  # More than 2 days
                    suggestions.append(
                        f"Consider manual sync trigger for {provider.provider_name} (last sync: {age_hours:.1f}h ago)"
                    )

        # General suggestions
        if sync_status.get_health_percentage() < 100:
            suggestions.append("Monitor Identity Center CloudTrail logs for sync-related events")
            suggestions.append("Consider setting up CloudWatch alarms for sync failures")

        return suggestions
