"""
Preview generator for permission cloning operations.

This module provides functionality to preview assignment copy operations and permission set
cloning without making actual changes to AWS resources.
"""

import logging
from typing import Any, Dict, List, Optional

from ..aws_clients.manager import AWSClientManager
from .assignment_retriever import AssignmentRetriever
from .filter_engine import FilterEngine
from .models import CopyFilters, PermissionAssignment, PermissionSetConfig
from .permission_set_retriever import PermissionSetRetriever

logger = logging.getLogger(__name__)


class PreviewGenerator:
    """
    Generates previews for permission cloning operations.

    This class provides previews for:
    - Assignment copy operations (user-to-user, group-to-group, cross-entity)
    - Permission set cloning operations
    - Conflict detection and duplicate identification
    - Resource impact analysis
    """

    def __init__(
        self,
        client_manager: AWSClientManager,
        instance_arn: str,
        identity_store_id: str = "d-1234567890",
    ):
        """
        Initialize the PreviewGenerator.

        Args:
            client_manager: AWS client manager for accessing AWS services
            instance_arn: SSO instance ARN
            identity_store_id: Identity store ID (defaults to a dummy value for testing)
        """
        self.client_manager = client_manager
        self.instance_arn = instance_arn
        self.assignment_retriever = AssignmentRetriever(
            client_manager, instance_arn, identity_store_id
        )
        self.permission_set_retriever = PermissionSetRetriever(client_manager, instance_arn)
        self.filter_engine = FilterEngine()

    def preview_assignment_copy(
        self,
        source_entity_id: str,
        source_entity_type: str,
        target_entity_id: str,
        target_entity_type: str,
        filters: Optional[CopyFilters] = None,
    ) -> Dict[str, Any]:
        """
        Preview an assignment copy operation.

        Args:
            source_entity_id: ID of the source entity
            source_entity_type: Type of the source entity (USER or GROUP)
            target_entity_id: ID of the target entity
            target_entity_type: Type of the target entity (USER or GROUP)
            filters: Optional filters to apply to the copy operation

        Returns:
            Dictionary containing preview information
        """
        logger.info(
            f"Generating preview for assignment copy from {source_entity_type}:{source_entity_id} to {target_entity_type}:{target_entity_id}"
        )

        try:
            # Get source assignments
            source_assignments = self._get_source_assignments(source_entity_id, source_entity_type)

            # Apply filters if provided
            if filters:
                source_assignments = self.filter_engine.apply_filters(source_assignments, filters)

            # Get target assignments for conflict detection
            target_assignments = self._get_target_assignments(target_entity_id, target_entity_type)

            # Analyze conflicts and duplicates
            conflicts, duplicates, new_assignments = self._analyze_assignments(
                source_assignments, target_assignments
            )

            # Generate preview summary
            preview = {
                "operation_type": "assignment_copy",
                "source_entity": {
                    "id": source_entity_id,
                    "type": source_entity_type,
                    "total_assignments": len(source_assignments),
                },
                "target_entity": {
                    "id": target_entity_id,
                    "type": target_entity_type,
                    "existing_assignments": len(target_assignments),
                },
                "copy_summary": {
                    "total_source_assignments": len(source_assignments),
                    "assignments_to_copy": len(new_assignments),
                    "duplicate_assignments": len(duplicates),
                    "conflicting_assignments": len(conflicts),
                },
                "assignments": {
                    "new": new_assignments,
                    "duplicates": duplicates,
                    "conflicts": conflicts,
                },
                "filters_applied": filters.to_dict() if filters else None,
                "estimated_impact": self._estimate_impact(new_assignments),
                "warnings": [],  # Add empty warnings list to prevent KeyError
            }

            logger.info(
                f"Preview generated: {len(new_assignments)} assignments to copy, {len(duplicates)} duplicates, {len(conflicts)} conflicts"
            )
            return preview

        except Exception as e:
            logger.error(f"Failed to generate assignment copy preview: {str(e)}")
            raise

    def preview_permission_set_clone(
        self,
        source_permission_set_name: str,
        target_permission_set_name: str,
        target_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Preview a permission set clone operation.

        Args:
            source_permission_set_name: Name of the source permission set
            target_permission_set_name: Name for the new permission set
            target_description: Optional description for the new permission set

        Returns:
            Dictionary containing preview information
        """
        logger.info(
            f"Generating preview for permission set clone from '{source_permission_set_name}' to '{target_permission_set_name}'"
        )

        try:
            # Get source permission set configuration
            source_arn = self.permission_set_retriever.get_permission_set_by_name(
                source_permission_set_name
            )
            if not source_arn:
                raise ValueError(f"Source permission set '{source_permission_set_name}' not found")

            source_config = self.permission_set_retriever.get_permission_set_config(source_arn)

            # Check if target name already exists
            existing_target = self.permission_set_retriever.get_permission_set_by_name(
                target_permission_set_name
            )

            # Generate preview
            preview = {
                "operation_type": "permission_set_clone",
                "source_permission_set": {
                    "name": source_config.name,
                    "description": source_config.description,
                    "session_duration": source_config.session_duration,
                    "relay_state_url": source_config.relay_state_url,
                },
                "target_permission_set": {
                    "name": target_permission_set_name,
                    "description": target_description or source_config.description,
                    "already_exists": existing_target is not None,
                },
                "policies_summary": {
                    "aws_managed_policies": len(source_config.aws_managed_policies),
                    "customer_managed_policies": len(source_config.customer_managed_policies),
                    "has_inline_policy": source_config.inline_policy is not None,
                },
                "clone_details": {
                    "session_duration_will_copy": source_config.session_duration,
                    "relay_state_will_copy": source_config.relay_state_url is not None,
                    "total_policies_to_copy": (
                        len(source_config.aws_managed_policies)
                        + len(source_config.customer_managed_policies)
                        + (1 if source_config.inline_policy else 0)
                    ),
                },
                "validation": {
                    "can_proceed": existing_target is None,
                    "warnings": self._generate_clone_warnings(
                        source_config, target_permission_set_name
                    ),
                },
            }

            logger.info(
                f"Permission set clone preview generated: {preview['clone_details']['total_policies_to_copy']} policies to copy"
            )
            return preview

        except Exception as e:
            logger.error(f"Failed to generate permission set clone preview: {str(e)}")
            raise

    def preview_bulk_operations(self, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Preview multiple operations in bulk.

        Args:
            operations: List of operation dictionaries with operation details

        Returns:
            Dictionary containing bulk preview information
        """
        logger.info(f"Generating bulk preview for {len(operations)} operations")

        try:
            bulk_preview = {
                "operation_type": "bulk_preview",
                "total_operations": len(operations),
                "operation_summaries": [],
                "overall_impact": {
                    "total_assignments_to_copy": 0,
                    "total_permission_sets_to_clone": 0,
                    "total_conflicts": 0,
                    "total_duplicates": 0,
                },
            }

            for i, operation in enumerate(operations):
                try:
                    if operation.get("type") == "assignment_copy":
                        op_preview = self.preview_assignment_copy(
                            operation["source_entity_id"],
                            operation["source_entity_type"],
                            operation["target_entity_id"],
                            operation["target_entity_type"],
                            operation.get("filters"),
                        )
                        bulk_preview["overall_impact"]["total_assignments_to_copy"] += op_preview[
                            "copy_summary"
                        ]["assignments_to_copy"]
                        bulk_preview["overall_impact"]["total_conflicts"] += op_preview[
                            "copy_summary"
                        ]["conflicting_assignments"]
                        bulk_preview["overall_impact"]["total_duplicates"] += op_preview[
                            "copy_summary"
                        ]["duplicate_assignments"]

                    elif operation.get("type") == "permission_set_clone":
                        op_preview = self.preview_permission_set_clone(
                            operation["source_permission_set_name"],
                            operation["target_permission_set_name"],
                            operation.get("target_description"),
                        )
                        bulk_preview["overall_impact"]["total_permission_sets_to_clone"] += 1

                    bulk_preview["operation_summaries"].append(
                        {
                            "index": i,
                            "type": operation.get("type"),
                            "status": "success",
                            "preview": op_preview,
                        }
                    )

                except Exception as e:
                    bulk_preview["operation_summaries"].append(
                        {
                            "index": i,
                            "type": operation.get("type"),
                            "status": "error",
                            "error": str(e),
                        }
                    )

            logger.info(f"Bulk preview generated for {len(operations)} operations")
            return bulk_preview

        except Exception as e:
            logger.error(f"Failed to generate bulk preview: {str(e)}")
            raise

    def _get_source_assignments(
        self, entity_id: str, entity_type: str
    ) -> List[PermissionAssignment]:
        """Get source entity assignments."""
        try:
            # Use the internal method that accepts entity_id and entity_type directly
            raw_assignments = self.assignment_retriever._fetch_entity_assignments(
                entity_id, entity_type
            )
            # Convert to PermissionAssignment objects and enrich with names
            return self.assignment_retriever._enrich_assignments(raw_assignments)
        except Exception as e:
            logger.error(f"Error getting source assignments: {e}")
            return []

    def _get_target_assignments(
        self, entity_id: str, entity_type: str
    ) -> List[PermissionAssignment]:
        """Get target entity assignments."""
        try:
            # Use the internal method that accepts entity_id and entity_type directly
            raw_assignments = self.assignment_retriever._fetch_entity_assignments(
                entity_id, entity_type
            )
            # Convert to PermissionAssignment objects and enrich with names
            return self.assignment_retriever._enrich_assignments(raw_assignments)
        except Exception as e:
            logger.error(f"Error getting target assignments: {e}")
            return []

    def _analyze_assignments(
        self,
        source_assignments: List[PermissionAssignment],
        target_assignments: List[PermissionAssignment],
    ) -> tuple[List[PermissionAssignment], List[PermissionAssignment], List[PermissionAssignment]]:
        """
        Analyze assignments for conflicts, duplicates, and new assignments.

        Returns:
            Tuple of (conflicts, duplicates, new_assignments)
        """
        conflicts = []
        duplicates = []
        new_assignments = []

        # Create lookup for target assignments
        target_lookup = {
            (assignment.permission_set_arn, assignment.account_id): assignment
            for assignment in target_assignments
        }

        for source_assignment in source_assignments:
            key = (source_assignment.permission_set_arn, source_assignment.account_id)

            if key in target_lookup:
                # Check if it's a duplicate (same permission set and account)
                target_assignment = target_lookup[key]
                if source_assignment.permission_set_name == target_assignment.permission_set_name:
                    duplicates.append(source_assignment)
                else:
                    # Conflict: same permission set ARN but different names
                    conflicts.append(source_assignment)
            else:
                # New assignment
                new_assignments.append(source_assignment)

        return conflicts, duplicates, new_assignments

    def _estimate_impact(self, assignments: List[PermissionAssignment]) -> Dict[str, Any]:
        """Estimate the impact of copying assignments."""
        if not assignments:
            return {"risk_level": "none", "estimated_time": "0s", "affected_accounts": 0}

        # Count unique accounts
        unique_accounts = len(set(assignment.account_id for assignment in assignments))

        # Estimate time (rough calculation: 2 seconds per assignment)
        estimated_seconds = len(assignments) * 2
        estimated_time = f"{estimated_seconds}s"

        # Determine risk level based on number of assignments and accounts
        if len(assignments) > 100 or unique_accounts > 50:
            risk_level = "high"
        elif len(assignments) > 50 or unique_accounts > 20:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "estimated_time": estimated_time,
            "affected_accounts": unique_accounts,
            "total_assignments": len(assignments),
        }

    def preview_assignment_copy_by_name(
        self,
        source_entity_type: str,
        source_entity_name: str,
        target_entity_type: str,
        target_entity_name: str,
        filters: Optional[CopyFilters] = None,
    ) -> Dict[str, Any]:
        """
        Preview an assignment copy operation using entity names.

        Args:
            source_entity_type: Type of the source entity ('user' or 'group')
            source_entity_name: Name of the source entity
            target_entity_type: Type of the target entity ('user' or 'group')
            target_entity_name: Name of the target entity
            filters: Optional filters to apply to the copy operation

        Returns:
            Dictionary containing preview information
        """
        logger.info(
            f"Generating preview for assignment copy from {source_entity_type}:{source_entity_name} to {target_entity_type}:{target_entity_name}"
        )

        try:
            # Resolve entity names to IDs
            from .entity_resolver import EntityResolver
            from .models import EntityType

            entity_resolver = EntityResolver(
                self.client_manager, self.assignment_retriever.identity_store_id
            )

            # Resolve source entity
            source_type = (
                EntityType.USER if source_entity_type.lower() == "user" else EntityType.GROUP
            )
            source_entity = entity_resolver.resolve_entity_by_name(source_type, source_entity_name)

            # Resolve target entity
            target_type = (
                EntityType.USER if target_entity_type.lower() == "user" else EntityType.GROUP
            )
            target_entity = entity_resolver.resolve_entity_by_name(target_type, target_entity_name)

            # Generate preview using resolved IDs
            preview = self.preview_assignment_copy(
                source_entity.entity_id,
                source_entity.entity_type.value,
                target_entity.entity_id,
                target_entity.entity_type.value,
                filters,
            )

            # Update preview with resolved names
            preview["source_entity"]["name"] = source_entity_name
            preview["target_entity"]["name"] = target_entity_name

            return preview

        except Exception as e:
            logger.error(f"Failed to generate assignment copy preview by name: {str(e)}")
            raise

    def _generate_clone_warnings(
        self, source_config: PermissionSetConfig, target_name: str
    ) -> List[str]:
        """Generate warnings for permission set cloning."""
        warnings = []

        # Check for long names
        if len(target_name) > 25:
            warnings.append("Target name is close to the 32-character limit")

        # Check for special characters in name
        if not target_name.replace("-", "").replace("_", "").isalnum():
            warnings.append("Target name contains special characters that may cause issues")

        # Check for no policies
        if (
            not source_config.aws_managed_policies
            and not source_config.customer_managed_policies
            and not source_config.inline_policy
        ):
            warnings.append("Source permission set has no policies defined")

        # Check for long descriptions
        if source_config.description and len(source_config.description) > 600:
            warnings.append("Source description is close to the 700-character limit")

        return warnings
