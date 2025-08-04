"""Tests for key manager implementation."""

import base64
import os
import tempfile
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.awsideman.encryption.key_manager import KeyManager, FallbackKeyManager
from src.awsideman.encryption.provider import EncryptionError


class TestKeyManager:
    """Test the KeyManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service_name = "test-service"
        self.username = "test-user"
        self.key_manager = KeyManager(self.service_name, self.username)
    
    @patch('keyring.get_password')
    @patch('keyring.set_password')
    def test_get_key_generates_new_key(self, mock_set, mock_get):
        """Test that get_key generates a new key when none exists."""
        # Mock keyring to return None (no existing key)
        mock_get.return_value = None
        
        key = self.key_manager.get_key()
        
        # Should be 32 bytes for AES-256
        assert len(key) == 32
        assert isinstance(key, bytes)
        
        # Should have called keyring to get and set
        mock_get.assert_called_once_with(self.service_name, self.username)
        mock_set.assert_called_once()
        
        # Verify the stored key is base64 encoded
        stored_key_str = mock_set.call_args[0][2]
        decoded_key = base64.b64decode(stored_key_str)
        assert decoded_key == key
    
    @patch('keyring.get_password')
    def test_get_key_retrieves_existing_key(self, mock_get):
        """Test that get_key retrieves an existing key."""
        # Create a test key and encode it
        test_key = os.urandom(32)
        encoded_key = base64.b64encode(test_key).decode('ascii')
        
        # Mock keyring to return the encoded key
        mock_get.return_value = encoded_key
        
        key = self.key_manager.get_key()
        
        # Should return the decoded key
        assert key == test_key
        assert len(key) == 32
        
        mock_get.assert_called_once_with(self.service_name, self.username)
    
    @patch('keyring.get_password')
    def test_get_key_caches_key(self, mock_get):
        """Test that get_key caches the key for performance."""
        # Create a test key and encode it
        test_key = os.urandom(32)
        encoded_key = base64.b64encode(test_key).decode('ascii')
        
        # Mock keyring to return the encoded key
        mock_get.return_value = encoded_key
        
        # Get key twice
        key1 = self.key_manager.get_key()
        key2 = self.key_manager.get_key()
        
        # Should be the same key
        assert key1 == key2 == test_key
        
        # Should only call keyring once due to caching
        assert mock_get.call_count == 1
    
    @patch('keyring.get_password')
    @patch('keyring.set_password')
    def test_rotate_key_with_existing_key(self, mock_set, mock_get):
        """Test key rotation when an existing key is present."""
        # Create an existing key
        old_key = os.urandom(32)
        encoded_old_key = base64.b64encode(old_key).decode('ascii')
        
        # Mock keyring to return the old key first
        mock_get.return_value = encoded_old_key
        
        old_key_returned, new_key = self.key_manager.rotate_key()
        
        # Should return the old key and generate a new one
        assert old_key_returned == old_key
        assert len(new_key) == 32
        assert new_key != old_key
        
        # Should have stored the new key
        mock_set.assert_called_once()
        stored_key_str = mock_set.call_args[0][2]
        decoded_new_key = base64.b64decode(stored_key_str)
        assert decoded_new_key == new_key
    
    @patch('keyring.get_password')
    @patch('keyring.set_password')
    def test_rotate_key_without_existing_key(self, mock_set, mock_get):
        """Test key rotation when no existing key is present."""
        # Mock keyring to return None (no existing key)
        mock_get.return_value = None
        
        old_key, new_key = self.key_manager.rotate_key()
        
        # Should return None for old key and generate a new one
        assert old_key is None
        assert len(new_key) == 32
        
        # Should have stored the new key
        mock_set.assert_called_once()
    
    @patch('keyring.delete_password')
    def test_delete_key_success(self, mock_delete):
        """Test successful key deletion."""
        result = self.key_manager.delete_key()
        
        assert result is True
        mock_delete.assert_called_once_with(self.service_name, self.username)
    
    @patch('keyring.delete_password')
    def test_delete_key_not_found(self, mock_delete):
        """Test key deletion when key doesn't exist."""
        from keyring.errors import KeyringError
        mock_delete.side_effect = KeyringError("not found")
        
        result = self.key_manager.delete_key()
        
        assert result is True  # Should return True even if key didn't exist
        mock_delete.assert_called_once_with(self.service_name, self.username)
    
    @patch('keyring.delete_password')
    def test_delete_key_error(self, mock_delete):
        """Test key deletion with keyring error."""
        from keyring.errors import KeyringError
        mock_delete.side_effect = KeyringError("access denied")
        
        result = self.key_manager.delete_key()
        
        assert result is False
        mock_delete.assert_called_once_with(self.service_name, self.username)
    
    @patch('keyring.get_password')
    def test_key_exists_true(self, mock_get):
        """Test key_exists when key is present."""
        mock_get.return_value = "some_key"
        
        assert self.key_manager.key_exists() is True
        mock_get.assert_called_once_with(self.service_name, self.username)
    
    @patch('keyring.get_password')
    def test_key_exists_false(self, mock_get):
        """Test key_exists when key is not present."""
        mock_get.return_value = None
        
        assert self.key_manager.key_exists() is False
        mock_get.assert_called_once_with(self.service_name, self.username)
    
    @patch('keyring.set_password')
    @patch('keyring.get_password')
    @patch('keyring.delete_password')
    def test_is_keyring_available_success(self, mock_delete, mock_get, mock_set):
        """Test keyring availability check when keyring works."""
        mock_get.return_value = "test"
        
        assert self.key_manager.is_keyring_available() is True
        
        # Should have performed test operations
        mock_set.assert_called_once()
        mock_get.assert_called_once()
        mock_delete.assert_called_once()
    
    @patch('keyring.set_password')
    def test_is_keyring_available_failure(self, mock_set):
        """Test keyring availability check when keyring fails."""
        mock_set.side_effect = Exception("Keyring not available")
        
        assert self.key_manager.is_keyring_available() is False
    
    @patch('keyring.get_password')
    def test_get_key_info_with_existing_key(self, mock_get):
        """Test get_key_info with existing valid key."""
        # Create a valid key
        test_key = os.urandom(32)
        encoded_key = base64.b64encode(test_key).decode('ascii')
        mock_get.return_value = encoded_key
        
        with patch.object(self.key_manager, 'is_keyring_available', return_value=True):
            info = self.key_manager.get_key_info()
        
        assert info['key_exists'] is True
        assert info['keyring_available'] is True
        assert info['key_length'] == 32
        assert info['key_valid'] is True
        assert info['service_name'] == self.service_name
        assert info['username'] == self.username
    
    @patch('keyring.get_password')
    def test_get_key_info_no_key(self, mock_get):
        """Test get_key_info when no key exists."""
        mock_get.return_value = None
        
        with patch.object(self.key_manager, 'is_keyring_available', return_value=True):
            info = self.key_manager.get_key_info()
        
        assert info['key_exists'] is False
        assert info['keyring_available'] is True
        assert 'key_length' not in info
        assert 'key_valid' not in info
    
    def test_decode_key_invalid_length(self):
        """Test key decoding with invalid length."""
        # Create a key that's not 32 bytes
        short_key = os.urandom(16)
        encoded_key = base64.b64encode(short_key).decode('ascii')
        
        with pytest.raises(EncryptionError) as exc_info:
            self.key_manager._decode_key(encoded_key)
        
        assert "Invalid key length" in str(exc_info.value)
        assert exc_info.value.encryption_type == "key_management"
    
    def test_decode_key_invalid_base64(self):
        """Test key decoding with invalid base64."""
        invalid_key = "not_valid_base64!"
        
        with pytest.raises(EncryptionError) as exc_info:
            self.key_manager._decode_key(invalid_key)
        
        assert "Failed to decode encryption key" in str(exc_info.value)
        assert exc_info.value.encryption_type == "key_management"
    
    @patch('keyring.get_password')
    def test_get_key_keyring_error(self, mock_get):
        """Test get_key with keyring error."""
        from keyring.errors import KeyringError
        mock_get.side_effect = KeyringError("access denied")
        
        with pytest.raises(EncryptionError) as exc_info:
            self.key_manager.get_key()
        
        assert "Failed to access keyring" in str(exc_info.value)
        assert exc_info.value.encryption_type == "key_management"
    
    @patch('keyring.set_password')
    def test_store_key_keyring_error(self, mock_set):
        """Test key storage with keyring error."""
        from keyring.errors import KeyringError
        mock_set.side_effect = KeyringError("access denied")
        
        test_key = os.urandom(32)
        
        with pytest.raises(EncryptionError) as exc_info:
            self.key_manager._store_key(test_key)
        
        assert "Failed to store key in keyring" in str(exc_info.value)
        assert exc_info.value.encryption_type == "key_management"
    
    def test_key_cache_expiration(self):
        """Test that key cache expires after TTL."""
        # Set a very short cache TTL for testing
        self.key_manager._cache_ttl = 0.1  # 100ms
        
        test_key = os.urandom(32)
        self.key_manager._cache_key(test_key)
        
        # Should be cached initially
        assert self.key_manager._is_key_cache_valid() is True
        
        # Wait for cache to expire
        import time
        time.sleep(0.2)
        
        # Should no longer be cached
        assert self.key_manager._is_key_cache_valid() is False


