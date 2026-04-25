from __future__ import annotations

from typing import Awaitable, Callable

from ..services.routing_service import WorkflowRoute


async def route_prompt(
    *,
    prompt: str,
    timeout_seconds: int,
    classify_prompt: Callable[[str], WorkflowRoute],
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
    route = classify_prompt(prompt)
    if route == "build_flash":
        result = await orchestrate_build_then_flash_fn(
            file_path=extract_file_path(prompt),
            build_timeout_seconds=timeout_seconds,
            flash_timeout_seconds=timeout_seconds,
        )
    elif route == "build":
        result = build_project(timeout_seconds=timeout_seconds)
    elif route == "requirements":
        result = await orchestrate_feature_prompt_fn(
            prompt=prompt,
            build_timeout_seconds=timeout_seconds,
            flash_timeout_seconds=timeout_seconds,
            cubemx_timeout_seconds=max(timeout_seconds, 300),
        )
    elif route == "debug":
        if is_debug_question(prompt):
            result = await orchestrate_debug_question_fn(prompt=prompt, timeout_seconds=timeout_seconds)
        else:
            result = await orchestrate_debug_session_fn(timeout_seconds=timeout_seconds)
    elif route == "cubemx":
        lowered = prompt.strip().lower()
        result = orchestrate_cubemx_regeneration_fn(timeout_seconds=timeout_seconds) if any(token in lowered for token in ("regenerate", "generate")) else parse_ioc()
    elif route == "cube_programmer":
        file_path = extract_file_path(prompt)
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
        "selected_domain": route,
        "result": result,
    }
