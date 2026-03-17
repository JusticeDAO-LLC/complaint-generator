from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, Tuple[datetime, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        value = self._store.get(key)
        if value is None:
            return None
        created_at, payload = value
        if datetime.now(timezone.utc) - created_at > timedelta(seconds=self.ttl_seconds):
            self._store.pop(key, None)
            return None
        return payload

    def set(self, key: str, payload: Any) -> None:
        self._store[key] = (datetime.now(timezone.utc), payload)

    def clear(self) -> None:
        self._store.clear()
