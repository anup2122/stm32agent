from __future__ import annotations

from typing import Awaitable, Callable


async def orchestrate_debug_session(
    *,
    session_name: str,
    reset_before_launch: bool,
    timeout_seconds: int,
    port_number: int | None,
    swo_port: int | None,
    enable_swo: bool,
    serial_number: str | None,
    frequency_khz: int | None,
    attach: bool,
    persistent: bool,
    shared_mode: bool,
    verify: bool,
    incremental: bool,
    erase_all: bool,
    verbose: bool,
    log_level: int | None,
    refresh_delay: int | None,
    initialize_reset: bool,
    apid: int | None,
    halt: bool,
    reset_target: Callable[..., Awaitable[dict[str, object]]],
    launch_debug_server: Callable[..., dict[str, object]],
) -> dict[str, object]:
    reset_result: dict[str, object] | None = None
    if reset_before_launch:
        reset_result = await reset_target(timeout_seconds=min(timeout_seconds, 60))
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

    launch_result = launch_debug_server(
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
            f"Debug session '{session_name}' is ready."
            if launch_result.get("success")
            else "Debug session launch failed after any requested reset."
        ),
    }


async def run_runtime_validation_stage(
    *,
    plan_file: str | None,
    increment_id: str | None,
    flash_timeout_seconds: int,
    update_plan_status: Callable[..., dict[str, object]],
    orchestrate_debug_session_fn: Callable[..., Awaitable[dict[str, object]]],
    stop_debug_session_fn: Callable[..., dict[str, object]] | None = None,
) -> dict[str, object]:
    if plan_file:
        update_plan_status(
            plan_file,
            stage="runtime_validation",
            status="in_progress",
            message="Launching a managed debug session for post-flash runtime validation.",
            increment_id=increment_id,
        )

    runtime_validation_result = await orchestrate_debug_session_fn(
        session_name="feature-runtime-validation",
        reset_before_launch=False,
        timeout_seconds=min(flash_timeout_seconds, 60),
    )
    cleanup_result: dict[str, object] | None = None
    if runtime_validation_result.get("success") and stop_debug_session_fn is not None:
        cleanup_result = stop_debug_session_fn(
            session_name="feature-runtime-validation",
            force=False,
            timeout_seconds=10,
        )
        cleanup_message = str(cleanup_result.get("message") or "").lower()
        cleanup_ok = bool(cleanup_result.get("success")) or "not running" in cleanup_message
        runtime_validation_result = {
            **runtime_validation_result,
            "cleanup_result": cleanup_result,
            "success": cleanup_ok,
        }

    if plan_file:
        update_plan_status(
            plan_file,
            stage="runtime_validation",
            status="completed" if runtime_validation_result.get("success") else "failed",
            message=(
                "Runtime validation completed and the debug session was released."
                if runtime_validation_result.get("success")
                else "Runtime validation could not prepare a post-flash debug session."
            ),
            details={"result": runtime_validation_result},
            increment_id=increment_id,
        )

    return runtime_validation_result
