# Multi-Account Performance Tests

This directory contains performance tests for multi-account operations scalability.

## Test Coverage

### `test_multi_account_performance.py`

Comprehensive performance tests for multi-account operations including:

1. **Large Account List Processing**
   - `test_large_account_list_processing_100_accounts`: Tests processing 100 accounts
   - `test_large_account_list_processing_200_accounts`: Tests processing 200 accounts
   - Validates throughput and processing time requirements

2. **Batch Size Efficiency**
   - `test_batch_size_efficiency_comparison`: Tests different batch sizes (5, 10, 15, 20, 25)
   - Identifies optimal batch size for maximum throughput
   - Validates that larger batch sizes generally perform better

3. **Memory Usage Testing**
   - `test_memory_usage_with_large_account_lists`: Tests memory usage with 50-200 accounts
   - Validates memory usage scales linearly, not exponentially
   - Requires `psutil` package (skipped if not available)

4. **Progress Tracking Performance**
   - `test_progress_tracking_performance_validation`: Tests progress tracking overhead
   - Validates that progress tracking adds minimal performance impact (<50% overhead)

5. **Concurrent Processing Scalability**
   - `test_concurrent_account_processing_scalability`: Tests different concurrency levels
   - Validates that concurrent processing provides significant performance improvements
   - Tests concurrency levels from 1 to 20

6. **Error Handling Performance Impact**
   - `test_error_handling_performance_impact`: Tests performance with mixed success/failure scenarios
   - Validates that error handling doesn't significantly impact performance

## Running Performance Tests

```bash
# Run all performance tests
python -m pytest tests/performance/test_multi_account_performance.py -v -m performance

# Run specific performance test
python -m pytest tests/performance/test_multi_account_performance.py::TestMultiAccountPerformance::test_large_account_list_processing_100_accounts -v

# Run with output to see performance metrics
python -m pytest tests/performance/test_multi_account_performance.py -v -s -m performance
```

## Performance Requirements Validated

- **Requirement 5.1**: Progress tracking performance validation
- **Requirement 6.1**: Batch size support and optimization
- **Requirement 6.2**: Configurable batch size performance
- **Requirement 6.3**: Rate limiting and performance considerations

## Test Features

- Mock AWS clients for consistent performance testing
- Progress tracking mocking to avoid Rich display conflicts
- Memory usage monitoring (when psutil is available)
- Throughput and latency measurements
- Scalability validation across different account counts
- Concurrency performance testing
- Error handling performance impact assessment

## Dependencies

- `pytest`: Test framework
- `asyncio`: Async operation testing
- `psutil`: Memory usage testing (optional)
- `unittest.mock`: Mocking AWS clients and operations
