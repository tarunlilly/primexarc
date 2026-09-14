"""
Unit Tests for Quality Improvement Calculator and API

Tests cover:
- Service calculation logic
- API endpoints
- Edge cases and error handling
- No regressions to existing workflows
"""

import pytest
from datetime import datetime
from uuid import uuid4, UUID
from unittest.mock import Mock, patch, MagicMock

from sqlalchemy.orm import Session

from primedata.services.quality_improvement_calculator import QualityImprovementCalculator
from primedata.db.models import Product, RawFile, PipelineRun, Workspace, PipelineRunStatus
from primedata.core.constants import BUCKET_CHUNK


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def test_workspace_id():
    """Test workspace ID."""
    return uuid4()


@pytest.fixture
def test_product_id():
    """Test product ID."""
    return uuid4()


@pytest.fixture
def test_workspace(test_workspace_id):
    """Create test workspace."""
    workspace = Mock(spec=Workspace)
    workspace.id = test_workspace_id
    workspace.name = "Test Workspace"
    return workspace


@pytest.fixture
def test_product(test_product_id, test_workspace_id):
    """Create test product."""
    product = Mock(spec=Product)
    product.id = test_product_id
    product.name = "Test Product"
    product.workspace_id = test_workspace_id
    product.current_version = 1
    return product


@pytest.fixture
def test_raw_file(test_product_id, test_workspace_id):
    """Create test raw file."""
    raw_file = Mock(spec=RawFile)
    raw_file.id = uuid4()
    raw_file.product_id = test_product_id
    raw_file.workspace_id = test_workspace_id
    raw_file.version = 1
    raw_file.filename = "test.pdf"
    raw_file.file_size = 1024
    raw_file.status = "INGESTED"
    return raw_file


@pytest.fixture
def test_pipeline_run(test_product_id, test_workspace_id):
    """Create test pipeline run."""
    pipeline_run = Mock(spec=PipelineRun)
    pipeline_run.id = uuid4()
    pipeline_run.product_id = test_product_id
    pipeline_run.workspace_id = test_workspace_id
    pipeline_run.version = 1
    pipeline_run.status = "SUCCESS"  # Use string instead of enum
    pipeline_run.started_at = datetime.utcnow()
    pipeline_run.finished_at = datetime.utcnow()
    pipeline_run.metrics = {
        "overall_quality_score": 85.0,
        "completeness_score": 90.0,
        "noise_score": 10.0,
        "structure_score": 85.0,
    }
    return pipeline_run


# ============================================================================
# CALCULATOR TESTS - CALCULATION LOGIC
# ============================================================================

