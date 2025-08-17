"""
Unit tests for encryption providers.

Tests various encryption implementations including Fernet, AES,
and no-op encryption providers with proper key management.
"""

import pytest

from src.awsideman.backup_restore.encryption import (
    AESEncryptionProvider,
    EncryptionProviderFactory,
    FernetEncryptionProvider,
    ManagedAESEncryptionProvider,
    NoOpEncryptionProvider,
    TransitEncryptionProvider,
)


class TestFernetEncryptionProvider:
    """Test cases for FernetEncryptionProvider class."""

    @pytest.fixture
    def fernet_provider(self):
        """Create a Fernet encryption provider."""
        return FernetEncryptionProvider()

    @pytest.fixture
    def fernet_provider_with_key(self):
        """Create a Fernet encryption provider with a specific key."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        return FernetEncryptionProvider(key.decode())

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, fernet_provider):
        """Test encryption and decryption roundtrip."""
        original_data = b"This is test data for encryption"

        # Encrypt data
        encrypted_data, metadata = await fernet_provider.encrypt(original_data)

        # Verify encryption metadata
        assert metadata["algorithm"] == "Fernet"
        assert metadata["encrypted"] is True
        assert metadata["version"] == "1.0"
        assert encrypted_data != original_data

        # Decrypt data
        decrypted_data = await fernet_provider.decrypt(encrypted_data, metadata)

        # Verify roundtrip
        assert decrypted_data == original_data

    @pytest.mark.asyncio
    async def test_encrypt_with_key_id(self, fernet_provider):
        """Test encryption with custom key ID."""
        data = b"test data"
        key_id = "custom-key-123"

        encrypted_data, metadata = await fernet_provider.encrypt(data, key_id)

        assert metadata["key_id"] == key_id

    @pytest.mark.asyncio
    async def test_decrypt_unencrypted_data(self, fernet_provider):
        """Test decrypting data marked as unencrypted."""
        data = b"unencrypted data"
        metadata = {"encrypted": False}

        result = await fernet_provider.decrypt(data, metadata)

        assert result == data

    @pytest.mark.asyncio
    async def test_decrypt_wrong_algorithm(self, fernet_provider):
        """Test decrypting with wrong algorithm in metadata."""
        data = b"encrypted data"
        metadata = {"algorithm": "AES", "encrypted": True}

        with pytest.raises(ValueError, match="Unsupported encryption algorithm"):
            await fernet_provider.decrypt(data, metadata)

    @pytest.mark.asyncio
    async def test_generate_key(self, fernet_provider):
        """Test key generation."""
        key_id = await fernet_provider.generate_key()

        assert isinstance(key_id, str)
        assert len(key_id) == 16  # SHA256 hash truncated to 16 chars

    @pytest.mark.asyncio
    async def test_rotate_key(self, fernet_provider):
        """Test key rotation."""
        old_key_id = "old-key-123"
        old_key = fernet_provider.master_key

        new_key_id = await fernet_provider.rotate_key(old_key_id)

        assert new_key_id != old_key_id
        assert fernet_provider.master_key != old_key
        assert isinstance(new_key_id, str)

    def test_get_master_key(self, fernet_provider):
        """Test getting master key."""
        master_key = fernet_provider.get_master_key()

        assert isinstance(master_key, bytes)
        assert len(master_key) == 44  # Fernet key length in base64

    def test_initialization_with_custom_key(self, fernet_provider_with_key):
        """Test initialization with custom key."""
        assert fernet_provider_with_key.master_key is not None
        assert fernet_provider_with_key.fernet is not None


class TestAESEncryptionProvider:
    """Test cases for AESEncryptionProvider class."""

    @pytest.fixture
    def aes_provider(self):
        """Create an AES encryption provider."""
        return AESEncryptionProvider()

    @pytest.fixture
    def aes_provider_with_password(self):
        """Create an AES encryption provider with specific password."""
        return AESEncryptionProvider(password="test-password-123")

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, aes_provider):
        """Test AES encryption and decryption roundtrip."""
        original_data = b"This is test data for AES encryption"

        # Encrypt data
        encrypted_data, metadata = await aes_provider.encrypt(original_data)

        # Verify encryption metadata
        assert metadata["algorithm"] == "AES-256-GCM"
        assert metadata["encrypted"] is True
        assert metadata["version"] == "1.0"
        assert "iv" in metadata
        assert "salt" in metadata
        assert encrypted_data != original_data

        # Decrypt data
        decrypted_data = await aes_provider.decrypt(encrypted_data, metadata)

        # Verify roundtrip
        assert decrypted_data == original_data

    @pytest.mark.asyncio
    async def test_encrypt_with_key_id(self, aes_provider):
        """Test AES encryption with custom key ID."""
        data = b"test data"
        key_id = "custom-aes-key-456"

        encrypted_data, metadata = await aes_provider.encrypt(data, key_id)

        assert metadata["key_id"] == key_id

    @pytest.mark.asyncio
    async def test_decrypt_unencrypted_data(self, aes_provider):
        """Test decrypting data marked as unencrypted."""
        data = b"unencrypted data"
        metadata = {"encrypted": False}

        result = await aes_provider.decrypt(data, metadata)

        assert result == data

    @pytest.mark.asyncio
    async def test_decrypt_wrong_algorithm(self, aes_provider):
        """Test decrypting with wrong algorithm in metadata."""
        data = b"encrypted data"
        metadata = {"algorithm": "Fernet", "encrypted": True}

        with pytest.raises(ValueError, match="Unsupported encryption algorithm"):
            await aes_provider.decrypt(data, metadata)

    @pytest.mark.asyncio
    async def test_generate_key(self, aes_provider):
        """Test AES key generation."""
        key_id = await aes_provider.generate_key()

        assert isinstance(key_id, str)
        assert len(key_id) == 16  # SHA256 hash truncated to 16 chars

    @pytest.mark.asyncio
    async def test_rotate_key(self, aes_provider):
        """Test AES key rotation."""
        old_key_id = "old-aes-key-123"
        old_key = aes_provider.key
        old_salt = aes_provider.salt

        new_key_id = await aes_provider.rotate_key(old_key_id)

        assert new_key_id != old_key_id
        assert aes_provider.key != old_key
        assert aes_provider.salt != old_salt
        assert isinstance(new_key_id, str)

    def test_get_key_info(self, aes_provider):
        """Test getting AES key information."""
        key_info = aes_provider.get_key_info()

        assert "salt" in key_info
        assert "password" in key_info
        assert isinstance(key_info["salt"], str)
        assert isinstance(key_info["password"], str)

    def test_initialization_with_custom_password(self, aes_provider_with_password):
        """Test initialization with custom password."""
        assert aes_provider_with_password.password == "test-password-123"
        assert aes_provider_with_password.key is not None
        assert aes_provider_with_password.salt is not None

    @pytest.mark.asyncio
    async def test_different_iv_each_encryption(self, aes_provider):
        """Test that each encryption uses a different IV."""
        data = b"test data"

        encrypted1, metadata1 = await aes_provider.encrypt(data)
        encrypted2, metadata2 = await aes_provider.encrypt(data)

        # Different IVs should result in different encrypted data
        assert encrypted1 != encrypted2
        assert metadata1["iv"] != metadata2["iv"]

        # But both should decrypt to the same original data
        decrypted1 = await aes_provider.decrypt(encrypted1, metadata1)
        decrypted2 = await aes_provider.decrypt(encrypted2, metadata2)

        assert decrypted1 == data
        assert decrypted2 == data


class TestNoOpEncryptionProvider:
    """Test cases for NoOpEncryptionProvider class."""

    @pytest.fixture
    def noop_provider(self):
        """Create a no-op encryption provider."""
        return NoOpEncryptionProvider()

    @pytest.mark.asyncio
    async def test_encrypt_passthrough(self, noop_provider):
        """Test that encryption passes data through unchanged."""
        original_data = b"This data should not be encrypted"

        encrypted_data, metadata = await noop_provider.encrypt(original_data)

        assert encrypted_data == original_data
        assert metadata["algorithm"] == "none"
        assert metadata["encrypted"] is False
        assert metadata["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_decrypt_passthrough(self, noop_provider):
        """Test that decryption passes data through unchanged."""
        data = b"This data should not be decrypted"
        metadata = {"algorithm": "none", "encrypted": False}

        decrypted_data = await noop_provider.decrypt(data, metadata)

        assert decrypted_data == data

    @pytest.mark.asyncio
    async def test_encrypt_with_key_id(self, noop_provider):
        """Test encryption with custom key ID."""
        data = b"test data"
        key_id = "dummy-key-789"

        encrypted_data, metadata = await noop_provider.encrypt(data, key_id)

        assert metadata["key_id"] == key_id
        assert encrypted_data == data

    @pytest.mark.asyncio
    async def test_generate_key(self, noop_provider):
        """Test dummy key generation."""
        key_id = await noop_provider.generate_key()

        assert isinstance(key_id, str)
        assert key_id.startswith("noop-")
        assert len(key_id) >= 13  # 'noop-' + hex chars (length may vary)

    @pytest.mark.asyncio
    async def test_rotate_key(self, noop_provider):
        """Test dummy key rotation."""
        old_key_id = "old-noop-key"

        new_key_id = await noop_provider.rotate_key(old_key_id)

        assert new_key_id != old_key_id
        assert new_key_id.startswith("noop-")
        assert isinstance(new_key_id, str)


class TestEncryptionProviderFactory:
    """Test cases for EncryptionProviderFactory class."""

    def test_create_fernet_provider(self):
        """Test creating Fernet provider via factory."""
        provider = EncryptionProviderFactory.create_fernet_provider()

        assert isinstance(provider, FernetEncryptionProvider)

    def test_create_fernet_provider_with_key(self):
        """Test creating Fernet provider with custom key."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()

        provider = EncryptionProviderFactory.create_fernet_provider(master_key=key)

        assert isinstance(provider, FernetEncryptionProvider)
        assert provider.master_key == key.encode()

    def test_create_aes_provider(self):
        """Test creating AES provider via factory."""
        provider = EncryptionProviderFactory.create_aes_provider()

        assert isinstance(provider, AESEncryptionProvider)

    def test_create_aes_provider_with_password(self):
        """Test creating AES provider with custom password."""
        password = "custom-password-123"

        provider = EncryptionProviderFactory.create_aes_provider(password=password)

        assert isinstance(provider, AESEncryptionProvider)
        assert provider.password == password

    def test_create_noop_provider(self):
        """Test creating no-op provider via factory."""
        provider = EncryptionProviderFactory.create_noop_provider()

        assert isinstance(provider, NoOpEncryptionProvider)

    def test_create_provider_fernet(self):
        """Test creating provider via factory method - Fernet."""
        provider = EncryptionProviderFactory.create_provider("fernet")

        assert isinstance(provider, FernetEncryptionProvider)

    def test_create_provider_aes(self):
        """Test creating provider via factory method - AES."""
        provider = EncryptionProviderFactory.create_provider("aes")

        assert isinstance(provider, AESEncryptionProvider)

    def test_create_provider_noop(self):
        """Test creating provider via factory method - no-op."""
        provider = EncryptionProviderFactory.create_provider("noop")

        assert isinstance(provider, NoOpEncryptionProvider)

    def test_create_provider_none(self):
        """Test creating provider via factory method - none."""
        provider = EncryptionProviderFactory.create_provider("none")

        assert isinstance(provider, NoOpEncryptionProvider)

    def test_create_provider_unsupported(self):
        """Test creating unsupported provider type."""
        with pytest.raises(ValueError, match="Unsupported encryption provider type"):
            EncryptionProviderFactory.create_provider("unsupported")

    def test_create_provider_case_insensitive(self):
        """Test that provider creation is case insensitive."""
        provider1 = EncryptionProviderFactory.create_provider("FERNET")
        provider2 = EncryptionProviderFactory.create_provider("Aes")
        provider3 = EncryptionProviderFactory.create_provider("NoOp")

        assert isinstance(provider1, FernetEncryptionProvider)
        assert isinstance(provider2, AESEncryptionProvider)
        assert isinstance(provider3, NoOpEncryptionProvider)