class TestFallbackKeyManager:
    """Test the FallbackKeyManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.service_name = "test-service"
        self.username = "test-user"
        self.key_manager = FallbackKeyManager(
            self.service_name, 
            self.username, 
            fallback_dir=self.temp_dir
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('keyring.get_password')
    @patch('keyring.set_password')
    def test_get_key_uses_keyring_when_available(self, mock_set, mock_get):
        """Test that fallback manager uses keyring when available."""
        # Mock keyring to be available and return a key
        test_key = os.urandom(32)
        encoded_key = base64.b64encode(test_key).decode('ascii')
        mock_get.return_value = encoded_key
        
        with patch.object(self.key_manager, 'is_keyring_available', return_value=True):
            key = self.key_manager.get_key()
        
        assert key == test_key
        mock_get.assert_called_once()
    
    def test_get_key_uses_file_when_keyring_unavailable(self):
        """Test that fallback manager uses file storage when keyring unavailable."""
        with patch.object(self.key_manager, 'is_keyring_available', return_value=False):
            key = self.key_manager.get_key()
        
        # Should generate a new key
        assert len(key) == 32
        assert isinstance(key, bytes)
        
        # Should have created the fallback file
        assert os.path.exists(self.key_manager.fallback_file)
        
        # File should have restricted permissions
        file_stat = os.stat(self.key_manager.fallback_file)
        file_mode = file_stat.st_mode & 0o777
        assert file_mode == 0o600  # Owner read/write only
    
    def test_get_key_reads_existing_file(self):
        """Test that fallback manager reads existing key file."""
        # Create an existing key file
        test_key = os.urandom(32)
        encoded_key = base64.b64encode(test_key).decode('ascii')
        
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(self.key_manager.fallback_file, 'w') as f:
            f.write(encoded_key)
        
        with patch.object(self.key_manager, 'is_keyring_available', return_value=False):
            key = self.key_manager.get_key()
        
        assert key == test_key
    
    def test_get_key_file_error_handling(self):
        """Test error handling when file operations fail."""
        # Make the fallback directory read-only to cause write errors
        os.makedirs(self.temp_dir, exist_ok=True)
        os.chmod(self.temp_dir, 0o444)  # Read-only
        
        with patch.object(self.key_manager, 'is_keyring_available', return_value=False):
            with pytest.raises(EncryptionError) as exc_info:
                self.key_manager.get_key()
        
        assert "Failed to get key from fallback file" in str(exc_info.value)
        assert exc_info.value.encryption_type == "key_management"
        
        # Restore permissions for cleanup
        os.chmod(self.temp_dir, 0o755)
    
    def test_store_key_to_file_creates_directory(self):
        """Test that storing key creates directory if it doesn't exist."""
        # Remove the temp directory
        import shutil
        shutil.rmtree(self.temp_dir)
        
        test_key = os.urandom(32)
        self.key_manager._store_key_to_file(test_key)
        
        # Directory should be created
        assert os.path.exists(self.temp_dir)
        assert os.path.exists(self.key_manager.fallback_file)
        
        # Directory should have restricted permissions
        dir_stat = os.stat(self.temp_dir)
        dir_mode = dir_stat.st_mode & 0o777
        assert dir_mode == 0o700  # Owner read/write/execute only
    
    def test_store_key_to_file_permission_error(self):
        """Test error handling when file storage fails due to permissions."""
        # Create a directory we can't write to
        readonly_dir = os.path.join(self.temp_dir, "readonly")
        os.makedirs(readonly_dir, mode=0o444)  # Read-only
        
        # Update fallback file path to the read-only directory
        self.key_manager.fallback_file = os.path.join(readonly_dir, ".encryption_key")
        
        test_key = os.urandom(32)
        
        with pytest.raises(EncryptionError) as exc_info:
            self.key_manager._store_key_to_file(test_key)
        
        assert "Failed to store key to fallback file" in str(exc_info.value)
        assert exc_info.value.encryption_type == "key_management"
        
        # Restore permissions for cleanup
        os.chmod(readonly_dir, 0o755)


