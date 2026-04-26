from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from mcp.server.fastmcp import FastMCP

from .. import shared
from ..application.services import artifact_service, cubemx_tool_service, project_config_service, routing_service, workflow_state
from ..application.workflows import build_flash_test as build_flash_test_workflow
from ..application.workflows import debug_question as debug_question_workflow
from ..application.workflows import generate_project as generate_project_workflow
from ..application.workflows import live_debug as live_debug_workflow
from ..application.workflows import prompt_router as prompt_router_workflow
from ..cube_programmer import server as programmer_server
from ..build import server as build_server
from ..cubemx import server as cubemx_server
from ..debug import server as debug_server
from ..ioc_builder import server as ioc_builder_server
from ..requirements import server as requirements_server

WorkflowRoute = routing_service.WorkflowRoute

mcp = FastMCP("stm32orchestrator")

UART_CORE_FEATURE_ID = "core-uart-device-to-pc"
UART_APP_INCLUDE_SNIPPET = "#include <string.h>"
UART_APP_MESSAGE_SNIPPET = 'static const char uart_message[] = "STM32CubeP USART2 telemetry ready\\r\\n";'
UART_APP_BOOT_SNIPPET = "HAL_UART_Transmit(&huart2, (uint8_t *)uart_message, strlen(uart_message), HAL_MAX_DELAY);"
UART_APP_LOOP_SNIPPET = "HAL_UART_Transmit(&huart2, (uint8_t *)uart_message, strlen(uart_message), HAL_MAX_DELAY);\nHAL_Delay(1000);"


def classify_prompt(prompt: str) -> WorkflowRoute:
    return routing_service.classify_prompt(prompt)


def extract_file_path(prompt: str) -> str | None:
    return routing_service.extract_file_path(prompt)


def is_debug_question(prompt: str) -> bool:
    return routing_service.is_debug_question(prompt)


def configured_firmware_artifact() -> str | None:
    return project_config_service.configured_firmware_artifact(load_project_metadata=shared.load_project_metadata)

def select_flash_artifact(build_result: dict[str, object], file_path: str | None = None) -> tuple[str | None, str | None]:
    return artifact_service.select_flash_artifact(
        build_result,
        file_path=file_path,
        configured_firmware_artifact=configured_firmware_artifact,
    )


def normalize_cubemx_toolchain(value: object) -> str | None:
    return project_config_service.normalize_cubemx_toolchain(value)


def workspace_project_metadata_path(project_config: dict[str, object]) -> Path:
    return project_config_service.workspace_project_metadata_path(project_config)


def inferred_project_name(contract: dict[str, object]) -> str:
    return project_config_service.inferred_project_name(contract)


def inferred_project_toolchain(contract: dict[str, object]) -> str:
    return project_config_service.inferred_project_toolchain(contract)


def derived_project_paths(project_name: str) -> dict[str, str]:
    return project_config_service.derived_project_paths(project_name)


def merge_project_metadata_with_prompt_fallback(project_config: dict[str, object], contract: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    return project_config_service.merge_project_metadata_with_prompt_fallback(project_config, contract)


def ensure_project_metadata_for_feature_contract(contract: dict[str, object]) -> dict[str, object]:
    return project_config_service.ensure_project_metadata_for_feature_contract(
        contract,
        load_project_metadata=shared.load_project_metadata,
    )


@mcp.tool(description="Normalize stm32-project.json into the concise JSONC format with real comments and derived-path duplication removed.")
def stm32_normalize_project_config(write_changes: bool = True) -> dict[str, object]:
    return project_config_service.normalize_project_config(
        write_changes=write_changes,
        load_project_metadata=shared.load_project_metadata,
        compact_project_metadata=shared.compact_project_metadata,
        render_project_metadata_jsonc=shared.render_project_metadata_jsonc,
        summarize_config_status=programmer_server.summarize_config_status,
    )


def configured_cubemx_request() -> dict[str, object]:
    return project_config_service.configured_cubemx_request(
        load_project_metadata=shared.load_project_metadata,
        summarize_config_status=programmer_server.summarize_config_status,
    )


def with_effective_ioc_path(cubemx_request: dict[str, object], ioc_path: object) -> dict[str, object]:
    return workflow_state.with_effective_ioc_path(cubemx_request, ioc_path)


def ioc_plan_details(ioc_result: dict[str, object], mode: str) -> dict[str, object]:
    return workflow_state.ioc_plan_details(ioc_result, mode)


def summarize_ioc_validation(ioc_result: dict[str, object], mode: str) -> dict[str, object] | None:
    return workflow_state.summarize_ioc_validation(ioc_result, mode)


def reusable_cubemx_result_from_ioc_validation(
    ioc_result: dict[str, object],
    effective_cubemx_request: dict[str, object],
) -> dict[str, object] | None:
    return workflow_state.reusable_cubemx_result_from_ioc_validation(ioc_result, effective_cubemx_request)


def summarize_execution_policy(contract: dict[str, object]) -> dict[str, object] | None:
    return workflow_state.summarize_execution_policy(contract)


def contract_feature_ids(contract: dict[str, object]) -> set[str]:
    return workflow_state.contract_feature_ids(contract)


def contract_feature_lookup(contract: dict[str, object]) -> dict[str, dict[str, object]]:
    return workflow_state.contract_feature_lookup(contract)


def contract_increment_records(contract: dict[str, object]) -> list[dict[str, object]]:
    return workflow_state.contract_increment_records(contract)


def interface_intent_lookup(contract: dict[str, object]) -> dict[str, dict[str, object]]:
    return workflow_state.interface_intent_lookup(contract)


def contract_for_increment(contract: dict[str, object], increment: dict[str, object]) -> dict[str, object]:
    return workflow_state.contract_for_increment(contract, increment)


def next_pending_increment(plan_state: dict[str, object] | None, contract: dict[str, object]) -> list[dict[str, object]]:
    return workflow_state.next_pending_increment(plan_state, contract)


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
    increment_id: str | None,
    flash_timeout_seconds: int,
) -> dict[str, object]:
    return await live_debug_workflow.run_runtime_validation_stage(
        plan_file=plan_file,
        increment_id=increment_id,
        flash_timeout_seconds=flash_timeout_seconds,
        update_plan_status=requirements_server.update_plan_status,
        orchestrate_debug_session_fn=stm32_orchestrate_debug_session,
    )


