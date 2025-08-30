"""
Resource comparators for backup diff operations.

This module provides specialized comparison logic for different AWS Identity Center
resource types, detecting creation, deletion, and modification of resources between
two backup states.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

from .diff_models import AttributeChange, ChangeType, ResourceChange, ResourceDiff
from .models import AssignmentData, GroupData, PermissionSetData, UserData


class ResourceComparator(ABC):
    """Abstract base class for resource comparators."""

    @abstractmethod
    def compare(self, source_resources: List[Any], target_resources: List[Any]) -> ResourceDiff:
        """
        Compare resources of a specific type between two backup states.

        Args:
            source_resources: Resources from the source backup
            target_resources: Resources from the target backup

        Returns:
            ResourceDiff containing all detected changes
        """
        pass

    def _create_resource_maps(self, resources: List[Any], id_field: str) -> Dict[str, Any]:
        """
        Create a mapping of resource ID to resource object.

        Args:
            resources: List of resource objects
            id_field: Name of the field containing the resource ID

        Returns:
            Dictionary mapping resource IDs to resource objects
        """
        resource_map = {}
        for resource in resources:
            if hasattr(resource, id_field):
                resource_id = getattr(resource, id_field)
                resource_map[resource_id] = resource
        return resource_map

    def _detect_attribute_changes(
        self, before: Any, after: Any, exclude_fields: Optional[Set[str]] = None
    ) -> List[AttributeChange]:
        """
        Detect changes in attributes between two resource objects.

        Args:
            before: Resource object from source backup
            after: Resource object from target backup
            exclude_fields: Set of field names to exclude from comparison

        Returns:
            List of AttributeChange objects for modified attributes
        """
        if exclude_fields is None:
            exclude_fields = set()

        changes = []

        # Convert objects to dictionaries for comparison
        before_dict = before.to_dict() if hasattr(before, "to_dict") else before.__dict__
        after_dict = after.to_dict() if hasattr(after, "to_dict") else after.__dict__

        # Check all attributes in both objects
        all_attributes = set(before_dict.keys()) | set(after_dict.keys())

        for attr_name in all_attributes:
            if attr_name in exclude_fields:
                continue

            before_value = before_dict.get(attr_name)
            after_value = after_dict.get(attr_name)

            # Handle None values and type differences
            if before_value != after_value:
                # Special handling for lists (order-independent comparison for some fields)
                if isinstance(before_value, list) and isinstance(after_value, list):
                    # For membership lists, compare as sets
                    if attr_name in ["members", "managed_policies"]:
                        if set(before_value) != set(after_value):
                            changes.append(
                                AttributeChange(
                                    attribute_name=attr_name,
                                    before_value=before_value,
                                    after_value=after_value,
                                )
                            )
                    else:
                        # For other lists, compare directly
                        if before_value != after_value:
                            changes.append(
                                AttributeChange(
                                    attribute_name=attr_name,
                                    before_value=before_value,
                                    after_value=after_value,
                                )
                            )
                else:
                    changes.append(
                        AttributeChange(
                            attribute_name=attr_name,
                            before_value=before_value,
                            after_value=after_value,
                        )
                    )

        return changes


class UserComparator(ResourceComparator):
    """Comparator for AWS Identity Center users."""

    def compare(
        self, source_resources: List[UserData], target_resources: List[UserData]
    ) -> ResourceDiff:
        """
        Compare user resources between two backup states.

        Args:
            source_resources: Users from the source backup
            target_resources: Users from the target backup

        Returns:
            ResourceDiff containing user changes
        """
        source_users = self._create_resource_maps(source_resources, "user_id")
        target_users = self._create_resource_maps(target_resources, "user_id")

        source_ids = set(source_users.keys())
        target_ids = set(target_users.keys())

        created = []
        deleted = []
        modified = []

        # Find created users (in target but not in source)
        for user_id in target_ids - source_ids:
            user = target_users[user_id]
            created.append(
                ResourceChange(
                    change_type=ChangeType.CREATED,
                    resource_type="users",
                    resource_id=user_id,
                    resource_name=user.user_name,
                    after_value=user.to_dict(),
                )
            )

        # Find deleted users (in source but not in target)
        for user_id in source_ids - target_ids:
            user = source_users[user_id]
            deleted.append(
                ResourceChange(
                    change_type=ChangeType.DELETED,
                    resource_type="users",
                    resource_id=user_id,
                    resource_name=user.user_name,
                    before_value=user.to_dict(),
                )
            )

        # Find modified users (in both, but with differences)
        for user_id in source_ids & target_ids:
            source_user = source_users[user_id]
            target_user = target_users[user_id]

            attribute_changes = self._detect_attribute_changes(source_user, target_user)

            if attribute_changes:
                modified.append(
                    ResourceChange(
                        change_type=ChangeType.MODIFIED,
                        resource_type="users",
                        resource_id=user_id,
                        resource_name=target_user.user_name,
                        before_value=source_user.to_dict(),
                        after_value=target_user.to_dict(),
                        attribute_changes=attribute_changes,
                    )
                )

        return ResourceDiff(
            resource_type="users", created=created, deleted=deleted, modified=modified
        )


class GroupComparator(ResourceComparator):
    """Comparator for AWS Identity Center groups."""

    def compare(
        self, source_resources: List[GroupData], target_resources: List[GroupData]
    ) -> ResourceDiff:
        """
        Compare group resources between two backup states.

        Args:
            source_resources: Groups from the source backup
            target_resources: Groups from the target backup

        Returns:
            ResourceDiff containing group changes
        """
        source_groups = self._create_resource_maps(source_resources, "group_id")
        target_groups = self._create_resource_maps(target_resources, "group_id")

        source_ids = set(source_groups.keys())
        target_ids = set(target_groups.keys())

        created = []
        deleted = []
        modified = []

        # Find created groups (in target but not in source)
        for group_id in target_ids - source_ids:
            group = target_groups[group_id]
            created.append(
                ResourceChange(
                    change_type=ChangeType.CREATED,
                    resource_type="groups",
                    resource_id=group_id,
                    resource_name=group.display_name,
                    after_value=group.to_dict(),
                )
            )

        # Find deleted groups (in source but not in target)
        for group_id in source_ids - target_ids:
            group = source_groups[group_id]
            deleted.append(
                ResourceChange(
                    change_type=ChangeType.DELETED,
                    resource_type="groups",
                    resource_id=group_id,
                    resource_name=group.display_name,
                    before_value=group.to_dict(),
                )
            )

        # Find modified groups (in both, but with differences)
        for group_id in source_ids & target_ids:
            source_group = source_groups[group_id]
            target_group = target_groups[group_id]

            attribute_changes = self._detect_attribute_changes(source_group, target_group)

            if attribute_changes:
                modified.append(
                    ResourceChange(
                        change_type=ChangeType.MODIFIED,
                        resource_type="groups",
                        resource_id=group_id,
                        resource_name=target_group.display_name,
                        before_value=source_group.to_dict(),
                        after_value=target_group.to_dict(),
                        attribute_changes=attribute_changes,
                    )
                )

        return ResourceDiff(
            resource_type="groups", created=created, deleted=deleted, modified=modified
        )


class PermissionSetComparator(ResourceComparator):
    """Comparator for AWS Identity Center permission sets."""

    def compare(
        self, source_resources: List[PermissionSetData], target_resources: List[PermissionSetData]
    ) -> ResourceDiff:
        """
        Compare permission set resources between two backup states.

        Args:
            source_resources: Permission sets from the source backup
            target_resources: Permission sets from the target backup

        Returns:
            ResourceDiff containing permission set changes
        """
        source_permission_sets = self._create_resource_maps(source_resources, "permission_set_arn")
        target_permission_sets = self._create_resource_maps(target_resources, "permission_set_arn")

        source_arns = set(source_permission_sets.keys())
        target_arns = set(target_permission_sets.keys())

        created = []
        deleted = []
        modified = []

        # Find created permission sets (in target but not in source)
        for ps_arn in target_arns - source_arns:
            ps = target_permission_sets[ps_arn]
            created.append(
                ResourceChange(
                    change_type=ChangeType.CREATED,
                    resource_type="permission_sets",
                    resource_id=ps_arn,
                    resource_name=ps.name,
                    after_value=ps.to_dict(),
                )
            )

        # Find deleted permission sets (in source but not in target)
        for ps_arn in source_arns - target_arns:
            ps = source_permission_sets[ps_arn]
            deleted.append(
                ResourceChange(
                    change_type=ChangeType.DELETED,
                    resource_type="permission_sets",
                    resource_id=ps_arn,
                    resource_name=ps.name,
                    before_value=ps.to_dict(),
                )
            )

        # Find modified permission sets (in both, but with differences)
        for ps_arn in source_arns & target_arns:
            source_ps = source_permission_sets[ps_arn]
            target_ps = target_permission_sets[ps_arn]

            attribute_changes = self._detect_attribute_changes(source_ps, target_ps)

            if attribute_changes:
                modified.append(
                    ResourceChange(
                        change_type=ChangeType.MODIFIED,
                        resource_type="permission_sets",
                        resource_id=ps_arn,
                        resource_name=target_ps.name,
                        before_value=source_ps.to_dict(),
                        after_value=target_ps.to_dict(),
                        attribute_changes=attribute_changes,
                    )
                )

        return ResourceDiff(
            resource_type="permission_sets", created=created, deleted=deleted, modified=modified
        )


class AssignmentComparator(ResourceComparator):
    """Comparator for AWS Identity Center permission set assignments."""

    def compare(
        self, source_resources: List[AssignmentData], target_resources: List[AssignmentData]
    ) -> ResourceDiff:
        """
        Compare assignment resources between two backup states.

        Args:
            source_resources: Assignments from the source backup
            target_resources: Assignments from the target backup

        Returns:
            ResourceDiff containing assignment changes
        """
        # Create composite keys for assignments since they don't have a single unique ID
        source_assignments = self._create_assignment_maps(source_resources)
        target_assignments = self._create_assignment_maps(target_resources)

        source_keys = set(source_assignments.keys())
        target_keys = set(target_assignments.keys())

        created = []
        deleted = []
        modified = []

        # Find created assignments (in target but not in source)
        for assignment_key in target_keys - source_keys:
            assignment = target_assignments[assignment_key]
            created.append(
                ResourceChange(
                    change_type=ChangeType.CREATED,
                    resource_type="assignments",
                    resource_id=assignment_key,
                    resource_name=f"{assignment.principal_type}:{assignment.principal_id}",
                    after_value=assignment.to_dict(),
                )
            )

        # Find deleted assignments (in source but not in target)
        for assignment_key in source_keys - target_keys:
            assignment = source_assignments[assignment_key]
            deleted.append(
                ResourceChange(
                    change_type=ChangeType.DELETED,
                    resource_type="assignments",
                    resource_id=assignment_key,
                    resource_name=f"{assignment.principal_type}:{assignment.principal_id}",
                    before_value=assignment.to_dict(),
                )
            )

        # Find modified assignments (in both, but with differences)
        # Note: Assignments typically don't have modifiable attributes beyond their key components,
        # but we check for completeness
        for assignment_key in source_keys & target_keys:
            source_assignment = source_assignments[assignment_key]
            target_assignment = target_assignments[assignment_key]

            attribute_changes = self._detect_attribute_changes(source_assignment, target_assignment)

            if attribute_changes:
                modified.append(
                    ResourceChange(
                        change_type=ChangeType.MODIFIED,
                        resource_type="assignments",
                        resource_id=assignment_key,
                        resource_name=f"{target_assignment.principal_type}:{target_assignment.principal_id}",
                        before_value=source_assignment.to_dict(),
                        after_value=target_assignment.to_dict(),
                        attribute_changes=attribute_changes,
                    )
                )

        return ResourceDiff(
            resource_type="assignments", created=created, deleted=deleted, modified=modified
        )

    def _create_assignment_maps(
        self, assignments: List[AssignmentData]
    ) -> Dict[str, AssignmentData]:
        """
        Create a mapping of composite assignment keys to assignment objects.

        Args:
            assignments: List of assignment objects

        Returns:
            Dictionary mapping composite keys to assignment objects
        """
        assignment_map = {}
        for assignment in assignments:
            # Create a composite key from all identifying attributes
            key = f"{assignment.account_id}:{assignment.permission_set_arn}:{assignment.principal_type}:{assignment.principal_id}"
            assignment_map[key] = assignment
        return assignment_map
