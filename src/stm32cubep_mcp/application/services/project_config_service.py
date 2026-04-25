from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .workflow_state import contract_feature_ids

UART_CORE_FEATURE_ID = "core-uart-device-to-pc"
DEFAULT_GENERATED_PROJECTS_DIR = Path("generated")


def normalize_cubemx_toolchain(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    lowered = value.strip().lower()
    if lowered in {"cubeide", "stm32cubeide"}:
        return "STM32CubeIDE"
    return value.strip()


def workspace_project_metadata_path(project_config: dict[str, object], *, cwd: Path | None = None) -> Path:
    configured_path = project_config.get("path")
    if isinstance(configured_path, str) and configured_path.strip():
        return Path(configured_path).resolve()
    root = cwd or Path.cwd()
    return (root / "config" / "stm32-project.json").resolve()


def inferred_project_name(contract: dict[str, object]) -> str:
    target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    board_id = str(target.get("board_id") or "stm32-project").strip() or "stm32-project"
    feature_ids = contract_feature_ids(contract)

    if UART_CORE_FEATURE_ID in feature_ids:
        return f"{board_id}-UART2-printf"
    if "core-led-blink" in feature_ids and "pluggable-user-button-event" in feature_ids:
        return f"{board_id}-button-led"
    if "core-led-blink" in feature_ids:
        return f"{board_id}-blink"
    return f"{board_id}-generated"


def inferred_project_toolchain(contract: dict[str, object]) -> str:
    defaults = contract.get("defaults") if isinstance(contract.get("defaults"), dict) else {}
    configured = normalize_cubemx_toolchain(defaults.get("toolchain"))
    return configured or "STM32CubeIDE"


def derived_project_paths(
    project_name: str,
    *,
    cwd: Path | None = None,
    generated_projects_dir: Path | None = None,
) -> dict[str, str]:
    root = cwd or Path.cwd()
    generated_root = generated_projects_dir or DEFAULT_GENERATED_PROJECTS_DIR
    project_root = (root / generated_root / project_name).resolve()
    cubeide_root = (project_root / "STM32CubeIDE").resolve()
    debug_artifact = (cubeide_root / "Debug" / f"{project_name}.elf").resolve()
    return {
        "ioc_path": str((generated_root / project_name / f"{project_name}.ioc").as_posix()),
        "project_path": str(project_root),
        "script_path": str((project_root / "script.txt").resolve()),
        "build_project_path": str(cubeide_root),
        "workspace": str((root / generated_root / ".cubeide-workspace").resolve()),
        "artifact": str(debug_artifact),
    }


def merge_project_metadata_with_prompt_fallback(
    project_config: dict[str, object],
    contract: dict[str, object],
    *,
    cwd: Path | None = None,
    generated_projects_dir: Path | None = None,
) -> tuple[dict[str, object], list[str]]:
    existing_data = project_config.get("raw_data") if isinstance(project_config.get("raw_data"), dict) else project_config.get("data") if isinstance(project_config.get("data"), dict) else {}
    merged_data = json.loads(json.dumps(existing_data)) if existing_data else {}
    project_context = contract.get("project_context") if isinstance(contract.get("project_context"), dict) else {}

    firmware = merged_data.get("firmware") if isinstance(merged_data.get("firmware"), dict) else {}
    cubemx = merged_data.get("cubemx") if isinstance(merged_data.get("cubemx"), dict) else {}
    build = merged_data.get("build") if isinstance(merged_data.get("build"), dict) else {}
    debug = merged_data.get("debug") if isinstance(merged_data.get("debug"), dict) else {}

    if project_context.get("kind") in {"new_device", "new_project"}:
        project_name = inferred_project_name(contract)
    else:
        project_name = str(
            merged_data.get("project_name")
            or cubemx.get("project_name")
            or build.get("project_name")
            or inferred_project_name(contract)
        ).strip()
    toolchain = normalize_cubemx_toolchain(
        merged_data.get("project_toolchain") or cubemx.get("project_toolchain")
    ) or inferred_project_toolchain(contract)
    build_system = str(merged_data.get("build_system") or build.get("system") or "cubeide").strip() or "cubeide"
    default_configuration = str(
        merged_data.get("default_configuration") or build.get("default_configuration") or "Debug"
    ).strip() or "Debug"

    autofilled_fields: list[str] = []

    def fill(container: dict[str, object], key: str, value: object, field_name: str) -> None:
        existing = container.get(key)
        if isinstance(value, str):
            if isinstance(existing, str) and existing.strip():
                return
        elif existing is not None:
            return
        container[key] = value
        autofilled_fields.append(field_name)

    merged_data["version"] = int(merged_data.get("version") or 1)
    fill(merged_data, "project_name", project_name, "project_name")
    fill(merged_data, "generated_root", (generated_projects_dir or DEFAULT_GENERATED_PROJECTS_DIR).as_posix(), "generated_root")
    fill(merged_data, "project_toolchain", toolchain, "project_toolchain")
    fill(merged_data, "build_system", build_system, "build_system")
    fill(merged_data, "default_configuration", default_configuration, "default_configuration")

    if project_context.get("kind") in {"new_device", "new_project"} and merged_data.get("project_name") != project_name:
        merged_data["project_name"] = project_name
        autofilled_fields.append("project_name")

    if bool(project_context.get("use_managed_project_copy")) and project_name:
        managed_paths = derived_project_paths(project_name, cwd=cwd, generated_projects_dir=generated_projects_dir)
        managed_overrides: list[tuple[dict[str, object], str, object, str]] = [
            (firmware, "ioc_path", managed_paths["ioc_path"], "firmware.ioc_path"),
            (firmware, "default_artifact", managed_paths["artifact"], "firmware.default_artifact"),
            (cubemx, "project_name", project_name, "cubemx.project_name"),
            (cubemx, "project_toolchain", toolchain, "cubemx.project_toolchain"),
            (cubemx, "project_path", managed_paths["project_path"], "cubemx.project_path"),
            (cubemx, "script_path", managed_paths["script_path"], "cubemx.script_path"),
            (build, "system", build_system, "build.system"),
            (build, "workspace", managed_paths["workspace"], "build.workspace"),
            (build, "project_path", managed_paths["build_project_path"], "build.project_path"),
            (build, "project_name", project_name, "build.project_name"),
            (build, "default_configuration", default_configuration, "build.default_configuration"),
            (build, "configurations", [default_configuration], "build.configurations"),
            (build, "artifact", managed_paths["artifact"], "build.artifact"),
            (debug, "elf_path", managed_paths["artifact"], "debug.elf_path"),
        ]

        for container, key, value, field_name in managed_overrides:
            if container.get(key) == value:
                continue
            container[key] = value
            autofilled_fields.append(field_name)

    merged_data["firmware"] = firmware
    merged_data["cubemx"] = cubemx
    merged_data["build"] = build
    merged_data["debug"] = debug
    return merged_data, autofilled_fields


def ensure_project_metadata_for_feature_contract(
    contract: dict[str, object],
    *,
    load_project_metadata: Callable[[], dict[str, object]],
    cwd: Path | None = None,
    generated_projects_dir: Path | None = None,
) -> dict[str, object]:
    project_config = load_project_metadata()
    merged_data, autofilled_fields = merge_project_metadata_with_prompt_fallback(
        project_config,
        contract,
        cwd=cwd,
        generated_projects_dir=generated_projects_dir,
    )
    metadata_path = workspace_project_metadata_path(project_config, cwd=cwd)

    if autofilled_fields:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(merged_data, indent=2) + "\n", encoding="utf-8")

    refreshed_config = load_project_metadata()
    return {
        "project_config": refreshed_config,
        "metadata_path": str(metadata_path),
        "autofilled_fields": autofilled_fields,
    }


