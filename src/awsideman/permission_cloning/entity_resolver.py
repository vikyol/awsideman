"""
Entity validation and resolution system for AWS Identity Center.

This module provides functionality to validate and resolve user and group references
in AWS Identity Center, including checking entity existence and resolving names to IDs
and vice versa.
"""

import logging
from typing import Dict, List, Optional, Tuple

from botocore.exceptions import ClientError

from ..aws_clients.manager import AWSClientManager
from .models import EntityReference, EntityType, ValidationResult, ValidationResultType

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Validates and resolves user and group references in AWS Identity Center.

    This class provides methods to:
    - Validate that entities exist in AWS Identity Center
    - Resolve entity names to IDs and vice versa
    - Check entity existence efficiently with caching
    """

    def __init__(self, client_manager: AWSClientManager, identity_store_id: str):
        """
        Initialize the EntityResolver.

        Args:
            client_manager: AWS client manager for accessing Identity Center services
            identity_store_id: The Identity Store ID for the AWS Identity Center instance
        """
        self.client_manager = client_manager
        self.identity_store_id = identity_store_id
        self._identity_store_client = None

        # Cache for entity lookups to improve performance
        self._user_cache: Dict[str, Dict[str, str]] = {}  # {id: {name, email, ...}}
        self._group_cache: Dict[str, Dict[str, str]] = {}  # {id: {name, description, ...}}
        self._user_name_to_id_cache: Dict[str, str] = {}  # {name: id}
        self._group_name_to_id_cache: Dict[str, str] = {}  # {name: id}

    @property
    def identity_store_client(self):
        """Get the Identity Store client, creating it if needed."""
        if self._identity_store_client is None:
            self._identity_store_client = self.client_manager.get_identity_store_client()
        return self._identity_store_client

    def validate_entity(self, entity: EntityReference) -> ValidationResult:
        """
        Validate that an entity reference is valid and exists in AWS Identity Center.

        Args:
            entity: The entity reference to validate

        Returns:
            ValidationResult indicating success or failure with details
        """
        # First validate the entity reference structure
        structure_validation = entity.validate()
        if structure_validation.has_errors:
            return structure_validation

        # Check if entity exists in AWS Identity Center
        try:
            exists, error_message = self._check_entity_exists(entity.entity_type, entity.entity_id)
            if not exists:
                return ValidationResult(
                    ValidationResultType.ERROR,
                    [
                        error_message
                        or f"{entity.entity_type.value} with ID {entity.entity_id} not found"
                    ],
                )

            # Verify the name matches if we have it cached
            cached_name = self._get_cached_entity_name(entity.entity_type, entity.entity_id)
            if cached_name and cached_name != entity.entity_name:
                return ValidationResult(
                    ValidationResultType.WARNING,
                    [f"Entity name mismatch: expected '{cached_name}', got '{entity.entity_name}'"],
                )

            return ValidationResult(ValidationResultType.SUCCESS, [])

        except Exception as e:
            logger.error(f"Error validating entity {entity.entity_id}: {str(e)}")
            return ValidationResult(
                ValidationResultType.ERROR, [f"Failed to validate entity: {str(e)}"]
            )

    def resolve_entity_by_id(
        self, entity_type: EntityType, entity_id: str
    ) -> Optional[EntityReference]:
        """
        Resolve an entity by its ID to get complete entity information.

        Args:
            entity_type: The type of entity (USER or GROUP)
            entity_id: The unique identifier of the entity

        Returns:
            EntityReference with complete information, or None if not found
        """
        try:
            if entity_type == EntityType.USER:
                user_info = self._get_user_by_id(entity_id)
                if user_info:
                    return EntityReference(
                        entity_type=EntityType.USER,
                        entity_id=entity_id,
                        entity_name=user_info.get("UserName", ""),
                    )
            elif entity_type == EntityType.GROUP:
                group_info = self._get_group_by_id(entity_id)
                if group_info:
                    return EntityReference(
                        entity_type=EntityType.GROUP,
                        entity_id=entity_id,
                        entity_name=group_info.get("DisplayName", ""),
                    )

            return None

        except Exception as e:
            logger.error(f"Error resolving entity by ID {entity_id}: {str(e)}")
            return None

    def resolve_entity_by_name(
        self, entity_type: EntityType, entity_name: str
    ) -> Optional[EntityReference]:
        """
        Resolve an entity by its name to get complete entity information.

        Args:
            entity_type: The type of entity (USER or GROUP)
            entity_name: The name of the entity

        Returns:
            EntityReference with complete information, or None if not found
        """
        try:
            if entity_type == EntityType.USER:
                user_info = self._get_user_by_name(entity_name)
                if user_info:
                    return EntityReference(
                        entity_type=EntityType.USER,
                        entity_id=user_info.get("UserId", ""),
                        entity_name=entity_name,
                    )
            elif entity_type == EntityType.GROUP:
                group_info = self._get_group_by_name(entity_name)
                if group_info:
                    return EntityReference(
                        entity_type=EntityType.GROUP,
                        entity_id=group_info.get("GroupId", ""),
                        entity_name=entity_name,
                    )

            return None

        except Exception as e:
            logger.error(f"Error resolving entity by name {entity_name}: {str(e)}")
            return None

    def validate_entities(self, entities: List[EntityReference]) -> ValidationResult:
        """
        Validate multiple entity references.

        Args:
            entities: List of entity references to validate

        Returns:
            ValidationResult with combined results from all validations
        """
        all_errors = []
        all_warnings = []

        for i, entity in enumerate(entities):
            validation = self.validate_entity(entity)
            if validation.has_errors:
                all_errors.extend([f"Entity {i+1}: {msg}" for msg in validation.messages])
            elif validation.has_warnings:
                all_warnings.extend([f"Entity {i+1}: {msg}" for msg in validation.messages])

        if all_errors:
            return ValidationResult(ValidationResultType.ERROR, all_errors)
        elif all_warnings:
            return ValidationResult(ValidationResultType.WARNING, all_warnings)
        else:
            return ValidationResult(ValidationResultType.SUCCESS, [])

    def check_entities_exist(
        self, entities: List[EntityReference]
    ) -> Tuple[List[EntityReference], List[str]]:
        """
        Check which entities exist and return lists of existing entities and error messages.

        Args:
            entities: List of entity references to check

        Returns:
            Tuple of (existing_entities, error_messages)
        """
        existing_entities = []
        error_messages = []

        for entity in entities:
            validation = self.validate_entity(entity)
            if validation.is_valid or validation.has_warnings:
                existing_entities.append(entity)
            else:
                error_messages.extend(validation.messages)

        return existing_entities, error_messages

    def _check_entity_exists(
        self, entity_type: EntityType, entity_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if an entity exists in AWS Identity Center.

        Args:
            entity_type: The type of entity to check
            entity_id: The ID of the entity to check

        Returns:
            Tuple of (exists, error_message)
        """
        try:
            if entity_type == EntityType.USER:
                user_info = self._get_user_by_id(entity_id)
                return user_info is not None, None
            elif entity_type == EntityType.GROUP:
                group_info = self._get_group_by_id(entity_id)
                return group_info is not None, None
            else:
                return False, f"Unknown entity type: {entity_type}"

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ["ResourceNotFoundException", "NotFound"]:
                return False, f"{entity_type.value} not found"
            else:
                return False, f"AWS error checking {entity_type.value}: {str(e)}"
        except Exception as e:
            return False, f"Error checking {entity_type.value}: {str(e)}"

    def _get_user_by_id(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        Get user information by ID, with caching.

        Args:
            user_id: The user ID to look up

        Returns:
            User information dictionary or None if not found
        """
        # Check cache first
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        try:
            response = self.identity_store_client.describe_user(
                IdentityStoreId=self.identity_store_id, UserId=user_id
            )

            user_info = {
                "UserId": response.get("UserId", ""),
                "UserName": response.get("UserName", ""),
                "DisplayName": response.get("DisplayName", ""),
                "Name": response.get("Name", {}),
            }

            # Cache the result
            self._user_cache[user_id] = user_info
            if user_info.get("UserName"):
                self._user_name_to_id_cache[user_info["UserName"]] = user_id

            return user_info

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ["ResourceNotFoundException", "NotFound"]:
                return None
            raise

    def _get_group_by_id(self, group_id: str) -> Optional[Dict[str, str]]:
        """
        Get group information by ID, with caching.

        Args:
            group_id: The group ID to look up

        Returns:
            Group information dictionary or None if not found
        """
        # Check cache first
        if group_id in self._group_cache:
            return self._group_cache[group_id]

        try:
            response = self.identity_store_client.describe_group(
                IdentityStoreId=self.identity_store_id, GroupId=group_id
            )

            group_info = {
                "GroupId": response.get("GroupId", ""),
                "DisplayName": response.get("DisplayName", ""),
                "Description": response.get("Description", ""),
            }

            # Cache the result
            self._group_cache[group_id] = group_info
            if group_info.get("DisplayName"):
                self._group_name_to_id_cache[group_info["DisplayName"]] = group_id

            return group_info

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ["ResourceNotFoundException", "NotFound"]:
                return None
            raise

    def _get_user_by_name(self, user_name: str) -> Optional[Dict[str, str]]:
        """
        Get user information by name, with caching.

        Args:
            user_name: The username to look up

        Returns:
            User information dictionary or None if not found
        """
        # Check cache first
        if user_name in self._user_name_to_id_cache:
            user_id = self._user_name_to_id_cache[user_name]
            return self._get_user_by_id(user_id)

        try:
            # Search for user by username
            response = self.identity_store_client.list_users(
                IdentityStoreId=self.identity_store_id,
                MaxResults=1,  # Only need one match for name lookup
                Filters=[{"AttributePath": "UserName", "AttributeValue": user_name}],
            )

            users = response.get("Users", [])
            if users:
                user = users[0]  # Take the first match
                user_id = user.get("UserId", "")

                # Cache the result
                user_info = {
                    "UserId": user_id,
                    "UserName": user.get("UserName", ""),
                    "DisplayName": user.get("DisplayName", ""),
                    "Name": user.get("Name", {}),
                }

                self._user_cache[user_id] = user_info
                self._user_name_to_id_cache[user_name] = user_id

                return user_info

            return None

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ["ResourceNotFoundException", "NotFound"]:
                return None
            raise

    def _get_group_by_name(self, group_name: str) -> Optional[Dict[str, str]]:
        """
        Get group information by name, with caching.

        Args:
            group_name: The group name to look up

        Returns:
            Group information dictionary or None if not found
        """
        # Check cache first
        if group_name in self._group_name_to_id_cache:
            group_id = self._group_name_to_id_cache[group_name]
            return self._get_group_by_id(group_id)

        try:
            # Search for group by display name
            response = self.identity_store_client.list_groups(
                IdentityStoreId=self.identity_store_id,
                MaxResults=1,  # Only need one match for name lookup
                Filters=[{"AttributePath": "DisplayName", "AttributeValue": group_name}],
            )

            groups = response.get("Groups", [])
            if groups:
                group = groups[0]  # Take the first match
                group_id = group.get("GroupId", "")

                # Cache the result
                group_info = {
                    "GroupId": group_id,
                    "DisplayName": group.get("DisplayName", ""),
                    "Description": group.get("Description", ""),
                }

                self._group_cache[group_id] = group_info
                self._group_name_to_id_cache[group_name] = group_id

                return group_info

            return None

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ["ResourceNotFoundException", "NotFound"]:
                return None
            raise

    def _get_cached_entity_name(self, entity_type: EntityType, entity_id: str) -> Optional[str]:
        """
        Get the cached name for an entity if available.

        Args:
            entity_type: The type of entity
            entity_id: The ID of the entity

        Returns:
            The cached name or None if not cached
        """
        if entity_type == EntityType.USER:
            user_info = self._user_cache.get(entity_id)
            return user_info.get("UserName") if user_info else None
        elif entity_type == EntityType.GROUP:
            group_info = self._group_cache.get(entity_id)
            return group_info.get("DisplayName") if group_info else None

        return None

    def clear_cache(self) -> None:
        """Clear all cached entity information."""
        self._user_cache.clear()
        self._group_cache.clear()
        self._user_name_to_id_cache.clear()
        self._group_name_to_id_cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the current cache state.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "user_cache_size": len(self._user_cache),
            "group_cache_size": len(self._group_cache),
            "user_name_to_id_cache_size": len(self._user_name_to_id_cache),
            "group_name_to_id_cache_size": len(self._group_name_to_id_cache),
        }

    def warm_cache_for_entities(self, entities: List[EntityReference]) -> None:
        """
        Pre-populate cache for a list of entities to improve performance.

        Args:
            entities: List of entity references to pre-load into cache
        """
        for entity in entities:
            try:
                if entity.entity_type == EntityType.USER:
                    self._get_user_by_id(entity.entity_id)
                elif entity.entity_type == EntityType.GROUP:
                    self._get_group_by_id(entity.entity_id)
            except Exception as e:
                logger.warning(f"Failed to warm cache for entity {entity.entity_id}: {str(e)}")

    def search_entities(
        self, entity_type: EntityType, search_term: str, max_results: int = 10
    ) -> List[EntityReference]:
        """
        Search for entities by name or display name.

        Args:
            entity_type: The type of entity to search for
            search_term: The search term to match against names
            max_results: Maximum number of results to return

        Returns:
            List of matching EntityReference objects
        """
        try:
            if entity_type == EntityType.USER:
                response = self.identity_store_client.list_users(
                    IdentityStoreId=self.identity_store_id,
                    MaxResults=max_results,
                    Filters=[{"AttributePath": "UserName", "AttributeValue": search_term}],
                )

                users = response.get("Users", [])
                return [
                    EntityReference(
                        entity_type=EntityType.USER,
                        entity_id=user.get("UserId", ""),
                        entity_name=user.get("UserName", ""),
                    )
                    for user in users
                ]

            elif entity_type == EntityType.GROUP:
                response = self.identity_store_client.list_groups(
                    IdentityStoreId=self.identity_store_id,
                    MaxResults=max_results,
                    Filters=[{"AttributePath": "DisplayName", "AttributeValue": search_term}],
                )

                groups = response.get("Groups", [])
                return [
                    EntityReference(
                        entity_type=EntityType.GROUP,
                        entity_id=group.get("GroupId", ""),
                        entity_name=group.get("DisplayName", ""),
                    )
                    for group in groups
                ]

            return []

        except Exception as e:
            logger.error(
                f"Error searching for {entity_type.value}s with term '{search_term}': {str(e)}"
            )
            return []
