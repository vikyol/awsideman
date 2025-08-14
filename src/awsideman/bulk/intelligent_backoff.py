"""Intelligent backoff strategies for rate limiting in multi-account operations.

This module provides adaptive backoff strategies based on error type analysis,
per-service rate limit tracking, circuit breaker patterns, and jitter to avoid
thundering herd problems.

Classes:
    BackoffStrategy: Base class for backoff strategies
    ExponentialBackoffStrategy: Exponential backoff with jitter
    AdaptiveBackoffStrategy: Adaptive backoff based on error type analysis
    ServiceRateLimitTracker: Per-service rate limit tracking
    CircuitBreaker: Circuit breaker pattern for persistent failures
    IntelligentBackoffManager: Main manager for intelligent backoff strategies
"""

import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from rich.console import Console

console = Console()


class ServiceType(str, Enum):
    """AWS service types for rate limit tracking."""

    SSO_ADMIN = "sso-admin"
    IDENTITY_STORE = "identitystore"
    ORGANIZATIONS = "organizations"
    STS = "sts"
    UNKNOWN = "unknown"


class ErrorSeverity(str, Enum):
    """Error severity levels for adaptive backoff."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BackoffContext:
    """Context information for backoff calculations."""

    service_type: ServiceType
    error_type: str
    error_severity: ErrorSeverity
    retry_count: int
    consecutive_failures: int
    last_success_time: Optional[float] = None
    error_history: List[str] = field(default_factory=list)

    def add_error(self, error_type: str):
        """Add an error to the history."""
        self.error_history.append(error_type)
        # Keep only last 10 errors for memory efficiency
        if len(self.error_history) > 10:
            self.error_history = self.error_history[-10:]


@dataclass
class RateLimitInfo:
    """Rate limit information for a service."""

    service_type: ServiceType
    requests_per_second: float
    burst_capacity: int
    current_requests: int = 0
    last_reset_time: float = field(default_factory=time.time)
    consecutive_throttles: int = 0
    last_throttle_time: Optional[float] = None

    def reset_if_needed(self):
        """Reset rate limit counters if time window has passed."""
        current_time = time.time()
        if current_time - self.last_reset_time >= 1.0:  # 1 second window
            self.current_requests = 0
            self.last_reset_time = current_time

    def can_make_request(self) -> bool:
        """Check if a request can be made within rate limits."""
        self.reset_if_needed()
        return self.current_requests < self.requests_per_second

    def record_request(self):
        """Record a request being made."""
        self.reset_if_needed()
        self.current_requests += 1

    def record_throttle(self):
        """Record a throttling event with intelligent rate adjustment."""
        self.consecutive_throttles += 1
        self.last_throttle_time = time.time()

        # More aggressive reduction for repeated throttles
        if self.consecutive_throttles == 1:
            reduction_factor = 0.8  # 20% reduction on first throttle
        elif self.consecutive_throttles <= 3:
            reduction_factor = 0.6  # 40% reduction for early throttles
        elif self.consecutive_throttles <= 5:
            reduction_factor = 0.4  # 60% reduction for persistent throttles
        else:
            reduction_factor = 0.2  # 80% reduction for severe throttling

        # Apply minimum rate limit based on service type
        min_rate = self._get_minimum_rate_limit()
        self.requests_per_second = max(min_rate, self.requests_per_second * reduction_factor)

    def record_success(self):
        """Record a successful request with intelligent rate recovery."""
        if self.consecutive_throttles > 0:
            # Conservative recovery - increase rate limit gradually
            if self.consecutive_throttles >= 5:
                # Very conservative recovery after severe throttling
                recovery_factor = 1.05  # 5% increase
            elif self.consecutive_throttles >= 3:
                # Moderate recovery after moderate throttling
                recovery_factor = 1.08  # 8% increase
            else:
                # Normal recovery after light throttling
                recovery_factor = 1.1  # 10% increase

            self.requests_per_second = min(
                self.requests_per_second * recovery_factor, self._get_default_rate_limit()
            )
        self.consecutive_throttles = 0

    def _get_default_rate_limit(self) -> float:
        """Get default rate limit for the service type."""
        defaults = {
            ServiceType.SSO_ADMIN: 20.0,
            ServiceType.IDENTITY_STORE: 10.0,
            ServiceType.ORGANIZATIONS: 5.0,
            ServiceType.STS: 50.0,
            ServiceType.UNKNOWN: 5.0,
        }
        return defaults.get(self.service_type, 5.0)

    def _get_minimum_rate_limit(self) -> float:
        """Get minimum rate limit for the service type to prevent over-throttling."""
        minimums = {
            ServiceType.SSO_ADMIN: 1.0,
            ServiceType.IDENTITY_STORE: 0.5,
            ServiceType.ORGANIZATIONS: 0.5,
            ServiceType.STS: 2.0,
            ServiceType.UNKNOWN: 0.5,
        }
        return minimums.get(self.service_type, 0.5)


class BackoffStrategy(ABC):
    """Base class for backoff strategies."""

    @abstractmethod
    def calculate_delay(self, context: BackoffContext) -> float:
        """Calculate the delay for the given context.

        Args:
            context: Backoff context with error and retry information

        Returns:
            Delay in seconds
        """
        pass

    @abstractmethod
    def should_retry(self, context: BackoffContext, max_retries: int) -> bool:
        """Determine if a retry should be attempted.

        Args:
            context: Backoff context with error and retry information
            max_retries: Maximum number of retries allowed

        Returns:
            True if retry should be attempted, False otherwise
        """
        pass


class ExponentialBackoffStrategy(BackoffStrategy):
    """Exponential backoff strategy with jitter."""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter_factor: float = 0.1,
    ):
        """Initialize exponential backoff strategy.

        Args:
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential calculation
            jitter_factor: Factor for jitter (0.0 to 1.0)
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter_factor = jitter_factor

    def calculate_delay(self, context: BackoffContext) -> float:
        """Calculate exponential backoff delay with jitter."""
        # Basic exponential backoff
        delay = self.base_delay * (self.exponential_base**context.retry_count)

        # Apply maximum delay limit
        delay = min(delay, self.max_delay)

        # Add jitter to avoid thundering herd
        if self.jitter_factor > 0:
            jitter = delay * self.jitter_factor * random.random()
            delay += jitter

        return delay

    def should_retry(self, context: BackoffContext, max_retries: int) -> bool:
        """Check if retry should be attempted based on retry count."""
        return context.retry_count < max_retries


class AdaptiveBackoffStrategy(BackoffStrategy):
    """Adaptive backoff strategy based on error type analysis."""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 300.0,
        jitter_factor: float = 0.2,
        enable_adaptive_jitter: bool = True,
    ):
        """Initialize adaptive backoff strategy.

        Args:
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            jitter_factor: Factor for jitter (0.0 to 1.0)
            enable_adaptive_jitter: Whether to use adaptive jitter based on error patterns
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self.enable_adaptive_jitter = enable_adaptive_jitter

        # Enhanced error type multipliers with more AWS-specific errors
        self.error_multipliers = {
            # High priority throttling errors - need longer backoff
            "ThrottlingException": 3.0,
            "TooManyRequestsException": 3.0,
            "Throttling": 3.0,
            "RequestLimitExceeded": 3.0,
            "SlowDown": 2.5,  # S3 specific
            # Service availability errors - moderate backoff
            "ServiceUnavailable": 2.0,
            "ServiceUnavailableException": 2.0,
            "InternalServerError": 2.0,
            "InternalFailure": 2.0,
            "InternalError": 2.0,
            # Network and timeout errors - moderate backoff
            "RequestTimeout": 1.5,
            "RequestTimeoutException": 1.5,
            "ConnectionError": 1.5,
            "NetworkError": 1.5,
            "EndpointConnectionError": 1.5,
            "ConnectTimeoutError": 1.5,
            "ReadTimeoutError": 1.5,
            # Temporary service errors - moderate backoff
            "ProvisionedThroughputExceededException": 2.0,
            "LimitExceededException": 2.0,
            "ConcurrentModificationException": 1.8,
            "ConflictException": 1.5,
            # Permission errors - short backoff (likely won't resolve quickly)
            "AccessDeniedException": 0.5,
            "AccessDenied": 0.5,
            "UnauthorizedException": 0.5,
            "Forbidden": 0.5,
            "InvalidUserID.NotFound": 0.3,
            # Resource errors - short backoff
            "ResourceNotFoundException": 0.5,
            "NoSuchBucket": 0.3,
            "NoSuchKey": 0.3,
            "EntityDoesNotExistException": 0.5,
            # Validation errors - very short backoff (won't resolve with time)
            "ValidationException": 0.1,
            "InvalidParameterException": 0.1,
            "InvalidParameterValue": 0.1,
            "MissingParameterException": 0.1,
            "InvalidRequest": 0.1,
            "MalformedPolicyDocument": 0.1,
            # SSO-specific errors
            "InstanceNotFound": 0.3,
            "ResourceNotFound": 0.5,
        }

        # Enhanced severity multipliers with more granular control
        self.severity_multipliers = {
            ErrorSeverity.LOW: 0.5,
            ErrorSeverity.MEDIUM: 1.0,
            ErrorSeverity.HIGH: 2.0,
            ErrorSeverity.CRITICAL: 4.0,
        }

    def calculate_delay(self, context: BackoffContext) -> float:
        """Calculate adaptive delay based on error type and severity."""
        # Start with base exponential backoff
        base_delay = self.base_delay * (2**context.retry_count)

        # Apply error type multiplier
        error_multiplier = self.error_multipliers.get(context.error_type, 1.0)
        delay = base_delay * error_multiplier

        # Apply severity multiplier
        severity_multiplier = self.severity_multipliers.get(context.error_severity, 1.0)
        delay *= severity_multiplier

        # Apply consecutive failure penalty with exponential growth
        if context.consecutive_failures > 3:
            consecutive_penalty = 1.5 ** (context.consecutive_failures - 3)
            delay *= consecutive_penalty

        # Apply service-specific adjustments
        service_multiplier = self._get_service_multiplier(context.service_type)
        delay *= service_multiplier

        # Apply error pattern analysis for adaptive adjustment
        delay = self._apply_error_pattern_analysis(delay, context)

        # Apply maximum delay limit
        delay = min(delay, self.max_delay)

        # Add intelligent jitter to avoid thundering herd
        if self.jitter_factor > 0:
            delay = self._apply_intelligent_jitter(delay, context)

        return delay

    def should_retry(self, context: BackoffContext, max_retries: int) -> bool:
        """Determine if retry should be attempted based on error analysis."""
        # Don't retry certain error types
        non_retryable_errors = {
            "AccessDeniedException",
            "UnauthorizedException",
            "ValidationException",
            "InvalidParameterException",
            "MissingParameterException",
        }

        if context.error_type in non_retryable_errors:
            return False

        # Don't retry if we've exceeded max retries
        if context.retry_count >= max_retries:
            return False

        # Don't retry if we have too many consecutive failures
        if context.consecutive_failures > 10:
            return False

        # Retry for retryable errors
        retryable_errors = {
            "ThrottlingException",
            "TooManyRequestsException",
            "ServiceUnavailable",
            "InternalServerError",
            "RequestTimeout",
            "ConnectionError",
            "NetworkError",
        }

        return context.error_type in retryable_errors or context.error_severity in [
            ErrorSeverity.MEDIUM,
            ErrorSeverity.HIGH,
        ]

    def _get_service_multiplier(self, service_type: ServiceType) -> float:
        """Get service-specific delay multiplier."""
        multipliers = {
            ServiceType.SSO_ADMIN: 1.2,  # SSO Admin is more sensitive
            ServiceType.IDENTITY_STORE: 1.0,
            ServiceType.ORGANIZATIONS: 1.5,  # Organizations has lower limits
            ServiceType.STS: 0.8,  # STS is generally more resilient
            ServiceType.UNKNOWN: 1.0,
        }
        return multipliers.get(service_type, 1.0)

    def _apply_error_pattern_analysis(self, delay: float, context: BackoffContext) -> float:
        """Apply error pattern analysis to adjust delay based on error history.

        Args:
            delay: Current calculated delay
            context: Backoff context with error history

        Returns:
            Adjusted delay based on error patterns
        """
        if not context.error_history or len(context.error_history) < 2:
            return delay

        # Analyze error patterns in recent history
        recent_errors = context.error_history[-5:]  # Look at last 5 errors

        # Check for repeated throttling errors - increase delay more aggressively
        throttling_errors = {
            "ThrottlingException",
            "TooManyRequestsException",
            "Throttling",
            "RequestLimitExceeded",
        }
        throttling_count = sum(1 for error in recent_errors if error in throttling_errors)

        if throttling_count >= 3:
            # Aggressive backoff for repeated throttling
            delay *= 1.8
        elif throttling_count >= 2:
            # Moderate increase for some throttling
            delay *= 1.4

        # Check for alternating error types - might indicate system instability
        unique_errors = set(recent_errors)
        if len(unique_errors) >= 3 and len(recent_errors) >= 4:
            # Multiple different errors suggest system instability
            delay *= 1.3

        # Check for service unavailability patterns
        service_errors = {"ServiceUnavailable", "InternalServerError", "InternalFailure"}
        service_error_count = sum(1 for error in recent_errors if error in service_errors)

        if service_error_count >= 2:
            # Service seems unstable, increase delay
            delay *= 1.5

        return delay

    def _apply_intelligent_jitter(self, delay: float, context: BackoffContext) -> float:
        """Apply intelligent jitter based on context and error patterns.

        Args:
            delay: Base delay to apply jitter to
            context: Backoff context for jitter calculation

        Returns:
            Delay with intelligent jitter applied
        """
        if not self.enable_adaptive_jitter:
            # Use simple uniform jitter
            jitter_range = delay * self.jitter_factor
            jitter = random.uniform(-jitter_range, jitter_range)
            return max(0.1, delay + jitter)

        # Adaptive jitter based on error type and context
        base_jitter_factor = self.jitter_factor

        # Increase jitter for throttling errors to spread out retries more
        if context.error_type in {"ThrottlingException", "TooManyRequestsException", "Throttling"}:
            base_jitter_factor *= 1.5

        # Reduce jitter for validation errors (they won't resolve with time anyway)
        elif context.error_type in {"ValidationException", "InvalidParameterException"}:
            base_jitter_factor *= 0.5

        # Use different jitter algorithms based on retry count
        if context.retry_count <= 2:
            # Early retries: use uniform jitter
            jitter_range = delay * base_jitter_factor
            jitter = random.uniform(0, jitter_range)  # Only positive jitter for early retries
        else:
            # Later retries: use exponential jitter to spread out more
            jitter_range = delay * base_jitter_factor
            # Use exponential distribution for more spread
            jitter = random.expovariate(1.0 / (jitter_range / 2))
            jitter = min(jitter, jitter_range)  # Cap the jitter

        # Ensure minimum delay
        final_delay = max(0.1, delay + jitter)

        return final_delay


class ServiceRateLimitTracker:
    """Per-service rate limit tracking for different AWS APIs."""

    def __init__(self):
        """Initialize service rate limit tracker."""
        self.service_limits: Dict[ServiceType, RateLimitInfo] = {}
        self._initialize_default_limits()

    def _initialize_default_limits(self):
        """Initialize default rate limits for AWS services."""
        default_limits = {
            ServiceType.SSO_ADMIN: RateLimitInfo(
                service_type=ServiceType.SSO_ADMIN, requests_per_second=20.0, burst_capacity=40
            ),
            ServiceType.IDENTITY_STORE: RateLimitInfo(
                service_type=ServiceType.IDENTITY_STORE, requests_per_second=10.0, burst_capacity=20
            ),
            ServiceType.ORGANIZATIONS: RateLimitInfo(
                service_type=ServiceType.ORGANIZATIONS, requests_per_second=5.0, burst_capacity=10
            ),
            ServiceType.STS: RateLimitInfo(
                service_type=ServiceType.STS, requests_per_second=50.0, burst_capacity=100
            ),
            ServiceType.UNKNOWN: RateLimitInfo(
                service_type=ServiceType.UNKNOWN, requests_per_second=5.0, burst_capacity=10
            ),
        }

        self.service_limits.update(default_limits)

    def can_make_request(self, service_type: ServiceType) -> bool:
        """Check if a request can be made for the given service."""
        if service_type not in self.service_limits:
            return True

        return self.service_limits[service_type].can_make_request()

    def record_request(self, service_type: ServiceType):
        """Record a request being made for the given service."""
        if service_type in self.service_limits:
            self.service_limits[service_type].record_request()

    def record_throttle(self, service_type: ServiceType):
        """Record a throttling event for the given service."""
        if service_type in self.service_limits:
            self.service_limits[service_type].record_throttle()

    def record_success(self, service_type: ServiceType):
        """Record a successful request for the given service."""
        if service_type in self.service_limits:
            self.service_limits[service_type].record_success()

    def get_recommended_delay(self, service_type: ServiceType) -> float:
        """Get recommended delay before next request for the service."""
        if service_type not in self.service_limits:
            return 0.0

        rate_info = self.service_limits[service_type]

        if not rate_info.can_make_request():
            # Calculate delay until next request can be made
            time_until_reset = 1.0 - (time.time() - rate_info.last_reset_time)
            return max(0.0, time_until_reset)

        # If we've been throttled recently, add extra delay
        if rate_info.consecutive_throttles > 0:
            throttle_penalty = rate_info.consecutive_throttles * 0.5
            return throttle_penalty

        return 0.0

    def get_service_stats(self) -> Dict[ServiceType, Dict[str, Any]]:
        """Get statistics for all tracked services."""
        stats = {}

        for service_type, rate_info in self.service_limits.items():
            stats[service_type] = {
                "requests_per_second": rate_info.requests_per_second,
                "current_requests": rate_info.current_requests,
                "consecutive_throttles": rate_info.consecutive_throttles,
                "last_throttle_time": rate_info.last_throttle_time,
                "can_make_request": rate_info.can_make_request(),
                "recommended_delay": self.get_recommended_delay(service_type),
            }

        return stats


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3
    service_type: Optional[ServiceType] = None

    def __post_init__(self):
        """Adjust configuration based on service type."""
        if self.service_type:
            self._apply_service_specific_config()

    def _apply_service_specific_config(self):
        """Apply service-specific circuit breaker configuration."""
        if self.service_type == ServiceType.SSO_ADMIN:
            # SSO Admin is more sensitive, trip circuit breaker sooner
            self.failure_threshold = 3
            self.recovery_timeout = 90.0  # Longer recovery time
            self.success_threshold = 2
        elif self.service_type == ServiceType.ORGANIZATIONS:
            # Organizations has lower limits, be more conservative
            self.failure_threshold = 3
            self.recovery_timeout = 120.0  # Even longer recovery
            self.success_threshold = 2
        elif self.service_type == ServiceType.STS:
            # STS is more resilient, allow more failures
            self.failure_threshold = 8
            self.recovery_timeout = 30.0  # Shorter recovery
            self.success_threshold = 3
        elif self.service_type == ServiceType.IDENTITY_STORE:
            # Identity Store moderate settings
            self.failure_threshold = 4
            self.recovery_timeout = 60.0
            self.success_threshold = 2


class CircuitBreaker:
    """Circuit breaker pattern for persistent failures."""

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker.

        Args:
            name: Name of the circuit breaker
            config: Configuration for the circuit breaker
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None

    def can_execute(self) -> bool:
        """Check if execution is allowed based on circuit breaker state."""
        current_time = time.time()

        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has passed
            if (
                self.last_failure_time
                and current_time - self.last_failure_time >= self.config.recovery_timeout
            ):
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True

        return False

    def record_success(self):
        """Record a successful execution."""
        self.last_success_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        """Record a failed execution."""
        self.last_failure_time = time.time()
        self.failure_count += 1

        if self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitBreakerState.OPEN
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.success_count = 0

    def get_state_info(self) -> Dict[str, Any]:
        """Get current state information."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "can_execute": self.can_execute(),
        }


