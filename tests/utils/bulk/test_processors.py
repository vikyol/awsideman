"""Tests for bulk processors utilities."""
import csv
import json
import tempfile
from pathlib import Path

from src.awsideman.utils.bulk import CSVProcessor, FileFormatDetector, JSONProcessor


class TestCSVProcessor:
    """Test cases for CSVProcessor class."""

    def test_init(self):
        """Test CSVProcessor initialization."""
        file_path = Path("test.csv")
        processor = CSVProcessor(file_path)

        assert processor.file_path == file_path
        assert processor.required_columns == {
            "principal_name",
            "permission_set_name",
            "account_name",
        }
        assert processor.optional_columns == {
            "principal_type",
            "account_id",
            "permission_set_arn",
            "principal_id",
        }

    def test_validate_format_file_not_found(self):
        """Test validation when file doesn't exist."""
        processor = CSVProcessor(Path("nonexistent.csv"))
        errors = processor.validate_format()

        assert len(errors) == 1
        assert "File not found" in errors[0].message

    def test_validate_format_valid_csv(self):
        """Test validation with valid CSV file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["principal_name", "permission_set_name", "account_name"])
            writer.writerow(["john.doe", "ReadOnlyAccess", "Production"])
            writer.writerow(["jane.smith", "PowerUserAccess", "Development"])
            temp_path = Path(f.name)

        try:
            processor = CSVProcessor(temp_path)
            errors = processor.validate_format()

            assert len(errors) == 0
        finally:
            temp_path.unlink()

    def test_parse_assignments_valid_csv(self):
        """Test parsing valid CSV file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(
                ["principal_name", "permission_set_name", "account_name", "principal_type"]
            )
            writer.writerow(["john.doe", "ReadOnlyAccess", "Production", "USER"])
            writer.writerow(["Developers", "PowerUserAccess", "Development", "GROUP"])
            temp_path = Path(f.name)

        try:
            processor = CSVProcessor(temp_path)
            assignments = processor.parse_assignments()

            assert len(assignments) == 2

            # Check first assignment
            assert assignments[0]["principal_name"] == "john.doe"
            assert assignments[0]["permission_set_name"] == "ReadOnlyAccess"
            assert assignments[0]["account_name"] == "Production"
            assert assignments[0]["principal_type"] == "USER"
            assert assignments[0]["_row_number"] == 2
        finally:
            temp_path.unlink()


