from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .. import shared
from ..cube_programmer import server as programmer_server
from ..build import server as build_server
from ..cubemx import server as cubemx_server
from ..debug import server as debug_server
from ..ioc_builder import server as ioc_builder_server
from ..requirements import server as requirements_server

WorkflowRoute = Literal["cube_programmer", "build", "build_flash", "debug", "cubemx", "requirements", "unknown"]

BUILD_PROMPT_TOKENS = ("build", "compile", "cubeide", "cmake", "make", "headlessbuild")
FLASH_PROMPT_TOKENS = ("flash", "program", "download", "erase", "reset", "connect", "st-link", "verify")
DEBUG_PROMPT_TOKENS = ("breakpoint", "gdb", "register", "snapshot", "debug", "attach", "uart", "usart", "baud", "peripheral", "gpio", "timer", "spi", "i2c", "adc", "rcc")
FEATURE_PROMPT_TOKENS = ("write a project", "create project", "generate project", "send data", "transmit", "blink", "button")

mcp = FastMCP("stm32orchestrator")

UART_CORE_FEATURE_ID = "core-uart-device-to-pc"
UART_APP_INCLUDE_SNIPPET = "#include <string.h>"
UART_APP_MESSAGE_SNIPPET = 'static const char uart_message[] = "STM32CubeP USART2 telemetry ready\\r\\n";'
UART_APP_BOOT_SNIPPET = "HAL_UART_Transmit(&huart2, (uint8_t *)uart_message, strlen(uart_message), HAL_MAX_DELAY);"
UART_APP_LOOP_SNIPPET = "HAL_UART_Transmit(&huart2, (uint8_t *)uart_message, strlen(uart_message), HAL_MAX_DELAY);\nHAL_Delay(1000);"

DEFAULT_GENERATED_PROJECTS_DIR = Path("generated")


def classify_prompt(prompt: str) -> WorkflowRoute:
    lowered = prompt.strip().lower()
    if any(token in lowered for token in FEATURE_PROMPT_TOKENS) and any(token in lowered for token in ("nucleo", "stm32", "device", "board", "pc")):
        return "requirements"
    if any(token in lowered for token in ("cube mx", "cubemx", ".ioc", "regenerate project", "parse ioc")):
        return "cubemx"
    if any(token in lowered for token in DEBUG_PROMPT_TOKENS):
        return "debug"
    if any(token in lowered for token in BUILD_PROMPT_TOKENS) and any(token in lowered for token in FLASH_PROMPT_TOKENS):
        return "build_flash"
    if any(token in lowered for token in BUILD_PROMPT_TOKENS):
        return "build"
    if any(token in lowered for token in FLASH_PROMPT_TOKENS):
        return "cube_programmer"
    return "unknown"


def extract_file_path(prompt: str) -> str | None:
    match = re.search(r"file_path\s*=\s*([\S]+)", prompt)
    if match is None:
        return None
    return match.group(1).strip('"\'')


def is_debug_question(prompt: str) -> bool:
    lowered = prompt.strip().lower()
    return any(token in lowered for token in ("what", "which", "show", "read", "inspect", "tell me"))


def configured_firmware_artifact() -> str | None:
    project_config = shared.load_project_metadata()
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

def select_flash_artifact(build_result: dict[str, object], file_path: str | None = None) -> tuple[str | None, str | None]:
    if isinstance(file_path, str) and file_path.strip():
        return file_path, "prompt"

    artifact = build_result.get("artifact")
    if isinstance(artifact, str) and artifact.strip():
        return artifact, "build"

    configured_artifact = configured_firmware_artifact()
    if configured_artifact:
        return configured_artifact, "project_config"

    return None, None


