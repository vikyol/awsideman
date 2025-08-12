"""Security utilities for secure memory handling and input validation."""

import ctypes
import logging
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecureMemory:
    """
    Secure memory handling utilities for sensitive data like encryption keys.

    Provides memory locking and secure deletion capabilities to prevent
    sensitive data from being swapped to disk or remaining in memory
    after use.
    """

    def __init__(self):
        """Initialize secure memory handler."""
        self._locked_pages = set()
        self._is_available = self._check_availability()

    def _check_availability(self) -> bool:
        """
        Check if secure memory features are available on this platform.

        Returns:
            True if secure memory features are available, False otherwise
        """
        try:
            if os.name == "posix":
                # Check if mlock is available
                import mlock  # noqa: F401

                return True
            elif os.name == "nt":
                # Check if VirtualLock is available
                try:
                    ctypes.windll.kernel32.VirtualLock
                    return True
                except AttributeError:
                    return False
            else:
                return False
        except ImportError:
            logger.debug("Secure memory not available: mlock library not found")
            return False
        except Exception as e:
            logger.debug(f"Secure memory not available: {e}")
            return False

    def is_available(self) -> bool:
        """
        Check if secure memory features are available.

        Returns:
            True if available, False otherwise
        """
        return self._is_available

    def lock_memory(self, data: bytes) -> Optional[int]:
        """
        Lock memory pages containing sensitive data to prevent swapping.

        Args:
            data: Sensitive data to lock in memory

        Returns:
            Memory address if successful, None if failed
        """
        if not self._is_available:
            logger.debug("Secure memory not available, skipping memory lock")
            return None

        try:
            if os.name == "posix":
                # Use mlock on Unix systems
                import mlock

                addr = id(data)
                mlock.mlockall(mlock.MCL_CURRENT | mlock.MCL_FUTURE)
                self._locked_pages.add(addr)
                logger.debug(f"Locked memory page at address {addr}")
                return addr
            elif os.name == "nt":
                # Use VirtualLock on Windows
                addr = id(data)
                size = len(data)
                result = ctypes.windll.kernel32.VirtualLock(addr, size)
                if result:
                    self._locked_pages.add(addr)
                    logger.debug(f"Locked memory page at address {addr}")
                    return addr
                else:
                    logger.warning("Failed to lock memory page on Windows")
                    return None
        except Exception as e:
            logger.warning(f"Failed to lock memory: {e}")
            return None

    def unlock_memory(self, addr: int) -> bool:
        """
        Unlock previously locked memory pages.

        Args:
            addr: Memory address to unlock

        Returns:
            True if successful, False otherwise
        """
        if not self._is_available or addr not in self._locked_pages:
            return False

        try:
            if os.name == "posix":
                # Use munlock on Unix systems
                import mlock

                mlock.munlockall()
                self._locked_pages.discard(addr)
                logger.debug(f"Unlocked memory page at address {addr}")
                return True
            elif os.name == "nt":
                # Use VirtualUnlock on Windows
                # Note: We don't have the size, so this is best effort
                result = ctypes.windll.kernel32.VirtualUnlock(addr, 0)
                if result:
                    self._locked_pages.discard(addr)
                    logger.debug(f"Unlocked memory page at address {addr}")
                    return True
                else:
                    logger.warning("Failed to unlock memory page on Windows")
                    return False
        except Exception as e:
            logger.warning(f"Failed to unlock memory: {e}")
            return False

    def secure_zero(self, data: bytearray) -> None:
        """
        Securely zero out sensitive data in memory.

        Args:
            data: Bytearray to zero out
        """
        if not isinstance(data, bytearray):
            logger.warning("secure_zero called on non-bytearray, cannot securely clear")
            return

        try:
            # Overwrite with random data first
            for i in range(len(data)):
                data[i] = secrets.randbits(8)

            # Then overwrite with zeros
            for i in range(len(data)):
                data[i] = 0

            # Force memory barrier to ensure writes complete
            if os.name == "posix":
                os.sync()

            logger.debug(f"Securely zeroed {len(data)} bytes of sensitive data")

        except Exception as e:
            logger.warning(f"Failed to securely zero memory: {e}")

    def cleanup(self) -> None:
        """Clean up all locked memory pages."""
        for addr in list(self._locked_pages):
            self.unlock_memory(addr)