class TestJSONProcessor:
    """Test cases for JSONProcessor class."""

    def test_init(self):
        """Test JSONProcessor initialization."""
        file_path = Path("test.json")
        processor = JSONProcessor(file_path)

        assert processor.file_path == file_path
        assert processor.required_fields == {
            "principal_name",
            "permission_set_name",
            "account_name",
        }
        assert processor.optional_fields == {
            "principal_type",
            "account_id",
            "permission_set_arn",
            "principal_id",
        }

    def test_validate_format_valid_json(self):
        """Test validation with valid JSON file."""
        data = {
            "assignments": [
                {
                    "principal_name": "john.doe",
                    "permission_set_name": "ReadOnlyAccess",
                    "account_name": "Production",
                    "principal_type": "USER",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            processor = JSONProcessor(temp_path)
            errors = processor.validate_format()

            assert len(errors) == 0
        finally:
            temp_path.unlink()

    def test_parse_assignments_valid_json(self):
        """Test parsing valid JSON file."""
        data = {
            "assignments": [
                {
                    "principal_name": "john.doe",
                    "permission_set_name": "ReadOnlyAccess",
                    "account_name": "Production",
                    "principal_type": "USER",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            processor = JSONProcessor(temp_path)
            assignments = processor.parse_assignments()

            assert len(assignments) == 1
            assert assignments[0]["principal_name"] == "john.doe"
            assert assignments[0]["permission_set_name"] == "ReadOnlyAccess"
            assert assignments[0]["account_name"] == "Production"
            assert assignments[0]["principal_type"] == "USER"
            assert assignments[0]["_assignment_index"] == 1
        finally:
            temp_path.unlink()


class TestFileFormatDetector:
    """Test cases for FileFormatDetector class."""

    def test_detect_format_csv(self):
        """Test format detection for CSV files."""
        file_path = Path("test.csv")
        format_type = FileFormatDetector.detect_format(file_path)
        assert format_type == "csv"

    def test_detect_format_json(self):
        """Test format detection for JSON files."""
        file_path = Path("test.json")
        format_type = FileFormatDetector.detect_format(file_path)
        assert format_type == "json"

    def test_get_processor_csv(self):
        """Test getting CSV processor."""
        file_path = Path("test.csv")
        processor = FileFormatDetector.get_processor(file_path)

        assert isinstance(processor, CSVProcessor)
        assert processor.file_path == file_path

    def test_get_processor_json(self):
        """Test getting JSON processor."""
        file_path = Path("test.json")
        processor = FileFormatDetector.get_processor(file_path)

        assert isinstance(processor, JSONProcessor)
        assert processor.file_path == file_path


class TestBulkProcessorsIntegration:
    """Integration test cases for bulk processors working together."""

    def test_end_to_end_csv_processing(self):
        """Test complete CSV processing workflow."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(
                ["principal_name", "permission_set_name", "account_name", "principal_type"]
            )
            writer.writerow(["john.doe", "ReadOnlyAccess", "Production", "USER"])
            writer.writerow(["Developers", "PowerUserAccess", "Development", "GROUP"])
            temp_path = Path(f.name)

        try:
            # Test format detection
            assert FileFormatDetector.detect_format(temp_path) == "csv"
            assert FileFormatDetector.is_supported_format(temp_path) is True

            # Get processor and validate
            processor = FileFormatDetector.get_processor(temp_path)
            errors = processor.validate_format()
            assert len(errors) == 0

            # Parse assignments
            assignments = processor.parse_assignments()
            assert len(assignments) == 2

            # Verify first assignment
            assert assignments[0]["principal_name"] == "john.doe"
            assert assignments[0]["permission_set_name"] == "ReadOnlyAccess"
            assert assignments[0]["account_name"] == "Production"
            assert assignments[0]["principal_type"] == "USER"

            # Verify second assignment
            assert assignments[1]["principal_name"] == "Developers"
            assert assignments[1]["permission_set_name"] == "PowerUserAccess"
            assert assignments[1]["account_name"] == "Development"
            assert assignments[1]["principal_type"] == "GROUP"

        finally:
            temp_path.unlink()

    def test_end_to_end_json_processing(self):
        """Test complete JSON processing workflow."""
        data = {
            "assignments": [
                {
                    "principal_name": "john.doe",
                    "permission_set_name": "ReadOnlyAccess",
                    "account_name": "Production",
                    "principal_type": "USER",
                },
                {
                    "principal_name": "Developers",
                    "permission_set_name": "PowerUserAccess",
                    "account_name": "Development",
                    "principal_type": "GROUP",
                },
            ]
        }

        # Create a temporary JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            temp_path = Path(f.name)

        try:
            # Test format detection
            assert FileFormatDetector.detect_format(temp_path) == "json"
            assert FileFormatDetector.is_supported_format(temp_path) is True

            # Get processor and validate
            processor = FileFormatDetector.get_processor(temp_path)
            errors = processor.validate_format()
            assert len(errors) == 0

            # Parse assignments
            assignments = processor.parse_assignments()
            assert len(assignments) == 2

            # Verify first assignment
            assert assignments[0]["principal_name"] == "john.doe"
            assert assignments[0]["permission_set_name"] == "ReadOnlyAccess"
            assert assignments[0]["account_name"] == "Production"
            assert assignments[0]["principal_type"] == "USER"

            # Verify second assignment
            assert assignments[1]["principal_name"] == "Developers"
            assert assignments[1]["permission_set_name"] == "PowerUserAccess"
            assert assignments[1]["account_name"] == "Development"
            assert assignments[1]["principal_type"] == "GROUP"

        finally:
            temp_path.unlink()
