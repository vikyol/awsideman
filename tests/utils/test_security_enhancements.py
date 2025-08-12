"""Tests for security enhancements in advanced cache features."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.awsideman.cache.backends.base import CacheBackendError
from src.awsideman.cache.backends.dynamodb import DynamoDBBackend
from src.awsideman.cache.backends.file import FileBackend
from src.awsideman.encryption.aes import AESEncryption
from src.awsideman.encryption.key_manager import FallbackKeyManager
from src.awsideman.encryption.provider import EncryptionError
from src.awsideman.utils.security import (
    SecureLogger,
    SecureMemory,
    get_secure_logger,
    input_validator,
    timing_protection,
)


class TestSecureMemory:
    """Test secure memory handling utilities."""

    def test_secure_memory_availability(self):
        """Test secure memory availability detection."""
        secure_mem = SecureMemory()

        # Should return a boolean
        is_available = secure_mem.is_available()
        assert isinstance(is_available, bool)

    def test_memory_locking(self):
        """Test memory locking functionality."""
        secure_mem = SecureMemory()

        if not secure_mem.is_available():
            pytest.skip("Secure memory not available on this platform")

        test_data = b"sensitive_data_12345"

        # Lock memory
        addr = secure_mem.lock_memory(test_data)

        if addr is not None:
            # Should return an address
            assert isinstance(addr, int)

            # Unlock memory
            result = secure_mem.unlock_memory(addr)
            assert isinstance(result, bool)

    def test_secure_zero(self):
        """Test secure memory zeroing."""
        secure_mem = SecureMemory()

        # Create test data
        test_data = bytearray(b"sensitive_data_12345")
        original_data = bytes(test_data)

        # Secure zero
        secure_mem.secure_zero(test_data)

        # Data should be zeroed
        assert test_data == bytearray(len(original_data))
        assert all(b == 0 for b in test_data)

    def test_secure_zero_non_bytearray(self):
        """Test secure zero with non-bytearray data."""
        secure_mem = SecureMemory()

        # Should handle non-bytearray gracefully
        test_data = b"test_data"
        secure_mem.secure_zero(test_data)  # Should not raise exception

    def test_cleanup(self):
        """Test cleanup of locked memory pages."""
        secure_mem = SecureMemory()

        if not secure_mem.is_available():
            pytest.skip("Secure memory not available on this platform")

        test_data = b"test_data"
        addr = secure_mem.lock_memory(test_data)

        if addr is not None:
            # Cleanup should not raise exception
            secure_mem.cleanup()


class TestTimingProtection:
    """Test timing attack protection utilities."""

    def test_constant_time_compare_equal(self):
        """Test constant time comparison with equal data."""
        data1 = b"test_data_12345"
        data2 = b"test_data_12345"

        result = timing_protection.constant_time_compare(data1, data2)
        assert result is True

    def test_constant_time_compare_different(self):
        """Test constant time comparison with different data."""
        data1 = b"test_data_12345"
        data2 = b"test_data_54321"

        result = timing_protection.constant_time_compare(data1, data2)
        assert result is False

    def test_constant_time_compare_different_lengths(self):
        """Test constant time comparison with different length data."""
        data1 = b"short"
        data2 = b"much_longer_data"

        result = timing_protection.constant_time_compare(data1, data2)
        assert result is False

    def test_constant_time_select(self):
        """Test constant time value selection."""
        true_value = b"true_value"
        false_value = b"false_value"

        # Test true condition
        result = timing_protection.constant_time_select(True, true_value, false_value)
        assert result == true_value

        # Test false condition
        result = timing_protection.constant_time_select(False, true_value, false_value)
        assert result == false_value

    def test_constant_time_select_different_lengths(self):
        """Test constant time selection with different length values."""
        true_value = b"short"
        false_value = b"much_longer_value"

        # Should handle different lengths
        result_true = timing_protection.constant_time_select(True, true_value, false_value)
        result_false = timing_protection.constant_time_select(False, true_value, false_value)

        assert result_true == true_value
        assert result_false == false_value

    def test_timing_jitter(self):
        """Test timing jitter functionality."""
        start_time = time.perf_counter()
        timing_protection.add_timing_jitter(1.0, 2.0)
        end_time = time.perf_counter()

        elapsed_ms = (end_time - start_time) * 1000

        # Should add at least 1ms delay
        assert elapsed_ms >= 1.0
        # Should not add more than reasonable delay (allowing for system variance)
        assert elapsed_ms <= 10.0


class TestInputValidator:
    """Test input validation utilities."""

    def test_validate_cache_key_valid(self):
        """Test cache key validation with valid keys."""
        valid_keys = [
            "simple_key",
            "key-with-dashes",
            "key.with.dots",
            "key/with/slashes",
            "key:with:colons",
            "key123",
            "a" * 255,  # Maximum length
        ]

        for key in valid_keys:
            assert input_validator.validate_cache_key(key), f"Key should be valid: {key}"

    def test_validate_cache_key_invalid(self):
        """Test cache key validation with invalid keys."""
        invalid_keys = [
            "",  # Empty
            None,  # Not a string
            123,  # Not a string
            "key with spaces",  # Spaces not allowed
            "key\\with\\backslashes",  # Backslashes not allowed
            "../path/traversal",  # Path traversal
            "/absolute/path",  # Absolute path
            "key..with..dots",  # Double dots
            "a" * 256,  # Too long
            "key\x00null",  # Null byte
            "key\nnewline",  # Newline
        ]

        for key in invalid_keys:
            assert not input_validator.validate_cache_key(key), f"Key should be invalid: {key}"

    def test_sanitize_cache_key(self):
        """Test cache key sanitization."""
        test_cases = [
            ("simple_key", "simple_key"),
            ("key with spaces", "key_with_spaces"),
            ("key\\with\\backslashes", "key_with_backslashes"),
            ("../path/traversal", "_/path/traversal"),  # Fixed expectation
            ("/absolute/path", "absolute/path"),
            ("key..with..dots", "key_with_dots"),
            ("", "default_key"),
            ("a" * 300, "a" * 255),  # Truncated
        ]

        for input_key, expected in test_cases:
            result = input_validator.sanitize_cache_key(input_key)
            assert (
                result == expected
            ), f"Sanitization failed for {input_key}: got {result}, expected {expected}"

    def test_validate_aws_arn(self):
        """Test AWS ARN validation."""
        valid_arns = [
            "arn:aws:iam::123456789012:role/MyRole",
            "arn:aws:s3:::my-bucket",
            "arn:aws:sso:::permissionSet/ssoins-1234567890abcdef/ps-1234567890abcdef",
        ]

        invalid_arns = [
            "not-an-arn",
            "arn:aws:invalid",
            "",
            None,
            123,
        ]

        for arn in valid_arns:
            assert input_validator.validate_aws_arn(arn), f"ARN should be valid: {arn}"

        for arn in invalid_arns:
            assert not input_validator.validate_aws_arn(arn), f"ARN should be invalid: {arn}"

    def test_validate_aws_account_id(self):
        """Test AWS account ID validation."""
        valid_ids = ["123456789012", "000000000000", "999999999999"]
        invalid_ids = ["12345678901", "1234567890123", "abc123456789", "", None, 123]

        for account_id in valid_ids:
            assert input_validator.validate_aws_account_id(
                account_id
            ), f"Account ID should be valid: {account_id}"

        for account_id in invalid_ids:
            assert not input_validator.validate_aws_account_id(
                account_id
            ), f"Account ID should be invalid: {account_id}"

    def test_validate_uuid(self):
        """Test UUID validation."""
        valid_uuids = [
            "123e4567-e89b-12d3-a456-426614174000",
            "00000000-0000-0000-0000-000000000000",
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
        ]

        invalid_uuids = [
            "not-a-uuid",
            "123e4567-e89b-12d3-a456",  # Too short
            "123e4567-e89b-12d3-a456-426614174000-extra",  # Too long
            "",
            None,
            123,
        ]

        for uuid_str in valid_uuids:
            assert input_validator.validate_uuid(uuid_str), f"UUID should be valid: {uuid_str}"

        for uuid_str in invalid_uuids:
            assert not input_validator.validate_uuid(
                uuid_str
            ), f"UUID should be invalid: {uuid_str}"

    def test_validate_email(self):
        """Test email validation."""
        valid_emails = [
            "user@example.com",
            "test.email+tag@domain.co.uk",
            "user123@test-domain.org",
        ]

        invalid_emails = [
            "not-an-email",
            "@domain.com",  # Missing local part
            "user@",  # Missing domain
            "user@domain",  # Missing TLD
            "",
            None,
            123,
        ]

        for email in valid_emails:
            assert input_validator.validate_email(email), f"Email should be valid: {email}"

        for email in invalid_emails:
            assert not input_validator.validate_email(email), f"Email should be invalid: {email}"

    def test_validate_file_path(self):
        """Test file path validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            allowed_dirs = [temp_dir]

            # Valid paths
            valid_path = os.path.join(temp_dir, "test_file.txt")
            assert input_validator.validate_file_path(valid_path, allowed_dirs)

            # Invalid paths
            invalid_paths = [
                "/etc/passwd",  # Outside allowed dirs
                "../../../etc/passwd",  # Path traversal
                None,  # Not a string
                123,  # Not a string
            ]

            for path in invalid_paths:
                assert not input_validator.validate_file_path(
                    path, allowed_dirs
                ), f"Path should be invalid: {path}"

    def test_sanitize_log_data(self):
        """Test log data sanitization."""
        test_cases = [
            ("normal data", "normal data"),
            ({"password": "secret123"}, "'password': '[REDACTED]'"),  # Fixed expectation
            ({"api_key": "sk-1234567890"}, "'api_key': '[REDACTED]'"),  # Fixed expectation
            ("Credit card: 4111-1111-1111-1111", "Credit card: [CREDIT_CARD_REDACTED]"),
            ("SSN: 123-45-6789", "SSN: [SSN_REDACTED]"),
            ("Email: user@example.com", "Email: [EMAIL_REDACTED]"),
            (None, "None"),
            ("x" * 2000, "x" * 997 + "..."),  # Truncated
        ]

        for input_data, expected in test_cases:
            result = input_validator.sanitize_log_data(input_data)
            assert expected in result, f"Sanitization failed for {input_data}: got {result}"


