# Bulk Operations Examples

This directory contains examples of how to use the bulk operations feature in awsideman CLI, including sample input files and usage patterns.

## Example Input Files

This directory contains various example files demonstrating different bulk assignment scenarios:

### CSV Examples

- **`sample-user-assignments.csv`** - Basic user assignments with human-readable names
- **`sample-group-assignments.csv`** - Group assignments using group names
- **`mixed-assignments.csv`** - Mixed user and group assignments
- **`advanced-assignments.csv`** - Advanced format with optional ID/ARN fields
- **`validation-errors.csv`** - Examples that will trigger validation errors for testing

### JSON Examples

- **`sample-user-assignments.json`** - User assignments in JSON format
- **`sample-group-assignments.json`** - Group assignments in JSON format
- **`mixed-assignments.json`** - Mixed assignments in JSON format
- **`advanced-assignments.json`** - Advanced JSON with optional fields
- **`validation-errors.json`** - JSON examples with validation errors

## CLI Usage Examples

### Basic Bulk Assignment

```bash
# Assign permission sets from CSV file
awsideman bulk assign sample-user-assignments.csv

# Assign permission sets from JSON file
awsideman bulk assign sample-user-assignments.json

# Use dry-run mode to validate without making changes
awsideman bulk assign sample-user-assignments.csv --dry-run

# Specify custom batch size for processing
awsideman bulk assign mixed-assignments.csv --batch-size 5
```

### Bulk Revocation

```bash
# Revoke permission sets from CSV file
awsideman bulk revoke sample-user-assignments.csv

# Force revocation without confirmation prompts
awsideman bulk revoke sample-user-assignments.csv --force

# Stop processing on first error instead of continuing
awsideman bulk revoke mixed-assignments.csv --stop-on-error
```

### Using Different Profiles

```bash
# Use specific AWS profile
awsideman bulk assign sample-user-assignments.csv --profile production

# Use profile with dry-run
awsideman bulk assign mixed-assignments.csv --profile staging --dry-run
```

## File Format Requirements

### CSV Format

**Required Columns:**
- `principal_name` - Name of the user or group (human-readable)
- `permission_set_name` - Name of the permission set (human-readable)
- `account_name` - Name of the AWS account (human-readable)

**Optional Columns:**
- `principal_type` - Type of principal (USER or GROUP, defaults to USER)
- `account_id` - AWS account ID (will be resolved from name if not provided)
- `permission_set_arn` - ARN of the permission set (will be resolved from name if not provided)
- `principal_id` - ID of the user or group (for reference, will be resolved from name)

**Example CSV:**
```csv
principal_name,permission_set_name,account_name,principal_type
john.doe,ReadOnlyAccess,Production,USER
Developers,PowerUserAccess,Development,GROUP
jane.smith,AdministratorAccess,Staging,USER
```

### JSON Format

The JSON format uses a structured format with an `assignments` array:

**Required Fields:**
- `principal_name` - Name of the user or group
- `permission_set_name` - Name of the permission set
- `account_name` - Name of the AWS account

**Optional Fields:**
- `principal_type` - Type of principal (USER or GROUP, defaults to USER)
- `account_id` - AWS account ID
- `permission_set_arn` - ARN of the permission set
- `principal_id` - ID of the user or group

**Example JSON:**
```json
{
  "assignments": [
    {
      "principal_name": "john.doe",
      "permission_set_name": "ReadOnlyAccess",
      "account_name": "Production",
      "principal_type": "USER"
    },
    {
      "principal_name": "Developers",
      "permission_set_name": "PowerUserAccess",
      "account_name": "Development",
      "principal_type": "GROUP"
    }
  ]
}
```

## Name Resolution

The bulk operations feature automatically resolves human-readable names to AWS resource identifiers:

- **Principal Names** → Principal IDs (via Identity Store API)
- **Permission Set Names** → Permission Set ARNs (via SSO Admin API)
- **Account Names** → Account IDs (via Organizations API)

### Caching

Name resolution results are cached during processing to improve performance:
- Multiple assignments for the same principal/permission set/account will reuse cached values
- Cache is automatically cleared between different bulk operations
- Large files benefit significantly from caching