class TestEncryptionIntegration:
    """Integration tests for encryption providers."""

    @pytest.mark.asyncio
    async def test_cross_provider_compatibility(self):
        """Test that different providers handle their own encrypted data correctly."""
        original_data = b"Cross-provider test data"

        # Test with Fernet
        fernet_provider = FernetEncryptionProvider()
        fernet_encrypted, fernet_metadata = await fernet_provider.encrypt(original_data)
        fernet_decrypted = await fernet_provider.decrypt(fernet_encrypted, fernet_metadata)
        assert fernet_decrypted == original_data

        # Test with AES
        aes_provider = AESEncryptionProvider()
        aes_encrypted, aes_metadata = await aes_provider.encrypt(original_data)
        aes_decrypted = await aes_provider.decrypt(aes_encrypted, aes_metadata)
        assert aes_decrypted == original_data

        # Test with NoOp
        noop_provider = NoOpEncryptionProvider()
        noop_encrypted, noop_metadata = await noop_provider.encrypt(original_data)
        noop_decrypted = await noop_provider.decrypt(noop_encrypted, noop_metadata)
        assert noop_decrypted == original_data

        # Verify that encrypted data is different (except for NoOp)
        assert fernet_encrypted != original_data
        assert aes_encrypted != original_data
        assert noop_encrypted == original_data

        # Verify that encrypted data from different providers is different
        assert fernet_encrypted != aes_encrypted

    @pytest.mark.asyncio
    async def test_large_data_encryption(self):
        """Test encryption with large data."""
        # Create 1MB of test data
        large_data = b"A" * (1024 * 1024)

        providers = [FernetEncryptionProvider(), AESEncryptionProvider(), NoOpEncryptionProvider()]

        for provider in providers:
            encrypted_data, metadata = await provider.encrypt(large_data)
            decrypted_data = await provider.decrypt(encrypted_data, metadata)

            assert decrypted_data == large_data
            assert len(decrypted_data) == len(large_data)

    @pytest.mark.asyncio
    async def test_empty_data_encryption(self):
        """Test encryption with empty data."""
        empty_data = b""

        providers = [FernetEncryptionProvider(), AESEncryptionProvider(), NoOpEncryptionProvider()]

        for provider in providers:
            encrypted_data, metadata = await provider.encrypt(empty_data)
            decrypted_data = await provider.decrypt(encrypted_data, metadata)

            assert decrypted_data == empty_data

    @pytest.mark.asyncio
    async def test_unicode_data_encryption(self):
        """Test encryption with Unicode data."""
        unicode_text = "Hello, 世界! 🌍 Encryption test with émojis and spëcial chars"
        unicode_data = unicode_text.encode("utf-8")

        providers = [FernetEncryptionProvider(), AESEncryptionProvider(), NoOpEncryptionProvider()]

        for provider in providers:
            encrypted_data, metadata = await provider.encrypt(unicode_data)
            decrypted_data = await provider.decrypt(encrypted_data, metadata)

            assert decrypted_data == unicode_data
            assert decrypted_data.decode("utf-8") == unicode_text


