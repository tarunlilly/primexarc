"""
Centralized constants module for PrimeData.

This module consolidates all magic strings, numbers, and configuration values
that were previously scattered throughout the codebase.

Usage:
    from primedata.core.constants import BUCKET_RAW, API_V1_PREFIX, JWT_ALGORITHM_RS256
"""

import os

# Initialize logger for constants module
try:
    from primedata.utils.logger import get_logger
    _logger = get_logger(__name__)
except Exception:
    # Fallback if logger not available during import
    import logging
    _logger = logging.getLogger(__name__)

# ============================================================================
# S3 BUCKET NAMES (CRITICAL - 80+ occurrences)
# ============================================================================
BUCKET_RAW = "primedata-raw"           # Raw ingested files
BUCKET_CLEAN = "primedata-clean"       # Cleaned/preprocessed data
BUCKET_CHUNK = "primedata-chunk"       # Chunked content
BUCKET_EMBED = "primedata-embed"       # Embeddings and vectors
BUCKET_EXPORTS = "primedata-exports"   # Exported data and reports
BUCKET_CONFIG = "primedata-config"     # Configuration files


# ============================================================================
# API CONFIGURATION (HIGH - 50+ occurrences)
# ============================================================================
API_VERSION = "v1"
API_V1_PREFIX = "/api/v1"
API_HEALTHCHECK_PATH = "/health"

# API Endpoints
ENDPOINT_PRODUCTS = f"{API_V1_PREFIX}/products"
ENDPOINT_DATASOURCES = f"{API_V1_PREFIX}/datasources"
ENDPOINT_EXPORTS = f"{API_V1_PREFIX}/exports"
ENDPOINT_PIPELINE = f"{API_V1_PREFIX}/pipeline"
ENDPOINT_ARTIFACTS = f"{API_V1_PREFIX}/artifacts"
ENDPOINT_AUTH_PREFIX = f"{API_V1_PREFIX}/auth"
ENDPOINT_ANALYTICS = f"{API_V1_PREFIX}/analytics"
ENDPOINT_BILLING = f"{API_V1_PREFIX}/billing"
ENDPOINT_DATA_QUALITY = f"{API_V1_PREFIX}/data-quality"

# Airflow API
AIRFLOW_API_PREFIX = "/api/v1/dags"
AIRFLOW_DAG_ENDPOINT = AIRFLOW_API_PREFIX

# Airflow DAG ID - with environment variable support and logging
AIRFLOW_DAG_ID = os.getenv("AIRFLOW_DAG_ID", "primedata_simple")
_logger.debug(f"🔧 Airflow DAG ID configured: {AIRFLOW_DAG_ID}")


# ============================================================================
# STATUS & ENUM VALUES (HIGH - 50+ occurrences)
# ============================================================================
# Pipeline Run Status - Use PipelineRunStatus enum, but define string values here
STATUS_PIPELINE_PENDING = "PENDING"
STATUS_PIPELINE_RUNNING = "RUNNING"
STATUS_PIPELINE_SUCCEEDED = "SUCCEEDED"
STATUS_PIPELINE_FAILED = "FAILED"

# Raw File Status - Use RawFileStatus enum
STATUS_RAW_FILE_PROCESSING = "PROCESSING"
STATUS_RAW_FILE_INGESTED = "INGESTED"
STATUS_RAW_FILE_PROCESSED = "PROCESSED"
STATUS_RAW_FILE_DELETED = "DELETED"

# Artifact Status - Use ArtifactStatus enum
STATUS_ARTIFACT_ACTIVE = "ACTIVE"
STATUS_ARTIFACT_DELETED = "DELETED"
STATUS_ARTIFACT_ARCHIVED = "ARCHIVED"

# Product Status - Use ProductStatus enum
STATUS_PRODUCT_DRAFT = "DRAFT"
STATUS_PRODUCT_ACTIVE = "ACTIVE"

# Data Source Type
DATASOURCE_TYPE_S3 = "S3"
DATASOURCE_TYPE_AZURE = "AZURE_BLOB"
DATASOURCE_TYPE_FOLDER = "FOLDER"
DATASOURCE_TYPE_WEB = "WEB"
DATASOURCE_TYPE_DATABASE = "DATABASE"


# ============================================================================
# JWT & AUTHENTICATION (HIGH - 8+ occurrences)
# ============================================================================
# JWT Algorithms
JWT_ALGORITHM_RS256 = "RS256"
JWT_ALGORITHM_HS256 = "HS256"
JWT_ALGORITHM_DEFAULT = JWT_ALGORITHM_RS256

# JWT Configuration
JWT_KEY_ID = "primedata-key-1"
JWT_AUDIENCE_PRIMEDATA = "primedata-api"
JWT_ISSUER_DEFAULT = "https://api.local/auth"

# RSA Configuration
RSA_KEY_SIZE = 2048
RSA_PUBLIC_EXPONENT = 65537
RSA_MODULUS_BYTES = 256
RSA_KEY_TYPE = "RSA"

