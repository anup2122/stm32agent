from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from .classifiers import (
    EXISTING_PROJECT_TOKENS,
    NEW_DEVICE_TOKENS,
    NEW_PROJECT_TOKENS,
    looks_like_engineering_feature_spec,
)


def _load_project_data(project_metadata_loader: Callable[[], dict[str, object]] | None) -> dict[str, object]:
    if project_metadata_loader is None:
        return {}
    project_config = project_metadata_loader()
    if not isinstance(project_config, dict):
        return {}
    project_data = project_config.get("data")
    return project_data if isinstance(project_data, dict) else {}


def configured_ioc_path(
    *,
    project_metadata_loader: Callable[[], dict[str, object]] | None = None,
    cwd_resolver: Callable[[], Path] | None = None,
) -> Path | None:
    project_data = _load_project_data(project_metadata_loader)
    firmware = project_data.get("firmware")
    if not isinstance(firmware, dict):
        return None
    ioc_path = firmware.get("ioc_path")
    if not isinstance(ioc_path, str) or not ioc_path.strip():
        return None
    candidate = Path(ioc_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    base_path = cwd_resolver() if callable(cwd_resolver) else Path.cwd()
    return (base_path / candidate).resolve()

"""
Anup: critical.
"""
def detect_project_context(
    prompt: str,
    *,
    project_metadata_loader: Callable[[], dict[str, object]] | None = None,
    cwd_resolver: Callable[[], Path] | None = None,
) -> dict[str, object]:
    lowered = prompt.strip().lower()
    configured_path = configured_ioc_path(project_metadata_loader=project_metadata_loader, cwd_resolver=cwd_resolver)
    configured_source = str(configured_path) if configured_path is not None and configured_path.is_file() else None
    has_existing_hint = any(token in lowered for token in EXISTING_PROJECT_TOKENS)
    has_new_project_hint = any(token in lowered for token in NEW_PROJECT_TOKENS) or bool(
        re.search(r"\b(create|write|generate|start)\b.*\bproject\b", lowered)
    )
    has_new_device_hint = any(token in lowered for token in NEW_DEVICE_TOKENS)
    has_engineering_spec_hint = looks_like_engineering_feature_spec(prompt)

    if has_existing_hint:
        kind = "existing_project"
        reason = "The prompt refers to an existing or running project."
    elif has_new_device_hint or ("device" in lowered and has_new_project_hint):
        kind = "new_device"
        reason = "The prompt describes a device-centric request without asking to reuse an existing project."
    elif has_new_project_hint or has_engineering_spec_hint:
        kind = "new_project"
        reason = (
            "The prompt explicitly asks for a new project."
            if has_new_project_hint
            else "The prompt reads like a new feature-delivery specification for a target board."
        )
    elif configured_source is not None:
        kind = "existing_project"
        reason = "A configured IOC already exists, so the workflow defaults to reusing it through a managed copy."
    else:
        kind = "new_project"
        reason = "No existing IOC was configured, so the workflow defaults to a new project."

    return {
        "kind": kind,
        "ioc_handling": "copy_existing_ioc" if kind == "existing_project" else "download_from_github",
        "configured_source_ioc_path": configured_source,
        "use_managed_project_copy": True,
        "reason": reason,
    }
