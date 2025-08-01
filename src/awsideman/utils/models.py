"""Data models for AWS Organizations structure and metadata."""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Literal, Optional, Union
from enum import Enum


class NodeType(str, Enum):
    """Enumeration for organization node types."""
    ROOT = "ROOT"
    OU = "OU"
    ACCOUNT = "ACCOUNT"


class PolicyType(str, Enum):
    """Enumeration for AWS Organizations policy types."""
    SERVICE_CONTROL_POLICY = "SERVICE_CONTROL_POLICY"
    RESOURCE_CONTROL_POLICY = "RESOURCE_CONTROL_POLICY"


@dataclass
class OrgNode:
    """
    Represents a node in the AWS Organizations hierarchy.
    
    This can be a root, organizational unit (OU), or account.
    """
    id: str
    name: str
    type: NodeType
    children: List["OrgNode"]
    
    def __post_init__(self):
        """Ensure children is always a list."""
        if self.children is None:
            self.children = []
    
    def add_child(self, child: "OrgNode") -> None:
        """Add a child node to this node."""
        self.children.append(child)
    
    def is_root(self) -> bool:
        """Check if this node is a root."""
        return self.type == NodeType.ROOT
    
    def is_ou(self) -> bool:
        """Check if this node is an organizational unit."""
        return self.type == NodeType.OU
    
    def is_account(self) -> bool:
        """Check if this node is an account."""
        return self.type == NodeType.ACCOUNT


@dataclass
class AccountDetails:
    """
    Comprehensive metadata for an AWS account.
    
    Contains all relevant information about an account including
    its organizational context and metadata.
    """
    id: str
    name: str
    email: str
    status: str
    joined_timestamp: datetime
    tags: Dict[str, str]
    ou_path: List[str]  # List of OU IDs or names from root to account
    
    def __post_init__(self):
        """Ensure collections are properly initialized."""
        if self.tags is None:
            self.tags = {}
        if self.ou_path is None:
            self.ou_path = []
    
    def get_tag(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a tag value by key."""
        return self.tags.get(key, default)
    
    def has_tag(self, key: str, value: Optional[str] = None) -> bool:
        """Check if account has a specific tag, optionally with a specific value."""
        if key not in self.tags:
            return False
        if value is None:
            return True
        return self.tags[key] == value


@dataclass
class PolicyInfo:
    """
    Information about a policy attached to an organization target.
    
    Represents either a Service Control Policy (SCP) or Resource Control Policy (RCP).
    """
    id: str
    name: str
    type: PolicyType
    description: Optional[str]
    aws_managed: bool
    attachment_point: str  # ID of the target where policy is attached
    attachment_point_name: Optional[str]  # Human-readable name of attachment point
    effective_status: str  # Status of the policy (e.g., "ENABLED", "DISABLED")
    
    def __post_init__(self):
        """Set default values for optional fields."""
        if self.description is None:
            self.description = ""
        if self.attachment_point_name is None:
            self.attachment_point_name = self.attachment_point
    
    def is_scp(self) -> bool:
        """Check if this is a Service Control Policy."""
        return self.type == PolicyType.SERVICE_CONTROL_POLICY
    
    def is_rcp(self) -> bool:
        """Check if this is a Resource Control Policy."""
        return self.type == PolicyType.RESOURCE_CONTROL_POLICY


@dataclass
class HierarchyPath:
    """
    Represents a path through the organization hierarchy.
    
    Contains both IDs and names for each level from root to target.
    """
    ids: List[str]  # List of IDs from root to target
    names: List[str]  # List of names from root to target
    types: List[NodeType]  # List of node types from root to target
    
    def __post_init__(self):
        """Ensure all lists are properly initialized and have same length."""
        if self.ids is None:
            self.ids = []
        if self.names is None:
            self.names = []
        if self.types is None:
            self.types = []
        
        # Ensure all lists have the same length
        max_len = max(len(self.ids), len(self.names), len(self.types))
        self.ids.extend([""] * (max_len - len(self.ids)))
        self.names.extend([""] * (max_len - len(self.names)))
        self.types.extend([NodeType.OU] * (max_len - len(self.types)))
    
    def depth(self) -> int:
        """Get the depth of the hierarchy path."""
        return len(self.ids)
    
    def get_path_string(self, separator: str = " → ") -> str:
        """Get a human-readable string representation of the path."""
        return separator.join(self.names)
    
    def get_id_path_string(self, separator: str = "/") -> str:
        """Get a string representation of the path using IDs."""
        return separator.join(self.ids)


# Type aliases for common use cases
OrganizationTree = List[OrgNode]
PolicyList = List[PolicyInfo]
TagDict = Dict[str, str]