# A256GCM Configuration
A256GCM_KEY_SIZE = 32


# ============================================================================
# TIME & DURATION CONSTANTS (MEDIUM - 15+ occurrences)
# ============================================================================
# Cache & Session TTL (in seconds)
CACHE_TTL_5MIN = 300
CACHE_TTL_1HOUR = 3600
CACHE_TTL_24HOUR = 86400

# Presigned URL Expiry
PRESIGNED_URL_EXPIRY_1HOUR = 3600
PRESIGNED_URL_EXPIRY_24HOUR = 86400

# Default session timeout
SESSION_TIMEOUT_DEFAULT = 3600  # 1 hour

# API Timeouts
HTTP_TIMEOUT_DEFAULT = 30
HTTP_TIMEOUT_LONG = 120


# ============================================================================
# FILE SIZE CONSTANTS (MEDIUM - 10+ occurrences)
# ============================================================================
# Size thresholds (in bytes)
SIZE_1KB = 1024
SIZE_1MB = 1024 * 1024
SIZE_10MB = 10 * 1024 * 1024
SIZE_100MB = 100 * 1024 * 1024
SIZE_1GB = 1024 * 1024 * 1024

# File size validation
MAX_FILE_SIZE = SIZE_100MB
MIN_FILE_SIZE = SIZE_1KB

# JSON processing threshold
JSON_SIZE_THRESHOLD = SIZE_1MB  # Process JSON inline if smaller than 1MB

# Log file rotation size
LOG_FILE_MAX_BYTES = SIZE_10MB


# ============================================================================
# MIME/CONTENT TYPES (MEDIUM - 12+ occurrences)
# ============================================================================
CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_TEXT = "text/plain"
CONTENT_TYPE_HTML = "text/html"
CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CONTENT_TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CONTENT_TYPE_CSV = "text/csv"
CONTENT_TYPE_XML = "application/xml"
CONTENT_TYPE_BINARY = "application/octet-stream"


# ============================================================================
# EMBEDDING & VECTOR DIMENSIONS (MEDIUM - 10+ occurrences)
# ============================================================================
# Embedding dimensions for different models
EMBEDDING_DIM_MINILM = 384          # MiniLM-L6-v2
EMBEDDING_DIM_MPNET = 768           # mpnet-base-v2
EMBEDDING_DIM_DEFAULT = EMBEDDING_DIM_MINILM

# Default embedding model
EMBEDDING_MODEL_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"


# ============================================================================
# CHUNKING PARAMETERS (MEDIUM - 8+ occurrences)
# ============================================================================
# Text chunking sizes
CHUNK_SIZE_DEFAULT = 1000
CHUNK_SIZE_MIN = 50
CHUNK_SIZE_MAX = 2200
CHUNK_OVERLAP_DEFAULT = 200
CHUNK_OVERLAP_MIN = 50
CHUNK_OVERLAP_MAX = 500

# Hard overlap for specific content types (in characters)
CHUNK_HARD_OVERLAP_HEALTHCARE = 300
CHUNK_HARD_OVERLAP_REGULATORY = 300
CHUNK_HARD_OVERLAP_SCANNED = 300


# ============================================================================
# DATABASE CONFIGURATION (LOW - connection defaults)
# ============================================================================
# Database driver
DB_DRIVER_POSTGRESQL = "postgresql+psycopg2"

# Default connection parameters
DB_HOST_DEFAULT = "localhost"
DB_PORT_DEFAULT = 5432
DB_POOL_SIZE = 10
DB_POOL_RECYCLE = 300  # Recycle connections every 5 minutes
DB_POOL_TIMEOUT = 30


# ============================================================================
# SERVICE NAMES & IDENTIFIERS (MEDIUM - 8+ occurrences)
# ============================================================================
SERVICE_NAME_S3 = "s3"
SERVICE_NAME_AZURE = "azure_blob"
SERVICE_NAME_FOLDER = "folder"
SERVICE_NAME_DATABASE = "database"
SERVICE_NAME_WEB = "web"

# LocalStack/Development endpoints
LOCALSTACK_S3_ENDPOINT = "http://localhost:4566"
LOCALSTACK_S3_REGION = "us-east-1"

# Elasticsearch
ELASTICSEARCH_URL_DEFAULT = "http://localhost:9200"
ELASTICSEARCH_INDEX_EMBEDDINGS = "embeddings"


# ============================================================================
# METADATA & STORAGE PATHS (MEDIUM - 5+ occurrences)
# ============================================================================
METADATA_PATH_DEFAULT = "metadata"
PATH_SEGMENT_VERSION = "v"
PATH_SEGMENT_PROD = "prod"
PATH_SEGMENT_DEV = "dev"
PATH_SEGMENT_TEST = "test"


