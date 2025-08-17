"""
Permission Cloning Module

This module provides functionality for copying permission assignments between users and groups,
and cloning permission sets in AWS Identity Center.
"""

from .assignment_copier import AssignmentCopier
from .assignment_retriever import AssignmentRetriever
from .entity_resolver import EntityResolver
from .filter_engine import FilterEngine
from .models import (
    CloneResult,
    CopyFilters,
    CopyResult,
    CustomerManagedPolicy,
    EntityReference,
    EntityType,
    PermissionAssignment,
    PermissionSetConfig,
    ValidationResult,
    ValidationResultType,
)

__all__ = [
    "EntityType",
    "ValidationResultType",
    "EntityReference",
    "PermissionAssignment",
    "PermissionSetConfig",
    "CopyFilters",
    "CopyResult",
    "CloneResult",
    "ValidationResult",
    "CustomerManagedPolicy",
    "EntityResolver",
    "AssignmentRetriever",
    "FilterEngine",
    "AssignmentCopier",
]
