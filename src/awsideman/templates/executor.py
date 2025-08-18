"""
Template executor for AWS Identity Center templates.

This module handles the execution of templates including applying assignments
and generating previews of what would be executed.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .interfaces import (
    AssignmentCopierProtocol,
    AWSClientManagerProtocol,
    EntityResolverProtocol,
    TemplateExecutorInterface,
)
from .models import Template, TemplateAssignment

logger = logging.getLogger(__name__)


@dataclass
class AssignmentResult:
    """Result of individual assignment operation."""

    entity_name: str
    entity_type: str
    permission_set_name: str
    account_id: str
    account_name: str
    status: str  # 'created', 'skipped', 'failed'
    error_message: Optional[str] = None
    operation_id: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of template execution."""

    success: bool
    assignments_created: List[AssignmentResult]
    assignments_skipped: List[AssignmentResult]
    assignments_failed: List[AssignmentResult]
    operation_id: Optional[str]  # For rollback tracking
    execution_time: float
    error_message: Optional[str] = None

    def __post_init__(self):
        """Set success based on results."""
        if self.success is None:
            self.success = len(self.assignments_failed) == 0

    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        return {
            "total_assignments": len(self.assignments_created)
            + len(self.assignments_skipped)
            + len(self.assignments_failed),
            "created": len(self.assignments_created),
            "skipped": len(self.assignments_skipped),
            "failed": len(self.assignments_failed),
            "success_rate": len(self.assignments_created)
            / max(
                1,
                len(self.assignments_created)
                + len(self.assignments_skipped)
                + len(self.assignments_failed),
            ),
            "execution_time": self.execution_time,
            "operation_id": self.operation_id,
        }


@dataclass
class PreviewResult:
    """Result of template preview."""

    template: Template
    resolved_accounts: List[str]
    total_assignments: int
    entity_details: List[Dict[str, Any]]
    permission_set_details: List[Dict[str, Any]]
    account_details: List[Dict[str, Any]]

    def get_summary(self) -> Dict[str, Any]:
        """Get preview summary."""
        return {
            "template_name": self.template.metadata.name,
            "total_assignments": self.total_assignments,
            "resolved_accounts": len(self.resolved_accounts),
            "entities": len(self.entity_details),
            "permission_sets": len(self.permission_set_details),
        }


