"""Template support for AWS Identity Center permission assignments.

This module provides a comprehensive template system for managing AWS IAM Identity Center
permission assignments through declarative templates. It includes data models, parsing,
validation, storage, execution, error handling, and progress reporting capabilities.
"""

# Error handling and user experience
from .errors import (
    RetryHandler,
    TemplateError,
    TemplateErrorCollector,
    TemplateErrorHandler,
    TemplateErrorType,
)
from .executor import AssignmentResult, ExecutionResult, PreviewResult, TemplateExecutor

# Core template components
from .models import Template, TemplateAssignment, TemplateMetadata, TemplateTarget
from .parser import TemplateParser
from .progress import (
    OperationType,
    ProgressContext,
    TemplateLiveDisplay,
    TemplateProgressBar,
    TemplateProgressReporter,
    TemplateUserFeedback,
)
from .storage import TemplateInfo, TemplateStorageManager
from .validator import TemplateValidator, ValidationResult

# Export all public classes and functions
__all__ = [
    # Core models
    "Template",
    "TemplateMetadata",
    "TemplateTarget",
    "TemplateAssignment",
    # Core functionality
    "TemplateParser",
    "TemplateValidator",
    "ValidationResult",
    "TemplateStorageManager",
    "TemplateInfo",
    "TemplateExecutor",
    "ExecutionResult",
    "AssignmentResult",
    "PreviewResult",
    # Error handling
    "TemplateError",
    "TemplateErrorType",
    "TemplateErrorHandler",
    "TemplateErrorCollector",
    "RetryHandler",
    # Progress and user experience
    "OperationType",
    "ProgressContext",
    "TemplateProgressReporter",
    "TemplateProgressBar",
    "TemplateUserFeedback",
    "TemplateLiveDisplay",
]
