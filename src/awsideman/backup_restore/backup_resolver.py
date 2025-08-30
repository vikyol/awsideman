"""
Backup resolver for parsing date specifications and finding matching backups.

This module provides functionality to resolve date specifications (relative or absolute)
to actual backup identifiers, enabling flexible backup comparison operations.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional

from .local_metadata_index import LocalMetadataIndex
from .models import BackupMetadata

logger = logging.getLogger(__name__)


class BackupResolverError(Exception):
    """Base exception for backup resolver operations."""

    pass


class InvalidDateSpecError(BackupResolverError):
    """Raised when date specification is invalid."""

    def __init__(self, message: str, suggestions: Optional[List[str]] = None):
        """Initialize with error message and optional suggestions."""
        super().__init__(message)
        self.suggestions = suggestions or []


class BackupNotFoundError(BackupResolverError):
    """Raised when a specified backup cannot be found."""

    def __init__(self, message: str, available_backups: Optional[List[BackupMetadata]] = None):
        """Initialize with error message and optional available backups."""
        super().__init__(message)
        self.available_backups = available_backups or []


class BackupResolver:
    """
    Resolves date specifications to backup identifiers.

    Supports:
    - Relative dates: "2d", "7d", "30d" (days ago)
    - Absolute dates: "2025-01-15", "20250115", "2025-01-15T10:30:00"
    - Special values: "current" (current state)
    """

    def __init__(self, metadata_index: LocalMetadataIndex):
        """
        Initialize the backup resolver.

        Args:
            metadata_index: Local metadata index for backup information
        """
        self.metadata_index = metadata_index

        # Regex patterns for date parsing
        self.relative_date_pattern = re.compile(r"^(\d+)d$")  # e.g., "7d", "30d"
        self.absolute_date_patterns = [
            re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # YYYY-MM-DD
            re.compile(r"^\d{8}$"),  # YYYYMMDD
            re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"),  # YYYY-MM-DDTHH:MM:SS
            re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+$"),  # With microseconds
            re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"),  # With timezone
            re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),  # With Z timezone
        ]

    def resolve_backup_from_spec(self, spec: str) -> Optional[BackupMetadata]:
        """
        Resolve a date specification to a backup.

        Args:
            spec: Date specification string

        Returns:
            BackupMetadata if found, None otherwise

        Raises:
            InvalidDateSpecError: If the date specification is invalid
            BackupNotFoundError: If no backup matches the specification
        """
        if not spec or not isinstance(spec, str) or not spec.strip():
            raise InvalidDateSpecError(
                "Date specification cannot be empty",
                suggestions=["Use formats like: '7d', '2025-01-15', or 'current'"],
            )

        original_spec = spec.strip()
        spec_lower = original_spec.lower()

        # Handle special case: "current"
        if spec_lower == "current":
            # Return None to indicate current state should be collected
            return None

        try:
            # Try parsing as relative date (e.g., "7d")
            if self._is_relative_date(spec_lower):
                target_date = self._parse_relative_date(spec_lower)
                backup = self.find_closest_backup(target_date)
                if not backup:
                    available_range = self.get_available_date_range()
                    if available_range:
                        start_date, end_date = available_range
                        raise BackupNotFoundError(
                            f"No backup found for date specification '{original_spec}' (target date: {target_date.date()}). "
                            f"Available backups range from {start_date.date()} to {end_date.date()}"
                        )
                    else:
                        raise BackupNotFoundError(
                            f"No backups are available for specification '{original_spec}'"
                        )
                return backup

            # Try parsing as absolute date (use original case for proper parsing)
            if self._is_absolute_date(original_spec):
                target_date = self._parse_absolute_date(original_spec)
                backup = self.find_closest_backup(target_date)
                if not backup:
                    # Provide suggestions for closest available dates
                    closest_backups = self.suggest_closest_dates(target_date, count=3)
                    suggestion_dates = [b.timestamp.date() for b in closest_backups]
                    raise BackupNotFoundError(
                        f"No backup found for date specification '{original_spec}' (target date: {target_date.date()}). "
                        f"Closest available dates: {suggestion_dates}",
                        available_backups=closest_backups,
                    )
                return backup

            # If we get here, the spec format is not recognized
            available_range = self.get_available_date_range()
            suggestions = [
                "Use relative dates like '7d', '30d'",
                "Use absolute dates like '2025-01-15', '2025-01-15T10:30:00'",
                "Use 'current' for current state",
            ]

            if available_range:
                start_date, end_date = available_range
                suggestions.append(
                    f"Available backup dates range from {start_date.date()} to {end_date.date()}"
                )

            raise InvalidDateSpecError(
                f"Invalid date specification format: '{original_spec}'. Supported formats: relative dates (e.g., '7d'), absolute dates (e.g., '2025-01-15'), or 'current' for current state.",
                suggestions=suggestions,
            )

        except (InvalidDateSpecError, BackupNotFoundError):
            raise
        except ValueError as e:
            suggestions = [
                "Check date format (YYYY-MM-DD for absolute dates)",
                "Use positive numbers for relative dates (e.g., '7d', not '-7d')",
                "Ensure date is valid (e.g., not February 30th)",
            ]
            raise InvalidDateSpecError(
                f"Failed to parse date specification '{original_spec}': {e}",
                suggestions=suggestions,
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error resolving backup specification '{original_spec}': {e}")
            raise InvalidDateSpecError(
                f"Unexpected error parsing date specification '{original_spec}': {e}"
            ) from e

    def find_closest_backup(self, target_date: datetime) -> Optional[BackupMetadata]:
        """
        Find the backup closest to the target date.

        Args:
            target_date: Target date to find backup for

        Returns:
            BackupMetadata of the closest backup, None if no backups exist
        """
        try:
            # Get all available backups
            all_backups = self.metadata_index.list_backups()

            if not all_backups:
                logger.warning("No backups found in metadata index")
                return None

            # Find the backup with the smallest time difference
            closest_backup = None
            smallest_diff = None

            for backup in all_backups:
                time_diff = abs((backup.timestamp - target_date).total_seconds())

                if smallest_diff is None or time_diff < smallest_diff:
                    smallest_diff = time_diff
                    closest_backup = backup

            if closest_backup:
                logger.debug(
                    f"Found closest backup {closest_backup.backup_id} "
                    f"from {closest_backup.timestamp} for target date {target_date}"
                )

            return closest_backup

        except Exception as e:
            logger.error(f"Failed to find closest backup for {target_date}: {e}")
            return None

    def find_backup_by_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> List[BackupMetadata]:
        """
        Find all backups within a date range.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of BackupMetadata objects within the date range
        """
        try:
            all_backups = self.metadata_index.list_backups()

            matching_backups = [
                backup for backup in all_backups if start_date <= backup.timestamp <= end_date
            ]

            # Sort by timestamp (newest first)
            matching_backups.sort(key=lambda x: x.timestamp, reverse=True)

            logger.debug(
                f"Found {len(matching_backups)} backups between " f"{start_date} and {end_date}"
            )

            return matching_backups

        except Exception as e:
            logger.error(f"Failed to find backups in date range: {e}")
            return []

    def get_backup_by_id(self, backup_id: str) -> Optional[BackupMetadata]:
        """
        Get backup metadata by backup ID.

        Args:
            backup_id: Unique backup identifier

        Returns:
            BackupMetadata if found, None otherwise
        """
        try:
            return self.metadata_index.get_backup_metadata(backup_id)
        except Exception as e:
            logger.error(f"Failed to get backup {backup_id}: {e}")
            return None

    def _is_relative_date(self, spec: str) -> bool:
        """Check if the specification is a relative date format."""
        return bool(self.relative_date_pattern.match(spec))

    def _is_absolute_date(self, spec: str) -> bool:
        """Check if the specification is an absolute date format."""
        # First check regex patterns
        if any(pattern.match(spec) for pattern in self.absolute_date_patterns):
            return True

        # Also try to parse with fromisoformat as a fallback
        try:
            datetime.fromisoformat(spec.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    def _parse_relative_date(self, spec: str) -> datetime:
        """
        Parse a relative date specification.

        Args:
            spec: Relative date specification (e.g., "7d")

        Returns:
            datetime object representing the target date

        Raises:
            ValueError: If the specification is invalid
        """
        match = self.relative_date_pattern.match(spec)
        if not match:
            raise ValueError(f"Invalid relative date format: {spec}")

        days_ago = int(match.group(1))
        if days_ago < 0:
            raise ValueError("Number of days cannot be negative")

        target_date = datetime.now() - timedelta(days=days_ago)
        logger.debug(f"Parsed relative date '{spec}' to {target_date}")

        return target_date

    def _parse_absolute_date(self, spec: str) -> datetime:
        """
        Parse an absolute date specification.

        Args:
            spec: Absolute date specification

        Returns:
            datetime object representing the target date

        Raises:
            ValueError: If the specification is invalid
        """
        # Try different date formats
        date_formats = [
            "%Y-%m-%d",  # YYYY-MM-DD
            "%Y%m%d",  # YYYYMMDD
            "%Y-%m-%dT%H:%M:%S",  # YYYY-MM-DDTHH:MM:SS
            "%Y-%m-%dT%H:%M:%S.%f",  # With microseconds
        ]

        # Handle timezone-aware formats separately
        if "+" in spec or spec.endswith("Z"):
            try:
                # Try parsing with timezone info
                return datetime.fromisoformat(spec.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Try each format
        for date_format in date_formats:
            try:
                target_date = datetime.strptime(spec, date_format)
                logger.debug(f"Parsed absolute date '{spec}' to {target_date}")
                return target_date
            except ValueError:
                continue

        # If none of the formats worked, try fromisoformat as a last resort
        try:
            target_date = datetime.fromisoformat(spec)
            logger.debug(f"Parsed absolute date '{spec}' to {target_date} using fromisoformat")
            return target_date
        except ValueError:
            pass

        raise ValueError(f"Unable to parse absolute date: {spec}")

    def validate_date_spec(self, spec: str) -> bool:
        """
        Validate a date specification without resolving it.

        Args:
            spec: Date specification to validate

        Returns:
            True if the specification is valid, False otherwise
        """
        try:
            if not spec or not spec.strip():
                return False

            original_spec = spec.strip()
            spec_lower = original_spec.lower()

            # Check special cases (case insensitive)
            if spec_lower == "current":
                return True

            # Check relative date format (case insensitive)
            if self._is_relative_date(spec_lower):
                self._parse_relative_date(spec_lower)
                return True

            # Check absolute date format (case sensitive for proper parsing)
            if self._is_absolute_date(original_spec):
                self._parse_absolute_date(original_spec)
                return True

            return False

        except Exception:
            return False

    def get_available_date_range(self) -> Optional[tuple[datetime, datetime]]:
        """
        Get the date range of available backups.

        Returns:
            Tuple of (earliest_date, latest_date) or None if no backups exist
        """
        try:
            all_backups = self.metadata_index.list_backups()

            if not all_backups:
                return None

            timestamps = [backup.timestamp for backup in all_backups]
            return min(timestamps), max(timestamps)

        except Exception as e:
            logger.error(f"Failed to get available date range: {e}")
            return None

    def suggest_closest_dates(self, target_date: datetime, count: int = 3) -> List[BackupMetadata]:
        """
        Suggest the closest backup dates to a target date.

        Args:
            target_date: Target date to find suggestions for
            count: Number of suggestions to return

        Returns:
            List of BackupMetadata objects sorted by proximity to target date
        """
        try:
            all_backups = self.metadata_index.list_backups()

            if not all_backups:
                return []

            # Calculate time differences and sort
            backup_distances = [
                (backup, abs((backup.timestamp - target_date).total_seconds()))
                for backup in all_backups
            ]

            backup_distances.sort(key=lambda x: x[1])

            # Return the closest backups
            suggestions = [backup for backup, _ in backup_distances[:count]]

            logger.debug(f"Generated {len(suggestions)} suggestions for target date {target_date}")

            return suggestions

        except Exception as e:
            logger.error(f"Failed to generate date suggestions: {e}")
            return []
