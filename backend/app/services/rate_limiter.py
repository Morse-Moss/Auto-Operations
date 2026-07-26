from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from backend.app.core.config import get_settings


class CrawlRateLimiter:
    def __init__(self, max_per_minute: int | None = None):
        if max_per_minute is None:
            try:
                max_per_minute = int(get_settings().crawl_rate_limit_per_minute)
            except Exception:
                max_per_minute = 0
        self._max = max_per_minute or 5
        self._lock = Lock()
        self._windows: dict[int, list[float]] = defaultdict(list)

    @property
    def max_per_minute(self) -> int:
        return self._max

    def allow(self, account_id: int) -> bool:
        now = time.monotonic()
        cutoff = now - 60.0
        with self._lock:
            window = self._windows[account_id]
            self._windows[account_id] = [t for t in window if t > cutoff]
            if len(self._windows[account_id]) >= self.max_per_minute:
                return False
            self._windows[account_id].append(now)
            return True

    def reset(self, account_id: int) -> None:
        with self._lock:
            self._windows.pop(account_id, None)


_global_limiter: CrawlRateLimiter | None = None


def get_rate_limiter() -> CrawlRateLimiter:
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = CrawlRateLimiter()
    return _global_limiter
