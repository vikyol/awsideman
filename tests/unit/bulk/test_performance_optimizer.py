"""Tests for the performance optimizer."""

from unittest.mock import Mock

import pytest

from src.awsideman.bulk.performance_optimizer import (
    PerformanceConfig,
    PerformanceOptimizer,
    create_performance_optimized_processor,
)


class TestPerformanceOptimizer:
    """Test cases for PerformanceOptimizer."""

    @pytest.fixture
    def optimizer(self):
        """Create a PerformanceOptimizer instance."""
        return PerformanceOptimizer()

    def test_small_organization_config(self, optimizer):
        """Test configuration for small organizations."""
        config = optimizer.get_optimized_config(account_count=5, operation_type="assign")

        assert config.max_concurrent_accounts <= 15
        assert config.batch_size == 5  # Should match account count for small orgs
        assert config.rate_limit_delay == 0.1

    def test_medium_organization_config(self, optimizer):
        """Test configuration for medium organizations."""
        config = optimizer.get_optimized_config(account_count=30, operation_type="assign")

        assert config.max_concurrent_accounts <= 25
        assert config.batch_size <= 50
        assert config.rate_limit_delay == 0.05

    def test_large_organization_config(self, optimizer):
        """Test configuration for large organizations."""
        config = optimizer.get_optimized_config(account_count=100, operation_type="assign")

        assert config.max_concurrent_accounts == 30
        assert config.batch_size == 50
        assert config.rate_limit_delay == 0.02

    def test_revoke_operation_optimization(self, optimizer):
        """Test that revoke operations get more aggressive settings."""
        assign_config = optimizer.get_optimized_config(account_count=30, operation_type="assign")
        revoke_config = optimizer.get_optimized_config(account_count=30, operation_type="revoke")

        assert revoke_config.max_concurrent_accounts >= assign_config.max_concurrent_accounts
        assert revoke_config.rate_limit_delay <= assign_config.rate_limit_delay

    def test_performance_improvement_estimation(self, optimizer):
        """Test performance improvement estimation."""
        estimates = optimizer.estimate_performance_improvement(account_count=29)

        assert "current_estimated_time" in estimates
        assert "optimized_estimated_time" in estimates
        assert "improvement_ratio" in estimates
        assert "time_saved_seconds" in estimates
        assert "time_saved_percentage" in estimates

        # Should show significant improvement
        assert estimates["improvement_ratio"] > 1.5
        assert estimates["time_saved_percentage"] > 30

    def test_apply_optimizations(self, optimizer):
        """Test applying optimizations to a processor."""
        mock_processor = Mock()
        mock_processor.batch_size = 10
        mock_processor.max_concurrent_accounts = 10
        mock_processor.rate_limit_delay = 0.1

        optimizer.apply_optimizations(mock_processor, account_count=29, operation_type="assign")

        # Should have updated the processor settings
        assert mock_processor.batch_size > 10
        assert mock_processor.max_concurrent_accounts > 10
        assert mock_processor.rate_limit_delay < 0.1

    def test_create_performance_optimized_processor(self):
        """Test the factory function for creating optimized processors."""
        mock_aws_client = Mock()

        processor, config = create_performance_optimized_processor(
            aws_client_manager=mock_aws_client, account_count=29, operation_type="assign"
        )

        assert processor is not None
        assert isinstance(config, PerformanceConfig)
        assert config.max_concurrent_accounts > 10  # Should be optimized
        assert config.batch_size > 10  # Should be optimized


class TestPerformanceConfig:
    """Test cases for PerformanceConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PerformanceConfig()

        assert config.max_concurrent_accounts == 25
        assert config.batch_size == 50
        assert config.rate_limit_delay == 0.05
        assert config.account_timeout == 60
        assert config.max_retries == 2
        assert config.use_session_reuse is True

    def test_config_customization(self):
        """Test configuration customization."""
        config = PerformanceConfig(
            max_concurrent_accounts=35, batch_size=100, rate_limit_delay=0.01
        )

        assert config.max_concurrent_accounts == 35
        assert config.batch_size == 100
        assert config.rate_limit_delay == 0.01
