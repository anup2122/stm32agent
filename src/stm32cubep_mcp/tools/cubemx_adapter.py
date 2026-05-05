from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable


DEFAULT_CUBEMX_ENV_VAR = "STM32CUBEMX_PATH"
DEFAULT_CUBEMX_EXECUTABLE_NAME = "STM32CubeMX.exe"
DEFAULT_CUBEMX_CANDIDATES = {
    "windows": [
        r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe",
        r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe",
        r"C:\ST\STM32CubeMX\STM32CubeMX.exe",
    ],
    "linux": ["STM32CubeMX"],
    "darwin": ["STM32CubeMX"],
}


def cubemx_tool_entry(load_tools_local_config: Callable[[], dict[str, object]]) -> dict[str, object]:
    tools_config = load_tools_local_config()
    config_data = tools_config.get("data")
    if not isinstance(config_data, dict):
        return {}
    tools = config_data.get("tools")
    if not isinstance(tools, dict):
        return {}
    tool_entry = tools.get("cubemx")
    return tool_entry if isinstance(tool_entry, dict) else {}


# Derive CubeMX JAR candidates from the installed CubeIDE plugin layout when a standalone executable is not configured.
def derive_cubemx_candidates(resolve_cubeide_path: Callable[[], str]) -> list[Path]:
    try:
        cubeide_path = Path(resolve_cubeide_path()).resolve()
    except FileNotFoundError:
        return []

    cubeide_root = cubeide_path.parent
    return sorted(cubeide_root.glob("plugins/com.st.stm32cube.common.mx_*/STM32CubeMX.jar"))


# Derive Java runtime candidates from the CubeIDE installation and fall back to host Java lookup when needed.
def derive_java_candidates(resolve_cubeide_path: Callable[[], str], host_platform: str) -> list[Path]:
    try:
        cubeide_path = Path(resolve_cubeide_path()).resolve()
    except FileNotFoundError:
        return []

    cubeide_root = cubeide_path.parent
    executable_name = "java.exe" if host_platform == "windows" else "java"
    direct_candidate = cubeide_root / "jre" / "bin" / executable_name
    candidates: list[Path] = [direct_candidate]
    candidates.extend(sorted(cubeide_root.glob("plugins/com.st.stm32cube.ide.jre.*/jre/bin/java.exe")))
    return [candidate for candidate in candidates if candidate.is_file()]


def resolve_java_path(resolve_cubeide_path: Callable[[], str], host_platform: str) -> str | None:
    derived_candidates = derive_java_candidates(resolve_cubeide_path, host_platform)
    if derived_candidates:
        return str(derived_candidates[-1])

    return shutil.which("java")


