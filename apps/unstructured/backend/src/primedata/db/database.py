"""
Database configuration and session management.
"""

from primedata.utils.log_utils import get_logger
from primedata.core.settings import get_settings
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = get_logger(__name__)

# Get settings
logger.info("🔧 [db init] ENTRY | Loading database settings")
settings = get_settings()
logger.debug(f"✓ Settings loaded | ENV={settings.ENV}")

# Get database URL (constructed from components if needed)
logger.debug("📋 Constructing database URL")
database_url = settings.get_database_url()
logger.info(f"✓ Database URL configured (host={settings.POSTGRES_HOST}, port={settings.POSTGRES_PORT})")

# Create database engine
logger.debug(f"🔧 Creating engine | echo={settings.ENV == 'development'}")
engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300, echo=settings.ENV == "development")
logger.info(f"✅ Database engine created | pool_recycle=300s | echo={settings.ENV == 'development'}")

# Create session factory
logger.debug("🔧 Creating session factory")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logger.info("✅ Session factory created")

# Create base class for models
logger.debug("🔧 Creating declarative base")
Base = declarative_base()
logger.info("✅ Declarative base created")


def get_db():
    """
    Get database session.

    Yields:
        Database session for dependency injection in FastAPI endpoints

    Example:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    logger.debug("💾 [get_db] Creating new session")
    db = SessionLocal()
    try:
        logger.debug("✓ Session created and ready")
        yield db
    except Exception as e:
        logger.error(f"❌ Error in session context: {e}", exc_info=True)
        raise
    finally:
        logger.debug("💾 Closing session")
        db.close()
        logger.info("✅ Session closed")

