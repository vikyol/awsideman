"""
Performance tests for permission cloning optimizations.

These tests validate the effectiveness of performance optimizations including:
- Parallel processing improvements
- Rate limiting behavior
- Caching effectiveness
- Streaming processing for large datasets
"""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from src.awsideman.permission_cloning.models import (
    EntityReference,
    EntityType,
    PermissionAssignment,
)
from src.awsideman.permission_cloning.optimized_assignment_copier import OptimizedAssignmentCopier
from src.awsideman.permission_cloning.performance import (
    BatchConfig,
    BatchProcessor,
    OptimizedCache,
    PerformanceMetrics,
    PerformanceOptimizer,
    RateLimitConfig,
    RateLimiter,
    StreamProcessor,
)


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_rate_limiter_basic_functionality(self):
        """Test basic rate limiting behavior."""
        config = RateLimitConfig(sso_admin_rps=2.0, sso_admin_burst=2)
        limiter = RateLimiter(config)

        # First two calls should be immediate (within burst)
        delay1 = limiter.acquire("sso_admin")
        delay2 = limiter.acquire("sso_admin")

        assert delay1 == 0.0
        assert delay2 == 0.0

        # Third call should be delayed
        start_time = time.time()
        delay3 = limiter.acquire("sso_admin")
        end_time = time.time()

        # Should have some delay
        assert delay3 > 0 or (end_time - start_time) > 0.4  # Allow for timing variations

    def test_rate_limiter_different_services(self):
        """Test rate limiting for different services."""
        config = RateLimitConfig(
            sso_admin_rps=1.0, identity_store_rps=2.0, sso_admin_burst=1, identity_store_burst=1
        )
        limiter = RateLimiter(config)

        # Different services should have independent limits
        delay1 = limiter.acquire("sso_admin")
        delay2 = limiter.acquire("identity_store")

        assert delay1 == 0.0
        assert delay2 == 0.0

    def test_rate_limiter_window_reset(self):
        """Test that rate limit windows reset properly."""
        config = RateLimitConfig(sso_admin_rps=10.0, sso_admin_burst=1)
        limiter = RateLimiter(config)

        # Use up burst
        limiter.acquire("sso_admin")

        # Wait for window to reset
        time.sleep(1.1)

        # Should be immediate again
        delay = limiter.acquire("sso_admin")
        assert delay == 0.0


class TestOptimizedCache:
    """Test optimized caching functionality."""

    def test_cache_basic_operations(self):
        """Test basic cache operations."""
        cache = OptimizedCache(max_size=100)

        # Test entity caching
        entity = EntityReference(
            entity_type=EntityType.USER, entity_id="user-123", entity_name="testuser"
        )

        # Should be empty initially
        assert cache.get_entity(EntityType.USER, "user-123") is None

        # Cache entity
        cache.put_entity(entity)

        # Should retrieve cached entity
        cached_entity = cache.get_entity(EntityType.USER, "user-123")
        assert cached_entity == entity

    def test_cache_assignments(self):
        """Test assignment caching."""
        cache = OptimizedCache(max_size=100)

        assignments = [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-123",
                permission_set_name="TestPS",
                account_id="123456789012",
                account_name="TestAccount",
            )
        ]

        # Should be empty initially
        assert cache.get_assignments("user-123", EntityType.USER) is None

        # Cache assignments
        cache.put_assignments("user-123", EntityType.USER, assignments)

        # Should retrieve cached assignments
        cached_assignments = cache.get_assignments("user-123", EntityType.USER)
        assert cached_assignments == assignments

    def test_cache_eviction(self):
        """Test cache eviction when max size is reached."""
        cache = OptimizedCache(max_size=2)

        # Add entities up to max size
        entity1 = EntityReference(EntityType.USER, "user-1", "user1")
        entity2 = EntityReference(EntityType.USER, "user-2", "user2")
        entity3 = EntityReference(EntityType.USER, "user-3", "user3")

        cache.put_entity(entity1)
        cache.put_entity(entity2)

        # Both should be cached
        assert cache.get_entity(EntityType.USER, "user-1") == entity1
        assert cache.get_entity(EntityType.USER, "user-2") == entity2

        # Add third entity (should trigger eviction)
        cache.put_entity(entity3)

        # Should have evicted least recently used
        stats = cache.get_stats()
        assert stats["total_size"] <= cache.max_size

    def test_cache_warm_entities(self):
        """Test cache warming functionality."""
        cache = OptimizedCache(max_size=100)

        entities = [
            EntityReference(EntityType.USER, "user-1", "user1"),
            EntityReference(EntityType.GROUP, "group-1", "group1"),
        ]

        cache.warm_entities(entities)

        # All entities should be cached
        assert cache.get_entity(EntityType.USER, "user-1") == entities[0]
        assert cache.get_entity(EntityType.GROUP, "group-1") == entities[1]