# Discover CubeMX launch options across environment overrides, config entries, PATH defaults, and CubeIDE plugin installs.
def discover_cubemx(
    *,
    host_platform: str,
    load_tools_local_config: Callable[[], dict[str, object]],
    resolve_candidate_path: Callable[[str, Path | None], Path],
    resolve_cubeide_path: Callable[[], str],
) -> dict[str, object]:
    tools_config = load_tools_local_config()
    tool_entry = cubemx_tool_entry(load_tools_local_config)
    env_var = str(tool_entry.get("env_var") or DEFAULT_CUBEMX_ENV_VAR)
    executable_name = str(tool_entry.get("executable_name") or DEFAULT_CUBEMX_EXECUTABLE_NAME)
    config_path = Path(str(tools_config["path"])) if isinstance(tools_config.get("path"), str) else None
    checked_candidates: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    resolved_path: str | None = None
    resolution_source: str | None = None
    launch_kind: str | None = None

    def record_candidate(path_value: Path | str, source: str, candidate_kind: str) -> None:
        nonlocal resolved_path, resolution_source, launch_kind
        path_text = str(path_value)
        normalized = os.path.normcase(path_text)
        if normalized in seen_paths:
            return
        seen_paths.add(normalized)
        checked_candidates.append(
            {
                "path": path_text,
                "source": source,
                "kind": candidate_kind,
                "exists": Path(path_value).is_file(),
            }
        )
        if resolved_path is None and Path(path_value).is_file():
            resolved_path = path_text
            resolution_source = source
            launch_kind = candidate_kind

    env_candidate = os.environ.get(env_var)
    if env_candidate:
        env_path = Path(env_candidate).expanduser()
        kind = "jar" if env_path.suffix.lower() == ".jar" else "executable"
        record_candidate(env_path, "environment", kind)

    config_candidates = tool_entry.get("candidates")
    if isinstance(config_candidates, dict):
        platform_candidates = config_candidates.get(host_platform)
        if isinstance(platform_candidates, list):
            for candidate in platform_candidates:
                if isinstance(candidate, str) and candidate.strip():
                    resolved_candidate = resolve_candidate_path(candidate, config_path)
                    kind = "jar" if resolved_candidate.suffix.lower() == ".jar" else "executable"
                    record_candidate(resolved_candidate, "config", kind)

    which_result = shutil.which(executable_name)
    if which_result:
        record_candidate(which_result, "path", "executable")

    for candidate in DEFAULT_CUBEMX_CANDIDATES.get(host_platform, []):
        record_candidate(Path(candidate), "default", "executable")

    for candidate in derive_cubemx_candidates(resolve_cubeide_path):
        record_candidate(candidate, "cubeide_plugin", "jar")

    return {
        "tool": "cubemx",
        "host_platform": host_platform,
        "env_var": env_var,
        "path_hint": executable_name,
        "config_path": tools_config.get("path"),
        "config_status": tools_config.get("status"),
        "config_error": "; ".join(str(error) for error in tools_config.get("errors", [])) or None,
        "resolved_path": resolved_path,
        "resolution_source": resolution_source,
        "launch_kind": launch_kind,
        "java_path": resolve_java_path(resolve_cubeide_path, host_platform),
        "checked_candidates": checked_candidates,
    }


# Convert the resolved CubeMX discovery result into the concrete launcher command prefix, including Java for JAR launches.
def resolve_cubemx_launcher(discovery: dict[str, object]) -> dict[str, object]:
    resolved_path = discovery.get("resolved_path")
    launch_kind = discovery.get("launch_kind")
    if not isinstance(resolved_path, str):
        raise FileNotFoundError(
            "STM32CubeMX was not found. Set STM32CUBEMX_PATH or update config/stm32-tools.local.jsonc with a valid executable or JAR path."
        )
    if launch_kind == "jar":
        java_path = discovery.get("java_path")
        if not isinstance(java_path, str):
            raise FileNotFoundError("STM32CubeMX JAR was found, but no Java runtime was available to launch it.")
        return {
            "tool_path": resolved_path,
            "launch_kind": launch_kind,
            "command_prefix": [java_path, "-jar", resolved_path],
            "discovery": discovery,
        }
    return {
        "tool_path": resolved_path,
        "launch_kind": launch_kind or "executable",
        "command_prefix": [resolved_path],
        "discovery": discovery,
    }