class TestManagedAESEncryptionProvider:
    """Test cases for ManagedAESEncryptionProvider class."""

    @pytest.fixture
    def managed_aes_provider(self):
        """Create a managed AES encryption provider."""
        return ManagedAESEncryptionProvider(service_name="test-backup-service")

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, managed_aes_provider):
        """Test managed AES encryption and decryption roundtrip."""
        original_data = b"This is test data for managed AES encryption"

        # Encrypt data
        encrypted_data, metadata = await managed_aes_provider.encrypt(original_data)

        # Verify encryption metadata
        assert metadata["algorithm"] == "AES-256-GCM-Managed"
        assert metadata["encrypted"] is True
        assert metadata["version"] == "2.0"
        assert metadata["encryption_at_rest"] is True
        assert metadata["encryption_in_transit"] is True
        assert "key_fingerprint" in metadata
        assert "iv" in metadata
        assert metadata["service_name"] == "test-backup-service"
        assert encrypted_data != original_data

        # Decrypt data
        decrypted_data = await managed_aes_provider.decrypt(encrypted_data, metadata)

        # Verify roundtrip
        assert decrypted_data == original_data

    @pytest.mark.asyncio
    async def test_encrypt_with_key_id(self, managed_aes_provider):
        """Test managed AES encryption with custom key ID."""
        data = b"test data"
        key_id = "custom-managed-key-123"

        encrypted_data, metadata = await managed_aes_provider.encrypt(data, key_id)

        assert metadata["key_id"] == key_id

    @pytest.mark.asyncio
    async def test_generate_key(self, managed_aes_provider):
        """Test managed key generation."""
        key_id = await managed_aes_provider.generate_key()

        assert isinstance(key_id, str)
        assert len(key_id) == 16  # SHA256 hash truncated to 16 chars

    @pytest.mark.asyncio
    async def test_rotate_key(self, managed_aes_provider):
        """Test managed key rotation."""
        old_key_id = "old-managed-key-123"

        new_key_id = await managed_aes_provider.rotate_key(old_key_id)

        assert new_key_id != old_key_id
        assert isinstance(new_key_id, str)
        assert len(new_key_id) == 16

    def test_get_key_info(self, managed_aes_provider):
        """Test getting managed key information."""
        key_info = managed_aes_provider.get_key_info()

        assert "provider_type" in key_info
        assert key_info["provider_type"] == "managed_aes"
        assert key_info["service_name"] == "test-backup-service"

    @pytest.mark.asyncio
    async def test_verify_key_access(self, managed_aes_provider):
        """Test key access verification."""
        access_ok = await managed_aes_provider.verify_key_access()

        # Should be True if key manager is working
        assert isinstance(access_ok, bool)

    @pytest.mark.asyncio
    async def test_different_iv_each_encryption(self, managed_aes_provider):
        """Test that each encryption uses a different IV."""
        data = b"test data"

        encrypted1, metadata1 = await managed_aes_provider.encrypt(data)
        encrypted2, metadata2 = await managed_aes_provider.encrypt(data)

        # Different IVs should result in different encrypted data
        assert encrypted1 != encrypted2
        assert metadata1["iv"] != metadata2["iv"]

        # But both should decrypt to the same original data
        decrypted1 = await managed_aes_provider.decrypt(encrypted1, metadata1)
        decrypted2 = await managed_aes_provider.decrypt(encrypted2, metadata2)

        assert decrypted1 == data
        assert decrypted2 == data


