from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, TextIO

from .tool_resolution import cached_resolution, freeze_cache_value


DEFAULT_STLINK_GDB_SERVER_ENV_VAR = "STM32_STLINK_GDB_SERVER_PATH"
DEFAULT_STLINK_GDB_SERVER_CANDIDATES = {
    "windows": [
        r"C:\ST\STM32CubeIDE_1.14.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server.win32_2.2.300.202509021040\tools\bin\ST-LINK_gdbserver.exe",
    ],
    "linux": ["ST-LINK_gdbserver"],
    "darwin": ["ST-LINK_gdbserver"],
}


def default_stlink_gdb_server_executable_name(host_platform: str) -> str:
    return "ST-LINK_gdbserver.exe" if host_platform == "windows" else "ST-LINK_gdbserver"


def derive_stlink_gdb_server_candidates(
    *,
    resolve_cubeide_path: Callable[[], str],
    host_platform: str,
) -> list[Path]:
    try:
        cubeide_path = Path(resolve_cubeide_path()).resolve()
    except FileNotFoundError:
        return []

    cubeide_root = cubeide_path.parent
    executable_name = default_stlink_gdb_server_executable_name(host_platform)
    plugin_candidates = sorted(
        cubeide_root.glob("plugins/com.st.stm32cube.ide.mcu.externaltools.stlink-gdb-server*/tools/bin/*")
    )
    return [candidate for candidate in plugin_candidates if candidate.name.lower() == executable_name.lower()]


