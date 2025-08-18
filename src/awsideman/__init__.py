"""AWS Identity Center Manager - A CLI tool for managing AWS Identity Center operations."""

# Import template support modules
from .templates.errors import (
    RetryHandler,
    TemplateError,
    TemplateErrorCollector,
    TemplateErrorHandler,
    TemplateErrorType,
)
from .templates.executor import AssignmentResult, ExecutionResult, PreviewResult, TemplateExecutor
from .templates.models import Template, TemplateAssignment, TemplateMetadata, TemplateTarget
from .templates.parser import TemplateParser
from .templates.progress import (
    OperationType,
    ProgressContext,
    TemplateLiveDisplay,
    TemplateProgressBar,
    TemplateProgressReporter,
    TemplateUserFeedback,
)
from .templates.storage import TemplateInfo, TemplateStorageManager
from .templates.validator import TemplateValidator, ValidationResult

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Template models
    "Template",
    "TemplateMetadata",
    "TemplateTarget",
    "TemplateAssignment",
    # Template functionality
    "TemplateParser",
    "TemplateValidator",
    "ValidationResult",
    "TemplateStorageManager",
    "TemplateInfo",
    "TemplateExecutor",
    "ExecutionResult",
    "AssignmentResult",
    "PreviewResult",
    # Template error handling
    "TemplateError",
    "TemplateErrorType",
    "TemplateErrorHandler",
    "TemplateErrorCollector",
    "RetryHandler",
    # Template progress and UX
    "OperationType",
    "ProgressContext",
    "TemplateProgressReporter",
    "TemplateProgressBar",
    "TemplateUserFeedback",
    "TemplateLiveDisplay",
]
