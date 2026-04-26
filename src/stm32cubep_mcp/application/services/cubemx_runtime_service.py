from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from ...tools import cubemx_adapter


def terminate_cubemx_process(
    process: subprocess.Popen[str] | object,
    *,
    host_platform: str,
    subprocess_module: object,
) -> None:
    cubemx_adapter.terminate_cubemx_process(
        process,
        host_platform=host_platform,
        subprocess_module=subprocess_module,
    )


def cubemx_script_reports_success(output_text: str) -> bool:
    return cubemx_adapter.cubemx_script_reports_success(output_text)


def cubemx_failure_reason(stdout: str, stderr: str) -> str | None:
    return cubemx_adapter.cubemx_failure_reason(stdout, stderr)


def run_cubemx_command_with_progress(
    command: list[str],
    timeout_seconds: int,
    *,
    progress_callback: Callable[[dict[str, object]], None] | None,
    completion_markers: list[Path] | None,
    completion_tree_root: Path | None,
    poll_interval_seconds: float,
    host_platform: str,
    configured_cubemx_log_path_resolver: Callable[[], Path | None],
    capture_completion_marker_state_fn: Callable[[list[Path]], dict[Path, tuple[bool, float | None]]],
    check_completion_markers_fn: Callable[..., dict[str, object] | None],
    collect_tree_state_fn: Callable[[Path | None], dict[str, float]],
    open_process_fn: Callable[[list[str]], subprocess.Popen[str] | object] | None = None,
    subprocess_module: object = subprocess,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    return cubemx_adapter.run_cubemx_command_with_progress(
        command,
        timeout_seconds,
        progress_callback=progress_callback,
        completion_markers=completion_markers,
        completion_tree_root=completion_tree_root,
        poll_interval_seconds=poll_interval_seconds,
        open_process=open_process_fn
        or (lambda invocation: subprocess.Popen(
            invocation,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )),
        terminate_process=lambda process: terminate_cubemx_process(
            process,
            host_platform=host_platform,
            subprocess_module=subprocess_module,
        ),
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
        configured_cubemx_log_path_resolver=configured_cubemx_log_path_resolver,
        capture_completion_marker_state_fn=capture_completion_marker_state_fn,
        check_completion_markers_fn=check_completion_markers_fn,
        collect_tree_state_fn=collect_tree_state_fn,
        failure_reason_fn=cubemx_failure_reason,
    )


def run_cubemx_command(
    command: list[str],
    timeout_seconds: int,
    *,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    completion_markers: list[Path] | None = None,
    completion_tree_root: Path | None = None,
    poll_interval_seconds: float = 2.0,
    host_platform: str,
    configured_cubemx_log_path_resolver: Callable[[], Path | None],
    capture_completion_marker_state_fn: Callable[[list[Path]], dict[Path, tuple[bool, float | None]]],
    check_completion_markers_fn: Callable[..., dict[str, object] | None],
    collect_tree_state_fn: Callable[[Path | None], dict[str, float]],
    open_process_fn: Callable[[list[str]], subprocess.Popen[str] | object] | None = None,
    subprocess_module: object = subprocess,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    return run_cubemx_command_with_progress(
        command,
        timeout_seconds,
        progress_callback=progress_callback,
        completion_markers=completion_markers,
        completion_tree_root=completion_tree_root,
        poll_interval_seconds=poll_interval_seconds,
        host_platform=host_platform,
        configured_cubemx_log_path_resolver=configured_cubemx_log_path_resolver,
        capture_completion_marker_state_fn=capture_completion_marker_state_fn,
        check_completion_markers_fn=check_completion_markers_fn,
        collect_tree_state_fn=collect_tree_state_fn,
        open_process_fn=open_process_fn,
        subprocess_module=subprocess_module,
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )
