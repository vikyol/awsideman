"""
Performance optimizations and batch processing for permission cloning operations.

This module provides functionality to optimize permission cloning operations through:
- Parallel processing for multiple assignment operations
- Rate limiting to respect AWS API constraints
- Optimized caching strategy for entity and permission set lookups
- Streaming processing for large assignment lists
- Performance monitoring and metrics
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from botocore.exceptions import ClientError

from .models import EntityReference, EntityType, PermissionAssignment

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for AWS API rate limiting."""

    # AWS Identity Center API limits (requests per second)
    sso_admin_rps: float = 10.0  # Conservative limit for SSO Admin API
    identity_store_rps: float = 20.0  # Conservative limit for Identity Store API
    organizations_rps: float = 10.0  # Conservative limit for Organizations API

    # Burst allowances
    sso_admin_burst: int = 20
    identity_store_burst: int = 40
    organizations_burst: int = 20

    # Backoff configuration
    initial_backoff_ms: int = 100
    max_backoff_ms: int = 5000
    backoff_multiplier: float = 2.0
    max_retries: int = 3


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    # Batch sizes for different operations
    assignment_copy_batch_size: int = 10
    entity_resolution_batch_size: int = 50
    cache_warm_batch_size: int = 100

    # Parallel processing limits
    max_workers: int = 5
    max_concurrent_api_calls: int = 10

    # Memory management
    max_memory_mb: int = 500
    stream_threshold: int = 1000  # Stream processing for operations larger than this


