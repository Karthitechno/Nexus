"""NEXUS Redis Client and Connection Pool Manager.

Provides a thread-safe singleton connection pool, health checks,
and safe execution with graceful degradation if Redis is unavailable.
"""
import os
import logging
from typing import Optional, Any, Dict, List, Tuple

logger = logging.getLogger("nexus.storage.redis")


class RedisManager:
    _instance: Optional["RedisManager"] = None

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = (
            redis_url
            or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        ).strip("\"'")
        self._pool = None
        self._client = None
        self._available = False
        self._init_client()

    @classmethod
    def get_instance(cls, redis_url: Optional[str] = None) -> "RedisManager":
        if cls._instance is None:
            cls._instance = cls(redis_url=redis_url)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Used in test fixtures."""
        if cls._instance and cls._instance._client:
            try:
                cls._instance._client.close()
            except Exception:
                pass
        cls._instance = None

    def _init_client(self):
        try:
            import redis
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                decode_responses=True,
            )
            self._client = redis.Redis(connection_pool=self._pool)
            # Test connection
            self._client.ping()
            self._available = True
            logger.info("Connected to Redis at %s", self.redis_url)
        except Exception as e:
            self._available = False
            self._client = None
            logger.warning("Redis is not available (%s). Operating in fallback mode.", e)

    def is_available(self) -> bool:
        if not self._available or not self._client:
            return False
        try:
            return bool(self._client.ping())
        except Exception:
            self._available = False
            return False

    def get_client(self):
        return self._client if self.is_available() else None

    # --- Safe Operations with Graceful Degradation ---

    def get(self, key: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            return self._client.get(key)
        except Exception as e:
            logger.warning("Redis GET failed on key '%s': %s", key, e)
            return None

    def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        nx: bool = False,
    ) -> bool:
        """Set key value. Returns True if set succeeded, False otherwise (e.g. if nx=True and key existed)."""
        if not self.is_available():
            return False
        try:
            res = self._client.set(key, value, ex=ex, nx=nx)
            return bool(res)
        except Exception as e:
            logger.warning("Redis SET failed on key '%s': %s", key, e)
            return False

    def delete(self, *keys: str) -> int:
        if not self.is_available() or not keys:
            return 0
        try:
            return self._client.delete(*keys)
        except Exception as e:
            logger.warning("Redis DELETE failed on keys '%s': %s", keys, e)
            return 0

    def expire(self, key: str, seconds: int) -> bool:
        if not self.is_available():
            return False
        try:
            return bool(self._client.expire(key, seconds))
        except Exception as e:
            logger.warning("Redis EXPIRE failed on key '%s': %s", key, e)
            return False

    def hset(self, key: str, mapping: Dict[str, Any]) -> int:
        if not self.is_available():
            return 0
        try:
            return self._client.hset(key, mapping=mapping)
        except Exception as e:
            logger.warning("Redis HSET failed on key '%s': %s", key, e)
            return 0

    def hgetall(self, key: str) -> Dict[str, str]:
        if not self.is_available():
            return {}
        try:
            return self._client.hgetall(key)
        except Exception as e:
            logger.warning("Redis HGETALL failed on key '%s': %s", key, e)
            return {}

    def lpush(self, key: str, *values: str) -> int:
        if not self.is_available() or not values:
            return 0
        try:
            return self._client.lpush(key, *values)
        except Exception as e:
            logger.warning("Redis LPUSH failed on key '%s': %s", key, e)
            return 0

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        if not self.is_available():
            return []
        try:
            return self._client.lrange(key, start, end)
        except Exception as e:
            logger.warning("Redis LRANGE failed on key '%s': %s", key, e)
            return []

    def ltrim(self, key: str, start: int, end: int) -> bool:
        if not self.is_available():
            return False
        try:
            return bool(self._client.ltrim(key, start, end))
        except Exception as e:
            logger.warning("Redis LTRIM failed on key '%s': %s", key, e)
            return False

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, int]:
        """Atomic rate limiter. Returns (allowed, current_count, retry_after_seconds)."""
        if not self.is_available():
            return True, 0, 0
        try:
            current = self._client.incr(key)
            if current == 1:
                self._client.expire(key, window_seconds)
            ttl = max(self._client.ttl(key), 1)
            if current > max_requests:
                return False, current, ttl
            return True, current, 0
        except Exception as e:
            logger.warning("Redis rate limit check failed on key '%s': %s", key, e)
            return True, 0, 0
