from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


def paginated(items: Iterable[Any], page: int = 1, page_size: int = 20) -> dict:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    materialized = list(items)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return {
        "total": len(materialized),
        "page": safe_page,
        "page_size": safe_page_size,
        "items": materialized[start:end],
    }


def paginate_statement(
    db: Session,
    statement: Select,
    page: int = 1,
    page_size: int = 20,
    serializer: Callable[[Sequence[Any]], list] | None = None,
) -> dict:
    """Database-side pagination with the same response shape as `paginated`.

    `statement` must already include filters and `order_by`. The total is computed
    with a COUNT over the statement, and only the current page rows are loaded via
    LIMIT/OFFSET. `serializer` receives the current-page rows as a sequence and
    returns the serialized items list (enabling per-page batch prefetching);
    when omitted, the raw rows are returned as items.
    """
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    rows = db.scalars(
        statement.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
    ).all()
    items = serializer(rows) if serializer is not None else list(rows)
    return {
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "items": items,
    }