class TimingProtection:
    """
    Utilities for protecting against timing attacks.

    Provides constant-time comparison and other timing-safe operations
    to prevent information leakage through timing analysis.
    """

    @staticmethod
    def constant_time_compare(a: bytes, b: bytes) -> bool:
        """
        Perform constant-time comparison to prevent timing attacks.

        Args:
            a: First bytes to compare
            b: Second bytes to compare

        Returns:
            True if bytes are equal, False otherwise
        """
        if len(a) != len(b):
            # Still do a comparison to maintain constant time
            result = 0
            for i in range(max(len(a), len(b))):
                x = a[i % len(a)] if a else 0
                y = b[i % len(b)] if b else 0
                result |= x ^ y
            return False

        result = 0
        for x, y in zip(a, b):
            result |= x ^ y

        return result == 0

    @staticmethod
    def constant_time_select(condition: bool, true_value: bytes, false_value: bytes) -> bytes:
        """
        Select value in constant time based on condition.

        Args:
            condition: Boolean condition
            true_value: Value to return if condition is True
            false_value: Value to return if condition is False

        Returns:
            Selected value
        """
        # Ensure both values are same length for constant time
        max_len = max(len(true_value), len(false_value))
        true_padded = true_value.ljust(max_len, b"\x00")
        false_padded = false_value.ljust(max_len, b"\x00")

        # Use bitwise operations for constant time selection
        mask = 0xFF if condition else 0x00
        result = bytearray(max_len)

        for i in range(max_len):
            result[i] = (true_padded[i] & mask) | (false_padded[i] & (~mask & 0xFF))

        # Return original length
        original_len = len(true_value) if condition else len(false_value)
        return bytes(result[:original_len])

    @staticmethod
    def add_timing_jitter(min_delay_ms: float = 1.0, max_delay_ms: float = 5.0) -> None:
        """
        Add random timing jitter to prevent timing analysis.

        Args:
            min_delay_ms: Minimum delay in milliseconds
            max_delay_ms: Maximum delay in milliseconds
        """
        delay_ms = (
            secrets.randbelow(int((max_delay_ms - min_delay_ms) * 1000)) / 1000.0 + min_delay_ms
        )
        time.sleep(delay_ms / 1000.0)


