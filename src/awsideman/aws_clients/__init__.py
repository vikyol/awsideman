"""AWS service client management and integration.

This package provides AWS client management functionality including:
- Client lifecycle and configuration management
- AWS service-specific client wrappers
- Client initialization and setup utilities
- Cached AWS client wrappers for transparent caching
"""

from .manager import AWSClientManager
from .cached_client import CachedAwsClient, CachedOrganizationsClient, CachedIdentityCenterClient, CachedIdentityStoreClient, create_cached_client_manager

__all__ = [
    'AWSClientManager',
    'CachedAwsClient',
    'CachedOrganizationsClient', 
    'CachedIdentityCenterClient',
    'CachedIdentityStoreClient',
    'create_cached_client_manager',
]

__version__ = '1.0.0'