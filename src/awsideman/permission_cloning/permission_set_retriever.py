"""
Permission set configuration retriever for AWS Identity Center.

This module provides functionality to retrieve complete permission set configurations
including AWS managed policies, customer managed policies, inline policies,
session duration, and relay state URL.
"""

import logging
from typing import Any, Dict, List, Optional

from ..aws_clients.manager import AWSClientManager
from .models import CustomerManagedPolicy, PermissionSetConfig

logger = logging.getLogger(__name__)


class PermissionSetRetriever:
    """
    Retrieves complete permission set configurations from AWS Identity Center.

    This class provides methods to fetch:
    - Permission set basic information (name, description, session duration)
    - AWS managed policies
    - Customer managed policies
    - Inline policies
    - Relay state URL configuration
    """

    def __init__(self, client_manager: AWSClientManager, instance_arn: str):
        """
        Initialize the PermissionSetRetriever.

        Args:
            client_manager: AWS client manager for accessing AWS services
            instance_arn: SSO instance ARN
        """
        self.client_manager = client_manager
        self.instance_arn = instance_arn
        self._permission_set_cache: Dict[str, PermissionSetConfig] = {}

    @property
    def sso_admin_client(self):
        """Get the SSO Admin client."""
        return self.client_manager.get_sso_admin_client()

    def get_permission_set_config(self, permission_set_arn: str) -> PermissionSetConfig:
        """
        Get complete configuration for a permission set.

        Args:
            permission_set_arn: ARN of the permission set to retrieve

        Returns:
            PermissionSetConfig with complete permission set information
        """
        # Check cache first
        if permission_set_arn in self._permission_set_cache:
            logger.debug(f"Returning cached config for permission set: {permission_set_arn}")
            return self._permission_set_cache[permission_set_arn]

        try:
            logger.info(f"Retrieving configuration for permission set: {permission_set_arn}")

            # Get basic permission set information
            basic_info = self._get_permission_set_basic_info(permission_set_arn)

            # Get attached policies
            aws_managed_policies = self._get_aws_managed_policies(permission_set_arn)
            customer_managed_policies = self._get_customer_managed_policies(permission_set_arn)

            # Get inline policy
            inline_policy = self._get_inline_policy(permission_set_arn)

            # Create configuration object
            config = PermissionSetConfig(
                name=basic_info["name"],
                description=basic_info["description"],
                session_duration=basic_info["session_duration"],
                relay_state_url=basic_info.get("relay_state_url"),
                aws_managed_policies=aws_managed_policies,
                customer_managed_policies=customer_managed_policies,
                inline_policy=inline_policy,
            )

            # Cache the result
            self._permission_set_cache[permission_set_arn] = config

            logger.info(
                f"Successfully retrieved configuration for permission set: {basic_info['name']}"
            )
            return config

        except Exception as e:
            logger.error(f"Failed to retrieve permission set configuration: {str(e)}")
            raise

    def _get_permission_set_basic_info(self, permission_set_arn: str) -> Dict[str, Any]:
        """
        Get basic information about a permission set.

        Args:
            permission_set_arn: ARN of the permission set

        Returns:
            Dictionary with basic permission set information
        """
        try:
            response = self.sso_admin_client.describe_permission_set(
                InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
            )

            permission_set = response["PermissionSet"]

            return {
                "name": permission_set["Name"],
                "description": permission_set.get("Description", ""),
                "session_duration": permission_set.get("SessionDuration", "PT1H"),
                "relay_state_url": permission_set.get("RelayState"),
            }

        except Exception as e:
            logger.error(f"Failed to get basic permission set info: {str(e)}")
            raise

    def _get_aws_managed_policies(self, permission_set_arn: str) -> List[str]:
        """
        Get AWS managed policies attached to a permission set.

        Args:
            permission_set_arn: ARN of the permission set

        Returns:
            List of AWS managed policy ARNs
        """
        try:
            response = self.sso_admin_client.list_managed_policies_in_permission_set(
                InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
            )

            aws_managed_policies = []
            for policy in response["AttachedManagedPolicies"]:
                if policy["Type"] == "AWS_MANAGED":
                    aws_managed_policies.append(policy["Arn"])

            logger.debug(f"Found {len(aws_managed_policies)} AWS managed policies")
            return aws_managed_policies

        except Exception as e:
            logger.error(f"Failed to get AWS managed policies: {str(e)}")
            return []

    def _get_customer_managed_policies(
        self, permission_set_arn: str
    ) -> List[CustomerManagedPolicy]:
        """
        Get customer managed policies attached to a permission set.

        Args:
            permission_set_arn: ARN of the permission set

        Returns:
            List of CustomerManagedPolicy objects
        """
        try:
            response = self.sso_admin_client.list_managed_policies_in_permission_set(
                InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
            )

            customer_managed_policies = []
            for policy in response["AttachedManagedPolicies"]:
                if policy["Type"] == "CUSTOMER_MANAGED":
                    # Extract policy name and path from ARN
                    arn_parts = policy["Arn"].split("/")
                    if len(arn_parts) >= 2:
                        policy_name = arn_parts[-1]
                        policy_path = "/".join(arn_parts[1:-1]) if len(arn_parts) > 2 else "/"

                        customer_managed_policies.append(
                            CustomerManagedPolicy(name=policy_name, path=policy_path)
                        )

            logger.debug(f"Found {len(customer_managed_policies)} customer managed policies")
            return customer_managed_policies

        except Exception as e:
            logger.error(f"Failed to get customer managed policies: {str(e)}")
            return []

    def _get_inline_policy(self, permission_set_arn: str) -> Optional[str]:
        """
        Get inline policy attached to a permission set.

        Args:
            permission_set_arn: ARN of the permission set

        Returns:
            Inline policy document as string, or None if no inline policy
        """
        try:
            response = self.sso_admin_client.get_inline_policy_for_permission_set(
                InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
            )

            inline_policy = response.get("InlinePolicy")
            if inline_policy:
                logger.debug("Found inline policy")
                return inline_policy
            else:
                logger.debug("No inline policy found")
                return None

        except Exception as e:
            logger.error(f"Failed to get inline policy: {str(e)}")
            return None

    def get_permission_set_by_name(self, permission_set_name: str) -> Optional[str]:
        """
        Get permission set ARN by name.

        Args:
            permission_set_name: Name of the permission set

        Returns:
            Permission set ARN if found, None otherwise
        """
        try:
            response = self.sso_admin_client.list_permission_sets(InstanceArn=self.instance_arn)

            for permission_set_arn in response["PermissionSets"]:
                try:
                    basic_info = self._get_permission_set_basic_info(permission_set_arn)
                    if basic_info["name"] == permission_set_name:
                        return permission_set_arn
                except Exception:
                    # Skip this permission set if we can't get its info
                    continue

            logger.warning(f"Permission set not found: {permission_set_name}")
            return None

        except Exception as e:
            logger.error(f"Failed to search for permission set by name: {str(e)}")
            return None

    def clear_cache(self) -> None:
        """Clear the permission set configuration cache."""
        self._permission_set_cache.clear()
        logger.debug("Permission set configuration cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the cache.

        Returns:
            Dictionary with cache statistics
        """
        return {"cached_permission_sets": len(self._permission_set_cache)}