class TestKeyManagerIntegration:
    """Integration tests for key manager."""
    
    def test_key_manager_with_real_operations(self):
        """Test key manager with real cryptographic operations."""
        # Use a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create fallback key manager to avoid keyring dependencies in tests
            key_manager = FallbackKeyManager(fallback_dir=temp_dir)
            
            # Mock keyring as unavailable to force file storage
            with patch.object(key_manager, 'is_keyring_available', return_value=False):
                # Get key (should generate new one)
                key1 = key_manager.get_key()
                assert len(key1) == 32
                
                # Get key again (should return same key)
                key2 = key_manager.get_key()
                assert key1 == key2
                
                # Rotate key
                old_key, new_key = key_manager.rotate_key()
                assert old_key == key1
                assert new_key != key1
                assert len(new_key) == 32
                
                # Get key should now return new key
                key3 = key_manager.get_key()
                assert key3 == new_key
                
                # Key info should be accurate
                info = key_manager.get_key_info()
                assert info['key_exists'] is True
                assert info['key_valid'] is True
                assert info['key_length'] == 32
    
    def test_error_handling_consistency(self):
        """Test that all key manager errors are properly wrapped."""
        key_manager = KeyManager()
        
        # Test with invalid encoded key
        with pytest.raises(EncryptionError) as exc_info:
            key_manager._decode_key("invalid_base64!")
        
        error = exc_info.value
        assert error.encryption_type == "key_management"
        assert "Failed to decode encryption key" in str(error)
        assert error.original_error is not None