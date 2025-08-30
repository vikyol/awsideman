"""
Backup diff manager for coordinating backup comparison operations.

This module provides the main BackupDiffManager class that orchestrates the entire
diff operation from input parsing to output generation, integrating with existing
storage engines and metadata index.
"""

import logging
from typing import Any, Callable, List, Optional

from botocore.exceptions import NoCredentialsError, TokenRetrievalError

from .backup_resolver import BackupNotFoundError, BackupResolver, InvalidDateSpecError
from .collector import IdentityCenterCollector
from .diff_engine import DiffEngine
from .diff_models import DiffResult
from .interfaces import StorageEngineInterface
from .local_metadata_index import LocalMetadataIndex
from .models import BackupData, BackupOptions
from .output_formatter import OutputFormatter
from .validation import DataValidator, ValidationError

logger = logging.getLogger(__name__)


class BackupDiffError(Exception):
    """Base exception for backup diff operations."""

    pass


class ComparisonError(BackupDiffError):
    """Raised when backup comparison fails."""

    pass


class DataCorruptionError(BackupDiffError):
    """Raised when backup data is corrupted or invalid."""

    pass


class OutputFormatError(BackupDiffError):
    """Raised when output format is invalid or unsupported."""

    pass


class AuthenticationError(Exception):
    """Raised when authentication fails during backup operations."""

    pass


class ProgressTracker:
    """Tracks progress for long-running diff operations."""

    def __init__(self, total_steps: int = 5):
        """Initialize progress tracker with total steps."""
        self.total_steps = total_steps
        self.current_step = 0
        self.step_descriptions = [
            "Validating input parameters",
            "Resolving backup specifications",
            "Loading backup data",
            "Computing differences",
            "Generating output",
        ]
        self.callbacks: List[Callable[[int, int, Optional[str]], None]] = []

    def add_callback(self, callback: Callable[[int, int, Optional[str]], None]) -> None:
        """Add a progress callback function."""
        self.callbacks.append(callback)

    def update(self, step_description: Optional[str] = None) -> None:
        """Update progress to next step."""
        if step_description:
            logger.info(f"Progress: {step_description}")
        else:
            if self.current_step < len(self.step_descriptions):
                logger.info(f"Progress: {self.step_descriptions[self.current_step]}")

        for callback in self.callbacks:
            try:
                callback(self.current_step, self.total_steps, step_description)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

        self.current_step += 1

    def complete(self) -> None:
        """Mark progress as complete."""
        for callback in self.callbacks:
            try:
                callback(self.total_steps, self.total_steps, "Complete")
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")


class InputValidator:
    """Validates input parameters for backup diff operations."""

    VALID_OUTPUT_FORMATS = ["console", "json", "csv", "html"]

    @classmethod
    def validate_output_format(cls, output_format: str) -> str:
        """
        Validate and normalize output format.

        Args:
            output_format: Output format string

        Returns:
            Normalized output format

        Raises:
            OutputFormatError: If format is invalid
        """
        if not output_format or not isinstance(output_format, str):
            raise OutputFormatError("Output format must be a non-empty string")

        normalized_format = output_format.lower().strip()

        if normalized_format not in cls.VALID_OUTPUT_FORMATS:
            raise OutputFormatError(
                f"Invalid output format '{output_format}'. "
                f"Valid formats: {', '.join(cls.VALID_OUTPUT_FORMATS)}"
            )

        return normalized_format

    @classmethod
    def validate_output_file(cls, output_file: Optional[str]) -> Optional[str]:
        """
        Validate output file path.

        Args:
            output_file: Output file path

        Returns:
            Validated output file path

        Raises:
            OutputFormatError: If file path is invalid
        """
        if output_file is None:
            return None

        if not isinstance(output_file, str) or not output_file.strip():
            raise OutputFormatError("Output file path must be a non-empty string")

        # Basic path validation
        import os

        output_file = output_file.strip()

        # Check if directory exists (if path contains directory)
        directory = os.path.dirname(output_file)
        if directory and not os.path.exists(directory):
            raise OutputFormatError(f"Output directory does not exist: {directory}")

        # Check if file is writable (if it exists)
        if os.path.exists(output_file):
            if not os.access(output_file, os.W_OK):
                raise OutputFormatError(f"Output file is not writable: {output_file}")

        return output_file

    @classmethod
    def validate_backup_specs(cls, source_spec: str, target_spec: Optional[str] = None) -> None:
        """
        Validate backup specifications.

        Args:
            source_spec: Source backup specification
            target_spec: Target backup specification

        Raises:
            InvalidDateSpecError: If specifications are invalid
        """
        if not source_spec or not isinstance(source_spec, str) or not source_spec.strip():
            raise InvalidDateSpecError("Source backup specification cannot be empty")

        if target_spec is not None:
            if not isinstance(target_spec, str) or not target_spec.strip():
                raise InvalidDateSpecError("Target backup specification cannot be empty")

        # Additional validation can be added here for specific formats


