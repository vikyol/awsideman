"""
Assignment retrieval functionality for AWS Identity Center permission cloning.

This module provides functionality to retrieve permission assignments for users and groups
in AWS Identity Center, including caching for performance optimization.
"""

import logging
from typing import Dict, List

from botocore.exceptions import ClientError

from ..aws_clients.manager import AWSClientManager
from .entity_resolver import EntityResolver
from .models import EntityReference, EntityType, PermissionAssignment

logger = logging.getLogger(__name__)


class AssignmentRetriever:
    """
    Retrieves permission assignments for users and groups in AWS Identity Center.

    This class provides methods to:
    - Fetch all permission assignments for users
    - Fetch all permission assignments for groups
    - Cache assignment data to improve performance
    - Handle pagination and large result sets efficiently
    """

    def __init__(self, client_manager: AWSClientManager, instance_arn: str, identity_store_id: str):
        """
        Initialize the AssignmentRetriever.

        Args:
            client_manager: AWS client manager for accessing AWS services
            instance_arn: The Identity Center instance ARN
            identity_store_id: The Identity Store ID for the AWS Identity Center instance
        """
        self.client_manager = client_manager
        self.instance_arn = instance_arn
        self.identity_store_id = identity_store_id
        self._sso_admin_client = None
        self._organizations_client = None

        # Initialize entity resolver for validation
        self.entity_resolver = EntityResolver(client_manager, identity_store_id)

        # Cache for assignment data to improve performance
        self._assignment_cache: Dict[str, List[PermissionAssignment]] = (
            {}
        )  # {entity_key: assignments}
        self._permission_set_cache: Dict[str, Dict[str, str]] = {}  # {arn: {name, description}}
        self._account_cache: Dict[str, str] = {}  # {id: name}

        # Cache keys for different entity types
        self._user_assignments_cache: Dict[str, List[PermissionAssignment]] = (
            {}
        )  # {user_id: assignments}
        self._group_assignments_cache: Dict[str, List[PermissionAssignment]] = (
            {}
        )  # {group_id: assignments}

    @property
    def sso_admin_client(self):
        """Get the SSO Admin client, creating it if needed."""
        if self._sso_admin_client is None:
            self._sso_admin_client = self.client_manager.get_identity_center_client()
        return self._sso_admin_client

    @property
    def organizations_client(self):
        """Get the Organizations client, creating it if needed."""
        if self._organizations_client is None:
            self._organizations_client = self.client_manager.get_organizations_client()
        return self._organizations_client

    def get_user_assignments(self, user_entity: EntityReference) -> List[PermissionAssignment]:
        """
        Get all permission assignments for a user.

        Args:
            user_entity: The user entity reference

        Returns:
            List of permission assignments for the user
        """
        # Validate the user entity first
        validation = self.entity_resolver.validate_entity(user_entity)
        if validation.has_errors:
            logger.error(f"Invalid user entity: {validation.messages}")
            return []

        # Check cache first
        cache_key = f"user:{user_entity.entity_id}"
        if cache_key in self._user_assignments_cache:
            logger.debug(f"Using cached assignments for user {user_entity.entity_name}")
            return self._user_assignments_cache[cache_key]

        try:
            assignments = self._fetch_entity_assignments(
                entity_id=user_entity.entity_id, entity_type="USER"
            )

            # Convert to PermissionAssignment objects and enrich with names
            enriched_assignments = self._enrich_assignments(assignments)

            # Cache the results
            self._user_assignments_cache[cache_key] = enriched_assignments

            logger.info(
                f"Retrieved {len(enriched_assignments)} assignments for user {user_entity.entity_name}"
            )
            return enriched_assignments

        except Exception as e:
            logger.error(
                f"Error retrieving assignments for user {user_entity.entity_name}: {str(e)}"
            )
            return []

    def get_group_assignments(self, group_entity: EntityReference) -> List[PermissionAssignment]:
        """
        Get all permission assignments for a group.

        Args:
            group_entity: The group entity reference

        Returns:
            List of permission assignments for the group
        """
        # Validate the group entity first
        validation = self.entity_resolver.validate_entity(group_entity)
        if validation.has_errors:
            logger.error(f"Invalid group entity: {validation.messages}")
            return []

        # Check cache first
        cache_key = f"group:{group_entity.entity_id}"
        if cache_key in self._group_assignments_cache:
            logger.debug(f"Using cached assignments for group {group_entity.entity_name}")
            return self._group_assignments_cache[cache_key]

        try:
            assignments = self._fetch_entity_assignments(
                entity_id=group_entity.entity_id, entity_type="GROUP"
            )

            # Convert to PermissionAssignment objects and enrich with names
            enriched_assignments = self._enrich_assignments(assignments)

            # Cache the results
            self._group_assignments_cache[cache_key] = enriched_assignments

            logger.info(
                f"Retrieved {len(enriched_assignments)} assignments for group {group_entity.entity_name}"
            )
            return enriched_assignments

        except Exception as e:
            logger.error(
                f"Error retrieving assignments for group {group_entity.entity_name}: {str(e)}"
            )
            return []

    def get_entity_assignments(self, entity: EntityReference) -> List[PermissionAssignment]:
        """
        Get all permission assignments for an entity (user or group).

        Args:
            entity: The entity reference (user or group)

        Returns:
            List of permission assignments for the entity
        """
        if entity.entity_type == EntityType.USER:
            return self.get_user_assignments(entity)
        elif entity.entity_type == EntityType.GROUP:
            return self.get_group_assignments(entity)
        else:
            logger.error(f"Unsupported entity type: {entity.entity_type}")
            return []

    def get_assignments_for_multiple_entities(
        self, entities: List[EntityReference]
    ) -> Dict[str, List[PermissionAssignment]]:
        """
        Get assignments for multiple entities efficiently.

        Args:
            entities: List of entity references

        Returns:
            Dictionary mapping entity IDs to their assignments
        """
        results = {}

        for entity in entities:
            try:
                assignments = self.get_entity_assignments(entity)
                results[entity.entity_id] = assignments
            except Exception as e:
                logger.error(
                    f"Error retrieving assignments for entity {entity.entity_name}: {str(e)}"
                )
                results[entity.entity_id] = []

        return results

    def warm_cache_for_entities(self, entities: List[EntityReference]) -> None:
        """
        Pre-populate cache for a list of entities to improve performance.

        Args:
            entities: List of entity references to pre-load into cache
        """
        logger.info(f"Warming cache for {len(entities)} entities")

        for entity in entities:
            try:
                self.get_entity_assignments(entity)
            except Exception as e:
                logger.warning(f"Failed to warm cache for entity {entity.entity_name}: {str(e)}")

    def clear_cache(self) -> None:
        """Clear all cached assignment data."""
        self._user_assignments_cache.clear()
        self._group_assignments_cache.clear()
        self._permission_set_cache.clear()
        self._account_cache.clear()
        logger.info("Assignment cache cleared")

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the current cache state.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "user_assignments_cache_size": len(self._user_assignments_cache),
            "group_assignments_cache_size": len(self._group_assignments_cache),
            "permission_set_cache_size": len(self._permission_set_cache),
            "account_cache_size": len(self._account_cache),
        }

    def _fetch_entity_assignments(self, entity_id: str, entity_type: str) -> List[Dict[str, str]]:
        """
        Fetch raw assignment data from AWS APIs.

        Args:
            entity_id: The entity ID to fetch assignments for
            entity_type: The entity type (USER or GROUP)

        Returns:
            List of raw assignment dictionaries from AWS API
        """
        assignments = []

        try:
            # Get all permission sets in the instance
            permission_sets = self._get_all_permission_sets()

            # Get all accounts in the organization
            accounts = self._get_all_accounts()

            # For each permission set and account combination, check for assignments
            for permission_set_arn in permission_sets:
                for account in accounts:
                    account_id = account["Id"]

                    try:
                        # Check if this entity has an assignment for this permission set and account
                        response = self.sso_admin_client.list_account_assignments(
                            InstanceArn=self.instance_arn,
                            AccountId=account_id,
                            PermissionSetArn=permission_set_arn,
                        )

                        # Filter assignments for this specific entity
                        for assignment in response.get("AccountAssignments", []):
                            if (
                                assignment.get("PrincipalId") == entity_id
                                and assignment.get("PrincipalType") == entity_type
                            ):
                                assignments.append(
                                    {
                                        "PermissionSetArn": permission_set_arn,
                                        "AccountId": account_id,
                                        "PrincipalId": entity_id,
                                        "PrincipalType": entity_type,
                                    }
                                )
                                # Found an assignment for this entity, no need to check other accounts for this permission set
                                break

                    except ClientError as e:
                        error_code = e.response.get("Error", {}).get("Code", "")
                        if error_code not in ["AccessDenied", "UnauthorizedOperation"]:
                            logger.warning(
                                f"Error checking assignments for account {account_id}, "
                                f"permission set {permission_set_arn}: {str(e)}"
                            )
                        continue

        except Exception as e:
            logger.error(f"Error fetching assignments for entity {entity_id}: {str(e)}")
            raise

        return assignments

    def _get_all_permission_sets(self) -> List[str]:
        """Get all permission sets in the instance."""
        if "permission_sets" in self._assignment_cache:
            return self._assignment_cache["permission_sets"]

        try:
            permission_sets = []
            paginator = self.sso_admin_client.get_paginator("list_permission_sets")

            for page in paginator.paginate(InstanceArn=self.instance_arn):
                permission_sets.extend(page.get("PermissionSets", []))

            # Cache the results
            self._assignment_cache["permission_sets"] = permission_sets
            return permission_sets

        except Exception as e:
            logger.error(f"Error retrieving permission sets: {str(e)}")
            raise

    def _get_all_accounts(self) -> List[Dict[str, str]]:
        """Get all accounts in the organization."""
        if "accounts" in self._assignment_cache:
            return self._assignment_cache["accounts"]

        try:
            accounts = []
            paginator = self.organizations_client.get_paginator("list_accounts")

            for page in paginator.paginate():
                accounts.extend(page.get("Accounts", []))

            # Cache the results
            self._assignment_cache["accounts"] = accounts
            return accounts

        except Exception as e:
            logger.error(f"Error retrieving accounts: {str(e)}")
            raise

    def _enrich_assignments(
        self, raw_assignments: List[Dict[str, str]]
    ) -> List[PermissionAssignment]:
        """
        Convert raw assignment data to enriched PermissionAssignment objects.

        Args:
            raw_assignments: List of raw assignment dictionaries from AWS API

        Returns:
            List of enriched PermissionAssignment objects
        """
        enriched_assignments = []

        for assignment in raw_assignments:
            try:
                permission_set_arn = assignment.get("PermissionSetArn", "")
                account_id = assignment.get("AccountId", "")

                # Get permission set name
                permission_set_name = self._get_permission_set_name(permission_set_arn)

                # Get account name
                account_name = self._get_account_name(account_id)

                # Create PermissionAssignment object
                enriched_assignment = PermissionAssignment(
                    permission_set_arn=permission_set_arn,
                    permission_set_name=permission_set_name,
                    account_id=account_id,
                    account_name=account_name,
                )

                enriched_assignments.append(enriched_assignment)

            except Exception as e:
                logger.warning(f"Error enriching assignment {assignment}: {str(e)}")
                continue

        return enriched_assignments

    def _get_permission_set_name(self, permission_set_arn: str) -> str:
        """Get permission set name from ARN, with caching."""
        if permission_set_arn in self._permission_set_cache:
            return self._permission_set_cache[permission_set_arn].get("name", "")

        try:
            response = self.sso_admin_client.describe_permission_set(
                InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
            )

            permission_set = response.get("PermissionSet", {})
            name = permission_set.get("Name", "")
            description = permission_set.get("Description", "")

            # Cache the result
            self._permission_set_cache[permission_set_arn] = {
                "name": name,
                "description": description,
            }

            return name

        except Exception as e:
            logger.warning(
                f"Error retrieving permission set name for {permission_set_arn}: {str(e)}"
            )
            return ""

    def _get_account_name(self, account_id: str) -> str:
        """Get account name from ID, with caching."""
        if account_id in self._account_cache:
            return self._account_cache[account_id]

        try:
            # Try to get account name from cache first
            if "accounts" in self._assignment_cache:
                for account in self._assignment_cache["accounts"]:
                    if account.get("Id") == account_id:
                        account_name = account.get("Name", "")
                        self._account_cache[account_id] = account_name
                        return account_name

            # If not in cache, try to get from Organizations API
            response = self.organizations_client.describe_account(AccountId=account_id)
            account_name = response.get("Account", {}).get("Name", "")

            # Cache the result
            self._account_cache[account_id] = account_name
            return account_name

        except Exception as e:
            logger.warning(f"Error retrieving account name for {account_id}: {str(e)}")
            return ""
