# User Find Command

The `awsideman user find` command allows you to search for users in AWS Identity Center using regex patterns. This command searches across multiple user attributes including usernames, display names, email addresses, and name components.

## Usage

```bash
awsideman user find <pattern> [OPTIONS]
```

## Arguments

- **pattern**: Required. The regex pattern to search for in user names, emails, or usernames.

## Options

- `--case-sensitive`, `-c`: Make the search case sensitive (default: case insensitive)
- `--limit`, `-l`: Maximum number of users to return
- `--profile`, `-p`: AWS profile to use (uses default profile if not specified)
- `--region`, `-r`: AWS region to use (uses profile default if not specified)
- `--verbose`, `-v`: Show detailed output
- `--help`: Show help message

## Examples

### Basic Search

```bash
# Find users with "john" in their name or username
poetry run awsideman user find "john"

# Find users with "admin" in their username
poetry run awsideman user find "admin"
```

### Case-Sensitive Search

```bash
# Case-sensitive search for "John" (won't match "john")
poetry run awsideman user find "John" --case-sensitive
```

### Regex Pattern Search

```bash
# Find users whose username starts with "admin"
poetry run awsideman user find "^admin"

# Find users whose email ends with "@company.com"
poetry run awsideman user find "@company\\.com$"

# Find users with "test" anywhere in their name
poetry run awsideman user find ".*test.*"
```

### Limit Results

```bash
# Limit results to first 5 matches
poetry run awsideman user find "user" --limit 5
```

### Profile and Region

```bash
# Use specific AWS profile
poetry run awsideman user find "john" --profile production

# Use specific AWS region
poetry run awsideman user find "john" --region us-west-2
```

### Verbose Output

```bash# Show detailed output including cache information
poetry run awsideman user find "john" --verbose
```

## Search Attributes

The command searches across the following user attributes:

1. **Username** (`UserName`)
2. **Display Name** (`DisplayName`)
3. **Email Addresses** (`Emails[].Value`)
4. **Given Name** (`Name.GivenName`)
5. **Family Name** (`Name.FamilyName`)
6. **Full Name** (combination of GivenName + FamilyName)

## Regex Pattern Examples

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `john` | Simple substring | "john.doe", "johnson", "johnny" |
| `^admin` | Starts with "admin" | "admin", "admin.user", "admin123" |
| `\.com$` | Ends with ".com" | "user@company.com", "test@domain.com" |
| `[A-Z][a-z]+` | Capital letter followed by lowercase | "John", "Admin", "User" |
| `\d+` | One or more digits | "user123", "admin456" |
| `.*test.*` | Contains "test" anywhere | "testuser", "usertest", "testing" |

## Output Format

The command displays results in a rich table format with the following columns:

- **User ID**: The unique identifier for the user
- **Username**: The user's login username
- **Display Name**: The user's display name
- **Given Name**: The user's first name
- **Family Name**: The user's last name
- **Emails**: The user's email addresses (comma-separated if multiple)

## Performance Considerations

- **Caching**: The command uses AWS client caching for better performance
- **Pagination**: Automatically handles large numbers of users through pagination
- **Regex Compilation**: Patterns are compiled once for efficient matching

## Error Handling

- **Invalid Regex**: Clear error message for malformed regex patterns
- **No Matches**: Informative message when no users match the pattern
- **AWS Errors**: Proper error handling for AWS API failures

## Use Cases

### User Discovery

```bash
# Find all users with "admin" in their name
poetry run awsideman user find "admin"

# Find users with specific email domain
poetry run awsideman user find "@company\\.com$"
```

### Compliance and Auditing

```bash
# Find users with "test" in their name (potential test accounts)
poetry run awsideman user find "test"

# Find users with specific naming patterns
poetry run awsideman user find "^[A-Z][a-z]+\\.[A-Z][a-z]+$"
```

### User Management

```bash
# Find users matching specific criteria for bulk operations
poetry run awsideman user find ".*@olddomain\\.com$" --limit 100

# Case-sensitive search for exact matches
poetry run awsideman user find "Admin" --case-sensitive
```

## Integration with Other Commands

The find command can be used in combination with other user management commands:

```bash
# Find users and then get detailed information
poetry run awsideman user find "john" | grep "User ID" | awk '{print $3}' | xargs -I {} poetry run awsideman user get {}
```

## Troubleshooting

### Common Issues

1. **No Results**: Check if the regex pattern is too restrictive
2. **Invalid Pattern**: Ensure regex syntax is correct
3. **Permission Errors**: Verify AWS credentials and permissions
4. **Timeout**: Large user bases may take time to search

### Debug Tips

- Use `--verbose` flag for detailed output
- Test regex patterns in a regex tester first
- Start with simple patterns and add complexity gradually
- Use `--limit` to test with smaller result sets

## Best Practices

1. **Use Specific Patterns**: Avoid overly broad patterns that return too many results
2. **Escape Special Characters**: Properly escape dots, hyphens, and other regex metacharacters
3. **Test Patterns**: Verify regex patterns work as expected
4. **Use Limits**: Set reasonable limits for large user bases
5. **Cache Results**: The command automatically caches results for better performance

## Examples in Practice

### Finding Admin Users

```bash
# Find users with "admin" in their username
poetry run awsideman user find "admin"

# Find users with "Admin" role (case-sensitive)
poetry run awsideman user find "Admin" --case-sensitive
```

### Finding Users by Email Domain

```bash
# Find users with @company.com emails
poetry run awsideman user find "@company\\.com$"

# Find users with @test.company.com emails
poetry run awsideman user find "@test\\.company\\.com$"
```

### Finding Users by Name Pattern

```bash
# Find users with "John" as first name
poetry run awsideman user find "^John"

# Find users with "Smith" as last name
poetry run awsideman user find "Smith$"

# Find users with specific name format (First.Last)
poetry run awsideman user find "^[A-Z][a-z]+\\.[A-Z][a-z]+$"
```

The user find command provides a powerful and flexible way to search for users in AWS Identity Center, making user management and discovery much more efficient.
