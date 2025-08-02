"""Tests for cache management commands."""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from typer.testing import CliRunner

from src.awsideman.commands.cache import app
from src.awsideman.utils.models import CacheEntry, CacheConfig


@pytest.fixture
def runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_cache_manager():
    """Create a mock cache manager."""
    mock = Mock()
    mock.config = CacheConfig()
    return mock


class TestCacheStatusCommand:
    """Tests for the cache status command."""
    
    def test_cache_status_with_empty_cache(self, runner, mock_cache_manager):
        """Test cache status command with empty cache."""
        # Mock empty cache stats
        mock_cache_manager.get_cache_stats.return_value = {
            'enabled': True,
            'total_entries': 0,
            'valid_entries': 0,
            'expired_entries': 0,
            'total_size_bytes': 0,
            'total_size_mb': 0.0,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100
        }
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['status'])
        
        assert result.exit_code == 0
        assert "Cache Status" in result.stdout
        assert "Cache Enabled: Yes" in result.stdout
        assert "Total Entries: 0" in result.stdout
        assert "No cache entries found." in result.stdout
    
    def test_cache_status_with_entries(self, runner, mock_cache_manager):
        """Test cache status command with cache entries."""
        # Mock cache stats with entries
        mock_cache_manager.get_cache_stats.return_value = {
            'enabled': True,
            'total_entries': 2,
            'valid_entries': 1,
            'expired_entries': 1,
            'total_size_bytes': 2048,
            'total_size_mb': 0.002,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100
        }
        
        # Mock cache files
        mock_file1 = Mock()
        mock_file1.name = "file1.json"
        mock_file1.stat.return_value.st_size = 1024
        
        mock_file2 = Mock()
        mock_file2.name = "file2.json"
        mock_file2.stat.return_value.st_size = 1024
        
        mock_cache_manager.path_manager.list_cache_files.return_value = [mock_file1, mock_file2]
        
        # Mock file contents
        current_time = time.time()
        cache_data1 = {
            'data': {'test': 'data1'},
            'created_at': current_time - 1800,  # 30 minutes ago
            'ttl': 3600,
            'key': 'test_key1',
            'operation': 'list_users'
        }
        
        cache_data2 = {
            'data': {'test': 'data2'},
            'created_at': current_time - 7200,  # 2 hours ago (expired)
            'ttl': 3600,
            'key': 'test_key2',
            'operation': 'list_groups'
        }
        
        def mock_open_side_effect(file_path, *args, **kwargs):
            mock_file = MagicMock()
            if 'file1.json' in str(file_path):
                mock_file.__enter__.return_value.read.return_value = json.dumps(cache_data1)
            else:
                mock_file.__enter__.return_value.read.return_value = json.dumps(cache_data2)
            return mock_file
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('builtins.open', side_effect=mock_open_side_effect), \
             patch('json.load') as mock_json_load:
            
            # Configure json.load to return appropriate data
            mock_json_load.side_effect = [cache_data1, cache_data2]
            
            result = runner.invoke(app, ['status'])
        
        assert result.exit_code == 0
        assert "Cache Status" in result.stdout
        assert "Total Entries: 2" in result.stdout
        assert "Valid Entries: 1" in result.stdout
        assert "Expired Entries: 1" in result.stdout
        assert "Recent Cache Entries" in result.stdout
    
    def test_cache_status_disabled(self, runner, mock_cache_manager):
        """Test cache status command when cache is disabled."""
        mock_cache_manager.get_cache_stats.return_value = {
            'enabled': False,
            'total_entries': 0,
            'valid_entries': 0,
            'expired_entries': 0,
            'total_size_bytes': 0,
            'total_size_mb': 0.0,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100
        }
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['status'])
        
        assert result.exit_code == 0
        assert "Cache Enabled: No" in result.stdout
        assert "Cache is disabled. No statistics available." in result.stdout
    
    def test_cache_status_error(self, runner, mock_cache_manager):
        """Test cache status command when there's an error."""
        mock_cache_manager.get_cache_stats.return_value = {
            'enabled': True,
            'error': 'Test error message'
        }
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['status'])
        
        assert result.exit_code == 0
        assert "Error getting cache status: Test error message" in result.stdout
    
    def test_cache_status_exception(self, runner):
        """Test cache status command when CacheManager raises an exception."""
        with patch('src.awsideman.commands.cache.CacheManager', side_effect=Exception("Test exception")):
            result = runner.invoke(app, ['status'])
        
        assert result.exit_code == 1
        assert "Error displaying cache status: Test exception" in result.stdout


