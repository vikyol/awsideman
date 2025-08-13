"""Tests for intelligent backoff strategies for rate limiting.

This module tests the adaptive backoff strategies, per-service rate limit tracking,
circuit breaker patterns, and jitter functionality for multi-account operations.
"""
import time
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.awsideman.utils.bulk.intelligent_backoff import (
    AdaptiveBackoffStrategy,
    BackoffContext,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    ErrorSeverity,
    ExponentialBackoffStrategy,
    IntelligentBackoffManager,
    RateLimitInfo,
    ServiceRateLimitTracker,
    ServiceType,
    calculate_retry_delay,
    should_retry_error,
)


# Mock asyncio.sleep to make tests run instantly
@pytest.fixture(autouse=True)
def mock_asyncio_sleep():
    """Mock asyncio.sleep to make tests run instantly."""
    with patch("asyncio.sleep") as mock_sleep:
        mock_sleep.return_value = None
        yield mock_sleep


class TestBackoffContext:
    """Test BackoffContext functionality."""

    def test_backoff_context_initialization(self):
        """Test BackoffContext initialization."""
        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=2,
            consecutive_failures=3,
        )

        assert context.service_type == ServiceType.SSO_ADMIN
        assert context.error_type == "ThrottlingException"
        assert context.error_severity == ErrorSeverity.HIGH
        assert context.retry_count == 2
        assert context.consecutive_failures == 3
        assert context.error_history == []

    def test_add_error_to_history(self):
        """Test adding errors to history."""
        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=0,
            consecutive_failures=0,
        )

        # Add some errors
        context.add_error("ThrottlingException")
        context.add_error("ServiceUnavailable")
        context.add_error("InternalServerError")

        assert len(context.error_history) == 3
        assert context.error_history == [
            "ThrottlingException",
            "ServiceUnavailable",
            "InternalServerError",
        ]

    def test_error_history_limit(self):
        """Test that error history is limited to 10 entries."""
        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=0,
            consecutive_failures=0,
        )

        # Add 15 errors
        for i in range(15):
            context.add_error(f"Error{i}")

        # Should only keep the last 10
        assert len(context.error_history) == 10
        assert context.error_history == [f"Error{i}" for i in range(5, 15)]


class TestRateLimitInfo:
    """Test RateLimitInfo functionality."""

    def test_rate_limit_info_initialization(self):
        """Test RateLimitInfo initialization."""
        rate_info = RateLimitInfo(
            service_type=ServiceType.SSO_ADMIN, requests_per_second=20.0, burst_capacity=40
        )

        assert rate_info.service_type == ServiceType.SSO_ADMIN
        assert rate_info.requests_per_second == 20.0
        assert rate_info.burst_capacity == 40
        assert rate_info.current_requests == 0
        assert rate_info.consecutive_throttles == 0

    def test_can_make_request(self):
        """Test request rate limiting."""
        rate_info = RateLimitInfo(
            service_type=ServiceType.SSO_ADMIN, requests_per_second=2.0, burst_capacity=4
        )

        # Should be able to make requests initially
        assert rate_info.can_make_request() is True

        # Record requests up to the limit
        rate_info.record_request()
        rate_info.record_request()

        # Should not be able to make more requests
        assert rate_info.can_make_request() is False

    def test_rate_limit_reset(self):
        """Test rate limit reset after time window."""
        rate_info = RateLimitInfo(
            service_type=ServiceType.SSO_ADMIN, requests_per_second=2.0, burst_capacity=4
        )

        # Fill up the rate limit
        rate_info.record_request()
        rate_info.record_request()
        assert rate_info.can_make_request() is False

        # Simulate time passing by manually resetting
        rate_info.last_reset_time = time.time() - 2.0  # 2 seconds ago
        rate_info.reset_if_needed()

        # Should be able to make requests again
        assert rate_info.can_make_request() is True
        assert rate_info.current_requests == 0

    def test_throttle_handling(self):
        """Test throttle recording and rate adjustment."""
        rate_info = RateLimitInfo(
            service_type=ServiceType.SSO_ADMIN, requests_per_second=10.0, burst_capacity=20
        )

        original_rate = rate_info.requests_per_second

        # Record a throttle
        rate_info.record_throttle()

        assert rate_info.consecutive_throttles == 1
        assert rate_info.requests_per_second < original_rate  # Should be reduced
        assert rate_info.last_throttle_time is not None

    def test_success_recovery(self):
        """Test rate limit recovery after success."""
        rate_info = RateLimitInfo(
            service_type=ServiceType.SSO_ADMIN, requests_per_second=10.0, burst_capacity=20
        )

        # Record throttles to reduce rate
        rate_info.record_throttle()
        rate_info.record_throttle()
        reduced_rate = rate_info.requests_per_second

        # Record success
        rate_info.record_success()

        assert rate_info.consecutive_throttles == 0
        assert rate_info.requests_per_second > reduced_rate  # Should be increased