# ============================================================================
# ENVIRONMENT & CORS (MEDIUM - Depends on environment)
# ============================================================================
# Default CORS origins (can be overridden by environment variable)
CORS_ORIGINS_DEFAULT = [
    "https://primedata-frontend.apps.lrl.lilly.com",
    "https://primedata-frontend.apps-internal.lrl.lilly.com",
    "https://primedata-internal.apps-internal.lrl.lilly.com",
    "https://primedata-backend.apps-api-d.lrl.lilly.com",
    "https://primedata-backend.apps-d.lrl.lilly.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://primedata.apps-d.lrl.lilly.com",
]

# Default URLs
FRONTEND_URL_DEFAULT = "https://airdops.com"
FRONTEND_URL_DEV = "http://localhost:3000"
BACKEND_URL_DEFAULT = "http://localhost:7000"

# Default AWS region
AWS_REGION_DEFAULT = "us-east-2"


# ============================================================================
# HTTP STATUS CODES (Reference - use from `status` module)
# ============================================================================
# Note: For HTTP status codes, use FastAPI's status module instead
# from fastapi import status
# status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST, etc.


# ============================================================================
# PAGINATION DEFAULTS (MEDIUM - common defaults)
# ============================================================================
PAGINATION_LIMIT_DEFAULT = 50
PAGINATION_LIMIT_MIN = 1
PAGINATION_LIMIT_MAX = 1000
PAGINATION_OFFSET_DEFAULT = 0


# ============================================================================
# RETRY & BACKOFF CONFIGURATION (MEDIUM - resilience)
# ============================================================================
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2
RETRY_BACKOFF_MAX = 60  # Maximum 60 seconds between retries


# ============================================================================
# LOGGING CONFIGURATION (MEDIUM)
# ============================================================================
LOG_LEVEL_DEFAULT = "INFO"
LOG_FORMAT_DEFAULT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_MAX_BYTES = LOG_FILE_MAX_BYTES
LOG_BACKUP_COUNT = 5


# ============================================================================
# REGEX PATTERNS & VALIDATORS (MEDIUM - 5+ occurrences)
# ============================================================================
# Email validation regex (simplified)
EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

# UUID validation regex
UUID_REGEX = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


# ============================================================================
# PII DETECTION PATTERNS (shared across scoring_utils & trust_scoring)
# ============================================================================
PII_EMAIL_PATTERN = r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
PII_PHONE_PATTERN = r"(?:\+?\d[\s-]?)?(?:\(\d{3}\)|\d{3})[\s-]?\d{3}[\s-]?\d{4}"
PII_SSN_PATTERN = r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b"
PII_CREDIT_CARD_PATTERN = r"\b(?:\d[ -]*?){13,16}\b"


# ============================================================================
# SCORING THRESHOLDS (used in trust_scoring & scoring_utils)
# ============================================================================
SCORING_FRESHNESS_DECAY_DAYS_DEFAULT = 365.0
SCORING_SENTENCE_LEN_MIN_GOOD = 10
SCORING_SENTENCE_LEN_MAX_GOOD = 30
SCORING_SENTENCE_LEN_ACCESSIBLE_MIN = 10
SCORING_SENTENCE_LEN_ACCESSIBLE_MAX = 25
SCORING_SENTENCE_LEN_ACCESSIBLE_IDEAL = 17.5
SCORING_TOKEN_TARGET = 900.0


# ============================================================================
# PREPROCESSING CONSTANTS (used in preprocess.py, content_analyzer.py)
# ============================================================================
PLAYBOOK_SAMPLE_MAX_CHARS = 2000
PLAYBOOK_ROUTING_SAMPLE_CHARS = 1000
PDF_CORRUPTION_SPACE_RATIO_THRESHOLD = 0.3
PDF_CORRUPTION_FIX_MAX_PASSES = 10
PREPROCESSING_PROGRESS_LOG_INTERVAL = 20

UNSUPPORTED_IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg"
)

# Content analyzer thresholds
CONTENT_LONG_SENTENCE_THRESHOLD = 30
CONTENT_SHORT_SENTENCE_THRESHOLD = 15
CONTENT_MIN_WORD_COUNT = 100
CONTENT_MAX_WORD_COUNT = 10000


# ============================================================================
# AUGMENTATION DEFAULTS
# ============================================================================
AUGMENTATION_MAX_CHUNKS = 50
AUGMENTATION_SNIPPET_MAX_CHARS = 300
AUGMENTATION_MAX_KEYWORDS = 5


# ============================================================================
# FEATURE FLAGS (MEDIUM - feature toggles)
# ============================================================================
FEATURE_ENABLE_ELASTICSEARCH = True
FEATURE_ENABLE_QDRANT_INDEXING = True
FEATURE_ENABLE_DATA_QUALITY_VALIDATION = True
FEATURE_ENABLE_BILLING_LIMITS = True


if __name__ == "__main__":
    # Print all constants for documentation
    print("PrimeData Constants Module")
    print("=" * 60)

    import inspect

    for name, value in sorted(inspect.getmembers(__name__, lambda x: not inspect.ismodule(x))):
        if name.isupper() and not name.startswith("_"):
            print(f"{name}: {value}")
