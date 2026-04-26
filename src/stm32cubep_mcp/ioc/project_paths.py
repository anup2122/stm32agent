from __future__ import annotations

from pathlib import Path
from typing import Callable


def configured_ioc_path(
    load_firmware_metadata_fn: Callable[[], dict[str, object]],
    *,
    cwd: Path | None = None,
) -> str | None:
    firmware = load_firmware_metadata_fn()
    ioc_path = firmware.get("ioc_path")
    if isinstance(ioc_path, str) and ioc_path.strip():
        base_dir = cwd or Path.cwd()
        return str((base_dir / ioc_path).resolve())
    return None


def read_ioc_project_manager_value(ioc_path: Path | None, key: str) -> str | None:
    if ioc_path is None or not ioc_path.is_file():
        return None

    prefix = f"ProjectManager.{key}="
    for raw_line in ioc_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw_line.startswith(prefix):
            return raw_line.partition("=")[2].strip()
    return None


def cubeide_project_dir_candidates(
    project_root: Path | None,
    ioc_path: Path | None,
    project_name: str | None = None,
    *,
    read_ioc_project_manager_value_fn: Callable[[Path | None, str], str | None] = read_ioc_project_manager_value,
) -> list[Path]:
    if project_root is None:
        return []

    toolchain_location = read_ioc_project_manager_value_fn(ioc_path, "ToolChainLocation")

    def candidate_for(base_root: Path) -> Path:
        if toolchain_location:
            return (base_root / toolchain_location / "STM32CubeIDE").resolve()
        return (base_root / "STM32CubeIDE").resolve()

    candidates: list[Path] = [candidate_for(project_root)]
    if isinstance(project_name, str) and project_name.strip():
        named_root = (project_root / project_name.strip()).resolve()
        named_candidate = candidate_for(named_root)
        if named_candidate not in candidates:
            candidates.append(named_candidate)

    return candidates


def resolve_completion_marker(
    project_root: Path | None,
    ioc_path: Path | None,
    project_name: str | None = None,
    *,
    cubeide_project_dir_candidates_fn: Callable[[Path | None, Path | None, str | None], list[Path]] = cubeide_project_dir_candidates,
) -> Path | None:
    candidates = cubeide_project_dir_candidates_fn(project_root, ioc_path, project_name)
    if not candidates:
        return None

    for project_dir in candidates:
        marker_path = project_dir / ".project"
        if marker_path.is_file():
            return marker_path
    return candidates[0] / ".project"


def resolve_completion_markers(
    project_root: Path | None,
    ioc_path: Path | None,
    project_name: str | None = None,
    *,
    cubeide_project_dir_candidates_fn: Callable[[Path | None, Path | None, str | None], list[Path]] = cubeide_project_dir_candidates,
) -> list[Path]:
    markers: list[Path] = []
    for project_dir in cubeide_project_dir_candidates_fn(project_root, ioc_path, project_name):
        markers.append(project_dir / ".project")
        markers.append(project_dir / ".cproject")
    return markers


def discover_ioc_path(
    ioc_path: str | None = None,
    *,
    configured_ioc_path_fn: Callable[[], str | None],
) -> dict[str, object]:
    explicit_path = Path(ioc_path).resolve() if isinstance(ioc_path, str) and ioc_path.strip() else None
    configured_path_value = configured_ioc_path_fn()
    configured_path = Path(configured_path_value).resolve() if configured_path_value else None

    if explicit_path is not None:
        return {
            "requested_path": str(explicit_path),
            "configured_path": str(configured_path) if configured_path else None,
            "resolved_path": str(explicit_path) if explicit_path.is_file() else None,
            "resolution_source": "requested" if explicit_path.is_file() else None,
            "discovered_ioc_files": [],
            "search_roots": [],
        }

    if configured_path is not None and configured_path.is_file():
        return {
            "requested_path": None,
            "configured_path": str(configured_path),
            "resolved_path": str(configured_path),
            "resolution_source": "project_config",
            "discovered_ioc_files": [],
            "search_roots": [],
        }

    return {
        "requested_path": str(explicit_path) if explicit_path else None,
        "configured_path": str(configured_path) if configured_path else None,
        "resolved_path": None,
        "resolution_source": None,
        "discovered_ioc_files": [],
        "search_roots": [],
    }


def default_ioc_path(*, discover_ioc_path_fn: Callable[[], dict[str, object]]) -> str | None:
    resolved = discover_ioc_path_fn().get("resolved_path")
    return str(resolved) if isinstance(resolved, str) else None
