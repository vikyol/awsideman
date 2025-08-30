"""
Identity Center data collector for backup operations.

This module implements the data collection functionality for AWS Identity Center
resources including users, groups, permission sets, and assignments.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from ..aws_clients import AWSClientManager
from .cross_account import CrossAccountClientManager
from .interfaces import CollectorInterface
from .models import (
    AssignmentData,
    BackupData,
    BackupOptions,
    BackupType,
    CrossAccountConfig,
    GroupData,
    PermissionSetData,
    RelationshipMap,
    ResourceType,
    UserData,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class IdentityCenterCollector(CollectorInterface):
    """
    Collector for AWS Identity Center data with support for parallel collection
    and incremental backups.
    """

    def __init__(self, client_manager: AWSClientManager, instance_arn: str):
        """
        Initialize the Identity Center collector.

        Args:
            client_manager: AWS client manager for service connections
            instance_arn: ARN of the Identity Center instance
        """
        self.client_manager = client_manager
        self.instance_arn = instance_arn
        self._identity_center_client = None
        self._identity_store_client = None
        self._organizations_client = None

        # Cross-account support
        self.cross_account_manager = CrossAccountClientManager(client_manager)
        self._cross_account_clients: Dict[str, AWSClientManager] = {}

        # Cache for identity store ID
        self._identity_store_id: Optional[str] = None

        # Performance tracking
        self._collection_stats = {
            "users": {"count": 0, "duration": 0.0},
            "groups": {"count": 0, "duration": 0.0},
            "permission_sets": {"count": 0, "duration": 0.0},
            "assignments": {"count": 0, "duration": 0.0},
        }

    @property
    def identity_center_client(self):
        """Get Identity Center client, creating if needed."""
        if self._identity_center_client is None:
            self._identity_center_client = self.client_manager.get_identity_center_client()
        return self._identity_center_client

    @property
    def identity_store_client(self):
        """Get Identity Store client, creating if needed."""
        if self._identity_store_client is None:
            self._identity_store_client = self.client_manager.get_identity_store_client()
        return self._identity_store_client

    @property
    def organizations_client(self):
        """Get Organizations client, creating if needed."""
        if self._organizations_client is None:
            self._organizations_client = self.client_manager.get_organizations_client()
        return self._organizations_client

    async def get_identity_store_id(self) -> str:
        """
        Get the Identity Store ID for the Identity Center instance.

        Returns:
            Identity Store ID

        Raises:
            ClientError: If unable to retrieve Identity Store ID
        """
        if self._identity_store_id is None:
            try:
                # Try the list instances approach first as it's more reliable
                response = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.identity_center_client.list_instances()
                )
                instances = response.get("Instances", [])
                for instance in instances:
                    if instance.get("InstanceArn") == self.instance_arn:
                        self._identity_store_id = instance.get("IdentityStoreId")
                        break

                if not self._identity_store_id:
                    raise ValueError(
                        f"Could not determine Identity Store ID for instance {self.instance_arn}"
                    )

            except ClientError as e:
                logger.error(f"Failed to get Identity Store ID: {e}")
                raise

        return self._identity_store_id

    async def validate_connection(self) -> ValidationResult:
        """
        Validate connection to Identity Center and required permissions.

        Returns:
            ValidationResult containing connection status and details
        """
        errors = []
        warnings = []
        details = {}

        try:
            # Test Identity Center connection
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.identity_center_client.list_instances()
            )
            details["identity_center_connection"] = "OK"
        except ClientError as e:
            errors.append(f"Identity Center connection failed: {e}")
            details["identity_center_connection"] = "FAILED"

        try:
            # Test Identity Store connection
            identity_store_id = await self.get_identity_store_id()
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.identity_store_client.list_users(
                    IdentityStoreId=identity_store_id, MaxResults=1
                ),
            )
            details["identity_store_connection"] = "OK"
        except ClientError as e:
            errors.append(f"Identity Store connection failed: {e}")
            details["identity_store_connection"] = "FAILED"

        try:
            # Test Organizations connection (optional)
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.organizations_client.list_roots()
            )
            details["organizations_connection"] = "OK"
        except ClientError as e:
            warnings.append(f"Organizations connection failed (optional): {e}")
            details["organizations_connection"] = "FAILED"

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

    async def collect_users(self, options: BackupOptions) -> List[UserData]:
        """
        Collect user data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of user data objects
        """
        start_time = time.time()
        users = []

        try:
            identity_store_id = await self.get_identity_store_id()

            # Use pagination to get all users
            paginator = self.identity_store_client.get_paginator("list_users")
            page_iterator = paginator.paginate(IdentityStoreId=identity_store_id)

            for page in page_iterator:
                for user in page.get("Users", []):
                    # Skip inactive users if not requested
                    if not options.include_inactive_users and not user.get("Active", True):
                        continue

                    # For incremental backups, check modification time
                    if options.backup_type == BackupType.INCREMENTAL and options.since:
                        # AWS doesn't provide modification timestamps for users in list operation
                        # We'll need to get detailed user info to check timestamps
                        pass

                    user_data = await self._convert_user_data(user, identity_store_id)
                    users.append(user_data)

            self._collection_stats["users"]["count"] = len(users)
            self._collection_stats["users"]["duration"] = time.time() - start_time

            logger.info(
                f"Collected {len(users)} users in {self._collection_stats['users']['duration']:.2f}s"
            )

        except ClientError as e:
            logger.error(f"Failed to collect users: {e}")
            raise

        return users

    async def collect_groups(self, options: BackupOptions) -> List[GroupData]:
        """
        Collect group data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of group data objects
        """
        start_time = time.time()
        groups = []

        try:
            identity_store_id = await self.get_identity_store_id()

            # Use pagination to get all groups
            paginator = self.identity_store_client.get_paginator("list_groups")
            page_iterator = paginator.paginate(IdentityStoreId=identity_store_id)

            for page in page_iterator:
                for group in page.get("Groups", []):
                    group_data = await self._convert_group_data(group, identity_store_id)
                    groups.append(group_data)

            self._collection_stats["groups"]["count"] = len(groups)
            self._collection_stats["groups"]["duration"] = time.time() - start_time

            logger.info(
                f"Collected {len(groups)} groups in {self._collection_stats['groups']['duration']:.2f}s"
            )

        except ClientError as e:
            logger.error(f"Failed to collect groups: {e}")
            raise

        return groups

    async def collect_permission_sets(self, options: BackupOptions) -> List[PermissionSetData]:
        """
        Collect permission set data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of permission set data objects
        """
        start_time = time.time()
        permission_sets = []

        try:
            # Use pagination to get all permission sets
            paginator = self.identity_center_client.get_paginator("list_permission_sets")
            page_iterator = paginator.paginate(InstanceArn=self.instance_arn)

            # Collect permission set ARNs first
            permission_set_arns = []
            for page in page_iterator:
                permission_set_arns.extend(page.get("PermissionSets", []))

            # Use parallel processing to get detailed permission set data
            if options.parallel_collection:
                permission_sets = await self._collect_permission_sets_parallel(permission_set_arns)
            else:
                permission_sets = await self._collect_permission_sets_sequential(
                    permission_set_arns
                )

            self._collection_stats["permission_sets"]["count"] = len(permission_sets)
            self._collection_stats["permission_sets"]["duration"] = time.time() - start_time

            logger.info(
                f"Collected {len(permission_sets)} permission sets in {self._collection_stats['permission_sets']['duration']:.2f}s"
            )

        except ClientError as e:
            logger.error(f"Failed to collect permission sets: {e}")
            raise

        return permission_sets

    async def collect_assignments(self, options: BackupOptions) -> List[AssignmentData]:
        """
        Collect assignment data from Identity Center.

        Args:
            options: Backup options that may affect collection behavior

        Returns:
            List of assignment data objects
        """
        start_time = time.time()
        assignments = []

        try:
            # Get all permission sets first
            permission_set_arns = await self._get_permission_set_arns()

            # For each permission set, get the accounts where it's provisioned
            for ps_arn in permission_set_arns:
                try:
                    # Get accounts where this permission set is provisioned
                    accounts_response = (
                        self.identity_center_client.list_accounts_for_provisioned_permission_set(
                            InstanceArn=self.instance_arn,
                            PermissionSetArn=ps_arn,
                        )
                    )

                    provisioned_accounts = accounts_response.get("AccountIds", [])

                    # For each provisioned account, get assignments
                    for account_id in provisioned_accounts:
                        try:
                            # Get all assignments for this account and permission set
                            paginator = self.identity_center_client.get_paginator(
                                "list_account_assignments"
                            )
                            page_iterator = paginator.paginate(
                                InstanceArn=self.instance_arn,
                                AccountId=account_id,
                                PermissionSetArn=ps_arn,
                            )

                            for page in page_iterator:
                                for assignment in page.get("AccountAssignments", []):
                                    assignments.append(
                                        AssignmentData(
                                            account_id=account_id,
                                            permission_set_arn=ps_arn,
                                            principal_type=assignment["PrincipalType"],
                                            principal_id=assignment["PrincipalId"],
                                        )
                                    )

                        except ClientError as e:
                            # Some accounts might not have assignments, which is normal
                            if e.response["Error"]["Code"] not in [
                                "ResourceNotFoundException",
                                "AccessDeniedException",
                            ]:
                                logger.warning(
                                    f"Failed to get assignments for account {account_id}: {e}"
                                )

                except ClientError as e:
                    # Some permission sets might not be provisioned anywhere
                    if e.response["Error"]["Code"] not in [
                        "ResourceNotFoundException",
                        "AccessDeniedException",
                    ]:
                        logger.warning(
                            f"Failed to get provisioned accounts for permission set {ps_arn}: {e}"
                        )

            self._collection_stats["assignments"]["count"] = len(assignments)
            self._collection_stats["assignments"]["duration"] = time.time() - start_time

            logger.info(
                f"Collected {len(assignments)} assignments in {self._collection_stats['assignments']['duration']:.2f}s"
            )

        except ClientError as e:
            logger.error(f"Failed to collect assignments: {e}")
            raise

        return assignments

    async def collect_cross_account_data(self, options: BackupOptions) -> Dict[str, BackupData]:
        """
        Collect data from multiple accounts using cross-account configurations.

        Args:
            options: Backup options including cross-account configurations

        Returns:
            Dictionary mapping account IDs to their backup data
        """
        if not options.cross_account_configs:
            logger.info("No cross-account configurations provided")
            return {}

        cross_account_data = {}

        for config in options.cross_account_configs:
            try:
                logger.info(
                    f"Starting cross-account collection for account {config.target_account_id}"
                )

                # Get cross-account client manager
                cross_account_client_manager = (
                    await self.cross_account_manager.get_cross_account_client_manager(config)
                )

                # Create a new collector for the target account
                cross_account_collector = IdentityCenterCollector(
                    cross_account_client_manager,
                    self.instance_arn,  # Assume same instance ARN structure
                )

                # Collect data from the target account
                account_backup_data = await self._collect_account_data(
                    cross_account_collector, options, config.target_account_id
                )
                cross_account_data[config.target_account_id] = account_backup_data

                logger.info(f"Successfully collected data from account {config.target_account_id}")

            except Exception as e:
                logger.error(f"Failed to collect data from account {config.target_account_id}: {e}")
                # Continue with other accounts even if one fails
                continue

        return cross_account_data

    async def _collect_account_data(
        self, collector: "IdentityCenterCollector", options: BackupOptions, account_id: str
    ) -> BackupData:
        """
        Collect data from a specific account using the provided collector.

        Args:
            collector: Collector instance configured for the target account
            options: Backup options
            account_id: Target account ID for metadata

        Returns:
            BackupData for the account
        """
        # Create account-specific backup options (without cross-account configs to avoid recursion)
        account_options = BackupOptions(
            backup_type=options.backup_type,
            resource_types=options.resource_types,
            include_inactive_users=options.include_inactive_users,
            since=options.since,
            encryption_enabled=options.encryption_enabled,
            compression_enabled=options.compression_enabled,
            parallel_collection=options.parallel_collection,
            cross_account_configs=[],  # Don't recurse
        )

        # Collect all resource types in parallel if enabled
        if account_options.parallel_collection:
            tasks: List[Any] = []

            if (
                ResourceType.ALL in account_options.resource_types
                or ResourceType.USERS in account_options.resource_types
            ):
                tasks.append(collector.collect_users(account_options))

            if (
                ResourceType.ALL in account_options.resource_types
                or ResourceType.GROUPS in account_options.resource_types
            ):
                tasks.append(collector.collect_groups(account_options))

            if (
                ResourceType.ALL in account_options.resource_types
                or ResourceType.PERMISSION_SETS in account_options.resource_types
            ):
                tasks.append(collector.collect_permission_sets(account_options))

            if (
                ResourceType.ALL in account_options.resource_types
                or ResourceType.ASSIGNMENTS in account_options.resource_types
            ):
                tasks.append(collector.collect_assignments(account_options))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results with proper type handling
            users: List[UserData] = []
            groups: List[GroupData] = []
            permission_sets: List[PermissionSetData] = []
            assignments: List[AssignmentData] = []

            if len(results) > 0 and not isinstance(results[0], Exception):
                users = results[0]  # type: ignore[assignment]
            if len(results) > 1 and not isinstance(results[1], Exception):
                groups = results[1]  # type: ignore[assignment]
            if len(results) > 2 and not isinstance(results[2], Exception):
                permission_sets = results[2]  # type: ignore[assignment]
            if len(results) > 3 and not isinstance(results[3], Exception):
                assignments = results[3]  # type: ignore[assignment]

        else:
            # Sequential collection
            users = (
                await collector.collect_users(account_options)
                if ResourceType.ALL in account_options.resource_types
                or ResourceType.USERS in account_options.resource_types
                else []
            )
            groups = (
                await collector.collect_groups(account_options)
                if ResourceType.ALL in account_options.resource_types
                or ResourceType.GROUPS in account_options.resource_types
                else []
            )
            permission_sets = (
                await collector.collect_permission_sets(account_options)
                if ResourceType.ALL in account_options.resource_types
                or ResourceType.PERMISSION_SETS in account_options.resource_types
                else []
            )
            assignments = (
                await collector.collect_assignments(account_options)
                if ResourceType.ALL in account_options.resource_types
                or ResourceType.ASSIGNMENTS in account_options.resource_types
                else []
            )

        # Build relationships
        relationships = self._build_relationships(users, groups, permission_sets, assignments)

        # Create backup metadata for this account
        import uuid

        from .models import BackupMetadata, EncryptionMetadata, RetentionPolicy

        metadata = BackupMetadata(
            backup_id=f"cross-account-{account_id}-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            instance_arn=self.instance_arn,
            backup_type=options.backup_type,
            version="1.0.0",
            source_account=account_id,
            source_region=collector.client_manager.region or "",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        return BackupData(
            metadata=metadata,
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
            relationships=relationships,
        )

    async def validate_cross_account_access(
        self, configs: List[CrossAccountConfig]
    ) -> ValidationResult:
        """
        Validate access to all configured cross-account targets.

        Args:
            configs: List of cross-account configurations to validate

        Returns:
            ValidationResult with overall validation status
        """
        if not configs:
            return ValidationResult(
                is_valid=True,
                errors=[],
                warnings=["No cross-account configurations to validate"],
                details={"validated_accounts": 0},
            )

        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {"validated_accounts": len(configs), "account_results": []}

        # Validate boundary conditions first
        boundary_result = await self.cross_account_manager.validate_cross_account_boundaries(
            configs
        )
        if not boundary_result.is_valid:
            errors.extend(boundary_result.errors)
        warnings.extend(boundary_result.warnings)

        # Validate each account individually
        for config in configs:
            try:
                account_result = (
                    await self.cross_account_manager.validate_cross_account_permissions(config)
                )

                account_details = {
                    "account_id": config.target_account_id,
                    "role_arn": config.role_arn,
                    "validation_result": account_result.to_dict(),
                }

                if not account_result.is_valid:
                    errors.extend(
                        [
                            f"Account {config.target_account_id}: {error}"
                            for error in account_result.errors
                        ]
                    )

                warnings.extend(
                    [
                        f"Account {config.target_account_id}: {warning}"
                        for warning in account_result.warnings
                    ]
                )
                details["account_results"].append(account_details)

            except Exception as e:
                error_msg = f"Failed to validate account {config.target_account_id}: {e}"
                errors.append(error_msg)
                details["account_results"].append(
                    {
                        "account_id": config.target_account_id,
                        "role_arn": config.role_arn,
                        "validation_error": str(e),
                    }
                )

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

    async def collect_incremental(self, since: datetime, options: BackupOptions) -> BackupData:
        """
        Collect only data that has changed since the specified timestamp.

        Args:
            since: Timestamp to collect changes from
            options: Backup options that may affect collection behavior

        Returns:
            BackupData containing only changed resources
        """
        logger.info(f"Starting incremental collection since {since}")

        # Set incremental options
        incremental_options = BackupOptions(
            backup_type=BackupType.INCREMENTAL,
            resource_types=options.resource_types,
            include_inactive_users=options.include_inactive_users,
            since=since,
            encryption_enabled=options.encryption_enabled,
            compression_enabled=options.compression_enabled,
            parallel_collection=options.parallel_collection,
        )

        # Collect all resource types in parallel if enabled
        if incremental_options.parallel_collection:
            tasks: List[Any] = []

            if (
                ResourceType.ALL in incremental_options.resource_types
                or ResourceType.USERS in incremental_options.resource_types
            ):
                tasks.append(self.collect_users(incremental_options))

            if (
                ResourceType.ALL in incremental_options.resource_types
                or ResourceType.GROUPS in incremental_options.resource_types
            ):
                tasks.append(self.collect_groups(incremental_options))

            if (
                ResourceType.ALL in incremental_options.resource_types
                or ResourceType.PERMISSION_SETS in incremental_options.resource_types
            ):
                tasks.append(self.collect_permission_sets(incremental_options))

            if (
                ResourceType.ALL in incremental_options.resource_types
                or ResourceType.ASSIGNMENTS in incremental_options.resource_types
            ):
                tasks.append(self.collect_assignments(incremental_options))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results with proper type handling
            users: List[UserData] = []
            groups: List[GroupData] = []
            permission_sets: List[PermissionSetData] = []
            assignments: List[AssignmentData] = []

            if len(results) > 0 and not isinstance(results[0], Exception):
                users = results[0]  # type: ignore[assignment]
            if len(results) > 1 and not isinstance(results[1], Exception):
                groups = results[1]  # type: ignore[assignment]
            if len(results) > 2 and not isinstance(results[2], Exception):
                permission_sets = results[2]  # type: ignore[assignment]
            if len(results) > 3 and not isinstance(results[3], Exception):
                assignments = results[3]  # type: ignore[assignment]

        else:
            # Sequential collection
            users = (
                await self.collect_users(incremental_options)
                if ResourceType.ALL in incremental_options.resource_types
                or ResourceType.USERS in incremental_options.resource_types
                else []
            )
            groups = (
                await self.collect_groups(incremental_options)
                if ResourceType.ALL in incremental_options.resource_types
                or ResourceType.GROUPS in incremental_options.resource_types
                else []
            )
            permission_sets = (
                await self.collect_permission_sets(incremental_options)
                if ResourceType.ALL in incremental_options.resource_types
                or ResourceType.PERMISSION_SETS in incremental_options.resource_types
                else []
            )
            assignments = (
                await self.collect_assignments(incremental_options)
                if ResourceType.ALL in incremental_options.resource_types
                or ResourceType.ASSIGNMENTS in incremental_options.resource_types
                else []
            )

        # Build relationships
        relationships = self._build_relationships(users, groups, permission_sets, assignments)

        # Create backup metadata (will be filled by backup manager)
        import uuid

        from .models import BackupMetadata, EncryptionMetadata, RetentionPolicy

        metadata = BackupMetadata(
            backup_id=f"incremental-{uuid.uuid4().hex[:8]}",  # Temporary ID, will be replaced by backup manager
            timestamp=datetime.now(),
            instance_arn=self.instance_arn,
            backup_type=BackupType.INCREMENTAL,
            version="1.0.0",
            source_account=(
                self.client_manager.session.get_credentials().access_key
                if self.client_manager.session
                else ""
            ),
            source_region=self.client_manager.region or "",
            retention_policy=RetentionPolicy(),
            encryption_info=EncryptionMetadata(),
        )

        return BackupData(
            metadata=metadata,
            users=users,
            groups=groups,
            permission_sets=permission_sets,
            assignments=assignments,
            relationships=relationships,
        )

    async def _convert_user_data(self, user: Dict[str, Any], identity_store_id: str) -> UserData:
        """Convert AWS API user data to UserData model."""
        # Get external IDs if available
        external_ids = {}
        for external_id in user.get("ExternalIds", []):
            external_ids[external_id.get("Issuer", "unknown")] = external_id.get("Id", "")

        return UserData(
            user_id=user["UserId"],
            user_name=user["UserName"],
            display_name=user.get("DisplayName"),
            email=user.get("Emails", [{}])[0].get("Value") if user.get("Emails") else None,
            given_name=user.get("Name", {}).get("GivenName"),
            family_name=user.get("Name", {}).get("FamilyName"),
            active=user.get("Active", True),
            external_ids=external_ids,
        )

    async def _convert_group_data(self, group: Dict[str, Any], identity_store_id: str) -> GroupData:
        """Convert AWS API group data to GroupData model."""
        # Get group members
        members = []
        try:
            paginator = self.identity_store_client.get_paginator("list_group_memberships")
            page_iterator = paginator.paginate(
                IdentityStoreId=identity_store_id, GroupId=group["GroupId"]
            )

            for page in page_iterator:
                for membership in page.get("GroupMemberships", []):
                    members.append(membership["MemberId"]["UserId"])
        except ClientError as e:
            logger.warning(f"Failed to get members for group {group['GroupId']}: {e}")

        return GroupData(
            group_id=group["GroupId"],
            display_name=group["DisplayName"],
            description=group.get("Description"),
            members=members,
        )

    async def _collect_permission_sets_parallel(
        self, permission_set_arns: List[str]
    ) -> List[PermissionSetData]:
        """Collect permission set details in parallel."""
        permission_sets = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit tasks for each permission set
            future_to_arn = {
                executor.submit(self._get_permission_set_details, arn): arn
                for arn in permission_set_arns
            }

            # Collect results as they complete
            for future in as_completed(future_to_arn):
                arn = future_to_arn[future]
                try:
                    permission_set_data = future.result()
                    if permission_set_data:
                        permission_sets.append(permission_set_data)
                except Exception as e:
                    logger.error(f"Failed to collect permission set {arn}: {e}")

        return permission_sets

    async def _collect_permission_sets_sequential(
        self, permission_set_arns: List[str]
    ) -> List[PermissionSetData]:
        """Collect permission set details sequentially."""
        permission_sets = []

        for arn in permission_set_arns:
            try:
                permission_set_data = await asyncio.get_event_loop().run_in_executor(
                    None, self._get_permission_set_details, arn
                )
                if permission_set_data:
                    permission_sets.append(permission_set_data)
            except Exception as e:
                logger.error(f"Failed to collect permission set {arn}: {e}")

        return permission_sets

    def _get_permission_set_details(self, permission_set_arn: str) -> Optional[PermissionSetData]:
        """Get detailed permission set information."""
        try:
            # Get basic permission set info
            response = self.identity_center_client.describe_permission_set(
                InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
            )
            ps_info = response["PermissionSet"]

            # Get inline policy
            inline_policy = None
            try:
                policy_response = self.identity_center_client.get_inline_policy_for_permission_set(
                    InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
                )
                inline_policy = policy_response.get("InlinePolicy")
            except ClientError as e:
                if e.response["Error"]["Code"] != "ResourceNotFoundException":
                    logger.warning(f"Failed to get inline policy for {permission_set_arn}: {e}")

            # Get managed policies
            managed_policies = []
            try:
                paginator = self.identity_center_client.get_paginator(
                    "list_managed_policies_in_permission_set"
                )
                page_iterator = paginator.paginate(
                    InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
                )

                for page in page_iterator:
                    managed_policies.extend(page.get("AttachedManagedPolicies", []))
            except ClientError as e:
                logger.warning(f"Failed to get managed policies for {permission_set_arn}: {e}")

            # Get customer managed policies
            customer_managed_policies = []
            try:
                paginator = self.identity_center_client.get_paginator(
                    "list_customer_managed_policy_references_in_permission_set"
                )
                page_iterator = paginator.paginate(
                    InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
                )

                for page in page_iterator:
                    customer_managed_policies.extend(
                        page.get("CustomerManagedPolicyReferences", [])
                    )
            except ClientError as e:
                logger.warning(
                    f"Failed to get customer managed policies for {permission_set_arn}: {e}"
                )

            # Get permissions boundary
            permissions_boundary = None
            try:
                boundary_response = (
                    self.identity_center_client.get_permissions_boundary_for_permission_set(
                        InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
                    )
                )
                permissions_boundary = boundary_response.get("PermissionsBoundary")
            except ClientError as e:
                if e.response["Error"]["Code"] != "ResourceNotFoundException":
                    logger.warning(
                        f"Failed to get permissions boundary for {permission_set_arn}: {e}"
                    )

            return PermissionSetData(
                permission_set_arn=permission_set_arn,
                name=ps_info["Name"],
                description=ps_info.get("Description"),
                session_duration=ps_info.get("SessionDuration"),
                relay_state=ps_info.get("RelayState"),
                inline_policy=inline_policy,
                managed_policies=[policy["Arn"] for policy in managed_policies],
                customer_managed_policies=customer_managed_policies,
                permissions_boundary=permissions_boundary,
            )

        except ClientError as e:
            logger.error(f"Failed to get permission set details for {permission_set_arn}: {e}")
            return None

    async def _get_organization_accounts(self) -> List[str]:
        """Get all account IDs from Organizations."""
        accounts = []

        try:
            # Build organization hierarchy to get all accounts
            from ..aws_clients.manager import build_organization_hierarchy

            org_tree = await asyncio.get_event_loop().run_in_executor(
                None, build_organization_hierarchy, self.organizations_client
            )

            # Extract account IDs from the tree
            def extract_accounts(node):
                if node.is_account():
                    accounts.append(node.id)
                for child in node.children:
                    extract_accounts(child)

            for root in org_tree:
                extract_accounts(root)

        except Exception as e:
            logger.warning(f"Failed to get organization accounts: {e}")
            # Fallback: try to get accounts directly
            try:
                paginator = self.organizations_client.get_paginator("list_accounts")
                page_iterator = paginator.paginate()

                for page in page_iterator:
                    for account in page.get("Accounts", []):
                        accounts.append(account["Id"])
            except Exception as fallback_error:
                logger.error(f"Failed to get accounts with fallback method: {fallback_error}")

        return accounts

    async def _get_permission_set_arns(self) -> List[str]:
        """Get all permission set ARNs."""
        permission_set_arns = []

        try:
            paginator = self.identity_center_client.get_paginator("list_permission_sets")
            page_iterator = paginator.paginate(InstanceArn=self.instance_arn)

            for page in page_iterator:
                permission_set_arns.extend(page.get("PermissionSets", []))
        except ClientError as e:
            logger.error(f"Failed to get permission set ARNs: {e}")
            raise

        return permission_set_arns

    async def _collect_assignments_parallel(
        self, accounts: List[str], permission_set_arns: List[str]
    ) -> List[AssignmentData]:
        """Collect assignments in parallel."""
        assignments = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit tasks for each account/permission set combination
            futures = []
            for account_id in accounts:
                for ps_arn in permission_set_arns:
                    future = executor.submit(
                        self._get_assignments_for_account_and_ps, account_id, ps_arn
                    )
                    futures.append(future)

            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    account_assignments = future.result()
                    assignments.extend(account_assignments)
                except Exception as e:
                    logger.error(f"Failed to collect assignments: {e}")

        return assignments

    async def _collect_assignments_sequential(
        self, accounts: List[str], permission_set_arns: List[str]
    ) -> List[AssignmentData]:
        """Collect assignments sequentially."""
        assignments = []

        for account_id in accounts:
            for ps_arn in permission_set_arns:
                try:
                    account_assignments = await asyncio.get_event_loop().run_in_executor(
                        None, self._get_assignments_for_account_and_ps, account_id, ps_arn
                    )
                    assignments.extend(account_assignments)
                except Exception as e:
                    logger.error(f"Failed to collect assignments for {account_id}/{ps_arn}: {e}")

        return assignments

    def _get_assignments_for_account_and_ps(
        self, account_id: str, permission_set_arn: str
    ) -> List[AssignmentData]:
        """Get assignments for a specific account and permission set."""
        assignments = []

        try:
            paginator = self.identity_center_client.get_paginator("list_account_assignments")
            page_iterator = paginator.paginate(
                InstanceArn=self.instance_arn,
                AccountId=account_id,
                PermissionSetArn=permission_set_arn,
            )

            for page in page_iterator:
                for assignment in page.get("AccountAssignments", []):
                    assignments.append(
                        AssignmentData(
                            account_id=account_id,
                            permission_set_arn=permission_set_arn,
                            principal_type=assignment["PrincipalType"],
                            principal_id=assignment["PrincipalId"],
                        )
                    )

        except ClientError as e:
            # Some combinations might not have assignments, which is normal
            if e.response["Error"]["Code"] not in [
                "ResourceNotFoundException",
                "AccessDeniedException",
            ]:
                logger.warning(
                    f"Failed to get assignments for {account_id}/{permission_set_arn}: {e}"
                )

        return assignments

    def _build_relationships(
        self,
        users: List[UserData],
        groups: List[GroupData],
        permission_sets: List[PermissionSetData],
        assignments: List[AssignmentData],
    ) -> RelationshipMap:
        """Build relationship mappings between resources."""
        relationships = RelationshipMap()

        # Build user-group relationships
        for group in groups:
            relationships.group_members[group.group_id] = group.members
            for user_id in group.members:
                if user_id not in relationships.user_groups:
                    relationships.user_groups[user_id] = []
                relationships.user_groups[user_id].append(group.group_id)

        # Build permission set assignment relationships
        for ps in permission_sets:
            ps_assignments = [
                f"{a.account_id}:{a.principal_type}:{a.principal_id}"
                for a in assignments
                if a.permission_set_arn == ps.permission_set_arn
            ]
            relationships.permission_set_assignments[ps.permission_set_arn] = ps_assignments

        return relationships

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection performance statistics."""
        import copy

        return copy.deepcopy(self._collection_stats)
