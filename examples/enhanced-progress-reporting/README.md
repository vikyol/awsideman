# Enhanced Progress Reporting for Multi-Account Operations

This example demonstrates the enhanced progress reporting features implemented for large-scale multi-account operations.

## Features Implemented

### 1. Detailed Progress Information for Extended Operations

The enhanced progress tracker provides comprehensive statistics including:
- Processing rates (accounts per minute/second)
- Time per account (including retries and delays)
- Success/failure percentages
- Estimated completion time
- Milestone tracking for large operations

### 2. Progress Persistence for Resumable Operations

Operations can be resumed if interrupted:
- Progress is automatically saved every 5 seconds
- Operations can be restored from saved snapshots
- Automatic cleanup of old progress files
- Resume notifications show current progress

### 3. Estimated Time Remaining Calculations

Smart time estimation based on:
- Current processing rate
- Rolling average of recent processing rates
- Account complexity and retry patterns
- Real-time updates as processing continues

## Usage Examples

### Basic Enhanced Progress Tracking

```python
from rich.console import Console
from src.awsideman.bulk.multi_account_progress import MultiAccountProgressTracker

console = Console()
tracker = MultiAccountProgressTracker(
    console,
    operation_id="my_large_operation",
    enable_persistence=True
)

# Start tracking for a large operation
tracker.start_multi_account_progress(
    total_accounts=500,
    operation_type="assign",
    show_live_results=True,
    batch_size=20
)

# Process accounts...
for i, account in enumerate(accounts):
    tracker.update_current_account(account.name, account.id)

    # Simulate processing
    result = process_account(account)

    tracker.record_account_result(
        account_id=account.id,
        status="success" if result.success else "failed",
        account_name=account.name,
        error=result.error_message if not result.success else None,
        processing_time=result.duration,
        retry_count=result.retry_count
    )

# Display final summary with enhanced information
tracker.display_final_summary(results)
```

### Progress Persistence and Resumption

```python
# Start an operation that might be interrupted
tracker = MultiAccountProgressTracker(
    console,
    operation_id="long_running_operation_123",
    enable_persistence=True
)

# If the operation was previously interrupted, it will automatically resume
tracker.start_multi_account_progress(1000, "assign")
# Output: "Resuming operation from 347/1000 accounts"
```

### Detailed Progress Information Display

```python
# During long operations, display detailed progress
tracker.display_detailed_progress_info()

# Get programmatic access to detailed stats
stats = tracker.get_detailed_stats()
completion_info = tracker.get_estimated_completion_info()

print(f"Progress: {stats['progress_percentage']:.1f}%")
print(f"Rate: {stats['accounts_per_minute']:.1f} accounts/min")
print(f"ETA: {completion_info['estimated_remaining_time_formatted']}")
```

## Progress Persistence Storage

Progress files are stored in `~/.awsideman/progress/` with the following structure:

```json
{
  "operation_id": "multi_account_1234567890",
  "operation_type": "assign",
  "total_accounts": 1000,
  "processed_accounts": 347,
  "successful_count": 320,
  "failed_count": 15,
  "skipped_count": 12,
  "start_time": 1234567890.123,
  "last_update_time": 1234567950.456,
  "current_account_id": "123456789012",
  "current_account_name": "production-account",
  "estimated_completion_time": 1234568500.789,
  "processing_rate": 2.5,
  "batch_size": 20
}
```

## Milestone Tracking

For operations with 100+ accounts, the system automatically tracks milestones:
- 10% completion
- 25% completion
- 50% completion
- 75% completion
- 90% completion

Milestones are displayed in real-time and included in the final summary.

## Performance Considerations

The enhanced progress reporting is designed for efficiency:
- Minimal memory footprint even for thousands of accounts
- Periodic persistence saves (every 5 seconds) to avoid I/O overhead
- Rolling window for processing rate calculations
- Automatic cleanup of old progress files

## Error Handling

The system gracefully handles various error scenarios:
- Progress persistence failures don't interrupt operations
- Corrupted progress files are ignored
- Network interruptions are handled with automatic retry
- Rate limiting is detected and handled with intelligent backoff
