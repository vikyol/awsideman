# Advanced Cache Features Design Document

## Overview

This design document outlines the architecture for implementing advanced cache features including encryption and DynamoDB backend support. The design maintains backward compatibility with the existing file-based cache while providing enterprise-grade security and scalability options.

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

#### 1. Enhanced CacheManager

The existing CacheManager will be extended to support pluggable backends and encryption:

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

#### 3. File Backend (Enhanced)

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
    """Default no-encryption provider"""
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
- DynamoDB unavailable → Fallback to file backend
- File system errors → Log error, continue without caching
- Encryption key unavailable → Disable encryption, warn user

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
- Implement backend interface and file backend refactoring
- Add basic encryption support
- Create configuration system

### Phase 2: DynamoDB Backend
- Implement DynamoDB backend
- Add table management functionality
- Create migration utilities

### Phase 3: Advanced Features
- Implement hybrid backend
- Add key rotation functionality
- Create comprehensive CLI commands

### Phase 4: Enterprise Features
- Add audit logging
- Implement advanced security features
- Add monitoring and alerting capabilities