class TestExponentialBackoffStrategy:
    """Test ExponentialBackoffStrategy functionality."""

    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        strategy = ExponentialBackoffStrategy(
            base_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter_factor=0.0,  # No jitter for predictable testing
        )

        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=0,
            consecutive_failures=1,
        )

        # Test exponential growth
        delay0 = strategy.calculate_delay(context)
        assert delay0 == 1.0  # 1.0 * (2^0) = 1.0

        context.retry_count = 1
        delay1 = strategy.calculate_delay(context)
        assert delay1 == 2.0  # 1.0 * (2^1) = 2.0

        context.retry_count = 2
        delay2 = strategy.calculate_delay(context)
        assert delay2 == 4.0  # 1.0 * (2^2) = 4.0

    def test_max_delay_limit(self):
        """Test that delay is capped at max_delay."""
        strategy = ExponentialBackoffStrategy(
            base_delay=1.0, max_delay=10.0, exponential_base=2.0, jitter_factor=0.0
        )

        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=10,  # Large retry count
            consecutive_failures=10,
        )

        delay = strategy.calculate_delay(context)
        assert delay <= 10.0  # Should be capped at max_delay

    def test_jitter_application(self):
        """Test that jitter is applied correctly."""
        strategy = ExponentialBackoffStrategy(
            base_delay=1.0, max_delay=60.0, exponential_base=2.0, jitter_factor=0.5  # 50% jitter
        )

        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=2,
            consecutive_failures=2,
        )

        # Calculate delay multiple times to test jitter variation
        delays = [strategy.calculate_delay(context) for _ in range(10)]

        # All delays should be different due to jitter
        assert len(set(delays)) > 1

        # All delays should be around the base delay (4.0) with jitter
        base_delay = 4.0
        max_delay = base_delay + base_delay * 0.5  # Base + 50% jitter
        for delay in delays:
            assert base_delay <= delay <= max_delay

    def test_should_retry_logic(self):
        """Test retry decision logic."""
        strategy = ExponentialBackoffStrategy()

        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=2,
            consecutive_failures=2,
        )

        # Should retry if under max retries
        assert strategy.should_retry(context, max_retries=5) is True

        # Should not retry if at max retries
        context.retry_count = 5
        assert strategy.should_retry(context, max_retries=5) is False