async def run_feature_delivery_workflow(
    *,
    prompt: str,
    build_timeout_seconds: int,
    flash_timeout_seconds: int,
    cubemx_timeout_seconds: int,
    verify_mode: programmer_server.VerifyMode,
    post_action: programmer_server.PostDownloadAction,
) -> dict[str, object]:
    return await generate_project_workflow.orchestrate_feature_delivery(
        prompt=prompt,
        build_timeout_seconds=build_timeout_seconds,
        flash_timeout_seconds=flash_timeout_seconds,
        cubemx_timeout_seconds=cubemx_timeout_seconds,
        verify_mode=verify_mode,
        post_action=post_action,
        uart_core_feature_id=UART_CORE_FEATURE_ID,
        requirements_decompose=requirements_server.stm32_requirements_decompose,
        summarize_execution_policy=summarize_execution_policy,
        ensure_project_metadata_for_feature_contract=ensure_project_metadata_for_feature_contract,
        configured_cubemx_request=configured_cubemx_request,
        next_pending_increment=next_pending_increment,
        contract_for_increment=contract_for_increment,
        contract_feature_ids=contract_feature_ids,
        ioc_plan_details=ioc_plan_details,
        summarize_ioc_validation=summarize_ioc_validation,
        with_effective_ioc_path=with_effective_ioc_path,
        reusable_cubemx_result_from_ioc_validation=reusable_cubemx_result_from_ioc_validation,
        construct_ioc_file=ioc_builder_server.construct_ioc_file,
        apply_ioc_change_set=ioc_builder_server.apply_ioc_change_set,
        regenerate_project_internal=cubemx_server.regenerate_project_internal,
        apply_uart_device_to_pc_firmware_patch=apply_uart_device_to_pc_firmware_patch,
        build_project=build_server.stm32_build_project,
        select_flash_artifact=select_flash_artifact,
        flash_firmware=programmer_server.stm32_flash_firmware,
        run_runtime_validation_stage_fn=run_runtime_validation_stage,
        update_plan_status=requirements_server.update_plan_status,
        read_plan_status=requirements_server.read_plan_status,
    )


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
    return cubemx_tool_service.orchestrate_cubemx_regeneration(
        validate_build=validate_build,
        timeout_seconds=timeout_seconds,
        build_timeout_seconds=build_timeout_seconds,
        configured_cubemx_request_fn=configured_cubemx_request,
        regenerate_project_fn=cubemx_server.stm32_cubemx_regenerate_project,
    )


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
    return await build_flash_test_workflow.orchestrate_build_then_flash(
        target=target,
        clean=clean,
        file_path=file_path,
        build_timeout_seconds=build_timeout_seconds,
        flash_timeout_seconds=flash_timeout_seconds,
        verify_mode=verify_mode,
        post_action=post_action,
        build_project=build_server.stm32_build_project,
        flash_firmware=programmer_server.stm32_flash_firmware,
        select_flash_artifact=select_flash_artifact,
    )


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
    return await live_debug_workflow.orchestrate_debug_session(
        session_name=session_name,
        reset_before_launch=reset_before_launch,
        timeout_seconds=timeout_seconds,
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
        reset_target=programmer_server.stm32_reset,
        launch_debug_server=debug_server.stm32_debug_launch,
    )


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
    return await prompt_router_workflow.route_prompt(
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        classify_prompt=classify_prompt,
        extract_file_path=extract_file_path,
        is_debug_question=is_debug_question,
        orchestrate_build_then_flash_fn=stm32_orchestrate_build_then_flash,
        build_project=build_server.stm32_build_project,
        orchestrate_feature_prompt_fn=stm32_orchestrate_feature_prompt,
        orchestrate_debug_question_fn=stm32_orchestrate_debug_question,
        orchestrate_debug_session_fn=stm32_orchestrate_debug_session,
        orchestrate_cubemx_regeneration_fn=stm32_orchestrate_cubemx_regeneration,
        parse_ioc=cubemx_server.stm32_cubemx_parse_ioc,
        flash_firmware=programmer_server.stm32_flash_firmware,
        report_host_capabilities=programmer_server.stm32_report_host_capabilities,
    )


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
    return await debug_question_workflow.orchestrate_debug_question(
        prompt=prompt,
        session_name=session_name,
        timeout_seconds=timeout_seconds,
        debug_status=debug_server.stm32_debug_status,
        orchestrate_debug_session_fn=stm32_orchestrate_debug_session,
        answer_question=debug_server.stm32_debug_answer_question,
    )


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
