"""Tests for comprehensive error handling system."""

import asyncio
from datetime import datetime

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from src.awsideman.utils.error_handler import (
    ErrorCategory,
    ErrorContext,
    ErrorSeverity,
    RemediationStep,
    StatusError,
    StatusErrorHandler,
    get_error_handler,
    handle_status_error,
)


class TestErrorContext:
    """Test ErrorContext functionality."""

    def test_error_context_creation(self):
        """Test creating error context with basic information."""
        context = ErrorContext(
            component="TestComponent",
            operation="test_operation",
            user_id="test-user",
            resource_id="test-resource",
        )

        assert context.component == "TestComponent"
        assert context.operation == "test_operation"
        assert context.user_id == "test-user"
        assert context.resource_id == "test-resource"
        assert isinstance(context.timestamp, datetime)
        assert context.additional_context == {}

    def test_error_context_with_additional_context(self):
        """Test error context with additional context information."""
        additional = {"key1": "value1", "key2": 42}
        context = ErrorContext(
            component="TestComponent", operation="test_operation", additional_context=additional
        )

        assert context.additional_context == additional


class TestStatusError:
    """Test StatusError functionality."""

    def test_status_error_creation(self):
        """Test creating a status error with all fields."""
        context = ErrorContext(component="TestComponent", operation="test_op")
        remediation = [
            RemediationStep(
                description="Fix the issue", action_type="manual", command="fix-command"
            )
        ]

        error = StatusError(
            error_id="TEST_001",
            message="Test error message",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            remediation_steps=remediation,
            is_retryable=True,
            retry_after_seconds=30,
        )

        assert error.error_id == "TEST_001"
        assert error.message == "Test error message"
        assert error.category == ErrorCategory.VALIDATION
        assert error.severity == ErrorSeverity.MEDIUM
        assert error.context == context
        assert len(error.remediation_steps) == 1
        assert error.is_retryable is True
        assert error.retry_after_seconds == 30

    def test_get_error_code(self):
        """Test error code generation."""
        context = ErrorContext(component="TestComponent", operation="test_op")
        error = StatusError(
            error_id="TEST_001",
            message="Test message",
            category=ErrorCategory.CONNECTION,
            severity=ErrorSeverity.HIGH,
            context=context,
        )

        assert error.get_error_code() == "CONNECTION_TEST_001"

    def test_get_user_message_with_remediation(self):
        """Test user message generation with remediation steps."""
        context = ErrorContext(component="TestComponent", operation="test_op")
        remediation = [
            RemediationStep(description="Check your configuration", action_type="manual")
        ]

        error = StatusError(
            error_id="TEST_001",
            message="Configuration error",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            remediation_steps=remediation,
        )

        user_message = error.get_user_message()
        assert "Configuration error" in user_message
        assert "Check your configuration" in user_message

    def test_get_user_message_with_retry(self):
        """Test user message generation with retry information."""
        context = ErrorContext(component="TestComponent", operation="test_op")
        error = StatusError(
            error_id="TEST_001",
            message="Temporary error",
            category=ErrorCategory.SERVICE_ERROR,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            is_retryable=True,
            retry_after_seconds=60,
        )

        user_message = error.get_user_message()
        assert "Temporary error" in user_message
        assert "Retry in 60 seconds" in user_message

    def test_get_technical_details(self):
        """Test technical details generation."""
        context = ErrorContext(
            component="TestComponent",
            operation="test_op",
            request_id="req-123",
            resource_id="res-456",
        )

        original_exception = ValueError("Original error")

        error = StatusError(
            error_id="TEST_001",
            message="Test error",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            original_exception=original_exception,
        )

        details = error.get_technical_details()

        assert details["error_id"] == "TEST_001"
        assert details["error_code"] == "VALIDATION_TEST_001"
        assert details["category"] == "validation"
        assert details["severity"] == "medium"
        assert details["component"] == "TestComponent"
        assert details["operation"] == "test_op"
        assert details["request_id"] == "req-123"
        assert details["resource_id"] == "res-456"
        assert details["exception_type"] == "ValueError"
        assert details["exception_message"] == "Original error"


