"""
Application settings and configuration.
"""

import json
import logging
import os
from typing import List, Optional, Union, ClassVar

logger = logging.getLogger(__name__)

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for pydantic v1
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Environment
    ENV: str = "development"

    # Database Configuration
    # Option 1: Full DATABASE_URL (preferred - simplest)
    # Option 2: Individual components (fallback - more flexible, allows database name from secrets)
    DATABASE_URL: Optional[str] = None  # Primary: full connection string

    # Individual components (used if DATABASE_URL not set)
    # ⚠️ WARNING: All components must be set via environment variables or .env file!
    # Values are read from Settings instance attributes (loaded from .env or environment)
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_HOST: str = "localhost"  # Default fallback
    POSTGRES_PORT: int = 5432  # Default fallback
    POSTGRES_DB: Optional[str] = None  # ⚠️ MUST be set via POSTGRES_DB environment variable or .env file!
    POSTGRES_SCHEMA: str = "public"  # PostgreSQL schema name (defaults to 'public')

    def get_database_url(self) -> str:
        """
        Get database URL, constructing from components if DATABASE_URL not set.

        Priority:
        1. DATABASE_URL from settings (loaded from .env or environment)
        2. Construct from POSTGRES_* components (if all set)
        3. Raise error if insufficient configuration
        """
        logger.info("🔧 [get_database_url] ENTRY")
        logger.debug(f"📋 Checking configuration priority | DATABASE_URL={bool(self.DATABASE_URL)}")

        # Read DATABASE_URL from settings (loaded from .env or environment)
        if self.DATABASE_URL:
            logger.debug("✓ Using DATABASE_URL from settings")
            logger.info(f"✅ [get_database_url] EXIT | source=DATABASE_URL")
            return self.DATABASE_URL

        # Otherwise, construct from individual components
        logger.debug("📋 DATABASE_URL not set, attempting to construct from components")
        user = self.POSTGRES_USER
        password = self.POSTGRES_PASSWORD
        host = self.POSTGRES_HOST
        port = self.POSTGRES_PORT
        db_name = self.POSTGRES_DB

        logger.debug(f"✓ Components | host={host} | port={port} | user={bool(user)} | password={bool(password)} | db_name={bool(db_name)}")

        if not all([user, password, db_name]):
            missing = []
            if not user:
                missing.append("POSTGRES_USER")
            if not password:
                missing.append("POSTGRES_PASSWORD")
            if not db_name:
                missing.append("POSTGRES_DB")

            logger.error(f"❌ Missing database configuration | missing_vars={missing}")
            raise ValueError(
                f"Database configuration required! Either set DATABASE_URL, "
                f"or set all of: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB. "
                f"Missing environment variables: {', '.join(missing)}. "
                f"See backend/env.example for configuration template."
            )

        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"
        logger.info(f"✅ [get_database_url] EXIT | source=POSTGRES_* | host={host} | port={port}")
        return url

    # CORS - can be set via environment variable as JSON array or comma-separated string
    # Example: CORS_ORIGINS='["http://localhost:3000","https://airdops.com"]'
    # Or: CORS_ORIGINS=http://localhost:3000,https://airdops.com
    # IMPORTANT: If requests are blocked with "No Access-Control-Allow-Origin header",
    # verify this list includes the frontend origin and backend environment is restarted
    CORS_ORIGINS: Union[List[str], str] = [
        # Frontend URLs
        "https://primedata-frontend.apps.lrl.lilly.com",
        "https://primedata-frontend.apps-internal.lrl.lilly.com",
        # Internal backend URLs (for service-to-service calls from frontend via API)
        "https://primedata-internal.apps-internal.lrl.lilly.com",
        "https://primedata-backend.apps-api-d.lrl.lilly.com",
        "https://primedata-backend.apps-d.lrl.lilly.com",
        # Localhost for development
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://primedata.apps-d.lrl.lilly.com"
    ]

    # Authentication
    NEXTAUTH_SECRET: str = "REPLACE_WITH_64_CHAR_RANDOM_STRING_FOR_PRODUCTION_USE_ONLY"
    JWT_ISSUER: str = "https://api.local/auth"
    JWT_AUDIENCE: str = "primedata-api"
    API_SESSION_EXCHANGE_ALLOWED_ISS: str = "https://nextauth.local"


    # Storage Configuration
    # AWS S3 Configuration (production storage backend)
    S3_ENDPOINT_URL: Optional[str] = None  # For LocalStack/S3-compatible services (e.g., http://localhost:4566)
    S3_REGION: str = "us-east-2"
    S3_ACCESS_KEY_ID: Optional[str] = None  # Optional: uses IAM role/profile if not set
    S3_SECRET_ACCESS_KEY: Optional[str] = None  # Optional: uses IAM role/profile if not set
    S3_USE_PATH_STYLE: bool = False  # Set to True for LocalStack

    # S3 Connection pooling and retry settings
    S3_CONNECT_TIMEOUT: int = 10
    S3_READ_TIMEOUT: int = 120
    S3_MAX_RETRIES: int = 5
    S3_MAX_POOL_CONNECTIONS: int = 10

    # Elasticsearch Configuration
    # Reads from ELASTICSEARCH_URL environment variable, or defaults based on environment
    # In K8s: set ELASTICSEARCH_URL=http://elasticsearch.primedata-dev.svc.cluster.local:9200 or http://elasticsearch:9200
    # For local dev: set ELASTICSEARCH_URL=http://localhost:9200 or leave unset for default
    ELASTICSEARCH_URL: ClassVar[str] = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

    # OpenSearch Configuration
    # Reads from OPENSEARCH_URL environment variable
    # Example: OPENSEARCH_URL=https://opensearch.example.com:9200
    # For AWS OpenSearch domain with IAM auth, also set OPENSEARCH_ROLE_ARN environment variable
    # Example: OPENSEARCH_ROLE_ARN=arn:aws:iam::123456789012:role/opensearch-access-role
    OPENSEARCH_URL: ClassVar[str] = os.getenv("OPENSEARCH_URL", "https://localhost:9200")
    OPENSEARCH_ROLE_ARN: ClassVar[Optional[str]] = os.getenv("OPENSEARCH_ROLE_ARN")
    AWS_REGION: ClassVar[str] = os.getenv("AWS_REGION", "us-east-1")

    # OpenAI Configuration
    OPENAI_API_KEY: Optional[str] = None  # OpenAI API key for embedding models

    # Azure OpenAI Configuration (via Service Principal / Graph API)
    # Set these environment variables to enable Azure OpenAI embedding models
    # AZURE_OPENAI_ENDPOINT: https://<resource>.openai.azure.com
    # AZURE_OPENAI_DEPLOYMENT_NAME: <deployment-name>
    # AZURE_OPENAI_MODEL_NAME: <model-name> (e.g., text-embedding-3-small)
    # AZURE_OPENAI_API_VERSION: <api-version> (default: 2024-02-01)
    # AZURE_OPENAI_DIMENSIONS: <dimensions> (e.g., 1536)
    # AZURE_CLIENT_ID: <app-registration-client-id>
    # AZURE_CLIENT_SECRET: <client-secret>
    # AZURE_TENANT_ID: <tenant-id>
    AZURE_OPENAI_ENDPOINT: ClassVar[Optional[str]] = os.getenv("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_DEPLOYMENT_NAME: ClassVar[Optional[str]] = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    AZURE_OPENAI_MODEL_NAME: ClassVar[Optional[str]] = os.getenv("AZURE_OPENAI_MODEL_NAME")
    AZURE_OPENAI_API_VERSION: ClassVar[str] = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    AZURE_OPENAI_DIMENSIONS: ClassVar[int] = int(os.getenv("AZURE_OPENAI_DIMENSIONS", "1536"))
    AZURE_CLIENT_ID: ClassVar[Optional[str]] = os.getenv("AZURE_CLIENT_ID")
    AZURE_CLIENT_SECRET: ClassVar[Optional[str]] = os.getenv("AZURE_CLIENT_SECRET")
    AZURE_TENANT_ID: ClassVar[Optional[str]] = os.getenv("AZURE_TENANT_ID")
    AZURE_OPENAI_SCOPE: ClassVar[str] = os.getenv("AZURE_OPENAI_SCOPE", "https://cognitiveservices.azure.com/.default")

    # AIRD Configuration (M0)
    AIRD_PLAYBOOK_DIR: str = ""  # Path to playbook directory (empty = auto-detect)
    AIRD_SCORING_WEIGHTS_PATH: str = ""  # Path to scoring weights JSON (empty = auto-detect)

    # Email Configuration (SMTP)
    SMTP_ENABLED: bool = False  # Set to True to enable email sending
    # Email domain validation (DNS MX record checks)
    EMAIL_DOMAIN_VALIDATION_ENABLED: bool = False  # Disabled for internal domains (prevents DNS check failures)
    SMTP_HOST: str = "smtp.gmail.com"  # SMTP server hostname
    SMTP_PORT: int = 587  # SMTP server port (587 for TLS, 465 for SSL, 25 for plain)
    SMTP_USE_TLS: bool = True  # Use TLS encryption
    SMTP_USE_SSL: bool = False  # Use SSL encryption (alternative to TLS)
    SMTP_USERNAME: Optional[str] = None  # SMTP username (usually your email)
    SMTP_PASSWORD: Optional[str] = None  # SMTP password or app-specific password
    SMTP_FROM_EMAIL: str = "noreply@primedata.com"  # From email address
    SMTP_TO_EMAIL: Optional[str] = None  # Recipient email for contact/feedback forms (defaults to SMTP_USERNAME if not set)
    FRONTEND_URL: str = "https://airdops.com"  # Frontend URL for email links

    class Config:
        # Check for .env.local first (for local development), then fall back to .env
        # pydantic_settings will try files in order and use the first one that exists
        env_file = [".env.local", ".env"]
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env (for backward compatibility during migration)


# Global settings instance
_settings: Settings = None


def get_settings() -> Settings:
    """Get application settings (singleton pattern)."""
    global _settings
    if _settings is None:
        logger.info("🔧 [get_settings] ENTRY | Initializing settings singleton")
        logger.debug("📋 Creating Settings instance")
        _settings = Settings()
        logger.debug(f"✓ Settings instance created | ENV={_settings.ENV}")

        # Parse CORS_ORIGINS from environment if it's a string
        logger.debug("📋 Processing CORS_ORIGINS configuration")
        cors_origins_env = os.getenv("CORS_ORIGINS")
        if cors_origins_env:
            logger.debug(f"✓ CORS_ORIGINS environment variable found")
            try:
                logger.debug("📋 Attempting JSON parse")
                # Try parsing as JSON array first
                parsed = json.loads(cors_origins_env)
                if isinstance(parsed, list):
                    logger.debug(f"✓ Parsed as JSON list | count={len(parsed)}")
                    _settings.CORS_ORIGINS = parsed
                else:
                    # If JSON but not a list, treat as single value
                    logger.debug(f"✓ Parsed as JSON non-list | treating as single value")
                    _settings.CORS_ORIGINS = [str(parsed)]
            except (json.JSONDecodeError, ValueError):
                logger.debug("⚠️ JSON parse failed, attempting comma-separated parse")
                # If not JSON, treat as comma-separated string
                origins_list = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
                if origins_list:
                    logger.debug(f"✓ Parsed as comma-separated list | count={len(origins_list)}")
                    _settings.CORS_ORIGINS = origins_list
                else:
                    # Single value
                    logger.debug(f"✓ Treating as single value")
                    _settings.CORS_ORIGINS = [cors_origins_env.strip()]
        else:
            logger.debug("⚠️ CORS_ORIGINS environment variable not set, using defaults")

        # Ensure CORS_ORIGINS is always a list
        if isinstance(_settings.CORS_ORIGINS, str):
            logger.debug("📋 Converting CORS_ORIGINS string to list")
            _settings.CORS_ORIGINS = [_settings.CORS_ORIGINS]

        # Log final configuration
        cors_count = len(_settings.CORS_ORIGINS)
        logger.info(f"✅ [get_settings] EXIT | CORS_ORIGINS configured with {cors_count} origin(s) | ENV={_settings.ENV}")
        logger.debug(f"🔐 CORS origins: {_settings.CORS_ORIGINS}")

    return _settings
