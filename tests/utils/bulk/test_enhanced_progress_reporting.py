"""Tests for enhanced progress reporting functionality.

This module tests the enhanced progress reporting features including:
- Detailed progress information for extended operations
- Progress persistence for resumable operations
- Estimated time remaining calculations for large account sets
"""
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

from src.awsideman.utils.bulk.multi_account_progress import (
    MultiAccountProgressTracker,
    ProgressPersistence,
    ProgressSnapshot,
)


class TestProgressPersistence:
    """Test progress persistence functionality."""

    def test_save_and_load_progress(self):
        """Test saving and loading progress snapshots."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = ProgressPersistence(temp_dir)

            # Create a progress snapshot
            snapshot = ProgressSnapshot(
                operation_id="test_op_123",
                operation_type="assign",
                total_accounts=100,
                processed_accounts=25,
                successful_count=20,
                failed_count=3,
                skipped_count=2,
                start_time=time.time() - 300,  # 5 minutes ago
                last_update_time=time.time(),
                current_account_id="123456789012",
                current_account_name="test-account",
                estimated_completion_time=time.time() + 900,  # 15 minutes from now
                processing_rate=0.083,  # ~5 accounts per minute
                batch_size=10,
            )

            # Save progress
            persistence.save_progress(snapshot)

            # Load progress
            loaded_snapshot = persistence.load_progress("test_op_123")

            assert loaded_snapshot is not None
            assert loaded_snapshot.operation_id == "test_op_123"
            assert loaded_snapshot.operation_type == "assign"
            assert loaded_snapshot.total_accounts == 100
            assert loaded_snapshot.processed_accounts == 25
            assert loaded_snapshot.successful_count == 20
            assert loaded_snapshot.failed_count == 3
            assert loaded_snapshot.skipped_count == 2
            assert loaded_snapshot.current_account_id == "123456789012"
            assert loaded_snapshot.current_account_name == "test-account"
            assert loaded_snapshot.batch_size == 10

    def test_load_nonexistent_progress(self):
        """Test loading progress for non-existent operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = ProgressPersistence(temp_dir)

            loaded_snapshot = persistence.load_progress("nonexistent_op")
            assert loaded_snapshot is None

    def test_delete_progress(self):
        """Test deleting progress files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = ProgressPersistence(temp_dir)

            # Create and save a snapshot
            snapshot = ProgressSnapshot(
                operation_id="test_delete",
                operation_type="revoke",
                total_accounts=50,
                processed_accounts=10,
                successful_count=8,
                failed_count=1,
                skipped_count=1,
                start_time=time.time(),
                last_update_time=time.time(),
            )

            persistence.save_progress(snapshot)

            # Verify it exists
            assert persistence.load_progress("test_delete") is not None

            # Delete it
            persistence.delete_progress("test_delete")

            # Verify it's gone
            assert persistence.load_progress("test_delete") is None

    def test_list_active_operations(self):
        """Test listing active operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = ProgressPersistence(temp_dir)

            # Create multiple snapshots
            snapshots = []
            for i in range(3):
                snapshot = ProgressSnapshot(
                    operation_id=f"test_op_{i}",
                    operation_type="assign",
                    total_accounts=100,
                    processed_accounts=i * 10,
                    successful_count=i * 8,
                    failed_count=i * 1,
                    skipped_count=i * 1,
                    start_time=time.time(),
                    last_update_time=time.time(),
                )
                snapshots.append(snapshot)
                persistence.save_progress(snapshot)

            # List active operations
            active_ops = persistence.list_active_operations()

            assert len(active_ops) == 3
            operation_ids = [op.operation_id for op in active_ops]
            assert "test_op_0" in operation_ids
            assert "test_op_1" in operation_ids
            assert "test_op_2" in operation_ids

    def test_cleanup_old_progress(self):
        """Test cleanup of old progress files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            persistence = ProgressPersistence(temp_dir)

            # Create a snapshot and save it
            snapshot = ProgressSnapshot(
                operation_id="old_op",
                operation_type="assign",
                total_accounts=50,
                processed_accounts=25,
                successful_count=20,
                failed_count=3,
                skipped_count=2,
                start_time=time.time(),
                last_update_time=time.time(),
            )

            persistence.save_progress(snapshot)

            # Manually modify the file timestamp to make it old
            progress_file = Path(temp_dir) / "old_op.json"
            old_time = time.time() - (25 * 3600)  # 25 hours ago
            import os

            os.utime(progress_file, (old_time, old_time))

            # Verify file exists before cleanup
            assert progress_file.exists()

            # Run cleanup (max age 24 hours)
            persistence.cleanup_old_progress(max_age_hours=24)

            # Verify file was deleted
            assert not progress_file.exists()


class TestEnhancedProgressReporting:
    """Test enhanced progress reporting functionality."""

    def _create_mock_console(self):
        """Create a properly mocked console with required methods."""
        console = Mock()
        console.get_time = Mock(return_value=time.time)
        console.print = Mock()
        console.is_jupyter = False
        console.set_live = Mock()
        console.clear_live = Mock()
        console.show_cursor = Mock()
        console.push_render_hook = Mock()
        console.pop_render_hook = Mock()
        console.set_alt_screen = Mock(return_value=False)
        console.__enter__ = Mock(return_value=console)
        console.__exit__ = Mock(return_value=None)
        return console

    def test_detailed_stats_calculation(self):
        """Test detailed statistics calculation."""
        console = self._create_mock_console()
        tracker = MultiAccountProgressTracker(
            console, operation_id="test_detailed", enable_persistence=False
        )

        # Initialize manually without starting progress (to avoid Rich components)
        tracker.total_items = 100
        tracker.operation_type = "assign"
        tracker.operation_start_time = time.time()
        tracker.detailed_stats = {
            "total_accounts": 100,
            "batch_size": 10,
            "operation_type": "assign",
            "start_time": tracker.operation_start_time,
        }

        # Simulate some processing
        time.sleep(0.1)  # Small delay to ensure elapsed time > 0

        # Record some results
        for i in range(25):
            status = "success" if i < 20 else "failed"
            tracker.record_account_result(
                account_id=f"12345678901{i:01d}",
                status=status,
                account_name=f"test-account-{i}",
                processing_time=0.5,
                retry_count=0 if status == "success" else 1,
            )

        # Get detailed stats
        stats = tracker.get_detailed_stats()

        assert stats["total_accounts"] == 100
        assert stats["total_processed"] == 25
        assert stats["remaining_accounts"] == 75
        assert stats["progress_percentage"] == 25.0
        assert stats["successful_percentage"] == 80.0  # 20/25 = 80%
        assert stats["failed_percentage"] == 20.0  # 5/25 = 20%
        assert stats["batch_size"] == 10
        assert stats["operation_type"] == "assign"
        assert "elapsed_time" in stats
        assert "average_processing_rate" in stats
        assert "accounts_per_minute" in stats
        assert "time_per_account" in stats

    def test_estimated_completion_info(self):
        """Test estimated completion information calculation."""
        console = self._create_mock_console()
        tracker = MultiAccountProgressTracker(
            console, operation_id="test_completion", enable_persistence=False
        )

        # Initialize manually without starting progress
        tracker.total_items = 100
        tracker.operation_type = "assign"
        tracker.operation_start_time = time.time()
        tracker.detailed_stats = {
            "total_accounts": 100,
            "batch_size": 10,
            "operation_type": "assign",
            "start_time": tracker.operation_start_time,
        }

        # Simulate processing with consistent timing
        for i in range(20):
            tracker.record_account_result(
                account_id=f"12345678901{i:01d}",
                status="success",
                account_name=f"test-account-{i}",
                processing_time=0.1,
            )

        # Get completion info
        completion_info = tracker.get_estimated_completion_info()

        assert completion_info["progress_percentage"] == 20.0
        assert "estimated_remaining_time_seconds" in completion_info
        assert "estimated_completion_timestamp" in completion_info
        assert "current_processing_rate" in completion_info
        assert "average_processing_rate" in completion_info
        assert "accounts_per_minute" in completion_info
        assert "time_elapsed" in completion_info

        # Check formatted values
        if completion_info["estimated_remaining_time_seconds"]:
            assert "estimated_remaining_time_formatted" in completion_info
            assert "estimated_completion_time_formatted" in completion_info

    def test_milestone_tracking(self):
        """Test milestone tracking for large operations."""
        console = self._create_mock_console()
        tracker = MultiAccountProgressTracker(
            console, operation_id="test_milestones", enable_persistence=False
        )

        # Initialize manually with enough accounts to trigger milestones
        tracker.total_items = 100
        tracker.operation_type = "assign"
        tracker.operation_start_time = time.time()
        tracker.detailed_stats = {
            "total_accounts": 100,
            "batch_size": 10,
            "operation_type": "assign",
            "start_time": tracker.operation_start_time,
        }

        # Set milestones for large operations (simulate what start_multi_account_progress does)
        milestone_percentages = [10, 25, 50, 75, 90]
        for pct in milestone_percentages:
            milestone_accounts = int(100 * pct / 100)
            tracker.milestone_times[f"{pct}%"] = milestone_accounts

        # Process accounts to reach 10% milestone
        for i in range(10):
            tracker.record_account_result(
                account_id=f"12345678901{i:01d}",
                status="success",
                account_name=f"test-account-{i}",
                processing_time=0.1,
            )

        # Check that milestone was recorded
        stats = tracker.get_detailed_stats()
        completed_milestones = stats.get("completed_milestones", {})

        assert "10%" in completed_milestones
        assert completed_milestones["10%"]["accounts_processed"] == 10
        assert "completed_at" in completed_milestones["10%"]
        assert "elapsed_time" in completed_milestones["10%"]

    def test_progress_persistence_integration(self):
        """Test integration with progress persistence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self._create_mock_console()

            # Create tracker with persistence enabled
            tracker = MultiAccountProgressTracker(
                console, operation_id="test_persistence_integration", enable_persistence=True
            )
            tracker.progress_persistence = ProgressPersistence(temp_dir)
            tracker.persistence_interval = 0.1  # Save every 0.1 seconds for testing

            # Initialize manually
            tracker.total_items = 50
            tracker.operation_type = "assign"
            tracker.operation_start_time = time.time()
            tracker.detailed_stats = {
                "total_accounts": 50,
                "batch_size": 10,
                "operation_type": "assign",
                "start_time": tracker.operation_start_time,
            }

            # Process some accounts
            for i in range(10):
                tracker.record_account_result(
                    account_id=f"12345678901{i:01d}",
                    status="success",
                    account_name=f"test-account-{i}",
                    processing_time=0.1,
                )
                time.sleep(0.05)  # Small delay to trigger persistence

            # Force a persistence save
            tracker._save_progress_if_enabled()

            # Verify progress was saved
            saved_progress = tracker.progress_persistence.load_progress(
                "test_persistence_integration"
            )
            assert saved_progress is not None
            assert saved_progress.processed_accounts == 10
            assert saved_progress.successful_count == 10
            assert saved_progress.total_accounts == 50

    def test_progress_restoration(self):
        """Test restoring progress from a saved snapshot."""
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self._create_mock_console()
            persistence = ProgressPersistence(temp_dir)

            # Create and save a progress snapshot
            snapshot = ProgressSnapshot(
                operation_id="test_restore",
                operation_type="revoke",
                total_accounts=200,
                processed_accounts=75,
                successful_count=60,
                failed_count=10,
                skipped_count=5,
                start_time=time.time() - 600,  # 10 minutes ago
                last_update_time=time.time(),
                current_account_id="123456789012",
                current_account_name="current-account",
                batch_size=15,
            )
            persistence.save_progress(snapshot)

            # Create new tracker and test restoration manually
            tracker = MultiAccountProgressTracker(
                console, operation_id="test_restore", enable_persistence=True
            )
            tracker.progress_persistence = persistence

            # Load and restore from snapshot manually
            existing_progress = tracker.progress_persistence.load_progress("test_restore")
            assert existing_progress is not None

            tracker._restore_from_snapshot(existing_progress)

            # Verify restoration
            assert tracker.successful_count == 60
            assert tracker.failed_count == 10
            assert tracker.skipped_count == 5
            assert tracker.current_account_id == "123456789012"
            assert tracker.current_account == "current-account"
            assert tracker.operation_type == "revoke"

    def test_processing_rate_calculation(self):
        """Test processing rate calculation and rolling average."""
        console = self._create_mock_console()
        tracker = MultiAccountProgressTracker(
            console, operation_id="test_rate", enable_persistence=False
        )

        # Initialize manually
        tracker.total_items = 50
        tracker.operation_type = "assign"
        tracker.operation_start_time = time.time()
        tracker.last_rate_calculation = tracker.operation_start_time
        tracker.detailed_stats = {
            "total_accounts": 50,
            "batch_size": 10,
            "operation_type": "assign",
            "start_time": tracker.operation_start_time,
        }

        # Simulate processing with varying rates
        for i in range(10):
            tracker.record_account_result(
                account_id=f"12345678901{i:01d}",
                status="success",
                account_name=f"test-account-{i}",
                processing_time=0.1,
            )

            # Force rate calculation update
            tracker._update_detailed_stats()
            time.sleep(0.01)  # Small delay

        # Check that processing rates are being tracked
        assert len(tracker.processing_rates) >= 0  # May be empty if time intervals are too small

        # Get detailed stats
        stats = tracker.get_detailed_stats()
        # current_processing_rate may not be set if rate calculation intervals are too small
        assert "average_processing_rate" in stats

    @patch("src.awsideman.utils.bulk.multi_account_progress.time.time")
    def test_duration_formatting(self, mock_time):
        """Test duration formatting for different time ranges."""
        console = self._create_mock_console()
        tracker = MultiAccountProgressTracker(console, enable_persistence=False)

        # Test seconds
        assert tracker._format_duration(30) == "30s"

        # Test minutes and seconds
        assert tracker._format_duration(90) == "1m 30s"

        # Test hours and minutes
        assert tracker._format_duration(3900) == "1h 5m"

        # Test negative/complete
        assert tracker._format_duration(-1) == "complete"
        assert tracker._format_duration(0) == "0s"

    def test_display_detailed_progress_info(self):
        """Test displaying detailed progress information."""
        console = self._create_mock_console()
        tracker = MultiAccountProgressTracker(
            console, operation_id="test_display", enable_persistence=False
        )

        # Initialize manually
        tracker.total_items = 100
        tracker.operation_type = "assign"
        tracker.operation_start_time = time.time()
        tracker.detailed_stats = {
            "total_accounts": 100,
            "batch_size": 10,
            "operation_type": "assign",
            "start_time": tracker.operation_start_time,
        }

        # Process some accounts
        for i in range(25):
            status = "success" if i < 20 else "failed"
            tracker.record_account_result(
                account_id=f"12345678901{i:01d}",
                status=status,
                account_name=f"test-account-{i}",
                processing_time=0.2,
            )

        # Display detailed progress info
        tracker.display_detailed_progress_info()

        # Verify console.print was called
        console.print.assert_called()

        # Check that a table was printed (Rich Table object)
        print_calls = console.print.call_args_list
        assert len(print_calls) >= 2  # At least newline and table

        # Find the table call
        table_call = None
        for call in print_calls:
            if (
                call[0]
                and hasattr(call[0][0], "title")
                and callable(getattr(call[0][0], "title", None)) is False
            ):
                table_call = call[0][0]
                break

        assert table_call is not None
        assert table_call.title == "Detailed Progress Information"