class IntelligentBackoffManager:
    """Main manager for intelligent backoff strategies."""

    def __init__(
        self,
        default_strategy: Optional[BackoffStrategy] = None,
        enable_circuit_breaker: bool = True,
    ):
        """Initialize intelligent backoff manager.

        Args:
            default_strategy: Default backoff strategy to use
            enable_circuit_breaker: Whether to enable circuit breaker pattern
        """
        self.default_strategy = default_strategy or AdaptiveBackoffStrategy()
        self.rate_limit_tracker = ServiceRateLimitTracker()
        self.enable_circuit_breaker = enable_circuit_breaker

        # Circuit breakers for different contexts
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Context tracking
        self.contexts: Dict[str, BackoffContext] = {}

    def get_or_create_context(
        self, context_key: str, service_type: ServiceType, error_type: str = "Unknown"
    ) -> BackoffContext:
        """Get or create a backoff context for the given key."""
        if context_key not in self.contexts:
            self.contexts[context_key] = BackoffContext(
                service_type=service_type,
                error_type=error_type,
                error_severity=self._classify_error_severity(error_type),
                retry_count=0,
                consecutive_failures=0,
            )

        return self.contexts[context_key]

    def get_or_create_circuit_breaker(
        self, breaker_key: str, service_type: Optional[ServiceType] = None
    ) -> CircuitBreaker:
        """Get or create a circuit breaker for the given key with service-specific configuration."""
        if breaker_key not in self.circuit_breakers:
            # Create service-specific configuration
            config = (
                CircuitBreakerConfig(service_type=service_type)
                if service_type
                else CircuitBreakerConfig()
            )
            self.circuit_breakers[breaker_key] = CircuitBreaker(breaker_key, config)

        return self.circuit_breakers[breaker_key]

    async def execute_with_backoff(
        self,
        func: Callable,
        context_key: str,
        service_type: ServiceType,
        max_retries: int = 3,
        *args,
        **kwargs,
    ) -> Any:
        """Execute a function with intelligent backoff and retry logic.

        Args:
            func: Function to execute
            context_key: Unique key for this execution context
            service_type: AWS service type being called
            max_retries: Maximum number of retries
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function execution

        Raises:
            Exception: The last exception if all retries are exhausted
        """
        context = self.get_or_create_context(context_key, service_type)
        circuit_breaker = None

        if self.enable_circuit_breaker:
            circuit_breaker = self.get_or_create_circuit_breaker(context_key, service_type)

            # Check circuit breaker before attempting execution
            if not circuit_breaker.can_execute():
                raise Exception(
                    f"Circuit breaker is open for {context_key} (service: {service_type.value})"
                )

        last_exception = None

        while context.retry_count <= max_retries:
            try:
                # Check service rate limits
                if not self.rate_limit_tracker.can_make_request(service_type):
                    delay = self.rate_limit_tracker.get_recommended_delay(service_type)
                    if delay > 0:
                        console.print(
                            f"[yellow]Rate limit delay: {delay:.1f}s for {service_type.value}[/yellow]"
                        )
                        await asyncio.sleep(delay)

                # Record the request
                self.rate_limit_tracker.record_request(service_type)

                # Execute the function
                result = func(*args, **kwargs)

                # Record success
                self.rate_limit_tracker.record_success(service_type)
                if circuit_breaker:
                    circuit_breaker.record_success()

                # Reset context on success
                context.consecutive_failures = 0
                context.last_success_time = time.time()

                return result

            except Exception as e:
                last_exception = e

                # Classify and record the error
                error_type = self._classify_error_type(e)
                context.error_type = error_type
                context.error_severity = self._classify_error_severity(error_type)
                context.add_error(error_type)
                context.consecutive_failures += 1

                # Record failure in tracking systems
                if self._is_throttling_error(e):
                    self.rate_limit_tracker.record_throttle(service_type)

                if circuit_breaker:
                    circuit_breaker.record_failure()

                # Check if we should retry
                if not self.default_strategy.should_retry(context, max_retries):
                    break

                # Calculate delay
                delay = self.default_strategy.calculate_delay(context)

                # Add service-specific delay
                service_delay = self.rate_limit_tracker.get_recommended_delay(service_type)
                total_delay = max(delay, service_delay)

                console.print(
                    f"[yellow]Retry {context.retry_count + 1}/{max_retries} "
                    f"after {total_delay:.1f}s: {error_type}[/yellow]"
                )

                # Wait before retry
                await asyncio.sleep(total_delay)

                # Increment retry count
                context.retry_count += 1

        # All retries exhausted
        if last_exception:
            raise last_exception
        else:
            raise Exception("Maximum retries exceeded")

    def _classify_error_type(self, error: Exception) -> str:
        """Classify an exception into an error type."""
        if isinstance(error, ClientError):
            return error.response.get("Error", {}).get("Code", "Unknown")

        return type(error).__name__

    def _classify_error_severity(self, error_type: str) -> ErrorSeverity:
        """Classify error severity based on error type with enhanced AWS error classification."""
        # Critical errors - usually indicate configuration or permission issues
        critical_errors = {
            "AccessDeniedException",
            "AccessDenied",
            "UnauthorizedException",
            "Forbidden",
            "ValidationException",
            "InvalidParameterException",
            "InvalidParameterValue",
            "MissingParameterException",
            "InvalidRequest",
            "MalformedPolicyDocument",
            "InvalidUserID.NotFound",
            "EntityDoesNotExistException",
        }

        # High severity errors - throttling and service issues that need aggressive backoff
        high_errors = {
            "ThrottlingException",
            "TooManyRequestsException",
            "Throttling",
            "RequestLimitExceeded",
            "ServiceUnavailable",
            "ServiceUnavailableException",
            "ProvisionedThroughputExceededException",
            "LimitExceededException",
        }

        # Medium severity errors - temporary issues that may resolve
        medium_errors = {
            "InternalServerError",
            "InternalFailure",
            "InternalError",
            "RequestTimeout",
            "RequestTimeoutException",
            "ConnectionError",
            "NetworkError",
            "EndpointConnectionError",
            "ConnectTimeoutError",
            "ReadTimeoutError",
            "ConcurrentModificationException",
            "ConflictException",
            "SlowDown",
        }

        # Low severity errors - resource not found, etc.
        low_errors = {
            "ResourceNotFoundException",
            "NoSuchBucket",
            "NoSuchKey",
            "InstanceNotFound",
            "ResourceNotFound",
        }

        if error_type in critical_errors:
            return ErrorSeverity.CRITICAL
        elif error_type in high_errors:
            return ErrorSeverity.HIGH
        elif error_type in medium_errors:
            return ErrorSeverity.MEDIUM
        elif error_type in low_errors:
            return ErrorSeverity.LOW
        else:
            # Default to medium for unknown errors
            return ErrorSeverity.MEDIUM

    def _is_throttling_error(self, error: Exception) -> bool:
        """Check if an error is a throttling error."""
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "")
            throttling_codes = {"ThrottlingException", "TooManyRequestsException", "Throttling"}
            return error_code in throttling_codes

        return False

    def get_manager_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics for the backoff manager."""
        return {
            "contexts": {
                key: {
                    "service_type": ctx.service_type.value,
                    "error_type": ctx.error_type,
                    "error_severity": ctx.error_severity.value,
                    "retry_count": ctx.retry_count,
                    "consecutive_failures": ctx.consecutive_failures,
                    "error_history": ctx.error_history,
                    "last_success_time": ctx.last_success_time,
                }
                for key, ctx in self.contexts.items()
            },
            "circuit_breakers": {
                key: breaker.get_state_info() for key, breaker in self.circuit_breakers.items()
            },
            "service_stats": self.rate_limit_tracker.get_service_stats(),
            "summary": self._get_summary_stats(),
        }

    def _get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics across all contexts and services."""
        total_contexts = len(self.contexts)
        total_circuit_breakers = len(self.circuit_breakers)

        # Count contexts by service type
        service_context_counts = {}
        total_retries = 0
        total_consecutive_failures = 0

        for ctx in self.contexts.values():
            service_type = ctx.service_type.value
            service_context_counts[service_type] = service_context_counts.get(service_type, 0) + 1
            total_retries += ctx.retry_count
            total_consecutive_failures += ctx.consecutive_failures

        # Count circuit breakers by state
        circuit_breaker_states = {"closed": 0, "open": 0, "half_open": 0}
        for breaker in self.circuit_breakers.values():
            circuit_breaker_states[breaker.state.value] += 1

        # Get service rate limit health
        service_health = {}
        for service_type, stats in self.rate_limit_tracker.get_service_stats().items():
            if stats["consecutive_throttles"] == 0:
                health = "healthy"
            elif stats["consecutive_throttles"] <= 2:
                health = "warning"
            else:
                health = "critical"
            service_health[service_type.value] = health

        return {
            "total_contexts": total_contexts,
            "total_circuit_breakers": total_circuit_breakers,
            "total_retries": total_retries,
            "total_consecutive_failures": total_consecutive_failures,
            "service_context_counts": service_context_counts,
            "circuit_breaker_states": circuit_breaker_states,
            "service_health": service_health,
            "avg_retries_per_context": total_retries / max(1, total_contexts),
            "avg_consecutive_failures": total_consecutive_failures / max(1, total_contexts),
        }

    def reset_context(self, context_key: str):
        """Reset a specific context."""
        if context_key in self.contexts:
            del self.contexts[context_key]
        if context_key in self.circuit_breakers:
            del self.circuit_breakers[context_key]

    def reset_all_contexts(self):
        """Reset all contexts and circuit breakers."""
        self.contexts.clear()
        self.circuit_breakers.clear()


# Utility functions for backward compatibility
def should_retry_error(error: Exception, retry_count: int, max_retries: int) -> bool:
    """Check if an error should be retried (backward compatibility)."""
    strategy = AdaptiveBackoffStrategy()

    # Get proper error type for ClientError
    if isinstance(error, ClientError):
        error_type = error.response.get("Error", {}).get("Code", "Unknown")
    else:
        error_type = error.__class__.__name__

    context = BackoffContext(
        service_type=ServiceType.UNKNOWN,
        error_type=error_type,
        error_severity=ErrorSeverity.MEDIUM,
        retry_count=retry_count,
        consecutive_failures=retry_count,
    )
    return strategy.should_retry(context, max_retries)


def calculate_retry_delay(retry_count: int, error_type: str = "Unknown") -> float:
    """Calculate retry delay (backward compatibility)."""
    strategy = AdaptiveBackoffStrategy()
    context = BackoffContext(
        service_type=ServiceType.UNKNOWN,
        error_type=error_type,
        error_severity=ErrorSeverity.MEDIUM,
        retry_count=retry_count,
        consecutive_failures=retry_count,
    )
    return strategy.calculate_delay(context)