class TemplateExecutor(TemplateExecutorInterface):
    """Executes template operations (apply, dry-run)."""

    def __init__(
        self, client_manager: AWSClientManagerProtocol, instance_arn: str, identity_store_id: str
    ):
        """Initialize the template executor."""
        self.client_manager = client_manager
        self.instance_arn = instance_arn
        self.identity_store_id = identity_store_id
        self._entity_resolver = None
        self._assignment_copier = None
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
    def assignment_copier(self) -> AssignmentCopierProtocol:
        """Get the assignment copier, creating it if needed."""
        if self._assignment_copier is None:
            from ..permission_cloning.assignment_copier import AssignmentCopier
            from ..permission_cloning.assignment_retriever import AssignmentRetriever
            from ..permission_cloning.filter_engine import FilterEngine

            assignment_retriever = AssignmentRetriever(
                self.client_manager, self.instance_arn, self.identity_store_id
            )
            filter_engine = FilterEngine()

            self._assignment_copier = AssignmentCopier(
                entity_resolver=self.entity_resolver,
                assignment_retriever=assignment_retriever,
                filter_engine=filter_engine,
            )
        return self._assignment_copier

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

    def apply_template(self, template: Template, dry_run: bool = False) -> ExecutionResult:
        """Apply template assignments."""
        start_time = time.time()
        operation_id = str(uuid.uuid4())

        logger.info(f"Starting template execution: {template.metadata.name} (dry_run={dry_run})")

        # Initialize result tracking
        assignments_created = []
        assignments_skipped = []
        assignments_failed = []

        try:
            # Resolve all accounts for the template
            resolved_accounts = self._resolve_template_accounts(template)
            logger.info(f"Resolved {len(resolved_accounts)} target accounts")

            # Process each assignment
            for assignment in template.assignments:
                assignment_results = self._create_assignments(
                    assignment, resolved_accounts, dry_run, operation_id
                )

                # Categorize results
                for result in assignment_results:
                    if result.status == "created":
                        assignments_created.append(result)
                    elif result.status == "skipped":
                        assignments_skipped.append(result)
                    elif result.status == "failed":
                        assignments_failed.append(result)

            execution_time = time.time() - start_time

            result = ExecutionResult(
                success=len(assignments_failed) == 0,
                assignments_created=assignments_created,
                assignments_skipped=assignments_skipped,
                assignments_failed=assignments_failed,
                operation_id=operation_id,
                execution_time=execution_time,
            )

            logger.info(f"Template execution completed: {result.get_summary()}")
            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Template execution failed: {e}")

            return ExecutionResult(
                success=False,
                assignments_created=assignments_created,
                assignments_skipped=assignments_skipped,
                assignments_failed=assignments_failed,
                operation_id=operation_id,
                execution_time=execution_time,
                error_message=str(e),
            )

    def preview_template(self, template: Template) -> PreviewResult:
        """Generate preview of template execution."""
        logger.info(f"Generating preview for template: {template.metadata.name}")

        # Resolve accounts
        resolved_accounts = self._resolve_template_accounts(template)

        # Get entity details
        entity_details = self._get_entity_details(template)

        # Get permission set details
        permission_set_details = self._get_permission_set_details(template)

        # Get account details
        account_details = self._get_account_details(resolved_accounts)

        # Calculate total assignments
        total_assignments = 0
        for assignment in template.assignments:
            entity_count = len(assignment.entities)
            permission_set_count = len(assignment.permission_sets)
            account_count = len(resolved_accounts)
            total_assignments += entity_count * permission_set_count * account_count

        return PreviewResult(
            template=template,
            resolved_accounts=resolved_accounts,
            total_assignments=total_assignments,
            entity_details=entity_details,
            permission_set_details=permission_set_details,
            account_details=account_details,
        )

    def _resolve_template_accounts(self, template: Template) -> List[str]:
        """Resolve account targets using multi-account logic."""
        accounts = set()

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

    def _create_assignments(
        self, assignment: TemplateAssignment, accounts: List[str], dry_run: bool, operation_id: str
    ) -> List[AssignmentResult]:
        """Create individual assignments from template."""
        results = []

        for entity_ref in assignment.entities:
            for permission_set in assignment.permission_sets:
                for account_id in accounts:
                    result = self._create_single_assignment(
                        entity_ref, permission_set, account_id, dry_run, operation_id
                    )
                    results.append(result)

        return results

    def _create_single_assignment(
        self,
        entity_ref: str,
        permission_set: str,
        account_id: str,
        dry_run: bool,
        operation_id: str,
    ) -> AssignmentResult:
        """Create a single permission assignment."""
        try:
            # Parse entity reference
            entity_type, entity_name = self._parse_entity_reference(entity_ref)

            # Get account name
            account_name = self._get_account_name(account_id)

            if dry_run:
                # Simulate assignment creation
                return AssignmentResult(
                    entity_name=entity_name,
                    entity_type=entity_type,
                    permission_set_name=permission_set,
                    account_id=account_id,
                    account_name=account_name,
                    status="created",
                    operation_id=operation_id,
                )

            # Check if assignment already exists
            if self._assignment_exists(entity_ref, permission_set, account_id):
                return AssignmentResult(
                    entity_name=entity_name,
                    entity_type=entity_type,
                    permission_set_name=permission_set,
                    account_id=account_id,
                    account_name=account_name,
                    status="skipped",
                    error_message="Assignment already exists",
                    operation_id=operation_id,
                )

            # Create assignment
            self._create_assignment_via_api(entity_ref, permission_set, account_id)

            return AssignmentResult(
                entity_name=entity_name,
                entity_type=entity_type,
                permission_set_name=permission_set,
                account_id=account_id,
                account_name=account_name,
                status="created",
                operation_id=operation_id,
            )

        except Exception as e:
            logger.error(
                f"Failed to create assignment {entity_ref}:{permission_set}:{account_id}: {e}"
            )
            return AssignmentResult(
                entity_name=entity_ref,
                entity_type="unknown",
                permission_set_name=permission_set,
                account_id=account_id,
                account_name="unknown",
                status="failed",
                error_message=str(e),
                operation_id=operation_id,
            )

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

    def _get_account_name(self, account_id: str) -> str:
        """Get account name from account ID."""
        try:
            response = self.organizations_client.describe_account(account_id=account_id)
            return response.get("Account", {}).get("Name", account_id)
        except Exception as e:
            logger.warning(f"Failed to get account name for {account_id}: {e}")
            return account_id

    def _assignment_exists(self, entity_ref: str, permission_set: str, account_id: str) -> bool:
        """Check if assignment already exists."""
        try:
            # Parse entity reference
            entity_type, entity_name = self._parse_entity_reference(entity_ref)

            # Convert entity_type string to EntityType enum
            from ..permission_cloning.models import EntityType

            if entity_type == "user":
                entity_type_enum = EntityType.USER
            elif entity_type == "group":
                entity_type_enum = EntityType.GROUP
            else:
                return False

            # Resolve entity
            entity = self.entity_resolver.resolve_entity_by_name(entity_type_enum, entity_name)
            if not entity:
                return False

            # Get permission set ARN
            permission_set_arn = self._get_permission_set_arn(permission_set)
            if not permission_set_arn:
                return False

            # Check for existing assignment
            response = self.identity_center_client.list_account_assignments(
                InstanceArn=self.instance_arn,
                AccountId=account_id,
                PermissionSetArn=permission_set_arn,
            )

            for assignment in response.get("AccountAssignments", []):
                if assignment.get("PrincipalId") == entity.entity_id:
                    return True

            return False

        except Exception as e:
            logger.warning(f"Failed to check if assignment exists: {e}")
            return False

    def _get_permission_set_arn(self, permission_set_name: str) -> Optional[str]:
        """Get permission set ARN by name."""
        try:
            response = self.identity_center_client.list_permission_sets(
                InstanceArn=self.instance_arn
            )

            # The API returns 'PermissionSets' not 'PermissionSetArns'
            permission_set_arns = response.get("PermissionSets", [])

            for permission_set_arn in permission_set_arns:
                ps_response = self.identity_center_client.describe_permission_set(
                    InstanceArn=self.instance_arn, PermissionSetArn=permission_set_arn
                )
                name = ps_response.get("PermissionSet", {}).get("Name")
                if name == permission_set_name:
                    return permission_set_arn

            return None

        except Exception as e:
            logger.error(f"Failed to get permission set ARN for {permission_set_name}: {e}")
            return None

    def _create_assignment_via_api(
        self, entity_ref: str, permission_set: str, account_id: str
    ) -> None:
        """Create assignment via AWS API."""
        try:
            # Parse entity reference
            entity_type, entity_name = self._parse_entity_reference(entity_ref)

            # Convert entity_type string to EntityType enum
            from ..permission_cloning.models import EntityType

            if entity_type == "user":
                entity_type_enum = EntityType.USER
            elif entity_type == "group":
                entity_type_enum = EntityType.GROUP
            else:
                raise ValueError(f"Invalid entity type: {entity_type}")

            # Resolve entity
            entity = self.entity_resolver.resolve_entity_by_name(entity_type_enum, entity_name)
            if not entity:
                raise ValueError(f"Entity not found: {entity_ref}")

            # Get permission set ARN
            permission_set_arn = self._get_permission_set_arn(permission_set)
            if not permission_set_arn:
                raise ValueError(f"Permission set not found: {permission_set}")

            # Create assignment
            self.identity_center_client.create_account_assignment(
                InstanceArn=self.instance_arn,
                TargetId=account_id,
                TargetType="AWS_ACCOUNT",
                PermissionSetArn=permission_set_arn,
                PrincipalType=entity_type.upper(),
                PrincipalId=entity.entity_id,
            )

            logger.info(f"Created assignment: {entity_ref} -> {permission_set} -> {account_id}")

        except Exception as e:
            logger.error(f"Failed to create assignment via API: {e}")
            raise

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
                        resource_id=account["Id"]
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
            raise RuntimeError(f"Failed to resolve accounts by tags: {e}")

    def _get_entity_details(self, template: Template) -> List[Dict[str, Any]]:
        """Get detailed information about entities in the template."""
        entity_details = []

        for assignment in template.assignments:
            for entity_ref in assignment.entities:
                try:
                    entity_type, entity_name = self._parse_entity_reference(entity_ref)

                    # Convert entity_type string to EntityType enum
                    from ..permission_cloning.models import EntityType

                    if entity_type == "user":
                        entity_type_enum = EntityType.USER
                    elif entity_type == "group":
                        entity_type_enum = EntityType.GROUP
                    else:
                        entity_type_enum = None

                    entity = (
                        self.entity_resolver.resolve_entity_by_name(entity_type_enum, entity_name)
                        if entity_type_enum
                        else None
                    )

                    if entity:
                        entity_details.append(
                            {
                                "reference": entity_ref,
                                "type": entity_type,
                                "name": entity_name,
                                "id": entity.entity_id,
                                "exists": True,
                            }
                        )
                    else:
                        entity_details.append(
                            {
                                "reference": entity_ref,
                                "type": entity_type,
                                "name": entity_name,
                                "id": None,
                                "exists": False,
                            }
                        )

                except Exception as e:
                    entity_details.append(
                        {
                            "reference": entity_ref,
                            "type": "unknown",
                            "name": "unknown",
                            "id": None,
                            "exists": False,
                            "error": str(e),
                        }
                    )

        return entity_details

    def _get_permission_set_details(self, template: Template) -> List[Dict[str, Any]]:
        """Get detailed information about permission sets in the template."""
        permission_set_details = []

        for assignment in template.assignments:
            for permission_set in assignment.permission_sets:
                try:
                    arn = self._get_permission_set_arn(permission_set)

                    if arn:
                        permission_set_details.append(
                            {"name": permission_set, "arn": arn, "exists": True}
                        )
                    else:
                        permission_set_details.append(
                            {"name": permission_set, "arn": None, "exists": False}
                        )

                except Exception as e:
                    permission_set_details.append(
                        {"name": permission_set, "arn": None, "exists": False, "error": str(e)}
                    )

        return permission_set_details

    def _get_account_details(self, account_ids: List[str]) -> List[Dict[str, Any]]:
        """Get detailed information about accounts."""
        account_details = []

        for account_id in account_ids:
            try:
                name = self._get_account_name(account_id)
                account_details.append({"id": account_id, "name": name, "status": "ACTIVE"})
            except Exception as e:
                account_details.append(
                    {"id": account_id, "name": "unknown", "status": "unknown", "error": str(e)}
                )

        return account_details