def discover_stlink_gdb_server(
    *,
    host_platform: str,
    load_tools_local_config: Callable[[], dict[str, object]],
    resolve_candidate_path: Callable[[str, Path | None], Path],
    resolve_cubeide_path: Callable[[], str],
    which_resolver: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    tools_config = load_tools_local_config()
    config_data = tools_config.get("data")
    tool_entry: dict[str, object] = {}

    if isinstance(config_data, dict):
        tools = config_data.get("tools")
        if isinstance(tools, dict):
            stlink_gdb_server = tools.get("stlink_gdb_server")
            if isinstance(stlink_gdb_server, dict):
                tool_entry = stlink_gdb_server

    env_var = str(tool_entry.get("env_var") or DEFAULT_STLINK_GDB_SERVER_ENV_VAR)
    executable_name = str(tool_entry.get("executable_name") or default_stlink_gdb_server_executable_name(host_platform))
    config_path = Path(str(tools_config["path"])) if isinstance(tools_config.get("path"), str) else None
    which_result = which_resolver(executable_name)
    try:
        cubeide_hint = resolve_cubeide_path()
    except FileNotFoundError:
        cubeide_hint = None
    cache_key = freeze_cache_value(
        {
            "host_platform": host_platform,
            "tool_entry": tool_entry,
            "config_path": tools_config.get("path"),
            "config_status": tools_config.get("status"),
            "config_errors": list(tools_config.get("errors", [])),
            "env_var": env_var,
            "env_candidate": os.environ.get(env_var),
            "which_result": which_result,
            "cubeide_hint": cubeide_hint,
        }
    )

    def resolve_discovery() -> dict[str, object]:
        checked_candidates: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        resolved_path: str | None = None
        resolution_source: str | None = None

        def record_candidate(path_value: Path | str, source: str) -> None:
            nonlocal resolved_path, resolution_source

            path_text = str(path_value)
            normalized = os.path.normcase(path_text)
            if normalized in seen_paths:
                return
            seen_paths.add(normalized)

            candidate_path = Path(path_text)
            exists = candidate_path.is_file()
            checked_candidates.append(
                {
                    "path": path_text,
                    "exists": exists,
                    "source": source,
                }
            )
            if exists and resolved_path is None:
                resolved_path = path_text
                resolution_source = source

        env_candidate = os.environ.get(env_var)
        if env_candidate:
            record_candidate(Path(env_candidate).expanduser(), "environment")

        config_candidates = tool_entry.get("candidates")
        if isinstance(config_candidates, dict):
            platform_candidates = config_candidates.get(host_platform)
            if isinstance(platform_candidates, list):
                for candidate in platform_candidates:
                    if isinstance(candidate, str) and candidate.strip():
                        record_candidate(resolve_candidate_path(candidate, base_path=config_path), "config")

        if which_result:
            record_candidate(which_result, "path")

        for candidate in derive_stlink_gdb_server_candidates(
            resolve_cubeide_path=resolve_cubeide_path,
            host_platform=host_platform,
        ):
            record_candidate(candidate, "cubeide_plugin")

        for candidate in DEFAULT_STLINK_GDB_SERVER_CANDIDATES.get(host_platform, []):
            record_candidate(Path(candidate), "default")

        return {
            "tool": "stlink_gdb_server",
            "host_platform": host_platform,
            "env_var": env_var,
            "path_hint": executable_name,
            "config_path": tools_config.get("path"),
            "config_status": tools_config.get("status"),
            "config_error": "; ".join(str(error) for error in tools_config.get("errors", [])) or None,
            "resolved_path": resolved_path,
            "resolution_source": resolution_source,
            "checked_candidates": checked_candidates,
        }

    return cached_resolution("stlink_gdb_server", cache_key, resolve_discovery)


def build_stlink_gdb_server_command(
    tool_path: str,
    *,
    port_number: int,
    persistent: bool,
    server_log_path: Path,
    log_level: int | None = None,
    verbose: bool = False,
    refresh_delay: int | None = None,
    verify: bool = False,
    swd: bool = True,
    swo_port: int | None = None,
    cpu_clock_hz: int | None = None,
    swo_clock_div: int | None = None,
    initialize_reset: bool = False,
    serial_number: str | None = None,
    apid: int | None = None,
    attach: bool = False,
    shared_mode: bool = False,
    erase_all: bool = False,
    cube_programmer_path: str | None = None,
    frequency_khz: int | None = None,
    halt: bool = False,
    incremental: bool = False,
) -> list[str]:
    command = [tool_path, "-p", str(port_number), "-f", str(server_log_path)]
    if persistent:
        command.append("-e")
    if log_level is not None:
        command.extend(["-l", str(log_level)])
    if verbose:
        command.append("-v")
    if refresh_delay is not None:
        command.extend(["-r", str(refresh_delay)])
    if verify:
        command.append("-s")
    if swd:
        command.append("-d")
    if swo_port is not None:
        command.extend(["-z", str(swo_port)])
    if cpu_clock_hz is not None:
        command.extend(["-a", str(cpu_clock_hz)])
    if swo_clock_div is not None:
        command.extend(["-b", str(swo_clock_div)])
    if initialize_reset:
        command.append("-k")
    if serial_number:
        command.extend(["-i", serial_number])
    if apid is not None:
        command.extend(["-m", str(apid)])
    if attach:
        command.append("-g")
    if shared_mode:
        command.append("-t")
    if erase_all:
        command.append("--erase-all")
    if cube_programmer_path:
        command.extend(["-cp", cube_programmer_path])
    if frequency_khz is not None:
        command.extend(["--frequency", str(frequency_khz)])
    if halt:
        command.append("--halt")
    if incremental:
        command.append("--incremental")
    return command


def build_stlink_gdb_server_version_command(tool_path: str) -> list[str]:
    return [tool_path, "--version"]


def build_list_debuggers_command(tool_path: str, *, cube_programmer_path: str | None = None) -> list[str]:
    command = [tool_path]
    if cube_programmer_path:
        command.extend(["-cp", cube_programmer_path])
    command.append("-q")
    return command


def launch_stlink_gdb_server_process(
    command: list[str],
    *,
    output_handle: TextIO,
    working_directory: str,
    host_platform: str,
    subprocess_module: object = subprocess,
) -> subprocess.Popen[str]:
    creationflags = getattr(subprocess_module, "CREATE_NO_WINDOW", 0) if host_platform == "windows" else 0
    stdout_redirect = getattr(subprocess_module, "STDOUT", subprocess.STDOUT)
    return subprocess_module.Popen(
        command,
        stdout=output_handle,
        stderr=stdout_redirect,
        text=True,
        cwd=working_directory,
        creationflags=creationflags,
    )


def resolve_stlink_gdb_server_path(discovery: dict[str, object]) -> str:
    tool_path = discovery.get("resolved_path")
    if isinstance(tool_path, str) and Path(tool_path).is_file():
        return tool_path

    checked_paths = [str(candidate["path"]) for candidate in discovery.get("checked_candidates", [])]
    checked_suffix = f" Checked: {checked_paths}." if checked_paths else ""
    env_var = str(discovery.get("env_var") or DEFAULT_STLINK_GDB_SERVER_ENV_VAR)
    raise FileNotFoundError(
        "ST-LINK GDB server executable was not found. Set "
        f"{env_var}, add ST-LINK_gdbserver to PATH, or update config/stm32-tools.local.json."
        f"{checked_suffix}"
    )


def run_debug_command(
    command: list[str],
    *,
    timeout_seconds: int,
    subprocess_module: object = subprocess,
) -> dict[str, object]:
    try:
        completed = subprocess_module.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        return {
            "success": completed.returncode == 0,
            "exit_code": completed.returncode,
            "command": command,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError as exc:
        return {
            "success": False,
            "exit_code": -2,
            "command": command,
            "stdout": "",
            "stderr": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "exit_code": -1,
            "command": command,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": ((exc.stderr or "").strip() if isinstance(exc.stderr, str) else "") or f"Command timed out after {timeout_seconds} seconds.",
        }