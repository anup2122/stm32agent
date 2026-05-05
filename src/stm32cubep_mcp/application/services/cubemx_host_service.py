from __future__ import annotations

from pathlib import Path
from typing import Callable

from ...tools import cubemx_adapter


# Read one named section from the loaded project metadata and return it only when it is shaped like a mapping.
def project_section_metadata(
    section_name: str,
    *,
    load_project_metadata_fn: Callable[[], dict[str, object]],
) -> dict[str, object]:
    project_config = load_project_metadata_fn()
    project_data = project_config.get("data")
    if not isinstance(project_data, dict):
        return {}
    section = project_data.get(section_name, {})
    return section if isinstance(section, dict) else {}


def load_firmware_metadata(*, load_project_metadata_fn: Callable[[], dict[str, object]]) -> dict[str, object]:
    return project_section_metadata("firmware", load_project_metadata_fn=load_project_metadata_fn)


def load_build_metadata(*, load_project_metadata_fn: Callable[[], dict[str, object]]) -> dict[str, object]:
    return project_section_metadata("build", load_project_metadata_fn=load_project_metadata_fn)


def load_cubemx_metadata(*, load_project_metadata_fn: Callable[[], dict[str, object]]) -> dict[str, object]:
    return project_section_metadata("cubemx", load_project_metadata_fn=load_project_metadata_fn)


# Resolve the configured CubeMX log path into an absolute filesystem path when one is present.
def configured_cubemx_log_path(
    *,
    load_cubemx_metadata_fn: Callable[[], dict[str, object]],
) -> Path | None:
    cubemx_metadata = load_cubemx_metadata_fn()
    log_path = cubemx_metadata.get("log_path")
    if not isinstance(log_path, str) or not log_path.strip():
        return None
    return Path(log_path).expanduser().resolve()


def cubemx_tool_entry(
    *,
    load_tools_local_config_fn: Callable[[], dict[str, object]],
) -> dict[str, object]:
    return cubemx_adapter.cubemx_tool_entry(load_tools_local_config_fn)


def derive_cubemx_candidates(
    *,
    resolve_cubeide_path_fn: Callable[[], str],
) -> list[Path]:
    return cubemx_adapter.derive_cubemx_candidates(resolve_cubeide_path_fn)


def derive_java_candidates(
    *,
    resolve_cubeide_path_fn: Callable[[], str],
    host_platform: str,
) -> list[Path]:
    return cubemx_adapter.derive_java_candidates(resolve_cubeide_path_fn, host_platform)


def resolve_java_path(
    *,
    resolve_cubeide_path_fn: Callable[[], str],
    host_platform: str,
) -> str | None:
    return cubemx_adapter.resolve_java_path(resolve_cubeide_path_fn, host_platform)


def discover_cubemx(
    *,
    host_platform: str,
    load_tools_local_config_fn: Callable[[], dict[str, object]],
    resolve_candidate_path_fn: Callable[[str, Path | None], Path],
    resolve_cubeide_path_fn: Callable[[], str],
) -> dict[str, object]:
    return cubemx_adapter.discover_cubemx(
        host_platform=host_platform,
        load_tools_local_config=load_tools_local_config_fn,
        resolve_candidate_path=resolve_candidate_path_fn,
        resolve_cubeide_path=resolve_cubeide_path_fn,
    )


def resolve_cubemx_launcher(
    *,
    discover_cubemx_fn: Callable[[], dict[str, object]],
) -> dict[str, object]:
    return cubemx_adapter.resolve_cubemx_launcher(discover_cubemx_fn())
