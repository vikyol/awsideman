"""Optimized storage implementation with compression and memory efficiency."""

import gzip
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .models import OperationRecord


class CompressedJSONStorage:
    """Compressed JSON storage with memory optimization."""

    def __init__(self, file_path: Path, compression_level: int = 6):
        """Initialize compressed storage.

        Args:
            file_path: Path to the storage file
            compression_level: Compression level (1-9, higher = better compression)
        """
        self.file_path = file_path
        self.compression_level = compression_level
        self._lock = threading.Lock()

    def read_data(self) -> Dict[str, Any]:
        """Read and decompress data from file."""
        if not self.file_path.exists():
            return {}

        try:
            with gzip.open(self.file_path, "rt", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            # Try reading as uncompressed file (for migration)
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return {}

    def write_data(self, data: Dict[str, Any]) -> None:
        """Compress and write data to file."""
        with self._lock:
            # Write to temporary file first for atomic operation
            temp_file = self.file_path.with_suffix(".tmp")

            try:
                with gzip.open(
                    temp_file, "wt", encoding="utf-8", compresslevel=self.compression_level
                ) as f:
                    json.dump(data, f, separators=(",", ":"), default=str)  # Compact JSON

                # Atomic move
                temp_file.replace(self.file_path)

            except Exception:
                # Clean up temp file on error
                if temp_file.exists():
                    temp_file.unlink()
                raise

    def append_data(self, key: str, new_items: List[Dict[str, Any]]) -> None:
        """Efficiently append data to existing file."""
        with self._lock:
            data = self.read_data()
            if key not in data:
                data[key] = []
            data[key].extend(new_items)
            self.write_data(data)

    def get_file_size(self) -> int:
        """Get compressed file size in bytes."""
        return self.file_path.stat().st_size if self.file_path.exists() else 0

    def get_compression_ratio(self) -> float:
        """Get compression ratio (compressed_size / uncompressed_size)."""
        if not self.file_path.exists():
            return 0.0

        compressed_size = self.get_file_size()

        # Estimate uncompressed size by reading and measuring JSON
        try:
            data = self.read_data()
            uncompressed_json = json.dumps(data, separators=(",", ":"), default=str)
            uncompressed_size = len(uncompressed_json.encode("utf-8"))

            return compressed_size / uncompressed_size if uncompressed_size > 0 else 0.0
        except Exception:
            return 0.0


class MemoryOptimizedOperationStore:
    """Memory-optimized operation store with compression and efficient querying."""

    def __init__(
        self,
        storage_directory: Optional[str] = None,
        compression_enabled: bool = True,
        compression_level: int = 6,
        memory_limit_mb: int = 100,
        batch_size: int = 1000,
    ):
        """Initialize the optimized operation store.

        Args:
            storage_directory: Directory to store operation files
            compression_enabled: Whether to use compression
            compression_level: Compression level (1-9)
            memory_limit_mb: Memory limit for in-memory operations
            batch_size: Batch size for processing large datasets
        """
        if storage_directory:
            self.storage_dir = Path(storage_directory).expanduser()
        else:
            self.storage_dir = Path.home() / ".awsideman" / "operations"

        self.compression_enabled = compression_enabled
        self.compression_level = compression_level
        self.memory_limit_bytes = memory_limit_mb * 1024 * 1024
        self.batch_size = batch_size

        # Storage files
        self.operations_file = self.storage_dir / (
            "operations.json.gz" if compression_enabled else "operations.json"
        )
        self.rollbacks_file = self.storage_dir / (
            "rollbacks.json.gz" if compression_enabled else "rollbacks.json"
        )
        self.index_file = self.storage_dir / "operation_index.json"

        # Ensure directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Initialize storage
        if compression_enabled:
            self.operations_storage = CompressedJSONStorage(self.operations_file, compression_level)
            self.rollbacks_storage = CompressedJSONStorage(self.rollbacks_file, compression_level)
        else:
            self.operations_storage = None
            self.rollbacks_storage = None

        # In-memory index for fast lookups
        self._operation_index: Dict[str, Dict[str, Any]] = {}
        self._index_lock = threading.Lock()

        # Initialize files and index
        self._initialize_storage()
        self._load_index()

    def _initialize_storage(self) -> None:
        """Initialize storage files if they don't exist."""
        if self.compression_enabled:
            if not self.operations_file.exists():
                self.operations_storage.write_data({"operations": []})
            if not self.rollbacks_file.exists():
                self.rollbacks_storage.write_data({"rollbacks": []})
        else:
            if not self.operations_file.exists():
                with open(self.operations_file, "w") as f:
                    json.dump({"operations": []}, f)
            if not self.rollbacks_file.exists():
                with open(self.rollbacks_file, "w") as f:
                    json.dump({"rollbacks": []}, f)

    def _load_index(self) -> None:
        """Load operation index for fast lookups."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r") as f:
                    self._operation_index = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self._rebuild_index()
        else:
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Rebuild the operation index from storage."""
        with self._index_lock:
            self._operation_index = {}

            # Read operations in batches to avoid memory issues
            for operation in self._iterate_operations():
                self._operation_index[operation["operation_id"]] = {
                    "timestamp": operation["timestamp"],
                    "operation_type": operation["operation_type"],
                    "principal_id": operation["principal_id"],
                    "principal_name": operation["principal_name"],
                    "permission_set_name": operation["permission_set_name"],
                    "rolled_back": operation.get("rolled_back", False),
                    "rollback_operation_id": operation.get("rollback_operation_id"),
                }

            self._save_index()

    def _save_index(self) -> None:
        """Save the operation index to disk."""
        try:
            with open(self.index_file, "w") as f:
                json.dump(self._operation_index, f, separators=(",", ":"))
        except Exception:
            pass  # Index is optional, don't fail if we can't save it

    def _iterate_operations(self) -> Iterator[Dict[str, Any]]:
        """Iterate over operations without loading all into memory."""
        if self.compression_enabled:
            data = self.operations_storage.read_data()
        else:
            try:
                with open(self.operations_file, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"operations": []}

        for operation in data.get("operations", []):
            yield operation

    def store_operation(self, operation: OperationRecord) -> None:
        """Store an operation record efficiently."""
        operation_dict = operation.to_dict()

        if self.compression_enabled:
            # Append to compressed storage
            self.operations_storage.append_data("operations", [operation_dict])
        else:
            # Read, append, write for uncompressed
            try:
                with open(self.operations_file, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"operations": []}

            data["operations"].append(operation_dict)

            with open(self.operations_file, "w") as f:
                json.dump(data, f, separators=(",", ":"), default=str)

        # Update index
        with self._index_lock:
            self._operation_index[operation.operation_id] = {
                "timestamp": operation.timestamp.isoformat(),
                "operation_type": operation.operation_type.value,
                "principal_id": operation.principal_id,
                "principal_name": operation.principal_name,
                "permission_set_name": operation.permission_set_name,
                "rolled_back": operation.rolled_back,
                "rollback_operation_id": operation.rollback_operation_id,
            }
            self._save_index()

    def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        """Get a specific operation by ID using index for fast lookup."""
        # Check index first
        if operation_id not in self._operation_index:
            return None

        # Find the operation in storage
        for operation_dict in self._iterate_operations():
            if operation_dict["operation_id"] == operation_id:
                return OperationRecord.from_dict(operation_dict)

        return None

    def get_operations(
        self,
        operation_type: Optional[str] = None,
        principal: Optional[str] = None,
        permission_set: Optional[str] = None,
        days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[OperationRecord]:
        """Get operations with efficient filtering using index."""
        # Calculate date filter if specified
        cutoff_date = None
        if days is not None:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Pre-filter using index
        candidate_ids = []
        with self._index_lock:
            for op_id, index_data in self._operation_index.items():
                # Apply index-based filters
                if operation_type and index_data["operation_type"] != operation_type:
                    continue

                if principal and not (
                    principal.lower() in index_data["principal_name"].lower()
                    or principal in index_data["principal_id"]
                ):
                    continue

                if (
                    permission_set
                    and permission_set.lower() not in index_data["permission_set_name"].lower()
                ):
                    continue

                if cutoff_date:
                    op_timestamp = datetime.fromisoformat(index_data["timestamp"])
                    if op_timestamp < cutoff_date:
                        continue

                candidate_ids.append(op_id)

        # Load full operations for candidates
        operations = []
        for operation_dict in self._iterate_operations():
            if operation_dict["operation_id"] in candidate_ids:
                operation = OperationRecord.from_dict(operation_dict)
                operations.append(operation)

                # Early exit if we have enough results
                if limit and len(operations) >= limit:
                    break

        # Sort by timestamp (newest first)
        operations.sort(key=lambda x: x.timestamp, reverse=True)

        # Apply final limit
        if limit:
            operations = operations[:limit]

        return operations

    def mark_operation_rolled_back(self, operation_id: str, rollback_operation_id: str) -> bool:
        """Mark an operation as rolled back efficiently."""
        # Update index first
        with self._index_lock:
            if operation_id in self._operation_index:
                self._operation_index[operation_id]["rolled_back"] = True
                self._operation_index[operation_id]["rollback_operation_id"] = rollback_operation_id
                self._save_index()
            else:
                return False

        # Update storage
        if self.compression_enabled:
            data = self.operations_storage.read_data()
        else:
            try:
                with open(self.operations_file, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return False

        # Find and update the operation
        updated = False
        for op_data in data.get("operations", []):
            if op_data["operation_id"] == operation_id:
                op_data["rolled_back"] = True
                op_data["rollback_operation_id"] = rollback_operation_id
                updated = True
                break

        if updated:
            if self.compression_enabled:
                self.operations_storage.write_data(data)
            else:
                with open(self.operations_file, "w") as f:
                    json.dump(data, f, separators=(",", ":"), default=str)

        return updated

    def store_rollback_record(self, rollback_data: Dict) -> None:
        """Store a rollback operation record."""
        if self.compression_enabled:
            self.rollbacks_storage.append_data("rollbacks", [rollback_data])
        else:
            try:
                with open(self.rollbacks_file, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {"rollbacks": []}

            data["rollbacks"].append(rollback_data)

            with open(self.rollbacks_file, "w") as f:
                json.dump(data, f, separators=(",", ":"), default=str)

    def cleanup_old_operations(self, days: int = 90) -> int:
        """Remove operations older than specified days with memory optimization."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        # Use temporary file for large datasets
        temp_file = self.storage_dir / "operations_temp.json"

        try:
            kept_operations = []
            removed_count = 0

            # Process operations in batches
            current_batch = []
            for operation_dict in self._iterate_operations():
                op_timestamp = datetime.fromisoformat(operation_dict["timestamp"])

                if op_timestamp >= cutoff_date:
                    current_batch.append(operation_dict)
                else:
                    removed_count += 1

                # Process batch when it reaches size limit
                if len(current_batch) >= self.batch_size:
                    kept_operations.extend(current_batch)
                    current_batch = []

                    # Check memory usage
                    if len(kept_operations) * 1000 > self.memory_limit_bytes:  # Rough estimate
                        # Write to temp file and clear memory
                        self._write_batch_to_temp(temp_file, kept_operations)
                        kept_operations = []

            # Process remaining batch
            if current_batch:
                kept_operations.extend(current_batch)

            # Write final data
            if temp_file.exists():
                # Append remaining operations to temp file
                if kept_operations:
                    self._write_batch_to_temp(temp_file, kept_operations)

                # Replace original file with temp file
                if self.compression_enabled:
                    # Read from temp and write compressed
                    with open(temp_file, "r") as f:
                        temp_data = json.load(f)
                    self.operations_storage.write_data(temp_data)
                else:
                    temp_file.replace(self.operations_file)
            else:
                # Small dataset, write directly
                final_data = {"operations": kept_operations}
                if self.compression_enabled:
                    self.operations_storage.write_data(final_data)
                else:
                    with open(self.operations_file, "w") as f:
                        json.dump(final_data, f, separators=(",", ":"), default=str)

            # Rebuild index after cleanup
            if removed_count > 0:
                self._rebuild_index()

            return removed_count

        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()

    def _write_batch_to_temp(self, temp_file: Path, operations: List[Dict]) -> None:
        """Write a batch of operations to temporary file."""
        if temp_file.exists():
            # Append to existing temp file
            with open(temp_file, "r") as f:
                temp_data = json.load(f)
            temp_data["operations"].extend(operations)
        else:
            temp_data = {"operations": operations}

        with open(temp_file, "w") as f:
            json.dump(temp_data, f, separators=(",", ":"), default=str)

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get comprehensive storage statistics."""
        stats = {
            "total_operations": len(self._operation_index),
            "operations_file_size": (
                self.operations_file.stat().st_size if self.operations_file.exists() else 0
            ),
            "rollbacks_file_size": (
                self.rollbacks_file.stat().st_size if self.rollbacks_file.exists() else 0
            ),
            "index_file_size": self.index_file.stat().st_size if self.index_file.exists() else 0,
            "compression_enabled": self.compression_enabled,
        }

        if self.compression_enabled:
            stats["operations_compression_ratio"] = self.operations_storage.get_compression_ratio()
            stats["rollbacks_compression_ratio"] = self.rollbacks_storage.get_compression_ratio()

        # Calculate memory usage estimate
        index_memory = len(json.dumps(self._operation_index).encode("utf-8"))
        stats["index_memory_usage"] = index_memory

        return stats

    def optimize_storage(self) -> Dict[str, Any]:
        """Perform storage optimization operations."""
        results = {
            "operations_before": len(self._operation_index),
            "files_rotated": [],
            "compression_applied": False,
            "index_rebuilt": False,
        }

        # Rotate large files
        max_size_mb = 50
        max_size_bytes = max_size_mb * 1024 * 1024

        if self.operations_file.exists() and self.operations_file.stat().st_size > max_size_bytes:
            self._rotate_file(self.operations_file)
            results["files_rotated"].append("operations")

        if self.rollbacks_file.exists() and self.rollbacks_file.stat().st_size > max_size_bytes:
            self._rotate_file(self.rollbacks_file)
            results["files_rotated"].append("rollbacks")

        # Enable compression if not already enabled and files are large
        if not self.compression_enabled:
            total_size = (
                self.operations_file.stat().st_size if self.operations_file.exists() else 0
            ) + (self.rollbacks_file.stat().st_size if self.rollbacks_file.exists() else 0)

            if total_size > 10 * 1024 * 1024:  # 10MB threshold
                self._migrate_to_compression()
                results["compression_applied"] = True

        # Rebuild index if it's missing or corrupted
        if not self.index_file.exists() or len(self._operation_index) == 0:
            self._rebuild_index()
            results["index_rebuilt"] = True

        results["operations_after"] = len(self._operation_index)

        return results

    def _rotate_file(self, file_path: Path) -> None:
        """Rotate a file by creating a timestamped backup."""
        if not file_path.exists():
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_name(f"{file_path.stem}_{timestamp}{file_path.suffix}")

        file_path.rename(backup_path)

        # Create new empty file
        if file_path.name.startswith("operations"):
            if self.compression_enabled:
                self.operations_storage.write_data({"operations": []})
            else:
                with open(file_path, "w") as f:
                    json.dump({"operations": []}, f)
        elif file_path.name.startswith("rollbacks"):
            if self.compression_enabled:
                self.rollbacks_storage.write_data({"rollbacks": []})
            else:
                with open(file_path, "w") as f:
                    json.dump({"rollbacks": []}, f)

    def _migrate_to_compression(self) -> None:
        """Migrate existing uncompressed files to compressed format."""
        # Migrate operations file
        if self.operations_file.exists() and not self.operations_file.name.endswith(".gz"):
            try:
                with open(self.operations_file, "r") as f:
                    data = json.load(f)

                # Create compressed storage
                compressed_file = self.operations_file.with_suffix(".json.gz")
                compressed_storage = CompressedJSONStorage(compressed_file, self.compression_level)
                compressed_storage.write_data(data)

                # Remove old file and update references
                self.operations_file.unlink()
                self.operations_file = compressed_file
                self.operations_storage = compressed_storage

            except Exception:
                pass  # Migration failed, continue with uncompressed

        # Migrate rollbacks file
        if self.rollbacks_file.exists() and not self.rollbacks_file.name.endswith(".gz"):
            try:
                with open(self.rollbacks_file, "r") as f:
                    data = json.load(f)

                # Create compressed storage
                compressed_file = self.rollbacks_file.with_suffix(".json.gz")
                compressed_storage = CompressedJSONStorage(compressed_file, self.compression_level)
                compressed_storage.write_data(data)

                # Remove old file and update references
                self.rollbacks_file.unlink()
                self.rollbacks_file = compressed_file
                self.rollbacks_storage = compressed_storage

            except Exception:
                pass  # Migration failed, continue with uncompressed

        self.compression_enabled = True


# Alias for backward compatibility
OptimizedOperationStore = MemoryOptimizedOperationStore
