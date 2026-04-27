from __future__ import annotations

from typing import Awaitable, Callable

from ..services.routing_service import PromptMode, WorkflowRoute


async def route_prompt(
    *,
    prompt: str,
    timeout_seconds: int,
    mode: PromptMode = "auto",
    classify_prompt: Callable[[str], WorkflowRoute],
    resolve_prompt_mode: Callable[[str, str | None], PromptMode],
    prompt_without_mode_prefix: Callable[[str], str],
    extract_file_path: Callable[[str], str | None],
    is_debug_question: Callable[[str], bool],
    orchestrate_build_then_flash_fn: Callable[..., Awaitable[dict[str, object]]],
    build_project: Callable[..., dict[str, object]],
    orchestrate_feature_prompt_fn: Callable[..., Awaitable[dict[str, object]]],
    orchestrate_debug_question_fn: Callable[..., Awaitable[dict[str, object]]],
    orchestrate_debug_session_fn: Callable[..., Awaitable[dict[str, object]]],
    orchestrate_cubemx_regeneration_fn: Callable[..., dict[str, object]],
    parse_ioc: Callable[[], dict[str, object]],
    flash_firmware: Callable[..., Awaitable[dict[str, object]]],
    report_host_capabilities: Callable[..., dict[str, object]],
) -> dict[str, object]:
    resolved_mode = resolve_prompt_mode(prompt, mode)
    effective_prompt = prompt_without_mode_prefix(prompt)
    route = classify_prompt(effective_prompt)

    blocked_result: dict[str, object] | None = None
    if resolved_mode == "develop-agent":
        blocked_result = {
            "success": True,
            "implemented": True,
            "message": "Prompt resolved as develop-agent. Firmware/build/flash routing is intentionally skipped; handle this as MCP server development work.",
        }
    elif resolved_mode == "inspect-only" and route in {"build_flash", "build", "requirements", "debug", "cubemx"}:
        blocked_result = report_host_capabilities(timeout_seconds=min(timeout_seconds, 15))
        route = "cube_programmer"
    elif resolved_mode == "test-only" and route == "requirements":
        blocked_result = {
            "success": False,
            "implemented": True,
            "message": "test-only mode blocks firmware/project generation. Use firmware-delivery mode to allow generated project changes.",
        }

    if blocked_result is not None:
        result = blocked_result
    elif route == "build_flash":
        result = await orchestrate_build_then_flash_fn(
            file_path=extract_file_path(effective_prompt),
            build_timeout_seconds=timeout_seconds,
            flash_timeout_seconds=timeout_seconds,
        )
    elif route == "build":
        result = build_project(timeout_seconds=timeout_seconds)
    elif route == "requirements":
        result = await orchestrate_feature_prompt_fn(
            prompt=effective_prompt,
            build_timeout_seconds=timeout_seconds,
            flash_timeout_seconds=timeout_seconds,
            cubemx_timeout_seconds=max(timeout_seconds, 300),
        )
    elif route == "debug":
        if is_debug_question(effective_prompt):
            result = await orchestrate_debug_question_fn(prompt=effective_prompt, timeout_seconds=timeout_seconds)
        else:
            result = await orchestrate_debug_session_fn(timeout_seconds=timeout_seconds)
    elif route == "cubemx":
        lowered = effective_prompt.strip().lower()
        result = orchestrate_cubemx_regeneration_fn(timeout_seconds=timeout_seconds) if any(token in lowered for token in ("regenerate", "generate")) else parse_ioc()
    elif route == "cube_programmer":
        file_path = extract_file_path(effective_prompt)
        if file_path:
            result = await flash_firmware(file_path=file_path, timeout_seconds=timeout_seconds)
        else:
            result = report_host_capabilities(timeout_seconds=min(timeout_seconds, 15))
    else:
        result = {
            "success": False,
            "implemented": False,
            "message": "Unable to classify the request. Ask for build, flash, debug, CubeMX, or host diagnostics explicitly.",
        }

    return {
        "server": "orchestrator",
        "prompt": prompt,
        "effective_prompt": effective_prompt,
        "resolved_mode": resolved_mode,
        "selected_domain": route,
        "result": result,
    }
