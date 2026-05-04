from __future__ import annotations

from pathlib import Path
from typing import Callable


def normalize_project_toolchain(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    lowered = value.strip().lower()
    if lowered in {"cubeide", "stm32cubeide"}:
        return "STM32CubeIDE"
    return value.strip()


def resolve_project_path(candidate: object) -> Path | None:
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    return Path(candidate).expanduser().resolve()


def resolve_cubemx_project_inputs(
    *,
    ioc_path: str | None = None,
    project_name: str | None = None,
    project_toolchain: str | None = None,
    project_path: str | None = None,
    script_path: str | None = None,
    output_root: str | None = None,
    discover_ioc_path_fn: Callable[[str | None], dict[str, object]],
    load_cubemx_metadata_fn: Callable[[], dict[str, object]],
    load_build_metadata_fn: Callable[[], dict[str, object]],
    resolve_completion_marker_fn: Callable[[Path | None, Path | None, str | None], Path | None],
    resolve_completion_markers_fn: Callable[[Path | None, Path | None, str | None], list[Path]],
) -> dict[str, object]:
    ioc_discovery = discover_ioc_path_fn(ioc_path)
    resolved_ioc_path = ioc_discovery.get("resolved_path")
    resolved_ioc = Path(resolved_ioc_path).resolve() if isinstance(resolved_ioc_path, str) else None
    resolution_source = str(ioc_discovery.get("resolution_source") or "")

    cubemx_metadata = load_cubemx_metadata_fn()
    build_metadata = load_build_metadata_fn()
    requested_ioc_project_root = resolved_ioc.parent if resolved_ioc is not None and resolution_source == "requested" else None
    resolved_project_name = (
        project_name
        or (resolved_ioc.stem if requested_ioc_project_root is not None else "")
        or str(cubemx_metadata.get("project_name") or "").strip()
        or str(build_metadata.get("project_name") or "").strip()
        or (resolved_ioc.stem if resolved_ioc is not None else "")
    )
    resolved_toolchain = normalize_project_toolchain(
        project_toolchain
        or cubemx_metadata.get("project_toolchain")
        or build_metadata.get("system")
    )
    resolved_project_root = (
        resolve_project_path(project_path)
        or requested_ioc_project_root
        or resolve_project_path(cubemx_metadata.get("project_path"))
        or resolve_project_path(output_root)
    )
    resolved_script_path = (
        resolve_project_path(script_path)
        or ((requested_ioc_project_root / "script.txt") if requested_ioc_project_root is not None else None)
        or resolve_project_path(cubemx_metadata.get("script_path"))
        or ((resolved_project_root / "script.txt") if resolved_project_root is not None else None)
    )
    completion_marker = resolve_completion_marker_fn(resolved_project_root, resolved_ioc, resolved_project_name)
    completion_markers = resolve_completion_markers_fn(resolved_project_root, resolved_ioc, resolved_project_name)

    missing_fields: list[str] = []
    if resolved_ioc is None:
        missing_fields.append("ioc_path")
    if not resolved_project_name:
        missing_fields.append("project_name")
    if resolved_toolchain is None:
        missing_fields.append("project_toolchain")
    if resolved_project_root is None:
        missing_fields.append("project_path")

    return {
        "ioc_discovery": ioc_discovery,
        "ioc_path": str(resolved_ioc) if resolved_ioc is not None else None,
        "project_name": resolved_project_name or None,
        "project_toolchain": resolved_toolchain,
        "project_path": str(resolved_project_root) if resolved_project_root is not None else None,
        "script_path": str(resolved_script_path) if resolved_script_path is not None else None,
        "completion_marker": str(completion_marker) if completion_marker is not None else None,
        "completion_markers": [str(marker) for marker in completion_markers],
        "missing_fields": missing_fields,
    }


def resolve_generation_root(ioc_path: Path, output_root: str | None = None, project_path: str | None = None, *, load_cubemx_metadata_fn: Callable[[], dict[str, object]]) -> Path:
    if isinstance(project_path, str) and project_path.strip():
        return Path(project_path).expanduser().resolve()
    if isinstance(output_root, str) and output_root.strip():
        return Path(output_root).expanduser().resolve()
    configured_project_path = load_cubemx_metadata_fn().get("project_path")
    if isinstance(configured_project_path, str) and configured_project_path.strip():
        return Path(configured_project_path).expanduser().resolve()
    raise ValueError("CubeMX project_path is required. Set cubemx.project_path in config/stm32-project.jsonc.")


def build_cubemx_script(ioc_path: Path, project_name: str, project_toolchain: str, project_path: Path) -> str:
    return "\n".join(
        [
            f'config load "{ioc_path}"',
            f'project name "{project_name}"',
            f'project toolchain "{project_toolchain}"',
            f'project path "{project_path}"',
            "project generate",
            "exit_mx",
            "",
        ]
    )


def regeneration_root(
    ioc_path: Path,
    output_root: str | None = None,
    project_path: str | None = None,
    *,
    resolve_generation_root_fn: Callable[[Path, str | None, str | None], Path],
    load_build_metadata_fn: Callable[[], dict[str, object]],
) -> Path | None:
    explicit_root = resolve_generation_root_fn(ioc_path, output_root, project_path)
    if explicit_root.exists():
        return explicit_root
    build_metadata = load_build_metadata_fn()
    configured_project_path = build_metadata.get("project_path")
    if isinstance(configured_project_path, str) and Path(configured_project_path).exists():
        return Path(configured_project_path).resolve()
    return None
