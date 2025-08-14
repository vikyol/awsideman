"""Resource inspection component for AWS Identity Center status monitoring."""

import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from .status_infrastructure import BaseStatusChecker, StatusCheckError
from .status_models import ResourceInspectionStatus, ResourceStatus, ResourceType, StatusLevel

logger = logging.getLogger(__name__)


class ResourceInspector(BaseStatusChecker):
    """
    Resource inspector component for AWS Identity Center.

    Provides detailed status checking for specific Identity Center resources
    including users, groups, and permission sets. Includes resource suggestion
    functionality for similar resources when target not found.
    """

    def __init__(self, idc_client, config=None):
        """
        Initialize the resource inspector.

        Args:
            idc_client: AWS Identity Center client wrapper
            config: Status check configuration
        """
        super().__init__(idc_client, config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Cache for resource listings to improve suggestion performance
        self._user_cache: Optional[List[Dict[str, Any]]] = None
        self._group_cache: Optional[List[Dict[str, Any]]] = None
        self._permission_set_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_minutes = 5  # Cache TTL in minutes

    async def check_status(self) -> ResourceInspectionStatus:
        """
        Perform basic resource inspection status check.

        This is a placeholder implementation for the base class requirement.
        Actual resource inspection should use the specific inspect_* methods.

        Returns:
            ResourceInspectionStatus: Basic inspection status
        """
        timestamp = datetime.now(timezone.utc)

        return ResourceInspectionStatus(
            timestamp=timestamp,
            status=StatusLevel.HEALTHY,
            message="Resource inspector is ready for specific resource inspections",
            inspection_type=None,
        )

    async def inspect_user(self, user_identifier: str) -> ResourceInspectionStatus:
        """
        Inspect a specific user resource.

        Args:
            user_identifier: User ID, username, or email to inspect

        Returns:
            ResourceInspectionStatus: User inspection results with suggestions if not found
        """
        timestamp = datetime.now(timezone.utc)

        try:
            self.logger.info(f"Inspecting user: {user_identifier}")

            # Try to find and retrieve the user
            user_data = await self._find_user(user_identifier)

            if user_data:
                # User found, create detailed status
                resource_status = await self._create_user_status(user_data)

                return ResourceInspectionStatus(
                    timestamp=timestamp,
                    status=StatusLevel.HEALTHY,
                    message=f"User '{user_identifier}' found and healthy",
                    target_resource=resource_status,
                    inspection_type=ResourceType.USER,
                )
            else:
                # User not found, get suggestions
                suggestions = await self._get_user_suggestions(user_identifier)

                return ResourceInspectionStatus(
                    timestamp=timestamp,
                    status=StatusLevel.WARNING,
                    message=f"User '{user_identifier}' not found",
                    similar_resources=suggestions,
                    inspection_type=ResourceType.USER,
                )

        except Exception as e:
            self.logger.error(f"Error inspecting user {user_identifier}: {str(e)}")

            return ResourceInspectionStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=f"Failed to inspect user '{user_identifier}': {str(e)}",
                inspection_type=ResourceType.USER,
                errors=[str(e)],
            )

    async def inspect_group(self, group_identifier: str) -> ResourceInspectionStatus:
        """
        Inspect a specific group resource.

        Args:
            group_identifier: Group ID or display name to inspect

        Returns:
            ResourceInspectionStatus: Group inspection results with suggestions if not found
        """
        timestamp = datetime.now(timezone.utc)

        try:
            self.logger.info(f"Inspecting group: {group_identifier}")

            # Try to find and retrieve the group
            group_data = await self._find_group(group_identifier)

            if group_data:
                # Group found, create detailed status
                resource_status = await self._create_group_status(group_data)

                return ResourceInspectionStatus(
                    timestamp=timestamp,
                    status=StatusLevel.HEALTHY,
                    message=f"Group '{group_identifier}' found and healthy",
                    target_resource=resource_status,
                    inspection_type=ResourceType.GROUP,
                )
            else:
                # Group not found, get suggestions
                suggestions = await self._get_group_suggestions(group_identifier)

                return ResourceInspectionStatus(
                    timestamp=timestamp,
                    status=StatusLevel.WARNING,
                    message=f"Group '{group_identifier}' not found",
                    similar_resources=suggestions,
                    inspection_type=ResourceType.GROUP,
                )

        except Exception as e:
            self.logger.error(f"Error inspecting group {group_identifier}: {str(e)}")

            return ResourceInspectionStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=f"Failed to inspect group '{group_identifier}': {str(e)}",
                inspection_type=ResourceType.GROUP,
                errors=[str(e)],
            )

    async def inspect_permission_set(
        self, permission_set_identifier: str
    ) -> ResourceInspectionStatus:
        """
        Inspect a specific permission set resource.

        Args:
            permission_set_identifier: Permission set ARN or name to inspect

        Returns:
            ResourceInspectionStatus: Permission set inspection results with suggestions if not found
        """
        timestamp = datetime.now(timezone.utc)

        try:
            self.logger.info(f"Inspecting permission set: {permission_set_identifier}")

            # Try to find and retrieve the permission set
            permission_set_data = await self._find_permission_set(permission_set_identifier)

            if permission_set_data:
                # Permission set found, create detailed status
                resource_status = await self._create_permission_set_status(permission_set_data)

                return ResourceInspectionStatus(
                    timestamp=timestamp,
                    status=StatusLevel.HEALTHY,
                    message=f"Permission set '{permission_set_identifier}' found and healthy",
                    target_resource=resource_status,
                    inspection_type=ResourceType.PERMISSION_SET,
                )
            else:
                # Permission set not found, get suggestions
                suggestions = await self._get_permission_set_suggestions(permission_set_identifier)

                return ResourceInspectionStatus(
                    timestamp=timestamp,
                    status=StatusLevel.WARNING,
                    message=f"Permission set '{permission_set_identifier}' not found",
                    similar_resources=suggestions,
                    inspection_type=ResourceType.PERMISSION_SET,
                )

        except Exception as e:
            self.logger.error(
                f"Error inspecting permission set {permission_set_identifier}: {str(e)}"
            )

            return ResourceInspectionStatus(
                timestamp=timestamp,
                status=StatusLevel.CRITICAL,
                message=f"Failed to inspect permission set '{permission_set_identifier}': {str(e)}",
                inspection_type=ResourceType.PERMISSION_SET,
                errors=[str(e)],
            )

    async def _find_user(self, user_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Find a user by ID, username, or email.

        Args:
            user_identifier: User identifier to search for

        Returns:
            Dict containing user data if found, None otherwise
        """
        try:
            identity_store_client = self.idc_client.get_raw_identity_store_client()
            identity_store_id = await self._get_identity_store_id()

            # Check if identifier is a UUID (user ID)
            uuid_pattern = (
                r"^(?:[0-9a-f]{10}-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
            )

            if re.match(uuid_pattern, user_identifier, re.IGNORECASE):
                # Direct lookup by user ID
                try:
                    response = identity_store_client.describe_user(
                        IdentityStoreId=identity_store_id, UserId=user_identifier
                    )
                    return response
                except ClientError as e:
                    if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                        return None
                    raise
            else:
                # Search by username or email
                # First try username search
                try:
                    response = identity_store_client.list_users(
                        IdentityStoreId=identity_store_id,
                        Filters=[{"AttributePath": "UserName", "AttributeValue": user_identifier}],
                    )

                    users = response.get("Users", [])
                    if users:
                        # Get full user details
                        user_id = users[0].get("UserId")
                        return identity_store_client.describe_user(
                            IdentityStoreId=identity_store_id, UserId=user_id
                        )
                except ClientError:
                    pass

                # If username search failed, try email search by listing all users
                users = await self._get_all_users()
                for user in users:
                    emails = user.get("Emails", [])
                    for email in emails:
                        if email.get("Value", "").lower() == user_identifier.lower():
                            # Get full user details
                            user_id = user.get("UserId")
                            return identity_store_client.describe_user(
                                IdentityStoreId=identity_store_id, UserId=user_id
                            )

            return None

        except Exception as e:
            self.logger.error(f"Error finding user {user_identifier}: {str(e)}")
            raise

    async def _find_group(self, group_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Find a group by ID or display name.

        Args:
            group_identifier: Group identifier to search for

        Returns:
            Dict containing group data if found, None otherwise
        """
        try:
            identity_store_client = self.idc_client.get_raw_identity_store_client()
            identity_store_id = await self._get_identity_store_id()

            # Check if identifier is a UUID (group ID)
            uuid_pattern = (
                r"^(?:[0-9a-f]{10}-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
            )

            if re.match(uuid_pattern, group_identifier, re.IGNORECASE):
                # Direct lookup by group ID
                try:
                    response = identity_store_client.describe_group(
                        IdentityStoreId=identity_store_id, GroupId=group_identifier
                    )
                    return response
                except ClientError as e:
                    if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                        return None
                    raise
            else:
                # Search by display name
                try:
                    response = identity_store_client.list_groups(
                        IdentityStoreId=identity_store_id,
                        Filters=[
                            {"AttributePath": "DisplayName", "AttributeValue": group_identifier}
                        ],
                    )

                    groups = response.get("Groups", [])
                    if groups:
                        # Get full group details
                        group_id = groups[0].get("GroupId")
                        return identity_store_client.describe_group(
                            IdentityStoreId=identity_store_id, GroupId=group_id
                        )
                except ClientError:
                    pass

            return None

        except Exception as e:
            self.logger.error(f"Error finding group {group_identifier}: {str(e)}")
            raise

    async def _find_permission_set(
        self, permission_set_identifier: str
    ) -> Optional[Dict[str, Any]]:
        """
        Find a permission set by ARN or name.

        Args:
            permission_set_identifier: Permission set identifier to search for

        Returns:
            Dict containing permission set data if found, None otherwise
        """
        try:
            sso_admin_client = self.idc_client.get_raw_identity_center_client()
            instance_arn = await self._get_instance_arn()

            # Check if identifier is an ARN
            if permission_set_identifier.startswith("arn:aws:sso:::permissionSet/"):
                # Direct lookup by ARN
                try:
                    response = sso_admin_client.describe_permission_set(
                        InstanceArn=instance_arn, PermissionSetArn=permission_set_identifier
                    )
                    return response.get("PermissionSet")
                except ClientError as e:
                    if e.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                        return None
                    raise
            else:
                # Search by name
                permission_sets = await self._get_all_permission_sets()
                for ps in permission_sets:
                    if ps.get("Name", "").lower() == permission_set_identifier.lower():
                        # Get full permission set details
                        return sso_admin_client.describe_permission_set(
                            InstanceArn=instance_arn, PermissionSetArn=ps.get("PermissionSetArn")
                        ).get("PermissionSet")

            return None

        except Exception as e:
            self.logger.error(f"Error finding permission set {permission_set_identifier}: {str(e)}")
            raise

    async def _create_user_status(self, user_data: Dict[str, Any]) -> ResourceStatus:
        """
        Create a ResourceStatus object for a user.

        Args:
            user_data: User data from AWS API

        Returns:
            ResourceStatus: User resource status
        """
        user_id = user_data.get("UserId", "")
        username = user_data.get("UserName", "")
        display_name = user_data.get("DisplayName", "")

        # Determine resource name (prefer display name, fall back to username)
        resource_name = display_name or username or user_id

        # Extract configuration details
        configuration = {
            "username": username,
            "display_name": display_name,
            "emails": user_data.get("Emails", []),
            "name": user_data.get("Name", {}),
            "status": user_data.get("Status", ""),
            "timezone": user_data.get("Timezone", ""),
            "locale": user_data.get("Locale", ""),
        }

        # Extract health details
        health_details = {
            "active": user_data.get("Status", "").upper() == "ENABLED",
            "email_count": len(user_data.get("Emails", [])),
            "has_display_name": bool(display_name),
            "has_username": bool(username),
        }

        # Parse timestamps
        last_updated = None
        if "Meta" in user_data and "LastModified" in user_data["Meta"]:
            try:
                last_updated = datetime.fromisoformat(
                    user_data["Meta"]["LastModified"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return ResourceStatus(
            resource_id=user_id,
            resource_name=resource_name,
            resource_type=ResourceType.USER,
            exists=True,
            status=StatusLevel.HEALTHY,
            last_updated=last_updated,
            configuration=configuration,
            health_details=health_details,
        )

    async def _create_group_status(self, group_data: Dict[str, Any]) -> ResourceStatus:
        """
        Create a ResourceStatus object for a group.

        Args:
            group_data: Group data from AWS API

        Returns:
            ResourceStatus: Group resource status
        """
        group_id = group_data.get("GroupId", "")
        display_name = group_data.get("DisplayName", "")

        # Extract configuration details
        configuration = {
            "display_name": display_name,
            "description": group_data.get("Description", ""),
        }

        # Extract health details
        health_details = {
            "has_display_name": bool(display_name),
            "has_description": bool(group_data.get("Description", "")),
        }

        # Parse timestamps
        last_updated = None
        if "Meta" in group_data and "LastModified" in group_data["Meta"]:
            try:
                last_updated = datetime.fromisoformat(
                    group_data["Meta"]["LastModified"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return ResourceStatus(
            resource_id=group_id,
            resource_name=display_name or group_id,
            resource_type=ResourceType.GROUP,
            exists=True,
            status=StatusLevel.HEALTHY,
            last_updated=last_updated,
            configuration=configuration,
            health_details=health_details,
        )

    async def _create_permission_set_status(
        self, permission_set_data: Dict[str, Any]
    ) -> ResourceStatus:
        """
        Create a ResourceStatus object for a permission set.

        Args:
            permission_set_data: Permission set data from AWS API

        Returns:
            ResourceStatus: Permission set resource status
        """
        permission_set_arn = permission_set_data.get("PermissionSetArn", "")
        name = permission_set_data.get("Name", "")

        # Extract configuration details
        configuration = {
            "name": name,
            "description": permission_set_data.get("Description", ""),
            "session_duration": permission_set_data.get("SessionDuration", ""),
            "relay_state": permission_set_data.get("RelayState", ""),
        }

        # Extract health details
        health_details = {
            "has_name": bool(name),
            "has_description": bool(permission_set_data.get("Description", "")),
            "has_session_duration": bool(permission_set_data.get("SessionDuration", "")),
            "has_relay_state": bool(permission_set_data.get("RelayState", "")),
        }

        # Parse timestamps
        last_updated = None
        if "CreatedDate" in permission_set_data:
            try:
                last_updated = permission_set_data["CreatedDate"]
                if isinstance(last_updated, str):
                    last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return ResourceStatus(
            resource_id=permission_set_arn,
            resource_name=name or permission_set_arn,
            resource_type=ResourceType.PERMISSION_SET,
            exists=True,
            status=StatusLevel.HEALTHY,
            last_updated=last_updated,
            configuration=configuration,
            health_details=health_details,
        )

    async def _get_user_suggestions(
        self, user_identifier: str, max_suggestions: int = 5
    ) -> List[str]:
        """
        Get suggestions for similar users when target user not found.

        Args:
            user_identifier: Original user identifier that wasn't found
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of suggested user identifiers
        """
        try:
            users = await self._get_all_users()
            suggestions = []

            # Create list of searchable strings for each user
            user_strings = []
            for user in users:
                searchable = []

                # Add username
                if user.get("UserName"):
                    searchable.append(user["UserName"])

                # Add display name
                if user.get("DisplayName"):
                    searchable.append(user["DisplayName"])

                # Add emails
                for email in user.get("Emails", []):
                    if email.get("Value"):
                        searchable.append(email["Value"])

                # Add name components
                name = user.get("Name", {})
                if name.get("GivenName"):
                    searchable.append(name["GivenName"])
                if name.get("FamilyName"):
                    searchable.append(name["FamilyName"])

                user_strings.append((user, searchable))

            # Calculate similarity scores
            scored_users = []
            for user, searchable_strings in user_strings:
                max_similarity = 0
                best_match = ""

                for searchable in searchable_strings:
                    similarity = SequenceMatcher(
                        None, user_identifier.lower(), searchable.lower()
                    ).ratio()
                    if similarity > max_similarity:
                        max_similarity = similarity
                        best_match = searchable

                if max_similarity > 0.5:  # Only include reasonably similar matches
                    scored_users.append((max_similarity, best_match, user))

            # Sort by similarity score (descending) and take top suggestions
            scored_users.sort(key=lambda x: x[0], reverse=True)

            for _, match_string, user in scored_users[:max_suggestions]:
                # Format suggestion with multiple identifiers
                suggestion_parts = []

                if user.get("UserName"):
                    suggestion_parts.append(f"username: {user['UserName']}")

                if user.get("DisplayName"):
                    suggestion_parts.append(f"name: {user['DisplayName']}")

                primary_email = None
                for email in user.get("Emails", []):
                    if email.get("Primary", False):
                        primary_email = email.get("Value")
                        break

                if primary_email:
                    suggestion_parts.append(f"email: {primary_email}")

                if suggestion_parts:
                    suggestions.append(" | ".join(suggestion_parts))

            return suggestions

        except Exception as e:
            self.logger.error(f"Error getting user suggestions: {str(e)}")
            return []

    async def _get_group_suggestions(
        self, group_identifier: str, max_suggestions: int = 5
    ) -> List[str]:
        """
        Get suggestions for similar groups when target group not found.

        Args:
            group_identifier: Original group identifier that wasn't found
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of suggested group identifiers
        """
        try:
            groups = await self._get_all_groups()
            suggestions = []

            # Calculate similarity scores
            scored_groups = []
            for group in groups:
                display_name = group.get("DisplayName", "")
                description = group.get("Description", "")

                # Calculate similarity with display name
                name_similarity = SequenceMatcher(
                    None, group_identifier.lower(), display_name.lower()
                ).ratio()

                # Calculate similarity with description (lower weight)
                desc_similarity = (
                    SequenceMatcher(None, group_identifier.lower(), description.lower()).ratio()
                    * 0.5
                )

                max_similarity = max(name_similarity, desc_similarity)

                if max_similarity > 0.5:  # Only include reasonably similar matches
                    scored_groups.append((max_similarity, group))

            # Sort by similarity score (descending) and take top suggestions
            scored_groups.sort(key=lambda x: x[0], reverse=True)

            for _, group in scored_groups[:max_suggestions]:
                # Format suggestion
                suggestion_parts = []

                if group.get("DisplayName"):
                    suggestion_parts.append(f"name: {group['DisplayName']}")

                if group.get("Description"):
                    suggestion_parts.append(f"description: {group['Description'][:50]}...")

                if suggestion_parts:
                    suggestions.append(" | ".join(suggestion_parts))

            return suggestions

        except Exception as e:
            self.logger.error(f"Error getting group suggestions: {str(e)}")
            return []

    async def _get_permission_set_suggestions(
        self, permission_set_identifier: str, max_suggestions: int = 5
    ) -> List[str]:
        """
        Get suggestions for similar permission sets when target permission set not found.

        Args:
            permission_set_identifier: Original permission set identifier that wasn't found
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of suggested permission set identifiers
        """
        try:
            permission_sets = await self._get_all_permission_sets()
            suggestions = []

            # Calculate similarity scores
            scored_permission_sets = []
            for ps in permission_sets:
                name = ps.get("Name", "")
                description = ps.get("Description", "")

                # Calculate similarity with name
                name_similarity = SequenceMatcher(
                    None, permission_set_identifier.lower(), name.lower()
                ).ratio()

                # Calculate similarity with description (lower weight)
                desc_similarity = (
                    SequenceMatcher(
                        None, permission_set_identifier.lower(), description.lower()
                    ).ratio()
                    * 0.5
                )

                max_similarity = max(name_similarity, desc_similarity)

                if max_similarity > 0.5:  # Only include reasonably similar matches
                    scored_permission_sets.append((max_similarity, ps))

            # Sort by similarity score (descending) and take top suggestions
            scored_permission_sets.sort(key=lambda x: x[0], reverse=True)

            for _, ps in scored_permission_sets[:max_suggestions]:
                # Format suggestion
                suggestion_parts = []

                if ps.get("Name"):
                    suggestion_parts.append(f"name: {ps['Name']}")

                if ps.get("Description"):
                    suggestion_parts.append(f"description: {ps['Description'][:50]}...")

                if suggestion_parts:
                    suggestions.append(" | ".join(suggestion_parts))

            return suggestions

        except Exception as e:
            self.logger.error(f"Error getting permission set suggestions: {str(e)}")
            return []

    async def _get_all_users(self) -> List[Dict[str, Any]]:
        """
        Get all users with caching.

        Returns:
            List of user dictionaries
        """
        # Check cache validity
        if (
            self._user_cache is not None
            and self._cache_timestamp is not None
            and (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
            < self._cache_ttl_minutes * 60
        ):
            return self._user_cache

        try:
            identity_store_client = self.idc_client.get_raw_identity_store_client()
            identity_store_id = await self._get_identity_store_id()

            users = []
            next_token = None

            while True:
                params = {"IdentityStoreId": identity_store_id}
                if next_token:
                    params["NextToken"] = next_token

                response = identity_store_client.list_users(**params)
                users.extend(response.get("Users", []))

                next_token = response.get("NextToken")
                if not next_token:
                    break

            # Update cache
            self._user_cache = users
            self._cache_timestamp = datetime.now(timezone.utc)

            return users

        except Exception as e:
            self.logger.error(f"Error getting all users: {str(e)}")
            return []

    async def _get_all_groups(self) -> List[Dict[str, Any]]:
        """
        Get all groups with caching.

        Returns:
            List of group dictionaries
        """
        # Check cache validity
        if (
            self._group_cache is not None
            and self._cache_timestamp is not None
            and (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
            < self._cache_ttl_minutes * 60
        ):
            return self._group_cache

        try:
            identity_store_client = self.idc_client.get_raw_identity_store_client()
            identity_store_id = await self._get_identity_store_id()

            groups = []
            next_token = None

            while True:
                params = {"IdentityStoreId": identity_store_id}
                if next_token:
                    params["NextToken"] = next_token

                response = identity_store_client.list_groups(**params)
                groups.extend(response.get("Groups", []))

                next_token = response.get("NextToken")
                if not next_token:
                    break

            # Update cache
            self._group_cache = groups
            self._cache_timestamp = datetime.now(timezone.utc)

            return groups

        except Exception as e:
            self.logger.error(f"Error getting all groups: {str(e)}")
            return []

    async def _get_all_permission_sets(self) -> List[Dict[str, Any]]:
        """
        Get all permission sets with caching.

        Returns:
            List of permission set dictionaries
        """
        # Check cache validity
        if (
            self._permission_set_cache is not None
            and self._cache_timestamp is not None
            and (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
            < self._cache_ttl_minutes * 60
        ):
            return self._permission_set_cache

        try:
            sso_admin_client = self.idc_client.get_raw_identity_center_client()
            instance_arn = await self._get_instance_arn()

            permission_sets = []
            next_token = None

            while True:
                params = {"InstanceArn": instance_arn}
                if next_token:
                    params["NextToken"] = next_token

                response = sso_admin_client.list_permission_sets(**params)

                # Get detailed information for each permission set
                for ps_arn in response.get("PermissionSets", []):
                    try:
                        ps_detail = sso_admin_client.describe_permission_set(
                            InstanceArn=instance_arn, PermissionSetArn=ps_arn
                        )
                        permission_sets.append(ps_detail.get("PermissionSet", {}))
                    except ClientError:
                        # Skip permission sets we can't describe
                        continue

                next_token = response.get("NextToken")
                if not next_token:
                    break

            # Update cache
            self._permission_set_cache = permission_sets
            self._cache_timestamp = datetime.now(timezone.utc)

            return permission_sets

        except Exception as e:
            self.logger.error(f"Error getting all permission sets: {str(e)}")
            return []

    async def _get_identity_store_id(self) -> str:
        """
        Get the Identity Store ID from the Identity Center instance.

        Returns:
            str: Identity Store ID
        """
        try:
            sso_admin_client = self.idc_client.get_raw_identity_center_client()

            # List instances to get the identity store ID
            response = sso_admin_client.list_instances()
            instances = response.get("Instances", [])

            if not instances:
                raise StatusCheckError("No Identity Center instances found", "ResourceInspector")

            # Use the first instance
            return instances[0]["IdentityStoreId"]

        except Exception as e:
            self.logger.error(f"Error getting identity store ID: {str(e)}")
            raise

    async def _get_instance_arn(self) -> str:
        """
        Get the Identity Center instance ARN.

        Returns:
            str: Instance ARN
        """
        try:
            sso_admin_client = self.idc_client.get_raw_identity_center_client()

            # List instances to get the instance ARN
            response = sso_admin_client.list_instances()
            instances = response.get("Instances", [])

            if not instances:
                raise StatusCheckError("No Identity Center instances found", "ResourceInspector")

            # Use the first instance
            return instances[0]["InstanceArn"]

        except Exception as e:
            self.logger.error(f"Error getting instance ARN: {str(e)}")
            raise

    def clear_cache(self) -> None:
        """Clear the resource cache to force fresh data on next request."""
        self._user_cache = None
        self._group_cache = None
        self._permission_set_cache = None
        self._cache_timestamp = None
        self.logger.info("Resource cache cleared")
