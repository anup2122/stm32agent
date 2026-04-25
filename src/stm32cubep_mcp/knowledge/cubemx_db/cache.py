from __future__ import annotations

import json
from pathlib import Path


def write_index_cache(cache_root: Path, name: str, payload: object) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / name
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def read_index_cache(cache_root: Path, name: str) -> object:
    target = cache_root / name
    return json.loads(target.read_text(encoding="utf-8"))