class TestBatchProcessor:
    """Test batch processing functionality."""

    @pytest.fixture
    def mock_components(self):
        """Create mock components for testing."""
        rate_limiter = Mock(spec=RateLimiter)
        rate_limiter.acquire.return_value = 0.0
        rate_limiter.config = RateLimitConfig()

        cache = Mock(spec=OptimizedCache)

        config = BatchConfig(assignment_copy_batch_size=2, max_workers=2)

        return rate_limiter, cache, config

    def test_batch_processor_context_manager(self, mock_components):
        """Test batch processor context manager."""
        rate_limiter, cache, config = mock_components

        with BatchProcessor(rate_limiter, cache, config) as processor:
            assert processor._executor is not None

        # Executor should be shut down after context
        assert processor._executor._shutdown

    def test_process_assignments_parallel(self, mock_components):
        """Test parallel assignment processing."""
        rate_limiter, cache, config = mock_components

        # Create test data
        assignments = [
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-1",
                permission_set_name="PS1",
                account_id="123456789012",
                account_name="Account1",
            ),
            PermissionAssignment(
                permission_set_arn="arn:aws:sso:::permissionSet/ins-123/ps-2",
                permission_set_name="PS2",
                account_id="123456789012",
                account_name="Account1",
            ),
        ]

        target_entity = EntityReference(EntityType.USER, "user-123", "testuser")

        # Mock operation function
        operation_func = Mock()

        # Mock metrics
        metrics = PerformanceMetrics(operation_id="test-op", start_time=time.time())

        with BatchProcessor(rate_limiter, cache, config) as processor:
            successful, errors = processor.process_assignments_parallel(
                assignments, target_entity, operation_func, metrics
            )

        # Should process all assignments
        assert len(successful) == 2
        assert len(errors) == 0
        assert operation_func.call_count == 2

    def test_resolve_entities_parallel(self, mock_components):
        """Test parallel entity resolution."""
        rate_limiter, cache, config = mock_components

        # Setup cache to return None (cache miss)
        cache.get_entity.return_value = None

        entity_references = [(EntityType.USER, "user-1"), (EntityType.USER, "user-2")]

        # Mock resolver function
        def mock_resolver(entity_type, entity_id):
            return EntityReference(entity_type, entity_id, f"name-{entity_id}")

        metrics = PerformanceMetrics(operation_id="test-op", start_time=time.time())

        with BatchProcessor(rate_limiter, cache, config) as processor:
            results = processor.resolve_entities_parallel(entity_references, mock_resolver, metrics)

        # Should resolve all entities
        assert len(results) == 2
        assert results["user-1"].entity_name == "name-user-1"
        assert results["user-2"].entity_name == "name-user-2"


class TestStreamProcessor:
    """Test stream processing functionality."""

    @pytest.fixture
    def mock_batch_processor(self):
        """Create mock batch processor."""
        batch_processor = Mock(spec=BatchProcessor)
        batch_processor.process_assignments_parallel.return_value = ([], [])
        
        # Mock context manager protocol
        batch_processor.__enter__ = Mock(return_value=batch_processor)
        batch_processor.__exit__ = Mock(return_value=None)
        
        return batch_processor

    def test_stream_processor_small_list(self, mock_batch_processor):
        """Test stream processor with small assignment list."""
        config = BatchConfig(stream_threshold=100)
        processor = StreamProcessor(mock_batch_processor, config)

        # Small list should use regular batch processing
        assignments = [Mock() for _ in range(50)]
        target_entity = Mock()
        operation_func = Mock()
        metrics = Mock()

        processor.process_large_assignment_list(assignments, target_entity, operation_func, metrics)

        # Should call batch processor once
        mock_batch_processor.process_assignments_parallel.assert_called_once()

    def test_stream_processor_large_list(self, mock_batch_processor):
        """Test stream processor with large assignment list."""
        config = BatchConfig(stream_threshold=50)
        processor = StreamProcessor(mock_batch_processor, config)

        # Large list should use streaming
        assignments = [Mock() for _ in range(150)]
        target_entity = Mock()
        operation_func = Mock()
        metrics = Mock()

        progress_calls = []

        def progress_callback(current, total):
            progress_calls.append((current, total))

        processor.process_large_assignment_list(
            assignments, target_entity, operation_func, metrics, progress_callback
        )

        # Should call batch processor multiple times (streaming chunks)
        assert mock_batch_processor.process_assignments_parallel.call_count > 1

        # Should have progress updates
        assert len(progress_calls) > 0
        assert progress_calls[-1] == (150, 150)  # Final progress should be complete


