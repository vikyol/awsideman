"""Comprehensive logging configuration for AWS Identity Center status monitoring."""

import json
import logging
import logging.handlers
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class LogLevel(str, Enum):
    """Log levels for configuration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Log output formats."""

    SIMPLE = "simple"
    DETAILED = "detailed"
    JSON = "json"
    STRUCTURED = "structured"


@dataclass
class LoggingConfig:
    """Configuration for logging system."""

    level: LogLevel = LogLevel.INFO
    format_type: LogFormat = LogFormat.DETAILED
    enable_file_logging: bool = True
    enable_console_logging: bool = True
    log_directory: str = ".awsideman/logs"
    log_filename: str = "awsideman-status.log"
    max_file_size_mb: int = 10
    backup_count: int = 5
    enable_structured_logging: bool = True
    include_timestamps: bool = True
    include_thread_info: bool = False
    include_process_info: bool = False
    console_colors: bool = True
    log_aws_requests: bool = False
    log_performance_metrics: bool = True
    sensitive_data_patterns: List[str] = field(
        default_factory=lambda: [r"password", r"secret", r"token", r"key", r"credential"]
    )

    def __post_init__(self) -> None:
        """Ensure collections are properly initialized."""
        if self.sensitive_data_patterns is None:
            self.sensitive_data_patterns = []