class TestSecureLogger:
    """Test secure logging utilities."""

    def test_secure_logger_creation(self):
        """Test secure logger creation."""
        logger = get_secure_logger("test_logger")
        assert isinstance(logger, SecureLogger)
        assert logger.logger.name == "test_logger"

    def test_secure_logging_methods(self):
        """Test secure logging methods."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            secure_logger = SecureLogger("test")

            # Test each logging method
            secure_logger.debug("test message", "arg1", sensitive_key="secret")
            secure_logger.info("test message", "arg1", sensitive_key="secret")
            secure_logger.warning("test message", "arg1", sensitive_key="secret")
            secure_logger.error("test message", "arg1", sensitive_key="secret")

            # Verify methods were called
            assert mock_logger.debug.called
            assert mock_logger.info.called
            assert mock_logger.warning.called
            assert mock_logger.error.called

    def test_security_event_logging(self):
        """Test security event logging."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            secure_logger = SecureLogger("test")

            # Test security event logging
            secure_logger.security_event(
                "test_event", {"key": "value", "password": "secret"}, "INFO"
            )

            # Verify info method was called
            assert mock_logger.info.called

            # Check that password was redacted
            call_args = mock_logger.info.call_args[0][0]
            assert "[REDACTED]" in call_args
            assert "secret" not in call_args