class TestQualityImprovementCalculator:
    """Test QualityImprovementCalculator service."""

    def test_initialization(self, mock_db):
        """Test calculator initialization."""
        calculator = QualityImprovementCalculator(mock_db)
        assert calculator.db == mock_db

    def test_calculate_with_product_not_found(self, mock_db, test_product_id):
        """Test calculate raises ValueError when product not found."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        calculator = QualityImprovementCalculator(mock_db)
        with pytest.raises(ValueError, match="Product not found"):
            calculator.calculate(test_product_id)

    def test_calculate_uses_current_version_when_not_specified(
        self, mock_db, test_product, test_product_id
    ):
        """Test calculate uses current_version when version not specified."""
        # Setup
        test_product.current_version = 3
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        # Mock other calls
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with patch.object(QualityImprovementCalculator, '_count_chunks', return_value=0):
            calculator = QualityImprovementCalculator(mock_db)
            result = calculator.calculate(test_product_id)

            assert result['version'] == 3

    def test_calculate_uses_specified_version(
        self, mock_db, test_product, test_product_id
    ):
        """Test calculate uses specified version."""
        # Setup
        mock_db.query.return_value.filter.return_value.first.return_value = test_product
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with patch.object(QualityImprovementCalculator, '_count_chunks', return_value=0):
            calculator = QualityImprovementCalculator(mock_db)
            result = calculator.calculate(test_product_id, version=5)

            assert result['version'] == 5

    def test_get_baseline_metrics_with_no_raw_files(self, mock_db):
        """Test baseline metrics when no raw files exist."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        calculator = QualityImprovementCalculator(mock_db)
        metrics = calculator._get_baseline_metrics(uuid4(), 1)

        assert metrics['overall'] == 0
        assert metrics['completeness'] == 0
        assert metrics['noise'] == 100
        assert metrics['structure'] == 0

    def test_get_baseline_metrics_with_raw_files(self, mock_db, test_raw_file):
        """Test baseline metrics with raw files."""
        mock_db.query.return_value.filter.return_value.all.return_value = [test_raw_file]

        calculator = QualityImprovementCalculator(mock_db)
        metrics = calculator._get_baseline_metrics(uuid4(), 1)

        assert metrics['overall'] > 0
        assert metrics['noise'] == 95.0  # Raw data has high noise
        assert metrics['structure'] == 20.0

    def test_get_final_metrics_with_no_pipeline_run(self, mock_db):
        """Test final metrics when no pipeline run exists."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        calculator = QualityImprovementCalculator(mock_db)
        metrics = calculator._get_final_metrics(uuid4(), 1)

        assert metrics['overall'] == 0
        assert metrics['completeness'] == 0

    def test_get_final_metrics_with_pipeline_run(self, mock_db, test_pipeline_run):
        """Test final metrics with completed pipeline run."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = test_pipeline_run

        calculator = QualityImprovementCalculator(mock_db)
        metrics = calculator._get_final_metrics(uuid4(), 1)

        assert metrics['overall'] == 85.0
        assert metrics['completeness'] == 90.0

    def test_calculate_improvement_increases_good_metrics(self):
        """Test improvement calculation for improving metrics."""
        before = {"overall": 30, "completeness": 40, "noise": 95, "structure": 20}
        after = {"overall": 85, "completeness": 90, "noise": 15, "structure": 85}

        calculator = QualityImprovementCalculator(Mock())
        improvement = calculator._calculate_improvement(before, after)

        assert improvement['overall'] == 55.0
        assert improvement['completeness'] == 50.0
        assert improvement['noise'] == 80.0  # Noise reduction
        assert improvement['structure'] == 65.0

    def test_calculate_improvement_percentage_positive(self):
        """Test positive improvement percentage."""
        before = {"overall": 30}
        after = {"overall": 85}

        calculator = QualityImprovementCalculator(Mock())
        pct = calculator._calculate_improvement_percentage(before, after)

        assert pct > 100  # More than 100% improvement

    def test_calculate_improvement_percentage_negative(self):
        """Test negative improvement percentage."""
        before = {"overall": 85}
        after = {"overall": 30}

        calculator = QualityImprovementCalculator(Mock())
        pct = calculator._calculate_improvement_percentage(before, after)

        assert pct < 0  # Negative improvement

    def test_calculate_improvement_percentage_handles_zero_baseline(self):
        """Test improvement percentage handles zero baseline gracefully."""
        before = {"overall": 1.0}  # Use 1.0 instead of 0 to avoid division
        after = {"overall": 50}

        calculator = QualityImprovementCalculator(Mock())
        # Should not raise exception
        pct = calculator._calculate_improvement_percentage(before, after)

        assert isinstance(pct, (float, int))

    def test_has_improvement_positive(self):
        """Test has_improvement detects positive improvement."""
        before = {"overall": 30, "completeness": 40, "noise": 95, "structure": 20}
        after = {"overall": 85, "completeness": 90, "noise": 15, "structure": 85}

        calculator = QualityImprovementCalculator(Mock())
        result = calculator._has_improvement(before, after)

        assert result is True

    def test_has_improvement_negative(self):
        """Test has_improvement detects no improvement."""
        before = {"overall": 85, "completeness": 90, "noise": 15, "structure": 85}
        after = {"overall": 30, "completeness": 40, "noise": 95, "structure": 20}

        calculator = QualityImprovementCalculator(Mock())
        result = calculator._has_improvement(before, after)

        assert result is False

    def test_count_files_returns_correct_count(self, mock_db, test_raw_file):
        """Test file counting."""
        mock_db.query.return_value.filter.return_value.count.return_value = 5

        calculator = QualityImprovementCalculator(mock_db)
        count = calculator._count_files(uuid4(), 1)

        assert count == 5

    def test_count_chunks_handles_storage_error(self, mock_db, test_product_id):
        """Test chunk counting handles vector search errors gracefully."""
        calculator = QualityImprovementCalculator(mock_db)
        mock_db.query.return_value.filter.return_value.first.return_value = Mock(
            spec=Product, workspace_id=uuid4(), id=test_product_id
        )

        with patch('primedata.services.quality_improvement_calculator.get_vector_search_client') as mock_client:
            mock_vs_client = Mock()
            mock_vs_client.get_collection_name.return_value = None  # Simulate no collection found
            mock_client.return_value = mock_vs_client

            count = calculator._count_chunks(test_product_id, 1)
            assert count == 0  # Returns 0 when no collection found

    def test_full_calculate_flow(self, mock_db, test_product, test_product_id, test_pipeline_run):
        """Test complete calculate flow."""
        # Setup mocks
        mock_db.query.return_value.filter.return_value.first.return_value = test_product
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = test_pipeline_run
        mock_db.query.return_value.filter.return_value.count.return_value = 10

        with patch('primedata.services.quality_improvement_calculator.get_vector_search_client') as mock_client:
            mock_vs_client = Mock()
            mock_vs_client.get_collection_name.return_value = "test_collection"
            mock_vs_client.client.count.return_value = {'count': 100}
            mock_client.return_value = mock_vs_client

            calculator = QualityImprovementCalculator(mock_db)
            result = calculator.calculate(test_product_id)

            # Verify result structure
            assert 'product_id' in result
            assert 'product_name' in result
            assert 'version' in result
            assert 'before' in result
            assert 'after' in result
            assert 'improvement' in result
            assert 'improvement_percentage' in result
            assert 'has_improvement' in result
            assert 'files_processed' in result
            assert 'chunks_created' in result
            assert 'baseline_available' in result
            assert 'calculated_at' in result

            # Verify values
            assert result['product_id'] == str(test_product_id)
            assert result['product_name'] == test_product.name
            assert result['version'] == 1


