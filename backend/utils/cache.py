# backend/utils/cache.py
import time
from functools import wraps
from typing import Callable, Any, Tuple

def memoize_ttl(ttl_seconds: int = 300):
    """
    Super-simple in-process TTL cache decorator.
    Uses (args, sorted(kwargs)) as the key.
    """
    def deco(fn: Callable):
        cache: dict[Tuple[Any, ...], Tuple[Any, float]] = {}

        @wraps(fn)
        def wrapped(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            if key in cache:
                val, exp = cache[key]
                if now < exp:
                    return val
            val = fn(*args, **kwargs)
            cache[key] = (val, now + ttl_seconds)
            return val

        def cache_clear():
            cache.clear()

        wrapped.cache_clear = cache_clear  # type: ignore[attr-defined]
        return wrapped
    return deco
