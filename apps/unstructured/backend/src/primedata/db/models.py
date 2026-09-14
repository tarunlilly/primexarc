"""
Database models for PrimeData.

This file contains placeholder models that will be expanded as the application grows.
"""

import os
import uuid
from enum import Enum

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

from primedata.db.database import Base
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Get PostgreSQL schema from environment variable
POSTGRES_SCHEMA = os.getenv("POSTGRES_SCHEMA", "public")
logger.info(f"🔧 Database Schema Configuration: POSTGRES_SCHEMA={POSTGRES_SCHEMA}")


class AuthProvider(str, Enum):
    """Authentication provider enum."""

    GOOGLE = "google"
    SIMPLE = "simple"
    NONE = "none"
    BOUNCER = "bouncer"


class WorkspaceRole(str, Enum):
    """Workspace role enum."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class ProductStatus(str, Enum):
    """Product status enum."""

    DRAFT = "draft"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"
    FAILED_POLICY = "failed_policy"  # M2: Policy evaluation failed
    READY_WITH_WARNINGS = "ready_with_warnings"  # M2: Policy passed but with warnings


class DataSourceType(str, Enum):
    """Data source type enum."""

    WEB = "WEB"
    DB = "DB"
    CONFLUENCE = "CONFLUENCE"
    SHAREPOINT = "SHAREPOINT"
    FOLDER = "FOLDER"
    AWS_S3 = "AWS_S3"
    AZURE_BLOB = "AZURE_BLOB"


class BillingPlan(str, Enum):
    """Billing plan enum."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PipelineRunStatus(str, Enum):
    """Pipeline run status enum."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    READY_WITH_WARNINGS = "ready_with_warnings"  # M0: Pipeline completed with warnings
    FAILED_POLICY = "failed_policy"  # M0: Pipeline failed policy evaluation


class PolicyStatus(str, Enum):
    """Policy evaluation status enum (M2)."""

    PASSED = "passed"
    FAILED = "failed"
    WARNINGS = "warnings"
    UNKNOWN = "unknown"


class RawFileStatus(str, Enum):
    """Raw file processing status enum."""

    INGESTED = "ingested"  # File uploaded to object storage and recorded in DB
    PROCESSING = "processing"  # Currently being processed by pipeline
    PROCESSED = "processed"  # Successfully processed by pipeline
    FAILED = "failed"  # Processing failed
    DELETED = "deleted"  # Soft deleted


class ArtifactType(str, Enum):
    """Pipeline artifact type enum."""

    JSONL = "jsonl"  # Processed chunks
    JSON = "json"  # Metrics, fingerprint, etc.
    CSV = "csv"  # Validation summaries
    PDF = "pdf"  # Trust reports
    VECTOR = "vector"  # Qdrant vectors
    TEXT = "text"  # Plain text files
    BINARY = "binary"  # Other binary files


class ArtifactStatus(str, Enum):
    """Artifact status enum for lifecycle management."""

    ACTIVE = "active"  # Currently in use
    ARCHIVED = "archived"  # Moved to cold storage
    DELETED = "deleted"  # Soft deleted
    PURGED = "purged"  # Hard deleted (after retention period)


class RetentionPolicy(str, Enum):
    """Artifact retention policy enum."""

    KEEP_FOREVER = "keep_forever"  # Never delete (production artifacts)
    DAYS_30 = "30_days"  # Keep for 30 days
    DAYS_90 = "90_days"  # Keep for 90 days
    DAYS_365 = "365_days"  # Keep for 1 year
    DELETE_ON_PROMOTE = "delete_on_promote"  # Delete when product is promoted
    ON_FAILURE_KEEP_90 = "on_failure_keep_90"  # Keep failed runs for 90 days


class ACLAccessType(str, Enum):
    """ACL access type enum (M5)."""

    FULL = "full"
    INDEX = "index"
    DOCUMENT = "document"
    FIELD = "field"


class User(Base):
    """User model."""

    __tablename__ = "users"

    id = Column(String(255), primary_key=True, index=True)  # Support any user ID format (UUID, string, etc.)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    timezone = Column(String(50), nullable=True, default="UTC")
    picture_url = Column(String(500), nullable=True)
    auth_provider = Column(SQLEnum(AuthProvider), nullable=False, default=AuthProvider.NONE)
    google_sub = Column(String(255), unique=True, nullable=True, index=True)
    roles = Column(JSON, nullable=False, default=list)  # List of roles
    is_active = Column(Boolean, default=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for OAuth users (Google, etc.)
    # Email verification fields
    email_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), unique=True, nullable=True, index=True)
    verification_token_expires = Column(DateTime(timezone=True), nullable=True)
    # Password reset fields
    password_reset_token = Column(String(255), unique=True, nullable=True, index=True)
    password_reset_token_expires = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workspace_memberships = relationship("WorkspaceMember", back_populates="user", lazy="selectin")
    owned_products = relationship("Product", back_populates="owner")

    # Schema specification
    __table_args__ = ({"schema": POSTGRES_SCHEMA},)
    acls = relationship("ACL", back_populates="user")  # M5


class Workspace(Base):
    """Workspace model."""

    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    settings = Column(JSON, nullable=True, default=dict)  # Workspace settings (API keys, etc.)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    members = relationship("WorkspaceMember", back_populates="workspace", lazy="selectin")
    products = relationship("Product", back_populates="workspace", lazy="selectin")
    data_quality_rules = relationship("DataQualityRule", back_populates="workspace")
    billing_profile = relationship("BillingProfile", back_populates="workspace", uselist=False)
    eval_queries = relationship("EvalQuery", back_populates="workspace", cascade="all, delete-orphan")
    eval_runs = relationship("EvalRun", back_populates="workspace", cascade="all, delete-orphan")

    # Schema specification
    __table_args__ = ({"schema": POSTGRES_SCHEMA},)


class WorkspaceMember(Base):
    """Workspace membership model."""

    __tablename__ = "workspace_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=False)
    user_id = Column(String(255), ForeignKey(f"{POSTGRES_SCHEMA}.users.id"), nullable=False)  # Support any user ID format
    role = Column(SQLEnum(WorkspaceRole), nullable=False, default=WorkspaceRole.VIEWER)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="workspace_memberships")

    # Unique constraint and indexes
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="unique_workspace_user"),
        Index("idx_workspace_members_user_id", "user_id"),  # For fast user workspace membership lookups
        {"schema": POSTGRES_SCHEMA},
    )


class Product(Base):
    """Product model."""

    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=False, index=True)
    owner_user_id = Column(String(255), ForeignKey(f"{POSTGRES_SCHEMA}.users.id"), nullable=False)  # Support any user ID format
    name = Column(String(255), nullable=False)
    status = Column(SQLEnum(ProductStatus), nullable=False, default=ProductStatus.DRAFT)
    current_version = Column(Integer, nullable=False, default=0)
    promoted_version = Column(Integer, nullable=True, default=None)
    # AIRD configuration
    aird_enabled = Column(Boolean, nullable=False, default=True)  # Enable AIRD pipeline processing
    # AIRD playbook configuration (M1)
    playbook_id = Column(String(50), nullable=True, default=None)  # e.g., "TECH", "SCANNED", "REGULATORY"
    # Playbook selection metadata (for auto-detection verification)
    playbook_selection = Column(JSON, nullable=True, default=None)  # Stores: method, reason, detected_at, confidence
    # Preprocessing statistics (M1) - Hybrid storage: small JSON in DB, large JSON in S3
    preprocessing_stats = Column(
        JSON, nullable=True, default=None
    )  # sections, chunks, mid_sentence_boundary_rate (small JSON only)
    preprocessing_stats_path = Column(String(1000), nullable=True, default=None)  # S3 path for large JSON
    # Trust scoring and policy (M2) - Hybrid storage: small JSON in DB, large JSON in S3
    trust_score = Column(Float, nullable=True, default=None)  # Aggregated AI Trust Score
    readiness_fingerprint = Column(
        JSON, nullable=True, default=None
    )  # Readiness fingerprint (all 13 metrics) - small JSON only
    readiness_fingerprint_path = Column(String(1000), nullable=True, default=None)  # S3 path for large JSON
    policy_status = Column(SQLEnum(PolicyStatus), nullable=True, default=PolicyStatus.UNKNOWN)  # M2: Policy evaluation status
    policy_violations = Column(JSON, nullable=True, default=list)  # List of violation strings
    chunk_metrics = Column(JSON, nullable=True, default=list)  # Per-chunk metrics (small JSON only)
    chunk_metrics_path = Column(String(1000), nullable=True, default=None)  # S3 path for large JSON
    # Artifacts and reports (M3)
    validation_summary_path = Column(String(500), nullable=True, default=None)  # Storage path to validation CSV
    trust_report_path = Column(String(500), nullable=True, default=None)  # Storage path to trust report PDF
    # Chunking configuration
    chunking_config = Column(
        JSON,
        nullable=True,
        default=lambda: {
            "mode": "auto",  # "auto" or "manual"
            "auto_settings": {"content_type": "general", "model_optimized": True, "confidence_threshold": 0.7},
            "manual_settings": {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "min_chunk_size": 100,
                "max_chunk_size": 2000,
                "chunking_strategy": "fixed_size",
            },
            "last_analyzed": None,
            "analysis_confidence": 0.0,
        },
    )
    # Embedding configuration
    embedding_config = Column(JSON, nullable=True, default=None)
    # Vector creation configuration
    vector_creation_enabled = Column(Boolean, nullable=False, default=True)  # Enable vector/embedding creation and indexing
    use_case_description = Column(Text, nullable=True, default=None)  # Use case description (only set during creation)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workspace = relationship("Workspace", back_populates="products")
    owner = relationship("User", back_populates="owned_products")
    data_sources = relationship("DataSource", back_populates="product")
    data_quality_rules = relationship("DataQualityRule", back_populates="product")
    # Metadata is now stored in Qdrant payloads, not PostgreSQL tables
    raw_files = relationship("RawFile", back_populates="product")  # Track ingested raw files
    acls = relationship("ACL", back_populates="product")  # M5
    pipeline_artifacts = relationship("PipelineArtifact", back_populates="product")  # Track pipeline artifacts
    eval_queries = relationship("EvalQuery", back_populates="product", cascade="all, delete-orphan")
    eval_runs = relationship("EvalRun", back_populates="product", cascade="all, delete-orphan")

    # Unique constraint and indexes
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="unique_workspace_product_name"),
        Index("idx_products_workspace_id", "workspace_id"),
        Index("idx_products_owner_user_id", "owner_user_id"),
        Index("idx_products_status", "status"),  # For filtering by status
        Index("idx_products_created_at", "created_at"),  # For time-based queries
        {"schema": POSTGRES_SCHEMA},
    )


class DataSource(Base):
    """Data source model."""

    __tablename__ = "data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Unnamed Data Source")
    type = Column(SQLEnum(DataSourceType), nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    last_cursor = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workspace = relationship("Workspace")
    product = relationship("Product", back_populates="data_sources")

    # Indexes
    __table_args__ = (
        Index("idx_data_sources_workspace_id", "workspace_id"),
        Index("idx_data_sources_product_id", "product_id"),
        {"schema": POSTGRES_SCHEMA},
    )


class RawFile(Base):
    """Raw file model for tracking ingested files in object storage.

    Enterprise-grade metadata catalog for object storage files.
    Follows the metadata catalog pattern (DB for queries, object storage for files).
    Supports S3, GCS, Azure Blob, AWS S3, etc.
    """

    __tablename__ = "raw_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id"), nullable=False, index=True)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.data_sources.id"), nullable=True, index=True)
    version = Column(Integer, nullable=False, default=0)
    filename = Column(String(500), nullable=False)  # Original filename
    file_stem = Column(String(500), nullable=False, index=True)  # Filename without extension (for preprocessing)
    storage_key = Column(String(1000), nullable=False, unique=True)  # Full object storage key (S3 key, GCS blob name, etc.)
    storage_bucket = Column(String(255), nullable=False, default="primedata-raw")  # Storage bucket/container name
    file_size = Column(Integer, nullable=False)  # Size in bytes
    content_type = Column(String(255), nullable=False, default="application/octet-stream")  # MIME type
    status = Column(SQLEnum(RawFileStatus), nullable=False, default=RawFileStatus.INGESTED)  # Processing status
    file_checksum = Column(String(64), nullable=False)  # MD5 or SHA256 checksum for integrity validation
    storage_etag = Column(String(255), nullable=True)  # Storage provider ETag for validation (S3 ETag, GCS generation, etc.)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)  # When processing completed
    error_message = Column(Text, nullable=True)  # Error message if processing failed

    # Relationships
    workspace = relationship("Workspace")
    product = relationship("Product")
    data_source = relationship("DataSource")

    # Indexes
    __table_args__ = (
        Index("idx_raw_files_product_version", "product_id", "version"),
        Index("idx_raw_files_file_stem", "file_stem"),
        Index("idx_raw_files_data_source", "data_source_id"),
        Index("idx_raw_files_status", "status"),  # For querying by status
        UniqueConstraint("product_id", "version", "file_stem", name="uq_raw_file_product_version_stem"),
        {"schema": POSTGRES_SCHEMA},
    )


# DocumentMetadata and VectorMetadata models removed - metadata is now stored in Qdrant payloads
# This eliminates data duplication and reduces database costs


class ACL(Base):
    """Access Control List model (M5)."""

    __tablename__ = "acls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(String(255), ForeignKey(f"{POSTGRES_SCHEMA}.users.id"), nullable=False, index=True)  # Support any user ID format
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id"), nullable=False, index=True)
    access_type = Column(SQLEnum(ACLAccessType), nullable=False, index=True)
    index_scope = Column(String(500), nullable=True)  # Comma-separated index IDs or null
    doc_scope = Column(String(500), nullable=True)  # Comma-separated document IDs or null
    field_scope = Column(String(500), nullable=True)  # Comma-separated field names or null
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="acls")
    product = relationship("Product", back_populates="acls")

    # Indexes
    __table_args__ = (
        Index("idx_acls_user_id", "user_id"),
        Index("idx_acls_product_id", "product_id"),
        Index("idx_acls_access_type", "access_type"),
        Index("idx_acls_user_product", "user_id", "product_id"),
        {"schema": POSTGRES_SCHEMA},
    )


class PipelineRun(Base):
    """Pipeline run model."""

    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(SQLEnum(PipelineRunStatus), nullable=False, default=PipelineRunStatus.QUEUED)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # Always has start time
    finished_at = Column(DateTime(timezone=True), nullable=True)
    dag_run_id = Column(String(255), nullable=False, default="", index=True)  # Required for Airflow tracking
    metrics = Column(JSON, nullable=False, default=dict)  # Recent runs only (<90 days)
    metrics_path = Column(String(1000), nullable=True, default=None)  # S3 path for archived metrics
    archived_at = Column(DateTime(timezone=True), nullable=True)  # When metrics were moved to S3
    # AIRD stage tracking fields (M0)
    stage_metrics = Column(JSON, nullable=True, default=None)  # Per-stage metrics (deprecated, use metrics.aird_stages)
    aird_stages_completed = Column(
        JSON, nullable=True, default=None
    )  # List of completed stage names (deprecated, use metrics.aird_stages_completed)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workspace = relationship("Workspace")
    product = relationship("Product")
    artifacts = relationship("PipelineArtifact", back_populates="pipeline_run", cascade="all, delete-orphan")
    eval_runs = relationship("EvalRun", back_populates="pipeline_run")

    # Indexes
    __table_args__ = (
        Index("idx_pipeline_runs_product_version", "product_id", "version"),
        Index("idx_pipeline_runs_workspace_id", "workspace_id"),
        Index("idx_pipeline_runs_dag_run_id", "dag_run_id"),
        Index(
            "idx_pipeline_runs_product_status_created", "product_id", "status", "created_at"
        ),  # Composite index for common queries
        Index("idx_pipeline_runs_created_at", "created_at"),  # For archiving queries
        {"schema": POSTGRES_SCHEMA},
    )


class CustomPlaybook(Base):
    """Custom playbook model for user-created playbooks."""

    __tablename__ = "custom_playbooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=False, index=True)
    owner_user_id = Column(String(255), ForeignKey(f"{POSTGRES_SCHEMA}.users.id"), nullable=False, index=True)  # Support any user ID format
    name = Column(String(255), nullable=False)  # User-friendly name
    playbook_id = Column(String(100), nullable=False)  # Unique identifier (e.g., "CUSTOM_MY_PLAYBOOK")
    description = Column(Text, nullable=True)  # Optional description
    yaml_content = Column(Text, nullable=False)  # Full YAML content
    config = Column(JSON, nullable=True)  # Parsed YAML as JSON for quick access
    base_playbook_id = Column(String(50), nullable=True)  # Original playbook this was based on (e.g., "ACADEMIC")
    is_active = Column(Boolean, nullable=False, default=True)  # Soft delete flag
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workspace = relationship("Workspace")
    owner = relationship("User")

    # Indexes
    __table_args__ = (
        UniqueConstraint("workspace_id", "playbook_id", name="unique_workspace_playbook_id"),
        Index("idx_custom_playbooks_workspace_id", "workspace_id"),
        Index("idx_custom_playbooks_owner_user_id", "owner_user_id"),
        Index("idx_custom_playbooks_playbook_id", "playbook_id"),
        {"schema": POSTGRES_SCHEMA},
    )


class PipelineArtifact(Base):
    """Pipeline artifact registry for enterprise traceability.

    Tracks all artifacts generated during pipeline execution:
    - Location (storage bucket/key)
    - Integrity (size, checksum)
    - Lineage (input artifacts)
    - Metadata (stage-specific info)
    - Retention (lifecycle management)

    Enables full data lineage, audit trails, and cost optimization.
    Supports S3, GCS, Azure Blob, AWS S3, etc.
    """

    __tablename__ = "pipeline_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.pipeline_runs.id"), nullable=False, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, index=True)

    # Artifact identification
    stage_name = Column(String(100), nullable=False, index=True)  # "preprocess", "scoring", "fingerprint", etc.
    artifact_type = Column(SQLEnum(ArtifactType), nullable=False)  # "jsonl", "json", "csv", "pdf", "vector"
    artifact_name = Column(String(255), nullable=False)  # "processed_chunks", "metrics", "fingerprint", etc.

    # Storage location
    storage_bucket = Column(
        String(255), nullable=False
    )  # Storage bucket/container name (e.g., "primedata-clean", "primedata-embed")
    storage_key = Column(String(1000), nullable=False, index=True)  # Full object storage key (S3 key, GCS blob name, etc.)
    file_size = Column(BigInteger, nullable=False)  # Size in bytes
    checksum = Column(String(64), nullable=False)  # MD5 or SHA256 for integrity verification
    storage_etag = Column(String(255), nullable=False)  # Storage provider ETag for validation (S3 ETag, GCS generation, etc.)

    # Data lineage (Phase 2)
    input_artifacts = Column(JSON, nullable=True, default=list)  # List of artifact IDs this depends on
    # Format: [{"artifact_id": "uuid", "stage": "preprocess", "artifact_name": "processed_chunks"}]

    # Stage-specific metadata (renamed from 'metadata' as it's reserved in SQLAlchemy)
    artifact_metadata = Column(JSON, nullable=True, default=dict)  # Stage-specific metadata:
    # - chunks_count, files_processed, playbook_id, thresholds, embedding_model, etc.

    # Lifecycle management (Phase 3)
    status = Column(SQLEnum(ArtifactStatus), nullable=False, default=ArtifactStatus.ACTIVE, index=True)
    retention_policy = Column(SQLEnum(RetentionPolicy), nullable=False, default=RetentionPolicy.DAYS_90)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Optional: Track who/what created it (for audit)
    created_by = Column(String(255), ForeignKey(f"{POSTGRES_SCHEMA}.users.id"), nullable=True)  # Support any user ID format

    # Relationships
    pipeline_run = relationship("PipelineRun", back_populates="artifacts")
    workspace = relationship("Workspace")
    product = relationship("Product")
    creator = relationship("User")

    # Indexes
    __table_args__ = (
        Index("idx_artifacts_product_version", "product_id", "version"),
        Index("idx_artifacts_stage_type", "stage_name", "artifact_type"),
        Index("idx_artifacts_status_created", "status", "created_at"),
        Index("idx_artifacts_retention", "retention_policy", "created_at"),
        Index("idx_artifacts_storage_key", "storage_key"),  # For quick lookup by storage key
        {"schema": POSTGRES_SCHEMA},
    )


class DqViolationSeverity(str, Enum):
    """Data quality violation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DqViolation(Base):
    """Data quality violation model."""

    __tablename__ = "dq_violations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, index=True)
    pipeline_run_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Violation details
    rule_name = Column(String(255), nullable=False)
    rule_type = Column(String(100), nullable=False)
    severity = Column(SQLEnum(DqViolationSeverity), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True, default=dict)

    # Statistics
    affected_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    violation_rate = Column(Float, default=0.0)

    # Archiving fields for cost optimization
    archived_at = Column(DateTime(timezone=True), nullable=True)  # When violation was archived
    archived_to_s3 = Column(Boolean, nullable=False, default=False)  # Whether archived to S3

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    product = relationship("Product")

    # Indexes
    __table_args__ = (
        Index("idx_dq_violations_product_version", "product_id", "version"),
        Index("idx_dq_violations_severity", "severity"),
        Index("idx_dq_violations_created_at", "created_at"),
        Index(
            "idx_dq_violations_product_version_severity", "product_id", "version", "severity"
        ),  # Composite index for filtering
        {"schema": POSTGRES_SCHEMA},
    )