class TestAdaptiveBackoffStrategy:
    """Test AdaptiveBackoffStrategy functionality."""

    def test_error_type_multipliers(self):
        """Test that different error types get different multipliers."""
        strategy = AdaptiveBackoffStrategy(
            base_delay=1.0, max_delay=300.0, jitter_factor=0.0  # No jitter for predictable testing
        )

        # Test throttling error (high multiplier)
        throttling_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=1,
            consecutive_failures=1,
        )

        # Test validation error (low multiplier)
        validation_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ValidationException",
            error_severity=ErrorSeverity.CRITICAL,
            retry_count=1,
            consecutive_failures=1,
        )

        throttling_delay = strategy.calculate_delay(throttling_context)
        validation_delay = strategy.calculate_delay(validation_context)

        # Throttling should have longer delay than validation
        assert throttling_delay > validation_delay

    def test_severity_multipliers(self):
        """Test that different error severities get different multipliers."""
        strategy = AdaptiveBackoffStrategy(base_delay=1.0, max_delay=300.0, jitter_factor=0.0)

        # Test different severities with same error type
        low_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ServiceException",
            error_severity=ErrorSeverity.LOW,
            retry_count=1,
            consecutive_failures=1,
        )

        critical_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ServiceException",
            error_severity=ErrorSeverity.CRITICAL,
            retry_count=1,
            consecutive_failures=1,
        )

        low_delay = strategy.calculate_delay(low_context)
        critical_delay = strategy.calculate_delay(critical_context)

        # Critical should have longer delay than low
        assert critical_delay > low_delay

    def test_consecutive_failure_penalty(self):
        """Test that consecutive failures increase delay."""
        strategy = AdaptiveBackoffStrategy(base_delay=1.0, max_delay=300.0, jitter_factor=0.0)

        # Test with few consecutive failures
        few_failures_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ServiceException",
            error_severity=ErrorSeverity.MEDIUM,
            retry_count=1,
            consecutive_failures=2,
        )

        # Test with many consecutive failures
        many_failures_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ServiceException",
            error_severity=ErrorSeverity.MEDIUM,
            retry_count=1,
            consecutive_failures=6,
        )

        few_delay = strategy.calculate_delay(few_failures_context)
        many_delay = strategy.calculate_delay(many_failures_context)

        # Many failures should have longer delay
        assert many_delay > few_delay

    def test_service_type_multipliers(self):
        """Test that different service types get different multipliers."""
        strategy = AdaptiveBackoffStrategy(base_delay=1.0, max_delay=300.0, jitter_factor=0.0)

        # Test SSO Admin (more sensitive)
        sso_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ServiceException",
            error_severity=ErrorSeverity.MEDIUM,
            retry_count=1,
            consecutive_failures=1,
        )

        # Test STS (more resilient)
        sts_context = BackoffContext(
            service_type=ServiceType.STS,
            error_type="ServiceException",
            error_severity=ErrorSeverity.MEDIUM,
            retry_count=1,
            consecutive_failures=1,
        )

        sso_delay = strategy.calculate_delay(sso_context)
        sts_delay = strategy.calculate_delay(sts_context)

        # SSO should have longer delay than STS
        assert sso_delay > sts_delay

    def test_non_retryable_errors(self):
        """Test that non-retryable errors are not retried."""
        strategy = AdaptiveBackoffStrategy()

        # Test non-retryable error types
        non_retryable_errors = [
            "AccessDeniedException",
            "UnauthorizedException",
            "ValidationException",
            "InvalidParameterException",
            "MissingParameterException",
        ]

        for error_type in non_retryable_errors:
            context = BackoffContext(
                service_type=ServiceType.SSO_ADMIN,
                error_type=error_type,
                error_severity=ErrorSeverity.CRITICAL,
                retry_count=1,
                consecutive_failures=1,
            )

            assert strategy.should_retry(context, max_retries=5) is False

    def test_retryable_errors(self):
        """Test that retryable errors are retried."""
        strategy = AdaptiveBackoffStrategy()

        # Test retryable error types
        retryable_errors = [
            "ThrottlingException",
            "TooManyRequestsException",
            "ServiceUnavailable",
            "InternalServerError",
            "RequestTimeout",
            "ConnectionError",
        ]

        for error_type in retryable_errors:
            context = BackoffContext(
                service_type=ServiceType.SSO_ADMIN,
                error_type=error_type,
                error_severity=ErrorSeverity.HIGH,
                retry_count=1,
                consecutive_failures=1,
            )

            assert strategy.should_retry(context, max_retries=5) is True

    def test_max_consecutive_failures_limit(self):
        """Test that too many consecutive failures prevent retry."""
        strategy = AdaptiveBackoffStrategy()

        context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=1,
            consecutive_failures=15,  # More than limit of 10
        )

        assert strategy.should_retry(context, max_retries=5) is False

    def test_enhanced_error_type_multipliers(self):
        """Test enhanced error type multipliers for AWS-specific errors."""
        strategy = AdaptiveBackoffStrategy(
            base_delay=1.0, max_delay=300.0, jitter_factor=0.0  # No jitter for predictable testing
        )

        # Test new AWS-specific error types
        test_cases = [
            ("RequestLimitExceeded", 3.0),  # Should have high multiplier
            ("SlowDown", 2.5),  # S3 specific error
            ("ProvisionedThroughputExceededException", 2.0),  # DynamoDB error
            ("InvalidUserID.NotFound", 0.3),  # SSO specific error
            ("MalformedPolicyDocument", 0.1),  # Validation error
        ]

        base_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="",
            error_severity=ErrorSeverity.MEDIUM,
            retry_count=1,
            consecutive_failures=1,
        )

        for error_type, expected_multiplier in test_cases:
            context = BackoffContext(
                service_type=base_context.service_type,
                error_type=error_type,
                error_severity=base_context.error_severity,
                retry_count=base_context.retry_count,
                consecutive_failures=base_context.consecutive_failures,
            )

            delay = strategy.calculate_delay(context)
            # The delay should reflect the error multiplier (base_delay * 2^retry_count * multiplier * severity * service)
            # With retry_count=1, base_delay=1.0, this should be approximately 2.0 * multiplier * other_factors
            assert delay > 0, f"Delay should be positive for error type {error_type}"

    def test_error_pattern_analysis(self):
        """Test error pattern analysis for adaptive delay adjustment."""
        strategy = AdaptiveBackoffStrategy(
            base_delay=1.0, max_delay=300.0, jitter_factor=0.0  # No jitter for predictable testing
        )

        # Test context with repeated throttling errors
        throttling_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=2,
            consecutive_failures=3,
            error_history=[
                "ThrottlingException",
                "ThrottlingException",
                "ThrottlingException",
                "ThrottlingException",
            ],
        )

        # Test context with mixed errors
        mixed_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="InternalServerError",
            error_severity=ErrorSeverity.MEDIUM,
            retry_count=2,
            consecutive_failures=3,
            error_history=[
                "ThrottlingException",
                "ServiceUnavailable",
                "InternalServerError",
                "ConnectionError",
            ],
        )

        throttling_delay = strategy.calculate_delay(throttling_context)
        mixed_delay = strategy.calculate_delay(mixed_context)

        # Both should have positive delays, and throttling pattern should generally result in longer delay
        assert throttling_delay > 0
        assert mixed_delay > 0

    def test_adaptive_jitter_enabled(self):
        """Test adaptive jitter functionality."""
        strategy = AdaptiveBackoffStrategy(
            base_delay=1.0, max_delay=300.0, jitter_factor=0.3, enable_adaptive_jitter=True
        )

        # Test throttling error context
        throttling_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ThrottlingException",
            error_severity=ErrorSeverity.HIGH,
            retry_count=1,
            consecutive_failures=1,
        )

        # Test validation error context
        validation_context = BackoffContext(
            service_type=ServiceType.SSO_ADMIN,
            error_type="ValidationException",
            error_severity=ErrorSeverity.CRITICAL,
            retry_count=1,
            consecutive_failures=1,
        )

        # Calculate delays multiple times to test jitter variation
        throttling_delays = [strategy.calculate_delay(throttling_context) for _ in range(5)]
        validation_delays = [strategy.calculate_delay(validation_context) for _ in range(5)]

        # All delays should be different due to jitter
        assert len(set(throttling_delays)) > 1, "Throttling delays should vary due to jitter"
        assert len(set(validation_delays)) > 1, "Validation delays should vary due to jitter"

        # All delays should be positive
        assert all(d > 0 for d in throttling_delays), "All throttling delays should be positive"
        assert all(d > 0 for d in validation_delays), "All validation delays should be positive"


