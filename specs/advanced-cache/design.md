# Advanced Cache Features Design Document

## Overview

This design document outlines the architecture for implementing advanced cache features including encryption and DynamoDB backend support. The design provides enterprise-grade security and scalability options with a clean, modern architecture.

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cache Layer                              │
├─────────────────────────────────────────────────────────────────┤
│  CacheManager (Enhanced)                                        │
│  ├── Backend Interface                                          │
│  ├── Encryption Interface                                       │
│  └── Configuration Manager                                      │
├─────────────────────────────────────────────────────────────────┤
│  Cache Backends                    │  Encryption Providers      │
│  ├── FileBackend (existing)        │  ├── AESEncryption         │
│  ├── DynamoDBBackend (new)         │  ├── NoEncryption (default)│
│  └── HybridBackend (new)           │  └── KeyManager            │
├─────────────────────────────────────────────────────────────────┤
│  Storage Layer                                                  │
│  ├── Local Files (~/.awsideman/cache/)                         │
│  ├── DynamoDB Table                                             │
│  └── OS Keyring (encryption keys)                              │
└─────────────────────────────────────────────────────────────────┘
```

### Component Design

#### 1. CacheManager

The CacheManager provides a unified interface with pluggable backends and encryption:

```python
class CacheManager:
    def __init__(self,
                 config: CacheConfig,
                 backend: CacheBackend = None,
                 encryption: EncryptionProvider = None):
        self.config = config
        self.backend = backend or self._create_default_backend()
        self.encryption = encryption or self._create_default_encryption()

    def get(self, key: str) -> Optional[Any]:
        encrypted_data = self.backend.get(key)
        if encrypted_data:
            return self.encryption.decrypt(encrypted_data)
        return None

    def set(self, key: str, data: Any, ttl: Optional[int] = None, operation: str = "unknown"):
        encrypted_data = self.encryption.encrypt(data)
        self.backend.set(key, encrypted_data, ttl, operation)
```

#### 2. Backend Interface

```python
from abc import ABC, abstractmethod

class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        """Retrieve raw encrypted data from backend"""
        pass

    @abstractmethod
    def set(self, key: str, data: bytes, ttl: Optional[int] = None, operation: str = "unknown"):
        """Store raw encrypted data to backend"""
        pass

    @abstractmethod
    def invalidate(self, key: Optional[str] = None):
        """Remove cache entries"""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get backend-specific statistics"""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if backend is healthy"""
        pass
```

#### 3. File Backend

```python
class FileBackend(CacheBackend):
    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.path_manager = CachePathManager(cache_dir)

    def get(self, key: str) -> Optional[bytes]:
        cache_file = self.path_manager.get_cache_file_path(key)
        if cache_file.exists():
            return cache_file.read_bytes()
        return None

    def set(self, key: str, data: bytes, ttl: Optional[int] = None, operation: str = "unknown"):
        cache_file = self.path_manager.get_cache_file_path(key)
        cache_file.write_bytes(data)
