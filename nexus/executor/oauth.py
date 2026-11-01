"""PayPal OAuth2 token manager - cached, auto-refreshing via Redis."""
import os
import time
import threading
import logging
import httpx
from nexus.storage.redis_client import RedisManager

logger = logging.getLogger("nexus.oauth")

REDIS_OAUTH_KEY = "nexus:oauth:paypal:token"


class PayPalOAuthManager:
    def __init__(self, redis_mgr: RedisManager = None):
        self.client_id = os.environ.get("PAYPAL_CLIENT_ID", "").strip("\"'")
        self.client_secret = os.environ.get("PAYPAL_CLIENT_SECRET", "").strip("\"'")
        self.base_url = os.environ.get("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com").strip("\"'").rstrip("/")
        self.redis = redis_mgr or RedisManager.get_instance()
        self._local_token: str = ""
        self._local_expires_at: float = 0.0
        self._lock = threading.Lock()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_token(self) -> str:
        if not self.is_configured():
            raise RuntimeError("PayPal credentials not configured")

        # 1. Check shared Redis cache
        cached_token = self.redis.get(REDIS_OAUTH_KEY)
        if cached_token:
            self._local_token = cached_token
            return cached_token

        # 2. Check local in-memory fallback
        with self._lock:
            # Re-check Redis under lock
            cached_token = self.redis.get(REDIS_OAUTH_KEY)
            if cached_token:
                self._local_token = cached_token
                return cached_token

            if self._local_token and time.time() < self._local_expires_at - 60:
                return self._local_token

            # 3. Refresh live token from PayPal
            self._refresh()
            return self._local_token

    def _refresh(self):
        url = f"{self.base_url}/v1/oauth2/token"
        resp = httpx.post(
            url,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        expires_in = data.get("expires_in", 3600)

        self._local_token = token
        self._local_expires_at = time.time() + expires_in

        # Store in shared Redis with safety TTL buffer (120s before expiry)
        ttl = max(60, expires_in - 120)
        self.redis.set(REDIS_OAUTH_KEY, token, ex=ttl)
        logger.info("PayPal OAuth2 token refreshed and shared via Redis (TTL=%ds)", ttl)

    def invalidate(self):
        with self._lock:
            self._local_token = ""
            self._local_expires_at = 0.0
            self.redis.delete(REDIS_OAUTH_KEY)
            logger.info("PayPal OAuth2 token invalidated across local and Redis cache")
