"""Tests for orphaned assignment cleanup caching functionality."""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent / "src"))

from awsideman.commands.status.cleanup import (  # noqa: E402
    _clear_cache,
    _get_cache_file_path,
    _load_detection_results,
    _save_detection_results,
)


class TestCleanupCaching:
    """Test cases for cleanup caching functionality."""

    def test_get_cache_file_path(self):
        """Test cache file path generation."""
        profile_name = "test-profile"
        cache_path = _get_cache_file_path(profile_name)

        # Should be in temp directory
        assert tempfile.gettempdir() in cache_path
        assert "awsideman" in cache_path
        assert "orphaned_cleanup" in cache_path
        assert "test-profile_orphaned_assignments.json" in cache_path

    def test_save_and_load_detection_results(self):
        """Test saving and loading detection results."""
        profile_name = "test-profile"

        # Create a mock result object
        from awsideman.utils.status_models import (
            OrphanedAssignment,
            OrphanedAssignmentStatus,
            PrincipalType,
            StatusLevel,
        )

        mock_assignment = OrphanedAssignment(
            assignment_id="assignment-123",
            permission_set_arn="arn:aws:sso:::permissionSet/test",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
            account_name="Test Account",
            principal_id="user-123",
            principal_name="test.user",
            principal_type=PrincipalType.USER,
            error_message="Principal not found",
            created_date=datetime.now(timezone.utc),
        )

        mock_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Test message",
            orphaned_assignments=[mock_assignment],
            cleanup_available=True,
        )

        # Save results
        cache_file = _save_detection_results(profile_name, mock_result)
        assert os.path.exists(cache_file)

        # Load results
        loaded_result = _load_detection_results(profile_name)
        assert loaded_result is not None
        assert len(loaded_result.orphaned_assignments) == 1

        loaded_assignment = loaded_result.orphaned_assignments[0]
        assert loaded_assignment.permission_set_arn == mock_assignment.permission_set_arn
        assert loaded_assignment.permission_set_name == mock_assignment.permission_set_name
        assert loaded_assignment.account_id == mock_assignment.account_id
        assert loaded_assignment.principal_id == mock_assignment.principal_id
        assert loaded_assignment.principal_type == mock_assignment.principal_type

    def test_load_nonexistent_cache(self):
        """Test loading from non-existent cache file."""
        profile_name = "nonexistent-profile"
        result = _load_detection_results(profile_name)
        assert result is None

    def test_load_expired_cache(self):
        """Test loading expired cache (older than 1 hour)."""
        profile_name = "expired-profile"

        # Create expired cache data
        expired_time = datetime.now(timezone.utc).replace(hour=datetime.now(timezone.utc).hour - 2)
        cache_data = {
            "timestamp": expired_time.isoformat(),  # 2 hours ago
            "profile": profile_name,
            "orphaned_assignments": [],
        }

        cache_file = _get_cache_file_path(profile_name)
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)

        with open(cache_file, "w") as f:
            json.dump(cache_data, f)

        # Should return None for expired cache
        result = _load_detection_results(profile_name)
        assert result is None

    def test_clear_cache(self):
        """Test clearing cache file."""
        profile_name = "test-clear-profile"

        # Create a cache file first
        cache_file = _get_cache_file_path(profile_name)
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)

        with open(cache_file, "w") as f:
            json.dump({"test": "data"}, f)

        assert os.path.exists(cache_file)

        # Clear cache
        _clear_cache(profile_name)

        # File should be deleted
        assert not os.path.exists(cache_file)

    def test_clear_nonexistent_cache(self):
        """Test clearing non-existent cache file."""
        profile_name = "nonexistent-clear-profile"

        # Should not raise an error
        _clear_cache(profile_name)

    def test_cache_file_structure(self):
        """Test that saved cache file has correct structure."""
        profile_name = "structure-test-profile"

        # Create mock result
        from awsideman.utils.status_models import (
            OrphanedAssignment,
            OrphanedAssignmentStatus,
            PrincipalType,
            StatusLevel,
        )

        mock_assignment = OrphanedAssignment(
            assignment_id="assignment-123",
            permission_set_arn="arn:aws:sso:::permissionSet/test",
            permission_set_name="TestPermissionSet",
            account_id="123456789012",
            account_name="Test Account",
            principal_id="user-123",
            principal_name="test.user",
            principal_type=PrincipalType.USER,
            error_message="Principal not found",
            created_date=datetime.now(timezone.utc),
        )

        mock_result = OrphanedAssignmentStatus(
            timestamp=datetime.now(timezone.utc),
            status=StatusLevel.WARNING,
            message="Test message",
            orphaned_assignments=[mock_assignment],
            cleanup_available=True,
        )

        # Save and verify structure
        cache_file = _save_detection_results(profile_name, mock_result)

        with open(cache_file, "r") as f:
            cache_data = json.load(f)

        # Check structure
        assert "timestamp" in cache_data
        assert "profile" in cache_data
        assert "orphaned_assignments" in cache_data
        assert cache_data["profile"] == profile_name
        assert len(cache_data["orphaned_assignments"]) == 1

        assignment_data = cache_data["orphaned_assignments"][0]
        assert assignment_data["permission_set_arn"] == mock_assignment.permission_set_arn
        assert assignment_data["permission_set_name"] == mock_assignment.permission_set_name
        assert assignment_data["account_id"] == mock_assignment.account_id
        assert assignment_data["principal_id"] == mock_assignment.principal_id
        assert assignment_data["principal_type"] == mock_assignment.principal_type.value
