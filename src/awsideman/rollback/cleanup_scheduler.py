"""Scheduled cleanup for rollback operations."""

import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from ..utils.config import Config
from .logger import OperationLogger


class CleanupScheduler:
    """Scheduler for automatic cleanup of rollback operations."""

    def __init__(self, config: Optional[Config] = None):
        """Initialize the cleanup scheduler.

        Args:
            config: Configuration instance. If None, creates a new one.
        """
        self.config = config or Config()
        # For global cleanup, use default storage (no profile isolation)
        self.logger = OperationLogger()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_cleanup: Optional[datetime] = None
        self._cleanup_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    def start(self, interval_hours: int = 24) -> None:
        """Start the scheduled cleanup process.

        Args:
            interval_hours: Hours between cleanup runs
        """
        if self._thread and self._thread.is_alive():
            return  # Already running

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._cleanup_loop,
            args=(interval_hours,),
            daemon=True,
            name="RollbackCleanupScheduler",
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the scheduled cleanup process.

        Args:
            timeout: Maximum time to wait for thread to stop

        Returns:
            True if stopped successfully, False if timeout
        """
        if not self._thread or not self._thread.is_alive():
            return True

        self._stop_event.set()
        self._thread.join(timeout=timeout)
        return not self._thread.is_alive()

    def is_running(self) -> bool:
        """Check if the scheduler is running.

        Returns:
            True if scheduler is running, False otherwise
        """
        return self._thread is not None and self._thread.is_alive()

    def set_cleanup_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Set a callback to be called after each cleanup.

        Args:
            callback: Function to call with cleanup results
        """
        self._cleanup_callback = callback

    def run_cleanup_now(self) -> Dict[str, Any]:
        """Run cleanup immediately.

        Returns:
            Dictionary with cleanup results
        """
        rollback_config = self.config.get_rollback_config()

        if not rollback_config.get("enabled", True):
            return {"skipped": True, "reason": "Rollback disabled in configuration"}

        results = self.logger.perform_maintenance(
            retention_days=rollback_config.get("retention_days", 90),
            max_operations=rollback_config.get("max_operations", 10000),
            max_file_size_mb=50,  # Fixed size limit for file rotation
        )

        results["cleanup_time"] = datetime.now().isoformat()
        self._last_cleanup = datetime.now()

        # Call callback if set
        if self._cleanup_callback:
            try:
                self._cleanup_callback(results)
            except Exception:
                pass  # Don't let callback errors break cleanup

        return results

    def get_next_cleanup_time(self, interval_hours: int = 24) -> Optional[datetime]:
        """Get the time of the next scheduled cleanup.

        Args:
            interval_hours: Hours between cleanup runs

        Returns:
            Next cleanup time, or None if never run
        """
        if self._last_cleanup is None:
            return None

        return self._last_cleanup + timedelta(hours=interval_hours)

    def should_run_cleanup(self, interval_hours: int = 24) -> bool:
        """Check if cleanup should run based on schedule.

        Args:
            interval_hours: Hours between cleanup runs

        Returns:
            True if cleanup should run, False otherwise
        """
        rollback_config = self.config.get_rollback_config()

        # Check if auto cleanup is enabled
        if not rollback_config.get("auto_cleanup", True):
            return False

        # Check if rollback is enabled
        if not rollback_config.get("enabled", True):
            return False

        # Check if enough time has passed
        if self._last_cleanup is None:
            return True

        next_cleanup = self._last_cleanup + timedelta(hours=interval_hours)
        return datetime.now() >= next_cleanup

    def _cleanup_loop(self, interval_hours: int) -> None:
        """Main cleanup loop running in background thread.

        Args:
            interval_hours: Hours between cleanup runs
        """
        while not self._stop_event.is_set():
            try:
                if self.should_run_cleanup(interval_hours):
                    self.run_cleanup_now()

                # Sleep for 1 hour intervals, checking for stop event
                for _ in range(interval_hours):
                    if self._stop_event.wait(timeout=3600):  # 1 hour
                        return

            except Exception:
                # Log error but continue running
                # In a real implementation, you might want to use proper logging
                pass

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status information.

        Returns:
            Dictionary with scheduler status
        """
        rollback_config = self.config.get_rollback_config()

        return {
            "running": self.is_running(),
            "auto_cleanup_enabled": rollback_config.get("auto_cleanup", True),
            "rollback_enabled": rollback_config.get("enabled", True),
            "last_cleanup": self._last_cleanup.isoformat() if self._last_cleanup else None,
            "next_cleanup": (
                self.get_next_cleanup_time().isoformat() if self.get_next_cleanup_time() else None
            ),
            "retention_days": rollback_config.get("retention_days", 90),
            "max_operations": rollback_config.get("max_operations", 10000),
            "storage_stats": self.logger.get_storage_stats(),
        }


# Global scheduler instance
_global_scheduler: Optional[CleanupScheduler] = None


def get_global_scheduler() -> CleanupScheduler:
    """Get the global cleanup scheduler instance.

    Returns:
        Global CleanupScheduler instance
    """
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = CleanupScheduler()
    return _global_scheduler


def start_global_scheduler(interval_hours: int = 24) -> None:
    """Start the global cleanup scheduler.

    Args:
        interval_hours: Hours between cleanup runs
    """
    scheduler = get_global_scheduler()
    scheduler.start(interval_hours)


def stop_global_scheduler(timeout: float = 5.0) -> bool:
    """Stop the global cleanup scheduler.

    Args:
        timeout: Maximum time to wait for scheduler to stop

    Returns:
        True if stopped successfully, False if timeout
    """
    global _global_scheduler
    if _global_scheduler is None:
        return True

    result = _global_scheduler.stop(timeout)
    if result:
        _global_scheduler = None
    return result
