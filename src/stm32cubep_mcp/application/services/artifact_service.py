from __future__ import annotations

from typing import Callable


def select_flash_artifact(
    build_result: dict[str, object],
    *,
    file_path: str | None = None,
    configured_firmware_artifact: Callable[[], str | None],
) -> tuple[str | None, str | None]:
    if isinstance(file_path, str) and file_path.strip():
        return file_path, "prompt"

    artifact = build_result.get("artifact")
    if isinstance(artifact, str) and artifact.strip():
        return artifact, "build"

    configured_artifact = configured_firmware_artifact()
    if configured_artifact:
        return configured_artifact, "project_config"

    return None, None