def normalize_cubemx_toolchain(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    lowered = value.strip().lower()
    if lowered in {"cubeide", "stm32cubeide"}:
        return "STM32CubeIDE"
    return value.strip()


def workspace_project_metadata_path(project_config: dict[str, object]) -> Path:
    configured_path = project_config.get("path")
    if isinstance(configured_path, str) and configured_path.strip():
        return Path(configured_path).resolve()
    return (Path.cwd() / "config" / "stm32-project.json").resolve()


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


def derived_project_paths(project_name: str) -> dict[str, str]:
    project_root = (Path.cwd() / DEFAULT_GENERATED_PROJECTS_DIR / project_name).resolve()
    cubeide_root = (project_root / "Projects" / "STM32CubeIDE").resolve()
    debug_artifact = (cubeide_root / "Debug" / f"{project_name}.elf").resolve()
    return {
        "ioc_path": str((DEFAULT_GENERATED_PROJECTS_DIR / project_name / f"{project_name}.ioc").as_posix()),
        "project_path": str(project_root),
        "script_path": str((project_root / "script.txt").resolve()),
        "build_project_path": str(cubeide_root),
        "workspace": str((Path.cwd() / DEFAULT_GENERATED_PROJECTS_DIR / ".cubeide-workspace").resolve()),
        "artifact": str(debug_artifact),
    }


def merge_project_metadata_with_prompt_fallback(project_config: dict[str, object], contract: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    existing_data = project_config.get("raw_data") if isinstance(project_config.get("raw_data"), dict) else project_config.get("data") if isinstance(project_config.get("data"), dict) else {}
    merged_data = json.loads(json.dumps(existing_data)) if existing_data else {}

    firmware = merged_data.get("firmware") if isinstance(merged_data.get("firmware"), dict) else {}
    cubemx = merged_data.get("cubemx") if isinstance(merged_data.get("cubemx"), dict) else {}
    build = merged_data.get("build") if isinstance(merged_data.get("build"), dict) else {}
    debug = merged_data.get("debug") if isinstance(merged_data.get("debug"), dict) else {}

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
    fill(merged_data, "generated_root", DEFAULT_GENERATED_PROJECTS_DIR.as_posix(), "generated_root")
    fill(merged_data, "project_toolchain", toolchain, "project_toolchain")
    fill(merged_data, "build_system", build_system, "build_system")
    fill(merged_data, "default_configuration", default_configuration, "default_configuration")

    merged_data["firmware"] = firmware
    merged_data["cubemx"] = cubemx
    merged_data["build"] = build
    merged_data["debug"] = debug
    return merged_data, autofilled_fields


def ensure_project_metadata_for_feature_contract(contract: dict[str, object]) -> dict[str, object]:
    project_config = shared.load_project_metadata()
    merged_data, autofilled_fields = merge_project_metadata_with_prompt_fallback(project_config, contract)
    metadata_path = workspace_project_metadata_path(project_config)

    if autofilled_fields:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(merged_data, indent=2) + "\n", encoding="utf-8")

    refreshed_config = shared.load_project_metadata()
    return {
        "project_config": refreshed_config,
        "metadata_path": str(metadata_path),
        "autofilled_fields": autofilled_fields,
    }


@mcp.tool(description="Normalize stm32-project.json into the concise JSONC format with real comments and derived-path duplication removed.")
def stm32_normalize_project_config(write_changes: bool = True) -> dict[str, object]:
    project_config = shared.load_project_metadata()
    metadata_path = workspace_project_metadata_path(project_config)
    project_data = project_config.get("raw_data") if isinstance(project_config.get("raw_data"), dict) else project_config.get("data")
    if not isinstance(project_data, dict):
        return {
            "server": "orchestrator",
            "workflow": "normalize_project_config",
            "success": False,
            "metadata_path": str(metadata_path),
            "project_config": programmer_server.summarize_config_status(project_config),
            "message": "No stm32-project.json payload is available to normalize.",
        }

    compacted = shared.compact_project_metadata(project_data)
    rendered = shared.render_project_metadata_jsonc(project_data)
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


def configured_cubemx_request() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    if not isinstance(project_data, dict):
        return {
            "project_config": programmer_server.summarize_config_status(project_config),
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
        "project_config": programmer_server.summarize_config_status(project_config),
        "ioc_path": ioc_path,
        "project_name": project_name,
        "project_toolchain": project_toolchain,
        "project_path": project_path,
        "script_path": script_path,
        "missing_fields": missing_fields,
    }


def with_effective_ioc_path(cubemx_request: dict[str, object], ioc_path: object) -> dict[str, object]:
    if not isinstance(ioc_path, str) or not ioc_path.strip():
        return dict(cubemx_request)
    updated_request = dict(cubemx_request)
    updated_request["ioc_path"] = ioc_path
    return updated_request


def ioc_plan_details(ioc_result: dict[str, object], mode: str) -> dict[str, object]:
    details: dict[str, object] = {
        "ioc_path": ioc_result.get("ioc_path"),
        "mode": mode,
    }
    cubemx_validation = ioc_result.get("cubemx_validation")
    if isinstance(cubemx_validation, dict):
        details["cubemx_validation"] = cubemx_validation
    return details


def summarize_ioc_validation(ioc_result: dict[str, object], mode: str) -> dict[str, object] | None:
    cubemx_validation = ioc_result.get("cubemx_validation")
    if not isinstance(cubemx_validation, dict):
        return None
    return {
        "mode": mode,
        "ioc_path": ioc_result.get("ioc_path"),
        "status": cubemx_validation.get("validation"),
        "success": bool(cubemx_validation.get("success")),
        "message": cubemx_validation.get("message"),
    }


def reusable_cubemx_result_from_ioc_validation(
    ioc_result: dict[str, object],
    effective_cubemx_request: dict[str, object],
) -> dict[str, object] | None:
    cubemx_validation = ioc_result.get("cubemx_validation")
    if not isinstance(cubemx_validation, dict):
        return None
    if not bool(cubemx_validation.get("success")) or cubemx_validation.get("validation") != "accepted":
        return None

    cubemx_result = cubemx_validation.get("cubemx_result")
    if not isinstance(cubemx_result, dict) or not bool(cubemx_result.get("success")):
        return None

    expected_project_path = str(effective_cubemx_request.get("project_path") or "")
    result_project_path = str(cubemx_result.get("project_path") or "")
    if expected_project_path and result_project_path and Path(expected_project_path).resolve() != Path(result_project_path).resolve():
        return None

    return cubemx_result


def summarize_execution_policy(contract: dict[str, object]) -> dict[str, object] | None:
    execution_policy = contract.get("execution_policy")
    if not isinstance(execution_policy, dict):
        return None
    return {
        "mode": execution_policy.get("mode"),
        "ioc_cubemx_validation": execution_policy.get("ioc_cubemx_validation"),
        "build_after_each_increment": execution_policy.get("build_after_each_increment"),
        "flash_after_successful_build": execution_policy.get("flash_after_successful_build"),
        "runtime_check_after_flash": execution_policy.get("runtime_check_after_flash"),
        "ask_user_on_repeated_failures": execution_policy.get("ask_user_on_repeated_failures"),
    }


def contract_feature_ids(contract: dict[str, object]) -> set[str]:
    feature_ids: set[str] = set()
    for key in ("core_features", "pluggable_features"):
        features = contract.get(key)
        if not isinstance(features, list):
            continue
        for feature in features:
            if not isinstance(feature, dict):
                continue
            feature_id = feature.get("id")
            if isinstance(feature_id, str) and feature_id.strip():
                feature_ids.add(feature_id.strip())
    return feature_ids


def source_project_root_for_ioc(ioc_path: str) -> Path:
    return Path(ioc_path).resolve().parent


def resolve_main_source_path(project_root: Path) -> Path:
    for candidate in (project_root / "Src" / "main.c", project_root / "Core" / "Src" / "main.c"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"main.c was not found under source project root: {project_root}")


def replace_user_code_block(contents: str, block_name: str, snippet: str) -> str:
    pattern = re.compile(
        rf"(?P<indent>[ \t]*)/\* USER CODE BEGIN {re.escape(block_name)} \*/\n(?P<body>.*?)(?P=indent)/\* USER CODE END {re.escape(block_name)} \*/",
        re.DOTALL,
    )
    match = pattern.search(contents)
    if match is None:
        raise ValueError(f"USER CODE block '{block_name}' was not found.")

    indent = match.group("indent")
    body_lines = match.group("body").splitlines()
    preserved_suffix: list[str] = []
    while body_lines and body_lines[-1].strip() in {"", "}"}:
        line = body_lines.pop()
        if line.strip():
            preserved_suffix.insert(0, line)

    snippet_indent = indent
    if preserved_suffix and preserved_suffix[0].strip() == "}":
        suffix_indent = preserved_suffix[0][: len(preserved_suffix[0]) - len(preserved_suffix[0].lstrip(" \t"))]
        snippet_indent = f"{suffix_indent}  "

    snippet_lines = [f"{snippet_indent}{line}" for line in snippet.splitlines()] if snippet else []
    replacement_body = "\n".join([*snippet_lines, *preserved_suffix])
    if replacement_body:
        replacement_body = f"{replacement_body}\n"
    return f"{contents[:match.start('body')]}{replacement_body}{contents[match.end('body'):] }"


def inject_uart_loop_body(contents: str, snippet: str) -> str:
    pattern = re.compile(
        r"(?P<prefix>[ \t]*/\* USER CODE END WHILE \*/\n)(?P<gap>.*?)(?P<indent>[ \t]*)/\* USER CODE BEGIN 3 \*/",
        re.DOTALL,
    )
    match = pattern.search(contents)
    if match is None:
        raise ValueError("The USER CODE WHILE/3 loop region was not found.")

    indent = match.group("indent")
    snippet_lines = [f"{indent}{line}" for line in snippet.splitlines()] if snippet else []
    injected_gap = "\n" + "\n".join(snippet_lines) + "\n"
    return f"{contents[:match.start('gap')]}{injected_gap}{contents[match.end('gap'):]}"


def ensure_user_code_3_closing_brace(contents: str) -> str:
    pattern = re.compile(
        r"(?P<begin>[ \t]*/\* USER CODE BEGIN 3 \*/\n)(?P<body>.*?)(?P<indent>[ \t]*)/\* USER CODE END 3 \*/",
        re.DOTALL,
    )
    match = pattern.search(contents)
    if match is None:
        raise ValueError("USER CODE 3 block was not found.")

    body = match.group("body")
    if "}" in body:
        return contents

    indent = match.group("indent")
    restored_body = f"{indent}}}\n"
    return f"{contents[:match.start('body')]}{restored_body}{contents[match.end('body'):] }"


def apply_uart_device_to_pc_firmware_patch(ioc_path: str) -> dict[str, object]:
    project_root = source_project_root_for_ioc(ioc_path)
    main_source_path = resolve_main_source_path(project_root)
    contents = main_source_path.read_text(encoding="utf-8")

    updated = replace_user_code_block(contents, "Includes", UART_APP_INCLUDE_SNIPPET)
    updated = replace_user_code_block(updated, "PV", UART_APP_MESSAGE_SNIPPET)
    updated = replace_user_code_block(updated, "2", UART_APP_BOOT_SNIPPET)
    updated = inject_uart_loop_body(updated, UART_APP_LOOP_SNIPPET)
    updated = ensure_user_code_3_closing_brace(updated)

    if updated != contents:
        main_source_path.write_text(updated, encoding="utf-8")

    return {
        "success": True,
        "project_root": str(project_root),
        "main_source_path": str(main_source_path),
        "feature": UART_CORE_FEATURE_ID,
    }


async def run_runtime_validation_stage(
    *,
    plan_file: str | None,
    flash_timeout_seconds: int,
) -> dict[str, object]:
    if plan_file:
        requirements_server.update_plan_status(
            plan_file,
            stage="runtime_validation",
            status="in_progress",
            message="Launching a managed debug session for post-flash runtime validation.",
        )

    runtime_validation_result = await stm32_orchestrate_debug_session(
        session_name="feature-runtime-validation",
        reset_before_launch=False,
        timeout_seconds=min(flash_timeout_seconds, 60),
    )

    if plan_file:
        requirements_server.update_plan_status(
            plan_file,
            stage="runtime_validation",
            status="completed" if runtime_validation_result.get("success") else "failed",
            message=(
                "Runtime validation session is ready after flash."
                if runtime_validation_result.get("success")
                else "Runtime validation could not prepare a post-flash debug session."
            ),
            details={"result": runtime_validation_result},
        )

    return runtime_validation_result


async def run_feature_delivery_workflow(
    *,
    prompt: str,
    build_timeout_seconds: int,
    flash_timeout_seconds: int,
    cubemx_timeout_seconds: int,
    verify_mode: programmer_server.VerifyMode,
    post_action: programmer_server.PostDownloadAction,
) -> dict[str, object]:
    requirements_result = requirements_server.stm32_requirements_decompose(prompt, persist_plan=True)
    contract = requirements_result.get("contract") if isinstance(requirements_result.get("contract"), dict) else None
    plan_artifact = requirements_result.get("plan_artifact") if isinstance(requirements_result.get("plan_artifact"), dict) else None
    plan_file = str(contract.get("plan_file")) if isinstance(contract, dict) and isinstance(contract.get("plan_file"), str) else None
    execution_policy_summary = summarize_execution_policy(contract) if isinstance(contract, dict) else None

    if not requirements_result.get("success") or contract is None:
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": False,
            "stage": "requirements",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "message": "Requirements decomposition failed, so the workflow stopped before IOC synthesis.",
        }

    metadata_autofill = ensure_project_metadata_for_feature_contract(contract)

    cubemx_request = configured_cubemx_request()
    configured_ioc_path = cubemx_request.get("ioc_path")
    ioc_path = str(configured_ioc_path) if isinstance(configured_ioc_path, str) and configured_ioc_path.strip() else None
    should_construct_ioc = bool(ioc_path) and not Path(ioc_path).is_file()

    if plan_file:
        requirements_server.update_plan_status(
            plan_file,
            stage="ioc_builder",
            status="in_progress",
            message=(
                "Constructing the IOC from the board reference template for the current increment."
                if should_construct_ioc
                else "Applying the deterministic IOC change set for the current increment."
            ),
            details={
                "increment": contract.get("current_increment") if isinstance(contract.get("current_increment"), dict) else None,
                "ioc_path": ioc_path,
                "mode": "construct" if should_construct_ioc else "apply",
            },
        )

    ioc_result = (
        ioc_builder_server.construct_ioc_file(contract, ioc_path=ioc_path)
        if should_construct_ioc
        else ioc_builder_server.apply_ioc_change_set(contract, ioc_path=ioc_path)
    )

    def report_cubemx_progress(progress: dict[str, object]) -> None:
        if not plan_file:
            return
        stage_name = str(progress.get("stage") or "cubemx")
        message = str(progress.get("message") or "CubeMX work is still in progress.")
        details = {key: value for key, value in progress.items() if key not in {"stage", "message"}}
        requirements_server.update_plan_status(
            plan_file,
            stage="cubemx" if stage_name.startswith("cubemx") else stage_name,
            status="completed" if stage_name == "cubemx_complete" and progress.get("success") else "in_progress",
            message=message,
            details=details or None,
            append_history=stage_name == "cubemx_complete",
        )

    if not ioc_result.get("success"):
        ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
        if plan_file:
            requirements_server.update_plan_status(
                plan_file,
                stage="ioc_builder",
                status="failed",
                message=(
                    "IOC construction could not materialize the configured IOC file."
                    if should_construct_ioc
                    else "IOC synthesis could not be applied to the configured IOC file."
                ),
                details={
                    "result": ioc_result,
                    **ioc_plan_details(ioc_result, mode="construct" if should_construct_ioc else "apply"),
                },
            )
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": False,
            "stage": "ioc_builder",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "metadata_autofill": metadata_autofill,
            "ioc_result": ioc_result,
            "ioc_validation_summary": ioc_validation_summary,
            "plan_artifact": plan_artifact,
            "message": "IOC preparation failed, so the workflow stopped before CubeMX regeneration.",
        }

    if plan_file:
        requirements_server.update_plan_status(
            plan_file,
            stage="cubemx",
            status="in_progress",
            message="Running CubeMX regeneration for the updated IOC file.",
            details=ioc_plan_details(ioc_result, mode="construct" if should_construct_ioc else "apply"),
        )

    effective_cubemx_request = with_effective_ioc_path(cubemx_request, ioc_result.get("ioc_path"))

    reused_cubemx_run_result = reusable_cubemx_result_from_ioc_validation(ioc_result, effective_cubemx_request)
    if reused_cubemx_run_result is not None:
        cubemx_run_result = reused_cubemx_run_result
        if plan_file:
            requirements_server.update_plan_status(
                plan_file,
                stage="cubemx",
                status="completed",
                message="Reused the CubeMX regeneration already performed during IOC validation.",
                details={"result": cubemx_run_result, "reused_from_ioc_validation": True},
                append_history=True,
            )
    else:
        cubemx_run_result = cubemx_server.regenerate_project_internal(
            ioc_path=str(effective_cubemx_request["ioc_path"]),
            project_name=str(effective_cubemx_request["project_name"]),
            project_toolchain=str(effective_cubemx_request["project_toolchain"]),
            project_path=str(effective_cubemx_request["project_path"]),
            script_path=str(effective_cubemx_request["script_path"]) if isinstance(effective_cubemx_request.get("script_path"), str) else None,
            validate_build=False,
            timeout_seconds=cubemx_timeout_seconds,
            build_timeout_seconds=build_timeout_seconds,
            progress_callback=report_cubemx_progress,
        )
    cubemx_result = {
        "server": "orchestrator",
        "workflow": "cubemx_regeneration",
        "cubemx_request": effective_cubemx_request,
        "result": cubemx_run_result,
        "success": bool(cubemx_run_result.get("success")),
        "reused_from_ioc_validation": reused_cubemx_run_result is not None,
    }
    if not cubemx_result.get("success"):
        ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
        if plan_file:
            requirements_server.update_plan_status(
                plan_file,
                stage="cubemx",
                status="failed",
                message="CubeMX regeneration failed for the updated IOC file.",
                details={"result": cubemx_result},
            )
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": False,
            "stage": "cubemx",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "metadata_autofill": metadata_autofill,
            "ioc_result": ioc_result,
            "ioc_validation_summary": ioc_validation_summary,
            "cubemx_result": cubemx_result,
            "plan_artifact": plan_artifact,
            "message": "CubeMX regeneration failed, so the build and flash steps were skipped.",
        }

    firmware_patch_result: dict[str, object] | None = None
    if UART_CORE_FEATURE_ID in contract_feature_ids(contract):
        try:
            firmware_patch_result = apply_uart_device_to_pc_firmware_patch(str(effective_cubemx_request["ioc_path"]))
        except (FileNotFoundError, ValueError) as exc:
            ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
            if plan_file:
                requirements_server.update_plan_status(
                    plan_file,
                    stage="firmware_patch",
                    status="failed",
                    message="Post-regeneration firmware patching failed for the current increment.",
                    details={"error": str(exc), "ioc_path": effective_cubemx_request["ioc_path"]},
                )
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "firmware_patch",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "ioc_result": ioc_result,
                "ioc_validation_summary": ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "plan_artifact": plan_artifact,
                "message": "CubeMX regeneration succeeded, but the firmware source patch could not be applied.",
            }

    if plan_file:
        requirements_server.update_plan_status(
            plan_file,
            stage="build",
            status="in_progress",
            message="Building the regenerated CubeIDE project for the current increment.",
        )

    build_result = build_server.stm32_build_project(timeout_seconds=build_timeout_seconds)
    if not build_result.get("success"):
        ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
        if plan_file:
            requirements_server.update_plan_status(
                plan_file,
                stage="build",
                status="failed",
                message="Build failed after CubeMX regeneration.",
                details={"result": build_result},
            )
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": False,
            "stage": "build",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "metadata_autofill": metadata_autofill,
            "ioc_result": ioc_result,
            "ioc_validation_summary": ioc_validation_summary,
            "cubemx_result": cubemx_result,
            "build_result": build_result,
            "plan_artifact": plan_artifact,
            "message": "Build failed after regeneration, so the flash step was skipped.",
        }

    artifact_path, artifact_source = select_flash_artifact(build_result)
    if not artifact_path:
        ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
        if plan_file:
            requirements_server.update_plan_status(
                plan_file,
                stage="artifact_resolution",
                status="failed",
                message="Build succeeded but no artifact was available for flashing.",
                details={"build_result": build_result},
            )
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": False,
            "stage": "artifact_resolution",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "metadata_autofill": metadata_autofill,
            "ioc_result": ioc_result,
            "ioc_validation_summary": ioc_validation_summary,
            "cubemx_result": cubemx_result,
            "build_result": build_result,
            "plan_artifact": plan_artifact,
            "message": "Build succeeded, but no flash artifact could be resolved.",
        }

    execution_policy = contract.get("execution_policy") if isinstance(contract.get("execution_policy"), dict) else {}
    should_flash = bool(execution_policy.get("flash_after_successful_build", True))
    if not should_flash:
        ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
        if plan_file:
            requirements_server.update_plan_status(
                plan_file,
                stage="build",
                status="completed",
                message="Build completed and flash was skipped by execution policy.",
                details={"artifact_path": artifact_path, "artifact_source": artifact_source, "flash_after_successful_build": False},
                append_history=True,
            )
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": True,
            "stage": "completed",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "ioc_result": ioc_result,
            "ioc_validation_summary": ioc_validation_summary,
            "cubemx_result": cubemx_result,
            "build_result": build_result,
            "artifact_path": artifact_path,
            "artifact_source": artifact_source,
            "flash_skipped": True,
            "plan_artifact": plan_artifact,
            "message": "Requirements decomposition, IOC synthesis, regeneration, and build completed successfully. Flash was skipped by execution policy.",
        }

    if plan_file:
        requirements_server.update_plan_status(
            plan_file,
            stage="flash",
            status="in_progress",
            message="Flashing the newly built artifact to the attached device.",
            details={"artifact_path": artifact_path, "artifact_source": artifact_source},
        )

    flash_result = await programmer_server.stm32_flash_firmware(
        file_path=artifact_path,
        timeout_seconds=flash_timeout_seconds,
        verify_mode=verify_mode,
        post_action=post_action,
    )
    runtime_validation_enabled = bool(execution_policy.get("runtime_check_after_flash"))
    if plan_file:
        requirements_server.update_plan_status(
            plan_file,
            stage="flash",
            status="completed" if flash_result.get("success") else "failed",
            message=(
                "Flash completed and runtime validation will start next."
                if flash_result.get("success") and runtime_validation_enabled
                else "Feature delivery workflow completed successfully for the current increment."
                if flash_result.get("success")
                else "Flashing failed after a successful build."
            ),
            details={"result": flash_result},
        )

    runtime_validation_result: dict[str, object] | None = None
    if flash_result.get("success") and runtime_validation_enabled:
        runtime_validation_result = await run_runtime_validation_stage(
            plan_file=plan_file,
            flash_timeout_seconds=flash_timeout_seconds,
        )
        if not runtime_validation_result.get("success"):
            ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "runtime_validation",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "ioc_result": ioc_result,
                "ioc_validation_summary": ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "build_result": build_result,
                "flash_result": flash_result,
                "runtime_validation_result": runtime_validation_result,
                "artifact_source": artifact_source,
                "flash_skipped": False,
                "plan_artifact": plan_artifact,
                "message": "Flash succeeded, but runtime validation failed to prepare a debug session.",
            }

    ioc_validation_summary = summarize_ioc_validation(ioc_result, mode="construct" if should_construct_ioc else "apply")
    return {
        "server": "orchestrator",
        "workflow": "feature_delivery",
        "success": bool(flash_result.get("success")),
        "stage": "completed" if flash_result.get("success") else "flash",
        "requirements_result": requirements_result,
        "execution_policy_summary": execution_policy_summary,
        "metadata_autofill": metadata_autofill,
        "ioc_result": ioc_result,
        "ioc_validation_summary": ioc_validation_summary,
        "cubemx_result": cubemx_result,
        "firmware_patch_result": firmware_patch_result,
        "build_result": build_result,
        "flash_result": flash_result,
        "runtime_validation_result": runtime_validation_result,
        "artifact_source": artifact_source,
        "flash_skipped": False,
        "plan_artifact": plan_artifact,
        "message": (
            "Requirements decomposition, IOC synthesis, regeneration, build, flash, and runtime validation all completed successfully."
            if runtime_validation_result is not None and runtime_validation_result.get("success")
            else "Requirements decomposition, IOC synthesis, regeneration, build, and flash all completed successfully."
            if flash_result.get("success")
            else "The workflow reached the flash stage, but flashing failed."
        ),
    }


