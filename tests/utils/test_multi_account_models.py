"""Tests for multi-account data models."""
import pytest
import time
from typing import List

from src.awsideman.utils.models import (
    AccountInfo,
    AccountResult,
    MultiAccountAssignment,
    MultiAccountResults
)


class TestAccountInfo:
    """Test cases for AccountInfo data model."""
    
    def test_account_info_creation(self):
        """Test basic AccountInfo creation."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "DevOps"},
            ou_path=["root", "production-ou"]
        )
        
        assert account.account_id == "123456789012"
        assert account.account_name == "test-account"
        assert account.email == "test@example.com"
        assert account.status == "ACTIVE"
        assert account.tags == {"Environment": "Production", "Team": "DevOps"}
        assert account.ou_path == ["root", "production-ou"]
    
    def test_account_info_defaults(self):
        """Test AccountInfo with default values."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE"
        )
        
        assert account.tags == {}
        assert account.ou_path == []
    
    def test_matches_tag_filter(self):
        """Test tag filtering functionality."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "DevOps"}
        )
        
        # Test matching tag
        assert account.matches_tag_filter("Environment", "Production") is True
        assert account.matches_tag_filter("Team", "DevOps") is True
        
        # Test non-matching tag
        assert account.matches_tag_filter("Environment", "Development") is False
        assert account.matches_tag_filter("Team", "QA") is False
        
        # Test non-existent tag
        assert account.matches_tag_filter("NonExistent", "Value") is False
    
    def test_get_display_name(self):
        """Test display name generation."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE"
        )
        
        assert account.get_display_name() == "test-account (123456789012)"
    
    def test_has_tag(self):
        """Test has_tag functionality."""
        account = AccountInfo(
            account_id="123456789012",
            account_name="test-account",
            email="test@example.com",
            status="ACTIVE",
            tags={"Environment": "Production", "Team": "DevOps"}
        )
        
        # Test tag exists without value check
        assert account.has_tag("Environment") is True
        assert account.has_tag("Team") is True
        assert account.has_tag("NonExistent") is False
        
        # Test tag exists with value check
        assert account.has_tag("Environment", "Production") is True
        assert account.has_tag("Environment", "Development") is False
        assert account.has_tag("NonExistent", "Value") is False


class TestAccountResult:
    """Test cases for AccountResult data model."""
    
    def test_account_result_creation(self):
        """Test basic AccountResult creation."""
        result = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="success",
            processing_time=1.5,
            retry_count=0
        )
        
        assert result.account_id == "123456789012"
        assert result.account_name == "test-account"
        assert result.status == "success"
        assert result.processing_time == 1.5
        assert result.retry_count == 0
        assert result.error_message is None
        assert result.timestamp is not None
    
    def test_account_result_with_error(self):
        """Test AccountResult with error information."""
        result = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="failed",
            error_message="Permission denied",
            processing_time=0.5,
            retry_count=2
        )
        
        assert result.status == "failed"
        assert result.error_message == "Permission denied"
        assert result.retry_count == 2
    
    def test_is_successful(self):
        """Test success status checking."""
        success_result = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="success"
        )
        
        failed_result = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="failed"
        )
        
        skipped_result = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="skipped"
        )
        
        assert success_result.is_successful() is True
        assert failed_result.is_successful() is False
        assert skipped_result.is_successful() is False
    
    def test_get_error_summary(self):
        """Test error summary generation."""
        result_with_error = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="failed",
            error_message="Permission denied"
        )
        
        result_without_error = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="skipped"
        )
        
        assert result_with_error.get_error_summary() == "Permission denied"
        assert result_without_error.get_error_summary() == "Status: skipped"
    
    def test_get_display_name(self):
        """Test display name generation."""
        result = AccountResult(
            account_id="123456789012",
            account_name="test-account",
            status="success"
        )
        
        assert result.get_display_name() == "test-account (123456789012)"


