"""
Performance optimization components for backup and restore operations.

This module provides parallel processing, compression, deduplication,
and resource monitoring capabilities to optimize backup and restore performance.
"""

import asyncio
import gc
import gzip
import hashlib
import logging
import multiprocessing
import threading
import time
import zlib
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import lz4.frame
import psutil

from .interfaces import (
    CompressionProviderInterface,
    DeduplicationProviderInterface,
    PerformanceOptimizerInterface,
)
from .models import BackupData, PerformanceMetrics, ResourceUsageMetrics

logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    """Result of compression operation."""

    compressed_data: bytes
    original_size: int
    compressed_size: int
    compression_ratio: float
    compression_time: float
    algorithm: str


@dataclass
class DeduplicationResult:
    """Result of deduplication operation."""

    deduplicated_data: bytes
    original_size: int
    deduplicated_size: int
    deduplication_ratio: float
    duplicate_blocks: int
    unique_blocks: int
    processing_time: float


@dataclass
class ParallelProcessingResult:
    """Result of parallel processing operation."""

    results: List[Any]
    total_time: float
    worker_count: int
    success_count: int
    error_count: int
    errors: List[str]


class CompressionProvider(CompressionProviderInterface):
    """
    Compression provider supporting multiple algorithms.

    Supports gzip, lz4, and zlib compression with automatic
    algorithm selection based on data characteristics.
    """

    ALGORITHMS = {
        "gzip": {"compress": gzip.compress, "decompress": gzip.decompress, "level": 6},
        "lz4": {"compress": lz4.frame.compress, "decompress": lz4.frame.decompress, "level": None},
        "zlib": {"compress": zlib.compress, "decompress": zlib.decompress, "level": 6},
    }

    def __init__(self, default_algorithm: str = "lz4", compression_level: Optional[int] = None):
        """
        Initialize compression provider.

        Args:
            default_algorithm: Default compression algorithm to use
            compression_level: Compression level (algorithm-specific)
        """
        self.default_algorithm = default_algorithm
        self.compression_level = compression_level
        self._compression_stats = {}
        self._stats_lock = Lock()

    async def compress(self, data: bytes, algorithm: Optional[str] = None) -> CompressionResult:
        """
        Compress data using specified or default algorithm.

        Args:
            data: Data to compress
            algorithm: Compression algorithm to use

        Returns:
            CompressionResult with compression details
        """
        algorithm = algorithm or self.default_algorithm
        if algorithm not in self.ALGORITHMS:
            raise ValueError(f"Unsupported compression algorithm: {algorithm}")

        start_time = time.time()
        original_size = len(data)

        try:
            # Get compression function and parameters
            algo_config = self.ALGORITHMS[algorithm]
            compress_func = algo_config["compress"]

            # Apply compression level if supported
            if algorithm in ["gzip", "zlib"] and self.compression_level is not None:
                compressed_data = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: compress_func(data, self.compression_level)
                )
            else:
                compressed_data = await asyncio.get_event_loop().run_in_executor(
                    None, compress_func, data
                )

            compressed_size = len(compressed_data)
            compression_time = time.time() - start_time
            compression_ratio = original_size / compressed_size if compressed_size > 0 else 1.0

            # Update statistics
            with self._stats_lock:
                if algorithm not in self._compression_stats:
                    self._compression_stats[algorithm] = {
                        "total_operations": 0,
                        "total_original_size": 0,
                        "total_compressed_size": 0,
                        "total_time": 0.0,
                        "average_ratio": 0.0,
                    }

                stats = self._compression_stats[algorithm]
                stats["total_operations"] += 1
                stats["total_original_size"] += original_size
                stats["total_compressed_size"] += compressed_size
                stats["total_time"] += compression_time
                stats["average_ratio"] = (
                    stats["total_original_size"] / stats["total_compressed_size"]
                )

            logger.debug(
                f"Compressed {original_size} bytes to {compressed_size} bytes "
                f"using {algorithm} (ratio: {compression_ratio:.2f})"
            )

            return CompressionResult(
                compressed_data=compressed_data,
                original_size=original_size,
                compressed_size=compressed_size,
                compression_ratio=compression_ratio,
                compression_time=compression_time,
                algorithm=algorithm,
            )

        except Exception as e:
            logger.error(f"Compression failed with {algorithm}: {e}")
            raise

    async def decompress(self, data: bytes, algorithm: str) -> bytes:
        """
        Decompress data using specified algorithm.

        Args:
            data: Compressed data
            algorithm: Algorithm used for compression

        Returns:
            Decompressed data
        """
        if algorithm not in self.ALGORITHMS:
            raise ValueError(f"Unsupported compression algorithm: {algorithm}")

        try:
            decompress_func = self.ALGORITHMS[algorithm]["decompress"]
            decompressed_data = await asyncio.get_event_loop().run_in_executor(
                None, decompress_func, data
            )

            logger.debug(
                f"Decompressed {len(data)} bytes to {len(decompressed_data)} bytes using {algorithm}"
            )
            return decompressed_data

        except Exception as e:
            logger.error(f"Decompression failed with {algorithm}: {e}")
            raise

    def get_best_algorithm(self, data_sample: bytes) -> str:
        """
        Determine the best compression algorithm for given data.

        Args:
            data_sample: Sample of data to analyze

        Returns:
            Best algorithm name
        """
        if len(data_sample) < 1024:  # Small data, use fast compression
            return "lz4"

        # Test compression ratios with small sample
        test_sample = data_sample[:4096]  # Test with first 4KB
        best_algorithm = "lz4"
        best_ratio = 1.0

        for algorithm in ["lz4", "gzip", "zlib"]:
            try:
                algo_config = self.ALGORITHMS[algorithm]
                compress_func = algo_config["compress"]
                compressed = compress_func(test_sample)
                ratio = len(test_sample) / len(compressed)

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_algorithm = algorithm

            except Exception:
                continue

        logger.debug(f"Selected {best_algorithm} algorithm (ratio: {best_ratio:.2f})")
        return best_algorithm

    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression statistics."""
        with self._stats_lock:
            return dict(self._compression_stats)


class DeduplicationProvider(DeduplicationProviderInterface):
    """
    Deduplication provider using content-based chunking.

    Implements block-level deduplication to reduce storage requirements
    for similar backup data.
    """

    def __init__(self, block_size: int = 4096, hash_algorithm: str = "sha256"):
        """
        Initialize deduplication provider.

        Args:
            block_size: Size of blocks for deduplication
            hash_algorithm: Hash algorithm for block identification
        """
        self.block_size = block_size
        self.hash_algorithm = hash_algorithm
        self._block_cache: Dict[str, bytes] = {}
        self._cache_lock = Lock()
        self._dedup_stats = {
            "total_operations": 0,
            "total_blocks_processed": 0,
            "duplicate_blocks_found": 0,
            "cache_hits": 0,
            "cache_size": 0,
        }

    async def deduplicate(self, data: bytes) -> DeduplicationResult:
        """
        Deduplicate data by identifying and removing duplicate blocks.

        Args:
            data: Data to deduplicate

        Returns:
            DeduplicationResult with deduplication details
        """
        start_time = time.time()
        original_size = len(data)

        # Split data into blocks
        blocks = []
        block_hashes = []
        unique_blocks = {}
        duplicate_count = 0

        for i in range(0, len(data), self.block_size):
            block = data[i : i + self.block_size]
            block_hash = hashlib.new(self.hash_algorithm, block).hexdigest()

            blocks.append(block_hash)
            block_hashes.append(block_hash)

            with self._cache_lock:
                if block_hash in self._block_cache:
                    # Block already exists in cache
                    duplicate_count += 1
                    self._dedup_stats["cache_hits"] += 1
                elif block_hash in unique_blocks:
                    # Block already seen in this data
                    duplicate_count += 1
                else:
                    # New unique block
                    unique_blocks[block_hash] = block
                    self._block_cache[block_hash] = block

        # Create deduplicated data structure
        dedup_data = {
            "block_hashes": block_hashes,
            "unique_blocks": unique_blocks,
            "block_size": self.block_size,
            "hash_algorithm": self.hash_algorithm,
        }

        # Serialize deduplicated data
        import json

        deduplicated_data = json.dumps(
            dedup_data, default=lambda x: x.hex() if isinstance(x, bytes) else x
        ).encode()

        processing_time = time.time() - start_time
        deduplication_ratio = (
            original_size / len(deduplicated_data) if len(deduplicated_data) > 0 else 1.0
        )

        # Update statistics
        with self._cache_lock:
            self._dedup_stats["total_operations"] += 1
            self._dedup_stats["total_blocks_processed"] += len(blocks)
            self._dedup_stats["duplicate_blocks_found"] += duplicate_count
            self._dedup_stats["cache_size"] = len(self._block_cache)

        logger.debug(
            f"Deduplicated {original_size} bytes to {len(deduplicated_data)} bytes "
            f"(ratio: {deduplication_ratio:.2f}, duplicates: {duplicate_count})"
        )

        return DeduplicationResult(
            deduplicated_data=deduplicated_data,
            original_size=original_size,
            deduplicated_size=len(deduplicated_data),
            deduplication_ratio=deduplication_ratio,
            duplicate_blocks=duplicate_count,
            unique_blocks=len(unique_blocks),
            processing_time=processing_time,
        )

    async def rehydrate(self, deduplicated_data: bytes) -> bytes:
        """
        Rehydrate deduplicated data back to original form.

        Args:
            deduplicated_data: Deduplicated data to rehydrate

        Returns:
            Original data
        """
        try:
            import json

            dedup_data = json.loads(deduplicated_data.decode())

            block_hashes = dedup_data["block_hashes"]
            unique_blocks = {k: bytes.fromhex(v) for k, v in dedup_data["unique_blocks"].items()}

            # Reconstruct original data
            original_data = b""
            for block_hash in block_hashes:
                if block_hash in unique_blocks:
                    original_data += unique_blocks[block_hash]
                elif block_hash in self._block_cache:
                    original_data += self._block_cache[block_hash]
                else:
                    raise ValueError(f"Block {block_hash} not found in cache or unique blocks")

            logger.debug(f"Rehydrated {len(deduplicated_data)} bytes to {len(original_data)} bytes")
            return original_data

        except Exception as e:
            logger.error(f"Rehydration failed: {e}")
            raise

    def clear_cache(self):
        """Clear the deduplication cache."""
        with self._cache_lock:
            self._block_cache.clear()
            self._dedup_stats["cache_size"] = 0

    def get_deduplication_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        with self._cache_lock:
            return dict(self._dedup_stats)


class ResourceMonitor:
    """
    Resource usage monitor for tracking memory and CPU usage.

    Provides real-time monitoring of system resources during
    backup and restore operations.
    """

    def __init__(self, monitoring_interval: float = 1.0):
        """
        Initialize resource monitor.

        Args:
            monitoring_interval: Interval between monitoring samples in seconds
        """
        self.monitoring_interval = monitoring_interval
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._metrics: List[ResourceUsageMetrics] = []
        self._metrics_lock = Lock()
        self._process = psutil.Process()

    def start_monitoring(self):
        """Start resource monitoring."""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self._monitor_thread.start()
        logger.debug("Started resource monitoring")

    def stop_monitoring(self):
        """Stop resource monitoring."""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.debug("Stopped resource monitoring")

    def _monitor_resources(self):
        """Monitor system resources in background thread."""
        while self._monitoring:
            try:
                # Get current resource usage
                cpu_percent = self._process.cpu_percent()
                memory_info = self._process.memory_info()
                memory_percent = self._process.memory_percent()

                # Get system-wide metrics
                system_cpu = psutil.cpu_percent()
                system_memory = psutil.virtual_memory()

                # Get file descriptor count (Unix-like systems)
                try:
                    fd_count = len(self._process.open_files())
                except (psutil.AccessDenied, AttributeError):
                    fd_count = 0

                # Get thread count
                thread_count = self._process.num_threads()

                metrics = ResourceUsageMetrics(
                    timestamp=datetime.now(),
                    cpu_percent=cpu_percent,
                    memory_rss_mb=memory_info.rss / 1024 / 1024,
                    memory_vms_mb=memory_info.vms / 1024 / 1024,
                    memory_percent=memory_percent,
                    system_cpu_percent=system_cpu,
                    system_memory_percent=system_memory.percent,
                    file_descriptors=fd_count,
                    thread_count=thread_count,
                )

                with self._metrics_lock:
                    self._metrics.append(metrics)
                    # Keep only last 1000 samples to prevent memory growth
                    if len(self._metrics) > 1000:
                        self._metrics = self._metrics[-1000:]

                time.sleep(self.monitoring_interval)

            except Exception as e:
                logger.warning(f"Error monitoring resources: {e}")
                time.sleep(self.monitoring_interval)

    def get_current_metrics(self) -> Optional[ResourceUsageMetrics]:
        """Get the most recent resource metrics."""
        with self._metrics_lock:
            return self._metrics[-1] if self._metrics else None

    def get_metrics_history(
        self, duration: Optional[timedelta] = None
    ) -> List[ResourceUsageMetrics]:
        """
        Get resource metrics history.

        Args:
            duration: Optional duration to limit history

        Returns:
            List of resource metrics
        """
        with self._metrics_lock:
            if not duration:
                return list(self._metrics)

            cutoff_time = datetime.now() - duration
            return [m for m in self._metrics if m.timestamp >= cutoff_time]

    def get_peak_usage(self, duration: Optional[timedelta] = None) -> Dict[str, float]:
        """
        Get peak resource usage over specified duration.

        Args:
            duration: Optional duration to analyze

        Returns:
            Dictionary with peak usage metrics
        """
        metrics = self.get_metrics_history(duration)
        if not metrics:
            return {}

        return {
            "peak_cpu_percent": max(m.cpu_percent for m in metrics),
            "peak_memory_rss_mb": max(m.memory_rss_mb for m in metrics),
            "peak_memory_percent": max(m.memory_percent for m in metrics),
            "peak_system_cpu_percent": max(m.system_cpu_percent for m in metrics),
            "peak_system_memory_percent": max(m.system_memory_percent for m in metrics),
            "peak_file_descriptors": max(m.file_descriptors for m in metrics),
            "peak_thread_count": max(m.thread_count for m in metrics),
        }

    def clear_metrics(self):
        """Clear collected metrics."""
        with self._metrics_lock:
            self._metrics.clear()


class ParallelProcessor:
    """
    Parallel processing coordinator for backup and restore operations.

    Provides thread-based and process-based parallel execution
    with automatic worker scaling and error handling.
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        use_processes: bool = False,
        chunk_size: Optional[int] = None,
    ):
        """
        Initialize parallel processor.

        Args:
            max_workers: Maximum number of workers (defaults to CPU count)
            use_processes: Whether to use processes instead of threads
            chunk_size: Size of work chunks for batch processing
        """
        self.max_workers = max_workers or min(32, (multiprocessing.cpu_count() or 1) + 4)
        self.use_processes = use_processes
        self.chunk_size = chunk_size or 100
        self._executor: Optional[Union[ThreadPoolExecutor, ProcessPoolExecutor]] = None

    async def process_parallel(
        self, func: Callable, items: List[Any], *args, **kwargs
    ) -> ParallelProcessingResult:
        """
        Process items in parallel using the specified function.

        Args:
            func: Function to apply to each item
            items: List of items to process
            *args: Additional arguments for the function
            **kwargs: Additional keyword arguments for the function

        Returns:
            ParallelProcessingResult with processing details
        """
        if not items:
            return ParallelProcessingResult(
                results=[],
                total_time=0.0,
                worker_count=0,
                success_count=0,
                error_count=0,
                errors=[],
            )

        start_time = time.time()
        results = []
        errors = []
        success_count = 0
        error_count = 0

        # Determine optimal worker count
        worker_count = min(self.max_workers, len(items))

        try:
            # Create executor
            if self.use_processes:
                executor = ProcessPoolExecutor(max_workers=worker_count)
            else:
                executor = ThreadPoolExecutor(max_workers=worker_count)

            self._executor = executor

            # Submit tasks
            future_to_item = {}
            for item in items:
                future = executor.submit(func, item, *args, **kwargs)
                future_to_item[future] = item

            # Collect results as they complete
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    result = future.result()
                    results.append(result)
                    success_count += 1
                except Exception as e:
                    error_msg = f"Error processing item {item}: {e}"
                    errors.append(error_msg)
                    error_count += 1
                    logger.warning(error_msg)

        except Exception as e:
            logger.error(f"Parallel processing failed: {e}")
            errors.append(f"Parallel processing error: {e}")
            error_count += 1

        finally:
            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None

        total_time = time.time() - start_time

        logger.info(
            f"Parallel processing completed: {success_count} success, {error_count} errors, "
            f"{total_time:.2f}s with {worker_count} workers"
        )

        return ParallelProcessingResult(
            results=results,
            total_time=total_time,
            worker_count=worker_count,
            success_count=success_count,
            error_count=error_count,
            errors=errors,
        )

    async def process_batched(
        self, func: Callable, items: List[Any], batch_size: Optional[int] = None, *args, **kwargs
    ) -> ParallelProcessingResult:
        """
        Process items in batches for memory efficiency.

        Args:
            func: Function to apply to each batch
            items: List of items to process
            batch_size: Size of each batch
            *args: Additional arguments for the function
            **kwargs: Additional keyword arguments for the function

        Returns:
            ParallelProcessingResult with processing details
        """
        batch_size = batch_size or self.chunk_size
        batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]

        return await self.process_parallel(func, batches, *args, **kwargs)

    def shutdown(self):
        """Shutdown the parallel processor."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


class PerformanceOptimizer(PerformanceOptimizerInterface):
    """
    Main performance optimizer coordinating all optimization techniques.

    Combines parallel processing, compression, deduplication, and
    resource monitoring for optimal backup and restore performance.
    """

    def __init__(
        self,
        enable_compression: bool = True,
        enable_deduplication: bool = True,
        enable_parallel_processing: bool = True,
        enable_resource_monitoring: bool = True,
        max_workers: Optional[int] = None,
        compression_algorithm: str = "lz4",
    ):
        """
        Initialize performance optimizer.

        Args:
            enable_compression: Whether to enable compression
            enable_deduplication: Whether to enable deduplication
            enable_parallel_processing: Whether to enable parallel processing
            enable_resource_monitoring: Whether to enable resource monitoring
            max_workers: Maximum number of parallel workers
            compression_algorithm: Default compression algorithm
        """
        self.enable_compression = enable_compression
        self.enable_deduplication = enable_deduplication
        self.enable_parallel_processing = enable_parallel_processing
        self.enable_resource_monitoring = enable_resource_monitoring

        # Initialize components
        self.compression_provider = (
            CompressionProvider(compression_algorithm) if enable_compression else None
        )
        self.deduplication_provider = DeduplicationProvider() if enable_deduplication else None
        self.parallel_processor = (
            ParallelProcessor(max_workers) if enable_parallel_processing else None
        )
        self.resource_monitor = ResourceMonitor() if enable_resource_monitoring else None

        # Performance metrics
        self._performance_metrics: List[PerformanceMetrics] = []
        self._metrics_lock = Lock()

    async def optimize_backup_data(self, backup_data: BackupData) -> Tuple[bytes, Dict[str, Any]]:
        """
        Optimize backup data using all enabled optimization techniques.

        Args:
            backup_data: Backup data to optimize

        Returns:
            Tuple of (optimized_data, optimization_metadata)
        """
        start_time = time.time()
        optimization_metadata = {
            "original_size": 0,
            "final_size": 0,
            "compression_applied": False,
            "deduplication_applied": False,
            "optimization_time": 0.0,
        }

        # Start resource monitoring
        if self.resource_monitor:
            self.resource_monitor.start_monitoring()

        try:
            # Serialize backup data
            from .serialization import BackupSerializer

            serializer = BackupSerializer()
            serialized_data = await serializer.serialize(backup_data)
            optimization_metadata["original_size"] = len(serialized_data)

            current_data = serialized_data

            # Apply deduplication first (works better on uncompressed data)
            if self.enable_deduplication and self.deduplication_provider:
                dedup_result = await self.deduplication_provider.deduplicate(current_data)
                current_data = dedup_result.deduplicated_data
                optimization_metadata["deduplication_applied"] = True
                optimization_metadata["deduplication_ratio"] = dedup_result.deduplication_ratio
                optimization_metadata["duplicate_blocks"] = dedup_result.duplicate_blocks

            # Apply compression
            if self.enable_compression and self.compression_provider:
                # Choose best algorithm based on data characteristics
                algorithm = self.compression_provider.get_best_algorithm(current_data)
                compression_result = await self.compression_provider.compress(
                    current_data, algorithm
                )
                current_data = compression_result.compressed_data
                optimization_metadata["compression_applied"] = True
                optimization_metadata["compression_algorithm"] = algorithm
                optimization_metadata["compression_ratio"] = compression_result.compression_ratio

            optimization_metadata["final_size"] = len(current_data)
            optimization_metadata["optimization_time"] = time.time() - start_time
            optimization_metadata["total_reduction_ratio"] = (
                optimization_metadata["original_size"] / optimization_metadata["final_size"]
                if optimization_metadata["final_size"] > 0
                else 1.0
            )

            logger.info(
                f"Optimized backup data: {optimization_metadata['original_size']} -> "
                f"{optimization_metadata['final_size']} bytes "
                f"(ratio: {optimization_metadata['total_reduction_ratio']:.2f})"
            )

            return current_data, optimization_metadata

        finally:
            # Stop resource monitoring
            if self.resource_monitor:
                self.resource_monitor.stop_monitoring()

    async def restore_optimized_data(
        self, optimized_data: bytes, optimization_metadata: Dict[str, Any]
    ) -> BackupData:
        """
        Restore optimized data back to original BackupData.

        Args:
            optimized_data: Optimized data to restore
            optimization_metadata: Metadata about applied optimizations

        Returns:
            Original BackupData
        """
        start_time = time.time()

        # Start resource monitoring
        if self.resource_monitor:
            self.resource_monitor.start_monitoring()

        try:
            current_data = optimized_data

            # Reverse compression
            if optimization_metadata.get("compression_applied") and self.compression_provider:
                algorithm = optimization_metadata.get("compression_algorithm", "lz4")
                current_data = await self.compression_provider.decompress(current_data, algorithm)

            # Reverse deduplication
            if optimization_metadata.get("deduplication_applied") and self.deduplication_provider:
                current_data = await self.deduplication_provider.rehydrate(current_data)

            # Deserialize backup data
            from .serialization import BackupSerializer

            serializer = BackupSerializer()
            backup_data = await serializer.deserialize(current_data)

            restore_time = time.time() - start_time
            logger.info(f"Restored optimized data in {restore_time:.2f}s")

            return backup_data

        finally:
            # Stop resource monitoring
            if self.resource_monitor:
                self.resource_monitor.stop_monitoring()

    async def process_parallel_collection(
        self, collection_tasks: List[Callable], *args, **kwargs
    ) -> List[Any]:
        """
        Process data collection tasks in parallel.

        Args:
            collection_tasks: List of collection functions to execute
            *args: Additional arguments for collection functions
            **kwargs: Additional keyword arguments for collection functions

        Returns:
            List of collection results
        """
        if not self.enable_parallel_processing or not self.parallel_processor:
            # Execute sequentially
            results = []
            for task in collection_tasks:
                try:
                    result = await task(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Collection task failed: {e}")
                    results.append([])  # Empty result for failed task
            return results

        # Execute in parallel
        parallel_result = await self.parallel_processor.process_parallel(
            lambda task: asyncio.run(task(*args, **kwargs)), collection_tasks
        )

        return parallel_result.results

    def get_performance_metrics(self) -> List[PerformanceMetrics]:
        """Get collected performance metrics."""
        with self._metrics_lock:
            return list(self._performance_metrics)

    def get_resource_usage(self, duration: Optional[timedelta] = None) -> Dict[str, Any]:
        """
        Get resource usage statistics.

        Args:
            duration: Optional duration to analyze

        Returns:
            Resource usage statistics
        """
        if not self.resource_monitor:
            return {}

        current_metrics = self.resource_monitor.get_current_metrics()
        peak_usage = self.resource_monitor.get_peak_usage(duration)
        metrics_history = self.resource_monitor.get_metrics_history(duration)

        return {
            "current": current_metrics.to_dict() if current_metrics else {},
            "peak": peak_usage,
            "history_count": len(metrics_history),
            "monitoring_active": self.resource_monitor._monitoring,
        }

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Get optimization statistics from all components."""
        stats = {
            "compression_enabled": self.enable_compression,
            "deduplication_enabled": self.enable_deduplication,
            "parallel_processing_enabled": self.enable_parallel_processing,
            "resource_monitoring_enabled": self.enable_resource_monitoring,
        }

        if self.compression_provider:
            stats["compression"] = self.compression_provider.get_compression_stats()

        if self.deduplication_provider:
            stats["deduplication"] = self.deduplication_provider.get_deduplication_stats()

        return stats

    def clear_caches(self):
        """Clear all optimization caches."""
        if self.deduplication_provider:
            self.deduplication_provider.clear_cache()

        if self.resource_monitor:
            self.resource_monitor.clear_metrics()

        with self._metrics_lock:
            self._performance_metrics.clear()

        # Force garbage collection
        gc.collect()

    def shutdown(self):
        """Shutdown the performance optimizer."""
        if self.parallel_processor:
            self.parallel_processor.shutdown()

        if self.resource_monitor:
            self.resource_monitor.stop_monitoring()
