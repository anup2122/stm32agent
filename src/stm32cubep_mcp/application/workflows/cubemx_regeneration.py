from __future__ import annotations

from typing import Callable


def orchestrate_cubemx_regeneration(
    *,
    validate_build: bool,
    timeout_seconds: int,
    build_timeout_seconds: int,
    configured_cubemx_request: Callable[[], dict[str, object]],
    regenerate_project: Callable[..., dict[str, object]],
) -> dict[str, object]:
    cubemx_request = configured_cubemx_request()
    missing_fields = list(cubemx_request.get("missing_fields", [])) if isinstance(cubemx_request.get("missing_fields"), list) else []
    if missing_fields:
        return {
            "server": "orchestrator",
            "workflow": "cubemx_regeneration",
            "success": False,
            "cubemx_request": cubemx_request,
            "message": "Missing required CubeMX project metadata in stm32-project.json: " + ", ".join(missing_fields),
        }

    result = regenerate_project(
        ioc_path=str(cubemx_request["ioc_path"]),
        project_name=str(cubemx_request["project_name"]),
        project_toolchain=str(cubemx_request["project_toolchain"]),
        project_path=str(cubemx_request["project_path"]),
        script_path=str(cubemx_request["script_path"]) if isinstance(cubemx_request.get("script_path"), str) else None,
        validate_build=validate_build,
        timeout_seconds=timeout_seconds,
        build_timeout_seconds=build_timeout_seconds,
    )
    return {
        "server": "orchestrator",
        "workflow": "cubemx_regeneration",
        "cubemx_request": cubemx_request,
        "result": result,
        "success": bool(result.get("success")),
    }
