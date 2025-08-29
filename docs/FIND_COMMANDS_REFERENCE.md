# Find Commands Reference

## Overview

The `find` commands in awsideman provide powerful search capabilities across users, groups, and permission sets using regex patterns. These commands are designed to help administrators quickly locate specific resources in large AWS Identity Center environments.

## Common Features

All find commands share the following features:

- **Regex Pattern Matching**: Use regular expressions for flexible and powerful searching
- **Case Sensitivity Control**: Option to make searches case-sensitive or case-insensitive
- **Result Limiting**: Limit the number of results returned
- **Profile Support**: Work with different AWS profiles
- **Verbose Output**: Detailed logging and cache information
- **Rich Table Display**: Beautiful, formatted output using Rich library

## Command Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--case-sensitive` | `-c` | Make the search case sensitive | `False` |
| `--limit` | `-l` | Maximum number of results to return | `None` (no limit) |
| `--profile` | `-p` | AWS profile to use | Default profile |
| `--region` | `-r` | AWS region to use | Profile default |
| `--verbose` | `-v` | Show detailed output | `False` |

## User Find Command

### Command
```bash
awsideman user find <pattern> [OPTIONS]
```

### Description
Searches for users in the Identity Store based on a regex pattern. The search covers:
- Username
- Display name
- Email addresses
- Given name
- Family name
- Full name combinations

### Examples

#### Basic Search
```bash
# Find users with 'han' in their name (case insensitive)
awsideman user find 'han'

# Find users with 'john' in their username (case sensitive)
awsideman user find 'john' --case-sensitive
```

#### Email Search
```bash
# Find users with email addresses ending in '@company.com'
awsideman user find '@company\\.com$'

# Find users with email addresses containing 'admin'
awsideman user find 'admin.*@'
```

#### Pattern Matching
```bash
# Find users with names starting with 'A' and ending with 'n'
awsideman user find '^A.*n$'

# Find users with usernames containing exactly 3 characters
awsideman user find '^.{3}$'
```

#### Advanced Usage
```bash
# Limit results to 10 users
awsideman user find 'admin' --limit 10

# Use a specific AWS profile
awsideman user find 'test' --profile dev-account

# Verbose output with cache information
awsideman user find 'user' --verbose
```

### Output Format
The command displays results in a table with columns:
- **User ID**: Unique identifier for the user
- **Username**: Login username
- **Email**: Primary email address
- **Display Name**: Human-readable display name
- **Full Name**: Combined given and family name

## Group Find Command

###Command
```bash
awsideman group find <pattern> [OPTIONS]
```

### Description
Searches for groups in the Identity Store based on a regex pattern. The search covers:
- Display name
- Description
- External IDs

### Examples

#### Basic Search
```bash
# Find groups with 'admin' in their name (case insensitive)
awsideman group find 'admin'

# Find groups with 'dev' in their name (case sensitive)
awsideman group find 'dev' --case-sensitive
```

#### Description Search
```bash
# Find groups with descriptions containing 'temporary'
awsideman group find 'temporary'

# Find groups with descriptions starting with 'Team'
awsideman group find '^Team'
```

#### Pattern Matching
```bash
# Find groups with names starting with 'A' and ending with 's'
awsideman group find '^A.*s$'

# Find groups with names containing exactly 5 characters
awsideman group find '^.{5}$'
```

#### Advanced Usage
```bash
# Limit results to 5 groups
awsideman group find 'team' --limit 5

# Use a specific AWS profile
awsideman group find 'test' --profile dev-account

# Verbose output with cache information
awsideman group find 'group' --verbose
```

### Output Format
The command displays results in a table with columns:
- **Group ID**: Unique identifier for the group
- **Display Name**: Human-readable display name
- **Description**: Group description
- **External ID**: External identifier (if configured)

## Permission Set Find Command

### Command
```bash
awsideman permission-set find <pattern> [OPTIONS]
```

### Description
Searches for permission sets in AWS Identity Center based on a regex pattern. The search covers:
- Permission set name
- Description

### Examples

#### Basic Search
```bash
# Find permission sets with 'admin' in their name (case insensitive)
awsideman permission-set find 'admin'

# Find permission sets with 'readonly' in their name (case sensitive)
awsideman permission-set find 'readonly' --case-sensitive
```

