"""Summary statistics component for AWS Identity Center status monitoring."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from botocore.exceptions import ClientError

from .status_infrastructure import BaseStatusChecker, StatusCheckError
from .status_models import BaseStatusResult, StatusLevel, SummaryStatistics

logger = logging.getLogger(__name__)


class SummaryStatisticsCollector(BaseStatusChecker):
    """
    Collects summary statistics for AWS Identity Center deployment.

    Gathers comprehensive statistics including total counts of users, groups,
    permission sets, assignments, and active accounts with creation/modification
    date tracking for key metrics.
    """

    def __init__(self, idc_client, config=None):
        """
        Initialize the summary statistics collector.

        Args:
            idc_client: AWS Identity Center client wrapper
            config: Configuration for status checking operations
        """
        super().__init__(idc_client, config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def check_status(self) -> BaseStatusResult:
        """
        Collect comprehensive summary statistics.

        Returns:
            BaseStatusResult: Status result containing summary statistics
        """
        start_time = time.time()
        timestamp = datetime.now(timezone.utc)

        try:
            self.logger.info("Starting summary statistics collection")

            # Collect all statistics
            stats = await self._collect_summary_statistics()

            # Calculate collection duration
            collection_duration = time.time() - start_time

            # Create successful result
            result = BaseStatusResult(
                timestamp=timestamp,
                status=StatusLevel.HEALTHY,
                message=f"Summary statistics collected successfully in {collection_duration:.2f} seconds",
            )

            # Add statistics as details
            result.add_detail("summary_statistics", stats)
            result.add_detail("collection_duration_seconds", collection_duration)
            result.add_detail("statistics_timestamp", stats.last_updated.isoformat())

            self.logger.info(
                f"Summary statistics collection completed: {stats.total_users} users, "
                f"{stats.total_groups} groups, {stats.total_permission_sets} permission sets, "
                f"{stats.total_assignments} assignments across {stats.active_accounts} accounts"
            )

            return result

        except Exception as e:
            collection_duration = time.time() - start_time
            error_msg = f"Failed to collect summary statistics: {str(e)}"
            self.logger.error(error_msg)

            # Create error result
            result = BaseStatusResult(
                timestamp=timestamp, status=StatusLevel.CRITICAL, message=error_msg, errors=[str(e)]
            )

            result.add_detail("error_type", type(e).__name__)
            result.add_detail("collection_duration_seconds", collection_duration)
            result.add_detail("component", "SummaryStatisticsCollector")

            return result

    async def _collect_summary_statistics(self) -> SummaryStatistics:
        """
        Collect comprehensive summary statistics from Identity Center.

        Returns:
            SummaryStatistics: Complete summary statistics object
        """
        timestamp = datetime.now(timezone.utc)

        # Initialize statistics with defaults
        stats = SummaryStatistics(
            total_users=0,
            total_groups=0,
            total_permission_sets=0,
            total_assignments=0,
            active_accounts=0,
            last_updated=timestamp,
        )

        try:
            # Get Identity Center instance information
            instance_arn, identity_store_id = await self._get_instance_info()

            # Collect statistics in parallel for better performance
            if self.config and self.config.enable_parallel_checks:
                await self._collect_statistics_parallel(stats, instance_arn, identity_store_id)
            else:
                await self._collect_statistics_sequential(stats, instance_arn, identity_store_id)

            self.logger.debug(f"Statistics collection completed: {stats.__dict__}")

            return stats

        except Exception as e:
            self.logger.error(f"Error collecting summary statistics: {str(e)}")
            raise StatusCheckError(
                f"Failed to collect summary statistics: {str(e)}", "SummaryStatisticsCollector"
            ) from e

    async def _collect_statistics_parallel(
        self, stats: SummaryStatistics, instance_arn: str, identity_store_id: str
    ) -> None:
        """
        Collect statistics using parallel execution for better performance.

        Args:
            stats: SummaryStatistics object to populate
            instance_arn: Identity Center instance ARN
            identity_store_id: Identity store ID
        """
        # Create tasks for parallel execution
        tasks = [
            self._collect_user_statistics(stats, identity_store_id),
            self._collect_group_statistics(stats, identity_store_id),
            self._collect_permission_set_statistics(stats, instance_arn),
            self._collect_assignment_statistics(stats, instance_arn),
        ]

        # Execute all tasks in parallel
        await asyncio.gather(*tasks)

    async def _collect_statistics_sequential(
        self, stats: SummaryStatistics, instance_arn: str, identity_store_id: str
    ) -> None:
        """
        Collect statistics using sequential execution.

        Args:
            stats: SummaryStatistics object to populate
            instance_arn: Identity Center instance ARN
            identity_store_id: Identity store ID
        """
        await self._collect_user_statistics(stats, identity_store_id)
        await self._collect_group_statistics(stats, identity_store_id)
        await self._collect_permission_set_statistics(stats, instance_arn)
        await self._collect_assignment_statistics(stats, instance_arn)

    async def _collect_user_statistics(
        self, stats: SummaryStatistics, identity_store_id: str
    ) -> None:
        """
        Collect user statistics including counts and creation dates.

        Args:
            stats: SummaryStatistics object to populate
            identity_store_id: Identity store ID
        """
        try:
            self.logger.debug("Collecting user statistics")

            identity_store = self.idc_client.get_identity_store_client()
            user_count = 0
            user_creation_dates = {}

            # Use paginator to handle large numbers of users
            paginator = identity_store.get_paginator("list_users")
            page_iterator = paginator.paginate(IdentityStoreId=identity_store_id)

            for page in page_iterator:
                users = page.get("Users", [])
                user_count += len(users)

                # Collect creation dates for users
                for user in users:
                    user_id = user.get("UserId")
                    created_date = user.get("Meta", {}).get("Created")

                    if user_id and created_date:
                        # Parse the date string to datetime object
                        if isinstance(created_date, str):
                            try:
                                created_date = datetime.fromisoformat(
                                    created_date.replace("Z", "+00:00")
                                )
                            except ValueError:
                                # Handle different date formats
                                try:
                                    created_date = datetime.strptime(
                                        created_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                                    )
                                except ValueError:
                                    self.logger.warning(
                                        f"Could not parse user creation date: {created_date}"
                                    )
                                    continue

                        user_creation_dates[user_id] = created_date

            stats.total_users = user_count
            stats.user_creation_dates = user_creation_dates

            self.logger.debug(f"Collected statistics for {user_count} users")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            self.logger.error(f"AWS error collecting user statistics: {error_code} - {str(e)}")
            raise StatusCheckError(
                f"Failed to collect user statistics: {error_code}", "SummaryStatisticsCollector"
            ) from e
        except Exception as e:
            self.logger.error(f"Error collecting user statistics: {str(e)}")
            raise StatusCheckError(
                f"Failed to collect user statistics: {str(e)}", "SummaryStatisticsCollector"
            ) from e

    async def _collect_group_statistics(
        self, stats: SummaryStatistics, identity_store_id: str
    ) -> None:
        """
        Collect group statistics including counts and creation dates.

        Args:
            stats: SummaryStatistics object to populate
            identity_store_id: Identity store ID
        """
        try:
            self.logger.debug("Collecting group statistics")

            identity_store = self.idc_client.get_identity_store_client()
            group_count = 0
            group_creation_dates = {}

            # Use paginator to handle large numbers of groups
            paginator = identity_store.get_paginator("list_groups")
            page_iterator = paginator.paginate(IdentityStoreId=identity_store_id)

            for page in page_iterator:
                groups = page.get("Groups", [])
                group_count += len(groups)

                # Collect creation dates for groups
                for group in groups:
                    group_id = group.get("GroupId")
                    created_date = group.get("Meta", {}).get("Created")

                    if group_id and created_date:
                        # Parse the date string to datetime object
                        if isinstance(created_date, str):
                            try:
                                created_date = datetime.fromisoformat(
                                    created_date.replace("Z", "+00:00")
                                )
                            except ValueError:
                                # Handle different date formats
                                try:
                                    created_date = datetime.strptime(
                                        created_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                                    )
                                except ValueError:
                                    self.logger.warning(
                                        f"Could not parse group creation date: {created_date}"
                                    )
                                    continue

                        group_creation_dates[group_id] = created_date

            stats.total_groups = group_count
            stats.group_creation_dates = group_creation_dates

            self.logger.debug(f"Collected statistics for {group_count} groups")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            self.logger.error(f"AWS error collecting group statistics: {error_code} - {str(e)}")
            raise StatusCheckError(
                f"Failed to collect group statistics: {error_code}", "SummaryStatisticsCollector"
            ) from e
        except Exception as e:
            self.logger.error(f"Error collecting group statistics: {str(e)}")
            raise StatusCheckError(
                f"Failed to collect group statistics: {str(e)}", "SummaryStatisticsCollector"
            ) from e

    async def _collect_permission_set_statistics(
        self, stats: SummaryStatistics, instance_arn: str
    ) -> None:
        """
        Collect permission set statistics including counts and creation dates.

        Args:
            stats: SummaryStatistics object to populate
            instance_arn: Identity Center instance ARN
        """
        try:
            self.logger.debug("Collecting permission set statistics")

            sso_admin = self.idc_client.get_client("sso-admin")
            permission_set_count = 0
            permission_set_creation_dates = {}

            # Use paginator to handle large numbers of permission sets
            paginator = sso_admin.get_paginator("list_permission_sets")
            page_iterator = paginator.paginate(InstanceArn=instance_arn)

            for page in page_iterator:
                permission_set_arns = page.get("PermissionSets", [])
                permission_set_count += len(permission_set_arns)

                # Get detailed information for each permission set to collect creation dates
                for ps_arn in permission_set_arns:
                    try:
                        ps_details = sso_admin.describe_permission_set(
                            InstanceArn=instance_arn, PermissionSetArn=ps_arn
                        )

                        permission_set = ps_details.get("PermissionSet", {})
                        created_date = permission_set.get("CreatedDate")

                        if created_date:
                            permission_set_creation_dates[ps_arn] = created_date

                    except ClientError as e:
                        # Log warning but continue with other permission sets
                        self.logger.warning(
                            f"Could not get details for permission set {ps_arn}: {str(e)}"
                        )
                        continue

            stats.total_permission_sets = permission_set_count
            stats.permission_set_creation_dates = permission_set_creation_dates

            self.logger.debug(f"Collected statistics for {permission_set_count} permission sets")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            self.logger.error(
                f"AWS error collecting permission set statistics: {error_code} - {str(e)}"
            )
            raise StatusCheckError(
                f"Failed to collect permission set statistics: {error_code}",
                "SummaryStatisticsCollector",
            ) from e
        except Exception as e:
            self.logger.error(f"Error collecting permission set statistics: {str(e)}")
            raise StatusCheckError(
                f"Failed to collect permission set statistics: {str(e)}",
                "SummaryStatisticsCollector",
            ) from e

    async def _collect_assignment_statistics(
        self, stats: SummaryStatistics, instance_arn: str
    ) -> None:
        """
        Collect assignment statistics including total assignments and active accounts.

        Args:
            stats: SummaryStatistics object to populate
            instance_arn: Identity Center instance ARN
        """
        try:
            self.logger.debug("Collecting assignment statistics")

            sso_admin = self.idc_client.get_client("sso-admin")
            organizations = self.idc_client.get_client("organizations")

            total_assignments = 0
            active_accounts: Set[str] = set()

            # Get all accounts in the organization
            accounts = await self._get_all_accounts(organizations)

            # Get all permission sets
            permission_sets = await self._get_all_permission_sets(sso_admin, instance_arn)

            # Count assignments for each permission set and account combination
            for ps_arn in permission_sets:
                for account in accounts:
                    account_id = account["Id"]

                    try:
                        # List assignments for this permission set and account
                        paginator = sso_admin.get_paginator("list_account_assignments")
                        page_iterator = paginator.paginate(
                            InstanceArn=instance_arn, AccountId=account_id, PermissionSetArn=ps_arn
                        )

                        account_has_assignments = False
                        for page in page_iterator:
                            assignments = page.get("AccountAssignments", [])
                            if assignments:
                                total_assignments += len(assignments)
                                account_has_assignments = True

                        if account_has_assignments:
                            active_accounts.add(account_id)

                    except ClientError as e:
                        error_code = e.response.get("Error", {}).get("Code", "Unknown")
                        # Log warning but continue with other accounts/permission sets
                        self.logger.warning(
                            f"Could not list assignments for account {account_id}, "
                            f"permission set {ps_arn}: {error_code}"
                        )
                        continue

            stats.total_assignments = total_assignments
            stats.active_accounts = len(active_accounts)

            self.logger.debug(
                f"Collected assignment statistics: {total_assignments} assignments "
                f"across {len(active_accounts)} active accounts"
            )

        except Exception as e:
            self.logger.error(f"Error collecting assignment statistics: {str(e)}")
            raise StatusCheckError(
                f"Failed to collect assignment statistics: {str(e)}", "SummaryStatisticsCollector"
            ) from e

    async def _get_instance_info(self) -> tuple[str, str]:
        """
        Get Identity Center instance ARN and identity store ID.

        Returns:
            tuple: (instance_arn, identity_store_id)
        """
        try:
            sso_admin = self.idc_client.get_client("sso-admin")

            # List Identity Center instances
            response = sso_admin.list_instances()
            instances = response.get("Instances", [])

            if not instances:
                raise StatusCheckError(
                    "No Identity Center instances found", "SummaryStatisticsCollector"
                )

            # Use the first instance (typically there's only one)
            instance = instances[0]
            instance_arn = instance["InstanceArn"]
            identity_store_id = instance["IdentityStoreId"]

            return instance_arn, identity_store_id

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise StatusCheckError(
                f"Failed to get Identity Center instance info: {error_code}",
                "SummaryStatisticsCollector",
            ) from e

    async def _get_all_accounts(self, organizations_client) -> List[Dict[str, Any]]:
        """
        Get all accounts in the organization.

        Args:
            organizations_client: AWS Organizations client

        Returns:
            List[Dict[str, Any]]: List of account information
        """
        try:
            accounts = []

            # Use paginator to handle large numbers of accounts
            paginator = organizations_client.get_paginator("list_accounts")
            page_iterator = paginator.paginate()

            for page in page_iterator:
                page_accounts = page.get("Accounts", [])
                accounts.extend(page_accounts)

            return accounts

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            self.logger.warning(f"Could not list organization accounts: {error_code}")
            # Return empty list to continue with other statistics
            return []

    async def _get_all_permission_sets(self, sso_admin_client, instance_arn: str) -> List[str]:
        """
        Get all permission set ARNs.

        Args:
            sso_admin_client: SSO Admin client
            instance_arn: Identity Center instance ARN

        Returns:
            List[str]: List of permission set ARNs
        """
        try:
            permission_sets = []

            # Use paginator to handle large numbers of permission sets
            paginator = sso_admin_client.get_paginator("list_permission_sets")
            page_iterator = paginator.paginate(InstanceArn=instance_arn)

            for page in page_iterator:
                page_permission_sets = page.get("PermissionSets", [])
                permission_sets.extend(page_permission_sets)

            return permission_sets

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            raise StatusCheckError(
                f"Failed to list permission sets: {error_code}", "SummaryStatisticsCollector"
            ) from e

    def get_component_name(self) -> str:
        """Get the component name for identification."""
        return "SummaryStatisticsCollector"

    def get_component_version(self) -> str:
        """Get the component version."""
        return "1.0.0"

    def get_supported_checks(self) -> List[str]:
        """Get list of supported check types."""
        return ["summary_statistics", "statistics", "summary"]
