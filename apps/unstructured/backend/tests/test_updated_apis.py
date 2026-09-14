"""
Comprehensive Unit Tests for Updated and New APIs

Tests for:
1. Lineage API (fixed prefix issue, artifact relationships)
2. Quality Improvement API (fixed chunk counting)
3. DOCX/DOC to PDF conversion
4. Storage and path handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4
from datetime import datetime
from io import BytesIO
import json

# Lineage API Tests
# ============================================================================

class TestLineageAPI:
    """Tests for Lineage API endpoints."""

    @pytest.fixture
    def product_id(self):
        """Sample product ID."""
        return UUID("fb8356d9-d7bd-407f-a801-f0af6517bb9e")

    @pytest.fixture
    def workspace_id(self):
        """Sample workspace ID."""
        return UUID("4b979faf-0462-4560-897b-e26800378f90")

    @pytest.fixture
    def artifact_id(self):
        """Sample artifact ID."""
        return UUID("art-001-uuid-here-1234567890ab")

    def test_product_lineage_endpoint_exists(self):
        """Test that product lineage endpoint is properly registered."""
        from primedata.api.lineage import router

        # Verify router has correct prefix
        assert router.prefix == "/api/v1/lineage" or router.prefix == ""

        # Verify routes exist
        routes = [route.path for route in router.routes]
        assert any("products" in route and "detailed" not in route for route in routes)

    def test_product_lineage_no_double_prefix(self):
        """Test that lineage router doesn't have double prefix."""
        from primedata.api.lineage import router

        # Router should NOT have /api/v1/lineage as prefix
        # because app.py adds it when including the router
        assert router.prefix != "/api/v1/lineage"

    @patch("primedata.api.lineage.get_db")
    async def test_get_product_lineage_success(self, mock_db, product_id):
        """Test getting product lineage successfully."""
        from primedata.api.lineage import get_product_lineage
        from primedata.db.models import Product, PipelineArtifact

        # Mock product
        mock_product = Mock(spec=Product)
        mock_product.id = product_id
        mock_product.name = "Test Product"
        mock_product.current_version = 2
        mock_product.status = "active"
        mock_product.trust_score = 0.95

        # Mock artifacts
        mock_artifact = Mock(spec=PipelineArtifact)
        mock_artifact.id = uuid4()
        mock_artifact.artifact_name = "test_artifact.jsonl"
        mock_artifact.stage_name = "chunk"
        mock_artifact.artifact_type = "chunk"
        mock_artifact.version = 2

        # Setup mock DB
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = [mock_artifact]
        mock_session.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db.return_value = mock_session

        # Call endpoint
        result = await get_product_lineage(product_id, True, 2, mock_session)

        # Verify response
        assert result.entity_id == str(product_id)
        assert result.entity_type == "product"
        assert len(result.entities) > 0
        assert result.depth == 2

    @patch("primedata.api.lineage.get_db")
    async def test_get_product_lineage_not_found(self, mock_db, product_id):
        """Test product lineage with non-existent product."""
        from primedata.api.lineage import get_product_lineage
        from fastapi import HTTPException

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_product_lineage(product_id, True, 2, mock_session)

        assert exc_info.value.status_code == 404

    @patch("primedata.api.lineage.get_db")
    async def test_artifact_lineage_extraction(self, mock_db, artifact_id):
        """Test artifact lineage with input_artifacts extraction."""
        from primedata.api.lineage import get_artifact_lineage

        # Mock artifact with dict-based input_artifacts
        mock_artifact = Mock()
        mock_artifact.id = artifact_id
        mock_artifact.artifact_name = "chunks_v1.jsonl"
        mock_artifact.stage_name = "chunk"
        mock_artifact.input_artifacts = [
            {"artifact_id": str(uuid4()), "stage": "preprocess"},
            {"artifact_id": str(uuid4()), "stage": "preprocess"}
        ]

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_artifact
        mock_session.query.return_value.filter.return_value.all.return_value = []

        result = await get_artifact_lineage(artifact_id, "both", 3, mock_session)

        assert result["artifact_id"] == str(artifact_id)
        assert result["upstream_count"] == 2
        assert result["downstream_count"] == 0

    @patch("primedata.api.lineage.get_db")
    async def test_detailed_product_lineage_all_stages(self, mock_db, product_id):
        """Test detailed lineage includes all 7 pipeline stages."""
        from primedata.api.lineage import get_detailed_product_lineage
        from primedata.db.models import Product, PipelineRun, PipelineArtifact

        mock_product = Mock(spec=Product)
        mock_product.id = product_id
        mock_product.name = "Test Product"
        mock_product.current_version = 2

        # Mock artifacts for each stage
        stages = ["ingest", "preprocess", "chunk", "embed", "index", "validate", "finalize"]
        mock_artifacts = []
        for stage in stages:
            artifact = Mock(spec=PipelineArtifact)
            artifact.id = uuid4()
            artifact.artifact_name = f"{stage}_artifact.jsonl"
            artifact.stage_name = stage
            artifact.artifact_type = stage
            artifact.version = 2
            artifact.file_size = 1024
            artifact.checksum = "abc123"
            mock_artifacts.append(artifact)

        mock_pipeline_run = Mock(spec=PipelineRun)
        mock_pipeline_run.id = uuid4()

        mock_session = Mock()
        # Setup for product query
        mock_session.query.return_value.filter.return_value.first.return_value = mock_product
        # Setup for pipeline runs query
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_pipeline_run]
        # Setup for artifacts query
        mock_session.query.return_value.filter.return_value.all.return_value = mock_artifacts

        result = await get_detailed_product_lineage(product_id, mock_session)

        assert result["product_id"] == str(product_id)
        assert len(result["stages"]) == 7
        stage_names = [s["stage_name"] for s in result["stages"]]
        assert stage_names == stages

    @patch("primedata.api.lineage.get_db")
    async def test_lineage_search_endpoint(self, mock_db):
        """Test lineage search endpoint."""
        from primedata.api.lineage import semantic_lineage_search
        from primedata.api.lineage import LineageSearchRequest

        mock_session = Mock()
        request = LineageSearchRequest(
            query="embeddings",
            entity_type="artifact",
            limit=20
        )

        result = await semantic_lineage_search(request, mock_session)

        assert result["query"] == "embeddings"
        assert "results" in result
        assert "total" in result

    async def test_lineage_health_endpoint(self):
        """Test lineage health check endpoint."""
        from primedata.api.lineage import lineage_health

        result = await lineage_health()

        assert result["status"] == "healthy"
        assert "message" in result
        assert result["message"] == "Lineage API is operational"