class TestTransitEncryptionProvider:
    """Test cases for TransitEncryptionProvider class."""

    @pytest.fixture
    def base_provider(self):
        """Create a base encryption provider."""
        return AESEncryptionProvider()

    @pytest.fixture
    def transit_provider(self, base_provider):
        """Create a transit encryption provider."""
        return TransitEncryptionProvider(base_provider)

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, transit_provider):
        """Test transit encryption and decryption roundtrip."""
        original_data = b"This is test data for transit encryption"

        # Encrypt data
        encrypted_data, metadata = await transit_provider.encrypt(original_data)

        # Verify transit-specific metadata
        assert metadata["transit_encryption"] is True
        assert "timestamp" in metadata
        assert "nonce" in metadata
        assert "integrity_hash" in metadata
        assert encrypted_data != original_data

        # Decrypt data
        decrypted_data = await transit_provider.decrypt(encrypted_data, metadata)

        # Verify roundtrip
        assert decrypted_data == original_data

    @pytest.mark.asyncio
    async def test_integrity_verification(self, transit_provider):
        """Test integrity verification during decryption."""
        original_data = b"test data for integrity check"

        # Encrypt data
        encrypted_data, metadata = await transit_provider.encrypt(original_data)

        # Tamper with integrity hash
        metadata["integrity_hash"] = "tampered_hash"

        # Decryption should fail due to integrity check
        with pytest.raises(Exception):  # Should raise EncryptionError
            await transit_provider.decrypt(encrypted_data, metadata)

    @pytest.mark.asyncio
    async def test_timestamp_verification(self, transit_provider):
        """Test timestamp verification during decryption."""
        original_data = b"test data for timestamp check"

        # Encrypt data
        encrypted_data, metadata = await transit_provider.encrypt(original_data)

        # Modify timestamp in metadata
        metadata["timestamp"] = metadata["timestamp"] + 1000

        # Decryption should still work but log a warning
        decrypted_data = await transit_provider.decrypt(encrypted_data, metadata)
        assert decrypted_data == original_data

    @pytest.mark.asyncio
    async def test_generate_and_rotate_key(self, transit_provider):
        """Test key generation and rotation delegation."""
        # Test key generation
        key_id = await transit_provider.generate_key()
        assert isinstance(key_id, str)

        # Test key rotation
        new_key_id = await transit_provider.rotate_key(key_id)
        assert isinstance(new_key_id, str)
        assert new_key_id != key_id