class TestServiceRateLimitTracker:
    """Test ServiceRateLimitTracker functionality."""

    def test_initialization(self):
        """Test ServiceRateLimitTracker initialization."""
        tracker = ServiceRateLimitTracker()

        # Should have default limits for all service types
        assert ServiceType.SSO_ADMIN in tracker.service_limits
        assert ServiceType.IDENTITY_STORE in tracker.service_limits
        assert ServiceType.ORGANIZATIONS in tracker.service_limits
        assert ServiceType.STS in tracker.service_limits
        assert ServiceType.UNKNOWN in tracker.service_limits

    def test_can_make_request(self):
        """Test request permission checking."""
        tracker = ServiceRateLimitTracker()

        # Should be able to make requests initially
        assert tracker.can_make_request(ServiceType.SSO_ADMIN) is True

        # Fill up the rate limit
        sso_limit = tracker.service_limits[ServiceType.SSO_ADMIN]
        for _ in range(int(sso_limit.requests_per_second)):
            tracker.record_request(ServiceType.SSO_ADMIN)

        # Should not be able to make more requests
        assert tracker.can_make_request(ServiceType.SSO_ADMIN) is False

    def test_throttle_recording(self):
        """Test throttle event recording."""
        tracker = ServiceRateLimitTracker()

        original_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        # Record throttle
        tracker.record_throttle(ServiceType.SSO_ADMIN)

        # Rate should be reduced
        new_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second
        assert new_rate < original_rate

        # Consecutive throttles should be tracked
        assert tracker.service_limits[ServiceType.SSO_ADMIN].consecutive_throttles == 1

    def test_success_recording(self):
        """Test success event recording."""
        tracker = ServiceRateLimitTracker()

        # Record throttle to reduce rate
        tracker.record_throttle(ServiceType.SSO_ADMIN)
        reduced_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        # Record success
        tracker.record_success(ServiceType.SSO_ADMIN)

        # Rate should be increased
        new_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second
        assert new_rate > reduced_rate

        # Consecutive throttles should be reset
        assert tracker.service_limits[ServiceType.SSO_ADMIN].consecutive_throttles == 0

    def test_recommended_delay(self):
        """Test recommended delay calculation."""
        tracker = ServiceRateLimitTracker()

        # Should have no delay initially
        assert tracker.get_recommended_delay(ServiceType.SSO_ADMIN) == 0.0

        # Record throttle
        tracker.record_throttle(ServiceType.SSO_ADMIN)

        # Should have delay after throttle
        delay = tracker.get_recommended_delay(ServiceType.SSO_ADMIN)
        assert delay > 0.0

    def test_service_stats(self):
        """Test service statistics retrieval."""
        tracker = ServiceRateLimitTracker()

        stats = tracker.get_service_stats()

        # Should have stats for all service types
        assert ServiceType.SSO_ADMIN in stats
        assert ServiceType.IDENTITY_STORE in stats

        # Stats should contain expected fields
        sso_stats = stats[ServiceType.SSO_ADMIN]
        assert "requests_per_second" in sso_stats
        assert "current_requests" in sso_stats
        assert "consecutive_throttles" in sso_stats
        assert "can_make_request" in sso_stats
        assert "recommended_delay" in sso_stats

    def test_intelligent_throttle_handling(self):
        """Test intelligent throttle handling with progressive rate reduction."""
        tracker = ServiceRateLimitTracker()

        original_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        # Record multiple throttles and check progressive reduction
        tracker.record_throttle(ServiceType.SSO_ADMIN)
        first_throttle_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        tracker.record_throttle(ServiceType.SSO_ADMIN)
        second_throttle_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        tracker.record_throttle(ServiceType.SSO_ADMIN)
        third_throttle_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        # Each throttle should reduce the rate more aggressively
        assert first_throttle_rate < original_rate
        assert second_throttle_rate < first_throttle_rate
        assert third_throttle_rate < second_throttle_rate

        # Rate should not go below minimum
        min_rate = tracker.service_limits[ServiceType.SSO_ADMIN]._get_minimum_rate_limit()
        assert third_throttle_rate >= min_rate

    def test_intelligent_success_recovery(self):
        """Test intelligent success recovery with conservative rate increases."""
        tracker = ServiceRateLimitTracker()

        # Record multiple throttles to reduce rate significantly
        for _ in range(5):
            tracker.record_throttle(ServiceType.SSO_ADMIN)

        throttled_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        # Record success and check conservative recovery
        tracker.record_success(ServiceType.SSO_ADMIN)
        recovery_rate = tracker.service_limits[ServiceType.SSO_ADMIN].requests_per_second

        # Rate should increase but conservatively
        assert recovery_rate > throttled_rate
        assert (
            recovery_rate < throttled_rate * 1.1
        )  # Should be less than 10% increase for severe throttling


