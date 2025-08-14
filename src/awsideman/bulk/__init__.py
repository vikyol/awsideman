"""Bulk operations utilities for awsideman.

This package contains utility classes and functions for bulk operations,
including file processing, resource resolution, validation, and batch processing.

Modules:
    processors: File processing components for CSV and JSON formats
    resolver: Resource name resolution and caching utilities
    batch: Batch processing components with progress tracking and retry logic
"""

from .batch import (
    AssignmentResult,
    BatchProcessor,
    BulkOperationResults,
    ProgressTracker,
    RetryHandler,
)
from .multi_account_batch import MultiAccountBatchProcessor
from .multi_account_progress import MultiAccountProgressTracker
from .preview import PreviewGenerator
from .processors import CSVProcessor, FileFormatDetector, JSONProcessor, ValidationError
from .reporting import ReportGenerator
from .resolver import AssignmentValidator, ResolutionResult, ResourceResolver

__all__ = [
    "CSVProcessor",
    "JSONProcessor",
    "FileFormatDetector",
    "ValidationError",
    "ResourceResolver",
    "AssignmentValidator",
    "ResolutionResult",
    "BatchProcessor",
    "ProgressTracker",
    "MultiAccountProgressTracker",
    "MultiAccountBatchProcessor",
    "RetryHandler",
    "AssignmentResult",
    "BulkOperationResults",
    "PreviewGenerator",
    "ReportGenerator",
]
