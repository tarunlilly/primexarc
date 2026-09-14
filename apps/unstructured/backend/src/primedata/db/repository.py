"""Base repository pattern for database operations."""

from typing import Generic, TypeVar, Type, List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from ..db.database import Base
from ..core.exceptions import ResourceNotFoundError, ensure_found
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)
T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Generic repository for common database operations."""

    def __init__(self, model: Type[T], db: Session):
        logger.debug(f"🔧 [BaseRepository.__init__] Initializing repository for model={model.__name__}")
        self.model = model
        self.db = db
        logger.info(f"✅ Repository initialized | model={model.__name__}")

    def get_by_id(self, id: UUID) -> Optional[T]:
        """Get single record by ID."""
        logger.info(f"💾 [get_by_id] ENTRY | model={self.model.__name__} | id={id}")
        logger.debug(f"📋 Executing query for {self.model.__name__} by ID")
        result = self.db.query(self.model).filter(self.model.id == id).first()
        if result:
            logger.info(f"✅ [get_by_id] EXIT | Found {self.model.__name__} | id={id}")
        else:
            logger.debug(f"⚠️ [get_by_id] No record found | model={self.model.__name__} | id={id}")
        return result

    def get_by_id_or_raise(self, id: UUID, error_class=ResourceNotFoundError) -> T:
        """Get single record by ID or raise error."""
        logger.info(f"💾 [get_by_id_or_raise] ENTRY | model={self.model.__name__} | id={id} | error_class={error_class.__name__}")
        logger.debug(f"📋 Querying with error handling")
        resource = self.get_by_id(id)
        logger.debug(f"✓ Query completed, validating result")
        return ensure_found(resource, error_class)

    def get_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[T]:
        """Get all records with optional pagination."""
        logger.info(f"💾 [get_all] ENTRY | model={self.model.__name__} | limit={limit} | offset={offset}")
        logger.debug(f"📋 Building query for all {self.model.__name__} records")
        query = self.db.query(self.model)

        if offset:
            logger.debug(f"✓ Adding offset: {offset}")
            query = query.offset(offset)
        if limit:
            logger.debug(f"✓ Adding limit: {limit}")
            query = query.limit(limit)

        logger.debug(f"✓ Executing query")
        results = query.all()
        result_count = len(results)
        logger.info(f"✅ [get_all] EXIT | model={self.model.__name__} | count={result_count} | limit={limit} | offset={offset}")
        return results

    def filter_by_workspace(
        self,
        workspace_id: UUID,
        filters: Optional[dict] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """
        Common workspace filtering pattern.

        Used in 20+ endpoints throughout the application. Filters records
        by workspace_id and additional criteria with optional pagination.

        Args:
            workspace_id: Workspace UUID to filter by
            filters: Optional dict of field=value pairs for additional filters
            limit: Optional limit for pagination
            offset: Optional offset for pagination

        Returns:
            List of records matching criteria
        """
        logger.info(f"💾 [filter_by_workspace] ENTRY | model={self.model.__name__} | workspace_id={workspace_id} | filters={filters} | limit={limit} | offset={offset}")
        logger.debug(f"📋 Building workspace filter query")
        query = self.db.query(self.model).filter(self.model.workspace_id == workspace_id)
        logger.debug(f"✓ Workspace filter applied")

        if filters:
            logger.debug(f"📋 Applying {len(filters)} additional filters")
            for field, value in filters.items():
                if hasattr(self.model, field):
                    logger.debug(f"  ✓ Adding filter: {field}={value}")
                    query = query.filter(getattr(self.model, field) == value)
                else:
                    logger.debug(f"  ⚠️ Skipping filter - field {field} not found on {self.model.__name__}")

        if offset:
            logger.debug(f"✓ Adding offset: {offset}")
            query = query.offset(offset)
        if limit:
            logger.debug(f"✓ Adding limit: {limit}")
            query = query.limit(limit)

        logger.debug(f"✓ Executing filtered query")
        results = query.all()
        result_count = len(results)
        logger.info(f"✅ [filter_by_workspace] EXIT | model={self.model.__name__} | workspace_id={workspace_id} | count={result_count}")
        return results

    def count(self) -> int:
        """Get total count of records."""
        logger.info(f"💾 [count] ENTRY | model={self.model.__name__}")
        logger.debug(f"📋 Executing count query")
        count = self.db.query(self.model).count()
        logger.info(f"✅ [count] EXIT | model={self.model.__name__} | total_count={count}")
        return count

    def count_by_workspace(self, workspace_id: UUID) -> int:
        """Count records in workspace."""
        logger.info(f"💾 [count_by_workspace] ENTRY | model={self.model.__name__} | workspace_id={workspace_id}")
        logger.debug(f"📋 Executing workspace count query")
        count = self.db.query(self.model).filter(self.model.workspace_id == workspace_id).count()
        logger.info(f"✅ [count_by_workspace] EXIT | model={self.model.__name__} | workspace_id={workspace_id} | count={count}")
        return count

    def create(self, **kwargs) -> T:
        """Create new record."""
        logger.info(f"💾 [create] ENTRY | model={self.model.__name__} | attributes={list(kwargs.keys())}")
        logger.debug(f"📋 Creating instance with values: {kwargs}")
        instance = self.model(**kwargs)
        logger.debug(f"✓ Instance created, adding to session")
        self.db.add(instance)
        self.db.flush()  # Flush to get ID without committing
        instance_id = getattr(instance, 'id', 'N/A')
        logger.info(f"✅ [create] EXIT | model={self.model.__name__} | id={instance_id}")
        return instance

    def update(self, id: UUID, **kwargs) -> T:
        """Update record by ID."""
        logger.info(f"💾 [update] ENTRY | model={self.model.__name__} | id={id} | attributes={list(kwargs.keys())}")
        logger.debug(f"📋 Fetching record for update")
        instance = self.get_by_id_or_raise(id)
        logger.debug(f"✓ Record found, applying {len(kwargs)} updates")
        for key, value in kwargs.items():
            if hasattr(instance, key):
                logger.debug(f"  ✓ Updating {key} = {value}")
                setattr(instance, key, value)
            else:
                logger.debug(f"  ⚠️ Skipping {key} - attribute not found")
        logger.debug(f"✓ Flushing changes to database")
        self.db.flush()
        logger.info(f"✅ [update] EXIT | model={self.model.__name__} | id={id}")
        return instance

    def delete(self, id: UUID) -> bool:
        """Delete record by ID."""
        logger.info(f"💾 [delete] ENTRY | model={self.model.__name__} | id={id}")
        logger.debug(f"📋 Fetching record for deletion")
        instance = self.get_by_id(id)
        if instance:
            logger.debug(f"✓ Record found, deleting from session")
            self.db.delete(instance)
            self.db.flush()
            logger.info(f"✅ [delete] EXIT | model={self.model.__name__} | id={id} | status=DELETED")
            return True
        logger.warning(f"⚠️ [delete] Record not found | model={self.model.__name__} | id={id}")
        return False
