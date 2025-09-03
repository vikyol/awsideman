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


# Version will be set by build system
def _get_version():
    """Get the version from package metadata or pyproject.toml."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("awsideman")
    except PackageNotFoundError:
        # Fallback for development/editable installs
        import re
        from pathlib import Path

        # Try to read version from pyproject.toml using regex (works with all Python versions)
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if not pyproject_path.exists():
            raise RuntimeError(f"Could not find pyproject.toml at {pyproject_path}")

        with open(pyproject_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Look for version = "..." in the [tool.poetry] section
            version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if not version_match:
                raise RuntimeError("Could not find version in pyproject.toml")
            return version_match.group(1)


__version__ = _get_version()

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