@mcp.tool(description="High-level orchestration workflow that converts a supported feature prompt into IOC changes, regenerates the project, builds it, and flashes the resulting firmware.")
async def stm32_orchestrate_feature_prompt(
    prompt: str,
    build_timeout_seconds: int = 600,
    flash_timeout_seconds: int = 240,
    cubemx_timeout_seconds: int = 900,
    verify_mode: programmer_server.VerifyMode = "legacy",
    post_action: programmer_server.PostDownloadAction = "go",
) -> dict[str, object]:
    return await run_feature_delivery_workflow(
        prompt=prompt,
        build_timeout_seconds=build_timeout_seconds,
        flash_timeout_seconds=flash_timeout_seconds,
        cubemx_timeout_seconds=cubemx_timeout_seconds,
        verify_mode=verify_mode,
        post_action=post_action,
    )


@mcp.tool(description="Read the current live status of a persisted feature-delivery plan artifact so callers can poll progress during long-running workflows.")
def stm32_orchestrate_feature_status(plan_file: str) -> dict[str, object]:
    status = requirements_server.read_plan_status(plan_file)
    return {
        "server": "orchestrator",
        "workflow": "feature_delivery_status",
        **status,
    }


@mcp.tool(description="High-level orchestration entry point for deterministic CubeMX regeneration using the shared stm32-project.json metadata.")
def stm32_orchestrate_cubemx_regeneration(
    validate_build: bool = True,
    timeout_seconds: int = 900,
    build_timeout_seconds: int = 600,
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

    result = cubemx_server.stm32_cubemx_regenerate_project(
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


@mcp.tool(description="High-level orchestration workflow that builds the configured STM32 project and then flashes the resulting artifact in one step.")
async def stm32_orchestrate_build_then_flash(
    target: str | None = None,
    clean: bool = False,
    file_path: str | None = None,
    build_timeout_seconds: int = 600,
    flash_timeout_seconds: int = 240,
    verify_mode: programmer_server.VerifyMode = "legacy",
    post_action: programmer_server.PostDownloadAction = "go",
) -> dict[str, object]:
    build_result = build_server.stm32_build_project(
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

    flash_result = await programmer_server.stm32_flash_firmware(
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


@mcp.tool(description="High-level orchestration workflow that resets the attached STM32 target and launches a managed ST-LINK GDB server session for runtime diagnosis.")
async def stm32_orchestrate_debug_session(
    session_name: str = "default",
    reset_before_launch: bool = True,
    timeout_seconds: int = 60,
    port_number: int | None = None,
    swo_port: int | None = None,
    enable_swo: bool = True,
    serial_number: str | None = None,
    frequency_khz: int | None = None,
    attach: bool = False,
    persistent: bool = True,
    shared_mode: bool = False,
    verify: bool = False,
    incremental: bool = False,
    erase_all: bool = False,
    verbose: bool = False,
    log_level: int | None = None,
    refresh_delay: int | None = None,
    initialize_reset: bool = False,
    apid: int | None = None,
    halt: bool = False,
) -> dict[str, object]:
    reset_result: dict[str, object] | None = None
    if reset_before_launch:
        reset_result = await programmer_server.stm32_reset(timeout_seconds=min(timeout_seconds, 60))
        if not reset_result.get("success"):
            return {
                "server": "orchestrator",
                "workflow": "debug_session",
                "success": False,
                "stage": "reset",
                "session_name": session_name,
                "reset_result": reset_result,
                "message": "Target reset failed, so the debug server launch was skipped.",
            }

    launch_result = debug_server.stm32_debug_launch(
        session_name=session_name,
        port_number=port_number,
        swo_port=swo_port,
        enable_swo=enable_swo,
        serial_number=serial_number,
        frequency_khz=frequency_khz,
        attach=attach,
        persistent=persistent,
        shared_mode=shared_mode,
        verify=verify,
        incremental=incremental,
        erase_all=erase_all,
        verbose=verbose,
        log_level=log_level,
        refresh_delay=refresh_delay,
        initialize_reset=initialize_reset,
        apid=apid,
        halt=halt,
        timeout_seconds=timeout_seconds,
    )
    return {
        "server": "orchestrator",
        "workflow": "debug_session",
        "success": bool(launch_result.get("success")),
        "stage": "launch" if not launch_result.get("success") else "completed",
        "session_name": session_name,
        "reset_before_launch": reset_before_launch,
        "reset_result": reset_result,
        "launch_result": launch_result,
        "message": (
            f"Debug session '{session_name}' is ready for runtime diagnosis."
            if launch_result.get("success")
            else "Target reset succeeded, but the debug server launch failed. Inspect the launch result for details."
        ) if reset_before_launch else (
            f"Debug session '{session_name}' is ready for runtime diagnosis."
            if launch_result.get("success")
            else "Debug server launch failed. Inspect the launch result for details."
        ),
    }


def orchestration_status() -> dict[str, object]:
    return {
        "server": "orchestrator",
        "configurations": {
            "tools": programmer_server.summarize_config_status(programmer_server.load_tools_local_config()),
            "project": programmer_server.summarize_config_status(shared.load_project_metadata()),
        },
        "domains": {
            "cube_programmer": programmer_server.collect_host_capabilities(),
            "build": build_server.collect_build_capabilities(),
            "debug": debug_server.collect_debug_capabilities(),
            "cubemx": cubemx_server.stm32_cubemx_capabilities(),
        },
    }


@mcp.tool(description="Report the shared configuration state and summarize the tool-domain MCP servers that the STM32 orchestration layer coordinates.")
def stm32_orchestration_status() -> dict[str, object]:
    return orchestration_status()


@mcp.tool(description="Route a natural-language STM32 workflow request to the most appropriate tool-domain MCP server scaffold and return the normalized result.")
async def stm32_orchestrate_prompt(prompt: str, timeout_seconds: int = 120) -> dict[str, object]:
    route = classify_prompt(prompt)
    if route == "build_flash":
        result = await stm32_orchestrate_build_then_flash(
            file_path=extract_file_path(prompt),
            build_timeout_seconds=timeout_seconds,
            flash_timeout_seconds=timeout_seconds,
        )
    elif route == "build":
        result = build_server.stm32_build_project(timeout_seconds=timeout_seconds)
    elif route == "requirements":
        result = await stm32_orchestrate_feature_prompt(
            prompt=prompt,
            build_timeout_seconds=timeout_seconds,
            flash_timeout_seconds=timeout_seconds,
            cubemx_timeout_seconds=max(timeout_seconds, 300),
        )
    elif route == "debug":
        result = await stm32_orchestrate_debug_question(prompt=prompt, timeout_seconds=timeout_seconds) if is_debug_question(prompt) else await stm32_orchestrate_debug_session(timeout_seconds=timeout_seconds)
    elif route == "cubemx":
        lowered = prompt.strip().lower()
        result = stm32_orchestrate_cubemx_regeneration(timeout_seconds=timeout_seconds) if any(token in lowered for token in ("regenerate", "generate")) else cubemx_server.stm32_cubemx_parse_ioc()
    elif route == "cube_programmer":
        file_path = extract_file_path(prompt)
        if file_path:
            result = await programmer_server.stm32_flash_firmware(file_path=file_path, timeout_seconds=timeout_seconds)
        else:
            result = programmer_server.stm32_report_host_capabilities(timeout_seconds=min(timeout_seconds, 15))
    else:
        result = {
            "success": False,
            "implemented": False,
            "message": "Unable to classify the request. Ask for build, flash, debug, CubeMX, or host diagnostics explicitly.",
        }

    return {
        "server": "orchestrator",
        "prompt": prompt,
        "selected_domain": route,
        "result": result,
    }


@mcp.tool(description="High-level orchestration entry point for a project build using the shared stm32-project.json metadata.")
def stm32_orchestrate_build(timeout_seconds: int = 600) -> dict[str, object]:
    result = build_server.stm32_build_project(timeout_seconds=timeout_seconds)
    return {
        "server": "orchestrator",
        "workflow": "build",
        "result": result,
    }


@mcp.tool(description="High-level orchestration entry point for reset-first ST-LINK GDB server launch using the shared STM32 project metadata.")
async def stm32_orchestrate_debug(timeout_seconds: int = 60) -> dict[str, object]:
    result = await stm32_orchestrate_debug_session(timeout_seconds=timeout_seconds)
    return {
        "server": "orchestrator",
        "workflow": "debug",
        "result": result,
    }


@mcp.tool(description="High-level orchestration workflow that ensures a managed debug session exists and then answers a live peripheral or register question from target state.")
async def stm32_orchestrate_debug_question(
    prompt: str,
    session_name: str = "agentic-inspect",
    timeout_seconds: int = 60,
) -> dict[str, object]:
    status_result = debug_server.stm32_debug_status(session_name=session_name)
    launch_result: dict[str, object] | None = None
    if not status_result.get("success"):
        launch_result = await stm32_orchestrate_debug_session(
            session_name=session_name,
            reset_before_launch=False,
            timeout_seconds=timeout_seconds,
        )
        if not launch_result.get("success"):
            return {
                "server": "orchestrator",
                "workflow": "debug_question",
                "success": False,
                "prompt": prompt,
                "session_name": session_name,
                "launch_result": launch_result,
                "message": "The debug session could not be prepared for live target inspection.",
            }

    answer_result = debug_server.stm32_debug_answer_question(
        question=prompt,
        session_name=session_name,
        timeout_seconds=timeout_seconds,
    )
    return {
        "server": "orchestrator",
        "workflow": "debug_question",
        "success": bool(answer_result.get("success")),
        "prompt": prompt,
        "session_name": session_name,
        "launch_result": launch_result,
        "answer_result": answer_result,
        "message": str(answer_result.get("answer") or answer_result.get("message") or "Live target inspection finished."),
    }


@mcp.tool(description="High-level orchestration entry point for flashing the configured default firmware artifact from stm32-project.json.")
async def stm32_orchestrate_flash(timeout_seconds: int = 240) -> dict[str, object]:
    file_path = configured_firmware_artifact()
    if not isinstance(file_path, str) or not file_path.strip():
        return {
            "server": "orchestrator",
            "workflow": "flash",
            "success": False,
            "message": "No build.artifact or firmware.default_artifact is configured in stm32-project.json.",
        }

    result = await programmer_server.stm32_flash_firmware(file_path=file_path, timeout_seconds=timeout_seconds)
    return {
        "server": "orchestrator",
        "workflow": "flash",
        "result": result,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()