class TestEncryptionProviderFactoryEnhanced:
    """Enhanced test cases for EncryptionProviderFactory class."""

    def test_create_managed_aes_provider(self):
        """Test creating managed AES provider via factory."""
        provider = EncryptionProviderFactory.create_managed_aes_provider()

        assert isinstance(provider, ManagedAESEncryptionProvider)

    def test_create_managed_aes_provider_with_config(self):
        """Test creating managed AES provider with custom configuration."""
        provider = EncryptionProviderFactory.create_managed_aes_provider(
            service_name="custom-service", use_fallback=False
        )

        assert isinstance(provider, ManagedAESEncryptionProvider)
        assert provider.service_name == "custom-service"

    def test_create_transit_provider(self):
        """Test creating transit provider via factory."""
        base_provider = AESEncryptionProvider()
        provider = EncryptionProviderFactory.create_transit_provider(base_provider)

        assert isinstance(provider, TransitEncryptionProvider)
        assert provider.base_provider == base_provider

    def test_create_provider_managed_aes(self):
        """Test creating managed AES provider via factory method."""
        provider = EncryptionProviderFactory.create_provider("managed_aes")

        assert isinstance(provider, ManagedAESEncryptionProvider)

    def test_create_provider_transit(self):
        """Test creating transit provider via factory method."""
        provider = EncryptionProviderFactory.create_provider("transit")

        assert isinstance(provider, TransitEncryptionProvider)
        assert isinstance(provider.base_provider, ManagedAESEncryptionProvider)

    def test_create_provider_transit_with_base(self):
        """Test creating transit provider with custom base provider."""
        base_provider = AESEncryptionProvider()
        provider = EncryptionProviderFactory.create_provider("transit", base_provider=base_provider)

        assert isinstance(provider, TransitEncryptionProvider)
        assert provider.base_provider == base_provider

    def test_create_default_provider(self):
        """Test creating default provider."""
        provider = EncryptionProviderFactory.create_default_provider()

        assert isinstance(provider, ManagedAESEncryptionProvider)