class InputValidator:
    """
    Input validation and sanitization utilities.

    Provides comprehensive input validation to prevent injection attacks
    and ensure data integrity.
    """

    # Regex patterns for common validations
    CACHE_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\./:]{1,255}$")
    AWS_ARN_PATTERN = re.compile(
        r"^arn:aws:[a-zA-Z0-9\-]+:[a-zA-Z0-9\-]*:([0-9]{12}|):[a-zA-Z0-9\-/._*]+$"
    )
    AWS_ACCOUNT_ID_PATTERN = re.compile(r"^[0-9]{12}$")
    UUID_PATTERN = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    @classmethod
    def validate_cache_key(cls, key: str) -> bool:
        """
        Validate cache key format and safety.

        Args:
            key: Cache key to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(key, str):
            return False

        if not key or len(key) > 255:
            return False

        # Check for path traversal attempts
        if ".." in key or key.startswith("/") or "\\" in key:
            return False

        # Check against allowed pattern
        return bool(cls.CACHE_KEY_PATTERN.match(key))

    @classmethod
    def sanitize_cache_key(cls, key: str) -> str:
        """
        Sanitize cache key to make it safe.

        Args:
            key: Cache key to sanitize

        Returns:
            Sanitized cache key
        """
        if not isinstance(key, str):
            raise ValueError("Cache key must be a string")

        # Remove dangerous characters
        sanitized = re.sub(r"[^\w\-\./:]+", "_", key)

        # Remove path traversal attempts - replace .. with single _
        sanitized = re.sub(r"\.\.+", "_", sanitized)

        # Ensure it doesn't start with /
        if sanitized.startswith("/"):
            sanitized = sanitized[1:]

        # Truncate if too long
        if len(sanitized) > 255:
            sanitized = sanitized[:255]

        # Ensure it's not empty
        if not sanitized:
            sanitized = "default_key"

        return sanitized

    @classmethod
    def validate_aws_arn(cls, arn: str) -> bool:
        """
        Validate AWS ARN format.

        Args:
            arn: ARN to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(arn, str):
            return False

        return bool(cls.AWS_ARN_PATTERN.match(arn))

    @classmethod
    def validate_aws_account_id(cls, account_id: str) -> bool:
        """
        Validate AWS account ID format.

        Args:
            account_id: Account ID to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(account_id, str):
            return False

        return bool(cls.AWS_ACCOUNT_ID_PATTERN.match(account_id))

    @classmethod
    def validate_uuid(cls, uuid_str: str) -> bool:
        """
        Validate UUID format.

        Args:
            uuid_str: UUID string to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(uuid_str, str):
            return False

        return bool(cls.UUID_PATTERN.match(uuid_str))

    @classmethod
    def validate_email(cls, email: str) -> bool:
        """
        Validate email format.

        Args:
            email: Email to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(email, str):
            return False

        return bool(cls.EMAIL_PATTERN.match(email))

    @classmethod
    def validate_file_path(cls, path: str, allowed_dirs: Optional[List[str]] = None) -> bool:
        """
        Validate file path for security.

        Args:
            path: File path to validate
            allowed_dirs: List of allowed directory prefixes

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(path, str):
            return False

        try:
            # Resolve path to prevent traversal
            resolved_path = Path(path).resolve()

            # Check for path traversal
            if ".." in str(resolved_path):
                return False

            # Check against allowed directories if specified
            if allowed_dirs:
                allowed = False
                for allowed_dir in allowed_dirs:
                    allowed_resolved = Path(allowed_dir).resolve()
                    try:
                        resolved_path.relative_to(allowed_resolved)
                        allowed = True
                        break
                    except ValueError:
                        continue

                if not allowed:
                    return False

            return True

        except Exception:
            return False

    @classmethod
    def sanitize_log_data(cls, data: Any) -> str:
        """
        Sanitize data for safe logging.

        Args:
            data: Data to sanitize for logging

        Returns:
            Sanitized string safe for logging
        """
        if data is None:
            return "None"

        # Convert to string
        data_str = str(data)

        # Remove or mask sensitive patterns
        sensitive_patterns = [
            (r"'password':\s*'[^']*'", "'password': '[REDACTED]'"),
            (r'"password":\s*"[^"]*"', '"password": "[REDACTED]"'),
            (r"'api_key':\s*'[^']*'", "'api_key': '[REDACTED]'"),
            (r'"api_key":\s*"[^"]*"', '"api_key": "[REDACTED]"'),
            (r"'secret':\s*'[^']*'", "'secret': '[REDACTED]'"),
            (r'"secret":\s*"[^"]*"', '"secret": "[REDACTED]"'),
            (r"'key':\s*'[^']*'", "'key': '[REDACTED]'"),
            (r'"key":\s*"[^"]*"', '"key": "[REDACTED]"'),
            (r"'token':\s*'[^']*'", "'token': '[REDACTED]'"),
            (r'"token":\s*"[^"]*"', '"token": "[REDACTED]"'),
            (r"'password':\s*'[^']*'", "'password': '[REDACTED]'"),
            (r'"password":\s*"[^"]*"', '"password": "[REDACTED]"'),
            (r"password:\s*[^,}]+", "password: [REDACTED]"),
            (r"secret:\s*[^,}]+", "secret: [REDACTED]"),
            (r"key:\s*[^,}]+", "key: [REDACTED]"),
            (r"token:\s*[^,}]+", "token: [REDACTED]"),
            (r"api_key:\s*[^,}]+", "api_key: [REDACTED]"),
            (r"access_key:\s*[^,}]+", "access_key: [REDACTED]"),
            (r"[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}", "[CREDIT_CARD_REDACTED]"),
            (r"[0-9]{3}-[0-9]{2}-[0-9]{4}", "[SSN_REDACTED]"),
            (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL_REDACTED]"),
        ]

        sanitized = data_str
        for pattern, replacement in sensitive_patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        # Truncate if too long
        if len(sanitized) > 1000:
            sanitized = sanitized[:997] + "..."

        return sanitized


