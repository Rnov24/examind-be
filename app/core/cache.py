import time
import threading
from typing import Any, Optional, Dict, Tuple


class MemoryCache:
    """Thread-safe in-memory cache with Time-To-Live (TTL) expiration.
    Used for caching scoped DB user context, AI question explanations, and assistant responses.
    """

    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            val, expiry = entry
            if time.time() > expiry:
                del self._cache[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl_seconds = ttl if ttl is not None else self._default_ttl
        expiry = time.time() + ttl_seconds
        with self._lock:
            self._cache[key] = (value, expiry)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        now = time.time()
        with self._lock:
            expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
            for k in expired_keys:
                del self._cache[k]
            return len(expired_keys)

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)


# Global singleton cache instance
memory_cache = MemoryCache(default_ttl=300)