```

#### 4. DynamoDB Backend

```python
class DynamoDBBackend(CacheBackend):
    def __init__(self, table_name: str, region: str = None, profile: str = None):
        self.table_name = table_name
        self.region = region
        self.profile = profile
        self._client = None
        self._table = None

    @property
    def client(self):
        if not self._client:
            session = boto3.Session(profile_name=self.profile, region_name=self.region)
            self._client = session.client('dynamodb')
        return self._client

    @property
    def table(self):
        if not self._table:
            self._table = boto3.resource('dynamodb',
                                       region_name=self.region,
                                       profile_name=self.profile).Table(self.table_name)
        return self._table

    def get(self, key: str) -> Optional[bytes]:
        try:
            response = self.table.get_item(Key={'cache_key': key})
            if 'Item' in response:
                item = response['Item']
                # Check TTL
                if 'ttl' in item and item['ttl'] < int(time.time()):
                    return None
                return base64.b64decode(item['data'])
        except Exception as e:
            logger.error(f"DynamoDB get error: {e}")
            return None

    def set(self, key: str, data: bytes, ttl: Optional[int] = None, operation: str = "unknown"):
        try:
            item = {
                'cache_key': key,
                'data': base64.b64encode(data).decode('utf-8'),
                'operation': operation,
                'created_at': int(time.time())
            }

            if ttl:
                item['ttl'] = int(time.time() + ttl)

            self.table.put_item(Item=item)
        except Exception as e:
            logger.error(f"DynamoDB set error: {e}")

    def ensure_table_exists(self):
        """Create DynamoDB table if it doesn't exist"""
        try:
            self.table.load()
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                self._create_table()
            else:
                raise

    def _create_table(self):
        """Create the DynamoDB table with proper configuration"""
        dynamodb = boto3.resource('dynamodb',
                                region_name=self.region,
                                profile_name=self.profile)

        table = dynamodb.create_table(
            TableName=self.table_name,
            KeySchema=[
                {'AttributeName': 'cache_key', 'KeyType': 'HASH'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'cache_key', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST',
            TimeToLiveSpecification={
                'AttributeName': 'ttl',
                'Enabled': True
            }
        )

        # Wait for table to be created
        table.wait_until_exists()
        logger.info(f"Created DynamoDB table: {self.table_name}")
```

#### 5. Encryption Interface

```python
class EncryptionProvider(ABC):
    @abstractmethod
    def encrypt(self, data: Any) -> bytes:
        """Encrypt data and return bytes"""
        pass

    @abstractmethod
    def decrypt(self, encrypted_data: bytes) -> Any:
        """Decrypt bytes and return original data"""
        pass

class NoEncryption(EncryptionProvider):
    """No-encryption provider for development/testing"""
    def encrypt(self, data: Any) -> bytes:
        return json.dumps(data).encode('utf-8')

    def decrypt(self, encrypted_data: bytes) -> Any:
        return json.loads(encrypted_data.decode('utf-8'))

class AESEncryption(EncryptionProvider):
    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager

    def encrypt(self, data: Any) -> bytes:
        # Serialize data to JSON
        json_data = json.dumps(data).encode('utf-8')

        # Get encryption key
        key = self.key_manager.get_key()

        # Generate random IV
        iv = os.urandom(16)

        # Encrypt data
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_data = self._pad(json_data)
        encrypted_data = cipher.encrypt(padded_data)

        # Return IV + encrypted data
        return iv + encrypted_data

    def decrypt(self, encrypted_data: bytes) -> Any:
        # Extract IV and encrypted data
        iv = encrypted_data[:16]
        encrypted_content = encrypted_data[16:]

        # Get decryption key
        key = self.key_manager.get_key()

        # Decrypt data
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_data = cipher.decrypt(encrypted_content)
        json_data = self._unpad(padded_data)

        # Deserialize JSON
        return json.loads(json_data.decode('utf-8'))

    def _pad(self, data: bytes) -> bytes:
        """PKCS7 padding"""
        padding_length = 16 - (len(data) % 16)
        padding = bytes([padding_length] * padding_length)
        return data + padding

    def _unpad(self, data: bytes) -> bytes:
        """Remove PKCS7 padding"""
        padding_length = data[-1]
        return data[:-padding_length]
```

#### 6. Key Management

```python
import keyring
from cryptography.fernet import Fernet

class KeyManager:
    def __init__(self, service_name: str = "awsideman-cache"):
        self.service_name = service_name
        self.username = "encryption-key"

    def get_key(self) -> bytes:
        """Get or generate encryption key"""
        key_str = keyring.get_password(self.service_name, self.username)
        if not key_str:
            key = self._generate_key()
            self._store_key(key)
            return key
        return base64.b64decode(key_str.encode())

    def rotate_key(self) -> bytes:
        """Generate new key and return old key for re-encryption"""
        old_key_str = keyring.get_password(self.service_name, self.username)
        old_key = base64.b64decode(old_key_str.encode()) if old_key_str else None

        new_key = self._generate_key()
        self._store_key(new_key)

        return old_key, new_key

    def _generate_key(self) -> bytes:
        """Generate a new AES-256 key"""
        return os.urandom(32)  # 256 bits

    def _store_key(self, key: bytes):
        """Store key in OS keyring"""
        key_str = base64.b64encode(key).decode()
        keyring.set_password(self.service_name, self.username, key_str)
```

#### 7. Configuration

```python
@dataclass
class AdvancedCacheConfig(CacheConfig):
    # Backend configuration
    backend_type: str = "file"  # "file", "dynamodb", "hybrid"

    # DynamoDB configuration
    dynamodb_table_name: str = "awsideman-cache"
    dynamodb_region: str = None
    dynamodb_profile: str = None

    # Encryption configuration
    encryption_enabled: bool = False
    encryption_type: str = "aes256"  # "none", "aes256"

    # Hybrid backend configuration
    hybrid_local_ttl: int = 300  # 5 minutes local cache for hybrid mode

    @classmethod
    def from_config_file(cls, config_path: str = None) -> 'AdvancedCacheConfig':
        """Load configuration from YAML file"""
        if not config_path:
            config_path = Path.home() / ".awsideman" / "config.yaml"

        if config_path.exists():
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
                cache_config = config_data.get('cache', {})
                return cls(**cache_config)

        return cls()

    @classmethod
    def from_environment(cls) -> 'AdvancedCacheConfig':
        """Load configuration from environment variables"""
        return cls(
            enabled=os.getenv('AWSIDEMAN_CACHE_ENABLED', 'true').lower() == 'true',
            backend_type=os.getenv('AWSIDEMAN_CACHE_BACKEND', 'file'),
            encryption_enabled=os.getenv('AWSIDEMAN_CACHE_ENCRYPTION', 'false').lower() == 'true',
            dynamodb_table_name=os.getenv('AWSIDEMAN_CACHE_DYNAMODB_TABLE', 'awsideman-cache'),
            dynamodb_region=os.getenv('AWSIDEMAN_CACHE_DYNAMODB_REGION'),
            dynamodb_profile=os.getenv('AWSIDEMAN_CACHE_DYNAMODB_PROFILE'),
            default_ttl=int(os.getenv('AWSIDEMAN_CACHE_TTL', '3600')),
            max_size_mb=int(os.getenv('AWSIDEMAN_CACHE_MAX_SIZE_MB', '100'))
        )
```

## Data Models

### DynamoDB Table Schema

```
Table Name: awsideman-cache (configurable)

Primary Key:
- cache_key (String, Hash Key)

Attributes:
- data (String, Base64 encoded encrypted cache data)
- operation (String, AWS operation name)
- created_at (Number, Unix timestamp)
- ttl (Number, Unix timestamp for TTL expiration)

Indexes: None (simple key-value access pattern)

TTL: Enabled on 'ttl' attribute for automatic expiration
```

### Encrypted Cache Entry Format

```json
{
  "version": 1,
  "encryption_type": "aes256",
  "data": "<base64_encoded_encrypted_data>",
  "metadata": {
    "created_at": 1234567890,
    "ttl": 3600,
    "key": "cache_key",
    "operation": "list_roots"
  }
}
```

## Error Handling

### Backend Failures
- DynamoDB unavailable → Return cache miss, log error
- File system errors → Return cache miss, log error
- Encryption key unavailable → Fail fast with clear error message

### Migration Errors
- Partial migration → Resume from last successful entry
- Encryption/decryption errors → Skip corrupted entries, log warnings
- Backend connectivity issues → Retry with exponential backoff

## Testing Strategy

### Unit Tests
- Backend interface implementations
- Encryption/decryption functionality
- Key management operations
- Configuration loading and validation

### Integration Tests
- End-to-end cache operations with different backends
- Migration between backends
- Encryption key rotation
- DynamoDB table creation and management

### Performance Tests
- Encryption/decryption overhead measurement
- DynamoDB vs file backend performance comparison
- Large cache entry handling
- Concurrent access patterns

## Security Considerations

### Encryption
- Use AES-256 in CBC mode with random IVs
- Store keys in OS keyring (Keychain on macOS, Credential Manager on Windows, Secret Service on Linux)
- Implement secure key rotation with re-encryption of existing data
- Protect against timing attacks during decryption

### DynamoDB Security
- Use IAM roles and policies for access control
- Support VPC endpoints for private connectivity
- Enable encryption at rest and in transit
- Implement least-privilege access patterns

### Key Management
- Never log encryption keys
- Securely delete old keys after rotation
- Support for external key management systems (future)
- Audit logging for key operations

## Migration Strategy

### Phase 1: Core Infrastructure
- Implement backend interface and file backend
- Add encryption support
- Create configuration system

### Phase 2: DynamoDB Backend
- Implement DynamoDB backend
- Add table management functionality
- Create migration utilities

### Phase 3: Advanced Features
- Implement hybrid backend
- Add key rotation functionality
- Create comprehensive CLI commands

## Integration with Command System

### Current Architecture Problem

The current implementation has a fundamental architectural disconnect:

1. **Cache System**: Exists as `CachedAwsClient` with proper caching functionality
2. **Command System**: Uses `AWSClientManager` directly, bypassing the cache entirely
3. **Cache Warming**: Executes commands via `CliRunner`, but commands don't use cached clients

### Root Cause Analysis

**What's happening:**
- Cache warming command executes `awsideman user list` using CliRunner
- CliRunner runs the command in a separate process
- User list command uses `AWSClientManager` directly (not cached)
- AWS API calls are made without caching
- No cache entries are created
- Cache warming reports "already warm" because no entries were added

**What should happen:**
- Commands should use cached AWS clients that intercept API calls
- API responses should be cached automatically
- Cache warming should populate the cache with real data

### Solution: Integrated Cache Architecture

The solution requires modifying the command system to use cached clients by default:

#### 1. Enhanced AWSClientManager

```python
class AWSClientManager:
    def __init__(self,
                 profile: Optional[str] = None,
                 region: Optional[str] = None,
                 enable_caching: bool = True,
                 cache_config: Optional[CacheConfig] = None):
        self.profile = profile
        self.region = region
        self.enable_caching = enable_caching
        self.cache_config = cache_config
        self._cache_manager = None
        self._cached_client = None

    @property
    def cache_manager(self) -> Optional[CacheManager]:
        """Get or create cache manager if caching is enabled."""
        if self.enable_caching and not self._cache_manager:
            self._cache_manager = CacheManager(config=self.cache_config)
        return self._cache_manager

    @property
    def cached_client(self) -> Optional[CachedAwsClient]:
        """Get or create cached client if caching is enabled."""
        if self.enable_caching and not self._cached_client:
            self._cached_client = CachedAwsClient(self, self.cache_manager)
        return self._cached_client

    def get_organizations_client(self):
        """Get Organizations client (cached if caching enabled)."""
        if self.enable_caching and self.cached_client:
            return self.cached_client.get_organizations_client()
        else:
            return OrganizationsClientWrapper(self)

    def get_identity_center_client(self):
        """Get Identity Center client (cached if caching enabled)."""
        if self.enable_caching and self.cached_client:
            return self.cached_client.get_identity_center_client()
        else:
            return IdentityCenterClientWrapper(self)

    def get_identity_store_client(self):
        """Get Identity Store client (cached if caching enabled)."""
        if self.enable_caching and self.cached_client:
            return self.cached_client.get_identity_store_client()
        else:
            return IdentityStoreClientWrapper(self)
```

#### 2. Global Cache Configuration

```python
# In utils/config.py or similar
def get_default_cache_config() -> CacheConfig:
    """Get default cache configuration from config file or environment."""
    return AdvancedCacheConfig.from_config_file()

def create_aws_client_manager(
    profile: Optional[str] = None,
    region: Optional[str] = None,
    enable_caching: Optional[bool] = None,
    cache_config: Optional[CacheConfig] = None
) -> AWSClientManager:
    """Factory function to create AWSClientManager with proper cache integration."""

    # Use global cache configuration if not specified
    if cache_config is None:
        cache_config = get_default_cache_config()

    # Enable caching by default unless explicitly disabled
    if enable_caching is None:
        enable_caching = cache_config.enabled

    return AWSClientManager(
        profile=profile,
        region=region,
        enable_caching=enable_caching,
        cache_config=cache_config
    )
```

#### 3. Command Integration

Update all commands to use the factory function:

```python
# In commands/user/list.py
def list_users(
    filter: Optional[str] = None,
    limit: Optional[int] = None,
    next_token: Optional[str] = None,
    profile: Optional[str] = None,
    no_cache: bool = False,  # Add no-cache option
):
    """List all users in the Identity Store."""
    try:
        # Validate profile
        profile_name, profile_data = validate_profile(profile)

        # Create AWS client manager with caching
        aws_client = create_aws_client_manager(
            profile=profile_name,
            region=profile_data.get("region"),
            enable_caching=not no_cache
        )

        # Get identity store client (will be cached if caching enabled)
        identity_store = aws_client.get_identity_store_client()

        # Rest of the command logic remains the same...
```

#### 4. Cache Warming Integration

The cache warming command will now work correctly because commands use cached clients:

```python
def warm_cache(command: str, profile: Optional[str] = None, region: Optional[str] = None):
    """Warm up the cache by pre-executing a command."""
    try:
        cache_manager = get_cache_manager()

        if not cache_manager.config.enabled:
            console.print("[yellow]Cache is disabled. Cannot warm cache.[/yellow]")
            return

        # Get cache stats before warming
        stats_before = cache_manager.get_cache_stats()
        entries_before = stats_before.get("total_entries", 0)

        # Execute the command (will now use cached clients)
        _execute_command_with_cli_runner(command_parts, profile, region)

        # Get cache stats after warming
        stats_after = cache_manager.get_cache_stats()
        entries_after = stats_after.get("total_entries", 0)

        # Report results
        new_entries = entries_after - entries_before
        if new_entries > 0:
            console.print(f"[green]✓ Cache warmed successfully! Added {new_entries} new cache entries.[/green]")
        else:
            console.print("[yellow]Cache was already warm for this command (no new entries added).[/yellow]")

    except Exception as e:
        console.print(f"[red]Error warming cache: {e}[/red]")
        raise typer.Exit(1)
```

### Implementation Strategy

#### Phase 1: Core Integration
1. Modify `AWSClientManager` to support optional caching
2. Create factory function for consistent client creation
3. Update configuration system to support cache settings

#### Phase 2: Command Updates
1. Update all commands to use the factory function
2. Add `--no-cache` option to all commands
3. Ensure cache warming works with all command types

#### Phase 3: Testing & Validation
1. Test cache warming with different backends (file, DynamoDB)
2. Verify cache hit/miss behavior
3. Performance testing with and without caching

This architectural change ensures that:
- All commands use cached clients by default
- Cache warming actually populates the cache
- Users can disable caching per command if needed
- The cache system works seamlessly with all backends