class SecureLogger:
    """
    Secure logging utilities that prevent sensitive data exposure.

    Provides logging methods that automatically sanitize sensitive data
    and implement secure logging practices.
    """

    def __init__(self, logger_name: str):
        """
        Initialize secure logger.

        Args:
            logger_name: Name of the logger
        """
        self.logger = logging.getLogger(logger_name)
        self.validator = InputValidator()

    def debug(self, message: str, *args, **kwargs) -> None:
        """
        Log debug message with sanitization.

        Args:
            message: Log message
            *args: Message arguments
            **kwargs: Additional keyword arguments
        """
        sanitized_message = self.validator.sanitize_log_data(message)
        sanitized_args = [self.validator.sanitize_log_data(arg) for arg in args]

        # Remove sensitive kwargs
        safe_kwargs = {}
        for key, value in kwargs.items():
            if key.lower() not in ["password", "secret", "key", "token"]:
                safe_kwargs[key] = self.validator.sanitize_log_data(value)
            else:
                safe_kwargs[key] = "[REDACTED]"

        self.logger.debug(sanitized_message, *sanitized_args, **safe_kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        """
        Log info message with sanitization.

        Args:
            message: Log message
            *args: Message arguments
            **kwargs: Additional keyword arguments
        """
        sanitized_message = self.validator.sanitize_log_data(message)
        sanitized_args = [self.validator.sanitize_log_data(arg) for arg in args]

        safe_kwargs = {}
        for key, value in kwargs.items():
            if key.lower() not in ["password", "secret", "key", "token"]:
                safe_kwargs[key] = self.validator.sanitize_log_data(value)
            else:
                safe_kwargs[key] = "[REDACTED]"

        self.logger.info(sanitized_message, *sanitized_args, **safe_kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        """
        Log warning message with sanitization.

        Args:
            message: Log message
            *args: Message arguments
            **kwargs: Additional keyword arguments
        """
        sanitized_message = self.validator.sanitize_log_data(message)
        sanitized_args = [self.validator.sanitize_log_data(arg) for arg in args]

        safe_kwargs = {}
        for key, value in kwargs.items():
            if key.lower() not in ["password", "secret", "key", "token"]:
                safe_kwargs[key] = self.validator.sanitize_log_data(value)
            else:
                safe_kwargs[key] = "[REDACTED]"

        self.logger.warning(sanitized_message, *sanitized_args, **safe_kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        """
        Log error message with sanitization.

        Args:
            message: Log message
            *args: Message arguments
            **kwargs: Additional keyword arguments
        """
        sanitized_message = self.validator.sanitize_log_data(message)
        sanitized_args = [self.validator.sanitize_log_data(arg) for arg in args]

        safe_kwargs = {}
        for key, value in kwargs.items():
            if key.lower() not in ["password", "secret", "key", "token"]:
                safe_kwargs[key] = self.validator.sanitize_log_data(value)
            else:
                safe_kwargs[key] = "[REDACTED]"

        self.logger.error(sanitized_message, *sanitized_args, **safe_kwargs)

    def security_event(
        self, event_type: str, details: Dict[str, Any], severity: str = "INFO"
    ) -> None:
        """
        Log security event with special handling.

        Args:
            event_type: Type of security event
            details: Event details
            severity: Event severity (DEBUG, INFO, WARNING, ERROR)
        """
        # Sanitize details
        sanitized_details = {}
        for key, value in details.items():
            if key.lower() in ["password", "secret", "key", "token", "credential"]:
                sanitized_details[key] = "[REDACTED]"
            else:
                sanitized_details[key] = self.validator.sanitize_log_data(value)

        security_message = f"SECURITY_EVENT: {event_type} - {sanitized_details}"

        # Log at appropriate level
        if severity.upper() == "DEBUG":
            self.logger.debug(security_message)
        elif severity.upper() == "INFO":
            self.logger.info(security_message)
        elif severity.upper() == "WARNING":
            self.logger.warning(security_message)
        elif severity.upper() == "ERROR":
            self.logger.error(security_message)
        else:
            self.logger.info(security_message)


# Global instances for convenience
secure_memory = SecureMemory()
timing_protection = TimingProtection()
input_validator = InputValidator()


# Factory function for secure loggers
def get_secure_logger(name: str) -> SecureLogger:
    """
    Get a secure logger instance.

    Args:
        name: Logger name

    Returns:
        SecureLogger instance
    """
    return SecureLogger(name)
