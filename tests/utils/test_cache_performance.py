"""Performance tests for advanced cache features."""

import json
import tempfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch
import pytest

from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.factory import BackendFactory
from src.awsideman.encryption.provider import EncryptionProviderFactory
from src.awsideman.encryption.key_manager import FallbackKeyManager


class TestCachePerformance:
    """Performance tests for cache system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_encryption_decryption_performance(self):
        """Test encryption/decryption performance overhead."""
        # Create key manager
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        
        # Test data of various sizes
        test_cases = [
            ("small", {"data": "x" * 100}),  # 100 bytes
            ("medium", {"data": "x" * 10000}),  # 10KB
            ("large", {"data": "x" * 100000}),  # 100KB
        ]
        
        # Test no encryption
        no_encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test AES encryption
        aes_encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
        
        results = {}
        
        for size_name, test_data in test_cases:
            # Benchmark no encryption
            start_time = time.time()
            for _ in range(100):  # 100 iterations
                encrypted = no_encryption.encrypt(test_data)
                decrypted = no_encryption.decrypt(encrypted)
            no_encryption_time = time.time() - start_time
            
            # Benchmark AES encryption
            start_time = time.time()
            for _ in range(100):  # 100 iterations
                encrypted = aes_encryption.encrypt(test_data)
                decrypted = aes_encryption.decrypt(encrypted)
            aes_encryption_time = time.time() - start_time
            
            # Calculate overhead
            overhead_ms = (aes_encryption_time - no_encryption_time) * 10  # Per operation in ms
            
            results[size_name] = {
                'no_encryption_time': no_encryption_time,
                'aes_encryption_time': aes_encryption_time,
                'overhead_ms': overhead_ms,
                'data_size': len(json.dumps(test_data))
            }
            
            # Verify overhead is reasonable (< 10ms per operation for most cases)
            if size_name != "large":  # Large data may have higher overhead
                assert overhead_ms < 10, f"Encryption overhead too high for {size_name}: {overhead_ms}ms"
        
        # Print results for analysis
        print("\nEncryption Performance Results:")
        for size_name, result in results.items():
            print(f"{size_name.capitalize()} data ({result['data_size']} bytes): "
                  f"Overhead = {result['overhead_ms']:.2f}ms per operation")
    
    def test_file_backend_performance(self):
        """Test file backend performance."""
        config = AdvancedCacheConfig(
            backend_type="file",
            encryption_enabled=False,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test data
        test_data = {"performance": "test", "data": "x" * 1000}  # 1KB
        encrypted_data = encryption.encrypt(test_data)
        
        # Benchmark write operations
        write_times = []
        for i in range(100):
            start_time = time.time()
            backend.set(f"perf_key_{i}", encrypted_data, ttl=3600, operation="perf_test")
            write_times.append((time.time() - start_time) * 1000)  # Convert to ms
        
        # Benchmark read operations
        read_times = []
        for i in range(100):
            start_time = time.time()
            retrieved_data = backend.get(f"perf_key_{i}")
            read_times.append((time.time() - start_time) * 1000)  # Convert to ms
            assert retrieved_data == encrypted_data
        
        # Calculate statistics
        avg_write_time = sum(write_times) / len(write_times)
        avg_read_time = sum(read_times) / len(read_times)
        max_write_time = max(write_times)
        max_read_time = max(read_times)
        
        print(f"\nFile Backend Performance:")
        print(f"Average write time: {avg_write_time:.2f}ms")
        print(f"Average read time: {avg_read_time:.2f}ms")
        print(f"Max write time: {max_write_time:.2f}ms")
        print(f"Max read time: {max_read_time:.2f}ms")
        
        # Performance assertions (reasonable thresholds)
        assert avg_write_time < 50, f"Average write time too high: {avg_write_time}ms"
        assert avg_read_time < 20, f"Average read time too high: {avg_read_time}ms"
        assert max_write_time < 200, f"Max write time too high: {max_write_time}ms"
        assert max_read_time < 100, f"Max read time too high: {max_read_time}ms"
    
    @patch('boto3.Session')
    def test_dynamodb_backend_performance(self, mock_session):
        """Test DynamoDB backend performance simulation."""
        # Mock boto3 components with realistic delays
        mock_client = Mock()
        mock_table = Mock()
        mock_dynamodb = Mock()
        mock_dynamodb.Table.return_value = mock_table
        
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_client
        mock_session_instance.resource.return_value = mock_dynamodb
        mock_session.return_value = mock_session_instance
        
        # Mock table exists
        mock_table.load.return_value = None
        
        # Add realistic delays to simulate network latency
        def mock_put_item(*args, **kwargs):
            time.sleep(0.01)  # 10ms simulated latency
            return {}
        
        def mock_get_item(*args, **kwargs):
            time.sleep(0.005)  # 5ms simulated latency
            import base64
            test_data = b'{"test": "data"}'
            return {
                'Item': {
                    'cache_key': 'test_key',
                    'data': base64.b64encode(test_data).decode('utf-8'),
                    'operation': 'test',
                    'created_at': int(time.time()),
                    'ttl': int(time.time() + 3600)
                }
            }
        
        mock_table.put_item.side_effect = mock_put_item
        mock_table.get_item.side_effect = mock_get_item
        
        config = AdvancedCacheConfig(
            backend_type="dynamodb",
            dynamodb_table_name="perf-test-table"
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        test_data = {"performance": "dynamodb", "data": "x" * 1000}
        encrypted_data = encryption.encrypt(test_data)
        
        # Benchmark write operations
        write_times = []
        for i in range(20):  # Fewer iterations due to simulated latency
            start_time = time.time()
            backend.set(f"dynamo_key_{i}", encrypted_data, ttl=3600, operation="dynamo_perf")
            write_times.append((time.time() - start_time) * 1000)
        
        # Benchmark read operations
        read_times = []
        for i in range(20):
            start_time = time.time()
            retrieved_data = backend.get(f"dynamo_key_{i}")
            read_times.append((time.time() - start_time) * 1000)
            assert retrieved_data is not None
        
        avg_write_time = sum(write_times) / len(write_times)
        avg_read_time = sum(read_times) / len(read_times)
        
        print(f"\nDynamoDB Backend Performance (simulated):")
        print(f"Average write time: {avg_write_time:.2f}ms")
        print(f"Average read time: {avg_read_time:.2f}ms")
        
        # DynamoDB should be slower than file backend due to network
        assert avg_write_time > 5, "DynamoDB write time seems unrealistically fast"
        assert avg_read_time > 2, "DynamoDB read time seems unrealistically fast"
        assert avg_write_time < 100, f"DynamoDB write time too high: {avg_write_time}ms"
        assert avg_read_time < 50, f"DynamoDB read time too high: {avg_read_time}ms"
    
    def test_concurrent_access_performance(self):
        """Test concurrent access performance."""
        config = AdvancedCacheConfig(
            backend_type="file",
            encryption_enabled=False,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Test data
        test_data = {"concurrent": "test", "thread_id": 0}
        
        def worker_function(worker_id):
            """Worker function for concurrent testing."""
            worker_times = []
            worker_data = test_data.copy()
            worker_data["thread_id"] = worker_id
            encrypted_data = encryption.encrypt(worker_data)
            
            # Perform operations
            for i in range(10):
                key = f"concurrent_{worker_id}_{i}"
                
                # Write operation
                start_time = time.time()
                backend.set(key, encrypted_data, ttl=3600, operation="concurrent_test")
                write_time = (time.time() - start_time) * 1000
                
                # Read operation
                start_time = time.time()
                retrieved_data = backend.get(key)
                read_time = (time.time() - start_time) * 1000
                
                worker_times.append({
                    'write_time': write_time,
                    'read_time': read_time,
                    'success': retrieved_data == encrypted_data
                })
            
            return worker_times
        
        # Run concurrent workers
        num_workers = 5
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_function, i) for i in range(num_workers)]
            results = [future.result() for future in as_completed(futures)]
        
        total_time = time.time() - start_time
        
        # Analyze results
        all_operations = []
        for worker_results in results:
            all_operations.extend(worker_results)
        
        # Verify all operations succeeded
        success_count = sum(1 for op in all_operations if op['success'])
        total_operations = len(all_operations)
        
        avg_write_time = sum(op['write_time'] for op in all_operations) / total_operations
        avg_read_time = sum(op['read_time'] for op in all_operations) / total_operations
        
        print(f"\nConcurrent Access Performance:")
        print(f"Workers: {num_workers}")
        print(f"Total operations: {total_operations}")
        print(f"Success rate: {success_count}/{total_operations} ({success_count/total_operations*100:.1f}%)")
        print(f"Total time: {total_time:.2f}s")
        print(f"Average write time: {avg_write_time:.2f}ms")
        print(f"Average read time: {avg_read_time:.2f}ms")
        print(f"Operations per second: {total_operations/total_time:.1f}")
        
        # Performance assertions
        assert success_count == total_operations, "Some concurrent operations failed"
        assert avg_write_time < 100, f"Concurrent write time too high: {avg_write_time}ms"
        assert avg_read_time < 50, f"Concurrent read time too high: {avg_read_time}ms"
        assert total_operations/total_time > 50, f"Throughput too low: {total_operations/total_time:.1f} ops/sec"
    
    def test_large_data_performance(self):
        """Test performance with large data sets."""
        config = AdvancedCacheConfig(
            backend_type="file",
            encryption_enabled=True,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
        
        # Create large data sets
        data_sizes = [
            ("1KB", {"data": "x" * 1000}),
            ("10KB", {"data": "x" * 10000}),
            ("100KB", {"data": "x" * 100000}),
            ("1MB", {"data": "x" * 1000000}),
        ]
        
        results = {}
        
        for size_name, test_data in data_sizes:
            # Measure encryption time
            start_time = time.time()
            encrypted_data = encryption.encrypt(test_data)
            encryption_time = (time.time() - start_time) * 1000
            
            # Measure storage time
            start_time = time.time()
            backend.set(f"large_{size_name}", encrypted_data, ttl=3600, operation="large_test")
            storage_time = (time.time() - start_time) * 1000
            
            # Measure retrieval time
            start_time = time.time()
            retrieved_data = backend.get(f"large_{size_name}")
            retrieval_time = (time.time() - start_time) * 1000
            
            # Measure decryption time
            start_time = time.time()
            decrypted_data = encryption.decrypt(retrieved_data)
            decryption_time = (time.time() - start_time) * 1000
            
            # Verify data integrity
            assert decrypted_data == test_data
            
            total_time = encryption_time + storage_time + retrieval_time + decryption_time
            
            results[size_name] = {
                'encryption_time': encryption_time,
                'storage_time': storage_time,
                'retrieval_time': retrieval_time,
                'decryption_time': decryption_time,
                'total_time': total_time,
                'data_size': len(json.dumps(test_data))
            }
        
        print(f"\nLarge Data Performance Results:")
        for size_name, result in results.items():
            print(f"{size_name} ({result['data_size']} bytes):")
            print(f"  Encryption: {result['encryption_time']:.2f}ms")
            print(f"  Storage: {result['storage_time']:.2f}ms")
            print(f"  Retrieval: {result['retrieval_time']:.2f}ms")
            print(f"  Decryption: {result['decryption_time']:.2f}ms")
            print(f"  Total: {result['total_time']:.2f}ms")
        
        # Performance assertions - times should scale reasonably with data size
        assert results["1KB"]["total_time"] < 100, "1KB operation too slow"
        assert results["10KB"]["total_time"] < 500, "10KB operation too slow"
        assert results["100KB"]["total_time"] < 2000, "100KB operation too slow"
        # 1MB might be slower, but should still be reasonable
        assert results["1MB"]["total_time"] < 10000, "1MB operation too slow"
    
    def test_cache_stats_performance(self):
        """Test cache statistics collection performance."""
        config = AdvancedCacheConfig(
            backend_type="file",
            encryption_enabled=False,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        encryption = EncryptionProviderFactory.create_provider("none")
        
        # Create many cache entries
        num_entries = 1000
        test_data = {"stats": "test"}
        encrypted_data = encryption.encrypt(test_data)
        
        # Store entries
        for i in range(num_entries):
            backend.set(f"stats_key_{i}", encrypted_data, ttl=3600, operation="stats_test")
        
        # Benchmark stats collection
        stats_times = []
        for _ in range(10):  # Multiple runs
            start_time = time.time()
            stats = backend.get_stats()
            stats_time = (time.time() - start_time) * 1000
            stats_times.append(stats_time)
            
            # Verify stats are correct
            assert stats['valid_entries'] == num_entries
        
        avg_stats_time = sum(stats_times) / len(stats_times)
        max_stats_time = max(stats_times)
        
        print(f"\nCache Stats Performance:")
        print(f"Entries: {num_entries}")
        print(f"Average stats time: {avg_stats_time:.2f}ms")
        print(f"Max stats time: {max_stats_time:.2f}ms")
        
        # Stats collection should be reasonably fast even with many entries
        assert avg_stats_time < 1000, f"Stats collection too slow: {avg_stats_time}ms"
        assert max_stats_time < 2000, f"Max stats time too slow: {max_stats_time}ms"
    
    def test_memory_usage_stability(self):
        """Test memory usage stability during operations."""
        import psutil
        import os
        
        config = AdvancedCacheConfig(
            backend_type="file",
            encryption_enabled=True,
            file_cache_dir=self.temp_dir
        )
        
        backend = BackendFactory.create_backend(config)
        key_manager = FallbackKeyManager(fallback_dir=self.temp_dir)
        encryption = EncryptionProviderFactory.create_provider("aes256", key_manager=key_manager)
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform many operations
        test_data = {"memory": "test", "data": "x" * 1000}
        memory_samples = [initial_memory]
        
        for i in range(500):  # Many operations
            encrypted_data = encryption.encrypt(test_data)
            backend.set(f"memory_key_{i}", encrypted_data, ttl=3600, operation="memory_test")
            
            # Sample memory every 50 operations
            if i % 50 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_samples.append(current_memory)
        
        final_memory = process.memory_info().rss / 1024 / 1024
        max_memory = max(memory_samples)
        memory_growth = final_memory - initial_memory
        
        print(f"\nMemory Usage Analysis:")
        print(f"Initial memory: {initial_memory:.2f}MB")
        print(f"Final memory: {final_memory:.2f}MB")
        print(f"Max memory: {max_memory:.2f}MB")
        print(f"Memory growth: {memory_growth:.2f}MB")
        
        # Memory growth should be reasonable (not indicating major leaks)
        assert memory_growth < 100, f"Excessive memory growth: {memory_growth}MB"
        assert max_memory < initial_memory + 150, f"Peak memory usage too high: {max_memory}MB"