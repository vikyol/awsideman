# awsideman - AWS Identity Center Manager

A CLI tool for managing AWS Identity Center operations.

## Features

- Profile management for AWS credentials
- SSO instance configuration
- User management
- Group management (coming soon)
- Permission set management (coming soon)
- Assignment management (coming soon)
- Caching for improved performance (coming soon)
- Bulk operations (coming soon)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/awsideman.git
cd awsideman

# Install using Poetry
poetry install

# Or install in development mode
pip install -e .
```

## Usage

```bash
# Show help
awsideman --help

# Show version
awsideman --version

# Profile management
awsideman profile list
awsideman profile add my-profile --region us-east-1 --default
awsideman profile update my-profile --region us-west-2
awsideman profile remove my-profile

# SSO instance management
awsideman sso list
awsideman sso set arn:aws:sso:::instance/ssoins-12345678901234567 d-12345678ab
awsideman sso info

# User management
awsideman user list
awsideman user list --filter UserName=john
awsideman user list --limit 10
awsideman user get user-id-12345
awsideman user get john.doe@example.com
awsideman user create --username john.doe --email john.doe@example.com --given-name John --family-name Doe
awsideman user update user-id-12345 --email new.email@example.com --display-name "John Doe"
awsideman user delete user-id-12345
awsideman user delete user-id-12345 --force
```

## Development

```bash
# Install development dependencies
poetry install

# Run tests
poetry run pytest

# Format code
poetry run black .
poetry run isort .
```

## License

MIT