class TestCacheWarmCommand:
    """Tests for the cache warm command."""
    
    def test_cache_warm_success(self, runner, mock_cache_manager):
        """Test cache warm command with successful execution."""
        # Mock cache stats before and after
        mock_cache_manager.get_cache_stats.side_effect = [
            {
                'enabled': True,
                'total_entries': 0,
                'valid_entries': 0,
                'expired_entries': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0.0,
                'cache_directory': '/test/cache',
                'default_ttl': 3600,
                'max_size_mb': 100
            },
            {
                'enabled': True,
                'total_entries': 1,
                'valid_entries': 1,
                'expired_entries': 0,
                'total_size_bytes': 1024,
                'total_size_mb': 0.001,
                'cache_directory': '/test/cache',
                'default_ttl': 3600,
                'max_size_mb': 100
            }
        ]
        
        # Mock successful subprocess execution
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', return_value=mock_result):
            
            result = runner.invoke(app, ['warm', 'user list --limit 5'])
        
        assert result.exit_code == 0
        assert "Warming cache for command: user list --limit 5" in result.stdout
        assert "Cache warmed successfully! Added 1 new cache entries." in result.stdout
        assert "Total cache entries: 1" in result.stdout
    
    def test_cache_warm_already_warm(self, runner, mock_cache_manager):
        """Test cache warm command when cache is already warm."""
        # Mock cache stats (same before and after)
        cache_stats = {
            'enabled': True,
            'total_entries': 1,
            'valid_entries': 1,
            'expired_entries': 0,
            'total_size_bytes': 1024,
            'total_size_mb': 0.001,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100
        }
        mock_cache_manager.get_cache_stats.return_value = cache_stats
        
        # Mock successful subprocess execution
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', return_value=mock_result):
            
            result = runner.invoke(app, ['warm', 'user list --limit 5'])
        
        assert result.exit_code == 0
        assert "Cache was already warm for this command (no new entries added)." in result.stdout
        assert "Total cache entries: 1" in result.stdout
    
    def test_cache_warm_disabled(self, runner, mock_cache_manager):
        """Test cache warm command when cache is disabled."""
        mock_cache_manager.config.enabled = False
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['warm', 'user list'])
        
        assert result.exit_code == 0
        assert "Cache is disabled. Cannot warm cache." in result.stdout
    
    def test_cache_warm_empty_command(self, runner, mock_cache_manager):
        """Test cache warm command with empty command."""
        mock_cache_manager.config.enabled = True
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['warm', ''])
        
        assert result.exit_code == 1
        assert "Error: Empty command provided" in result.stdout
    
    def test_cache_warm_cache_command_recursion(self, runner, mock_cache_manager):
        """Test cache warm command with cache command (should prevent recursion)."""
        mock_cache_manager.config.enabled = True
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['warm', 'cache status'])
        
        assert result.exit_code == 1
        assert "Error: Cannot warm cache commands (would cause recursion)" in result.stdout
    
    def test_cache_warm_invalid_command(self, runner, mock_cache_manager):
        """Test cache warm command with invalid command."""
        mock_cache_manager.config.enabled = True
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['warm', 'invalid command'])
        
        assert result.exit_code == 1
        assert "Error: Unknown command 'invalid'" in result.stdout
        assert "Valid commands:" in result.stdout
        assert "user, group, permission-set" in result.stdout
    
    def test_cache_warm_command_failure(self, runner, mock_cache_manager):
        """Test cache warm command when the executed command fails."""
        mock_cache_manager.config.enabled = True
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        # Mock failed subprocess execution
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "Command failed"
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', return_value=mock_result):
            
            result = runner.invoke(app, ['warm', 'user list'])
        
        assert result.exit_code == 1
        assert "Error executing command: Command failed" in result.stdout
    
    def test_cache_warm_timeout(self, runner, mock_cache_manager):
        """Test cache warm command when the executed command times out."""
        mock_cache_manager.config.enabled = True
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        # Mock timeout exception
        from subprocess import TimeoutExpired
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', side_effect=TimeoutExpired('cmd', 300)):
            
            result = runner.invoke(app, ['warm', 'user list'])
        
        assert result.exit_code == 1
        assert "Error: Command timed out after 5 minutes" in result.stdout
    
    def test_cache_warm_file_not_found(self, runner, mock_cache_manager):
        """Test cache warm command when awsideman executable is not found."""
        mock_cache_manager.config.enabled = True
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', side_effect=FileNotFoundError()):
            
            result = runner.invoke(app, ['warm', 'user list'])
        
        assert result.exit_code == 1
        assert "Error: Could not find awsideman executable" in result.stdout
        assert "installed and in" in result.stdout