class TestMultiAccountAssignment:
    """Test cases for MultiAccountAssignment data model."""
    
    def create_sample_accounts(self) -> List[AccountInfo]:
        """Create sample accounts for testing."""
        return [
            AccountInfo(
                account_id="123456789012",
                account_name="account-1",
                email="account1@example.com",
                status="ACTIVE"
            ),
            AccountInfo(
                account_id="123456789013",
                account_name="account-2",
                email="account2@example.com",
                status="ACTIVE"
            )
        ]
    
    def test_multi_account_assignment_creation(self):
        """Test basic MultiAccountAssignment creation."""
        accounts = self.create_sample_accounts()
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@example.com",
            principal_type="USER",
            accounts=accounts,
            operation="assign"
        )
        
        assert assignment.permission_set_name == "ReadOnlyAccess"
        assert assignment.principal_name == "john.doe@example.com"
        assert assignment.principal_type == "USER"
        assert len(assignment.accounts) == 2
        assert assignment.operation == "assign"
        assert assignment.permission_set_arn is None
        assert assignment.principal_id is None
    
    def test_get_total_operations(self):
        """Test total operations calculation."""
        accounts = self.create_sample_accounts()
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@example.com",
            principal_type="USER",
            accounts=accounts,
            operation="assign"
        )
        
        assert assignment.get_total_operations() == 2
    
    def test_validate_valid_assignment(self):
        """Test validation of valid assignment."""
        accounts = self.create_sample_accounts()
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@example.com",
            principal_type="USER",
            accounts=accounts,
            operation="assign"
        )
        
        errors = assignment.validate()
        assert len(errors) == 0
    
    def test_validate_invalid_assignment(self):
        """Test validation of invalid assignment."""
        assignment = MultiAccountAssignment(
            permission_set_name="",
            principal_name="",
            principal_type="INVALID",
            accounts=[],
            operation="invalid"
        )
        
        errors = assignment.validate()
        assert len(errors) == 5
        assert "Permission set name cannot be empty" in errors
        assert "Principal name cannot be empty" in errors
        assert "Invalid principal type: INVALID" in errors
        assert "At least one account must be specified" in errors
        assert "Invalid operation: invalid" in errors
    
    def test_is_resolved(self):
        """Test name resolution status checking."""
        accounts = self.create_sample_accounts()
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@example.com",
            principal_type="USER",
            accounts=accounts,
            operation="assign"
        )
        
        # Initially not resolved
        assert assignment.is_resolved() is False
        
        # Partially resolved
        assignment.permission_set_arn = "arn:aws:sso:::permissionSet/ins-123/ps-456"
        assert assignment.is_resolved() is False
        
        # Fully resolved
        assignment.principal_id = "user-123"
        assert assignment.is_resolved() is True
    
    def test_get_account_ids(self):
        """Test account ID extraction."""
        accounts = self.create_sample_accounts()
        assignment = MultiAccountAssignment(
            permission_set_name="ReadOnlyAccess",
            principal_name="john.doe@example.com",
            principal_type="USER",
            accounts=accounts,
            operation="assign"
        )
        
        account_ids = assignment.get_account_ids()
        assert account_ids == ["123456789012", "123456789013"]


