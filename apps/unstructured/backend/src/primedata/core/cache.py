"""Simple in-memory cache with TTL support."""

from typing import Optional, Any, Callable
from datetime import datetime, timedelta
from functools import wraps

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class SimpleCache:
    """In-memory cache with TTL support."""

    def __init__(self, default_ttl: int = 300) -> None:
        """Initialize the cache with a default time-to-live.

        :param default_ttl: Default time-to-live in seconds (default: 5 minutes).
        """
        self._cache = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache if it exists and has not expired.

        :param key: Cache key to look up.
        :return: Cached value if found and not expired, None otherwise.
        """
        logger.debug(f"💾 Cache.get(key={key})")
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.utcnow() < expiry:
                logger.debug(f"✅ Cache hit: {key}")
                return value
            # Remove expired entry
            del self._cache[key]
            logger.debug(f"❌ Cache entry expired: {key}")
        logger.debug(f"❌ Cache miss: {key}")
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in the cache with an expiration time.

        :param key: Cache key to store under.
        :param value: Value to cache.
        :param ttl: Time-to-live in seconds (uses default if not specified).
        """
        logger.debug(f"💾 Cache.set(key={key}, value_type={type(value).__name__}, ttl={ttl})")
        ttl = ttl or self._default_ttl
        expiry = datetime.utcnow() + timedelta(seconds=ttl)
        self._cache[key] = (value, expiry)
        logger.info(f"💾 ✅ Cache set: {key} (ttl={ttl}s, expires={expiry})")
        logger.debug(f"📋 Cache size: {len(self._cache)} entries")

    def delete(self, key: str) -> None:
        """Delete a single cache entry by key.

        :param key: Cache key to delete.
        """
        logger.debug(f"💾 Cache.delete(key={key})")
        if key in self._cache:
            del self._cache[key]
            logger.info(f"💾 ✅ Cache deleted: {key}")
        else:
            logger.debug(f"⚠️ Cache.delete: key not found - {key}")

    def clear(self) -> None:
        """Remove all entries from the cache regardless of expiration."""
        entry_count = len(self._cache)
        self._cache.clear()
        logger.info(f"💾 ✅ Cache cleared: removed {entry_count} entries")

    def cleanup_expired(self) -> None:
        """Scan the cache and remove all entries that have passed their expiry time."""
        logger.debug(f"💾 Cache.cleanup_expired() - starting cleanup")
        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items() if now >= expiry
        ]
        removed_count = len(expired_keys)
        for key in expired_keys:
            del self._cache[key]
        if expired_keys:
            logger.info(f"💾 ✅ Cache cleanup: removed {removed_count} expired entries")
        else:
            logger.debug(f"💾 Cache cleanup: no expired entries found")
        logger.debug(f"📋 Cache size after cleanup: {len(self._cache)} entries")


# Global cache instance
_default_cache = SimpleCache(default_ttl=300)


def cached(ttl: int = 300, key_prefix: str = "") -> Callable:
    """Decorator to cache function results with a configurable TTL.

    :param ttl: Time-to-live in seconds for cached results.
    :param key_prefix: Prefix prepended to the auto-generated cache key.
    :return: Decorator that wraps the function with caching logic.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name, args, and kwargs
            # Note: This is a simple implementation; complex args may not serialize well
            logger.debug(f"💾 Caching function: {func.__name__}, key_prefix={key_prefix}")
            try:
                cache_key = f"{key_prefix}:{func.__name__}"
                # Add args to key (simple serialization)
                if args:
                    cache_key += f":{str(args)}"
                if kwargs:
                    cache_key += f":{str(kwargs)}"
                logger.debug(f"📋 Generated cache key: {cache_key}")
            except Exception as e:
                # If we can't create a cache key, just call the function
                logger.error(f"❌ Failed to generate cache key: {e}", exc_info=True)
                return func(*args, **kwargs)

            # Try to get from cache
            result = _default_cache.get(cache_key)
            if result is not None:
                logger.info(f"💾 ✅ Cache hit: {cache_key}")
                return result

            # Cache miss - call function and cache result
            logger.debug(f"💾 Cache miss: {cache_key}, calling function")
            result = func(*args, **kwargs)
            _default_cache.set(cache_key, result, ttl)
            logger.info(f"💾 ✅ Cached result: {cache_key} (ttl={ttl}s)")
            return result

        return wrapper

    return decorator


# Convenience functions
def get_cache() -> SimpleCache:
    """Get the default global cache instance.

    :return: The singleton SimpleCache instance.
    """
    logger.debug(f"💾 get_cache() - returning default cache instance")
    return _default_cache


def cache_get(key: str) -> Optional[Any]:
    """Get a value from the default cache by key.

    :param key: Cache key to look up.
    :return: Cached value if found and not expired, None otherwise.
    """
    logger.debug(f"💾 cache_get(key={key})")
    result = _default_cache.get(key)
    logger.debug(f"💾 cache_get result: {result is not None}")
    return result


def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Store a value in the default cache.

    :param key: Cache key to store under.
    :param value: Value to cache.
    :param ttl: Time-to-live in seconds (uses default if not specified).
    """
    logger.debug(f"💾 cache_set(key={key}, value_type={type(value).__name__}, ttl={ttl})")
    _default_cache.set(key, value, ttl)
    logger.info(f"💾 ✅ Value cached: key={key}, ttl={ttl or _default_cache._default_ttl}s")


def cache_delete(key: str) -> None:
    """Delete a value from the default cache.

    :param key: Cache key to delete.
    """
    logger.debug(f"💾 cache_delete(key={key})")
    _default_cache.delete(key)
    logger.info(f"💾 ✅ Cache entry deleted: {key}")


def cache_clear() -> None:
    """Clear all entries from the default cache."""
    logger.debug(f"💾 cache_clear()")
    entry_count = len(_default_cache._cache)
    _default_cache.clear()
    logger.info(f"💾 ✅ Cache cleared: removed {entry_count} entries")