class TestAESEncryptionSecurity:
    """Test AES encryption security enhancements."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        self.encryption = AESEncryption(self.key_manager)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_encryption_with_security_logging(self):
        """Test that encryption operations are logged securely."""
        test_data = {"test": "data", "password": "secret123"}

        with patch("src.awsideman.encryption.aes.logger") as mock_logger:
            # Create new encryption instance to use mocked logger
            encryption = AESEncryption(self.key_manager)

            # Encrypt data
            encryption.encrypt(test_data)

            # Verify security event was logged
            assert mock_logger.security_event.called

            # Check that sensitive data was not logged
            call_args = mock_logger.security_event.call_args
            assert "secret123" not in str(call_args)

    def test_decryption_timing_protection(self):
        """Test that decryption includes timing protection."""
        test_data = {"test": "data"}

        # Encrypt data
        encrypted = self.encryption.encrypt(test_data)

        # Measure decryption times
        times = []
        for _ in range(5):
            start = time.perf_counter()
            result = self.encryption.decrypt(encrypted)
            end = time.perf_counter()
            times.append(end - start)
            assert result == test_data

        # All times should be reasonably similar (timing jitter adds consistency)
        avg_time = sum(times) / len(times)
        for t in times:
            # Allow for reasonable variance
            assert abs(t - avg_time) / avg_time < 0.5, "Timing variance too high"

    def test_decryption_error_timing_consistency(self):
        """Test that decryption errors have consistent timing."""
        # Test with various invalid data
        invalid_data_samples = [
            b"too_short",
            b"x" * 16,  # Only IV, no content
            b"x" * 32,  # Invalid encrypted content
            os.urandom(64),  # Random data
        ]

        times = []
        for invalid_data in invalid_data_samples:
            start = time.perf_counter()
            try:
                self.encryption.decrypt(invalid_data)
            except EncryptionError:
                pass  # Expected
            end = time.perf_counter()
            times.append(end - start)

        # Error handling times should be reasonably consistent
        if len(times) > 1:
            avg_time = sum(times) / len(times)
            for t in times:
                # Allow for reasonable variance in error timing
                assert abs(t - avg_time) / avg_time < 1.0, "Error timing variance too high"


class TestCacheBackendSecurity:
    """Test cache backend security enhancements."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_backend_input_validation(self):
        """Test file backend input validation."""
        backend = FileBackend(self.temp_dir)

        # Test invalid cache keys
        invalid_keys = ["../traversal", "key with spaces", ""]

        for key in invalid_keys:
            with pytest.raises(CacheBackendError):
                backend.get(key)

            with pytest.raises(CacheBackendError):
                backend.set(key, b"test_data")

    def test_file_backend_data_validation(self):
        """Test file backend data validation."""
        backend = FileBackend(self.temp_dir)

        # Test invalid data types
        with pytest.raises(CacheBackendError):
            backend.set("valid_key", "not_bytes")  # Should be bytes

        # Test invalid TTL
        with pytest.raises(CacheBackendError):
            backend.set("valid_key", b"test_data", ttl=-1)  # Negative TTL

        with pytest.raises(CacheBackendError):
            backend.set("valid_key", b"test_data", ttl="invalid")  # Non-integer TTL

    @patch("boto3.resource")
    @patch("boto3.Session")
    def test_dynamodb_backend_input_validation(self, mock_session, mock_resource):
        """Test DynamoDB backend input validation."""
        # Mock DynamoDB resources
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.load.return_value = None

        backend = DynamoDBBackend("test-table", "us-east-1")

        # Test invalid cache keys
        invalid_keys = ["../traversal", "key with spaces", ""]

        for key in invalid_keys:
            with pytest.raises(CacheBackendError):
                backend.get(key)

            with pytest.raises(CacheBackendError):
                backend.set(key, b"test_data")

    @patch("boto3.resource")
    @patch("boto3.Session")
    def test_dynamodb_backend_data_validation(self, mock_session, mock_resource):
        """Test DynamoDB backend data validation."""
        # Mock DynamoDB resources
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        mock_table.load.return_value = None

        backend = DynamoDBBackend("test-table", "us-east-1")

        # Test invalid data types
        with pytest.raises(CacheBackendError):
            backend.set("valid_key", "not_bytes")  # Should be bytes

        # Test invalid TTL
        with pytest.raises(CacheBackendError):
            backend.set("valid_key", b"test_data", ttl=-1)  # Negative TTL


