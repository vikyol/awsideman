"""File processing components for bulk operations.

This module provides classes for processing CSV and JSON input files for bulk operations.
Includes validation, parsing, and error handling for different file formats.

Classes:
    CSVProcessor: Handles CSV file parsing and validation
    JSONProcessor: Handles JSON file parsing and validation
    FileFormatDetector: Detects file format based on extension
"""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ValidationError:
    """Represents a validation error with details."""

    message: str
    line_number: Optional[int] = None
    field: Optional[str] = None


class CSVProcessor:
    """Handles CSV file parsing and validation for bulk operations."""

    def __init__(self, file_path: Path):
        """Initialize CSV processor with file path.

        Args:
            file_path: Path to the CSV file to process
        """
        self.file_path = file_path
        self.required_columns = {"principal_name", "permission_set_name", "account_name"}
        self.optional_columns = {
            "principal_type",
            "account_id",
            "permission_set_arn",
            "principal_id",
        }
        self.all_columns = self.required_columns | self.optional_columns

    def validate_format(self) -> List[ValidationError]:
        """Validate CSV format and return list of validation errors.

        Returns:
            List of ValidationError objects describing any validation issues
        """
        errors = []

        # Check if file exists
        if not self.file_path.exists():
            errors.append(ValidationError(f"File not found: {self.file_path}"))
            return errors

        # Check if file is readable
        if not self.file_path.is_file():
            errors.append(ValidationError(f"Path is not a file: {self.file_path}"))
            return errors

        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                # Try to read the CSV and check basic structure
                reader = csv.DictReader(file)

                # Check if file has headers
                if reader.fieldnames is None:
                    errors.append(ValidationError("CSV file appears to be empty or has no headers"))
                    return errors

                # Normalize column names (handle both snake_case and kebab-case)
                normalized_columns = set()
                for col in reader.fieldnames:
                    normalized_col = col.lower().replace("-", "_").strip()
                    normalized_columns.add(normalized_col)

                # Check for required columns
                missing_required = self.required_columns - normalized_columns
                if missing_required:
                    errors.append(
                        ValidationError(
                            f"Missing required columns: {', '.join(sorted(missing_required))}"
                        )
                    )

                # Check for unknown columns
                unknown_columns = normalized_columns - self.all_columns
                if unknown_columns:
                    errors.append(
                        ValidationError(
                            f"Unknown columns found: {', '.join(sorted(unknown_columns))}. "
                            f"Valid columns are: {', '.join(sorted(self.all_columns))}"
                        )
                    )

                # Validate data rows
                row_count = 0
                for row_num, row in enumerate(reader, start=2):  # Start at 2 since row 1 is headers
                    row_count += 1

                    # Check for empty required fields
                    for col_name, value in row.items():
                        normalized_col = col_name.lower().replace("-", "_").strip()
                        if normalized_col in self.required_columns and not value.strip():
                            errors.append(
                                ValidationError(
                                    f"Empty value in required column '{col_name}'",
                                    line_number=row_num,
                                    field=col_name,
                                )
                            )

                    # Validate principal_type if provided
                    principal_type_col = None
                    for col_name, value in row.items():
                        if col_name.lower().replace("-", "_").strip() == "principal_type":
                            principal_type_col = col_name
                            break

                    if principal_type_col and row[principal_type_col].strip():
                        principal_type = row[principal_type_col].strip().upper()
                        if principal_type not in ["USER", "GROUP"]:
                            errors.append(
                                ValidationError(
                                    f"Invalid principal_type '{row[principal_type_col]}'. Must be 'USER' or 'GROUP'",
                                    line_number=row_num,
                                    field=principal_type_col,
                                )
                            )

                # Check if file has any data rows
                if row_count == 0:
                    errors.append(ValidationError("CSV file contains no data rows"))

        except csv.Error as e:
            errors.append(ValidationError(f"CSV parsing error: {str(e)}"))
        except UnicodeDecodeError as e:
            errors.append(
                ValidationError(
                    f"File encoding error: {str(e)}. Please ensure file is UTF-8 encoded"
                )
            )
        except Exception as e:
            errors.append(ValidationError(f"Unexpected error reading file: {str(e)}"))

        return errors

    def parse_assignments(self) -> List[Dict[str, Any]]:
        """Parse CSV file and return list of assignment dictionaries.

        Returns:
            List of dictionaries containing assignment data

        Raises:
            ValueError: If file validation fails
            FileNotFoundError: If file doesn't exist
        """
        # Validate format first
        validation_errors = self.validate_format()
        if validation_errors:
            error_messages = [error.message for error in validation_errors]
            raise ValueError(f"CSV validation failed: {'; '.join(error_messages)}")

        assignments = []

        with open(self.file_path, "r", encoding="utf-8") as file:
            reader = csv.DictReader(file)

            for row_num, row in enumerate(reader, start=2):
                # Normalize and clean the row data
                assignment = {}

                for col_name, value in row.items():
                    normalized_col = col_name.lower().replace("-", "_").strip()
                    cleaned_value = value.strip() if value else ""

                    # Map normalized column names to assignment fields
                    if normalized_col in self.all_columns:
                        assignment[normalized_col] = cleaned_value

                # Set default values for optional fields
                if "principal_type" not in assignment or not assignment["principal_type"]:
                    assignment["principal_type"] = "USER"
                else:
                    assignment["principal_type"] = assignment["principal_type"].upper()

                # Add row number for error tracking
                assignment["_row_number"] = row_num

                assignments.append(assignment)

        return assignments