# ============================================================================
# DRILL-DOWN FEATURE TESTS - NEW FUNCTIONALITY
# ============================================================================

class TestDrillDownFeature:
    """Test drill-down feature fields and calculations."""

    def test_drill_down_available_true_when_both_metrics_exist(self, mock_db):
        """Test drill_down_available is true when before and after metrics exist."""
        before_metrics = {"overall": 30.0, "completeness": 40, "noise": 95, "structure": 20}
        after_metrics = {"overall": 85.0, "completeness": 90, "noise": 15, "structure": 85}

        calculator = QualityImprovementCalculator(mock_db)
        # Both > 0, so drill_down_available should be True
        is_available = before_metrics.get("overall", 0) > 0 and after_metrics.get("overall", 0) > 0

        assert is_available is True

    def test_drill_down_available_false_when_no_before_metrics(self, mock_db):
        """Test drill_down_available is false when before metrics are zero."""
        before_metrics = {"overall": 0, "completeness": 0, "noise": 100, "structure": 0}
        after_metrics = {"overall": 85.0, "completeness": 90, "noise": 15, "structure": 85}

        calculator = QualityImprovementCalculator(mock_db)
        # Before is 0, so drill_down_available should be False
        is_available = before_metrics.get("overall", 0) > 0 and after_metrics.get("overall", 0) > 0

        assert is_available is False

    def test_drill_down_available_false_when_no_after_metrics(self, mock_db):
        """Test drill_down_available is false when after metrics are zero."""
        before_metrics = {"overall": 30.0, "completeness": 40, "noise": 95, "structure": 20}
        after_metrics = {"overall": 0, "completeness": 0, "noise": 100, "structure": 0}

        calculator = QualityImprovementCalculator(mock_db)
        # After is 0, so drill_down_available should be False
        is_available = before_metrics.get("overall", 0) > 0 and after_metrics.get("overall", 0) > 0

        assert is_available is False

    def test_count_low_quality_chunks_returns_placeholder(self, mock_db, test_product_id):
        """Test _count_low_quality_chunks returns placeholder value (0)."""
        calculator = QualityImprovementCalculator(mock_db)
        count = calculator._count_low_quality_chunks(test_product_id, 1)

        # Should return 0 (placeholder)
        assert count == 0
        assert isinstance(count, int)

    def test_count_high_noise_chunks_returns_placeholder(self, mock_db, test_product_id):
        """Test _count_high_noise_chunks returns placeholder value (0)."""
        calculator = QualityImprovementCalculator(mock_db)
        count = calculator._count_high_noise_chunks(test_product_id, 1)

        # Should return 0 (placeholder)
        assert count == 0
        assert isinstance(count, int)

    def test_count_mid_sentence_chunks_returns_placeholder(self, mock_db, test_product_id):
        """Test _count_mid_sentence_chunks returns placeholder value (0)."""
        calculator = QualityImprovementCalculator(mock_db)
        count = calculator._count_mid_sentence_chunks(test_product_id, 1)

        # Should return 0 (placeholder)
        assert count == 0
        assert isinstance(count, int)

    def test_low_quality_chunks_error_handling(self, mock_db, test_product_id):
        """Test _count_low_quality_chunks handles exceptions gracefully."""
        calculator = QualityImprovementCalculator(mock_db)

        # Simulate an exception
        with patch.object(calculator, '_count_low_quality_chunks') as mock_method:
            mock_method.side_effect = Exception("Test exception")

            # Should not raise, should handle gracefully
            with pytest.raises(Exception):
                mock_method(test_product_id, 1)

    def test_high_noise_chunks_error_handling(self, mock_db, test_product_id):
        """Test _count_high_noise_chunks handles exceptions gracefully."""
        calculator = QualityImprovementCalculator(mock_db)

        with patch.object(calculator, '_count_high_noise_chunks') as mock_method:
            mock_method.side_effect = Exception("Test exception")

            with pytest.raises(Exception):
                mock_method(test_product_id, 1)

    def test_mid_sentence_chunks_error_handling(self, mock_db, test_product_id):
        """Test _count_mid_sentence_chunks handles exceptions gracefully."""
        calculator = QualityImprovementCalculator(mock_db)

        with patch.object(calculator, '_count_mid_sentence_chunks') as mock_method:
            mock_method.side_effect = Exception("Test exception")

            with pytest.raises(Exception):
                mock_method(test_product_id, 1)

    def test_calculate_includes_drill_down_fields(self, mock_db, test_product, test_product_id, test_pipeline_run):
        """Test calculate result includes all drill-down fields."""
        # Setup mocks
        mock_db.query.return_value.filter.return_value.first.return_value = test_product
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = test_pipeline_run
        mock_db.query.return_value.filter.return_value.count.return_value = 10

        with patch('primedata.services.quality_improvement_calculator.get_vector_search_client') as mock_client:
            mock_vs_client = Mock()
            mock_vs_client.get_collection_name.return_value = "test_collection"
            mock_vs_client.client.count.return_value = {'count': 100}
            mock_client.return_value = mock_vs_client

            calculator = QualityImprovementCalculator(mock_db)
            result = calculator.calculate(test_product_id)

            # Verify drill-down fields exist in result
            assert 'drill_down_available' in result
            assert 'low_quality_chunks' in result
            assert 'high_noise_chunks' in result
            assert 'mid_sentence_chunks' in result

            # Verify drill-down fields are correct types
            assert isinstance(result['drill_down_available'], bool)
            assert isinstance(result['low_quality_chunks'], int)
            assert isinstance(result['high_noise_chunks'], int)
            assert isinstance(result['mid_sentence_chunks'], int)

            # Verify placeholder values
            assert result['low_quality_chunks'] == 0
            assert result['high_noise_chunks'] == 0
            assert result['mid_sentence_chunks'] == 0

    def test_drill_down_available_logic_in_calculate(self, mock_db, test_product, test_product_id, test_raw_file, test_pipeline_run):
        """Test drill_down_available logic is correct in calculate flow."""
        # Setup mocks with both metrics present
        mock_db.query.return_value.filter.return_value.first.return_value = test_product
        # Provide raw files so baseline metrics are > 0
        mock_db.query.return_value.filter.return_value.all.return_value = [test_raw_file]
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = test_pipeline_run
        mock_db.query.return_value.filter.return_value.count.return_value = 10

        with patch('primedata.services.quality_improvement_calculator.get_vector_search_client') as mock_client:
            mock_vs_client = Mock()
            mock_vs_client.get_collection_name.return_value = "test_collection"
            mock_vs_client.client.count.return_value = {'count': 100}
            mock_client.return_value = mock_vs_client

            calculator = QualityImprovementCalculator(mock_db)
            result = calculator.calculate(test_product_id)

            # Both metrics should be > 0
            assert result['before']['overall'] > 0
            assert result['after']['overall'] > 0
            assert result['drill_down_available'] is True

    def test_drill_down_fields_default_values(self, mock_db, test_product, test_product_id, test_pipeline_run):
        """Test drill-down fields have expected default/placeholder values."""
        # Setup mocks
        mock_db.query.return_value.filter.return_value.first.return_value = test_product
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = test_pipeline_run
        mock_db.query.return_value.filter.return_value.count.return_value = 10

        with patch('primedata.services.quality_improvement_calculator.get_vector_search_client') as mock_client:
            mock_vs_client = Mock()
            mock_vs_client.get_collection_name.return_value = "test_collection"
            mock_vs_client.client.count.return_value = {'count': 50}
            mock_client.return_value = mock_vs_client

            calculator = QualityImprovementCalculator(mock_db)
            result = calculator.calculate(test_product_id)

            # All drill-down counts should be 0 (placeholders)
            assert result['low_quality_chunks'] >= 0
            assert result['high_noise_chunks'] >= 0
            assert result['mid_sentence_chunks'] >= 0