# Terminate a running CubeMX process reliably, using `taskkill` on Windows to clean up child processes.
def terminate_cubemx_process(
    process: subprocess.Popen[str] | object,
    *,
    host_platform: str,
    subprocess_module: object,
) -> None:
    if host_platform == "windows":
        try:
            subprocess_module.run(  # type: ignore[attr-defined]
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        return


# Detect whether the CubeMX script transcript shows a successful generate-and-exit sequence.
def cubemx_script_reports_success(output_text: str) -> bool:
    normalized = output_text.lower()
    generate_index = normalized.rfind("project generate")
    if generate_index == -1:
        return False

    tail = normalized[generate_index:]
    return bool(re.search(r"project generate[\s\S]*\bok\b[\s\S]*exit_mx", tail))


# Translate known CubeMX transcript patterns into a clearer high-level failure reason.
def cubemx_failure_reason(stdout: str, stderr: str) -> str | None:
    combined = "\n".join(part for part in (stdout, stderr) if part).lower()
    if "the version of the current ioc is too high" in combined:
        return "The IOC file was created by a newer STM32CubeMX version than the one currently available on this host."
    if re.search(r"(^|\n)ko(\n|$)", combined):
        if cubemx_script_reports_success(combined):
            return None
        return "STM32CubeMX reported command-script failure. Inspect the CubeMX transcript for details."
    if "usage:" in combined and "generate generate code <path>" in combined:
        return "STM32CubeMX rejected the generate-code command syntax."
    return None


# Run CubeMX while streaming log progress, watching completion markers, and normalizing exit, timeout, and marker-based success outcomes.
def run_cubemx_command_with_progress(
    command: list[str],
    timeout_seconds: int,
    *,
    progress_callback: Callable[[dict[str, object]], None] | None,
    completion_markers: list[Path] | None,
    completion_tree_root: Path | None,
    poll_interval_seconds: float,
    open_process: Callable[[list[str]], subprocess.Popen[str] | object],
    terminate_process: Callable[[subprocess.Popen[str] | object], None],
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
    configured_cubemx_log_path_resolver: Callable[[], Path | None],
    capture_completion_marker_state_fn: Callable[[list[Path]], dict[Path, tuple[bool, float | None]]],
    check_completion_markers_fn: Callable[..., dict[str, object] | None],
    collect_tree_state_fn: Callable[[Path | None], dict[str, float]],
    failure_reason_fn: Callable[[str, str], str | None],
) -> dict[str, object]:
    try:
        process = open_process(command)
    except FileNotFoundError as exc:
        return {
            "success": False,
            "exit_code": -2,
            "command": command,
            "stdout": "",
            "stderr": str(exc),
        }

    cubemx_log_path = configured_cubemx_log_path_resolver()
    cubemx_log_offset = 0
    if cubemx_log_path is not None:
        try:
            cubemx_log_offset = cubemx_log_path.stat().st_size if cubemx_log_path.is_file() else 0
        except OSError:
            cubemx_log_offset = 0

    def emit_cubemx_log_progress() -> None:
        nonlocal cubemx_log_offset
        if progress_callback is None or cubemx_log_path is None:
            return
        try:
            if not cubemx_log_path.is_file():
                return
            current_size = cubemx_log_path.stat().st_size
            if current_size < cubemx_log_offset:
                cubemx_log_offset = 0
            if current_size == cubemx_log_offset:
                return
            with cubemx_log_path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(cubemx_log_offset)
                log_delta = handle.read()
                cubemx_log_offset = handle.tell()
        except OSError:
            return
        if log_delta:
            progress_callback(
                {
                    "stage": "cubemx_log",
                    "message": "STM32CubeMX log file produced new output.",
                    "log_path": str(cubemx_log_path),
                    "content": log_delta,
                }
            )

    started_at = monotonic_fn()
    deadline = started_at + timeout_seconds
    initial_marker_states = capture_completion_marker_state_fn(completion_markers or [])
    initial_tree_state = collect_tree_state_fn(completion_tree_root) if completion_tree_root is not None else None

    while True:
        return_code = process.poll()
        if return_code is not None:
            stdout, stderr = process.communicate()
            emit_cubemx_log_progress()
            stdout_text = stdout.strip()
            stderr_text = stderr.strip()
            failure_reason = failure_reason_fn(stdout_text, stderr_text)
            return {
                "success": return_code == 0 and failure_reason is None,
                "exit_code": return_code,
                "command": command,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "failure_reason": failure_reason,
            }

        completion_status = check_completion_markers_fn(
            completion_markers or [],
            initial_marker_states,
            tree_root=completion_tree_root,
            initial_tree_state=initial_tree_state,
        )
        if completion_status is not None:
            terminate_process(process)
            stdout, stderr = process.communicate()
            emit_cubemx_log_progress()
            return {
                "success": True,
                "exit_code": 0,
                "command": command,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "failure_reason": None,
                "completed_via_marker": True,
                "completion_marker": completion_status,
            }

        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            terminate_process(process)
            stdout, stderr = process.communicate()
            emit_cubemx_log_progress()
            stdout_text = stdout.strip()
            stderr_text = stderr.strip() or f"Command timed out after {timeout_seconds} seconds."
            failure_reason = failure_reason_fn(stdout_text, stderr_text) or f"STM32CubeMX did not finish within {timeout_seconds} seconds."
            return {
                "success": False,
                "exit_code": -1,
                "command": command,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "failure_reason": failure_reason,
            }

        emit_cubemx_log_progress()
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "cubemx_process",
                    "message": "CubeMX process is still running.",
                    "elapsed_seconds": round(monotonic_fn() - started_at, 1),
                    "remaining_seconds": round(remaining, 1),
                    "command": command,
                }
            )
        sleep_fn(min(poll_interval_seconds, remaining))
