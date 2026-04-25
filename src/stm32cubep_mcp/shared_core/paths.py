from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence


def unique_paths(paths: Sequence[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = os.path.normcase(str(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(path)
    return unique


def config_search_paths(env_var: str, relative_paths: Sequence[str]) -> list[Path]:
    search_paths: list[Path] = []
    env_path = os.environ.get(env_var)
    if env_path:
        search_paths.append(Path(env_path).expanduser())

    workspace_root = Path.cwd()
    for relative_path in relative_paths:
        search_paths.append((workspace_root / relative_path).expanduser())

    return unique_paths(search_paths)


def resolve_candidate_path(candidate: str, *, base_path: Path | None = None) -> Path:
    path = Path(candidate).expanduser()
    if path.is_absolute() or base_path is None:
        return path
    return (base_path.parent / path).resolve()