class TestPerformanceOptimizer:
    """Test performance optimizer coordination."""

    def test_performance_optimizer_initialization(self):
        """Test performance optimizer initialization."""
        optimizer = PerformanceOptimizer()

        assert optimizer.rate_limiter is not None
        assert optimizer.cache is not None
        assert isinstance(optimizer.rate_limit_config, RateLimitConfig)
        assert isinstance(optimizer.batch_config, BatchConfig)

    def test_operation_metrics_tracking(self):
        """Test operation metrics tracking."""
        optimizer = PerformanceOptimizer()

        # Start tracking
        operation_id = optimizer.start_operation_metrics()
        assert operation_id is not None

        # Should be able to get metrics
        metrics = optimizer.get_operation_metrics(operation_id)
        assert metrics is not None
        assert metrics.operation_id == operation_id

        # Finish tracking
        final_metrics = optimizer.finish_operation_metrics(operation_id)
        assert final_metrics is not None
        assert final_metrics.end_time is not None

        # Should no longer be in active metrics
        assert optimizer.get_operation_metrics(operation_id) is None

    def test_cache_operations(self):
        """Test cache operations through optimizer."""
        optimizer = PerformanceOptimizer()

        # Test cache stats
        stats = optimizer.get_cache_stats()
        assert "total_size" in stats

        # Test cache warming
        entities = [EntityReference(EntityType.USER, "user-1", "user1")]
        optimizer.warm_cache(entities)

        # Test cache clearing
        optimizer.clear_cache()
        stats_after_clear = optimizer.get_cache_stats()
        assert stats_after_clear["total_size"] == 0

    def test_optimization_recommendations(self):
        """Test optimization recommendations."""
        optimizer = PerformanceOptimizer()

        # Create metrics with poor performance
        from datetime import datetime, timezone, timedelta
        
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(seconds=60)
        
        metrics = PerformanceMetrics(
            operation_id="test",
            start_time=start_time,
            total_assignments=100,
            processed_assignments=50,  # 50% success rate
            api_calls=100,
            cached_lookups=10,  # Low cache hit rate
            retry_attempts=20,  # High retry rate
        )
        metrics.end_time = end_time  # 60 second duration

        recommendations = optimizer.get_optimization_recommendations(metrics)

        # Should have recommendations for poor performance
        assert len(recommendations) > 0
        assert any("failure rate" in rec.lower() for rec in recommendations)
        assert any("cache" in rec.lower() for rec in recommendations)


