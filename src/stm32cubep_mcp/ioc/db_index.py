from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..knowledge.cubemx_db import INDEX_VERSION as CUBEMX_DB_INDEX_VERSION
from ..knowledge.cubemx_db import build_cubemx_db_index

INDEX_VERSION = CUBEMX_DB_INDEX_VERSION


def cubemx_db_cache_root() -> Path:
    return (Path.cwd() / "generated" / "_cache" / "cubemx_db" / INDEX_VERSION).resolve()


@lru_cache(maxsize=1)
def local_cubemx_db_index() -> dict[str, object]:
    return build_cubemx_db_index(cache_root=cubemx_db_cache_root())
