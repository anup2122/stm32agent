from __future__ import annotations

from typing import Callable, Hashable, TypeVar, cast


T = TypeVar("T")

_RESOLUTION_CACHE: dict[tuple[str, Hashable], object] = {}


def freeze_cache_value(value: object) -> Hashable:
    if isinstance(value, dict):
        return tuple(sorted((str(key), freeze_cache_value(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(freeze_cache_value(item) for item in value)
    if isinstance(value, (str, int, float, bool, type(None))):
        return cast(Hashable, value)
    return repr(value)


def cached_resolution(tool_name: str, cache_key: Hashable, resolver: Callable[[], T]) -> T:
    scoped_key = (tool_name, cache_key)
    cached = _RESOLUTION_CACHE.get(scoped_key)
    if cached is not None:
        return cast(T, cached)

    result = resolver()
    _RESOLUTION_CACHE[scoped_key] = result
    return result


def clear_resolution_cache(tool_name: str | None = None) -> None:
    if tool_name is None:
        _RESOLUTION_CACHE.clear()
        return

    for scoped_key in list(_RESOLUTION_CACHE):
        if scoped_key[0] == tool_name:
            _RESOLUTION_CACHE.pop(scoped_key, None)