def normalize_project_config(
    *,
    write_changes: bool,
    load_project_metadata: Callable[[], dict[str, object]],
    compact_project_metadata: Callable[[dict[str, object]], dict[str, object]],
    render_project_metadata_jsonc: Callable[[dict[str, object]], str],
    summarize_config_status: Callable[[dict[str, object]], dict[str, object]],
    cwd: Path | None = None,
) -> dict[str, object]:
    project_config = load_project_metadata()
    metadata_path = workspace_project_metadata_path(project_config, cwd=cwd)
    project_data = project_config.get("raw_data") if isinstance(project_config.get("raw_data"), dict) else project_config.get("data")
    if not isinstance(project_data, dict):
        return {
            "server": "orchestrator",
            "workflow": "normalize_project_config",
            "success": False,
            "metadata_path": str(metadata_path),
            "project_config": summarize_config_status(project_config),
            "message": "No stm32-project.json payload is available to normalize.",
        }

    compacted = compact_project_metadata(project_data)
    rendered = render_project_metadata_jsonc(project_data)
    changed = None
    if metadata_path.is_file():
        changed = metadata_path.read_text(encoding="utf-8") != rendered
    else:
        changed = True

    if write_changes:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(rendered, encoding="utf-8")

    return {
        "server": "orchestrator",
        "workflow": "normalize_project_config",
        "success": True,
        "metadata_path": str(metadata_path),
        "changed": changed,
        "wrote_file": write_changes,
        "normalized_data": compacted,
        "message": "Normalized stm32-project.json into concise JSONC form." if changed else "stm32-project.json was already in normalized JSONC form.",
    }


