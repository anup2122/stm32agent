from __future__ import annotations

from pathlib import Path
from typing import Callable


# Assemble a combined CubeMX capabilities report from tool discovery, IOC discovery, and shared configuration state.
def build_cubemx_capabilities(
    *,
    discover_cubemx_fn: Callable[[], dict[str, object]],
    discover_ioc_path_fn: Callable[[], dict[str, object]],
    load_project_metadata_fn: Callable[[], dict[str, object]],
    load_tools_local_config_fn: Callable[[], dict[str, object]],
    summarize_config_status_fn: Callable[[dict[str, object]], dict[str, object]],
) -> dict[str, object]:
    cubemx_discovery = discover_cubemx_fn()
    ioc_discovery = discover_ioc_path_fn()
    return {
        "server": "cubemx",
        "implemented": True,
        "capabilities": {
            "ioc_parse": True,
            "ioc_search": True,
            "project_regeneration": True,
            "build_validation": True,
        },
        "tool_discovery": cubemx_discovery,
        "ioc_discovery": ioc_discovery,
        "default_ioc_path": ioc_discovery.get("resolved_path"),
        "project_config": summarize_config_status_fn(load_project_metadata_fn()),
        "tools_config": summarize_config_status_fn(load_tools_local_config_fn()),
    }


# Resolve the target IOC file, fail clearly when none is available, and otherwise return its parsed summary.
def parse_ioc_summary(
    *,
    ioc_path: str | None,
    discover_ioc_path_fn: Callable[[str | None], dict[str, object]],
    parse_ioc_properties_fn: Callable[[Path], dict[str, str]],
    summarize_ioc_fn: Callable[[Path, dict[str, str]], dict[str, object]],
) -> dict[str, object]:
    ioc_discovery = discover_ioc_path_fn(ioc_path)
    resolved_path = ioc_discovery.get("resolved_path")
    if not isinstance(resolved_path, str):
        return {
            "success": False,
            "implemented": True,
            "server": "cubemx",
            "operation": "parse_ioc",
            "ioc_path": ioc_path,
            "ioc_exists": False,
            "ioc_discovery": ioc_discovery,
            "message": "No IOC file could be resolved. Set firmware.ioc_path in config/stm32-project.jsonc.",
        }

    resolved_ioc = Path(resolved_path)
    properties = parse_ioc_properties_fn(resolved_ioc)
    summary = summarize_ioc_fn(resolved_ioc, properties)
    return {
        "success": True,
        "implemented": True,
        "server": "cubemx",
        "operation": "parse_ioc",
        "ioc_path": str(resolved_ioc),
        "ioc_exists": True,
        "ioc_discovery": ioc_discovery,
        "summary": summary,
        "message": f"Parsed IOC metadata from {resolved_ioc.name}.",
    }