class TestSecurityIntegration:
    """Test integration of security features."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_security(self):
        """Test end-to-end security with all features enabled."""
        # Create secure components
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = AESEncryption(key_manager)
        backend = FileBackend(self.temp_dir)

        # Test data with sensitive information
        sensitive_data = {
            "user": "test_user",
            "credentials": {"password": "super_secret_password", "api_key": "sk-1234567890abcdef"},
            "personal_info": {"email": "user@example.com", "ssn": "123-45-6789"},
        }

        # Encrypt data
        encrypted_data = encryption.encrypt(sensitive_data)

        # Store in backend
        cache_key = "secure_test_key"
        backend.set(cache_key, encrypted_data, ttl=3600, operation="security_test")

        # Retrieve and decrypt
        retrieved_data = backend.get(cache_key)
        assert retrieved_data is not None

        decrypted_data = encryption.decrypt(retrieved_data)
        assert decrypted_data == sensitive_data

        # Verify no sensitive data in cache files
        cache_files = list(Path(self.temp_dir).rglob("*.json"))
        for cache_file in cache_files:
            with open(cache_file, "rb") as f:
                file_content = f.read()

            # Sensitive data should not appear in plaintext
            assert b"super_secret_password" not in file_content
            assert b"sk-1234567890abcdef" not in file_content
            assert b"123-45-6789" not in file_content

    def test_security_under_error_conditions(self):
        """Test security behavior under error conditions."""
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = AESEncryption(key_manager)

        # Test with corrupted data
        corrupted_data = b"corrupted_encrypted_data"

        with pytest.raises(EncryptionError):
            encryption.decrypt(corrupted_data)

        # Test with invalid cache keys
        backend = FileBackend(self.temp_dir)

        with pytest.raises(CacheBackendError):
            backend.get("../invalid/key")

        with pytest.raises(CacheBackendError):
            backend.set("../invalid/key", b"data")

    def test_concurrent_security_operations(self):
        """Test security under concurrent operations."""
        import threading

        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = AESEncryption(key_manager)
        backend = FileBackend(self.temp_dir)

        results = []
        errors = []

        def worker(worker_id):
            try:
                # Each worker encrypts and stores its own data
                data = {"worker": worker_id, "secret": f"secret_{worker_id}"}
                encrypted = encryption.encrypt(data)
                key = f"worker_{worker_id}"

                backend.set(key, encrypted, ttl=3600, operation=f"worker_{worker_id}")

                # Retrieve and verify
                retrieved = backend.get(key)
                decrypted = encryption.decrypt(retrieved)

                if decrypted == data:
                    results.append(worker_id)
                else:
                    errors.append(f"Data mismatch for worker {worker_id}")

            except Exception as e:
                errors.append(f"Worker {worker_id} error: {e}")

        # Run concurrent workers
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All workers should succeed
        assert len(results) == 5, f"Some workers failed: {errors}"
        assert len(errors) == 0, f"Unexpected errors: {errors}"
