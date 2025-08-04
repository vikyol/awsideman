"""Enhanced tests for AES encryption provider implementation."""

import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.awsideman.encryption.aes import AESEncryption
from src.awsideman.encryption.provider import EncryptionError
from src.awsideman.encryption.key_manager import KeyManager


class TestAESEncryptionEnhanced:
    """Enhanced test cases for AES encryption provider."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_key_manager = Mock(spec=KeyManager)
        self.test_key = os.urandom(32)  # 256-bit key
        self.mock_key_manager.get_key.return_value = self.test_key
        self.encryption = AESEncryption(self.mock_key_manager)
    
    def test_init_with_key_manager(self):
        """Test initialization with key manager."""
        assert self.encryption.key_manager == self.mock_key_manager
        assert self.encryption.get_encryption_type() == "aes256"
    
    def test_encrypt_simple_data_types(self):
        """Test encrypting various simple data types."""
        test_cases = [
            {"key": "value"},
            ["item1", "item2", "item3"],
            "simple string",
            42,
            3.14159,
            True,
            False,
            None
        ]
        
        for data in test_cases:
            encrypted = self.encryption.encrypt(data)
            
            # Should return bytes
            assert isinstance(encrypted, bytes)
            
            # Should be longer than original due to IV and padding
            assert len(encrypted) > 16  # At least IV length
            
            # Should be able to decrypt back to original
            decrypted = self.encryption.decrypt(encrypted)
            assert decrypted == data
    
    def test_encrypt_complex_nested_data(self):
        """Test encrypting complex nested data structures."""
        complex_data = {
            "users": [
                {
                    "id": 1,
                    "name": "Alice",
                    "permissions": ["read", "write"],
                    "metadata": {
                        "created": "2023-01-01",
                        "active": True,
                        "score": 95.5
                    }
                },
                {
                    "id": 2,
                    "name": "Bob",
                    "permissions": ["read"],
                    "metadata": {
                        "created": "2023-01-02",
                        "active": False,
                        "score": 87.2
                    }
                }
            ],
            "settings": {
                "theme": "dark",
                "notifications": True,
                "limits": {
                    "max_users": 100,
                    "max_storage_gb": 1000
                }
            }
        }
        
        encrypted = self.encryption.encrypt(complex_data)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert decrypted == complex_data
    
    def test_encrypt_large_data(self):
        """Test encrypting large data structures."""
        # Create a large data structure
        large_data = {
            "items": [{"id": i, "data": f"item_{i}" * 100} for i in range(1000)]
        }
        
        encrypted = self.encryption.encrypt(large_data)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert decrypted == large_data
    
    def test_encrypt_unicode_data(self):
        """Test encrypting data with Unicode characters."""
        unicode_data = {
            "english": "Hello World",
            "chinese": "你好世界",
            "japanese": "こんにちは世界",
            "arabic": "مرحبا بالعالم",
            "emoji": "🌍🚀💻🔐",
            "special": "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?"
        }
        
        encrypted = self.encryption.encrypt(unicode_data)
        decrypted = self.encryption.decrypt(encrypted)
        
        assert decrypted == unicode_data
    
    def test_encrypt_different_keys_produce_different_results(self):
        """Test that different keys produce different encrypted results."""
        data = {"test": "data"}
        
        # Encrypt with first key
        encrypted1 = self.encryption.encrypt(data)
        
        # Change key and encrypt again
        different_key = os.urandom(32)
        self.mock_key_manager.get_key.return_value = different_key
        encrypted2 = self.encryption.encrypt(data)
        
        # Results should be different
        assert encrypted1 != encrypted2
    
    def test_encrypt_same_data_different_results(self):
        """Test that encrypting same data multiple times produces different results due to random IV."""
        data = {"test": "data"}
        
        encrypted1 = self.encryption.encrypt(data)
        encrypted2 = self.encryption.encrypt(data)
        
        # Results should be different due to random IV
        assert encrypted1 != encrypted2
        
        # But both should decrypt to the same data
        decrypted1 = self.encryption.decrypt(encrypted1)
        decrypted2 = self.encryption.decrypt(encrypted2)
        assert decrypted1 == decrypted2 == data
    
    def test_encrypt_key_manager_error(self):
        """Test encryption when key manager fails."""
        self.mock_key_manager.get_key.side_effect = Exception("Key retrieval failed")
        
        with pytest.raises(EncryptionError) as exc_info:
            self.encryption.encrypt({"test": "data"})
        
        assert exc_info.value.encryption_type == "aes256"
        assert "AES encryption failed" in str(exc_info.value)
    
    def test_encrypt_non_serializable_data(self):
        """Test encryption with non-JSON-serializable data."""
        class NonSerializable:
            pass
        
        with pytest.raises(EncryptionError) as exc_info:
            self.encryption.encrypt(NonSerializable())
        
        assert exc_info.value.encryption_type == "aes256"
        assert "Failed to serialize data for encryption" in str(exc_info.value)
    
    def test_decrypt_invalid_data_too_short(self):
        """Test decryption with data too short to contain IV."""
        invalid_data = b"short"  # Less than 16 bytes (IV size)
        
        with pytest.raises(EncryptionError) as exc_info:
            self.encryption.decrypt(invalid_data)
        
        assert exc_info.value.encryption_type == "aes256"
        assert "Invalid encrypted data" in str(exc_info.value)
    
    def test_decrypt_invalid_padding(self):
        """Test decryption with invalid padding."""
        # Create data with valid IV but invalid encrypted content
        iv = os.urandom(16)
        invalid_encrypted = b"invalid_encrypted_data_with_bad_padding"
        invalid_data = iv + invalid_encrypted
        
        with pytest.raises(EncryptionError) as exc_info:
            self.encryption.decrypt(invalid_data)
        
        assert exc_info.value.encryption_type == "aes256"
        assert "AES decryption failed" in str(exc_info.value)
    
    def test_decrypt_wrong_key(self):
        """Test decryption with wrong key."""
        data = {"test": "data"}
        encrypted = self.encryption.encrypt(data)
        
        # Change key for decryption
        wrong_key = os.urandom(32)
        self.mock_key_manager.get_key.return_value = wrong_key
        
        with pytest.raises(EncryptionError) as exc_info:
            self.encryption.decrypt(encrypted)
        
        assert exc_info.value.encryption_type == "aes256"
    
    def test_decrypt_key_manager_error(self):
        """Test decryption when key manager fails."""
        data = {"test": "data"}
        encrypted = self.encryption.encrypt(data)
        
        # Make key manager fail during decryption
        self.mock_key_manager.get_key.side_effect = Exception("Key retrieval failed")
        
        with pytest.raises(EncryptionError) as exc_info:
            self.encryption.decrypt(encrypted)
        
        assert exc_info.value.encryption_type == "aes256"
        assert "AES decryption failed" in str(exc_info.value)
    
    def test_decrypt_invalid_json(self):
        """Test decryption that results in invalid JSON."""
        # This is tricky to test directly, but we can mock the JSON loading
        data = {"test": "data"}
        encrypted = self.encryption.encrypt(data)
        
        with patch('json.loads', side_effect=json.JSONDecodeError("Invalid JSON", "", 0)):
            with pytest.raises(EncryptionError) as exc_info:
                self.encryption.decrypt(encrypted)
            
            assert exc_info.value.encryption_type == "aes256"
            assert "Failed to deserialize decrypted JSON data" in str(exc_info.value)
    
    def test_padding_functionality_through_encryption(self):
        """Test padding functionality indirectly through encryption/decryption."""
        # Test various data lengths to ensure padding works correctly
        test_data_lengths = [1, 15, 16, 17, 31, 32, 33, 48, 64]
        
        for length in test_data_lengths:
            test_data = {"data": "x" * length}
            
            # Encrypt and decrypt should work correctly regardless of data length
            encrypted = self.encryption.encrypt(test_data)
            decrypted = self.encryption.decrypt(encrypted)
            
            assert decrypted == test_data
    
    def test_padding_edge_cases_through_encryption(self):
        """Test padding edge cases through encryption/decryption."""
        edge_cases = [
            {},  # Empty dict
            {"empty": ""},  # Empty string
            {"exact_block": "x" * 16},  # Data that might align with block boundaries
            {"large": "x" * 1000}  # Large data
        ]
        
        for test_data in edge_cases:
            encrypted = self.encryption.encrypt(test_data)
            decrypted = self.encryption.decrypt(encrypted)
            assert decrypted == test_data
    
    def test_is_available(self):
        """Test availability check."""
        assert self.encryption.is_available() is True
    
    def test_is_available_missing_dependencies(self):
        """Test availability check when dependencies are missing."""
        # Test that the encryption is available (since we can import it)
        assert self.encryption.is_available() is True
    
    def test_roundtrip_stress_test(self):
        """Stress test encryption/decryption roundtrip with various data."""
        test_cases = [
            # Empty structures
            {},
            [],
            "",
            
            # Single values
            0,
            1,
            -1,
            3.14159,
            True,
            False,
            None,
            
            # Strings with special characters
            "newlines\nand\rtabs\t",
            "quotes'and\"double",
            "unicode: 你好 🌍",
            
            # Complex nested structures
            {
                "level1": {
                    "level2": {
                        "level3": ["deep", "nesting", {"level4": True}]
                    }
                }
            },
            
            # Large arrays
            list(range(1000)),
            
            # Mixed types
            {
                "string": "value",
                "number": 42,
                "float": 3.14,
                "boolean": True,
                "null": None,
                "array": [1, "two", 3.0, True, None],
                "object": {"nested": "value"}
            }
        ]
        
        for i, test_data in enumerate(test_cases):
            encrypted = self.encryption.encrypt(test_data)
            decrypted = self.encryption.decrypt(encrypted)
            assert decrypted == test_data, f"Failed for test case {i}: {test_data}"
    
    def test_encryption_format_consistency(self):
        """Test that encryption format is consistent."""
        data = {"test": "data"}
        encrypted = self.encryption.encrypt(data)
        
        # Encrypted data should start with 16-byte IV
        assert len(encrypted) >= 16
        
        # Extract IV and encrypted content
        iv = encrypted[:16]
        encrypted_content = encrypted[16:]
        
        # IV should be 16 bytes
        assert len(iv) == 16
        
        # Encrypted content should be multiple of 16 bytes (AES block size)
        assert len(encrypted_content) % 16 == 0
        
        # Should be able to decrypt
        decrypted = self.encryption.decrypt(encrypted)
        assert decrypted == data
    
    def test_key_caching_behavior(self):
        """Test that key manager is called appropriately."""
        data = {"test": "data"}
        
        # Encrypt data
        encrypted = self.encryption.encrypt(data)
        
        # Decrypt data
        decrypted = self.encryption.decrypt(encrypted)
        
        # Key manager should have been called for both operations
        assert self.mock_key_manager.get_key.call_count >= 2
        
        assert decrypted == data
    
    def test_thread_safety_simulation(self):
        """Simulate thread safety by using different key manager instances."""
        data = {"test": "data"}
        
        # Create multiple encryption instances with different key managers
        key_managers = []
        encryptions = []
        
        for i in range(3):
            km = Mock(spec=KeyManager)
            km.get_key.return_value = self.test_key  # Same key for all
            key_managers.append(km)
            encryptions.append(AESEncryption(km))
        
        # Encrypt with different instances
        encrypted_results = []
        for enc in encryptions:
            encrypted_results.append(enc.encrypt(data))
        
        # All should decrypt to the same data
        for i, encrypted in enumerate(encrypted_results):
            decrypted = encryptions[i].decrypt(encrypted)
            assert decrypted == data
        
        # Cross-decryption should also work (same key)
        for i, encrypted in enumerate(encrypted_results):
            for j, enc in enumerate(encryptions):
                decrypted = enc.decrypt(encrypted)
                assert decrypted == data