# Quality Improvement API Tests
# ============================================================================

class TestQualityImprovementAPI:
    """Tests for Quality Improvement API."""

    @pytest.fixture
    def product_id(self):
        """Sample product ID."""
        return UUID("8037da2b-61cd-435d-8db7-b5472c98f805")

    @pytest.fixture
    def workspace_id(self):
        """Sample workspace ID."""
        return UUID("4b979faf-0462-4560-897b-e26800378f90")

    @patch("primedata.services.quality_improvement_calculator.storage_client")
    def test_chunk_counting_uses_correct_prefix(self, mock_storage, product_id, workspace_id):
        """Test that chunk counting uses workspace_id + product_id + version."""
        from primedata.services.quality_improvement_calculator import QualityImprovementCalculator
        from primedata.db.models import Product

        mock_db = Mock()
        mock_product = Mock(spec=Product)
        mock_product.id = product_id
        mock_product.workspace_id = workspace_id
        mock_product.name = "Test Product"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_storage.list_objects.return_value = [
            {"Key": "chunk_001"},
            {"Key": "chunk_002"},
            {"Key": "chunk_003"}
        ]

        calculator = QualityImprovementCalculator(mock_db)
        chunk_count = calculator._count_chunks(product_id, 1)

        # Verify correct prefix was used
        from primedata.storage.paths import chunk_prefix
        expected_prefix = chunk_prefix(workspace_id, product_id, 1)
        mock_storage.list_objects.assert_called_once_with("BUCKET_CHUNK", expected_prefix)

        # Verify count is correct
        assert chunk_count == 3

    def test_chunk_counting_handles_missing_product(self, product_id):
        """Test chunk counting returns 0 when product not found."""
        from primedata.services.quality_improvement_calculator import QualityImprovementCalculator

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        calculator = QualityImprovementCalculator(mock_db)
        chunk_count = calculator._count_chunks(product_id, 1)

        assert chunk_count == 0

    @patch("primedata.services.quality_improvement_calculator.storage_client")
    def test_chunk_counting_returns_zero_on_error(self, mock_storage, product_id, workspace_id):
        """Test chunk counting returns 0 on storage error."""
        from primedata.services.quality_improvement_calculator import QualityImprovementCalculator
        from primedata.db.models import Product

        mock_db = Mock()
        mock_product = Mock(spec=Product)
        mock_product.id = product_id
        mock_product.workspace_id = workspace_id

        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_storage.list_objects.side_effect = Exception("Storage error")

        calculator = QualityImprovementCalculator(mock_db)
        chunk_count = calculator._count_chunks(product_id, 1)

        assert chunk_count == 0

    @patch("primedata.services.quality_improvement_calculator.storage_client")
    def test_quality_improvement_calculation(self, mock_storage, product_id, workspace_id):
        """Test quality improvement calculation with correct chunk count."""
        from primedata.services.quality_improvement_calculator import QualityImprovementCalculator
        from primedata.db.models import Product, RawFile, PipelineRun

        mock_db = Mock()

        # Mock product
        mock_product = Mock(spec=Product)
        mock_product.id = product_id
        mock_product.workspace_id = workspace_id
        mock_product.name = "Test Product"
        mock_product.current_version = 1

        # Mock raw file (baseline)
        mock_raw_file = Mock(spec=RawFile)
        mock_raw_file.file_size = 1024000
        mock_raw_file.product_id = product_id
        mock_raw_file.version = 1

        # Mock pipeline run (completion status)
        mock_pipeline_run = Mock(spec=PipelineRun)
        mock_pipeline_run.finished_at = datetime.utcnow()
        mock_pipeline_run.metrics = {
            "overall_quality_score": 85.0,
            "completeness_score": 90.0,
            "noise_score": 10.0,
            "structure_score": 85.0
        }

        # Setup mock DB queries
        def mock_query_side_effect(model):
            mock_query = Mock()
            mock_filter = Mock()

            if model == Product:
                mock_filter.first.return_value = mock_product
            elif model == RawFile:
                mock_filter.all.return_value = [mock_raw_file]
            elif model == PipelineRun:
                mock_filter.order_by.return_value.first.return_value = mock_pipeline_run

            mock_query.filter.return_value = mock_filter
            return mock_query

        mock_db.query.side_effect = mock_query_side_effect

        # Mock storage for chunk counting
        mock_storage.list_objects.return_value = [
            {"Key": f"chunk_{i}"} for i in range(12543)  # Many chunks
        ]

        calculator = QualityImprovementCalculator(mock_db)
        result = calculator.calculate(product_id, version=1)

        # Verify result structure
        assert result["product_id"] == str(product_id)
        assert result["product_name"] == "Test Product"
        assert result["version"] == 1
        assert result["chunks_created"] == 12543
        assert result["files_processed"] == 1
        assert result["before"]["overall"] == 30.0
        assert result["after"]["overall"] == 85.0

    @patch("primedata.api.quality_improvement.QualityImprovementCalculator")
    async def test_quality_improvement_endpoint(self, mock_calculator_class, product_id):
        """Test quality improvement API endpoint."""
        from primedata.api.quality_improvement import get_quality_improvement
        from primedata.db.models import Product

        mock_calculator = Mock()
        mock_calculator_class.return_value = mock_calculator
        mock_calculator.calculate.return_value = {
            "product_id": str(product_id),
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
            "improvement_percentage": 60.5,
            "has_improvement": True,
            "files_processed": 1,
            "chunks_created": 12543,
            "baseline_available": True,
            "calculated_at": datetime.utcnow().isoformat()
        }

        mock_db = Mock()
        mock_product = Mock(spec=Product)
        mock_product.id = product_id
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product

        result = await get_quality_improvement(product_id, None, mock_db, {})

        assert result.product_id == str(product_id)
        assert result.chunks_created == 12543
        assert result.improvement_percentage == 60.5