@dataclass
class PerformanceMetrics:
    """Performance metrics for cloning operations."""

    operation_id: str
    start_time: datetime
    end_time: Optional[datetime] = None

    # Operation counts
    total_assignments: int = 0
    processed_assignments: int = 0
    failed_assignments: int = 0
    cached_lookups: int = 0
    api_calls: int = 0

    # Timing metrics
    entity_resolution_time_ms: float = 0
    assignment_retrieval_time_ms: float = 0
    assignment_creation_time_ms: float = 0
    cache_operations_time_ms: float = 0

    # Rate limiting metrics
    rate_limit_delays_ms: float = 0
    retry_attempts: int = 0

    # Memory usage
    peak_memory_mb: float = 0

    @property
    def duration_ms(self) -> Optional[float]:
        """Get total operation duration in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None

    @property
    def assignments_per_second(self) -> Optional[float]:
        """Get assignments processed per second."""
        if self.duration_ms and self.processed_assignments > 0:
            return (self.processed_assignments / self.duration_ms) * 1000
        return None

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_assignments > 0:
            return (self.processed_assignments / self.total_assignments) * 100
        return 0.0


class RateLimiter:
    """Rate limiter for AWS API calls."""

    def __init__(self, config: RateLimitConfig):
        """Initialize rate limiter with configuration."""
        self.config = config
        self._locks = {
            "sso_admin": threading.Lock(),
            "identity_store": threading.Lock(),
            "organizations": threading.Lock(),
        }
        self._last_call_times = {"sso_admin": 0.0, "identity_store": 0.0, "organizations": 0.0}
        self._call_counts = {"sso_admin": 0, "identity_store": 0, "organizations": 0}
        self._window_start_times = {
            "sso_admin": time.time(),
            "identity_store": time.time(),
            "organizations": time.time(),
        }

    def acquire(self, service: str) -> float:
        """
        Acquire permission to make an API call, blocking if necessary.

        Args:
            service: Service name ('sso_admin', 'identity_store', 'organizations')

        Returns:
            Delay time in milliseconds
        """
        if service not in self._locks:
            return 0.0

        with self._locks[service]:
            current_time = time.time()

            # Get rate limit for this service
            if service == "sso_admin":
                rps = self.config.sso_admin_rps
                burst = self.config.sso_admin_burst
            elif service == "identity_store":
                rps = self.config.identity_store_rps
                burst = self.config.identity_store_burst
            else:  # organizations
                rps = self.config.organizations_rps
                burst = self.config.organizations_burst

            # Reset window if needed (1 second windows)
            if current_time - self._window_start_times[service] >= 1.0:
                self._call_counts[service] = 0
                self._window_start_times[service] = current_time

            # Check if we're within burst limit
            if self._call_counts[service] < burst:
                self._call_counts[service] += 1
                self._last_call_times[service] = current_time
                return 0.0

            # Calculate delay needed to respect rate limit
            time_since_last_call = current_time - self._last_call_times[service]
            min_interval = 1.0 / rps

            if time_since_last_call < min_interval:
                delay_seconds = min_interval - time_since_last_call
                time.sleep(delay_seconds)
                delay_ms = delay_seconds * 1000
            else:
                delay_ms = 0.0

            self._call_counts[service] += 1
            self._last_call_times[service] = time.time()
            return delay_ms


class OptimizedCache:
    """Optimized caching system for permission cloning operations."""

    def __init__(self, max_size: int = 10000):
        """Initialize optimized cache."""
        self.max_size = max_size
        self._lock = threading.RLock()

        # Separate caches for different data types
        self._entity_cache: Dict[str, EntityReference] = {}
        self._assignment_cache: Dict[str, List[PermissionAssignment]] = {}
        self._permission_set_cache: Dict[str, Dict[str, Any]] = {}
        self._account_cache: Dict[str, str] = {}

        # Access tracking for LRU eviction
        self._access_times: Dict[str, float] = {}
        self._access_counts: Dict[str, int] = {}

    def get_entity(self, entity_type: EntityType, entity_id: str) -> Optional[EntityReference]:
        """Get cached entity reference."""
        key = f"entity:{entity_type.value}:{entity_id}"
        with self._lock:
            entity = self._entity_cache.get(key)
            if entity:
                self._record_access(key)
            return entity

    def put_entity(self, entity: EntityReference) -> None:
        """Cache entity reference."""
        key = f"entity:{entity.entity_type.value}:{entity.entity_id}"
        with self._lock:
            self._entity_cache[key] = entity
            self._record_access(key)
            self._evict_if_needed()

    def get_assignments(
        self, entity_id: str, entity_type: EntityType
    ) -> Optional[List[PermissionAssignment]]:
        """Get cached assignments for entity."""
        key = f"assignments:{entity_type.value}:{entity_id}"
        with self._lock:
            assignments = self._assignment_cache.get(key)
            if assignments:
                self._record_access(key)
            return assignments

    def put_assignments(
        self, entity_id: str, entity_type: EntityType, assignments: List[PermissionAssignment]
    ) -> None:
        """Cache assignments for entity."""
        key = f"assignments:{entity_type.value}:{entity_id}"
        with self._lock:
            self._assignment_cache[key] = assignments
            self._record_access(key)
            self._evict_if_needed()

    def get_permission_set_info(self, permission_set_arn: str) -> Optional[Dict[str, Any]]:
        """Get cached permission set information."""
        with self._lock:
            info = self._permission_set_cache.get(permission_set_arn)
            if info:
                self._record_access(f"ps:{permission_set_arn}")
            return info

    def put_permission_set_info(self, permission_set_arn: str, info: Dict[str, Any]) -> None:
        """Cache permission set information."""
        key = f"ps:{permission_set_arn}"
        with self._lock:
            self._permission_set_cache[permission_set_arn] = info
            self._record_access(key)
            self._evict_if_needed()

    def get_account_name(self, account_id: str) -> Optional[str]:
        """Get cached account name."""
        with self._lock:
            name = self._account_cache.get(account_id)
            if name:
                self._record_access(f"account:{account_id}")
            return name

    def put_account_name(self, account_id: str, name: str) -> None:
        """Cache account name."""
        key = f"account:{account_id}"
        with self._lock:
            self._account_cache[account_id] = name
            self._record_access(key)
            self._evict_if_needed()

    def warm_entities(self, entities: List[EntityReference]) -> None:
        """Warm cache with entity references."""
        with self._lock:
            for entity in entities:
                self.put_entity(entity)

    def _record_access(self, key: str) -> None:
        """Record cache access for LRU tracking."""
        current_time = time.time()
        self._access_times[key] = current_time
        self._access_counts[key] = self._access_counts.get(key, 0) + 1

    def _evict_if_needed(self) -> None:
        """Evict least recently used items if cache is full."""
        total_items = (
            len(self._entity_cache)
            + len(self._assignment_cache)
            + len(self._permission_set_cache)
            + len(self._account_cache)
        )

        if total_items <= self.max_size:
            return

        # Find least recently used items
        items_to_evict = (
            total_items - self.max_size + 100
        )  # Evict extra to avoid frequent evictions

        # Sort by access time (oldest first)
        sorted_items = sorted(self._access_times.items(), key=lambda x: x[1])

        for key, _ in sorted_items[:items_to_evict]:
            self._evict_item(key)

    def _evict_item(self, key: str) -> None:
        """Evict a specific item from cache."""
        if key.startswith("entity:"):
            _, entity_type, entity_id = key.split(":", 2)
            cache_key = f"entity:{entity_type}:{entity_id}"
            self._entity_cache.pop(cache_key, None)
        elif key.startswith("assignments:"):
            _, entity_type, entity_id = key.split(":", 2)
            cache_key = f"assignments:{entity_type}:{entity_id}"
            self._assignment_cache.pop(cache_key, None)
        elif key.startswith("ps:"):
            permission_set_arn = key[3:]
            self._permission_set_cache.pop(permission_set_arn, None)
        elif key.startswith("account:"):
            account_id = key[8:]
            self._account_cache.pop(account_id, None)

        # Clean up tracking
        self._access_times.pop(key, None)
        self._access_counts.pop(key, None)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                "entity_cache_size": len(self._entity_cache),
                "assignment_cache_size": len(self._assignment_cache),
                "permission_set_cache_size": len(self._permission_set_cache),
                "account_cache_size": len(self._account_cache),
                "total_size": (
                    len(self._entity_cache)
                    + len(self._assignment_cache)
                    + len(self._permission_set_cache)
                    + len(self._account_cache)
                ),
                "max_size": self.max_size,
            }

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._entity_cache.clear()
            self._assignment_cache.clear()
            self._permission_set_cache.clear()
            self._account_cache.clear()
            self._access_times.clear()
            self._access_counts.clear()


class BatchProcessor:
    """Batch processor for permission cloning operations."""

    def __init__(self, rate_limiter: RateLimiter, cache: OptimizedCache, config: BatchConfig):
        """Initialize batch processor."""
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.config = config
        self._executor: Optional[ThreadPoolExecutor] = None

    def __enter__(self):
        """Enter context manager."""
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        if self._executor:
            self._executor.shutdown(wait=True)

    def process_assignments_parallel(
        self,
        assignments: List[PermissionAssignment],
        target_entity: EntityReference,
        operation_func,
        metrics: PerformanceMetrics,
    ) -> Tuple[List[PermissionAssignment], List[str]]:
        """
        Process assignments in parallel batches.

        Args:
            assignments: List of assignments to process
            target_entity: Target entity for assignments
            operation_func: Function to execute for each assignment
            metrics: Performance metrics tracker

        Returns:
            Tuple of (successful_assignments, error_messages)
        """
        if not self._executor:
            raise RuntimeError("BatchProcessor must be used as context manager")

        successful_assignments = []
        error_messages = []

        # Split assignments into batches
        batches = self._create_batches(assignments, self.config.assignment_copy_batch_size)

        # Submit batch jobs
        future_to_batch = {}
        for batch in batches:
            future = self._executor.submit(
                self._process_assignment_batch, batch, target_entity, operation_func, metrics
            )
            future_to_batch[future] = batch

        # Collect results
        for future in as_completed(future_to_batch):
            try:
                batch_successful, batch_errors = future.result()
                successful_assignments.extend(batch_successful)
                error_messages.extend(batch_errors)
            except Exception as e:
                batch = future_to_batch[future]
                error_msg = f"Batch processing failed for {len(batch)} assignments: {str(e)}"
                error_messages.append(error_msg)
                logger.error(error_msg)

        return successful_assignments, error_messages

    def resolve_entities_parallel(
        self,
        entity_references: List[Tuple[EntityType, str]],
        resolver_func,
        metrics: PerformanceMetrics,
    ) -> Dict[str, Optional[EntityReference]]:
        """
        Resolve entities in parallel batches.

        Args:
            entity_references: List of (entity_type, entity_id) tuples
            resolver_func: Function to resolve entities
            metrics: Performance metrics tracker

        Returns:
            Dictionary mapping entity_id to resolved EntityReference
        """
        if not self._executor:
            raise RuntimeError("BatchProcessor must be used as context manager")

        results = {}

        # Split entity references into batches
        batches = self._create_batches(entity_references, self.config.entity_resolution_batch_size)

        # Submit batch jobs
        future_to_batch = {}
        for batch in batches:
            future = self._executor.submit(
                self._resolve_entity_batch, batch, resolver_func, metrics
            )
            future_to_batch[future] = batch

        # Collect results
        for future in as_completed(future_to_batch):
            try:
                batch_results = future.result()
                results.update(batch_results)
            except Exception as e:
                batch = future_to_batch[future]
                logger.error(f"Entity resolution batch failed for {len(batch)} entities: {str(e)}")
                # Add None results for failed batch
                for entity_type, entity_id in batch:
                    results[entity_id] = None

        return results

    def _process_assignment_batch(
        self,
        assignments: List[PermissionAssignment],
        target_entity: EntityReference,
        operation_func,
        metrics: PerformanceMetrics,
    ) -> Tuple[List[PermissionAssignment], List[str]]:
        """Process a batch of assignments."""
        successful_assignments = []
        error_messages = []

        for assignment in assignments:
            try:
                # Apply rate limiting
                delay_ms = self.rate_limiter.acquire("sso_admin")
                metrics.rate_limit_delays_ms += delay_ms

                # Execute operation with retry logic
                success = self._execute_with_retry(
                    operation_func, target_entity, assignment, metrics
                )

                if success:
                    successful_assignments.append(assignment)
                    metrics.processed_assignments += 1
                else:
                    metrics.failed_assignments += 1
                    error_messages.append(
                        f"Failed to process assignment: {assignment.permission_set_name}"
                    )

                metrics.api_calls += 1

            except Exception as e:
                metrics.failed_assignments += 1
                error_msg = (
                    f"Error processing assignment {assignment.permission_set_name}: {str(e)}"
                )
                error_messages.append(error_msg)
                logger.error(error_msg)

        return successful_assignments, error_messages

    def _resolve_entity_batch(
        self,
        entity_references: List[Tuple[EntityType, str]],
        resolver_func,
        metrics: PerformanceMetrics,
    ) -> Dict[str, Optional[EntityReference]]:
        """Resolve a batch of entities."""
        results = {}

        for entity_type, entity_id in entity_references:
            try:
                # Check cache first
                cached_entity = self.cache.get_entity(entity_type, entity_id)
                if cached_entity:
                    results[entity_id] = cached_entity
                    metrics.cached_lookups += 1
                    continue

                # Apply rate limiting
                delay_ms = self.rate_limiter.acquire("identity_store")
                metrics.rate_limit_delays_ms += delay_ms

                # Resolve entity
                start_time = time.time()
                entity = resolver_func(entity_type, entity_id)
                metrics.entity_resolution_time_ms += (time.time() - start_time) * 1000

                # Cache result
                if entity:
                    self.cache.put_entity(entity)

                results[entity_id] = entity
                metrics.api_calls += 1

            except Exception as e:
                logger.error(f"Error resolving entity {entity_id}: {str(e)}")
                results[entity_id] = None

        return results

    def _execute_with_retry(
        self,
        operation_func,
        target_entity: EntityReference,
        assignment: PermissionAssignment,
        metrics: PerformanceMetrics,
    ) -> bool:
        """Execute operation with exponential backoff retry."""
        backoff_ms = self.rate_limiter.config.initial_backoff_ms

        for attempt in range(self.rate_limiter.config.max_retries + 1):
            try:
                start_time = time.time()
                operation_func(target_entity, assignment)
                metrics.assignment_creation_time_ms += (time.time() - start_time) * 1000
                return True

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                # Don't retry on certain errors
                if error_code in [
                    "ValidationException",
                    "ConflictException",
                    "ResourceNotFoundException",
                ]:
                    logger.warning(
                        f"Non-retryable error for assignment {assignment.permission_set_name}: {error_code}"
                    )
                    return False

                # Retry on throttling and server errors
                if error_code in [
                    "ThrottlingException",
                    "TooManyRequestsException",
                ] or error_code.startswith("5"):
                    if attempt < self.rate_limiter.config.max_retries:
                        metrics.retry_attempts += 1
                        time.sleep(backoff_ms / 1000.0)
                        backoff_ms = min(
                            backoff_ms * self.rate_limiter.config.backoff_multiplier,
                            self.rate_limiter.config.max_backoff_ms,
                        )
                        continue

                logger.error(
                    f"Error creating assignment {assignment.permission_set_name}: {str(e)}"
                )
                return False

            except Exception as e:
                logger.error(
                    f"Unexpected error creating assignment {assignment.permission_set_name}: {str(e)}"
                )
                return False

        return False

    def _create_batches(self, items: List[Any], batch_size: int) -> List[List[Any]]:
        """Split items into batches of specified size."""
        batches = []
        for i in range(0, len(items), batch_size):
            batches.append(items[i : i + batch_size])
        return batches


class StreamProcessor:
    """Stream processor for large assignment lists."""

    def __init__(self, batch_processor: BatchProcessor, config: BatchConfig):
        """Initialize stream processor."""
        self.batch_processor = batch_processor
        self.config = config

    def process_large_assignment_list(
        self,
        assignments: List[PermissionAssignment],
        target_entity: EntityReference,
        operation_func,
        metrics: PerformanceMetrics,
        progress_callback: Optional[callable] = None,
    ) -> Tuple[List[PermissionAssignment], List[str]]:
        """
        Process large assignment lists using streaming approach.

        Args:
            assignments: List of assignments to process
            target_entity: Target entity for assignments
            operation_func: Function to execute for each assignment
            metrics: Performance metrics tracker
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (successful_assignments, error_messages)
        """
        if len(assignments) < self.config.stream_threshold:
            # Use regular batch processing for smaller lists
            with self.batch_processor as bp:
                return bp.process_assignments_parallel(
                    assignments, target_entity, operation_func, metrics
                )

        logger.info(f"Using stream processing for {len(assignments)} assignments")

        successful_assignments = []
        error_messages = []

        # Process in chunks to manage memory
        chunk_size = self.config.stream_threshold
        total_chunks = (len(assignments) + chunk_size - 1) // chunk_size

        for chunk_idx in range(total_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(assignments))
            chunk = assignments[start_idx:end_idx]

            logger.info(
                f"Processing chunk {chunk_idx + 1}/{total_chunks} ({len(chunk)} assignments)"
            )

            # Process chunk
            with self.batch_processor as bp:
                chunk_successful, chunk_errors = bp.process_assignments_parallel(
                    chunk, target_entity, operation_func, metrics
                )

            successful_assignments.extend(chunk_successful)
            error_messages.extend(chunk_errors)

            # Update progress
            if progress_callback:
                progress_callback(end_idx, len(assignments))

            # Memory management - force garbage collection between chunks
            import gc

            gc.collect()

        return successful_assignments, error_messages


class PerformanceOptimizer:
    """Main performance optimization coordinator."""

    def __init__(
        self,
        rate_limit_config: Optional[RateLimitConfig] = None,
        batch_config: Optional[BatchConfig] = None,
        cache_size: int = 10000,
    ):
        """Initialize performance optimizer."""
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.batch_config = batch_config or BatchConfig()

        self.rate_limiter = RateLimiter(self.rate_limit_config)
        self.cache = OptimizedCache(cache_size)

        # Performance tracking
        self._active_metrics: Dict[str, PerformanceMetrics] = {}
        self._metrics_lock = threading.Lock()

    def create_batch_processor(self) -> BatchProcessor:
        """Create a new batch processor instance."""
        return BatchProcessor(self.rate_limiter, self.cache, self.batch_config)

    def create_stream_processor(self) -> StreamProcessor:
        """Create a new stream processor instance."""
        batch_processor = self.create_batch_processor()
        return StreamProcessor(batch_processor, self.batch_config)

    def start_operation_metrics(self, operation_id: Optional[str] = None) -> str:
        """Start tracking metrics for an operation."""
        if not operation_id:
            operation_id = str(uuid4())

        with self._metrics_lock:
            metrics = PerformanceMetrics(
                operation_id=operation_id, start_time=datetime.now(timezone.utc)
            )
            self._active_metrics[operation_id] = metrics

        return operation_id

    def finish_operation_metrics(self, operation_id: str) -> Optional[PerformanceMetrics]:
        """Finish tracking metrics for an operation."""
        with self._metrics_lock:
            metrics = self._active_metrics.pop(operation_id, None)
            if metrics:
                metrics.end_time = datetime.now(timezone.utc)

        return metrics

    def get_operation_metrics(self, operation_id: str) -> Optional[PerformanceMetrics]:
        """Get current metrics for an operation."""
        with self._metrics_lock:
            return self._active_metrics.get(operation_id)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache.get_stats()

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.cache.clear()

    def warm_cache(self, entities: List[EntityReference]) -> None:
        """Warm cache with entity data."""
        self.cache.warm_entities(entities)

    def get_optimization_recommendations(self, metrics: PerformanceMetrics) -> List[str]:
        """Get optimization recommendations based on metrics."""
        recommendations = []

        if not metrics.duration_ms:
            return recommendations

        # Analyze throughput
        if metrics.assignments_per_second and metrics.assignments_per_second < 2.0:
            recommendations.append("Consider increasing batch size to improve throughput")

        # Analyze success rate
        if metrics.success_rate < 95.0:
            recommendations.append(
                "High failure rate detected - consider reducing batch size or checking AWS permissions"
            )

        # Analyze cache hit rate
        if metrics.api_calls > 0:
            cache_hit_rate = (
                metrics.cached_lookups / (metrics.cached_lookups + metrics.api_calls)
            ) * 100
            if cache_hit_rate < 50.0:
                recommendations.append(
                    "Low cache hit rate - consider warming cache before operations"
                )

        # Analyze rate limiting impact
        if metrics.rate_limit_delays_ms > (
            metrics.duration_ms * 0.1
        ):  # More than 10% of time spent waiting
            recommendations.append(
                "Significant time spent on rate limiting - consider reducing concurrency"
            )

        # Analyze retry rate
        if metrics.retry_attempts > (metrics.total_assignments * 0.05):  # More than 5% retry rate
            recommendations.append(
                "High retry rate detected - consider reducing batch size or checking network connectivity"
            )

        return recommendations