class TestCacheClearCommand:
    """Tests for the cache clear command."""
    
    def test_cache_clear_success(self, runner, mock_cache_manager):
        """Test cache clear command with successful execution."""
        mock_cache_manager.config.enabled = True
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['clear'], input='y\n')
        
        assert result.exit_code == 0
        assert "Are you sure you want to clear all cache entries?" in result.stdout
        assert "Cache cleared successfully!" in result.stdout
        mock_cache_manager.invalidate.assert_called_once_with()
    
    def test_cache_clear_cancelled(self, runner, mock_cache_manager):
        """Test cache clear command when user cancels."""
        mock_cache_manager.config.enabled = True
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['clear'], input='n\n')
        
        assert result.exit_code == 0
        assert "Cache clear cancelled." in result.stdout
        mock_cache_manager.invalidate.assert_not_called()
    
    def test_cache_clear_force(self, runner, mock_cache_manager):
        """Test cache clear command with force flag."""
        mock_cache_manager.config.enabled = True
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['clear', '--force'])
        
        assert result.exit_code == 0
        assert "Cache cleared successfully!" in result.stdout
        mock_cache_manager.invalidate.assert_called_once_with()
    
    def test_cache_clear_disabled(self, runner, mock_cache_manager):
        """Test cache clear command when cache is disabled."""
        mock_cache_manager.config.enabled = False
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['clear'])
        
        assert result.exit_code == 0
        assert "Cache is disabled. Nothing to clear." in result.stdout
        mock_cache_manager.invalidate.assert_not_called()
    
    def test_cache_clear_error(self, runner, mock_cache_manager):
        """Test cache clear command when invalidation fails."""
        mock_cache_manager.config.enabled = True
        mock_cache_manager.invalidate.side_effect = Exception("Clear failed")
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['clear', '--force'])
        
        assert result.exit_code == 1
        assert "Error clearing cache: Clear failed" in result.stdout