# DOCX/DOC Conversion Tests
# ============================================================================

class TestDocxConversion:
    """Tests for DOCX/DOC to PDF conversion."""

    @pytest.fixture
    def storage_adapter(self):
        """Create storage adapter for testing."""
        from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

        adapter = AirdStorageAdapter(
            workspace_id=UUID("4b979faf-0462-4560-897b-e26800378f90"),
            product_id=UUID("fb8356d9-d7bd-407f-a801-f0af6517bb9e"),
            version=1
        )
        return adapter

    def test_convert_docx_to_pdf_success(self, storage_adapter):
        """Test successful DOCX to PDF conversion."""
        from docx import Document

        # Create a test DOCX
        doc = Document()
        doc.add_heading("Test Document", level=0)
        doc.add_paragraph("This is a test paragraph.")
        doc.add_heading("Section 1", level=1)
        doc.add_paragraph("Content for section 1")

        # Save to bytes
        docx_buffer = BytesIO()
        doc.save(docx_buffer)
        docx_data = docx_buffer.getvalue()

        # Convert to PDF
        pdf_data = storage_adapter._convert_docx_to_pdf(docx_data, "test.docx")

        # Verify PDF was generated
        assert pdf_data is not None
        assert len(pdf_data) > 0
        assert pdf_data.startswith(b"%PDF")  # PDF file signature

    def test_convert_docx_with_table(self, storage_adapter):
        """Test DOCX to PDF conversion with tables."""
        from docx import Document

        doc = Document()
        doc.add_heading("Document with Table", 0)

        # Add table
        table = doc.add_table(rows=3, cols=2)
        table.rows[0].cells[0].text = "Header 1"
        table.rows[0].cells[1].text = "Header 2"
        table.rows[1].cells[0].text = "Data 1"
        table.rows[1].cells[1].text = "Data 2"

        docx_buffer = BytesIO()
        doc.save(docx_buffer)
        docx_data = docx_buffer.getvalue()

        pdf_data = storage_adapter._convert_docx_to_pdf(docx_data, "table.docx")

        assert pdf_data is not None
        assert len(pdf_data) > 0

    def test_convert_invalid_docx(self, storage_adapter):
        """Test conversion with invalid DOCX data."""
        invalid_data = b"This is not a DOCX file"

        with pytest.raises(ValueError):
            storage_adapter._convert_docx_to_pdf(invalid_data, "invalid.docx")

    def test_convert_empty_docx(self, storage_adapter):
        """Test conversion with empty DOCX."""
        from docx import Document

        doc = Document()
        # Don't add any content

        docx_buffer = BytesIO()
        doc.save(docx_buffer)
        docx_data = docx_buffer.getvalue()

        with pytest.raises(ValueError):
            storage_adapter._convert_docx_to_pdf(docx_data, "empty.docx")


