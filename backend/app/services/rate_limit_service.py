from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60.0
_MAX_ATTEMPTS = 7
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def _client_host(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def check_rate_limit(request: Request, scope: str, subject: str = "") -> None:
    now = monotonic()
    key = f"{scope}:{_client_host(request)}:{subject.strip().lower()}"
    bucket = _BUCKETS[key]
    while bucket and now - bucket[0] > _WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _MAX_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")


def record_rate_limit_failure(request: Request, scope: str, subject: str = "") -> None:
    check_rate_limit(request, scope, subject)
    key = f"{scope}:{_client_host(request)}:{subject.strip().lower()}"
    _BUCKETS[key].append(monotonic())


def clear_rate_limit_state() -> None:
    _BUCKETS.clear()
