from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence
from typing import Callable

from .tool_resolution import cached_resolution, freeze_cache_value


DEFAULT_CLI_PATH = (
    r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"
)
DEFAULT_CLI_CANDIDATES = {
    "windows": [DEFAULT_CLI_PATH],
    "linux": [
        "/opt/st/stm32cubeprogrammer/bin/STM32_Programmer_CLI",
        "/usr/local/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI",
    ],
    "darwin": [
        "/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/MacOs/bin/STM32_Programmer_CLI",
        "/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI",
    ],
}
DEFAULT_CLI_ENV_VAR = "STM32_PROGRAMMER_CLI_PATH"


def default_cli_executable_name(host_platform: str) -> str:
    return "STM32_Programmer_CLI.exe" if host_platform == "windows" else "STM32_Programmer_CLI"


# Discover STM32CubeProgrammer CLI candidates from environment, config, PATH, and platform defaults, then cache the result.
def discover_cube_programmer(
    *,
    host_platform: str,
    load_tools_local_config: Callable[[], dict[str, object]],
    resolve_candidate_path: Callable[[str, Path | None], Path],
    which_resolver: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    tools_config = load_tools_local_config()
    config_data = tools_config.get("data")
    tool_entry: dict[str, object] = {}

    if isinstance(config_data, dict):
        tools = config_data.get("tools")
        if isinstance(tools, dict):
            cube_programmer = tools.get("cube_programmer")
            if isinstance(cube_programmer, dict):
                tool_entry = cube_programmer

    env_var = str(tool_entry.get("env_var") or DEFAULT_CLI_ENV_VAR)
    executable_name = str(tool_entry.get("executable_name") or default_cli_executable_name(host_platform))
    config_path = Path(str(tools_config["path"])) if isinstance(tools_config.get("path"), str) else None
    which_result = which_resolver(executable_name)
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

        for candidate in DEFAULT_CLI_CANDIDATES.get(host_platform, []):
            record_candidate(Path(candidate), "default")

        return {
            "tool": "cube_programmer",
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

    return cached_resolution("cube_programmer", cache_key, resolve_discovery)


def build_connect_command(cli_path: str, connect_arguments: list[str]) -> list[str]:
    return [cli_path, *connect_arguments]


def build_download_arguments(
    file_path: str,
    address: str | None = None,
    *,
    incremental: bool = False,
    skip_erase: bool = False,
    verify_mode: str = "legacy",
) -> list[str]:
    arguments: list[str] = []
    if skip_erase:
        arguments.append("--skipErase")
    arguments.extend(["--download", file_path])
    if address is not None:
        arguments.append(address)
    if incremental:
        arguments.append("incremental")
    if verify_mode == "legacy":
        arguments.append("--verify")
    elif verify_mode == "fast":
        arguments.extend(["--verify", "fast"])
    return arguments


def build_post_download_arguments(post_action: str) -> list[str]:
    if post_action == "none":
        return []
    if post_action == "reset":
        return ["-rst"]
    if post_action == "hardware_reset":
        return ["-hardRst"]
    return ["--go"]


def build_erase_arguments(sectors: Sequence[str] | None = None) -> list[str]:
    arguments = ["--erase"]
    if sectors:
        arguments.extend(str(token) for token in sectors)
    else:
        arguments.append("all")
    return arguments


def build_flash_arguments(
    file_path: str,
    address: str | None = None,
    *,
    sectors: Sequence[str] | None = None,
    incremental: bool = False,
    verify_mode: str = "legacy",
    post_action: str = "go",
) -> list[str]:
    return [
        *build_erase_arguments(sectors),
        *build_download_arguments(
            file_path,
            address,
            incremental=incremental,
            skip_erase=True,
            verify_mode=verify_mode,
        ),
        *build_post_download_arguments(post_action),
    ]


def build_verify_arguments(verify_mode: str = "legacy") -> list[str]:
    if verify_mode == "none":
        return []
    if verify_mode == "fast":
        return ["--verify", "fast"]
    return ["--verify"]


def build_reset_arguments(reset_kind: str = "software") -> list[str]:
    mapping = {
        "software": ["-rst"],
        "hardware": ["-hardRst"],
        "bootloader": ["-rstbl"],
    }
    return mapping[reset_kind]


def build_upload_arguments(address: str, size: int, file_path: str) -> list[str]:
    return ["--upload", address, str(size), file_path]


def build_checksum_arguments(address: str | None = None, size: int | None = None) -> list[str]:
    arguments = ["--checksum"]
    if address is not None:
        arguments.append(address)
    if size is not None:
        arguments.append(str(size))
    return arguments


def build_read_memory_arguments(width: int, address: str, size: int) -> list[str]:
    return [f"-r{width}", address, str(size)]


def build_write_memory_arguments(
    width: int,
    address: str,
    data: Sequence[int],
    *,
    verify: bool = True,
) -> list[str]:
    arguments = [f"-w{width}", address, *(str(token) for token in data)]
    if not verify:
        arguments.append("--noverify")
    return arguments


def build_go_arguments(address: str | None = None) -> list[str]:
    arguments = ["--go"]
    if address is not None:
        arguments.append(address)
    return arguments


# Resolve the CLI path from discovery output and raise a detailed error that includes the checked locations when none worked.
def resolve_cube_programmer_path(discovery: dict[str, object]) -> str:
    cli_path = discovery.get("resolved_path")
    if isinstance(cli_path, str) and Path(cli_path).is_file():
        return cli_path

    checked_paths = [str(candidate["path"]) for candidate in discovery.get("checked_candidates", [])]
    checked_suffix = f" Checked: {checked_paths}." if checked_paths else ""
    env_var = str(discovery.get("env_var") or DEFAULT_CLI_ENV_VAR)
    if discovery.get("config_error"):
        checked_suffix = f" Config error: {discovery['config_error']}.{checked_suffix}"

    if discovery.get("path_hint"):
        checked_suffix = f"{checked_suffix} PATH lookup name: {discovery['path_hint']}."

    raise FileNotFoundError(
        "STM32CubeProgrammer CLI was not found. Set "
        f"{env_var}, add STM32_Programmer_CLI to PATH, or install the tool at {DEFAULT_CLI_PATH}."
        f"{checked_suffix}"
    )


# Run the STM32CubeProgrammer CLI and normalize success, missing-tool, and timeout outcomes into a consistent result shape.
def run_cli_command(
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
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        return {
            "success": completed.returncode == 0,
            "exit_code": completed.returncode,
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
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
        stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
        timeout_message = f"Command timed out after {timeout_seconds} seconds."
        return {
            "success": False,
            "exit_code": -1,
            "command": command,
            "stdout": stdout,
            "stderr": f"{stderr}\n{timeout_message}".strip(),
        }