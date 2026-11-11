"""Tiny in-process TTL cache for expensive, slowly-changing analytics queries.

Fuel data only changes every 15 minutes, so a few minutes of caching removes
most repeated full-table aggregations. Single-process only (matches the rest
of the app: in-memory rate limiter, APScheduler).
"""

import time
from typing import Any, Callable

_STORE: dict[tuple, tuple[float, Any]] = {}
_MAX_ENTRIES = 500


def cached(key: tuple, ttl_seconds: float, compute: Callable[[], Any]) -> Any:
    now = time.monotonic()
    hit = _STORE.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = compute()
    if len(_STORE) >= _MAX_ENTRIES:
        for k in [k for k, (exp, _) in _STORE.items() if exp <= now]:
            _STORE.pop(k, None)
        if len(_STORE) >= _MAX_ENTRIES:
            _STORE.clear()
    _STORE[key] = (now + ttl_seconds, value)
    return value


def refresh(key: tuple, ttl_seconds: float, compute: Callable[[], Any]) -> Any:
    """Recompute and store unconditionally (used by scheduled warm-up jobs)."""
    value = compute()
    _STORE[key] = (time.monotonic() + ttl_seconds, value)
    return value


def clear() -> None:
    _STORE.clear()


def ttl_cached(ttl_seconds: float):
    """Decorator: cache an endpoint's result per query-parameter combination.

    `request` and `db` are ignored in the key. Exceptions are never cached.
    """
    import functools

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (
                fn.__name__,
                tuple(
                    sorted(
                        (k, v) for k, v in kwargs.items() if k not in ("request", "db")
                    )
                ),
            )
            return cached(key, ttl_seconds, lambda: fn(*args, **kwargs))

        return wrapper

    return decorator