class TestStatusErrorHandler:
    """Test StatusErrorHandler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = StatusErrorHandler()
        self.context = ErrorContext(component="TestComponent", operation="test_operation")

    def test_handle_credentials_error(self):
        """Test handling of AWS credentials errors."""
        exception = NoCredentialsError()

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "CREDS_001"
        assert status_error.category == ErrorCategory.AUTHENTICATION
        assert status_error.severity == ErrorSeverity.CRITICAL
        assert "AWS credentials not found" in status_error.message
        assert not status_error.is_retryable
        assert len(status_error.remediation_steps) > 0
        assert "aws configure" in status_error.remediation_steps[0].command

    def test_handle_connection_error(self):
        """Test handling of connection errors."""
        exception = EndpointConnectionError(endpoint_url="https://sso.amazonaws.com")

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "CONN_001"
        assert status_error.category == ErrorCategory.CONNECTION
        assert status_error.severity == ErrorSeverity.HIGH
        assert "Cannot connect to AWS Identity Center" in status_error.message
        assert status_error.is_retryable
        assert status_error.retry_after_seconds == 30
        assert len(status_error.remediation_steps) > 0

    def test_handle_client_error_access_denied(self):
        """Test handling of access denied client errors."""
        error_response = {
            "Error": {
                "Code": "AccessDenied",
                "Message": "User is not authorized to perform this action",
            },
            "ResponseMetadata": {"RequestId": "req-123"},
        }
        exception = ClientError(error_response, "ListInstances")

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "PERM_001"
        assert status_error.category == ErrorCategory.AUTHORIZATION
        assert status_error.severity == ErrorSeverity.HIGH
        assert "Insufficient permissions" in status_error.message
        assert not status_error.is_retryable
        assert self.context.request_id == "req-123"

    def test_handle_client_error_resource_not_found(self):
        """Test handling of resource not found errors."""
        error_response = {
            "Error": {
                "Code": "ResourceNotFoundException",
                "Message": "The specified resource was not found",
            }
        }
        exception = ClientError(error_response, "DescribeUser")

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "RES_001"
        assert status_error.category == ErrorCategory.RESOURCE_NOT_FOUND
        assert status_error.severity == ErrorSeverity.MEDIUM
        assert "Resource not found" in status_error.message
        assert not status_error.is_retryable

    def test_handle_client_error_throttling(self):
        """Test handling of throttling errors."""
        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        exception = ClientError(error_response, "ListUsers")

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "THROT_001"
        assert status_error.category == ErrorCategory.SERVICE_ERROR
        assert status_error.severity == ErrorSeverity.MEDIUM
        assert "API request throttled" in status_error.message
        assert status_error.is_retryable
        assert status_error.retry_after_seconds == 60

    def test_handle_timeout_error(self):
        """Test handling of timeout errors."""
        exception = asyncio.TimeoutError()

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "TIME_001"
        assert status_error.category == ErrorCategory.TIMEOUT
        assert status_error.severity == ErrorSeverity.MEDIUM
        assert "Operation timed out" in status_error.message
        assert status_error.is_retryable
        assert status_error.retry_after_seconds == 60

    def test_handle_validation_error(self):
        """Test handling of validation errors."""
        exception = ValueError("Invalid parameter value")

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "VAL_001"
        assert status_error.category == ErrorCategory.VALIDATION
        assert status_error.severity == ErrorSeverity.MEDIUM
        assert "Validation error" in status_error.message
        assert not status_error.is_retryable

    def test_handle_key_error(self):
        """Test handling of key errors."""
        exception = KeyError("missing_config_key")

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "KEY_001"
        assert status_error.category == ErrorCategory.CONFIGURATION
        assert status_error.severity == ErrorSeverity.MEDIUM
        assert "Missing required data or configuration" in status_error.message
        assert not status_error.is_retryable

    def test_handle_generic_error(self):
        """Test handling of generic exceptions."""
        exception = RuntimeError("Unexpected runtime error")

        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "GEN_001"
        assert status_error.category == ErrorCategory.INTERNAL
        assert status_error.severity == ErrorSeverity.HIGH
        assert "Unexpected error" in status_error.message
        assert status_error.is_retryable
        assert status_error.retry_after_seconds == 30

    def test_register_custom_error_handler(self):
        """Test registering custom error handlers."""

        class CustomError(Exception):
            pass

        def custom_handler(exception, context):
            return StatusError(
                error_id="CUSTOM_001",
                message="Custom error handled",
                category=ErrorCategory.INTERNAL,
                severity=ErrorSeverity.LOW,
                context=context,
            )

        self.handler.register_error_handler(CustomError, custom_handler)

        exception = CustomError("Test custom error")
        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "CUSTOM_001"
        assert status_error.message == "Custom error handled"
        assert status_error.severity == ErrorSeverity.LOW

    def test_error_handler_failure_fallback(self):
        """Test fallback when error handler itself fails."""

        # Mock a handler that raises an exception
        def failing_handler(exception, context):
            raise RuntimeError("Handler failed")

        self.handler.register_error_handler(ValueError, failing_handler)

        exception = ValueError("Original error")
        status_error = self.handler.handle_error(exception, self.context)

        assert status_error.error_id == "FALL_001"
        assert "Error handler failed" in status_error.message
        assert status_error.severity == ErrorSeverity.CRITICAL
        assert not status_error.is_retryable


class TestGlobalErrorHandler:
    """Test global error handler functions."""

    def test_get_error_handler_singleton(self):
        """Test that get_error_handler returns the same instance."""
        handler1 = get_error_handler()
        handler2 = get_error_handler()

        assert handler1 is handler2

    def test_handle_status_error_convenience_function(self):
        """Test the convenience function for handling errors."""
        exception = ValueError("Test error")

        status_error = handle_status_error(
            exception, component="TestComponent", operation="test_operation", user_id="test-user"
        )

        assert isinstance(status_error, StatusError)
        assert status_error.context.component == "TestComponent"
        assert status_error.context.operation == "test_operation"
        assert status_error.context.additional_context["user_id"] == "test-user"


class TestRemediationStep:
    """Test RemediationStep functionality."""

    def test_remediation_step_creation(self):
        """Test creating remediation steps."""
        step = RemediationStep(
            description="Check configuration file",
            action_type="manual",
            command="cat config.yaml",
            documentation_url="https://docs.example.com/config",
            priority=1,
        )

        assert step.description == "Check configuration file"
        assert step.action_type == "manual"
        assert step.command == "cat config.yaml"
        assert step.documentation_url == "https://docs.example.com/config"
        assert step.priority == 1

    def test_remediation_step_minimal(self):
        """Test creating minimal remediation step."""
        step = RemediationStep(description="Basic remediation", action_type="automatic")

        assert step.description == "Basic remediation"
        assert step.action_type == "automatic"
        assert step.command is None
        assert step.documentation_url is None
        assert step.priority == 1


class TestErrorHandlerIntegration:
    """Integration tests for error handler with real scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = StatusErrorHandler()

    @pytest.mark.asyncio
    async def test_error_handling_in_async_context(self):
        """Test error handling in async operations."""

        async def failing_operation():
            raise asyncio.TimeoutError("Operation timed out")

        context = ErrorContext(component="AsyncComponent", operation="async_operation")

        try:
            await failing_operation()
        except Exception as e:
            status_error = self.handler.handle_error(e, context)

            assert status_error.category == ErrorCategory.TIMEOUT
            assert status_error.is_retryable

    def test_error_chaining_and_context_preservation(self):
        """Test that error context is preserved through error handling."""
        original_context = ErrorContext(
            component="ChainComponent",
            operation="chain_operation",
            user_id="user-123",
            resource_id="resource-456",
            additional_context={"step": "validation"},
        )

        exception = ValueError("Validation failed")
        status_error = self.handler.handle_error(exception, original_context)

        # Verify context preservation
        assert status_error.context.component == "ChainComponent"
        assert status_error.context.operation == "chain_operation"
        assert status_error.context.user_id == "user-123"
        assert status_error.context.resource_id == "resource-456"
        assert status_error.context.additional_context["step"] == "validation"

    def test_multiple_error_scenarios(self):
        """Test handling multiple different error types."""
        test_cases = [
            (NoCredentialsError(), ErrorCategory.AUTHENTICATION),
            (EndpointConnectionError(endpoint_url="test"), ErrorCategory.CONNECTION),
            (asyncio.TimeoutError(), ErrorCategory.TIMEOUT),
            (ValueError("Invalid"), ErrorCategory.VALIDATION),
            (KeyError("missing"), ErrorCategory.CONFIGURATION),
            (RuntimeError("Runtime"), ErrorCategory.INTERNAL),
        ]

        for exception, expected_category in test_cases:
            context = ErrorContext(
                component="MultiTestComponent", operation=f"test_{type(exception).__name__}"
            )

            status_error = self.handler.handle_error(exception, context)
            assert status_error.category == expected_category
            assert len(status_error.remediation_steps) > 0
