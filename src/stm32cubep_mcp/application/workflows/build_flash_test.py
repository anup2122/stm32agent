from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable


async def orchestrate_build_then_flash(
    *,
    target: str | None,
    clean: bool,
    file_path: str | None,
    build_timeout_seconds: int,
    flash_timeout_seconds: int,
    verify_mode: object,
    post_action: object,
    build_project: Callable[..., dict[str, object]],
    flash_firmware: Callable[..., Awaitable[dict[str, object]]],
    select_flash_artifact: Callable[[dict[str, object], str | None], tuple[str | None, str | None]],
) -> dict[str, object]:
    build_result = build_project(
        target=target,
        clean=clean,
        timeout_seconds=build_timeout_seconds,
    )
    if not build_result.get("success"):
        return {
            "server": "orchestrator",
            "workflow": "build_then_flash",
            "success": False,
            "stage": "build",
            "build_result": build_result,
            "message": "Build failed, so the flash step was skipped.",
        }

    artifact_path, artifact_source = select_flash_artifact(build_result, file_path=file_path)
    if not artifact_path:
        return {
            "server": "orchestrator",
            "workflow": "build_then_flash",
            "success": False,
            "stage": "artifact_resolution",
            "build_result": build_result,
            "message": "Build succeeded, but no firmware artifact was available for the flash step.",
        }

    resolved_artifact = Path(artifact_path).expanduser()
    if not resolved_artifact.is_file():
        return {
            "server": "orchestrator",
            "workflow": "build_then_flash",
            "success": False,
            "stage": "artifact_resolution",
            "build_result": build_result,
            "firmware_path": str(resolved_artifact),
            "artifact_source": artifact_source,
            "message": f"Build succeeded, but the flash artifact was not found: {resolved_artifact}",
        }

    flash_result = await flash_firmware(
        file_path=str(resolved_artifact),
        timeout_seconds=flash_timeout_seconds,
        verify_mode=verify_mode,
        post_action=post_action,
    )
    return {
        "server": "orchestrator",
        "workflow": "build_then_flash",
        "success": bool(flash_result.get("success")),
        "stage": "flash" if not flash_result.get("success") else "completed",
        "target": target,
        "clean": clean,
        "firmware_path": str(resolved_artifact),
        "artifact_source": artifact_source,
        "build_result": build_result,
        "flash_result": flash_result,
        "message": (
            f"Build and flash succeeded using artifact {resolved_artifact}."
            if flash_result.get("success")
            else "Build succeeded, but the flash step failed. Inspect the flash result for details."
        ),
    }
