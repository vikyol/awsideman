"""
Template validator for AWS Identity Center templates.

This module provides comprehensive validation of templates including:
- Structure validation
- Entity resolution and validation
- Permission set validation
- Account validation
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

from ..permission_cloning.models import EntityReference
from .interfaces import AWSClientManagerProtocol, EntityResolverProtocol, TemplateValidatorInterface
from .models import Template

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of template validation."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    resolved_entities: Dict[str, EntityReference]
    resolved_accounts: List[str]

    def __post_init__(self):
        """Set is_valid based on errors."""
        if self.is_valid is None:
            self.is_valid = len(self.errors) == 0

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)

    def merge(self, other: "ValidationResult") -> None:
        """Merge another validation result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.resolved_entities.update(other.resolved_entities)
        self.resolved_accounts.extend(other.resolved_accounts)
        self.is_valid = len(self.errors) == 0


class TemplateValidator(TemplateValidatorInterface):
    """Validates template structure and resolves entities."""

    def __init__(
        self, client_manager: AWSClientManagerProtocol, instance_arn: str, identity_store_id: str
    ):
        """Initialize the template validator."""
        self.client_manager = client_manager
        self.instance_arn = instance_arn
        self.identity_store_id = identity_store_id
        self._entity_resolver = None
        self._identity_center_client = None
        self._organizations_client = None

    @property
    def entity_resolver(self) -> EntityResolverProtocol:
        """Get the entity resolver, creating it if needed."""
        if self._entity_resolver is None:
            from ..permission_cloning.entity_resolver import EntityResolver

            self._entity_resolver = EntityResolver(self.client_manager, self.identity_store_id)
        return self._entity_resolver

    @property
    def identity_center_client(self):
        """Get the Identity Center client."""
        if self._identity_center_client is None:
            self._identity_center_client = self.client_manager.get_identity_center_client()
        return self._identity_center_client

    @property
    def organizations_client(self):
        """Get the Organizations client."""
        if self._organizations_client is None:
            self._organizations_client = self.client_manager.get_organizations_client()
        return self._organizations_client

    def validate_template(self, template: Template) -> ValidationResult:
        """Comprehensive template validation."""
        result = ValidationResult(
            is_valid=True, errors=[], warnings=[], resolved_entities={}, resolved_accounts=[]
        )

        # Validate structure first
        structure_errors = self.validate_structure(template)
        for error in structure_errors:
            result.add_error(error)

        if not result.is_valid:
            return result

        # Validate entities
        entity_errors = self.validate_entities(template)
        for error in entity_errors:
            result.add_error(error)

        # Validate permission sets
        permission_set_errors = self.validate_permission_sets(template)
        for error in permission_set_errors:
            result.add_error(error)

        # Validate accounts
        account_errors = self.validate_accounts(template)
        for error in account_errors:
            result.add_error(error)

        return result

    def validate_structure(self, template: Template) -> List[str]:
        """Validate template structure and required fields."""
        errors = []

        # Validate metadata
        if not template.metadata.name:
            errors.append("Template name is required")

        # Validate assignments
        if not template.assignments:
            errors.append("At least one assignment must be specified")
        else:
            for i, assignment in enumerate(template.assignments):
                try:
                    assignment.__post_init__()
                except ValueError as e:
                    errors.append(f"Assignment {i + 1}: {str(e)}")

        return errors

    def validate_entities(self, template: Template) -> List[str]:
        """Validate that all entities exist and are resolvable."""
        errors = []

        for assignment in template.assignments:
            for entity_ref in assignment.entities:
                try:
                    # Parse entity reference (user:name or group:name)
                    entity_type, entity_name = self._parse_entity_reference(entity_ref)

                    # Resolve entity
                    resolved_entity = self.entity_resolver.resolve_entity_by_name(
                        entity_type, entity_name
                    )

                    if not resolved_entity:
                        errors.append(f"Entity not found: {entity_ref}")
                    else:
                        # Store resolved entity for later use
                        if not hasattr(self, "_resolved_entities"):
                            self._resolved_entities = {}
                        self._resolved_entities[entity_ref] = resolved_entity

                except ValueError as e:
                    errors.append(f"Invalid entity reference '{entity_ref}': {str(e)}")

        return errors

    def validate_permission_sets(self, template: Template) -> List[str]:
        """Validate that all permission sets exist."""
        errors = []

        try:
            # Get all permission sets from AWS
            response = self.identity_center_client.list_permission_sets(
                InstanceArn=self.instance_arn
            )

            existing_permission_sets = set()
            for permission_set_id in response.get("PermissionSetArns", []):
                # Get permission set details
                ps_response = self.identity_center_client.describe_permission_set(
                    InstanceArn=self.instance_arn, PermissionSetArn=permission_set_id
                )
                name = ps_response.get("PermissionSet", {}).get("Name")
                if name:
                    existing_permission_sets.add(name)

            # Validate each permission set in template
            for assignment in template.assignments:
                for permission_set in assignment.permission_sets:
                    if permission_set not in existing_permission_sets:
                        errors.append(f"Permission set not found: {permission_set}")

        except Exception as e:
            logger.error(f"Failed to validate permission sets: {e}")
            errors.append(f"Failed to validate permission sets: {str(e)}")

        return errors

    def validate_accounts(self, template: Template) -> List[str]:
        """Validate account IDs and tag filters."""
        errors = []

        for assignment in template.assignments:
            targets = assignment.targets

            if targets.account_ids:
                # Validate account IDs
                for account_id in targets.account_ids:
                    if not self._is_valid_account_id(account_id):
                        errors.append(f"Invalid account ID format: {account_id}")

            if targets.account_tags:
                # Validate tag structure
                for key, value in targets.account_tags.items():
                    if not key or not value:
                        errors.append(f"Invalid tag: {key}={value}")

            if targets.exclude_accounts:
                # Validate exclude account IDs
                for account_id in targets.exclude_accounts:
                    if not self._is_valid_account_id(account_id):
                        errors.append(f"Invalid exclude account ID format: {account_id}")

        return errors

    def _parse_entity_reference(self, entity_ref: str) -> tuple[str, str]:
        """Parse entity reference in format 'type:name'."""
        if ":" not in entity_ref:
            raise ValueError("Entity reference must be in format 'type:name'")

        parts = entity_ref.split(":", 1)
        if len(parts) != 2:
            raise ValueError("Entity reference must be in format 'type:name'")

        entity_type, entity_name = parts

        if entity_type.lower() not in ["user", "group"]:
            raise ValueError("Entity type must be 'user' or 'group'")

        if not entity_name.strip():
            raise ValueError("Entity name cannot be empty")

        return entity_type.lower(), entity_name.strip()

    def _is_valid_account_id(self, account_id: str) -> bool:
        """Validate AWS account ID format."""
        # AWS account IDs are 12-digit numbers
        return account_id.isdigit() and len(account_id) == 12

    def get_resolved_entities(self) -> Dict[str, EntityReference]:
        """Get all resolved entities from validation."""
        return getattr(self, "_resolved_entities", {})

    def get_resolved_accounts(self, template: Template) -> List[str]:
        """Resolve and return all target accounts for a template."""
        accounts = set()

        try:
            for assignment in template.assignments:
                targets = assignment.targets

                if targets.account_ids:
                    # Direct account IDs
                    accounts.update(targets.account_ids)

                elif targets.account_tags:
                    # Resolve accounts by tags
                    tag_accounts = self._resolve_accounts_by_tags(targets.account_tags)
                    accounts.update(tag_accounts)

                # Remove excluded accounts
                if targets.exclude_accounts:
                    accounts.difference_update(targets.exclude_accounts)

            return list(accounts)

        except Exception as e:
            logger.error(f"Failed to resolve accounts: {e}")
            return []

    def _resolve_accounts_by_tags(self, tags: Dict[str, str]) -> List[str]:
        """Resolve account IDs based on tag filters."""
        try:
            # List all accounts in the organization
            response = self.organizations_client.list_accounts()
            accounts = response.get("Accounts", [])

            matching_accounts = []

            for account in accounts:
                if account.get("Status") != "ACTIVE":
                    continue

                # Get account tags
                try:
                    tags_response = self.organizations_client.list_tags_for_resource(
                        ResourceId=account["Id"]
                    )
                    account_tags = {
                        tag["Key"]: tag["Value"] for tag in tags_response.get("Tags", [])
                    }

                    # Check if account matches all required tags
                    matches = True
                    for required_key, required_value in tags.items():
                        if account_tags.get(required_key) != required_value:
                            matches = False
                            break

                    if matches:
                        matching_accounts.append(account["Id"])

                except Exception as e:
                    logger.warning(f"Failed to get tags for account {account['Id']}: {e}")
                    continue

            return matching_accounts

        except Exception as e:
            logger.error(f"Failed to resolve accounts by tags: {e}")
            return []
