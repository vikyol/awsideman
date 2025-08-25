"""
Advanced account caching optimizer for multi-account operations.

This module provides intelligent caching strategies for account resolution
to dramatically improve performance for operations that need to resolve
many accounts, especially when using wildcard filters.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..aws_clients.manager import OrganizationsClientWrapper, get_account_details
from ..cache.manager import CacheManager
from .account_filter import AccountInfo

logger = logging.getLogger(__name__)


@dataclass
class AccountCacheEntry:
    """Represents a cached account with metadata."""

    account_info: AccountInfo
    cached_at: datetime
    account_count_at_cache_time: int  # Number of accounts when this was cached


@dataclass
class OrganizationSnapshot:
    """Represents a snapshot of the entire organization's accounts."""

    accounts: List[AccountInfo]
    total_count: int
    cached_at: datetime
    cache_key: str


class AccountCacheOptimizer:
    """
    Optimized caching system for account resolution operations.

    This class implements intelligent caching strategies:
    1. Long-term caching of organization snapshots (24 hours)
    2. Account count validation to detect organization changes
    3. Bulk account resolution with minimal API calls
    4. Fallback to individual account caching when needed
    """

    # Cache keys
    ORG_SNAPSHOT_KEY = "org_snapshot_v1"
    ACCOUNT_COUNT_KEY = "org_account_count_v1"

    # Cache TTLs (in seconds)
    ORG_SNAPSHOT_TTL = 24 * 3600  # 24 hours
    ACCOUNT_COUNT_TTL = 1 * 3600  # 1 hour (shorter for change detection)
    INDIVIDUAL_ACCOUNT_TTL = 12 * 3600  # 12 hours

    def __init__(
        self,
        organizations_client: Optional[OrganizationsClientWrapper],
        cache_manager: Optional[CacheManager] = None,
        profile: Optional[str] = None,
    ):
        """
        Initialize the account cache optimizer.

        Args:
            organizations_client: Organizations client for API calls (can be None for cache-only operations)
            cache_manager: Optional unified cache manager instance
            profile: AWS profile name for profile-specific caching
        """
        self.organizations_client = organizations_client
        self.cache_manager = cache_manager or CacheManager()
        self.profile = profile or "default"

        # Make cache keys profile-specific
        self.org_snapshot_key = f"{self.ORG_SNAPSHOT_KEY}_{self.profile}"
        self.account_count_key = f"{self.ACCOUNT_COUNT_KEY}_{self.profile}"

    def get_all_accounts_optimized(self) -> List[AccountInfo]:
        """
        Get all accounts in the organization using optimized caching.

        This method implements a multi-tier caching strategy:
        1. Check if we have a valid organization snapshot
        2. If not, check if account count has changed
        3. If count is same, try to rebuild from individual account cache
        4. Otherwise, fetch fresh data and cache it

        Returns:
            List of AccountInfo objects for all accounts
        """
        logger.debug("Starting optimized account resolution")

        # Try to get cached organization snapshot first
        cached_snapshot = self._get_cached_org_snapshot()
        if cached_snapshot:
            logger.info(
                f"Using cached organization snapshot with {len(cached_snapshot.accounts)} accounts"
            )
            return cached_snapshot.accounts

        # Check current account count vs cached count
        current_count = self._get_current_account_count()
        cached_count = self._get_cached_account_count()

        logger.debug(f"Current account count: {current_count}, Cached count: {cached_count}")

        # If counts match and we have individual account cache entries, try to rebuild
        if cached_count and current_count == cached_count:
            logger.debug("Account count unchanged, attempting to rebuild from individual cache")
            rebuilt_accounts = self._try_rebuild_from_individual_cache()
            if rebuilt_accounts:
                logger.info(
                    f"Successfully rebuilt {len(rebuilt_accounts)} accounts from individual cache"
                )
                # Cache the rebuilt snapshot
                self._cache_org_snapshot(rebuilt_accounts)
                return rebuilt_accounts

        # Need to fetch fresh data
        logger.info("Fetching fresh account data from AWS APIs")
        fresh_accounts = self._fetch_all_accounts_fresh()

        # Cache the results
        self._cache_org_snapshot(fresh_accounts)
        self._cache_account_count(len(fresh_accounts))

        logger.info(f"Successfully cached {len(fresh_accounts)} accounts")
        return fresh_accounts

    def _get_cached_org_snapshot(self) -> Optional[OrganizationSnapshot]:
        """Get cached organization snapshot if valid."""
        try:
            cached_data = self.cache_manager.get(self.org_snapshot_key)
            if not cached_data:
                return None

            # Validate cache structure
            if not all(key in cached_data for key in ["accounts", "total_count", "cached_at"]):
                logger.warning("Invalid organization snapshot cache structure")
                return None

            # Convert cached data back to AccountInfo objects
            accounts = []
            for account_data in cached_data["accounts"]:
                try:
                    account_info = AccountInfo(
                        account_id=account_data["account_id"],
                        account_name=account_data["account_name"],
                        email=account_data["email"],
                        status=account_data["status"],
                        tags=account_data.get("tags", {}),
                        ou_path=account_data.get("ou_path", []),
                    )
                    accounts.append(account_info)
                except (KeyError, TypeError) as e:
                    logger.warning(f"Failed to deserialize account data: {e}")
                    return None

            return OrganizationSnapshot(
                accounts=accounts,
                total_count=cached_data["total_count"],
                cached_at=datetime.fromisoformat(cached_data["cached_at"]),
                cache_key=self.org_snapshot_key,
            )

        except Exception as e:
            logger.warning(f"Failed to retrieve organization snapshot from cache: {e}")
            return None

    def _cache_org_snapshot(self, accounts: List[AccountInfo]) -> None:
        """Cache the organization snapshot."""
        try:
            # Convert AccountInfo objects to serializable format
            serializable_accounts = []
            for account in accounts:
                serializable_accounts.append(
                    {
                        "account_id": account.account_id,
                        "account_name": account.account_name,
                        "email": account.email,
                        "status": account.status,
                        "tags": account.tags,
                        "ou_path": account.ou_path,
                    }
                )

            cache_data = {
                "accounts": serializable_accounts,
                "total_count": len(accounts),
                "cached_at": datetime.now().isoformat(),
            }

            self.cache_manager.set(
                self.org_snapshot_key,
                cache_data,
                ttl=self.ORG_SNAPSHOT_TTL,
                operation="org_snapshot",
            )

            logger.debug(f"Cached organization snapshot with {len(accounts)} accounts")

        except Exception as e:
            logger.warning(f"Failed to cache organization snapshot: {e}")

    def _get_current_account_count(self) -> int:
        """Get current account count from AWS (with caching)."""
        try:
            # This is a lightweight operation that just counts accounts
            # without fetching full details
            from ..aws_clients.manager import build_organization_hierarchy

            organization_tree = build_organization_hierarchy(self.organizations_client)

            def count_accounts_in_tree(nodes):
                count = 0
                for node in nodes:
                    if node.is_account():
                        count += 1
                    count += count_accounts_in_tree(node.children)
                return count

            return count_accounts_in_tree(organization_tree)

        except Exception as e:
            logger.warning(f"Failed to get current account count: {e}")
            return 0

    def _get_cached_account_count(self) -> Optional[int]:
        """Get cached account count."""
        try:
            cached_count = self.cache_manager.get(self.account_count_key)
            return cached_count if isinstance(cached_count, int) else None
        except Exception as e:
            logger.warning(f"Failed to get cached account count: {e}")
            return None

    def _cache_account_count(self, count: int) -> None:
        """Cache the current account count."""
        try:
            self.cache_manager.set(
                self.account_count_key, count, ttl=self.ACCOUNT_COUNT_TTL, operation="account_count"
            )
            logger.debug(f"Cached account count: {count}")
        except Exception as e:
            logger.warning(f"Failed to cache account count: {e}")

    def _try_rebuild_from_individual_cache(self) -> Optional[List[AccountInfo]]:
        """
        Try to rebuild the organization snapshot from individual account cache entries.

        This is useful when the organization snapshot has expired but individual
        account data is still cached and valid.
        """
        try:
            # This is a simplified approach - in a full implementation,
            # you'd want to enumerate all cached account entries
            # For now, we'll return None to force fresh fetch
            logger.debug("Individual cache rebuild not implemented yet")
            return None

        except Exception as e:
            logger.warning(f"Failed to rebuild from individual cache: {e}")
            return None

    def _fetch_all_accounts_fresh(self) -> List[AccountInfo]:
        """
        Fetch all accounts fresh from AWS APIs.

        This is the fallback method when cache is invalid or missing.
        """
        from ..aws_clients.manager import build_organization_hierarchy

        all_accounts = []

        # Build the organization hierarchy to get all accounts
        organization_tree = build_organization_hierarchy(self.organizations_client)

        # Collect all account IDs first
        account_ids = []

        def collect_account_ids(nodes):
            for node in nodes:
                if node.is_account():
                    account_ids.append(node.id)
                collect_account_ids(node.children)

        collect_account_ids(organization_tree)

        logger.debug(f"Found {len(account_ids)} accounts to fetch details for")

        # Fetch account details for each account
        for i, account_id in enumerate(account_ids):
            try:
                if i % 10 == 0:  # Log progress every 10 accounts
                    logger.debug(f"Fetching account details: {i+1}/{len(account_ids)}")

                account_details = get_account_details(self.organizations_client, account_id)
                account_info = AccountInfo.from_account_details(account_details)
                all_accounts.append(account_info)

                # Also cache individual account for future use
                self._cache_individual_account(account_info)

            except Exception as e:
                logger.warning(f"Failed to get details for account {account_id}: {e}")
                continue

        return all_accounts

    def _cache_individual_account(self, account_info: AccountInfo) -> None:
        """Cache an individual account for future use."""
        try:
            cache_key = f"account_details_{self.profile}_{account_info.account_id}"

            cache_data = {
                "account_id": account_info.account_id,
                "account_name": account_info.account_name,
                "email": account_info.email,
                "status": account_info.status,
                "tags": account_info.tags,
                "ou_path": account_info.ou_path,
                "cached_at": datetime.now().isoformat(),
            }

            self.cache_manager.set(
                cache_key,
                cache_data,
                ttl=self.INDIVIDUAL_ACCOUNT_TTL,
                operation="individual_account",
            )

        except Exception as e:
            logger.warning(f"Failed to cache individual account {account_info.account_id}: {e}")

    def invalidate_cache(self) -> None:
        """Invalidate all account-related cache entries."""
        try:
            if self.profile == "*":
                # Clear all profile-specific cache entries
                self._invalidate_all_profiles()
            else:
                # Clear organization snapshot for specific profile
                try:
                    self.cache_manager.invalidate(self.org_snapshot_key)
                    logger.debug(f"Cleared organization snapshot for profile: {self.profile}")
                except Exception as e:
                    logger.warning(f"Failed to clear org snapshot for {self.profile}: {e}")

                # Clear account count for specific profile
                try:
                    self.cache_manager.invalidate(self.account_count_key)
                    logger.debug(f"Cleared account count for profile: {self.profile}")
                except Exception as e:
                    logger.warning(f"Failed to clear account count for {self.profile}: {e}")

            logger.info(f"Account cache invalidated for profile: {self.profile}")

        except Exception as e:
            logger.warning(f"Failed to invalidate account cache: {e}")

    def _invalidate_all_profiles(self) -> None:
        """Invalidate account cache for all profiles by enumerating existing cache entries."""
        try:
            cleared_count = 0

            # Get all cache entries to find account-related ones
            try:
                # Try to get cache statistics which might include entry enumeration
                self.cache_manager.get_cache_stats()

                # If the cache manager supports listing entries, use that
                if hasattr(self.cache_manager, "list_cache_keys"):
                    cache_keys = self.cache_manager.list_cache_keys()
                else:
                    # Fallback: try to enumerate from cache directory if it's a file cache
                    cache_keys = self._enumerate_cache_keys()

                # Clear account-related cache entries
                account_patterns = [
                    self.ORG_SNAPSHOT_KEY,
                    self.ACCOUNT_COUNT_KEY,
                    "account_details_",
                ]

                for key in cache_keys:
                    # Check if this key matches any account-related pattern
                    for pattern in account_patterns:
                        if key.startswith(pattern):
                            try:
                                self.cache_manager.invalidate(key)
                                cleared_count += 1
                                logger.debug(f"Cleared cache key: {key}")
                            except Exception as e:
                                logger.warning(f"Failed to clear cache key {key}: {e}")
                            break

                logger.info(
                    f"Cleared {cleared_count} account-related cache entries for all profiles"
                )

            except Exception as e:
                logger.warning(f"Could not enumerate cache entries: {e}")
                # Fallback to the old method with extended profile list
                self._fallback_clear_common_profiles()

        except Exception as e:
            logger.warning(f"Failed to clear all profile caches: {e}")

    def _enumerate_cache_keys(self) -> List[str]:
        """Enumerate cache keys from the cache backend."""
        cache_keys = []

        try:
            # Method 1: Try to use cache utils for file-based cache
            if hasattr(self.cache_manager, "path_manager") and self.cache_manager.path_manager:
                try:
                    cache_dir = self.cache_manager.path_manager.get_cache_directory()

                    if cache_dir and cache_dir.exists():
                        # List all cache files (both .json and .cache extensions)
                        for pattern in ["*.json", "*.cache"]:
                            for cache_file in cache_dir.glob(pattern):
                                # Extract cache key from filename
                                cache_key = cache_file.stem
                                cache_keys.append(cache_key)

                        logger.debug(f"Found {len(cache_keys)} cache files in {cache_dir}")
                except Exception as e:
                    logger.debug(f"Could not enumerate file cache: {e}")

            # Method 2: Try backend-specific enumeration
            if (
                not cache_keys
                and hasattr(self.cache_manager, "backend")
                and self.cache_manager.backend
            ):
                backend = self.cache_manager.backend
                try:
                    # Try different backend methods
                    if hasattr(backend, "list_keys"):
                        cache_keys = backend.list_keys()
                    elif hasattr(backend, "scan_keys"):
                        cache_keys = backend.scan_keys()
                    elif hasattr(backend, "get_all_keys"):
                        cache_keys = backend.get_all_keys()

                    logger.debug(f"Found {len(cache_keys)} cache keys from backend")
                except Exception as e:
                    logger.debug(f"Could not enumerate backend cache: {e}")

            # Method 3: Try to get keys from cache statistics
            if not cache_keys:
                try:
                    stats = self.cache_manager.get_cache_stats()
                    if isinstance(stats, dict) and "entries" in stats:
                        # Some cache implementations include entry details in stats
                        entries = stats.get("entries", [])
                        if isinstance(entries, list):
                            cache_keys = [
                                entry.get("key", "") for entry in entries if entry.get("key")
                            ]

                        logger.debug(f"Found {len(cache_keys)} cache keys from stats")
                except Exception as e:
                    logger.debug(f"Could not get cache keys from stats: {e}")

        except Exception as e:
            logger.debug(f"Could not enumerate cache keys: {e}")

        return cache_keys

    def _fallback_clear_common_profiles(self) -> None:
        """Fallback method to clear common profile patterns."""
        base_keys = [self.ORG_SNAPSHOT_KEY, self.ACCOUNT_COUNT_KEY]

        # Extended list of common profile names
        common_profiles = [
            "default",
            "prod",
            "production",
            "dev",
            "development",
            "staging",
            "test",
            "sandbox",
            "demo",
            "qa",
            "uat",
            "master",
            "main",
            "admin",
            "root",
            "shared",
            # Add some common AWS profile patterns
            "sso",
            "saml",
            "federated",
            "assume-role",
            # Add some organization-specific patterns
            "org",
            "organization",
            "management",
            "security",
            "logging",
            "audit",
            "billing",
            "compliance",
        ]

        cleared_count = 0

        for base_key in base_keys:
            # Clear the base key (for backward compatibility)
            try:
                self.cache_manager.invalidate(base_key)
                cleared_count += 1
            except Exception:
                pass

            # Clear profile-specific keys
            for profile in common_profiles:
                try:
                    profile_key = f"{base_key}_{profile}"
                    self.cache_manager.invalidate(profile_key)
                    cleared_count += 1
                except Exception:
                    pass

        # Also try to clear individual account cache entries with common patterns
        for profile in common_profiles:
            try:
                # This is a pattern match - we can't enumerate all account IDs
                # but we can try some common patterns
                # Note: This won't work perfectly without enumeration
                # but it's better than nothing
                pass
            except Exception:
                pass

        logger.info(f"Fallback clearing completed, attempted to clear {cleared_count} entries")

    def force_clear_all_account_cache(self) -> int:
        """
        Force clear all account-related cache by using cache statistics and brute force.

        Since cache key enumeration is not supported by all backends, this method
        uses different strategies based on the profile and situation.

        Returns:
            Number of cache entries cleared
        """
        cleared_count = 0

        try:
            # Get initial cache stats
            initial_stats = self.cache_manager.get_cache_stats()
            initial_entries = initial_stats.get("total_entries", 0)

            logger.info(f"Starting cache clear. Initial entries: {initial_entries}")

            if self.profile == "*":
                # For wildcard profile, clear all cache since we can't enumerate keys
                logger.info("Wildcard profile specified - clearing all cache entries")
                try:
                    self.cache_manager.invalidate()  # Clear all cache
                    cleared_count = initial_entries
                    logger.info(f"Cleared all {initial_entries} cache entries")
                except Exception as e:
                    logger.warning(f"Failed to clear all cache: {e}")
            else:
                # For specific profiles, try known patterns
                logger.info(f"Attempting to clear account cache for profile: {self.profile}")

                # Method 1: Clear known account-related patterns for this profile
                account_patterns = [
                    self.ORG_SNAPSHOT_KEY,
                    self.ACCOUNT_COUNT_KEY,
                    "account_details_",
                    "org_snapshot_",
                    "org_account_count_",
                ]

                # Try to clear profile-specific keys
                for pattern in account_patterns:
                    # Clear base pattern (for backward compatibility)
                    try:
                        self.cache_manager.invalidate(pattern)
                        cleared_count += 1
                        logger.debug(f"Cleared base pattern: {pattern}")
                    except Exception:
                        pass

                    # Clear profile-specific variation
                    try:
                        key = f"{pattern}_{self.profile}"
                        self.cache_manager.invalidate(key)
                        cleared_count += 1
                        logger.debug(f"Cleared profile key: {key}")
                    except Exception:
                        pass

                # Method 2: Try enumeration if available
                try:
                    cache_keys = self._enumerate_cache_keys()
                    if cache_keys:
                        logger.info(f"Found {len(cache_keys)} cache keys to examine")

                        # Look for keys that match our profile or are account-related
                        account_related_patterns = [
                            "org_snapshot",
                            "account_count",
                            "account_details",
                            "organization",
                            "accounts",
                            "multi_account",
                            "list_accounts",
                            "describe_account",
                            "list_roots",
                            "list_organizational_units",
                            "list_parents",
                        ]

                        for key in cache_keys:
                            key_lower = key.lower()
                            # Check if key contains our profile name or is account-related
                            if self.profile in key_lower or any(
                                pattern in key_lower for pattern in account_related_patterns
                            ):
                                try:
                                    self.cache_manager.invalidate(key)
                                    cleared_count += 1
                                    logger.debug(f"Cleared enumerated key: {key}")
                                except Exception:
                                    pass
                    else:
                        logger.info("Cache key enumeration not available")
                except Exception as e:
                    logger.debug(f"Cache key enumeration failed: {e}")

            # Get final stats
            final_stats = self.cache_manager.get_cache_stats()
            final_entries = final_stats.get("total_entries", 0)
            actual_cleared = initial_entries - final_entries

            logger.info(
                f"Cache clearing completed. Entries: {initial_entries} → {final_entries} (actually cleared: {actual_cleared})"
            )

            # Return the actual number cleared, not the attempted count
            return actual_cleared if actual_cleared > 0 else cleared_count

        except Exception as e:
            logger.error(f"Failed to force clear account cache: {e}")
            return cleared_count

    def inspect_cache_keys(self) -> Dict[str, Any]:
        """
        Inspect cache to understand what keys actually exist.

        This is a diagnostic method to help understand cache structure.

        Returns:
            Dictionary with cache inspection results
        """
        inspection = {
            "total_entries": 0,
            "account_related_keys": [],
            "other_keys": [],
            "key_patterns": {},
            "sample_keys": [],
        }

        try:
            # Get cache stats
            stats = self.cache_manager.get_cache_stats()
            inspection["total_entries"] = stats.get("total_entries", 0)

            # Try to enumerate cache keys
            cache_keys = self._enumerate_cache_keys()

            if cache_keys:
                inspection["sample_keys"] = cache_keys[:10]  # First 10 keys as samples

                # Categorize keys
                account_patterns = [
                    "org_snapshot",
                    "account_count",
                    "account_details",
                    "organization",
                    "accounts",
                    "multi_account",
                ]

                for key in cache_keys:
                    is_account_related = False
                    for pattern in account_patterns:
                        if pattern in key.lower():
                            inspection["account_related_keys"].append(key)
                            is_account_related = True
                            break

                    if not is_account_related:
                        inspection["other_keys"].append(key)

                # Analyze key patterns
                patterns = {}
                for key in cache_keys:
                    # Extract pattern (first part before underscore or full key if no underscore)
                    pattern = key.split("_")[0] if "_" in key else key
                    patterns[pattern] = patterns.get(pattern, 0) + 1

                inspection["key_patterns"] = patterns

            else:
                inspection["enumeration_failed"] = True
                inspection["message"] = (
                    "Could not enumerate cache keys - may need different approach"
                )

        except Exception as e:
            inspection["error"] = str(e)

        return inspection

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for account-related entries."""
        stats = {
            "org_snapshot_cached": False,
            "account_count_cached": False,
            "org_snapshot_age_seconds": None,
            "account_count_age_seconds": None,
        }

        try:
            # Check organization snapshot
            snapshot = self._get_cached_org_snapshot()
            if snapshot:
                stats["org_snapshot_cached"] = True
                age = datetime.now() - snapshot.cached_at
                stats["org_snapshot_age_seconds"] = int(age.total_seconds())

            # Check account count
            cached_count = self._get_cached_account_count()
            if cached_count is not None:
                stats["account_count_cached"] = True
                # We don't have age info for simple cached values
                # This would require storing metadata with the cache entry

        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")

        return stats
