"""Tests for comprehensive logging configuration system."""

import json
import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.awsideman.utils.logging_config import (
    ColoredConsoleFormatter,
    ContextLogger,
    LogFormat,
    LoggingConfig,
    LogLevel,
    PerformanceFilter,
    SensitiveDataFilter,
    StatusLoggingManager,
    StructuredFormatter,
    get_logging_manager,
    get_status_logger,
    setup_status_logging,
)


class TestLoggingConfig:
    """Test LoggingConfig functionality."""

    def test_default_config(self):
        """Test default logging configuration."""
        config = LoggingConfig()

        assert config.level == LogLevel.INFO
        assert config.format_type == LogFormat.DETAILED
        assert config.enable_file_logging is True
        assert config.enable_console_logging is True
        assert config.log_directory == ".awsideman/logs"
        assert config.log_filename == "awsideman-status.log"
        assert config.max_file_size_mb == 10
        assert config.backup_count == 5
        assert config.console_colors is True
        assert len(config.sensitive_data_patterns) > 0

    def test_custom_config(self):
        """Test custom logging configuration."""
        config = LoggingConfig(
            level=LogLevel.DEBUG,
            format_type=LogFormat.JSON,
            enable_file_logging=False,
            log_directory="/tmp/logs",
            max_file_size_mb=50,
            console_colors=False,
        )

        assert config.level == LogLevel.DEBUG
        assert config.format_type == LogFormat.JSON
        assert config.enable_file_logging is False
        assert config.log_directory == "/tmp/logs"
        assert config.max_file_size_mb == 50
        assert config.console_colors is False


class TestSensitiveDataFilter:
    """Test SensitiveDataFilter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = SensitiveDataFilter(["password", "secret", "token"])

    def test_filter_sensitive_message(self):
        """Test filtering sensitive data from log messages."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User password is secret123",
            args=(),
            exc_info=None,
        )

        result = self.filter.filter(record)

        assert result is True  # Filter doesn't block records
        assert "password" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_filter_sensitive_args(self):
        """Test filtering sensitive data from log arguments."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Login attempt with %s",
            args=("password=secret123",),
            exc_info=None,
        )

        result = self.filter.filter(record)

        assert result is True
        assert "[REDACTED]" in record.args[0]
        assert "secret123" not in record.args[0]

    def test_filter_case_insensitive(self):
        """Test that filtering is case insensitive."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="API TOKEN is abc123",
            args=(),
            exc_info=None,
        )

        result = self.filter.filter(record)

        assert result is True
        assert "TOKEN" not in record.msg
        assert "[REDACTED]" in record.msg


class TestStructuredFormatter:
    """Test StructuredFormatter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.formatter = StructuredFormatter()

    def test_format_basic_record(self):
        """Test formatting a basic log record."""
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_function"
        record.module = "test_module"

        formatted = self.formatter.format(record)
        data = json.loads(formatted)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.module"
        assert data["message"] == "Test message"
        assert data["module"] == "test_module"
        assert data["function"] == "test_function"
        assert data["line"] == 42
        assert "timestamp" in data

    def test_format_with_extra_fields(self):
        """Test formatting with extra fields."""
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_function"
        record.module = "test_module"
        record.operation_id = "op-123"
        record.user_id = "user-456"

        formatted = self.formatter.format(record)
        data = json.loads(formatted)

        assert "extra" in data
        assert data["extra"]["operation_id"] == "op-123"
        assert data["extra"]["user_id"] == "user-456"

    def test_format_with_exception(self):
        """Test formatting with exception information."""
        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()  # Get the current exception info
            record = logging.LogRecord(
                name="test.module",
                level=logging.ERROR,
                pathname="/path/to/file.py",
                lineno=42,
                msg="Error occurred",
                args=(),
                exc_info=exc_info,  # Pass the actual exception info tuple
            )
            record.funcName = "test_function"
            record.module = "test_module"

            formatted = self.formatter.format(record)
            data = json.loads(formatted)

            assert "exception" in data
            # formatException returns a tuple, so we need to check the string representation
            exception_str = str(data["exception"])
            assert "ValueError" in exception_str
            assert "Test exception" in exception_str


class TestColoredConsoleFormatter:
    """Test ColoredConsoleFormatter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.formatter = ColoredConsoleFormatter(use_colors=False)  # Disable colors for testing

    def test_format_basic_record(self):
        """Test formatting a basic log record."""
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_function"
        record.module = "test_module"

        formatted = self.formatter.format(record)

        assert "INFO" in formatted
        assert "test.module" in formatted
        assert "Test message" in formatted
        assert "[" in formatted  # Timestamp brackets

    def test_format_with_colors_disabled(self):
        """Test formatting without colors."""
        formatter = ColoredConsoleFormatter(use_colors=False)
        record = logging.LogRecord(
            name="test.module",
            level=logging.ERROR,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Error message",
            args=(),
            exc_info=None,
        )
        record.funcName = "test_function"
        record.module = "test_module"

        formatted = formatter.format(record)

        # Should not contain ANSI color codes
        assert "\033[" not in formatted
        assert "ERROR" in formatted
        assert "Error message" in formatted