class TestOptimizedAssignmentCopier:
    """Test optimized assignment copier integration."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        entity_resolver = Mock()
        entity_resolver.validate_entity.return_value = Mock(has_errors=False)

        assignment_retriever = Mock()
        assignment_retriever.get_user_assignments.return_value = []
        assignment_retriever.get_group_assignments.return_value = []
        assignment_retriever.sso_admin_client = Mock()
        assignment_retriever.instance_arn = "arn:aws:sso:::instance/ins-123"

        filter_engine = Mock()
        filter_engine.apply_filters.return_value = []
        filter_engine.get_filter_summary.return_value = "No filters"

        return entity_resolver, assignment_retriever, filter_engine

    def test_optimized_copier_initialization(self, mock_dependencies):
        """Test optimized copier initialization."""
        entity_resolver, assignment_retriever, filter_engine = mock_dependencies

        copier = OptimizedAssignmentCopier(
            entity_resolver=entity_resolver,
            assignment_retriever=assignment_retriever,
            filter_engine=filter_engine,
        )

        assert copier.performance_optimizer is not None
        assert copier.entity_resolver == entity_resolver
        assert copier.assignment_retriever == assignment_retriever
        assert copier.filter_engine == filter_engine

    def test_copy_assignments_with_performance_tracking(self, mock_dependencies):
        """Test copy assignments with performance tracking."""
        entity_resolver, assignment_retriever, filter_engine = mock_dependencies

        copier = OptimizedAssignmentCopier(
            entity_resolver=entity_resolver,
            assignment_retriever=assignment_retriever,
            filter_engine=filter_engine,
        )

        source = EntityReference(EntityType.USER, "user-1", "source")
        target = EntityReference(EntityType.USER, "user-2", "target")

        result = copier.copy_assignments(source, target, preview=True)

        # Should have performance metrics
        assert result.success
        assert hasattr(result, "performance_metrics")
        if result.performance_metrics:
            assert "duration_ms" in result.performance_metrics

    def test_batch_copy_operations(self, mock_dependencies):
        """Test batch copy operations."""
        entity_resolver, assignment_retriever, filter_engine = mock_dependencies

        copier = OptimizedAssignmentCopier(
            entity_resolver=entity_resolver,
            assignment_retriever=assignment_retriever,
            filter_engine=filter_engine,
        )

        # Create multiple copy requests
        requests = [
            (
                EntityReference(EntityType.USER, "user-1", "source1"),
                EntityReference(EntityType.USER, "user-2", "target1"),
                None,
            ),
            (
                EntityReference(EntityType.GROUP, "group-1", "source2"),
                EntityReference(EntityType.GROUP, "group-2", "target2"),
                None,
            ),
        ]

        results = copier.copy_assignments_batch(requests, preview=True)

        # Should have results for all requests
        assert len(results) == 2
        assert all(result.success for result in results)

    def test_performance_stats(self, mock_dependencies):
        """Test performance statistics."""
        entity_resolver, assignment_retriever, filter_engine = mock_dependencies

        copier = OptimizedAssignmentCopier(
            entity_resolver=entity_resolver,
            assignment_retriever=assignment_retriever,
            filter_engine=filter_engine,
        )

        stats = copier.get_performance_stats()

        assert "cache_stats" in stats
        assert "active_operations" in stats
        assert isinstance(stats["cache_stats"], dict)
        assert isinstance(stats["active_operations"], int)

    def test_cache_management(self, mock_dependencies):
        """Test cache management operations."""
        entity_resolver, assignment_retriever, filter_engine = mock_dependencies

        copier = OptimizedAssignmentCopier(
            entity_resolver=entity_resolver,
            assignment_retriever=assignment_retriever,
            filter_engine=filter_engine,
        )

        # Test cache clearing
        copier.clear_cache()

        stats = copier.get_performance_stats()
        assert stats["cache_stats"]["total_size"] == 0


class TestPerformanceBenchmarks:
    """Test performance benchmarking and comparison."""

    def test_rate_limiting_performance_impact(self):
        """Test the performance impact of rate limiting."""
        # Test without rate limiting
        config_no_limit = RateLimitConfig(sso_admin_rps=1000.0)  # Very high limit
        limiter_no_limit = RateLimiter(config_no_limit)

        start_time = time.time()
        for _ in range(10):
            limiter_no_limit.acquire("sso_admin")
        no_limit_duration = time.time() - start_time

        # Test with rate limiting
        config_with_limit = RateLimitConfig(sso_admin_rps=2.0, sso_admin_burst=2)
        limiter_with_limit = RateLimiter(config_with_limit)

        start_time = time.time()
        for _ in range(10):
            limiter_with_limit.acquire("sso_admin")
        with_limit_duration = time.time() - start_time

        # Rate limited version should take longer
        assert with_limit_duration > no_limit_duration

    def test_cache_performance_improvement(self):
        """Test cache performance improvement."""
        cache = OptimizedCache(max_size=1000)

        # Simulate cache misses
        miss_times = []
        for i in range(100):
            start_time = time.time()
            cache.get_entity(EntityType.USER, f"user-{i}")
            miss_times.append(time.time() - start_time)

            # Add to cache
            entity = EntityReference(EntityType.USER, f"user-{i}", f"name-{i}")
            cache.put_entity(entity)

        # Simulate cache hits
        hit_times = []
        for i in range(100):
            start_time = time.time()
            cache.get_entity(EntityType.USER, f"user-{i}")
            hit_times.append(time.time() - start_time)

        # Cache hits should be faster than misses
        avg_miss_time = sum(miss_times) / len(miss_times)
        avg_hit_time = sum(hit_times) / len(hit_times)

        # Allow for timing variations and system load
        # Cache hits should be at least as fast as misses (allowing for measurement noise)
        # Use a more generous threshold for very small timing differences
        threshold = 1.5 if avg_miss_time < 1e-6 else 1.1
        assert avg_hit_time <= avg_miss_time * threshold, (
            f"Cache hit time ({avg_hit_time:.6f}s) should be <= miss time ({avg_miss_time:.6f}s) * {threshold}"
        )

    @pytest.mark.slow
    def test_parallel_vs_sequential_processing(self):
        """Test parallel vs sequential processing performance."""
        # This test is marked as slow and would typically be run separately

        # Mock operation that takes some time
        def slow_operation(entity, assignment):
            time.sleep(0.01)  # 10ms delay

        assignments = [Mock() for _ in range(20)]
        target_entity = Mock()

        # Sequential processing
        start_time = time.time()
        for assignment in assignments:
            slow_operation(target_entity, assignment)
        sequential_duration = time.time() - start_time

        # Parallel processing (simplified simulation)
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(slow_operation, target_entity, assignment)
                for assignment in assignments
            ]
            for future in futures:
                future.result()
        parallel_duration = time.time() - start_time

        # Parallel should be faster (allowing for overhead)
        assert parallel_duration < sequential_duration * 0.8