class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive data from log messages."""

    def __init__(self, patterns: List[str]) -> None:
        """
        Initialize the filter with sensitive data patterns.

        Args:
            patterns: List of regex patterns to match sensitive data
        """
        super().__init__()
        self.patterns = patterns
        import re

        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record to redact sensitive data.

        Args:
            record: Log record to filter

        Returns:
            bool: Always True (we modify but don't filter out records)
        """
        # Redact sensitive data from message
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._redact_sensitive_data(record.msg)

        # Redact sensitive data from args
        if hasattr(record, "args") and record.args:
            record.args = tuple(
                self._redact_sensitive_data(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )

        return True

    def _redact_sensitive_data(self, text: str) -> str:
        """Redact sensitive data from text."""
        for pattern in self.compiled_patterns:
            text = pattern.sub("[REDACTED]", text)
        return text


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging with JSON output."""

    def __init__(self, include_extra: bool = True) -> None:
        """
        Initialize the structured formatter.

        Args:
            include_extra: Whether to include extra fields from log records
        """
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as structured JSON.

        Args:
            record: Log record to format

        Returns:
            str: JSON formatted log message
        """
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add thread and process info if available
        if hasattr(record, "thread") and record.thread:
            log_data["thread_id"] = record.thread

        if hasattr(record, "process") and record.process:
            log_data["process_id"] = record.process

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if enabled
        if self.include_extra:
            # Get all extra attributes (those not in standard LogRecord)
            standard_attrs = {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "exc_info",
                "exc_text",
                "stack_info",
            }

            extra_data = {}
            for key, value in record.__dict__.items():
                if key not in standard_attrs and not key.startswith("_"):
                    try:
                        # Ensure value is JSON serializable
                        json.dumps(value)
                        extra_data[key] = value
                    except (TypeError, ValueError):
                        extra_data[key] = str(value)

            if extra_data:
                log_data["extra"] = extra_data

        try:
            return json.dumps(log_data, default=str)
        except (TypeError, ValueError):
            # Fallback to simple format if JSON serialization fails
            return f"{log_data['timestamp']} - {log_data['level']} - {log_data['logger']} - {log_data['message']}"


class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter with color support."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def __init__(self, use_colors: bool = True) -> None:
        """
        Initialize the colored formatter.

        Args:
            use_colors: Whether to use colors in output
        """
        super().__init__()
        self.use_colors = use_colors and self._supports_color()

    def _supports_color(self) -> bool:
        """Check if the terminal supports colors."""
        return (
            hasattr(sys.stderr, "isatty")
            and sys.stderr.isatty()
            and os.environ.get("TERM") != "dumb"
        )

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with colors.

        Args:
            record: Log record to format

        Returns:
            str: Formatted log message with colors
        """
        if self.use_colors:
            color = self.COLORS.get(record.levelname, "")
            reset = self.COLORS["RESET"]

            # Format: [TIMESTAMP] LEVEL - LOGGER - MESSAGE
            formatted = (
                f"{color}[{datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{record.levelname:<8}{reset} - "
                f"{record.name} - "
                f"{record.getMessage()}"
            )

            # Add exception info if present
            if record.exc_info:
                formatted += f"\n{self.formatException(record.exc_info)}"

            return formatted
        else:
            # No colors, use simple format
            return (
                f"[{datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{record.levelname:<8} - "
                f"{record.name} - "
                f"{record.getMessage()}"
            )


class PerformanceFilter(logging.Filter):
    """Filter to add performance metrics to log records."""

    def __init__(self) -> None:
        """Initialize the performance filter."""
        super().__init__()
        self.start_times: Dict[str, float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add performance metrics to log records.

        Args:
            record: Log record to enhance

        Returns:
            bool: Always True
        """
        # Add memory usage if available
        try:
            import psutil

            process = psutil.Process()
            record.memory_mb = process.memory_info().rss / 1024 / 1024
            record.cpu_percent = process.cpu_percent()
        except ImportError:
            pass

        return True


class StatusLoggingManager:
    """
    Manager for status monitoring logging configuration.

    Provides centralized logging setup and management for all status
    monitoring components with support for multiple output formats,
    sensitive data filtering, and performance monitoring.
    """

    def __init__(self, config: Optional[LoggingConfig] = None):
        """
        Initialize the logging manager.

        Args:
            config: Logging configuration
        """
        self.config = config or LoggingConfig()
        self._loggers: Dict[str, logging.Logger] = {}
        self._handlers_configured = False

    def setup_logging(self) -> None:
        """Set up logging configuration for all components."""
        if self._handlers_configured:
            return

        # Create log directory if it doesn't exist
        if self.config.enable_file_logging:
            log_dir = Path(self.config.log_directory)
            log_dir.mkdir(parents=True, exist_ok=True)

        # Configure root logger
        root_logger = logging.getLogger("awsideman")
        root_logger.setLevel(getattr(logging, self.config.level.value))

        # Clear existing handlers
        root_logger.handlers.clear()

        # Add console handler
        if self.config.enable_console_logging:
            console_handler = self._create_console_handler()
            root_logger.addHandler(console_handler)

        # Add file handler
        if self.config.enable_file_logging:
            file_handler = self._create_file_handler()
            root_logger.addHandler(file_handler)

        # Configure AWS SDK logging
        self._configure_aws_logging()

        # Configure third-party library logging
        self._configure_third_party_logging()

        self._handlers_configured = True

    def _create_console_handler(self) -> logging.Handler:
        """Create console handler with appropriate formatter."""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, self.config.level.value))

        formatter: logging.Formatter
        if self.config.format_type == LogFormat.JSON:
            formatter = StructuredFormatter()
        elif self.config.console_colors:
            formatter = ColoredConsoleFormatter()
        else:
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)-8s - %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        handler.setFormatter(formatter)

        # Add filters
        if self.config.sensitive_data_patterns:
            handler.addFilter(SensitiveDataFilter(self.config.sensitive_data_patterns))

        if self.config.log_performance_metrics:
            handler.addFilter(PerformanceFilter())

        return handler

    def _create_file_handler(self) -> logging.Handler:
        """Create rotating file handler."""
        log_file = Path(self.config.log_directory) / self.config.log_filename

        handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file),
            maxBytes=self.config.max_file_size_mb * 1024 * 1024,
            backupCount=self.config.backup_count,
            encoding="utf-8",
        )

        handler.setLevel(getattr(logging, self.config.level.value))

        formatter: logging.Formatter
        if self.config.format_type == LogFormat.JSON or self.config.enable_structured_logging:
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)-8s - %(name)s - %(funcName)s:%(lineno)d - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

        handler.setFormatter(formatter)

        # Add filters
        if self.config.sensitive_data_patterns:
            handler.addFilter(SensitiveDataFilter(self.config.sensitive_data_patterns))

        if self.config.log_performance_metrics:
            handler.addFilter(PerformanceFilter())

        return handler

    def _configure_aws_logging(self) -> None:
        """Configure AWS SDK logging."""
        aws_loggers = ["boto3", "botocore", "urllib3.connectionpool"]

        for logger_name in aws_loggers:
            logger = logging.getLogger(logger_name)
            if self.config.log_aws_requests:
                logger.setLevel(logging.DEBUG)
            else:
                logger.setLevel(logging.WARNING)

    def _configure_third_party_logging(self) -> None:
        """Configure third-party library logging."""
        # Reduce noise from third-party libraries
        third_party_loggers = ["urllib3", "requests", "asyncio"]

        for logger_name in third_party_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.WARNING)

    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger instance for a specific component.

        Args:
            name: Logger name (usually module name)

        Returns:
            logging.Logger: Configured logger instance
        """
        if not self._handlers_configured:
            self.setup_logging()

        if name not in self._loggers:
            # Create logger with awsideman prefix
            full_name = f"awsideman.{name}" if not name.startswith("awsideman") else name
            logger = logging.getLogger(full_name)
            self._loggers[name] = logger

        return self._loggers[name]

    def log_operation_start(self, logger: logging.Logger, operation: str, **context) -> str:
        """
        Log the start of an operation with context.

        Args:
            logger: Logger to use
            operation: Operation name
            **context: Additional context information

        Returns:
            str: Operation ID for tracking
        """
        import uuid

        operation_id = str(uuid.uuid4())[:8]

        logger.info(
            f"Starting operation: {operation}",
            extra={
                "operation_id": operation_id,
                "operation": operation,
                "operation_start": True,
                **context,
            },
        )

        return operation_id

    def log_operation_end(
        self,
        logger: logging.Logger,
        operation: str,
        operation_id: str,
        success: bool = True,
        duration_ms: Optional[float] = None,
        **context,
    ) -> None:
        """
        Log the end of an operation.

        Args:
            logger: Logger to use
            operation: Operation name
            operation_id: Operation ID from start
            success: Whether operation was successful
            duration_ms: Operation duration in milliseconds
            **context: Additional context information
        """
        level = logging.INFO if success else logging.ERROR
        status = "completed" if success else "failed"

        extra_data = {
            "operation_id": operation_id,
            "operation": operation,
            "operation_end": True,
            "success": success,
            **context,
        }

        if duration_ms is not None:
            extra_data["duration_ms"] = duration_ms

        logger.log(level, f"Operation {status}: {operation}", extra=extra_data)

    def log_performance_metric(
        self,
        logger: logging.Logger,
        metric_name: str,
        value: Union[int, float],
        unit: str = "",
        **context,
    ) -> None:
        """
        Log a performance metric.

        Args:
            logger: Logger to use
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement
            **context: Additional context information
        """
        logger.info(
            f"Performance metric: {metric_name} = {value} {unit}",
            extra={
                "metric_name": metric_name,
                "metric_value": value,
                "metric_unit": unit,
                "performance_metric": True,
                **context,
            },
        )

    def create_context_logger(self, base_logger: logging.Logger, **context) -> "ContextLogger":
        """
        Create a context logger that automatically includes context in all log messages.

        Args:
            base_logger: Base logger to wrap
            **context: Context to include in all messages

        Returns:
            ContextLogger: Logger with automatic context
        """
        return ContextLogger(base_logger, context)


class ContextLogger:
    """Logger wrapper that automatically includes context in all log messages."""

    def __init__(self, logger: logging.Logger, context: Dict[str, Any]):
        """
        Initialize the context logger.

        Args:
            logger: Base logger to wrap
            context: Context to include in all messages
        """
        self.logger = logger
        self.context = context

    def _log_with_context(self, level: int, msg: str, *args, **kwargs) -> None:
        """Log message with automatic context inclusion."""
        extra = kwargs.get("extra", {})
        extra.update(self.context)
        kwargs["extra"] = extra
        self.logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        """Log debug message with context."""
        self._log_with_context(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        """Log info message with context."""
        self._log_with_context(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        """Log warning message with context."""
        self._log_with_context(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        """Log error message with context."""
        self._log_with_context(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        """Log critical message with context."""
        self._log_with_context(logging.CRITICAL, msg, *args, **kwargs)


# Global logging manager instance
_global_logging_manager: Optional[StatusLoggingManager] = None


def get_logging_manager() -> StatusLoggingManager:
    """Get the global logging manager instance."""
    global _global_logging_manager
    if _global_logging_manager is None:
        _global_logging_manager = StatusLoggingManager()
    return _global_logging_manager


def setup_status_logging(config: Optional[LoggingConfig] = None) -> None:
    """
    Set up logging for status monitoring components.

    Args:
        config: Logging configuration
    """
    global _global_logging_manager
    _global_logging_manager = StatusLoggingManager(config)
    _global_logging_manager.setup_logging()


def get_status_logger(name: str) -> logging.Logger:
    """
    Get a logger for status monitoring components.

    Args:
        name: Logger name

    Returns:
        logging.Logger: Configured logger
    """
    return get_logging_manager().get_logger(name)