class BillingProfile(Base):
    """Billing profile for workspace."""

    __tablename__ = "billing_profiles"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), primary_key=True)
    stripe_customer_id = Column(String(255), unique=True, nullable=True, index=True)
    plan = Column(SQLEnum(BillingPlan), default=BillingPlan.FREE, nullable=False)
    default_payment_method_id = Column(String(255), nullable=True)
    usage = Column(JSON, default=dict, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    workspace = relationship("Workspace", back_populates="billing_profile")

    # Indexes
    __table_args__ = (
        Index("idx_billing_profiles_stripe_customer", "stripe_customer_id"),
        Index("idx_billing_profiles_plan", "plan"),
        {"schema": POSTGRES_SCHEMA},
    )


class EvalQuery(Base):
    """Synthetic evaluation queries for RAG evaluation."""
    
    __tablename__ = "eval_queries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    chunk_id = Column(String(255), nullable=False, index=True)
    query = Column(Text, nullable=False)
    expected_chunk_id = Column(String(255), nullable=False)
    query_style = Column(String(50), nullable=True)  # 'technical', 'academic', 'clinical', etc.
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="eval_queries")
    workspace = relationship("Workspace", back_populates="eval_queries")
    
    # Indexes
    __table_args__ = (
        Index('idx_eval_queries_product_version', 'product_id', 'version'),
        {"schema": POSTGRES_SCHEMA},
    )