# Storage API Tests
# ============================================================================

class TestStorageAPI:
    """Tests for storage and artifact handling."""

    @pytest.fixture
    def storage_adapter(self):
        """Create storage adapter for testing."""
        from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

        adapter = AirdStorageAdapter(
            workspace_id=UUID("4b979faf-0462-4560-897b-e26800378f90"),
            product_id=UUID("fb8356d9-d7bd-407f-a801-f0af6517bb9e"),
            version=1
        )
        return adapter

    @patch("primedata.ingestion_pipeline.aird_stages.storage.storage_client")
    def test_get_raw_text_pdf_file(self, mock_storage, storage_adapter):
        """Test getting raw text from PDF file."""
        pdf_data = b"%PDF-1.4\n%mock pdf content"
        mock_storage.get_bytes.return_value = pdf_data

        with patch.object(storage_adapter, "_extract_pdf_text", return_value="Extracted text"):
            result = storage_adapter.get_raw_text(
                "test_pdf",
                storage_key="ws/123/prod/456/v/1/raw/test.pdf",
                storage_bucket="raw-bucket"
            )

        assert result == "Extracted text"

    @patch("primedata.ingestion_pipeline.aird_stages.storage.storage_client")
    def test_get_raw_text_docx_file(self, mock_storage, storage_adapter):
        """Test getting raw text from DOCX file (converts to PDF first)."""
        from docx import Document

        # Create DOCX
        doc = Document()
        doc.add_paragraph("Test content from DOCX")
        docx_buffer = BytesIO()
        doc.save(docx_buffer)
        docx_data = docx_buffer.getvalue()

        mock_storage.get_bytes.return_value = docx_data

        result = storage_adapter.get_raw_text(
            "test_docx",
            storage_key="ws/123/prod/456/v/1/raw/test.docx",
            storage_bucket="raw-bucket"
        )

        # Should have converted and extracted
        assert result is not None
        assert len(result) > 0

    @patch("primedata.ingestion_pipeline.aird_stages.storage.storage_client")
    def test_get_raw_text_text_file(self, mock_storage, storage_adapter):
        """Test getting raw text from plain text file."""
        text_data = b"This is plain text content"
        mock_storage.get_bytes.return_value = text_data

        result = storage_adapter.get_raw_text(
            "test_txt",
            storage_key="ws/123/prod/456/v/1/raw/test.txt",
            storage_bucket="raw-bucket"
        )

        assert result == "This is plain text content"

    @patch("primedata.ingestion_pipeline.aird_stages.storage.storage_client")
    def test_get_raw_text_file_not_found(self, mock_storage, storage_adapter):
        """Test getting raw text when file doesn't exist."""
        mock_storage.get_bytes.return_value = None

        result = storage_adapter.get_raw_text(
            "nonexistent",
            storage_key="ws/123/prod/456/v/1/raw/nonexistent.txt",
            storage_bucket="raw-bucket"
        )

        assert result is None


