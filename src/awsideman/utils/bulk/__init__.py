"""Bulk operations utilities for awsideman.

This package contains utility classes and functions for bulk operations,
including file processing, resource resolution, validation, and batch processing.

Modules:
    processors: File processing components for CSV and JSON formats
    resolver: Resource name resolution and caching utilities
    batch: Batch processing components with progress tracking and retry logic
"""

from .processors import CSVProcessor, JSONProcessor, FileFormatDetector, ValidationError
from .resolver import ResourceResolver, AssignmentValidator, ResolutionResult
from .batch import BatchProcessor, ProgressTracker, RetryHandler, AssignmentResult, BulkOperationResults
from .multi_account_progress import MultiAccountProgressTracker
from .multi_account_batch import MultiAccountBatchProcessor
from .preview import PreviewGenerator
from .reporting import ReportGenerator

__all__ = [
    'CSVProcessor',
    'JSONProcessor', 
    'FileFormatDetector',
    'ValidationError',
    'ResourceResolver',
    'AssignmentValidator',
    'ResolutionResult',
    'BatchProcessor',
    'ProgressTracker',
    'MultiAccountProgressTracker',
    'MultiAccountBatchProcessor',
    'RetryHandler',
    'AssignmentResult',
    'BulkOperationResults',
    'PreviewGenerator',
    'ReportGenerator'
]