#### Description Search
```bash
# Find permission sets with descriptions containing 'temporary'
awsideman permission-set find 'temporary'

# Find permission sets with descriptions starting with 'Full'
awsideman permission-set find '^Full'
```

#### Pattern Matching
```bash
# Find permission sets with names starting with 'A' and ending with 'n'
awsideman permission-set find '^A.*n$'

# Find permission sets with names containing exactly 8 characters
awsideman permission-set find '^.{8}$'
```

#### Advanced Usage
```bash
# Limit results to 5 permission sets
awsideman permission-set find 'team' --limit 5

# Use a specific AWS profile
awsideman permission-set find 'test' --profile dev-account

# Verbose output with cache information
awsideman permission-set find 'permission' --verbose
```

### Output Format
The command displays results in a table with columns:
- **Name**: Permission set name
- **Description**: Permission set description
- **Session Duration**: Session timeout duration
- **Relay State**: Relay state configuration
- **ARN**: Permission set ARN (truncated for display)

## Regex Pattern Examples

### Common Patterns

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `admin` | Contains "admin" anywhere | "admin", "Administrator", "sysadmin" |
| `^admin` | Starts with "admin" | "admin", "adminuser" |
| `admin$` | Ends with "admin" | "admin", "superadmin" |
| `^admin$` | Exactly "admin" | "admin" only |
| `admin\|user` | Contains "admin" or "user" | "admin", "user", "adminuser" |
| `[A-Z]` | Any uppercase letter | "A", "B", "Z" |
| `[a-z]+` | One or more lowercase letters | "a", "ab", "xyz" |
| `\d{3}` | Exactly 3 digits | "123", "456", "789" |
| `\w+@\w+\.\w+` | Basic email pattern | "user@domain.com" |

### Escaping Special Characters

When searching for literal characters that have special meaning in regex:

```bash
# Search for literal dot (.)
awsideman user find '\.'

# Search for literal plus sign (+)
awsideman user find '\+'

# Search for literal dollar sign ($)
awsideman user find '\$'
```

## Performance Considerations

### Caching
- All find commands use the awsideman caching system for better performance
- Subsequent searches on the same profile will be faster
- Use `--verbose` to see cache information

### Large Environments
- For environments with thousands of users/groups/permission sets, consider using `--limit`
- The search is performed locally after retrieving all resources from AWS
- Consider using more specific patterns to reduce result sets

### Best Practices
1. **Use specific patterns** when possible to reduce search time
2. **Leverage caching** by running searches multiple times
3. **Use limits** for large result sets
4. **Test patterns** with `--verbose` to understand what's being searched

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| Invalid regex pattern | Malformed regular expression | Check regex syntax and escape special characters |
| No SSO instance configured | Profile missing SSO configuration | Use `awsideman sso set` to configure the profile |
| AWS credentials error | Invalid or expired credentials | Check AWS profile configuration |
| Permission denied | Insufficient IAM permissions | Ensure profile has required permissions |

### Debugging
Use the `--verbose` flag to get detailed information about:
- Cache status
- AWS API calls
- Error details
- Search progress

## Integration with Other Commands

The find commands can be used in combination with other awsideman commands:

```bash
# Find a user and then get detailed information
awsideman user find 'john' | head -1 | awsideman user get <user_id>

# Find groups and then list their members
awsideman group find 'admin' | head -1 | awsideman group members list <group_id>

# Find permission sets and then check assignments
awsideman permission-set find 'readonly' | head -1 | awsideman assignment list --permission-set <permission_set_arn>
```

## Security Features

### Profile Isolation
- All find commands respect AWS profile boundaries
- No cross-profile data leakage
- Secure credential handling

### Input Validation
- Regex patterns are validated before execution
- Malicious patterns are rejected
- Safe error messages without information disclosure

### Audit Trail
- All searches are logged for audit purposes
- Profile information is tracked
- Search patterns are recorded

## Future Enhancements

Planned improvements for find commands:
- **Advanced filtering**: Filter by creation date, last modified, etc.
- **Export options**: Export results to CSV, JSON, or other formats
- **Batch operations**: Perform operations on multiple found resources
- **Saved searches**: Save and reuse common search patterns
- **Search history**: Track and repeat previous searches