class TestMultiAccountResults:
    """Test cases for MultiAccountResults data model."""
    
    def create_sample_results(self) -> tuple:
        """Create sample results for testing."""
        successful = [
            AccountResult("123456789012", "account-1", "success", processing_time=1.0),
            AccountResult("123456789013", "account-2", "success", processing_time=1.5)
        ]
        
        failed = [
            AccountResult("123456789014", "account-3", "failed", 
                         error_message="Permission denied", processing_time=0.5)
        ]
        
        skipped = [
            AccountResult("123456789015", "account-4", "skipped", processing_time=0.1)
        ]
        
        return successful, failed, skipped
    
    def test_multi_account_results_creation(self):
        """Test basic MultiAccountResults creation."""
        successful, failed, skipped = self.create_sample_results()
        
        results = MultiAccountResults(
            total_accounts=4,
            successful_accounts=successful,
            failed_accounts=failed,
            skipped_accounts=skipped,
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        assert results.total_accounts == 4
        assert len(results.successful_accounts) == 2
        assert len(results.failed_accounts) == 1
        assert len(results.skipped_accounts) == 1
        assert results.operation_type == "assign"
        assert results.duration == 10.5
        assert results.batch_size == 2
    
    def test_auto_correct_total_accounts(self):
        """Test automatic correction of total_accounts."""
        successful, failed, skipped = self.create_sample_results()
        
        # Provide incorrect total_accounts
        results = MultiAccountResults(
            total_accounts=10,  # Incorrect total
            successful_accounts=successful,
            failed_accounts=failed,
            skipped_accounts=skipped,
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        # Should be auto-corrected to 4
        assert results.total_accounts == 4
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        successful, failed, skipped = self.create_sample_results()
        
        results = MultiAccountResults(
            total_accounts=4,
            successful_accounts=successful,
            failed_accounts=failed,
            skipped_accounts=skipped,
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        # 2 successful out of 4 total = 50%
        assert results.success_rate == 50.0
        assert results.failure_rate == 25.0
        assert results.skip_rate == 25.0
    
    def test_success_rate_with_zero_accounts(self):
        """Test success rate calculation with zero accounts."""
        results = MultiAccountResults(
            total_accounts=0,
            successful_accounts=[],
            failed_accounts=[],
            skipped_accounts=[],
            operation_type="assign",
            duration=0.0,
            batch_size=2
        )
        
        assert results.success_rate == 0.0
        assert results.failure_rate == 0.0
        assert results.skip_rate == 0.0
    
    def test_get_summary_stats(self):
        """Test summary statistics generation."""
        successful, failed, skipped = self.create_sample_results()
        
        results = MultiAccountResults(
            total_accounts=4,
            successful_accounts=successful,
            failed_accounts=failed,
            skipped_accounts=skipped,
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        stats = results.get_summary_stats()
        
        assert stats['total_accounts'] == 4
        assert stats['successful_count'] == 2
        assert stats['failed_count'] == 1
        assert stats['skipped_count'] == 1
        assert stats['success_rate'] == 50.0
        assert stats['failure_rate'] == 25.0
        assert stats['skip_rate'] == 25.0
        assert stats['operation_type'] == "assign"
        assert stats['duration_seconds'] == 10.5
        assert stats['batch_size'] == 2
        assert 'average_processing_time' in stats
    
    def test_has_failures(self):
        """Test failure detection."""
        successful, failed, skipped = self.create_sample_results()
        
        results_with_failures = MultiAccountResults(
            total_accounts=4,
            successful_accounts=successful,
            failed_accounts=failed,
            skipped_accounts=skipped,
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        results_without_failures = MultiAccountResults(
            total_accounts=2,
            successful_accounts=successful,
            failed_accounts=[],
            skipped_accounts=[],
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        assert results_with_failures.has_failures() is True
        assert results_without_failures.has_failures() is False
    
    def test_is_complete_success(self):
        """Test complete success detection."""
        successful, failed, skipped = self.create_sample_results()
        
        complete_success = MultiAccountResults(
            total_accounts=2,
            successful_accounts=successful,
            failed_accounts=[],
            skipped_accounts=[],
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        partial_success = MultiAccountResults(
            total_accounts=4,
            successful_accounts=successful,
            failed_accounts=failed,
            skipped_accounts=skipped,
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        assert complete_success.is_complete_success() is True
        assert partial_success.is_complete_success() is False
    
    def test_get_account_id_lists(self):
        """Test account ID list extraction."""
        successful, failed, skipped = self.create_sample_results()
        
        results = MultiAccountResults(
            total_accounts=4,
            successful_accounts=successful,
            failed_accounts=failed,
            skipped_accounts=skipped,
            operation_type="assign",
            duration=10.5,
            batch_size=2
        )
        
        successful_ids = results.get_successful_account_ids()
        failed_ids = results.get_failed_account_ids()
        
        assert successful_ids == ["123456789012", "123456789013"]
        assert failed_ids == ["123456789014"]