class JSONProcessor:
    """Handles JSON file parsing and validation for bulk operations."""

    def __init__(self, file_path: Path):
        """Initialize JSON processor with file path.

        Args:
            file_path: Path to the JSON file to process
        """
        self.file_path = file_path
        self.required_fields = {"principal_name", "permission_set_name", "account_name"}
        self.optional_fields = {
            "principal_type",
            "account_id",
            "permission_set_arn",
            "principal_id",
        }
        self.all_fields = self.required_fields | self.optional_fields

        # JSON schema definition for assignment structure
        self.schema = {
            "type": "object",
            "properties": {
                "assignments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["principal_name", "permission_set_name", "account_name"],
                        "properties": {
                            "principal_name": {"type": "string", "minLength": 1},
                            "permission_set_name": {"type": "string", "minLength": 1},
                            "account_name": {"type": "string", "minLength": 1},
                            "principal_type": {"type": "string", "enum": ["USER", "GROUP"]},
                            "account_id": {"type": "string"},
                            "permission_set_arn": {"type": "string"},
                            "principal_id": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                }
            },
            "required": ["assignments"],
            "additionalProperties": False,
        }

    def validate_format(self) -> List[ValidationError]:
        """Validate JSON format and schema, return list of validation errors.

        Returns:
            List of ValidationError objects describing any validation issues
        """
        errors = []

        # Check if file exists
        if not self.file_path.exists():
            errors.append(ValidationError(f"File not found: {self.file_path}"))
            return errors

        # Check if file is readable
        if not self.file_path.is_file():
            errors.append(ValidationError(f"Path is not a file: {self.file_path}"))
            return errors

        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            # Validate basic structure
            if not isinstance(data, dict):
                errors.append(ValidationError("JSON root must be an object"))
                return errors

            # Check for required top-level key
            if "assignments" not in data:
                errors.append(ValidationError("JSON must contain 'assignments' key"))
                return errors

            # Check assignments is an array
            if not isinstance(data["assignments"], list):
                errors.append(ValidationError("'assignments' must be an array"))
                return errors

            # Check if assignments array is empty
            if len(data["assignments"]) == 0:
                errors.append(ValidationError("'assignments' array cannot be empty"))
                return errors

            # Validate each assignment
            for idx, assignment in enumerate(data["assignments"]):
                assignment_errors = self._validate_assignment(assignment, idx)
                errors.extend(assignment_errors)

            # Check for unknown top-level keys
            unknown_keys = set(data.keys()) - {"assignments"}
            if unknown_keys:
                errors.append(
                    ValidationError(
                        f"Unknown top-level keys: {', '.join(sorted(unknown_keys))}. "
                        f"Only 'assignments' is allowed"
                    )
                )

        except json.JSONDecodeError as e:
            errors.append(ValidationError(f"Invalid JSON format: {str(e)}"))
        except UnicodeDecodeError as e:
            errors.append(
                ValidationError(
                    f"File encoding error: {str(e)}. Please ensure file is UTF-8 encoded"
                )
            )
        except Exception as e:
            errors.append(ValidationError(f"Unexpected error reading file: {str(e)}"))

        return errors

    def _validate_assignment(self, assignment: Any, index: int) -> List[ValidationError]:
        """Validate a single assignment object.

        Args:
            assignment: Assignment object to validate
            index: Index of assignment in array for error reporting

        Returns:
            List of ValidationError objects for this assignment
        """
        errors = []
        assignment_prefix = f"Assignment {index + 1}"

        # Check if assignment is an object
        if not isinstance(assignment, dict):
            errors.append(ValidationError(f"{assignment_prefix}: must be an object"))
            return errors

        # Check for required fields
        missing_required = self.required_fields - set(assignment.keys())
        if missing_required:
            errors.append(
                ValidationError(
                    f"{assignment_prefix}: missing required fields: {', '.join(sorted(missing_required))}"
                )
            )

        # Check for unknown fields
        unknown_fields = set(assignment.keys()) - self.all_fields
        if unknown_fields:
            errors.append(
                ValidationError(
                    f"{assignment_prefix}: unknown fields: {', '.join(sorted(unknown_fields))}. "
                    f"Valid fields are: {', '.join(sorted(self.all_fields))}"
                )
            )

        # Validate field values
        for field, value in assignment.items():
            if field in self.all_fields:
                field_errors = self._validate_field_value(field, value, assignment_prefix)
                errors.extend(field_errors)

        return errors

    def _validate_field_value(
        self, field: str, value: Any, assignment_prefix: str
    ) -> List[ValidationError]:
        """Validate a single field value.

        Args:
            field: Field name
            value: Field value
            assignment_prefix: Prefix for error messages

        Returns:
            List of ValidationError objects for this field
        """
        errors = []

        # All fields should be strings
        if not isinstance(value, str):
            errors.append(ValidationError(f"{assignment_prefix}: '{field}' must be a string"))
            return errors

        # Required fields cannot be empty
        if field in self.required_fields and not value.strip():
            errors.append(ValidationError(f"{assignment_prefix}: '{field}' cannot be empty"))

        # Validate principal_type enum
        if field == "principal_type" and value.strip():
            if value.upper() not in ["USER", "GROUP"]:
                errors.append(
                    ValidationError(
                        f"{assignment_prefix}: 'principal_type' must be 'USER' or 'GROUP', got '{value}'"
                    )
                )

        return errors

    def parse_assignments(self) -> List[Dict[str, Any]]:
        """Parse JSON file and return list of assignment dictionaries.

        Returns:
            List of dictionaries containing assignment data

        Raises:
            ValueError: If file validation fails
            FileNotFoundError: If file doesn't exist
        """
        # Validate format first
        validation_errors = self.validate_format()
        if validation_errors:
            error_messages = [error.message for error in validation_errors]
            raise ValueError(f"JSON validation failed: {'; '.join(error_messages)}")

        with open(self.file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        assignments = []

        for idx, assignment in enumerate(data["assignments"]):
            # Clean and normalize the assignment data
            cleaned_assignment = {}

            for field, value in assignment.items():
                if field in self.all_fields:
                    cleaned_value = value.strip() if isinstance(value, str) else value
                    cleaned_assignment[field] = cleaned_value

            # Set default values for optional fields
            if (
                "principal_type" not in cleaned_assignment
                or not cleaned_assignment["principal_type"]
            ):
                cleaned_assignment["principal_type"] = "USER"
            else:
                cleaned_assignment["principal_type"] = cleaned_assignment["principal_type"].upper()

            # Add assignment index for error tracking
            cleaned_assignment["_assignment_index"] = idx + 1

            assignments.append(cleaned_assignment)

        return assignments


class FileFormatDetector:
    """Detects file format based on extension and provides appropriate processor."""

    SUPPORTED_EXTENSIONS = {".csv", ".json"}

    @classmethod
    def detect_format(cls, file_path: Path) -> str:
        """Detect file format based on extension.

        Args:
            file_path: Path to the file

        Returns:
            File format ('csv' or 'json')

        Raises:
            ValueError: If file format is not supported
        """
        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        # Get file extension in lowercase
        extension = file_path.suffix.lower()

        if extension == ".csv":
            return "csv"
        elif extension == ".json":
            return "json"
        else:
            supported_formats = ", ".join(sorted(cls.SUPPORTED_EXTENSIONS))
            raise ValueError(
                f"Unsupported file format '{extension}'. "
                f"Supported formats are: {supported_formats}"
            )

    @classmethod
    def get_processor(cls, file_path: Path):
        """Get appropriate processor for the file format.

        Args:
            file_path: Path to the file

        Returns:
            CSVProcessor or JSONProcessor instance

        Raises:
            ValueError: If file format is not supported
        """
        format_type = cls.detect_format(file_path)

        if format_type == "csv":
            return CSVProcessor(file_path)
        elif format_type == "json":
            return JSONProcessor(file_path)
        else:
            # This should not happen if detect_format works correctly
            raise ValueError(f"No processor available for format: {format_type}")

    @classmethod
    def is_supported_format(cls, file_path: Path) -> bool:
        """Check if file format is supported.

        Args:
            file_path: Path to the file

        Returns:
            True if format is supported, False otherwise
        """
        try:
            cls.detect_format(file_path)
            return True
        except ValueError:
            return False

    @classmethod
    def get_supported_formats(cls) -> List[str]:
        """Get list of supported file formats.

        Returns:
            List of supported file extensions
        """
        return sorted(list(cls.SUPPORTED_EXTENSIONS))