def configured_cubemx_request(
    *,
    load_project_metadata: Callable[[], dict[str, object]],
    summarize_config_status: Callable[[dict[str, object]], dict[str, object]],
) -> dict[str, object]:
    project_config = load_project_metadata()
    project_data = project_config.get("data")
    if not isinstance(project_data, dict):
        return {
            "project_config": summarize_config_status(project_config),
            "ioc_path": None,
            "project_name": None,
            "project_toolchain": None,
            "project_path": None,
            "script_path": None,
            "missing_fields": ["project_config"],
        }

    firmware = project_data.get("firmware") if isinstance(project_data.get("firmware"), dict) else {}
    build = project_data.get("build") if isinstance(project_data.get("build"), dict) else {}
    cubemx = project_data.get("cubemx") if isinstance(project_data.get("cubemx"), dict) else {}

    ioc_path = firmware.get("ioc_path") if isinstance(firmware.get("ioc_path"), str) and str(firmware.get("ioc_path")).strip() else None
    project_name = (
        cubemx.get("project_name")
        if isinstance(cubemx.get("project_name"), str) and str(cubemx.get("project_name")).strip()
        else build.get("project_name") if isinstance(build.get("project_name"), str) and str(build.get("project_name")).strip()
        else None
    )
    project_toolchain = normalize_cubemx_toolchain(cubemx.get("project_toolchain") or build.get("system"))
    project_path = cubemx.get("project_path") if isinstance(cubemx.get("project_path"), str) and str(cubemx.get("project_path")).strip() else None
    script_path = cubemx.get("script_path") if isinstance(cubemx.get("script_path"), str) and str(cubemx.get("script_path")).strip() else None

    missing_fields: list[str] = []
    if not ioc_path:
        missing_fields.append("firmware.ioc_path")
    if not project_name:
        missing_fields.append("cubemx.project_name")
    if not project_toolchain:
        missing_fields.append("cubemx.project_toolchain")
    if not project_path:
        missing_fields.append("cubemx.project_path")

    return {
        "project_config": summarize_config_status(project_config),
        "ioc_path": ioc_path,
        "project_name": project_name,
        "project_toolchain": project_toolchain,
        "project_path": project_path,
        "script_path": script_path,
        "missing_fields": missing_fields,
    }


def configured_firmware_artifact(*, load_project_metadata: Callable[[], dict[str, object]]) -> str | None:
    project_config = load_project_metadata()
    project_data = project_config.get("data")
    if not isinstance(project_data, dict):
        return None

    build_config = project_data.get("build")
    if isinstance(build_config, dict):
        artifact = build_config.get("artifact")
        if isinstance(artifact, str) and artifact.strip():
            return artifact

    firmware_config = project_data.get("firmware")
    if isinstance(firmware_config, dict):
        artifact = firmware_config.get("default_artifact")
        if isinstance(artifact, str) and artifact.strip():
            return artifact

    return None
