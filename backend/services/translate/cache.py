"""Translation cache: Redis when available, in-process dict otherwise.

Keyed by sha256(text) + target language so repeated phrases cost nothing
(INTRODUCTION §6 cost awareness). Falls back silently to memory — a missing
Redis must never break translation, and CI runs without one.
"""

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger("listenup.translate.cache")

TTL_SECONDS = 7 * 24 * 3600


def cache_key(namespace: str, text: str, target_lang: str, extra: str = "") -> str:
    digest = hashlib.sha256(text.strip().lower().encode()).hexdigest()[:32]
    return f"listenup:{namespace}:{digest}:{target_lang}:{extra}"


class TranslationCache:
    """get/set JSON blobs; counts hits/misses for the cost audit."""

    def __init__(self) -> None:
        self._redis: Any = None
        self._memory: dict[str, str] = {}
        self._connected = False
        self.hits = 0
        self.misses = 0

    async def _client(self) -> Any:
        if self._connected:
            return self._redis
        self._connected = True
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            import redis.asyncio as redis_async

            client = redis_async.from_url(url, socket_connect_timeout=1, socket_timeout=1)
            await client.ping()
            self._redis = client
            logger.info("translate_cache backend=redis url=%s", url.split("@")[-1])
        except Exception:
            self._redis = None
            logger.info("translate_cache backend=memory (Redis unavailable)")
        return self._redis

    async def get(self, key: str) -> dict | None:
        client = await self._client()
        raw: str | None
        if client is not None:
            try:
                raw = await client.get(key)
            except Exception:
                raw = self._memory.get(key)
        else:
            raw = self._memory.get(key)
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        cached: dict = json.loads(raw)  # trusted boundary: we wrote this
        return cached

    async def set(self, key: str, value: dict) -> None:
        raw = json.dumps(value)
        client = await self._client()
        if client is not None:
            try:
                await client.set(key, raw, ex=TTL_SECONDS)
                return
            except Exception:
                pass
        self._memory[key] = raw

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


_cache: TranslationCache | None = None


def get_cache() -> TranslationCache:
    global _cache
    if _cache is None:
        _cache = TranslationCache()
    return _cache