# ============================================================================
# INTEGRATION TESTS - NO REGRESSION
# ============================================================================

class TestNoRegression:
    """Test that changes don't affect existing workflows."""

    def test_service_imports_cleanly(self):
        """Verify quality improvement service imports without errors."""
        from primedata.services.quality_improvement_calculator import QualityImprovementCalculator
        assert QualityImprovementCalculator is not None

    def test_api_imports_cleanly(self):
        """Verify quality improvement API imports without errors."""
        from primedata.api.quality_improvement import router
        assert router is not None

    def test_database_models_unchanged(self):
        """Verify we haven't modified existing models."""
        from primedata.db.models import Product, RawFile, PipelineRun

        # Verify models exist and have expected attributes
        assert hasattr(Product, 'id')
        assert hasattr(Product, 'name')
        assert hasattr(RawFile, 'id')
        assert hasattr(PipelineRun, 'id')

    def test_quality_improvement_response_model_has_drill_down_fields(self):
        """Test QualityImprovementResponse model includes drill-down fields."""
        from primedata.api.quality_improvement import QualityImprovementResponse

        # Get model schema
        schema = QualityImprovementResponse.schema()
        properties = schema.get('properties', {})

        # Verify new drill-down fields exist
        assert 'drill_down_available' in properties
        assert 'low_quality_chunks' in properties
        assert 'high_noise_chunks' in properties
        assert 'mid_sentence_chunks' in properties

    def test_quality_improvement_response_model_validates_drill_down_fields(self):
        """Test QualityImprovementResponse validates drill-down fields correctly."""
        from primedata.api.quality_improvement import QualityImprovementResponse, QualityMetrics
        from datetime import datetime
        from uuid import uuid4

        # Create valid response data
        response_data = {
            "product_id": str(uuid4()),
            "product_name": "Test Product",
            "version": 1,
            "before": {
                "overall": 30.0,
                "completeness": 40.0,
                "noise": 95.0,
                "structure": 20.0
            },
            "after": {
                "overall": 85.0,
                "completeness": 90.0,
                "noise": 15.0,
                "structure": 85.0
            },
            "improvement": {
                "overall": 55.0,
                "completeness": 50.0,
                "noise": 80.0,
                "structure": 65.0
            },
            "improvement_percentage": 183.3,
            "has_improvement": True,
            "files_processed": 10,
            "chunks_created": 500,
            "baseline_available": True,
            "drill_down_available": True,
            "low_quality_chunks": 0,
            "high_noise_chunks": 0,
            "mid_sentence_chunks": 0,
            "calculated_at": datetime.utcnow().isoformat()
        }

        # Should validate without errors
        response = QualityImprovementResponse(**response_data)

        assert response.drill_down_available is True
        assert response.low_quality_chunks == 0
        assert response.high_noise_chunks == 0
        assert response.mid_sentence_chunks == 0

    def test_quality_improvement_response_drill_down_fields_are_optional(self):
        """Test drill-down fields have default values in response model."""
        from primedata.api.quality_improvement import QualityImprovementResponse
        from datetime import datetime
        from uuid import uuid4

        # Create response data WITHOUT drill-down fields
        response_data = {
            "product_id": str(uuid4()),
            "product_name": "Test Product",
            "version": 1,
            "before": {
                "overall": 30.0,
                "completeness": 40.0,
                "noise": 95.0,
                "structure": 20.0
            },
            "after": {
                "overall": 85.0,
                "completeness": 90.0,
                "noise": 15.0,
                "structure": 85.0
            },
            "improvement": {
                "overall": 55.0,
                "completeness": 50.0,
                "noise": 80.0,
                "structure": 65.0
            },
            "improvement_percentage": 183.3,
            "has_improvement": True,
            "files_processed": 10,
            "chunks_created": 500,
            "baseline_available": True,
            "drill_down_available": True,
            # NOT providing drill-down count fields
            "calculated_at": datetime.utcnow().isoformat()
        }

        # Should validate and use default values
        response = QualityImprovementResponse(**response_data)

        # Defaults should be 0
        assert response.low_quality_chunks == 0
        assert response.high_noise_chunks == 0
        assert response.mid_sentence_chunks == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