class BackupDiffManager:
    """
    Main manager class that coordinates the entire diff operation.

    This class provides the primary entry point for backup comparison operations,
    handling date specification parsing, backup loading, diff computation, and
    output generation.
    """

    def __init__(
        self,
        storage_engine: StorageEngineInterface,
        metadata_index: LocalMetadataIndex,
        collector: Optional[IdentityCenterCollector] = None,
        enable_validation: bool = True,
    ):
        """
        Initialize the backup diff manager.

        Args:
            storage_engine: Storage engine for loading backup data
            metadata_index: Local metadata index for backup information
            collector: Optional collector for current state comparison
            enable_validation: Whether to enable backup data validation (default: True)
        """
        self.storage_engine = storage_engine
        self.metadata_index = metadata_index
        self.collector = collector
        self.enable_validation = enable_validation
        self.backup_resolver = BackupResolver(metadata_index)
        self.diff_engine = DiffEngine()
        self.output_formatter = OutputFormatter()

    async def compare_backups(
        self,
        source_spec: str,
        target_spec: Optional[str] = None,
        output_format: str = "console",
        output_file: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
    ) -> DiffResult:
        """
        Main entry point for backup comparison operations.

        Args:
            source_spec: Source backup specification (date or backup ID)
            target_spec: Target backup specification (defaults to current state)
            output_format: Output format ('console', 'json', 'csv', 'html')
            output_file: Optional file path to save output
            progress_callback: Optional callback for progress updates

        Returns:
            DiffResult containing the comparison results

        Raises:
            BackupDiffError: If comparison operation fails
            InvalidDateSpecError: If date specifications are invalid
            BackupNotFoundError: If specified backups cannot be found
            ComparisonError: If backup comparison fails
            OutputFormatError: If output format is invalid
            DataCorruptionError: If backup data is corrupted
        """
        # Initialize progress tracker
        progress = ProgressTracker()
        if progress_callback:
            progress.add_callback(progress_callback)

        try:
            logger.info(f"Starting backup comparison: {source_spec} -> {target_spec or 'current'}")

            # Step 1: Validate input parameters
            progress.update("Validating input parameters")
            InputValidator.validate_backup_specs(source_spec, target_spec)
            normalized_format = InputValidator.validate_output_format(output_format)
            validated_output_file = InputValidator.validate_output_file(output_file)

            # Step 2: Resolve backup specifications to actual backups
            progress.update("Resolving backup specifications")
            source_backup_data = await self._resolve_and_load_backup(source_spec)
            target_backup_data = await self._resolve_and_load_backup(target_spec or "current")

            # Step 3: Validate backup data integrity (if enabled)
            if self.enable_validation:
                progress.update("Validating backup data")
                await self._validate_backup_data(source_backup_data, "source")
                await self._validate_backup_data(target_backup_data, "target")
            else:
                progress.update("Skipping backup data validation")

            # Step 4: Compute differences
            progress.update("Computing differences between backups")
            diff_result = self.diff_engine.compute_diff(source_backup_data, target_backup_data)

            # Step 5: Generate output
            progress.update("Generating output")
            if validated_output_file:
                await self._save_output(diff_result, normalized_format, validated_output_file)
                logger.info(f"Diff results saved to {validated_output_file}")
            else:
                logger.info("Diff computation completed")

            progress.complete()
            return diff_result

        except (
            InvalidDateSpecError,
            BackupNotFoundError,
            OutputFormatError,
            DataCorruptionError,
        ) as e:
            logger.error(f"Backup diff operation failed: {e}")
            raise
        except ValidationError as e:
            logger.error(f"Data validation failed: {e}")
            raise DataCorruptionError(f"Backup data validation failed: {e}") from e
        except (TokenRetrievalError, NoCredentialsError) as e:
            logger.error(f"Authentication error during backup comparison: {e}")
            # Re-raise as a specific authentication error that can be caught by the CLI
            if isinstance(e, TokenRetrievalError):
                raise AuthenticationError(f"AWS SSO authentication failed: {e}") from e
            else:
                raise AuthenticationError(f"No AWS credentials found: {e}") from e
        except AuthenticationError as e:
            logger.error(f"Authentication error during backup comparison: {e}")
            # Re-raise authentication errors so they can be caught by the CLI
            raise
        except Exception as e:
            logger.error(f"Unexpected error during backup comparison: {e}")
            raise ComparisonError(f"Failed to compare backups: {e}") from e

    async def _validate_backup_data(self, backup_data: BackupData, backup_label: str) -> None:
        """
        Validate backup data integrity and structure.

        Args:
            backup_data: Backup data to validate
            backup_label: Label for the backup (for error messages)

        Raises:
            DataCorruptionError: If backup data is invalid or corrupted
        """
        try:
            logger.debug(f"Validating {backup_label} backup data")

            # Skip validation for current state since it's not a stored backup
            if backup_label == "target" and backup_data.metadata.version == "current":
                logger.debug("Skipping validation for current state (not a stored backup)")
                return

            # Use the data validator to check backup integrity
            validator = DataValidator()
            validation_result = validator.validate_backup_data(backup_data)

            if not validation_result.is_valid:
                error_summary = "; ".join(validation_result.errors[:5])  # Show first 5 errors
                if len(validation_result.errors) > 5:
                    error_summary += f" (and {len(validation_result.errors) - 5} more errors)"

                raise DataCorruptionError(
                    f"{backup_label.capitalize()} backup data is invalid: {error_summary}"
                )

            if validation_result.warnings:
                warning_summary = "; ".join(validation_result.warnings[:3])  # Show first 3 warnings
                if len(validation_result.warnings) > 3:
                    warning_summary += f" (and {len(validation_result.warnings) - 3} more warnings)"
                logger.warning(
                    f"{backup_label.capitalize()} backup validation warnings: {warning_summary}"
                )

            logger.debug(
                f"{backup_label.capitalize()} backup data validation completed successfully"
            )

        except DataCorruptionError:
            raise
        except Exception as e:
            logger.error(f"Failed to validate {backup_label} backup data: {e}")
            raise DataCorruptionError(f"Failed to validate {backup_label} backup data: {e}") from e

    async def _resolve_and_load_backup(self, spec: str) -> BackupData:
        """
        Resolve a backup specification and load the backup data.

        Args:
            spec: Backup specification (date, backup ID, or 'current')

        Returns:
            BackupData for the resolved backup

        Raises:
            BackupNotFoundError: If backup cannot be found
            ComparisonError: If backup loading fails
            DataCorruptionError: If backup data is corrupted
        """
        try:
            if spec == "current":
                return await self._collect_current_state()

            # Try to resolve as backup ID first
            backup_metadata = self.metadata_index.get_backup_metadata(spec)
            if backup_metadata:
                logger.debug(f"Resolved {spec} as backup ID: {backup_metadata.backup_id}")
                backup_data = await self._load_backup_with_retry(backup_metadata.backup_id)
                return backup_data

            # Try to resolve as date specification
            backup_metadata = self.backup_resolver.resolve_backup_from_spec(spec)
            if not backup_metadata:
                # Provide helpful suggestions
                available_range = self.backup_resolver.get_available_date_range()
                if available_range:
                    start_date, end_date = available_range
                    raise BackupNotFoundError(
                        f"No backup found for specification: {spec}. "
                        f"Available backups range from {start_date.date()} to {end_date.date()}"
                    )
                else:
                    raise BackupNotFoundError(
                        f"No backup found for specification: {spec}. No backups are available."
                    )

            logger.debug(f"Resolved {spec} to backup: {backup_metadata.backup_id}")

            # Load backup data with retry logic
            backup_data = await self._load_backup_with_retry(backup_metadata.backup_id)
            return backup_data

        except (
            InvalidDateSpecError,
            BackupNotFoundError,
            DataCorruptionError,
            AuthenticationError,
        ):
            raise
        except Exception as e:
            logger.error(f"Failed to resolve and load backup {spec}: {e}")
            raise ComparisonError(f"Failed to resolve backup {spec}: {e}") from e

    async def _load_backup_with_retry(self, backup_id: str, max_retries: int = 3) -> BackupData:
        """
        Load backup data with retry logic for transient failures.

        Args:
            backup_id: Backup ID to load
            max_retries: Maximum number of retry attempts

        Returns:
            BackupData for the backup

        Raises:
            ComparisonError: If backup loading fails after all retries
            DataCorruptionError: If backup data is corrupted
        """
        import asyncio

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = 2 ** (attempt - 1)
                    logger.info(
                        f"Retrying backup load after {delay}s (attempt {attempt + 1}/{max_retries + 1})"
                    )
                    await asyncio.sleep(delay)

                backup_data = await self.storage_engine.retrieve_backup(backup_id)
                if not backup_data:
                    raise ComparisonError(f"Backup data is None for backup ID: {backup_id}")

                logger.debug(f"Successfully loaded backup {backup_id}")
                return backup_data

            except Exception as e:
                last_error = e
                logger.warning(f"Backup load attempt {attempt + 1} failed: {e}")

                # Check if this is an authentication error (don't retry)
                if isinstance(e, (TokenRetrievalError, NoCredentialsError)):
                    logger.error(f"Authentication error during backup load: {e}")
                    raise AuthenticationError(f"AWS authentication failed: {e}") from e

                # Check if this is a corruption error (don't retry)
                if "corrupt" in str(e).lower() or "invalid" in str(e).lower():
                    raise DataCorruptionError(
                        f"Backup {backup_id} appears to be corrupted: {e}"
                    ) from e

                if attempt >= max_retries:
                    break

        # All retries exhausted
        raise ComparisonError(
            f"Failed to load backup {backup_id} after {max_retries + 1} attempts: {last_error}"
        ) from last_error

    async def _collect_current_state(self) -> BackupData:
        """
        Collect current state data from AWS Identity Center.

        Returns:
            BackupData representing the current state

        Raises:
            ComparisonError: If current state collection fails
        """
        if not self.collector:
            raise ComparisonError(
                "Current state comparison requested but no collector provided. "
                "Initialize BackupDiffManager with an IdentityCenterCollector instance."
            )

        try:
            logger.info("Collecting current state from AWS Identity Center")

            # Create backup options for current state collection
            from .models import BackupType, ResourceType

            backup_options = BackupOptions(
                backup_type=BackupType.FULL,
                resource_types=[ResourceType.ALL],
            )

            # Collect current data with error handling for each resource type
            users = []
            groups = []
            permission_sets = []
            assignments = []
            collection_errors = []

            try:
                logger.debug("Collecting users from current state")
                users = await self.collector.collect_users(backup_options)
                logger.debug(f"Collected {len(users)} users")
            except Exception as e:
                error_msg = f"Failed to collect users: {e}"
                logger.error(error_msg)
                collection_errors.append(error_msg)

            try:
                logger.debug("Collecting groups from current state")
                groups = await self.collector.collect_groups(backup_options)
                logger.debug(f"Collected {len(groups)} groups")
            except Exception as e:
                error_msg = f"Failed to collect groups: {e}"
                logger.error(error_msg)
                collection_errors.append(error_msg)

            try:
                logger.debug("Collecting permission sets from current state")
                permission_sets = await self.collector.collect_permission_sets(backup_options)
                logger.debug(f"Collected {len(permission_sets)} permission sets")
            except Exception as e:
                error_msg = f"Failed to collect permission sets: {e}"
                logger.error(error_msg)
                collection_errors.append(error_msg)

            try:
                logger.debug("Collecting assignments from current state")
                assignments = await self.collector.collect_assignments(backup_options)
                logger.debug(f"Collected {len(assignments)} assignments")
            except Exception as e:
                error_msg = f"Failed to collect assignments: {e}"
                logger.error(error_msg)
                collection_errors.append(error_msg)

            # Check if we have any data at all
            total_resources = len(users) + len(groups) + len(permission_sets) + len(assignments)
            if total_resources == 0 and collection_errors:
                error_summary = "; ".join(collection_errors)
                raise ComparisonError(f"Failed to collect any current state data: {error_summary}")

            # Log warnings for partial failures
            if collection_errors:
                logger.warning(f"Partial collection failures: {'; '.join(collection_errors)}")

            # Create backup data structure
            from datetime import datetime

            from .models import BackupMetadata, BackupType, EncryptionMetadata, RetentionPolicy

            # Get actual instance ARN from collector if available
            instance_arn = getattr(self.collector, "instance_arn", "current")

            # Get actual account ID and region from collector if available
            source_account = getattr(self.collector.client_manager, "account_id", "000000000000")
            source_region = getattr(self.collector.client_manager, "region", "us-east-1")

            current_metadata = BackupMetadata(
                backup_id="current",
                timestamp=datetime.now(),
                instance_arn=instance_arn,
                backup_type=BackupType.FULL,
                version="current",
                source_account=source_account,
                source_region=source_region,
                retention_policy=RetentionPolicy(),
                encryption_info=EncryptionMetadata(encrypted=False),
            )

            backup_data = BackupData(
                metadata=current_metadata,
                users=users,
                groups=groups,
                permission_sets=permission_sets,
                assignments=assignments,
            )

            logger.info(
                f"Collected current state: {len(users)} users, {len(groups)} groups, "
                f"{len(permission_sets)} permission sets, {len(assignments)} assignments"
            )

            if collection_errors:
                logger.warning(
                    f"Current state collection completed with {len(collection_errors)} errors"
                )

            return backup_data

        except ComparisonError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error collecting current state: {e}")
            raise ComparisonError(f"Failed to collect current state: {e}") from e

    async def _save_output(
        self, diff_result: DiffResult, output_format: str, output_file: str
    ) -> None:
        """
        Save diff results to a file in the specified format.

        Args:
            diff_result: The diff results to save
            output_format: Output format ('json', 'csv', 'html', 'console')
            output_file: File path to save to

        Raises:
            OutputFormatError: If output formatting or saving fails
        """
        import os
        import tempfile

        try:
            logger.debug(f"Saving output in {output_format} format to {output_file}")

            # Format the output
            try:
                if output_format == "json":
                    formatted_output = self.output_formatter.format_json(diff_result)
                elif output_format == "csv":
                    formatted_output = self.output_formatter.format_csv(diff_result)
                elif output_format == "html":
                    formatted_output = self.output_formatter.format_html(diff_result)
                elif output_format == "console":
                    formatted_output = self.output_formatter.format_console(diff_result)
                else:
                    raise OutputFormatError(f"Unsupported output format: {output_format}")
            except Exception as e:
                raise OutputFormatError(f"Failed to format output as {output_format}: {e}") from e

            # Write to temporary file first, then move to final location (atomic write)
            temp_file = None
            try:
                # Create temporary file in the same directory as the target file
                output_dir = os.path.dirname(os.path.abspath(output_file))
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=output_dir, delete=False, suffix=".tmp"
                ) as f:
                    temp_file = f.name
                    f.write(formatted_output)

                # Atomic move to final location
                if os.name == "nt":  # Windows
                    # On Windows, we need to remove the target file first
                    if os.path.exists(output_file):
                        os.remove(output_file)
                    os.rename(temp_file, output_file)
                else:  # Unix-like systems
                    os.rename(temp_file, output_file)

                temp_file = None  # Successfully moved, don't clean up
                logger.debug(f"Output saved successfully to {output_file}")

            except PermissionError as e:
                raise OutputFormatError(f"Permission denied writing to {output_file}: {e}") from e
            except OSError as e:
                raise OutputFormatError(f"Failed to write to {output_file}: {e}") from e
            finally:
                # Clean up temporary file if it still exists
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to clean up temporary file {temp_file}: {cleanup_error}"
                        )

        except OutputFormatError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving output to {output_file}: {e}")
            raise ComparisonError(f"Failed to save output: {e}") from e

    def get_available_backups(self) -> List[Any]:
        """
        Get a list of available backups for comparison.

        Returns:
            List of backup metadata objects
        """
        try:
            return self.metadata_index.list_backups()
        except Exception as e:
            logger.error(f"Failed to list available backups: {e}")
            return []

    async def validate_backup_compatibility(self, backup_id1: str, backup_id2: str) -> bool:
        """
        Validate that two backups are compatible for comparison.

        Args:
            backup_id1: First backup ID
            backup_id2: Second backup ID

        Returns:
            True if backups are compatible, False otherwise
        """
        try:
            metadata1 = self.metadata_index.get_backup_metadata(backup_id1)
            metadata2 = self.metadata_index.get_backup_metadata(backup_id2)

            if not metadata1 or not metadata2:
                logger.warning(
                    f"Missing metadata for backup comparison: {backup_id1}, {backup_id2}"
                )
                return False

            # Check if backups are from the same instance
            if metadata1.instance_arn != metadata2.instance_arn:
                logger.warning(
                    f"Backups from different instances: {metadata1.instance_arn} vs {metadata2.instance_arn}"
                )
                return False

            # Additional compatibility checks could be added here
            return True

        except Exception as e:
            logger.error(f"Failed to validate backup compatibility: {e}")
            return False
