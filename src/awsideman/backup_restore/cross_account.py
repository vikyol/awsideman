"""
Cross-account and cross-region support for backup-restore operations.

This module provides functionality for assuming IAM roles across accounts,
validating cross-account permissions, and managing resource mappings for
cross-region operations.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

import boto3
from botocore.exceptions import ClientError

from ..aws_clients import AWSClientManager
from .models import CrossAccountConfig, ResourceMapping, ValidationResult

logger = logging.getLogger(__name__)


class CrossAccountClientManager:
    """
    Manages AWS clients for cross-account operations with role assumption.
    """

    def __init__(self, base_client_manager: AWSClientManager):
        """
        Initialize cross-account client manager.

        Args:
            base_client_manager: Base AWS client manager for the source account
        """
        self.base_client_manager = base_client_manager
        self._assumed_role_sessions: Dict[str, boto3.Session] = {}
        self._session_expiry: Dict[str, datetime] = {}
        self._role_validation_cache: Dict[str, ValidationResult] = {}

    async def assume_role(self, config: CrossAccountConfig) -> boto3.Session:
        """
        Assume an IAM role in a target account.

        Args:
            config: Cross-account configuration with role details

        Returns:
            boto3.Session with assumed role credentials

        Raises:
            ClientError: If role assumption fails
        """
        cache_key = f"{config.target_account_id}:{config.role_arn}"

        # Check if we have a valid cached session
        if cache_key in self._assumed_role_sessions:
            if self._session_expiry.get(cache_key, datetime.min) > datetime.now():
                logger.debug(f"Using cached session for {cache_key}")
                return self._assumed_role_sessions[cache_key]
            else:
                # Session expired, remove from cache
                self._assumed_role_sessions.pop(cache_key, None)
                self._session_expiry.pop(cache_key, None)

        try:
            # Get STS client from base session
            sts_client = self.base_client_manager.get_client("sts")

            # Prepare assume role parameters
            assume_role_params = {
                "RoleArn": config.role_arn,
                "RoleSessionName": config.session_name
                or f"awsideman-backup-{int(datetime.now().timestamp())}",
                "DurationSeconds": 3600,  # 1 hour
            }

            if config.external_id:
                assume_role_params["ExternalId"] = config.external_id

            # Assume the role
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: sts_client.assume_role(**assume_role_params)
            )

            credentials = response["Credentials"]

            # Create new session with assumed role credentials
            session = boto3.Session(
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
                region_name=self.base_client_manager.region,
            )

            # Cache the session
            self._assumed_role_sessions[cache_key] = session
            self._session_expiry[cache_key] = credentials["Expiration"] - timedelta(
                minutes=5
            )  # 5 min buffer

            logger.info(
                f"Successfully assumed role {config.role_arn} in account {config.target_account_id}"
            )
            return session

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "AccessDenied":
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "CrossAccountAccessDenied",
                            "Message": f"Access denied when assuming role {config.role_arn}. Check role trust policy and permissions.",
                        }
                    },
                    operation_name="AssumeRole",
                )
            elif error_code == "InvalidUserType":
                raise ClientError(
                    error_response={
                        "Error": {
                            "Code": "InvalidUserType",
                            "Message": "Cannot assume role with root account credentials. Use IAM user or role credentials.",
                        }
                    },
                    operation_name="AssumeRole",
                )
            else:
                logger.error(f"Failed to assume role {config.role_arn}: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error assuming role {config.role_arn}: {e}")
            raise

    async def get_cross_account_client_manager(
        self, config: CrossAccountConfig
    ) -> AWSClientManager:
        """
        Get an AWSClientManager for the target account.

        Args:
            config: Cross-account configuration

        Returns:
            AWSClientManager configured for the target account
        """
        session = await self.assume_role(config)

        # Create a new client manager with the assumed role session
        cross_account_manager = AWSClientManager(
            profile=None,  # Don't use profile since we have explicit session
            region=self.base_client_manager.region,
            enable_caching=self.base_client_manager.enable_caching,
        )
        cross_account_manager.session = session

        return cross_account_manager

    async def validate_cross_account_permissions(
        self, config: CrossAccountConfig
    ) -> ValidationResult:
        """
        Validate that the cross-account role has necessary permissions.

        Args:
            config: Cross-account configuration to validate

        Returns:
            ValidationResult with permission validation status
        """
        cache_key = f"{config.target_account_id}:{config.role_arn}"

        # Check cache first
        if cache_key in self._role_validation_cache:
            cached_result = self._role_validation_cache[cache_key]
            # Cache results for 5 minutes
            if hasattr(
                cached_result, "_cached_at"
            ) and datetime.now() - cached_result._cached_at < timedelta(minutes=5):
                return cached_result

        errors = []
        warnings = []
        details = {}

        try:
            # Try to assume the role
            session = await self.assume_role(config)
            details["role_assumption"] = "SUCCESS"

            # Test Identity Center permissions
            try:
                identity_center_client = session.client("sso-admin")
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: identity_center_client.list_instances()
                )
                details["identity_center_access"] = "SUCCESS"
            except ClientError as e:
                errors.append(f"Identity Center access denied: {e}")
                details["identity_center_access"] = "FAILED"

            # Test Identity Store permissions
            try:
                identity_store_client = session.client("identitystore")
                # Try a minimal operation to test permissions
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: identity_store_client.list_users(
                        IdentityStoreId="dummy-test",  # This will fail but tests permissions
                        MaxResults=1,
                    ),
                )
            except ClientError as e:
                if e.response["Error"]["Code"] not in [
                    "ValidationException",
                    "ResourceNotFoundException",
                ]:
                    errors.append(f"Identity Store access denied: {e}")
                    details["identity_store_access"] = "FAILED"
                else:
                    # ValidationException means we have permissions but invalid parameters
                    details["identity_store_access"] = "SUCCESS"

            # Test Organizations permissions (optional)
            try:
                organizations_client = session.client("organizations")
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: organizations_client.list_roots()
                )
                details["organizations_access"] = "SUCCESS"
            except ClientError as e:
                warnings.append(f"Organizations access limited (optional): {e}")
                details["organizations_access"] = "LIMITED"

        except ClientError as e:
            errors.append(f"Role assumption failed: {e}")
            details["role_assumption"] = "FAILED"
        except Exception as e:
            errors.append(f"Unexpected validation error: {e}")
            details["validation_error"] = str(e)

        result = ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

        # Cache the result
        result._cached_at = datetime.now()
        self._role_validation_cache[cache_key] = result

        return result

    async def validate_cross_account_boundaries(
        self, configs: List[CrossAccountConfig]
    ) -> ValidationResult:
        """
        Validate that cross-account operations respect security boundaries.

        Args:
            configs: List of cross-account configurations to validate

        Returns:
            ValidationResult with boundary validation status
        """
        errors = []
        warnings = []
        details = {"validated_accounts": [], "boundary_checks": []}

        try:
            # Get current account ID for validation
            sts_client = self.base_client_manager.get_client("sts")
            caller_identity = await asyncio.get_event_loop().run_in_executor(
                None, lambda: sts_client.get_caller_identity()
            )
            source_account_id = caller_identity["Account"]

            for config in configs:
                account_validation = {
                    "target_account": config.target_account_id,
                    "role_arn": config.role_arn,
                    "checks": [],
                }

                # Check 1: Ensure we're not trying to assume role in same account unnecessarily
                if config.target_account_id == source_account_id:
                    warnings.append(
                        f"Cross-account config specified for same account {source_account_id}"
                    )
                    account_validation["checks"].append("same_account_warning")

                # Check 2: Validate role ARN format
                if not config.role_arn.startswith(f"arn:aws:iam::{config.target_account_id}:role/"):
                    errors.append(
                        f"Role ARN {config.role_arn} does not match target account {config.target_account_id}"
                    )
                    account_validation["checks"].append("role_arn_mismatch")
                else:
                    account_validation["checks"].append("role_arn_valid")

                # Check 3: Validate external ID if provided
                if config.external_id and len(config.external_id) < 2:
                    warnings.append(
                        f"External ID for {config.target_account_id} is very short, consider using a longer value"
                    )
                    account_validation["checks"].append("weak_external_id")

                details["validated_accounts"].append(account_validation)
                details["boundary_checks"].append(account_validation)

        except Exception as e:
            errors.append(f"Boundary validation error: {e}")

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

    def clear_session_cache(self) -> None:
        """Clear all cached assumed role sessions."""
        self._assumed_role_sessions.clear()
        self._session_expiry.clear()
        self._role_validation_cache.clear()
        logger.info("Cleared cross-account session cache")


class ResourceMapper:
    """
    Handles resource mapping for cross-region and cross-account operations.
    """

    def __init__(self):
        """Initialize resource mapper."""
        self._region_mappings: Dict[str, str] = {}
        self._account_mappings: Dict[str, str] = {}

    def add_region_mapping(self, source_region: str, target_region: str) -> None:
        """
        Add a region mapping for cross-region operations.

        Args:
            source_region: Source AWS region
            target_region: Target AWS region
        """
        self._region_mappings[source_region] = target_region
        logger.debug(f"Added region mapping: {source_region} -> {target_region}")

    def add_account_mapping(self, source_account: str, target_account: str) -> None:
        """
        Add an account mapping for cross-account operations.

        Args:
            source_account: Source AWS account ID
            target_account: Target AWS account ID
        """
        self._account_mappings[source_account] = target_account
        logger.debug(f"Added account mapping: {source_account} -> {target_account}")

    def map_permission_set_arn(self, source_arn: str, mappings: List[ResourceMapping]) -> str:
        """
        Map a permission set ARN for cross-account/region operations.

        Args:
            source_arn: Original permission set ARN
            mappings: List of resource mappings to apply

        Returns:
            Mapped permission set ARN
        """
        # Parse the ARN: arn:aws:sso:::permissionSet/instance_id/ps_id
        arn_parts = source_arn.split(":")
        if len(arn_parts) < 6:
            logger.warning(f"Invalid permission set ARN format: {source_arn}")
            return source_arn

        # Extract components
        partition = arn_parts[1]  # aws
        service = arn_parts[2]  # sso
        region = arn_parts[3]  # region
        account = arn_parts[4]  # account
        resource = arn_parts[5]  # permissionSet/instance_id/ps_id

        # Apply mappings
        for mapping in mappings:
            if mapping.source_account_id == account:
                # Map account
                account = mapping.target_account_id

                # Map region if specified
                if mapping.source_region == region and mapping.target_region:
                    region = mapping.target_region

                break

        # Reconstruct ARN
        mapped_arn = f"arn:{partition}:{service}:{region}:{account}:{resource}"

        if mapped_arn != source_arn:
            logger.debug(f"Mapped permission set ARN: {source_arn} -> {mapped_arn}")

        return mapped_arn

    def map_assignment_account(self, source_account: str, mappings: List[ResourceMapping]) -> str:
        """
        Map an assignment account ID for cross-account operations.

        Args:
            source_account: Original account ID
            mappings: List of resource mappings to apply

        Returns:
            Mapped account ID
        """
        for mapping in mappings:
            if mapping.source_account_id == source_account:
                logger.debug(
                    f"Mapped assignment account: {source_account} -> {mapping.target_account_id}"
                )
                return mapping.target_account_id

        return source_account

    def map_permission_set_name(self, source_name: str, mappings: List[ResourceMapping]) -> str:
        """
        Map a permission set name using configured name mappings.

        Args:
            source_name: Original permission set name
            mappings: List of resource mappings to apply

        Returns:
            Mapped permission set name
        """
        for mapping in mappings:
            if source_name in mapping.permission_set_name_mappings:
                mapped_name = mapping.permission_set_name_mappings[source_name]
                logger.debug(f"Mapped permission set name: {source_name} -> {mapped_name}")
                return mapped_name

        return source_name

    def validate_mappings(self, mappings: List[ResourceMapping]) -> ValidationResult:
        """
        Validate resource mappings for consistency and correctness.

        Args:
            mappings: List of resource mappings to validate

        Returns:
            ValidationResult with mapping validation status
        """
        errors = []
        warnings = []
        details = {"validated_mappings": len(mappings), "issues": []}

        # Check for duplicate source accounts
        source_accounts = [m.source_account_id for m in mappings]
        if len(source_accounts) != len(set(source_accounts)):
            errors.append("Duplicate source account IDs found in mappings")

        # Validate account ID formats
        for mapping in mappings:
            if not mapping.source_account_id.isdigit() or len(mapping.source_account_id) != 12:
                errors.append(f"Invalid source account ID format: {mapping.source_account_id}")

            if not mapping.target_account_id.isdigit() or len(mapping.target_account_id) != 12:
                errors.append(f"Invalid target account ID format: {mapping.target_account_id}")

            # Validate region formats if specified
            if mapping.source_region and not self._is_valid_region(mapping.source_region):
                warnings.append(f"Potentially invalid source region: {mapping.source_region}")

            if mapping.target_region and not self._is_valid_region(mapping.target_region):
                warnings.append(f"Potentially invalid target region: {mapping.target_region}")

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

    def _is_valid_region(self, region: str) -> bool:
        """Check if a region string has a valid format."""
        # Basic validation for AWS region format
        import re

        pattern = r"^[a-z]{2}-[a-z]+-\d+$"
        return bool(re.match(pattern, region))


class CrossAccountPermissionValidator:
    """
    Validates permissions and boundaries for cross-account operations.
    """

    def __init__(self, cross_account_manager: CrossAccountClientManager):
        """
        Initialize permission validator.

        Args:
            cross_account_manager: Cross-account client manager
        """
        self.cross_account_manager = cross_account_manager

    async def validate_backup_permissions(
        self, configs: List[CrossAccountConfig]
    ) -> ValidationResult:
        """
        Validate permissions required for cross-account backup operations.

        Args:
            configs: List of cross-account configurations

        Returns:
            ValidationResult with permission validation status
        """
        errors = []
        warnings = []
        details = {"account_validations": []}

        for config in configs:
            account_result = {
                "account_id": config.target_account_id,
                "role_arn": config.role_arn,
                "permissions": {},
            }

            try:
                # Validate basic role assumption
                validation_result = (
                    await self.cross_account_manager.validate_cross_account_permissions(config)
                )

                if not validation_result.is_valid:
                    errors.extend(
                        [
                            f"Account {config.target_account_id}: {error}"
                            for error in validation_result.errors
                        ]
                    )
                    account_result["permissions"]["basic"] = "FAILED"
                else:
                    account_result["permissions"]["basic"] = "SUCCESS"

                # Test specific backup permissions
                try:
                    client_manager = (
                        await self.cross_account_manager.get_cross_account_client_manager(config)
                    )

                    # Test Identity Center read permissions
                    identity_center_client = client_manager.get_identity_center_client()
                    await asyncio.get_event_loop().run_in_executor(
                        None, lambda: identity_center_client.list_instances()
                    )
                    account_result["permissions"]["identity_center_read"] = "SUCCESS"

                    # Test Identity Store read permissions
                    # We can't test this without a valid identity store ID, so we'll mark as assumed
                    account_result["permissions"]["identity_store_read"] = "ASSUMED"

                except Exception as e:
                    errors.append(
                        f"Account {config.target_account_id}: Backup permission test failed: {e}"
                    )
                    account_result["permissions"]["backup_specific"] = "FAILED"

            except Exception as e:
                errors.append(f"Account {config.target_account_id}: Validation failed: {e}")
                account_result["permissions"]["validation"] = "FAILED"

            details["account_validations"].append(account_result)

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )

    async def validate_restore_permissions(
        self, config: CrossAccountConfig, target_instance_arn: str
    ) -> ValidationResult:
        """
        Validate permissions required for cross-account restore operations.

        Args:
            config: Cross-account configuration
            target_instance_arn: Target Identity Center instance ARN

        Returns:
            ValidationResult with permission validation status
        """
        errors = []
        warnings = []
        details = {"permissions": {}}

        try:
            # Get cross-account client manager
            client_manager = await self.cross_account_manager.get_cross_account_client_manager(
                config
            )

            # Test Identity Center write permissions
            try:
                identity_center_client = client_manager.get_identity_center_client()

                # Test instance access
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: identity_center_client.describe_instance(
                        InstanceArn=target_instance_arn
                    ),
                )
                details["permissions"]["instance_access"] = "SUCCESS"

                # Test permission set operations (list is read-only, safe to test)
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: identity_center_client.list_permission_sets(
                        InstanceArn=target_instance_arn
                    ),
                )
                details["permissions"]["permission_set_access"] = "SUCCESS"

            except ClientError as e:
                if e.response["Error"]["Code"] == "AccessDenied":
                    errors.append(
                        f"Access denied to Identity Center instance {target_instance_arn}"
                    )
                    details["permissions"]["instance_access"] = "DENIED"
                else:
                    errors.append(f"Identity Center access error: {e}")
                    details["permissions"]["instance_access"] = "ERROR"

            # Test Identity Store write permissions
            try:
                # We can't safely test write operations, so we'll check basic access
                details["permissions"]["identity_store_write"] = "ASSUMED"

            except Exception as e:
                warnings.append(f"Could not validate Identity Store write permissions: {e}")
                details["permissions"]["identity_store_write"] = "UNKNOWN"

        except Exception as e:
            errors.append(f"Restore permission validation failed: {e}")

        return ValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings, details=details
        )