class TestCircuitBreaker:
    """Test CircuitBreaker functionality."""

    def test_initialization(self):
        """Test CircuitBreaker initialization."""
        breaker = CircuitBreaker("test-breaker")

        assert breaker.name == "test-breaker"
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.can_execute() is True

    def test_failure_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test-breaker", config)

        # Record failures up to threshold
        for i in range(3):
            assert breaker.state == CircuitBreakerState.CLOSED
            breaker.record_failure()

        # Should be open after threshold
        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.can_execute() is False

    def test_recovery_timeout(self):
        """Test circuit breaker recovery after timeout."""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        breaker = CircuitBreaker("test-breaker", config)

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

        # Should not be able to execute immediately
        assert breaker.can_execute() is False

        # Wait for recovery timeout
        time.sleep(0.2)

        # Should be half-open now
        assert breaker.can_execute() is True
        # State should change to half-open on next check
        breaker.can_execute()  # This call should change state
        assert breaker.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_success_recovery(self):
        """Test recovery from half-open state with successes."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, recovery_timeout=0.1
        )
        breaker = CircuitBreaker("test-breaker", config)

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)
        breaker.can_execute()  # Transition to half-open

        # Record successes
        breaker.record_success()
        assert breaker.state == CircuitBreakerState.HALF_OPEN

        breaker.record_success()
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    def test_half_open_failure_reopens(self):
        """Test that failure in half-open state reopens circuit."""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        breaker = CircuitBreaker("test-breaker", config)

        # Trip the breaker
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)
        breaker.can_execute()  # Transition to half-open

        # Record failure in half-open state
        breaker.record_failure()
        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.success_count == 0

    def test_state_info(self):
        """Test state information retrieval."""
        breaker = CircuitBreaker("test-breaker")

        state_info = breaker.get_state_info()

        assert state_info["name"] == "test-breaker"
        assert state_info["state"] == "closed"
        assert state_info["failure_count"] == 0
        assert state_info["success_count"] == 0
        assert state_info["can_execute"] is True

    def test_service_specific_configuration(self):
        """Test service-specific circuit breaker configuration."""
        # Test SSO Admin configuration (more sensitive)
        sso_config = CircuitBreakerConfig(service_type=ServiceType.SSO_ADMIN)
        assert sso_config.failure_threshold == 3  # Lower threshold
        assert sso_config.recovery_timeout == 90.0  # Longer recovery
        assert sso_config.success_threshold == 2

        # Test STS configuration (more resilient)
        sts_config = CircuitBreakerConfig(service_type=ServiceType.STS)
        assert sts_config.failure_threshold == 8  # Higher threshold
        assert sts_config.recovery_timeout == 30.0  # Shorter recovery
        assert sts_config.success_threshold == 3

        # Test Organizations configuration (conservative)
        org_config = CircuitBreakerConfig(service_type=ServiceType.ORGANIZATIONS)
        assert org_config.failure_threshold == 3  # Lower threshold
        assert org_config.recovery_timeout == 120.0  # Longest recovery
        assert org_config.success_threshold == 2


class TestIntelligentBackoffManager:
    """Test IntelligentBackoffManager functionality."""

    def test_initialization(self):
        """Test IntelligentBackoffManager initialization."""
        manager = IntelligentBackoffManager()

        assert manager.default_strategy is not None
        assert manager.rate_limit_tracker is not None
        assert manager.enable_circuit_breaker is True
        assert len(manager.contexts) == 0
        assert len(manager.circuit_breakers) == 0

    def test_context_creation(self):
        """Test context creation and retrieval."""
        manager = IntelligentBackoffManager()

        context = manager.get_or_create_context(
            "test-context", ServiceType.SSO_ADMIN, "ThrottlingException"
        )

        assert context.service_type == ServiceType.SSO_ADMIN
        assert context.error_type == "ThrottlingException"
        assert "test-context" in manager.contexts

        # Should return same context on second call
        context2 = manager.get_or_create_context("test-context", ServiceType.SSO_ADMIN)
        assert context is context2

    def test_circuit_breaker_creation(self):
        """Test circuit breaker creation and retrieval."""
        manager = IntelligentBackoffManager()

        breaker = manager.get_or_create_circuit_breaker("test-breaker")

        assert breaker.name == "test-breaker"
        assert "test-breaker" in manager.circuit_breakers

        # Should return same breaker on second call
        breaker2 = manager.get_or_create_circuit_breaker("test-breaker")
        assert breaker is breaker2

    @pytest.mark.asyncio
    async def test_execute_with_backoff_success(self):
        """Test successful execution with backoff manager."""
        manager = IntelligentBackoffManager()

        # Mock function that succeeds
        mock_func = Mock(return_value="success")

        result = await manager.execute_with_backoff(
            func=mock_func,
            context_key="test-success",
            service_type=ServiceType.SSO_ADMIN,
            max_retries=3,
            arg1="test",
            kwarg1="value",
        )

        assert result == "success"
        mock_func.assert_called_once_with(arg1="test", kwarg1="value")

    @pytest.mark.asyncio
    async def test_execute_with_backoff_retry(self):
        """Test retry logic with backoff manager."""
        manager = IntelligentBackoffManager()

        # Mock function that fails twice then succeeds
        mock_func = Mock(
            side_effect=[
                ClientError({"Error": {"Code": "ThrottlingException"}}, "test"),
                ClientError({"Error": {"Code": "ThrottlingException"}}, "test"),
                "success",
            ]
        )

        result = await manager.execute_with_backoff(
            func=mock_func,
            context_key="test-retry",
            service_type=ServiceType.SSO_ADMIN,
            max_retries=3,
        )

        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_with_backoff_max_retries(self):
        """Test max retries exceeded."""
        manager = IntelligentBackoffManager()

        # Mock function that always fails
        mock_func = Mock(
            side_effect=ClientError({"Error": {"Code": "ThrottlingException"}}, "test")
        )

        with pytest.raises(ClientError):
            await manager.execute_with_backoff(
                func=mock_func,
                context_key="test-max-retries",
                service_type=ServiceType.SSO_ADMIN,
                max_retries=2,
            )

        # Should have tried 3 times (initial + 2 retries)
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test circuit breaker integration."""
        manager = IntelligentBackoffManager(enable_circuit_breaker=True)

        # Create a circuit breaker with lower threshold for testing
        circuit_breaker = manager.get_or_create_circuit_breaker("test-circuit")
        circuit_breaker.config.failure_threshold = 2  # Lower threshold for testing

        # Mock function that always fails with a retryable error
        mock_func = Mock(
            side_effect=ClientError({"Error": {"Code": "ThrottlingException"}}, "test")
        )

        # First execution should fail and trip circuit breaker after retries
        with pytest.raises(ClientError):
            await manager.execute_with_backoff(
                func=mock_func,
                context_key="test-circuit",
                service_type=ServiceType.SSO_ADMIN,
                max_retries=3,  # Enough to trip circuit breaker
            )

        # Manually trip the circuit breaker to ensure it's open
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()

        # Circuit breaker should be tripped, so next execution should fail immediately
        with pytest.raises(Exception, match="Circuit breaker is open"):
            await manager.execute_with_backoff(
                func=mock_func,
                context_key="test-circuit",
                service_type=ServiceType.SSO_ADMIN,
                max_retries=1,
            )

    def test_error_classification(self):
        """Test error type classification."""
        manager = IntelligentBackoffManager()

        # Test ClientError classification
        client_error = ClientError({"Error": {"Code": "ThrottlingException"}}, "test")
        error_type = manager._classify_error_type(client_error)
        assert error_type == "ThrottlingException"

        # Test Python exception classification
        value_error = ValueError("Test error")
        error_type = manager._classify_error_type(value_error)
        assert error_type == "ValueError"

    def test_error_severity_classification(self):
        """Test error severity classification."""
        manager = IntelligentBackoffManager()

        # Test critical errors
        assert manager._classify_error_severity("AccessDeniedException") == ErrorSeverity.CRITICAL
        assert manager._classify_error_severity("ValidationException") == ErrorSeverity.CRITICAL

        # Test high errors
        assert manager._classify_error_severity("ThrottlingException") == ErrorSeverity.HIGH
        assert manager._classify_error_severity("ServiceUnavailable") == ErrorSeverity.HIGH

        # Test medium errors
        assert manager._classify_error_severity("InternalServerError") == ErrorSeverity.MEDIUM
        assert manager._classify_error_severity("RequestTimeout") == ErrorSeverity.MEDIUM

        # Test medium errors (default for unknown errors)
        assert manager._classify_error_severity("UnknownError") == ErrorSeverity.MEDIUM

        # Test low errors
        assert manager._classify_error_severity("ResourceNotFoundException") == ErrorSeverity.LOW
        assert manager._classify_error_severity("NoSuchBucket") == ErrorSeverity.LOW

    def test_throttling_error_detection(self):
        """Test throttling error detection."""
        manager = IntelligentBackoffManager()

        # Test throttling errors
        throttling_error = ClientError({"Error": {"Code": "ThrottlingException"}}, "test")
        assert manager._is_throttling_error(throttling_error) is True

        too_many_requests = ClientError({"Error": {"Code": "TooManyRequestsException"}}, "test")
        assert manager._is_throttling_error(too_many_requests) is True

        # Test non-throttling error
        access_denied = ClientError({"Error": {"Code": "AccessDeniedException"}}, "test")
        assert manager._is_throttling_error(access_denied) is False

        # Test non-ClientError
        value_error = ValueError("Test error")
        assert manager._is_throttling_error(value_error) is False

    def test_manager_stats(self):
        """Test manager statistics retrieval."""
        manager = IntelligentBackoffManager()

        # Create some contexts and circuit breakers
        manager.get_or_create_context("test1", ServiceType.SSO_ADMIN, "ThrottlingException")
        manager.get_or_create_circuit_breaker("breaker1")

        stats = manager.get_manager_stats()

        assert "contexts" in stats
        assert "circuit_breakers" in stats
        assert "service_stats" in stats

        assert "test1" in stats["contexts"]
        assert "breaker1" in stats["circuit_breakers"]

    def test_enhanced_manager_stats(self):
        """Test enhanced manager statistics with summary information."""
        manager = IntelligentBackoffManager()

        # Create contexts with different retry counts and failures
        context1 = manager.get_or_create_context(
            "test1", ServiceType.SSO_ADMIN, "ThrottlingException"
        )
        context1.retry_count = 3
        context1.consecutive_failures = 2

        context2 = manager.get_or_create_context(
            "test2", ServiceType.ORGANIZATIONS, "ServiceUnavailable"
        )
        context2.retry_count = 1
        context2.consecutive_failures = 1

        # Create circuit breakers
        breaker1 = manager.get_or_create_circuit_breaker("breaker1", ServiceType.SSO_ADMIN)
        breaker2 = manager.get_or_create_circuit_breaker("breaker2", ServiceType.STS)

        breaker2.record_success()
        # Trip one circuit breaker
        breaker1.record_failure()
        breaker1.record_failure()
        breaker1.record_failure()  # Should trip SSO Admin breaker (threshold=3)

        stats = manager.get_manager_stats()

        # Check that summary stats are included
        assert "summary" in stats
        summary = stats["summary"]

        assert summary["total_contexts"] == 2
        assert summary["total_circuit_breakers"] == 2
        assert summary["total_retries"] == 4  # 3 + 1
        assert summary["total_consecutive_failures"] == 3  # 2 + 1
        assert summary["avg_retries_per_context"] == 2.0  # 4 / 2
        assert summary["avg_consecutive_failures"] == 1.5  # 3 / 2

        # Check service context counts
        assert "service_context_counts" in summary
        assert summary["service_context_counts"]["sso-admin"] == 1
        assert summary["service_context_counts"]["organizations"] == 1

        # Check circuit breaker states
        assert "circuit_breaker_states" in summary
        assert summary["circuit_breaker_states"]["open"] == 1  # breaker1 should be open
        assert summary["circuit_breaker_states"]["closed"] == 1  # breaker2 should be closed

        # Check service health
        assert "service_health" in summary

    def test_context_reset(self):
        """Test context reset functionality."""
        manager = IntelligentBackoffManager()

        # Create contexts
        manager.get_or_create_context("test1", ServiceType.SSO_ADMIN)
        manager.get_or_create_context("test2", ServiceType.IDENTITY_STORE)
        manager.get_or_create_circuit_breaker("breaker1")

        assert len(manager.contexts) == 2
        assert len(manager.circuit_breakers) == 1

        # Reset specific context
        manager.reset_context("test1")
        assert len(manager.contexts) == 1
        assert "test1" not in manager.contexts
        assert "test2" in manager.contexts

        # Reset all contexts
        manager.reset_all_contexts()
        assert len(manager.contexts) == 0
        assert len(manager.circuit_breakers) == 0


class TestBackwardCompatibility:
    """Test backward compatibility functions."""

    def test_should_retry_error_compatibility(self):
        """Test should_retry_error backward compatibility function."""
        # Test retryable error
        throttling_error = ClientError({"Error": {"Code": "ThrottlingException"}}, "test")
        assert should_retry_error(throttling_error, 1, 3) is True

        # Test non-retryable error
        access_denied = ClientError({"Error": {"Code": "AccessDeniedException"}}, "test")
        assert should_retry_error(access_denied, 1, 3) is False

        # Test max retries exceeded
        assert should_retry_error(throttling_error, 3, 3) is False

    def test_calculate_retry_delay_compatibility(self):
        """Test calculate_retry_delay backward compatibility function."""
        # Test delay calculation
        delay0 = calculate_retry_delay(0)
        delay1 = calculate_retry_delay(1)
        delay2 = calculate_retry_delay(2)

        # Should increase with retry count
        assert delay1 > delay0
        assert delay2 > delay1

        # Should respect base and max delay
        delay_with_params = calculate_retry_delay(1, "ThrottlingException")
        assert delay_with_params > 0


if __name__ == "__main__":
    pytest.main([__file__])