class TestEncryptionIntegrationEnhanced:
    """Enhanced integration tests for encryption providers."""

    @pytest.mark.asyncio
    async def test_managed_aes_with_key_rotation(self):
        """Test managed AES provider with key rotation."""
        provider = ManagedAESEncryptionProvider(service_name="test-rotation")
        original_data = b"Test data for key rotation"

        # Encrypt with initial key
        encrypted1, metadata1 = await provider.encrypt(original_data)

        # Decrypt with initial key (should work)
        decrypted1 = await provider.decrypt(encrypted1, metadata1)
        assert decrypted1 == original_data

        # Rotate key
        old_key_id = metadata1.get("key_id", "default")
        await provider.rotate_key(old_key_id)

        # Encrypt with new key
        encrypted2, metadata2 = await provider.encrypt(original_data)

        # New encryption should decrypt correctly
        decrypted2 = await provider.decrypt(encrypted2, metadata2)
        assert decrypted2 == original_data

        # Key fingerprints should be different
        assert metadata1.get("key_fingerprint") != metadata2.get("key_fingerprint")

        # Old encrypted data should fail to decrypt with new key (expected behavior)
        # This demonstrates that key rotation properly changes the encryption key
        with pytest.raises(Exception):  # Should raise EncryptionError due to key mismatch
            await provider.decrypt(encrypted1, metadata1)

    @pytest.mark.asyncio
    async def test_transit_with_managed_base(self):
        """Test transit encryption with managed AES base provider."""
        base_provider = ManagedAESEncryptionProvider(service_name="test-transit-base")
        transit_provider = TransitEncryptionProvider(base_provider)

        original_data = b"Test data for transit with managed base"

        # Encrypt and decrypt
        encrypted_data, metadata = await transit_provider.encrypt(original_data)
        decrypted_data = await transit_provider.decrypt(encrypted_data, metadata)

        assert decrypted_data == original_data
        assert metadata["transit_encryption"] is True
        assert metadata["encryption_at_rest"] is True
        assert metadata["encryption_in_transit"] is True

    @pytest.mark.asyncio
    async def test_all_providers_compatibility(self):
        """Test that all providers can handle their own encrypted data."""
        original_data = b"Cross-provider compatibility test data"

        providers = [
            FernetEncryptionProvider(),
            AESEncryptionProvider(),
            ManagedAESEncryptionProvider(service_name="test-compat"),
            TransitEncryptionProvider(AESEncryptionProvider()),
            NoOpEncryptionProvider(),
        ]

        for provider in providers:
            encrypted_data, metadata = await provider.encrypt(original_data)
            decrypted_data = await provider.decrypt(encrypted_data, metadata)

            assert decrypted_data == original_data

    @pytest.mark.asyncio
    async def test_large_data_with_managed_encryption(self):
        """Test managed encryption with large data."""
        # Create 1MB of test data
        large_data = b"A" * (1024 * 1024)

        provider = ManagedAESEncryptionProvider(service_name="test-large-data")

        encrypted_data, metadata = await provider.encrypt(large_data)
        decrypted_data = await provider.decrypt(encrypted_data, metadata)

        assert decrypted_data == large_data
        assert len(decrypted_data) == len(large_data)
        assert metadata["algorithm"] == "AES-256-GCM-Managed"


if __name__ == "__main__":
    pytest.main([__file__])