class TestPerformanceFilter:
    """Test PerformanceFilter functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.filter = PerformanceFilter()


class TestStatusLoggingManager:
    """Test StatusLoggingManager functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = LoggingConfig(
            log_directory=self.temp_dir,
            enable_file_logging=True,
            enable_console_logging=False,  # Disable console for testing
        )
        self.manager = StatusLoggingManager(self.config)

    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up any handlers
        for logger_name in list(logging.Logger.manager.loggerDict.keys()):
            if logger_name.startswith("awsideman"):
                logger = logging.getLogger(logger_name)
                for handler in logger.handlers[:]:
                    handler.close()
                    logger.removeHandler(handler)

        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_setup_logging_creates_log_directory(self):
        """Test that setup_logging creates the log directory."""
        self.manager.setup_logging()

        log_dir = Path(self.temp_dir)
        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_setup_logging_configures_root_logger(self):
        """Test that setup_logging configures the root logger."""
        self.manager.setup_logging()

        root_logger = logging.getLogger("awsideman")
        assert root_logger.level == getattr(logging, self.config.level.value)
        assert len(root_logger.handlers) > 0

    def test_get_logger_returns_configured_logger(self):
        """Test that get_logger returns a properly configured logger."""
        logger = self.manager.get_logger("test_component")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "awsideman.test_component"

    def test_get_logger_caches_loggers(self):
        """Test that get_logger caches logger instances."""
        logger1 = self.manager.get_logger("test_component")
        logger2 = self.manager.get_logger("test_component")

        assert logger1 is logger2

    def test_log_operation_start(self):
        """Test logging operation start."""
        logger = self.manager.get_logger("test_component")

        with patch.object(logger, "info") as mock_info:
            operation_id = self.manager.log_operation_start(
                logger, "test_operation", user_id="user-123"
            )

            assert isinstance(operation_id, str)
            assert len(operation_id) == 8  # UUID prefix length

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "Starting operation: test_operation" in call_args[0][0]
            assert call_args[1]["extra"]["operation_id"] == operation_id
            assert call_args[1]["extra"]["user_id"] == "user-123"

    def test_log_operation_end_success(self):
        """Test logging successful operation end."""
        logger = self.manager.get_logger("test_component")

        with patch.object(logger, "log") as mock_log:
            self.manager.log_operation_end(
                logger, "test_operation", "op-123", success=True, duration_ms=150.5
            )

            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert call_args[0][0] == logging.INFO
            assert "Operation completed: test_operation" in call_args[0][1]
            assert call_args[1]["extra"]["success"] is True
            assert call_args[1]["extra"]["duration_ms"] == 150.5

    def test_log_operation_end_failure(self):
        """Test logging failed operation end."""
        logger = self.manager.get_logger("test_component")

        with patch.object(logger, "log") as mock_log:
            self.manager.log_operation_end(
                logger, "test_operation", "op-123", success=False, error_code="ERR_001"
            )

            mock_log.assert_called_once()
            call_args = mock_log.call_args
            assert call_args[0][0] == logging.ERROR
            assert "Operation failed: test_operation" in call_args[0][1]
            assert call_args[1]["extra"]["success"] is False
            assert call_args[1]["extra"]["error_code"] == "ERR_001"

    def test_log_performance_metric(self):
        """Test logging performance metrics."""
        logger = self.manager.get_logger("test_component")

        with patch.object(logger, "info") as mock_info:
            self.manager.log_performance_metric(
                logger, "response_time", 125.5, "ms", operation="test_op"
            )

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            assert "Performance metric: response_time = 125.5 ms" in call_args[0][0]
            assert call_args[1]["extra"]["metric_name"] == "response_time"
            assert call_args[1]["extra"]["metric_value"] == 125.5
            assert call_args[1]["extra"]["metric_unit"] == "ms"
            assert call_args[1]["extra"]["operation"] == "test_op"

    def test_create_context_logger(self):
        """Test creating a context logger."""
        base_logger = self.manager.get_logger("test_component")
        context = {"user_id": "user-123", "operation": "test_op"}

        context_logger = self.manager.create_context_logger(base_logger, **context)

        assert isinstance(context_logger, ContextLogger)
        assert context_logger.logger is base_logger
        assert context_logger.context == context


