#!/bin/bash

# awsideman Release Script
# This script helps automate the release process

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."

    if ! command_exists git; then
        print_error "git is not installed"
        exit 1
    fi

    if ! command_exists poetry; then
        print_error "poetry is not installed"
        exit 1
    fi

    if ! command_exists python3; then
        print_error "python3 is not installed"
        exit 1
    fi

    print_success "All prerequisites are met"
}

# Function to check git status
check_git_status() {
    print_status "Checking git status..."

    if [[ -n $(git status --porcelain) ]]; then
        print_error "Working directory is not clean. Please commit or stash changes first."
        git status --short
        exit 1
    fi

    if [[ -n $(git log --oneline origin/main..HEAD) ]]; then
        print_warning "You have unpushed commits. Consider pushing them first."
    fi

    print_success "Git status is clean"
}

# Function to run tests
run_tests() {
    print_status "Running tests..."

    if ! poetry run pytest; then
        print_error "Tests failed. Please fix them before releasing."
        exit 1
    fi

    print_success "All tests passed"
}

# Function to run quality checks
run_quality_checks() {
    print_status "Running quality checks..."

    print_status "Running black..."
    if ! poetry run black --check src/ tests/; then
        print_error "Code formatting check failed. Run 'poetry run black src/ tests/' to fix."
        exit 1
    fi

    print_status "Running isort..."
    if ! poetry run isort --check-only src/ tests/; then
        print_error "Import sorting check failed. Run 'poetry run isort src/ tests/' to fix."
        exit 1
    fi

    print_status "Running ruff..."
    if ! poetry run ruff check src/ tests/; then
        print_error "Linting failed. Please fix the issues."
        exit 1
    fi

    # print_status "Running mypy..."
    # if ! poetry run mypy src/; then
    #     print_warning "Type checking failed. This is not blocking but should be addressed."
    # fi

    print_success "Quality checks completed"
}

# Function to build package
build_package() {
    print_status "Building package..."

    if ! poetry build; then
        print_error "Package build failed"
        exit 1
    fi

    print_success "Package built successfully"
}

# Function to create and push tag
create_tag() {
    local version=$1

    print_status "Creating and pushing tag v$version..."

    if git tag -l | grep -q "v$version"; then
        print_error "Tag v$version already exists"
        exit 1
    fi

    git tag -a "v$version" -m "Release v$version"
    git push origin "v$version"

    print_success "Tag v$version created and pushed"
}

# Function to show next steps
show_next_steps() {
    local version=$1

    echo
    print_success "Release preparation completed successfully!"
    echo
    echo "Next steps:"
    echo "1. The GitHub Actions workflow will automatically:"
    echo "   - Run all tests and quality checks"
    echo "   - Build the package"
    echo "   - Create a GitHub release"
    echo "   - Publish to PyPI (for alpha releases)"
    echo
    echo "2. Monitor the workflow at:"
    echo "   https://github.com/vikyol/awsideman/actions"
    echo
    echo "3. Review the release at:"
    echo "   https://github.com/vikyol/awsideman/releases"
    echo
    echo "4. Share the release with your community!"
    echo
}

# Main function
main() {
    local version=${1:-"0.1.0-alpha.1"}

    echo "awsideman Release Script"
    echo "=========================="
    echo "Version: $version"
    echo

    # Check if this is a dry run
    if [[ "$2" == "--dry-run" ]]; then
        print_warning "DRY RUN MODE - No changes will be made"
        echo
    fi

    # Run all checks
    check_prerequisites
    check_git_status
    run_tests
    run_quality_checks
    build_package

    # If not dry run, create tag
    if [[ "$2" != "--dry-run" ]]; then
        create_tag "$version"
    else
        print_warning "DRY RUN: Would create tag v$version"
    fi

    show_next_steps "$version"
}

# Check if version is provided
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <version> [--dry-run]"
    echo "Example: $0 0.1.0-alpha.1"
    echo "Example: $0 0.1.0-alpha.1 --dry-run"
    exit 1
fi

# Run main function
main "$@"