## Error Handling Examples

### Common Validation Errors

The `validation-errors.csv` and `validation-errors.json` files contain examples of common errors:

1. **Nonexistent Principal**: `nonexistent.user` - Principal name that doesn't exist in Identity Store
2. **Invalid Permission Set**: `InvalidPermissionSet` - Permission set name that doesn't exist
3. **Invalid Account**: `NonexistentAccount` - Account name that doesn't exist in organization
4. **Missing Required Fields**: Empty principal_name, permission_set_name, or account_name

### Error Handling Modes

```bash
# Continue processing on errors (default)
awsideman bulk assign validation-errors.csv --continue-on-error

# Stop processing on first error
awsideman bulk assign validation-errors.csv --stop-on-error
```

## Performance Considerations

### Batch Size Optimization

```bash
# Small batch size for rate-limited environments
awsideman bulk assign large-file.csv --batch-size 5

# Larger batch size for better throughput
awsideman bulk assign large-file.csv --batch-size 20
```

### File Size Recommendations

- **Small files** (< 100 assignments): Use default settings
- **Medium files** (100-1000 assignments): Consider batch-size 10-15
- **Large files** (> 1000 assignments): Use batch-size 5-10 and monitor for rate limiting

## Troubleshooting

### Name Resolution Issues

If you encounter name resolution errors:

1. **Verify Names**: Ensure principal, permission set, and account names exactly match those in AWS
2. **Check Permissions**: Verify your AWS credentials have access to Identity Store, SSO Admin, and Organizations APIs
3. **Profile Configuration**: Ensure your AWS profile is correctly configured for the target organization

### Common Issues

- **Case Sensitivity**: Names are case-sensitive and must match exactly
- **Special Characters**: Ensure special characters in names are properly handled
- **Network Issues**: Use smaller batch sizes if experiencing network timeouts
- **Rate Limiting**: Reduce batch size if encountering AWS API rate limits

## Programming Examples

### Using File Processors

```python
from pathlib import Path
from awsideman.bulk import FileFormatDetector, CSVProcessor, JSONProcessor

# Detect file format and get appropriate processor
file_path = Path("sample-user-assignments.csv")
processor = FileFormatDetector.get_processor(file_path)

# Validate file format
errors = processor.validate_format()
if errors:
    for error in errors:
        print(f"Validation error: {error.message}")
else:
    # Parse assignments
    assignments = processor.parse_assignments()
    print(f"Parsed {len(assignments)} assignments")
```

### Using Resource Resolver

```python
from awsideman.bulk import ResourceResolver
from awsideman.aws_clients.manager import AWSClientManager

# Initialize AWS client manager
client_manager = AWSClientManager(profile="my-profile")

# Initialize resolver
resolver = ResourceResolver(
    aws_client_manager=client_manager,
    instance_arn="arn:aws:sso:::instance/ssoins-1234567890abcdef",
    identity_store_id="d-1234567890"
)

# Resolve assignment names to IDs/ARNs
assignment = {
    'principal_name': 'john.doe',
    'principal_type': 'USER',
    'permission_set_name': 'ReadOnlyAccess',
    'account_name': 'Production'
}

resolved_assignment = resolver.resolve_assignment(assignment)

if resolved_assignment['resolution_success']:
    print(f"Principal ID: {resolved_assignment['principal_id']}")
    print(f"Permission Set ARN: {resolved_assignment['permission_set_arn']}")
    print(f"Account ID: {resolved_assignment['account_id']}")
else:
    print("Resolution errors:")
    for error in resolved_assignment['resolution_errors']:
        print(f"  - {error}")
```

### Performance Optimization

```python
# Pre-warm caches for better performance
resolver.warm_cache_for_assignments(assignments)

# Get cache statistics
stats = resolver.get_cache_stats()
print(f"Cached principals: {stats['principals']}")
print(f"Cached permission sets: {stats['permission_sets']}")
print(f"Cached accounts: {stats['accounts']}")

# Clear caches when needed
resolver.clear_cache()
```