class EvalRun(Base):
    """Evaluation runs for RAG metrics calculation."""
    
    __tablename__ = "eval_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.products.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, server_default='pending')  # 'pending', 'running', 'completed', 'failed'
    metrics = Column(JSONB, nullable=True)  # Store Recall@k, MRR, nDCG, etc.
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="eval_runs")
    workspace = relationship("Workspace", back_populates="eval_runs")
    pipeline_run = relationship("PipelineRun", back_populates="eval_runs")
    
    # Indexes
    __table_args__ = (
        Index('idx_eval_runs_product_version', 'product_id', 'version'),
        {"schema": POSTGRES_SCHEMA},
    )
class UserAuditLog(Base):
    """User audit log model for tracking user actions and changes."""

    __tablename__ = "user_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey(f"{POSTGRES_SCHEMA}.workspaces.id"), nullable=True, index=True)
    user_id = Column(String(255), ForeignKey(f"{POSTGRES_SCHEMA}.users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # e.g., CREATE, UPDATE, DELETE, VIEW
    resource_type = Column(String(100), nullable=False, index=True)  # e.g., PRODUCT, WORKSPACE, DOCUMENT
    resource_id = Column(String(255), nullable=False, index=True)  # ID of the affected resource
    changes = Column(JSONB, nullable=True, default=dict)  # Before/after changes {before: {...}, after: {...}}
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)  # Browser user agent
    status = Column(String(50), nullable=False, default="success", index=True)  # success, failure, partial
    error_message = Column(Text, nullable=True)  # Error details if status is failure
    audit_metadata = Column(JSONB, nullable=True, default=dict)  # Additional context
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    workspace = relationship("Workspace", foreign_keys=[workspace_id])

    # Indexes for efficient querying
    __table_args__ = (
        Index("idx_user_audit_user_id_timestamp", "user_id", "timestamp"),
        Index("idx_user_audit_workspace_timestamp", "workspace_id", "timestamp"),
        Index("idx_user_audit_action_timestamp", "action", "timestamp"),
        Index("idx_user_audit_resource_type_id", "resource_type", "resource_id"),
        {"schema": POSTGRES_SCHEMA},
    )


# Import enterprise models AFTER all models are defined
# This ensures Product and other base models exist before enterprise models try to reference them
from .models_enterprise import (
    AuditAction,
    DataQualityComplianceReport,
    DataQualityRule,
    DataQualityRuleAssignment,
    DataQualityRuleAudit,
    DataQualityRuleSet,
    RuleSeverity,
    RuleStatus,
)