class TestContextLogger:
    """Test ContextLogger functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.base_logger = Mock(spec=logging.Logger)
        self.context = {"user_id": "user-123", "operation": "test_op"}
        self.context_logger = ContextLogger(self.base_logger, self.context)

    def test_debug_with_context(self):
        """Test debug logging with context."""
        self.context_logger.debug("Debug message", extra={"additional": "data"})

        self.base_logger.log.assert_called_once()
        call_args = self.base_logger.log.call_args

        assert call_args[0][0] == logging.DEBUG
        assert call_args[0][1] == "Debug message"

        # Check that context is merged with extra
        extra = call_args[1]["extra"]
        assert extra["user_id"] == "user-123"
        assert extra["operation"] == "test_op"
        assert extra["additional"] == "data"

    def test_info_with_context(self):
        """Test info logging with context."""
        self.context_logger.info("Info message")

        self.base_logger.log.assert_called_once()
        call_args = self.base_logger.log.call_args

        assert call_args[0][0] == logging.INFO
        assert call_args[0][1] == "Info message"

        extra = call_args[1]["extra"]
        assert extra["user_id"] == "user-123"
        assert extra["operation"] == "test_op"

    def test_error_with_context(self):
        """Test error logging with context."""
        self.context_logger.error("Error message", exc_info=True)

        self.base_logger.log.assert_called_once()
        call_args = self.base_logger.log.call_args

        assert call_args[0][0] == logging.ERROR
        assert call_args[0][1] == "Error message"
        assert call_args[1]["exc_info"] is True

        extra = call_args[1]["extra"]
        assert extra["user_id"] == "user-123"
        assert extra["operation"] == "test_op"


class TestGlobalLoggingFunctions:
    """Test global logging functions."""

    def test_get_logging_manager_singleton(self):
        """Test that get_logging_manager returns the same instance."""
        manager1 = get_logging_manager()
        manager2 = get_logging_manager()

        assert manager1 is manager2
        assert isinstance(manager1, StatusLoggingManager)

    def test_setup_status_logging(self):
        """Test setup_status_logging function."""
        config = LoggingConfig(level=LogLevel.DEBUG)

        with patch("src.awsideman.utils.logging_config.StatusLoggingManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            setup_status_logging(config)

            mock_manager_class.assert_called_once_with(config)
            mock_manager.setup_logging.assert_called_once()

    def test_get_status_logger(self):
        """Test get_status_logger function."""
        with patch("src.awsideman.utils.logging_config.get_logging_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_logger = Mock()
            mock_manager.get_logger.return_value = mock_logger
            mock_get_manager.return_value = mock_manager

            logger = get_status_logger("test_component")

            assert logger is mock_logger
            mock_manager.get_logger.assert_called_once_with("test_component")


class TestLoggingIntegration:
    """Integration tests for logging system."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = LoggingConfig(
            log_directory=self.temp_dir,
            format_type=LogFormat.JSON,
            enable_file_logging=True,
            enable_console_logging=False,
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temp directory
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_logging(self):
        """Test complete logging workflow."""
        manager = StatusLoggingManager(self.config)
        manager.setup_logging()

        logger = manager.get_logger("integration_test")

        # Log various types of messages
        logger.info("Test info message", extra={"test_id": "test-123"})
        logger.warning("Test warning message")
        logger.error("Test error message", extra={"error_code": "ERR_001"})

        # Check that log file was created
        log_file = Path(self.temp_dir) / self.config.log_filename
        assert log_file.exists()

        # Read and verify log content
        with open(log_file, "r") as f:
            log_lines = f.readlines()

        assert len(log_lines) >= 3

        # Verify JSON format
        for line in log_lines:
            data = json.loads(line.strip())
            assert "timestamp" in data
            assert "level" in data
            assert "logger" in data
            assert "message" in data

    def test_sensitive_data_filtering(self):
        """Test that sensitive data is filtered from logs."""
        config = LoggingConfig(
            log_directory=self.temp_dir,
            enable_file_logging=True,
            enable_console_logging=False,
            sensitive_data_patterns=["password", "secret"],
        )

        manager = StatusLoggingManager(config)
        manager.setup_logging()

        logger = manager.get_logger("sensitive_test")
        logger.info("User password is secret123 and token is abc456")

        # Check log file content
        log_file = Path(self.temp_dir) / config.log_filename
        with open(log_file, "r") as f:
            content = f.read()

        assert "secret123" not in content
        assert "[REDACTED]" in content
