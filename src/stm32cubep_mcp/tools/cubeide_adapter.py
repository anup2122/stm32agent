from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable


DEFAULT_CUBEIDE_ENV_VAR = "STM32CUBEIDE_CLI_PATH"
DEFAULT_CUBEIDE_CANDIDATES = {
    "windows": [
        r"C:\ST\STM32CubeIDE_2.1.1\STM32CubeIDE\stm32cubeidec.exe",
        r"C:\ST\STM32CubeIDE_1.14.1\STM32CubeIDE\stm32cubeidec.exe",
    ],
    "linux": ["stm32cubeidec"],
    "darwin": ["stm32cubeidec"],
}
SKIPPED_BUILD_PATTERNS = (
    "doesn't appear to be a cdt project. skipping",
    'warning: no config matched',
)
IMPORT_ALREADY_EXISTS_PATTERNS = (
    "already exists in the workspace",
    "already exists in workspace",
)


def default_cubeide_executable_name(host_platform: str) -> str:
    return "stm32cubeidec.exe" if host_platform == "windows" else "stm32cubeidec"


def cubeide_tool_entry(load_tools_local_config: Callable[[], dict[str, object]]) -> dict[str, object]:
    tools_config = load_tools_local_config()
    config_data = tools_config.get("data")
    if not isinstance(config_data, dict):
        return {}
    tools = config_data.get("tools")
    if not isinstance(tools, dict):
        return {}
    tool_entry = tools.get("cubeide")
    return tool_entry if isinstance(tool_entry, dict) else {}


def discover_cubeide(
    *,
    host_platform: str,
    backend: str,
    load_tools_local_config: Callable[[], dict[str, object]],
    resolve_candidate_path: Callable[[str, Path | None], Path],
) -> dict[str, object]:
    tools_config = load_tools_local_config()
    tool_entry = cubeide_tool_entry(load_tools_local_config)
    env_var = str(tool_entry.get("env_var") or DEFAULT_CUBEIDE_ENV_VAR)
    executable_name = str(tool_entry.get("executable_name") or default_cubeide_executable_name(host_platform))
    config_path = Path(str(tools_config["path"])) if isinstance(tools_config.get("path"), str) else None
    checked_candidates: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    resolved_path: str | None = None
    resolution_source: str | None = None

    def record_candidate(path_value: str | Path, source: str) -> None:
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
                    record_candidate(resolve_candidate_path(candidate, config_path), "config")

    which_result = shutil.which(executable_name)
    if which_result:
        record_candidate(which_result, "path")

    for candidate in DEFAULT_CUBEIDE_CANDIDATES.get(host_platform, []):
        record_candidate(Path(candidate), "default")

    return {
        "tool": "cubeide",
        "backend": backend,
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


def resolve_cubeide_path(discovery: dict[str, object]) -> str:
    cli_path = discovery.get("resolved_path")
    if isinstance(cli_path, str) and Path(cli_path).is_file():
        return cli_path

    checked_paths = [str(candidate["path"]) for candidate in discovery.get("checked_candidates", [])]
    checked_suffix = f" Checked: {checked_paths}." if checked_paths else ""
    env_var = str(discovery.get("env_var") or DEFAULT_CUBEIDE_ENV_VAR)
    path_hint = str(discovery.get("path_hint") or "")
    if discovery.get("config_error"):
        checked_suffix = f" Config error: {discovery['config_error']}.{checked_suffix}"

    raise FileNotFoundError(
        f"STM32CubeIDE headless CLI was not found. Set {env_var}, add {path_hint} to PATH, "
        f"or configure the cubeide tool path in stm32-tools.local.jsonc.{checked_suffix}"
    )


def run_build_command(
    command: list[str],
    *,
    cwd: str | Path | None = None,
    timeout_seconds: int = 600,
) -> dict[str, object]:
    working_directory = Path(cwd).resolve() if cwd is not None else None
    try:
        completed = subprocess.run(
            [str(argument) for argument in command],
            cwd=str(working_directory) if working_directory is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "success": False,
            "exit_code": None,
            "command": [str(argument) for argument in command],
            "cwd": str(working_directory) if working_directory is not None else None,
            "stdout": "",
            "stderr": str(exc),
            "message": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "exit_code": None,
            "command": [str(argument) for argument in command],
            "cwd": str(working_directory) if working_directory is not None else None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "timed_out": True,
            "message": f"CubeIDE build command timed out after {timeout_seconds} seconds.",
        }

    return {
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "command": [str(argument) for argument in command],
        "cwd": str(working_directory) if working_directory is not None else None,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def cubeide_import_already_present(result: dict[str, object]) -> bool:
    combined_output = "\n".join(
        [
            str(result.get("stdout", "")),
            str(result.get("stderr", "")),
        ]
    ).lower()
    return any(pattern in combined_output for pattern in IMPORT_ALREADY_EXISTS_PATTERNS)


def cubeide_build_succeeded(result: dict[str, object]) -> bool:
    if not result.get("success"):
        return False
    combined_output = "\n".join(
        [
            str(result.get("stdout", "")),
            str(result.get("stderr", "")),
        ]
    ).lower()
    return not any(pattern in combined_output for pattern in SKIPPED_BUILD_PATTERNS)


def reset_cubeide_workspace(workspace: Path) -> None:
    resolved_workspace = workspace.resolve()
    if resolved_workspace.exists():
        shutil.rmtree(resolved_workspace)
    resolved_workspace.mkdir(parents=True, exist_ok=True)