class TestCacheIntegrationScenarios:
    """Integration tests for cache commands with realistic scenarios."""
    
    def test_cache_lifecycle_integration(self, runner):
        """Test complete cache lifecycle: warm -> status -> clear."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        
        # Initial empty cache
        empty_stats = {
            'enabled': True,
            'total_entries': 0,
            'valid_entries': 0,
            'expired_entries': 0,
            'total_size_bytes': 0,
            'total_size_mb': 0.0,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100
        }
        
        # Cache after warming
        warm_stats = {
            'enabled': True,
            'total_entries': 3,
            'valid_entries': 3,
            'expired_entries': 0,
            'total_size_bytes': 3072,
            'total_size_mb': 0.003,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100
        }
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            # 1. Check initial empty status
            mock_cache_manager.get_cache_stats.return_value = empty_stats
            result = runner.invoke(app, ['status'])
            assert result.exit_code == 0
            assert "Total Entries: 0" in result.stdout
            
            # 2. Warm the cache
            mock_cache_manager.get_cache_stats.side_effect = [empty_stats, warm_stats]
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            
            with patch('src.awsideman.commands.cache.subprocess.run', return_value=mock_result):
                result = runner.invoke(app, ['warm', 'user list'])
            
            assert result.exit_code == 0
            assert "Added 3 new cache entries" in result.stdout
            
            # 3. Check status after warming
            mock_cache_manager.get_cache_stats.return_value = warm_stats
            mock_cache_manager.get_cache_stats.side_effect = None
            result = runner.invoke(app, ['status'])
            assert result.exit_code == 0
            assert "Total Entries: 3" in result.stdout
            
            # 4. Clear the cache
            result = runner.invoke(app, ['clear', '--force'])
            assert result.exit_code == 0
            assert "Cache cleared successfully!" in result.stdout
            mock_cache_manager.invalidate.assert_called_with()
    
    def test_cache_warm_multiple_commands(self, runner):
        """Test warming cache with multiple different commands."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        
        commands_to_warm = [
            'user list',
            'group list',
            'permission-set list'
        ]
        
        # Mock progressive cache growth
        cache_stats_progression = [
            {'total_entries': 0},  # Initial
            {'total_entries': 2},  # After user list
            {'total_entries': 4},  # After group list  
            {'total_entries': 6}   # After permission-set list
        ]
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', return_value=mock_result):
            
            for i, command in enumerate(commands_to_warm):
                # Set up stats for before and after this command
                mock_cache_manager.get_cache_stats.side_effect = [
                    cache_stats_progression[i],
                    cache_stats_progression[i + 1]
                ]
                
                result = runner.invoke(app, ['warm', command])
                assert result.exit_code == 0
                assert f"Added {cache_stats_progression[i + 1]['total_entries'] - cache_stats_progression[i]['total_entries']} new cache entries" in result.stdout
    
    def test_cache_status_with_mixed_entry_states(self, runner):
        """Test cache status with a mix of valid, expired, and corrupted entries."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        
        # Mock cache stats with mixed states
        mixed_stats = {
            'enabled': True,
            'total_entries': 5,
            'valid_entries': 2,
            'expired_entries': 2,
            'corrupted_entries': 1,
            'total_size_bytes': 5120,
            'total_size_mb': 0.005,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100,
            'warning': '1 corrupted cache files detected'
        }
        
        mock_cache_manager.get_cache_stats.return_value = mixed_stats
        
        # Mock cache files with different states
        current_time = time.time()
        cache_files = []
        cache_data_list = []
        
        # Valid entries
        for i in range(2):
            mock_file = Mock()
            mock_file.name = f"valid_{i}.json"
            mock_file.stat.return_value.st_size = 1024
            cache_files.append(mock_file)
            
            cache_data = {
                'data': {'test': f'valid_data_{i}'},
                'created_at': current_time - 1800,  # 30 minutes ago
                'ttl': 3600,
                'key': f'valid_key_{i}',
                'operation': f'test_op_{i}'
            }
            cache_data_list.append(cache_data)
        
        # Expired entries
        for i in range(2):
            mock_file = Mock()
            mock_file.name = f"expired_{i}.json"
            mock_file.stat.return_value.st_size = 1024
            cache_files.append(mock_file)
            
            cache_data = {
                'data': {'test': f'expired_data_{i}'},
                'created_at': current_time - 7200,  # 2 hours ago (expired)
                'ttl': 3600,
                'key': f'expired_key_{i}',
                'operation': f'test_op_{i}'
            }
            cache_data_list.append(cache_data)
        
        # Corrupted entry (will cause JSON decode error)
        mock_file = Mock()
        mock_file.name = "corrupted.json"
        mock_file.stat.return_value.st_size = 1024
        cache_files.append(mock_file)
        
        mock_cache_manager.path_manager.list_cache_files.return_value = cache_files
        
        def mock_json_load_side_effect(*args, **kwargs):
            # Return data for valid/expired files, raise error for corrupted
            call_count = mock_json_load_side_effect.call_count
            mock_json_load_side_effect.call_count += 1
            
            if call_count < len(cache_data_list):
                return cache_data_list[call_count]
            else:
                raise json.JSONDecodeError("Invalid JSON", "", 0)
        
        mock_json_load_side_effect.call_count = 0
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('json.load', side_effect=mock_json_load_side_effect):
            
            result = runner.invoke(app, ['status'])
        
        assert result.exit_code == 0
        assert "Total Entries: 5" in result.stdout
        assert "Valid Entries: 2" in result.stdout
        assert "Expired Entries: 2" in result.stdout
        assert "Corrupted Entries: 1" in result.stdout
        assert "Warning: 1 corrupted cache files detected" in result.stdout
    
    def test_cache_warm_with_profile_switching(self, runner):
        """Test cache warming behavior with different AWS profiles."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        
        # Mock different cache states for different profiles
        profile_cache_stats = {
            'profile1': {'total_entries': 0},
            'profile2': {'total_entries': 0}
        }
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', return_value=mock_result):
            
            # Warm cache for profile1
            mock_cache_manager.get_cache_stats.side_effect = [
                profile_cache_stats['profile1'],
                {'total_entries': 2}
            ]
            
            result = runner.invoke(app, ['warm', 'user list --profile profile1'])
            assert result.exit_code == 0
            assert "Added 2 new cache entries" in result.stdout
            
            # Warm cache for profile2 (should be separate)
            mock_cache_manager.get_cache_stats.side_effect = [
                profile_cache_stats['profile2'],
                {'total_entries': 2}
            ]
            
            result = runner.invoke(app, ['warm', 'user list --profile profile2'])
            assert result.exit_code == 0
            assert "Added 2 new cache entries" in result.stdout
    
    def test_cache_error_recovery(self, runner):
        """Test cache command error recovery scenarios."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            # Test status command with cache manager error
            mock_cache_manager.get_cache_stats.side_effect = Exception("Cache stats error")
            result = runner.invoke(app, ['status'])
            assert result.exit_code == 1
            assert "Error displaying cache status" in result.stdout
            
            # Reset for next test
            mock_cache_manager.get_cache_stats.side_effect = None
            mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
            
            # Test clear command with invalidation error
            mock_cache_manager.invalidate.side_effect = Exception("Invalidation error")
            result = runner.invoke(app, ['clear', '--force'])
            assert result.exit_code == 1
            assert "Error clearing cache" in result.stdout


class TestCacheCommandValidation:
    """Tests for cache command input validation and edge cases."""
    
    def test_cache_warm_command_validation(self, runner):
        """Test validation of commands passed to cache warm."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            # Test empty command
            result = runner.invoke(app, ['warm', ''])
            assert result.exit_code == 1
            assert "Empty command provided" in result.stdout
            
            # Test whitespace-only command
            result = runner.invoke(app, ['warm', '   '])
            assert result.exit_code == 1
            assert "Empty command provided" in result.stdout
            
            # Test cache command recursion prevention
            cache_commands = ['cache status', 'cache clear', 'cache warm user list']
            for cmd in cache_commands:
                result = runner.invoke(app, ['warm', cmd])
                assert result.exit_code == 1
                assert "Cannot warm cache commands" in result.stdout
    
    def test_cache_warm_valid_command_detection(self, runner):
        """Test detection of valid awsideman commands for warming."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            # Test valid commands
            valid_commands = [
                'user list',
                'group list --limit 10',
                'permission-set list',
                'org tree',
                'org account 123456789012'
            ]
            
            for cmd in valid_commands:
                # Mock successful execution
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stderr = ""
                
                with patch('src.awsideman.commands.cache.subprocess.run', return_value=mock_result):
                    mock_cache_manager.get_cache_stats.side_effect = [
                        {'total_entries': 0},
                        {'total_entries': 1}
                    ]
                    
                    result = runner.invoke(app, ['warm', cmd])
                    assert result.exit_code == 0, f"Command '{cmd}' should be valid"
                    assert "Cache warmed successfully" in result.stdout
    
    def test_cache_status_output_formatting(self, runner):
        """Test cache status output formatting with various data scenarios."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        
        # Test with large cache sizes
        large_cache_stats = {
            'enabled': True,
            'total_entries': 1000,
            'valid_entries': 800,
            'expired_entries': 150,
            'corrupted_entries': 50,
            'total_size_bytes': 104857600,  # 100 MB
            'total_size_mb': 100.0,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 200
        }
        
        mock_cache_manager.get_cache_stats.return_value = large_cache_stats
        mock_cache_manager.path_manager.list_cache_files.return_value = []
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            result = runner.invoke(app, ['status'])
        
        assert result.exit_code == 0
        assert "Total Entries: 1000" in result.stdout
        assert "Valid Entries: 800" in result.stdout
        assert "Expired Entries: 150" in result.stdout
        assert "Corrupted Entries: 50" in result.stdout
        assert "Total Size: 100.0 MB" in result.stdout
        
        # Test with zero-size cache
        zero_cache_stats = {
            'enabled': True,
            'total_entries': 0,
            'valid_entries': 0,
            'expired_entries': 0,
            'corrupted_entries': 0,
            'total_size_bytes': 0,
            'total_size_mb': 0.0,
            'cache_directory': '/test/cache',
            'default_ttl': 3600,
            'max_size_mb': 100
        }
        
        mock_cache_manager.get_cache_stats.return_value = zero_cache_stats
        
        result = runner.invoke(app, ['status'])
        assert result.exit_code == 0
        assert "No cache entries found." in result.stdout
    
    def test_cache_warm_timeout_handling(self, runner):
        """Test cache warm command timeout handling."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        from subprocess import TimeoutExpired
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager), \
             patch('src.awsideman.commands.cache.subprocess.run', side_effect=TimeoutExpired('awsideman', 300)):
            
            result = runner.invoke(app, ['warm', 'user list'])
        
        assert result.exit_code == 1
        assert "Command timed out after 5 minutes" in result.stdout
    
    def test_cache_warm_subprocess_errors(self, runner):
        """Test cache warm command with various subprocess errors."""
        mock_cache_manager = Mock()
        mock_cache_manager.config = CacheConfig(enabled=True)
        mock_cache_manager.get_cache_stats.return_value = {'total_entries': 0}
        
        with patch('src.awsideman.commands.cache.CacheManager', return_value=mock_cache_manager):
            # Test FileNotFoundError
            with patch('src.awsideman.commands.cache.subprocess.run', side_effect=FileNotFoundError()):
                result = runner.invoke(app, ['warm', 'user list'])
                assert result.exit_code == 1
                assert "Could not find awsideman executable" in result.stdout
            
            # Test PermissionError
            with patch('src.awsideman.commands.cache.subprocess.run', side_effect=PermissionError("Permission denied")):
                result = runner.invoke(app, ['warm', 'user list'])
                assert result.exit_code == 1
                assert "Permission denied" in result.stdout
            
            # Test generic OSError
            with patch('src.awsideman.commands.cache.subprocess.run', side_effect=OSError("Generic OS error")):
                result = runner.invoke(app, ['warm', 'user list'])
                assert result.exit_code == 1
                assert "Error executing command" in result.stdout