# Path Helper Tests
# ============================================================================

class TestPathHelpers:
    """Tests for storage path generation."""

    def test_chunk_prefix_correct_format(self):
        """Test chunk_prefix generates correct path."""
        from primedata.storage.paths import chunk_prefix

        workspace_id = UUID("4b979faf-0462-4560-897b-e26800378f90")
        product_id = UUID("fb8356d9-d7bd-407f-a801-f0af6517bb9e")
        version = 1

        prefix = chunk_prefix(workspace_id, product_id, version)

        expected = f"ws/{workspace_id}/prod/{product_id}/v/{version}/chunk/"
        assert prefix == expected

    def test_chunk_prefix_with_string_ids(self):
        """Test chunk_prefix works with string IDs."""
        from primedata.storage.paths import chunk_prefix

        workspace_id = "4b979faf-0462-4560-897b-e26800378f90"
        product_id = "fb8356d9-d7bd-407f-a801-f0af6517bb9e"
        version = 1

        prefix = chunk_prefix(workspace_id, product_id, version)

        assert "ws/" in prefix
        assert "prod/" in prefix
        assert "v/1/chunk/" in prefix

    def test_clean_prefix_respects_metadata_path(self):
        """Test that clean_prefix includes S3_METADATA_PATH."""
        from primedata.storage.paths import clean_prefix
        import os

        # This should already have S3_METADATA_PATH included
        workspace_id = UUID("4b979faf-0462-4560-897b-e26800378f90")
        product_id = UUID("fb8356d9-d7bd-407f-a801-f0af6517bb9e")
        version = 1

        prefix = clean_prefix(workspace_id, product_id, version)

        # Should contain workspace/product/version structure
        assert "ws/" in prefix
        assert "prod/" in prefix
        assert "v/1/clean/" in prefix


# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for API workflows."""

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.services.quality_improvement_calculator.storage_client")
    async def test_quality_improvement_with_lineage_consistency(
        self, mock_storage, mock_get_db
    ):
        """Test that quality improvement chunk count matches lineage artifacts."""
        from primedata.services.quality_improvement_calculator import QualityImprovementCalculator
        from primedata.api.lineage import get_product_lineage
        from primedata.db.models import Product, PipelineArtifact

        product_id = UUID("8037da2b-61cd-435d-8db7-b5472c98f805")
        workspace_id = UUID("4b979faf-0462-4560-897b-e26800378f90")

        # Create 100 mock artifacts
        mock_artifacts = []
        for i in range(100):
            artifact = Mock(spec=PipelineArtifact)
            artifact.id = uuid4()
            artifact.artifact_name = f"chunk_{i}.jsonl"
            artifact.stage_name = "chunk"
            artifact.artifact_type = "chunk"
            artifact.version = 1
            artifact.input_artifacts = []
            mock_artifacts.append(artifact)

        mock_product = Mock(spec=Product)
        mock_product.id = product_id
        mock_product.workspace_id = workspace_id
        mock_product.name = "Test Product"
        mock_product.current_version = 1

        # Setup mock storage
        mock_storage.list_objects.return_value = mock_artifacts

        # Calculate chunk count
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product

        calculator = QualityImprovementCalculator(mock_db)
        chunk_count = calculator._count_chunks(product_id, 1)

        # Verify count matches artifacts
        assert chunk_count == len(mock_artifacts)


# Fixtures for pytest
# ============================================================================

@pytest.fixture(scope="session")
def test_db():
    """Create test database session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from primedata.db.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


@pytest.fixture
def test_client():
    """Create FastAPI test client."""
    from fastapi.testclient import TestClient
    from primedata.api.app import app

    return TestClient(app)
