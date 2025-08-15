"""Tests for status command helper functions."""

import pytest

from src.awsideman.commands.status.helpers import validate_output_format, validate_status_type
from src.awsideman.utils.status_models import OutputFormat


class TestValidationFunctions:
    """Test validation helper functions."""

    def test_validate_output_format_valid_formats(self):
        """Test validation of valid output formats."""
        assert validate_output_format("json") == OutputFormat.JSON
        assert validate_output_format("JSON") == OutputFormat.JSON
        assert validate_output_format("csv") == OutputFormat.CSV
        assert validate_output_format("CSV") == OutputFormat.CSV
        assert validate_output_format("table") == OutputFormat.TABLE
        assert validate_output_format("TABLE") == OutputFormat.TABLE
        assert validate_output_format(None) == OutputFormat.TABLE

    def test_validate_output_format_invalid_format(self):
        """Test validation of invalid output format."""
        with pytest.raises((SystemExit, Exception)):
            validate_output_format("xml")

    def test_validate_status_type_valid_types(self):
        """Test validation of valid status types."""
        assert validate_status_type("health") == "health"
        assert validate_status_type("provisioning") == "provisioning"
        assert validate_status_type("orphaned") == "orphaned"
        assert validate_status_type("sync") == "sync"
        assert validate_status_type("resource") == "resource"
        assert validate_status_type("summary") == "summary"
        assert validate_status_type(None) is None

    def test_validate_status_type_invalid_type(self):
        """Test validation of invalid status type."""
        with pytest.raises((SystemExit, Exception)):
            validate_status_type("invalid")
