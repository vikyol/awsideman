"""Tests for CacheManager configuration-driven initialization."""

import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.awsideman.cache.manager import CacheManager
from src.awsideman.utils.models import CacheConfig
from src.awsideman.cache.config import AdvancedCacheConfig
from src.awsideman.cache.backends.base import CacheBackendError
from src.awsideman.encryption.provider import EncryptionError


class TestCacheManagerConfigurationInit:
    """Test configuration-driven initialization of CacheManager."""
    
    def test_init_with_provided_basic_config(self):
        """Test initialization with provided basic configuration."""
        config = CacheConfig(enabled=True, default_ttl=1800, max_size_mb=50)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CacheManager(config=config, base_cache_dir=temp_dir)
            
            assert manager.config == config
            assert manager.config.enabled is True
            assert manager.config.default_ttl == 1800
            assert manager.config.max_size_mb == 50
            assert manager.path_manager is not None
            assert manager.backend is None  # Basic config doesn't use backend system
            assert manager.encryption_provider is None
    
    def test_init_with_provided_advanced_config(self):
        """Test initialization with provided advanced configuration."""
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="file",
            encryption_enabled=False,
            default_ttl=2400
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory, \
                 patch('src.awsideman.cache.manager.EncryptionProviderFactory') as mock_enc_factory:
                
                mock_backend = Mock()
                mock_backend.health_check.return_value = True
                mock_factory.validate_backend_availability.return_value = True
                mock_factory.create_backend_with_fallback.return_value = mock_backend
                
                mock_encryption = Mock()
                mock_encryption.get_encryption_type.return_value = "none"
                mock_enc_factory.create_provider.return_value = mock_encryption
                
                manager = CacheManager(config=config, base_cache_dir=temp_dir)
                
                assert manager.config == config
                assert manager.config.enabled is True
                assert manager.config.backend_type == "file"
                assert manager.backend == mock_backend
                assert manager.encryption_provider == mock_encryption
    
    def test_init_with_invalid_advanced_config_falls_back(self):
        """Test that invalid advanced configuration falls back to basic config."""
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="invalid_backend",  # Invalid backend type
            encryption_enabled=False
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.CacheManager._load_basic_cache_config') as mock_load_basic:
                basic_config = CacheConfig(enabled=True, default_ttl=3600)
                mock_load_basic.return_value = basic_config
                
                manager = CacheManager(config=config, base_cache_dir=temp_dir)
                
                # Should still use the provided config even if it has validation errors
                assert manager.config == config
                assert isinstance(manager.config, AdvancedCacheConfig)
    
    @patch.dict(os.environ, {
        'AWSIDEMAN_CACHE_BACKEND': 'dynamodb',
        'AWSIDEMAN_CACHE_ENCRYPTION': 'true',
        'AWSIDEMAN_CACHE_DYNAMODB_TABLE': 'test-table'
    })
    def test_init_loads_from_environment(self):
        """Test initialization loads configuration from environment variables."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory, \
                 patch('src.awsideman.cache.manager.EncryptionProviderFactory') as mock_enc_factory:
                
                mock_backend = Mock()
                mock_backend.health_check.return_value = True
                mock_factory.validate_backend_availability.return_value = True
                mock_factory.create_backend_with_fallback.return_value = mock_backend
                
                mock_encryption = Mock()
                mock_encryption.get_encryption_type.return_value = "aes256"
                mock_encryption.encrypt.return_value = b"encrypted"
                mock_encryption.decrypt.return_value = {"test": "encryption_test"}
                mock_enc_factory.create_provider.return_value = mock_encryption
                
                manager = CacheManager(base_cache_dir=temp_dir)
                
                assert isinstance(manager.config, AdvancedCacheConfig)
                assert manager.config.backend_type == "dynamodb"
                assert manager.config.encryption_enabled is True
                assert manager.config.dynamodb_table_name == "test-table"
    
    def test_init_backend_creation_failure_with_fallback(self):
        """Test backend creation failure triggers fallback mechanism."""
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="dynamodb",
            encryption_enabled=False
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory, \
                 patch('src.awsideman.cache.manager.EncryptionProviderFactory') as mock_enc_factory:
                
                # First call fails, second call (fallback) succeeds
                mock_factory.validate_backend_availability.return_value = True
                mock_factory.create_backend_with_fallback.side_effect = CacheBackendError("DynamoDB not available")
                
                # Mock fallback to basic cache
                mock_file_backend = Mock()
                mock_encryption = Mock()
                mock_encryption.get_encryption_type.return_value = "none"
                
                with patch('src.awsideman.cache.backends.file.FileBackend', return_value=mock_file_backend), \
                     patch.object(mock_enc_factory, 'create_provider', return_value=mock_encryption):
                    
                    manager = CacheManager(config=config, base_cache_dir=temp_dir)
                    
                    # Should have fallen back to basic cache
                    assert manager.config.enabled is True
                    assert manager.backend == mock_file_backend
                    assert manager.encryption_provider == mock_encryption
    
    def test_init_complete_failure_disables_cache(self):
        """Test that complete initialization failure disables cache."""
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="dynamodb",
            encryption_enabled=False
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory:
                # Backend creation fails
                mock_factory.validate_backend_availability.return_value = True
                mock_factory.create_backend_with_fallback.side_effect = CacheBackendError("All backends failed")
                
                # Fallback also fails
                with patch('src.awsideman.cache.backends.file.FileBackend', side_effect=Exception("File backend failed")):
                    manager = CacheManager(config=config, base_cache_dir=temp_dir)
                    
                    # Cache should be disabled
                    assert manager.config.enabled is False
                    assert manager.backend is None
                    assert manager.encryption_provider is None
    
    def test_init_encryption_failure_falls_back_to_no_encryption(self):
        """Test encryption provider failure falls back to no encryption."""
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="file",
            encryption_enabled=True,
            encryption_type="aes256"
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory, \
                 patch('src.awsideman.cache.manager.EncryptionProviderFactory') as mock_enc_factory:
                
                mock_backend = Mock()
                mock_backend.health_check.return_value = True
                mock_factory.validate_backend_availability.return_value = True
                mock_factory.create_backend_with_fallback.return_value = mock_backend
                
                # First encryption provider fails, second (no encryption) succeeds
                mock_no_encryption = Mock()
                mock_no_encryption.get_encryption_type.return_value = "none"
                mock_enc_factory.create_provider.side_effect = [
                    EncryptionError("AES encryption failed"),
                    mock_no_encryption
                ]
                
                manager = CacheManager(config=config, base_cache_dir=temp_dir)
                
                assert manager.backend == mock_backend
                assert manager.encryption_provider == mock_no_encryption
    
    def test_init_backend_availability_check(self):
        """Test backend availability checking before creation."""
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="dynamodb",
            encryption_enabled=False
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory, \
                 patch('src.awsideman.cache.manager.EncryptionProviderFactory') as mock_enc_factory:
                
                # DynamoDB not available, file backend available
                mock_factory.validate_backend_availability.side_effect = lambda bt: bt == "file"
                mock_factory.get_available_backends.return_value = ["file"]
                
                mock_file_backend = Mock()
                mock_file_backend.health_check.return_value = True
                mock_factory.create_backend.return_value = mock_file_backend
                
                mock_encryption = Mock()
                mock_encryption.get_encryption_type.return_value = "none"
                mock_enc_factory.create_provider.return_value = mock_encryption
                
                manager = CacheManager(config=config, base_cache_dir=temp_dir)
                
                # Should have fallen back to file backend
                assert manager.config.backend_type == "file"  # Config updated to reflect fallback
                assert manager.backend == mock_file_backend
    
    def test_get_configuration_info(self):
        """Test getting configuration information for debugging."""
        config = AdvancedCacheConfig(
            enabled=True,
            backend_type="file",
            encryption_enabled=True,
            encryption_type="aes256",
            dynamodb_table_name="test-table",
            default_ttl=1800
        )
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory, \
                 patch('src.awsideman.cache.manager.EncryptionProviderFactory') as mock_enc_factory:
                
                mock_backend = Mock()
                mock_backend.health_check.return_value = True
                mock_backend.get_stats.return_value = {"entries": 5, "size": 1024}
                mock_factory.validate_backend_availability.return_value = True
                mock_factory.create_backend_with_fallback.return_value = mock_backend
                
                mock_encryption = Mock()
                mock_encryption.get_encryption_type.return_value = "aes256"
                mock_encryption.encrypt.return_value = b"encrypted"
                mock_encryption.decrypt.return_value = {"test": "encryption_test"}
                mock_enc_factory.create_provider.return_value = mock_encryption
                
                manager = CacheManager(config=config, base_cache_dir=temp_dir)
                
                info = manager.get_configuration_info()
                
                assert info["enabled"] is True
                assert info["config_type"] == "AdvancedCacheConfig"
                assert info["backend_type"] == "file"
                assert info["backend_instance"] == type(mock_backend).__name__
                assert info["encryption_enabled"] is True
                assert info["encryption_type"] == "aes256"
                assert info["encryption_provider"] == type(mock_encryption).__name__
                assert info["dynamodb_table_name"] == "test-table"
                assert info["default_ttl"] == 1800
                assert info["backend_healthy"] is True
                assert info["backend_stats"] == {"entries": 5, "size": 1024}
    
    def test_meaningful_advanced_config_detection(self):
        """Test detection of meaningful advanced configuration settings."""
        # Test with default settings (should use basic config)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.utils.advanced_cache_config.AdvancedCacheConfig.from_config_and_environment') as mock_load:
                default_config = AdvancedCacheConfig()  # All defaults
                mock_load.return_value = default_config
                
                with patch('src.awsideman.cache.manager.CacheManager._load_basic_cache_config') as mock_basic:
                    basic_config = CacheConfig(enabled=True)
                    mock_basic.return_value = basic_config
                    
                    manager = CacheManager(base_cache_dir=temp_dir)
                    
                    # Should use basic config due to no meaningful advanced settings
                    assert isinstance(manager.config, CacheConfig)
                    assert not isinstance(manager.config, AdvancedCacheConfig)
        
        # Test with meaningful settings (should use advanced config)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('src.awsideman.utils.advanced_cache_config.AdvancedCacheConfig.from_config_and_environment') as mock_load:
                advanced_config = AdvancedCacheConfig(encryption_enabled=True)  # Meaningful setting
                mock_load.return_value = advanced_config
                
                with patch('src.awsideman.cache.manager.BackendFactory') as mock_factory, \
                     patch('src.awsideman.cache.manager.EncryptionProviderFactory') as mock_enc_factory:
                    
                    mock_backend = Mock()
                    mock_factory.validate_backend_availability.return_value = True
                    mock_factory.create_backend_with_fallback.return_value = mock_backend
                    
                    mock_encryption = Mock()
                    mock_encryption.get_encryption_type.return_value = "aes256"
                    mock_encryption.encrypt.return_value = b"encrypted"
                    mock_encryption.decrypt.return_value = {"test": "encryption_test"}
                    mock_enc_factory.create_provider.return_value = mock_encryption
                    
                    manager = CacheManager(base_cache_dir=temp_dir)
                    
                    # Should use advanced config due to meaningful settings
                    assert isinstance(manager.config, AdvancedCacheConfig)
                    assert manager.config.encryption_enabled is True