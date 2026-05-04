from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from .tool_resolution import cached_resolution, freeze_cache_value


DEFAULT_ARM_GDB_ENV_VAR = "STM32_ARM_GDB_PATH"
DEFAULT_ARM_GDB_CANDIDATES = {
    "windows": [
        r"C:\ST\STM32CubeIDE_1.14.1\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.win32_12.3.rel1\tools\bin\arm-none-eabi-gdb.exe",
    ],
    "linux": ["arm-none-eabi-gdb"],
    "darwin": ["arm-none-eabi-gdb"],
}


def default_arm_gdb_executable_name(host_platform: str) -> str:
    return "arm-none-eabi-gdb.exe" if host_platform == "windows" else "arm-none-eabi-gdb"


def derive_arm_gdb_candidates(
    *,
    resolve_cubeide_path: Callable[[], str],
    host_platform: str,
) -> list[Path]:
    try:
        cubeide_path = Path(resolve_cubeide_path()).resolve()
    except FileNotFoundError:
        return []

    cubeide_root = cubeide_path.parent
    executable_name = default_arm_gdb_executable_name(host_platform)
    plugin_candidates = sorted(
        cubeide_root.glob("plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32*/tools/bin/*")
    )
    return [candidate for candidate in plugin_candidates if candidate.name.lower() == executable_name.lower()]


def discover_arm_gdb(
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
            configured_arm_gdb = tools.get("arm_gdb")
            if isinstance(configured_arm_gdb, dict):
                tool_entry = configured_arm_gdb

    env_var = str(tool_entry.get("env_var") or DEFAULT_ARM_GDB_ENV_VAR)
    executable_name = str(tool_entry.get("executable_name") or default_arm_gdb_executable_name(host_platform))
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

        for candidate in derive_arm_gdb_candidates(
            resolve_cubeide_path=resolve_cubeide_path,
            host_platform=host_platform,
        ):
            record_candidate(candidate, "cubeide_plugin")

        for candidate in DEFAULT_ARM_GDB_CANDIDATES.get(host_platform, []):
            record_candidate(Path(candidate), "default")

        return {
            "tool": "arm_gdb",
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

    return cached_resolution("arm_gdb", cache_key, resolve_discovery)


def build_gdb_batch_command(gdb_path: str, *, elf_path: str | None, port_number: int, commands: list[str]) -> list[str]:
    command = [
        gdb_path,
        "--quiet",
        "--batch",
    ]
    if isinstance(elf_path, str) and elf_path.strip() and Path(elf_path).is_file():
        command.append(elf_path)
    command.extend([
        "-ex",
        "set pagination off",
        "-ex",
        f"target extended-remote :{port_number}",
    ])
    for gdb_command in commands:
        command.extend(["-ex", gdb_command])
    command.extend(["-ex", "disconnect", "-ex", "quit"])
    return command


def build_gdb_version_command(gdb_path: str) -> list[str]:
    return [gdb_path, "--version"]


def resolve_arm_gdb_path(discovery: dict[str, object]) -> str:
    tool_path = discovery.get("resolved_path")
    if isinstance(tool_path, str) and Path(tool_path).is_file():
        return tool_path

    checked_paths = [str(candidate["path"]) for candidate in discovery.get("checked_candidates", [])]
    checked_suffix = f" Checked: {checked_paths}." if checked_paths else ""
    env_var = str(discovery.get("env_var") or DEFAULT_ARM_GDB_ENV_VAR)
    raise FileNotFoundError(
        "ARM GDB executable was not found. Set "
        f"{env_var}, add arm-none-eabi-gdb to PATH, or update config/stm32-tools.local.json."
        f"{checked_suffix}"
    )