from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

from mcp import types as mcp_types
from mcp.server.fastmcp import Context, FastMCP

from .. import shared

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
LOCAL_TOOLS_CONFIG_ENV_VAR = "STM32_TOOLS_LOCAL_JSON"
LOCAL_TOOLS_CONFIG_PATHS = (
    "config/stm32-tools.local.json",
    "stm32-tools.local.json",
    ".vscode/stm32-tools.local.json",
    ".github/stm32-tools.local.json",
)
TOOLS_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "stm32-tools.local.schema.json"
SERVER_WORKFLOW_CAPABILITIES = {
    "device_connect": True,
    "flash": True,
    "memory_access": True,
    "core_control": True,
    "build": False,
    "structured_debug_snapshots": False,
    "orchestration_workflows": False,
}

Parity = Literal["NONE", "ODD", "EVEN"]
FlowControl = Literal["OFF", "Hardware", "Software"]
ResetMode = Literal["SWrst", "HWrst", "Crst"]
ConnectionMode = Literal["UR", "HOTPLUG", "NORMAL", "POWERDOWN", "HWRSTPULSE"]
LowPowerMode = Literal["inherit", "enable", "disable"]
SpeedMode = Literal["Reliable", "fast"]
LevelState = Literal["low", "high"]
VerifyMode = Literal["none", "legacy", "fast"]
InterfaceName = Literal["uart", "usb", "st-link", "stlink", "st-link-only", "stlink-only"]
ResetKind = Literal["software", "hardware", "bootloader"]
MemoryWidth = Literal[8, 16, 32]
PostDownloadAction = Literal["none", "reset", "hardware_reset", "go"]

mcp = FastMCP("stm32cubeprogrammer")
DEFAULT_LOGS_DIR = Path(__file__).resolve().parents[3] / "logs"
SUPPORTED_FIRMWARE_SUFFIXES = {".axf", ".elf", ".bin", ".hex", ".srec", ".s19", ".stm32", ".tsv"}
TARGET_TOKEN_PATTERN = re.compile(r"(?:STM32)?([A-Z]\d{3}[A-Z]{0,3})", re.IGNORECASE)
DEFAULT_LLM_RECOVERY_MAX_ATTEMPTS = 3
RECOVERY_TEXT_LIMIT = 4000
RECOVERY_CONNECTED_ACTIONS = (
    "retry_operation",
    "core_status",
    "reset",
    "halt",
    "go",
    "list_interfaces",
    "programmer_version",
    "ask_user",
)
RECOVERY_CONNECT_ACTIONS = (
    "retry_operation",
    "list_interfaces",
    "programmer_version",
    "ask_user",
)
RECOVERY_CONNECT_OVERRIDE_KEYS = {
    "port",
    "serial_number",
    "usb_product_id",
    "usb_vendor_id",
    "baudrate",
    "parity",
    "data_bits",
    "stop_bits",
    "flow_control",
    "rts",
    "dtr",
    "no_init_bits",
    "enable_console",
    "frequency_khz",
    "probe_index",
    "access_port",
    "mode",
    "reset",
    "shared_mode",
    "tcp_port",
    "low_power_mode",
    "get_auth_id",
    "speed",
    "target_sel",
}


def resolve_cli_path() -> str:
    discovery = discover_cube_programmer()
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


def host_platform_name() -> str:
    system_name = platform.system().lower()
    if system_name.startswith("win"):
        return "windows"
    if system_name.startswith("linux"):
        return "linux"
    if system_name.startswith("darwin"):
        return "darwin"
    return system_name or "unknown"


def default_cli_executable_name() -> str:
    return "STM32_Programmer_CLI.exe" if host_platform_name() == "windows" else "STM32_Programmer_CLI"


def unique_paths(paths: Sequence[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = os.path.normcase(str(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(path)
    return unique


def config_search_paths(env_var: str, relative_paths: Sequence[str]) -> list[Path]:
    search_paths: list[Path] = []
    env_path = os.environ.get(env_var)
    if env_path:
        search_paths.append(Path(env_path).expanduser())

    workspace_root = Path.cwd()
    for relative_path in relative_paths:
        search_paths.append((workspace_root / relative_path).expanduser())

    return unique_paths(search_paths)


def validate_string_list(value: object, field_name: str, errors: list[str]) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{field_name} must be an array of non-empty strings.")


def validate_tools_local_schema(payload: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Document must be a JSON object."]

    version = payload.get("version")
    if not isinstance(version, int):
        errors.append("version must be an integer.")

    tools = payload.get("tools")
    if not isinstance(tools, dict):
        errors.append("tools must be an object.")
        return errors

    supported_tools = ("cube_programmer", "cubeide", "cubemx", "stlink_gdb_server", "arm_gdb")
    for tool_name in supported_tools:
        tool_entry = tools.get(tool_name)
        if tool_entry is None:
            continue
        if not isinstance(tool_entry, dict):
            errors.append(f"tools.{tool_name} must be an object when provided.")
            continue

        env_var = tool_entry.get("env_var")
        if env_var is not None and not isinstance(env_var, str):
            errors.append(f"tools.{tool_name}.env_var must be a string when provided.")

        executable_name = tool_entry.get("executable_name")
        if executable_name is not None and not isinstance(executable_name, str):
            errors.append(f"tools.{tool_name}.executable_name must be a string when provided.")

        candidates = tool_entry.get("candidates")
        if candidates is not None and not isinstance(candidates, dict):
            errors.append(f"tools.{tool_name}.candidates must be an object when provided.")
        elif isinstance(candidates, dict):
            for platform_name, platform_candidates in candidates.items():
                validate_string_list(platform_candidates, f"tools.{tool_name}.candidates.{platform_name}", errors)

    return errors


def load_optional_json_config(
    *,
    env_var: str,
    relative_paths: Sequence[str],
    schema_path: Path,
    validator: Callable[[object], list[str]],
) -> dict[str, object]:
    searched_paths = config_search_paths(env_var, relative_paths)
    for candidate_path in searched_paths:
        if not candidate_path.is_file():
            continue

        try:
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "status": "invalid",
                "path": str(candidate_path),
                "searched_paths": [str(path) for path in searched_paths],
                "schema_path": str(schema_path),
                "errors": [f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}."],
                "data": None,
            }

        errors = validator(payload)
        return {
            "status": "loaded" if not errors else "invalid",
            "path": str(candidate_path),
            "searched_paths": [str(path) for path in searched_paths],
            "schema_path": str(schema_path),
            "errors": errors,
            "data": payload if not errors else None,
        }

    return {
        "status": "not_found",
        "path": None,
        "searched_paths": [str(path) for path in searched_paths],
        "schema_path": str(schema_path),
        "errors": [],
        "data": None,
    }


def load_tools_local_config() -> dict[str, object]:
    return load_optional_json_config(
        env_var=LOCAL_TOOLS_CONFIG_ENV_VAR,
        relative_paths=LOCAL_TOOLS_CONFIG_PATHS,
        schema_path=TOOLS_SCHEMA_PATH,
        validator=validate_tools_local_schema,
    )


def resolve_candidate_path(candidate: str, *, base_path: Path | None = None) -> Path:
    path = Path(candidate).expanduser()
    if path.is_absolute() or base_path is None:
        return path
    return (base_path.parent / path).resolve()


def discover_cube_programmer() -> dict[str, object]:
    host_platform = host_platform_name()
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
    executable_name = str(tool_entry.get("executable_name") or default_cli_executable_name())
    config_path = Path(str(tools_config["path"])) if isinstance(tools_config.get("path"), str) else None
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

    which_result = shutil.which(executable_name)
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


def summarize_config_status(config_result: dict[str, object]) -> dict[str, object]:
    return {
        "status": config_result.get("status"),
        "path": config_result.get("path"),
        "schema_path": config_result.get("schema_path"),
        "errors": list(config_result.get("errors", [])),
        "searched_paths": list(config_result.get("searched_paths", [])),
    }


def collect_host_tool_discovery() -> dict[str, object]:
    tools_config = load_tools_local_config()
    project_metadata = shared.load_project_metadata()
    cube_programmer = discover_cube_programmer()
    return {
        "host": {
            "platform": host_platform_name(),
            "workspace_root": str(Path.cwd()),
        },
        "schemas": {
            "stm32_tools_local": str(TOOLS_SCHEMA_PATH),
            "stm32_project": str(shared.PROJECT_SCHEMA_PATH),
        },
        "configurations": {
            "stm32_tools_local": summarize_config_status(tools_config),
            "stm32_project": summarize_config_status(project_metadata),
        },
        "tools": {
            "cube_programmer": cube_programmer,
        },
    }


def parse_programmer_version(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.strip():
            return line.strip()
    return None


def collect_host_capabilities(timeout_seconds: int = 10) -> dict[str, object]:
    discovery = collect_host_tool_discovery()
    cube_programmer = dict(discovery["tools"]["cube_programmer"])
    version_result: dict[str, object] | None = None
    runnable = False
    version_text: str | None = None

    resolved_path = cube_programmer.get("resolved_path")
    if isinstance(resolved_path, str):
        version_result = run_cli_command([resolved_path, "--version"], timeout_seconds)
        runnable = bool(version_result.get("success"))
        version_text = parse_programmer_version(str(version_result.get("stdout", "")))

    cube_programmer["runnable"] = runnable
    cube_programmer["version"] = version_text
    cube_programmer["version_check"] = version_result

    project_status = discovery["configurations"]["stm32_project"]["status"]
    capability_flags = {
        **SERVER_WORKFLOW_CAPABILITIES,
        "cube_programmer_cli": bool(resolved_path),
        "project_metadata_loaded": project_status == "loaded",
    }
    if not runnable:
        capability_flags["device_connect"] = False
        capability_flags["flash"] = False
        capability_flags["memory_access"] = False
        capability_flags["core_control"] = False

    return {
        **discovery,
        "tools": {
            "cube_programmer": cube_programmer,
        },
        "capabilities": capability_flags,
    }


def append_key_value(command: list[str], key: str, value: object | None) -> None:
    if value is None:
        return
    command.append(f"{key}={value}")


def normalize_tokens(values: Sequence[str | int]) -> list[str]:
    return [str(value) for value in values]


def default_connect_settings() -> dict[str, object]:
    return {
        "port": "SWD",
        "frequency_khz": 4000,
        "mode": "NORMAL",
        "reset": "SWrst",
    }


def log_directory() -> Path:
    logs_dir = Path(os.environ.get("STM32CUBEP_MCP_LOG_DIR", DEFAULT_LOGS_DIR))
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def create_log_path(prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_directory() / f"{prefix}_{timestamp}.log"


def build_fallback_attempts(overrides: dict[str, object]) -> list[dict[str, object]]:
    defaults = default_connect_settings()
    fallback_attempts: list[dict[str, object]] = [
        defaults,
        {**defaults, "mode": "HOTPLUG"},
        {**defaults, "mode": "UR", "reset": "HWrst"},
        {**defaults, "frequency_khz": 1000, "mode": "NORMAL", "reset": "HWrst"},
        {**defaults, "frequency_khz": 1000, "mode": "HOTPLUG", "reset": "HWrst"},
    ]
    attempts: list[dict[str, object]] = []

    for fallback in fallback_attempts:
        merged = dict(fallback)
        merged.update({key: value for key, value in overrides.items() if value is not None})
        if merged not in attempts:
            attempts.append(merged)
    return attempts


def build_connect_arguments(
    *,
    port: str,
    serial_number: str | None = None,
    usb_product_id: str | None = None,
    usb_vendor_id: str | None = None,
    baudrate: int | None = None,
    parity: Parity | None = None,
    data_bits: int | None = None,
    stop_bits: str | None = None,
    flow_control: FlowControl | None = None,
    rts: LevelState | None = None,
    dtr: LevelState | None = None,
    no_init_bits: int | None = None,
    enable_console: bool = False,
    frequency_khz: int | None = None,
    probe_index: int | None = None,
    access_port: int | None = None,
    mode: ConnectionMode | None = None,
    reset: ResetMode | None = None,
    shared_mode: bool = False,
    tcp_port: int | None = None,
    low_power_mode: LowPowerMode = "inherit",
    get_auth_id: bool = False,
    speed: SpeedMode | None = None,
    target_sel: str | None = None,
) -> list[str]:
    arguments = ["--connect", f"port={port}"]

    append_key_value(arguments, "sn", serial_number)
    append_key_value(arguments, "PID", usb_product_id)
    append_key_value(arguments, "VID", usb_vendor_id)
    append_key_value(arguments, "br", baudrate)
    append_key_value(arguments, "P", parity)
    append_key_value(arguments, "db", data_bits)
    append_key_value(arguments, "sb", stop_bits)
    append_key_value(arguments, "fc", flow_control)
    append_key_value(arguments, "rts", rts)
    append_key_value(arguments, "dtr", dtr)
    append_key_value(arguments, "noinit", no_init_bits)

    if enable_console:
        arguments.append("console")

    append_key_value(arguments, "freq", frequency_khz)
    append_key_value(arguments, "index", probe_index)
    append_key_value(arguments, "ap", access_port)
    append_key_value(arguments, "mode", mode)
    append_key_value(arguments, "reset", reset)

    if shared_mode:
        arguments.append("shared")

    append_key_value(arguments, "tcpport", tcp_port)

    if low_power_mode == "enable":
        arguments.append("LPM")
    elif low_power_mode == "disable":
        arguments.append("dLPM")

    if get_auth_id:
        arguments.append("getAuthID")

    append_key_value(arguments, "speed", speed)
    append_key_value(arguments, "TargetSel", target_sel)
    return arguments


def build_connect_command(**connect_kwargs: object) -> list[str]:
    return [resolve_cli_path(), *build_connect_arguments(**connect_kwargs)]


def build_download_arguments(
    file_path: str,
    address: str | None = None,
    *,
    incremental: bool = False,
    skip_erase: bool = False,
    verify_mode: VerifyMode = "legacy",
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


def validate_download_inputs(file_path: str, address: str | None = None) -> Path:
    firmware_path = Path(file_path)
    if not firmware_path.is_file():
        raise FileNotFoundError(f"Firmware file not found: {firmware_path}")

    suffix = firmware_path.suffix.lower()
    if suffix and suffix not in SUPPORTED_FIRMWARE_SUFFIXES:
        raise ValueError(
            "Unsupported firmware file type. Expected one of: "
            + ", ".join(sorted(SUPPORTED_FIRMWARE_SUFFIXES))
        )

    if suffix == ".bin" and address is None:
        raise ValueError("Binary firmware downloads require an explicit start address.")

    return firmware_path


def normalize_target_family(token: str) -> str | None:
    match = re.search(r"([A-Z]\d{3})", token.upper())
    if match is None:
        return None
    return match.group(1)


def extract_target_families_from_text(text: str) -> set[str]:
    families: set[str] = set()
    for token in TARGET_TOKEN_PATTERN.findall(text.upper()):
        family = normalize_target_family(token)
        if family is not None:
            families.add(family)
    return families


def extract_attached_target_families_from_output(text: str) -> set[str]:
    relevant_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Board") or stripped.startswith("Device name"):
            relevant_lines.append(stripped)
    return extract_target_families_from_text("\n".join(relevant_lines))


def extract_target_families_from_file(firmware_path: Path) -> set[str]:
    content = firmware_path.read_bytes().decode("latin-1", errors="ignore")
    combined_text = f"{firmware_path.name}\n{content}"
    return extract_target_families_from_text(combined_text)


def detect_target_mismatch(
    firmware_path: Path,
    command_result: dict[str, object],
    runtime_check_result: dict[str, object] | None = None,
) -> dict[str, object] | None:
    firmware_families = extract_target_families_from_file(firmware_path)
    attached_families = extract_attached_target_families_from_output(str(command_result.get("stdout", "")))

    if runtime_check_result is not None:
        attached_families.update(extract_attached_target_families_from_output(str(runtime_check_result.get("stdout", ""))))

    runtime_halted = runtime_check_result is not None and "Core is halted" in str(runtime_check_result.get("stdout", ""))
    incompatible_families = bool(firmware_families) and bool(attached_families) and firmware_families.isdisjoint(attached_families)

    if not incompatible_families:
        return None

    if command_result.get("success") is False or runtime_halted:
        return {
            "firmware_families": sorted(firmware_families),
            "attached_families": sorted(attached_families),
            "runtime_halted": runtime_halted,
            "reason": "this does not match to the attached target",
        }

    return None


def build_post_download_arguments(post_action: PostDownloadAction) -> list[str]:
    if post_action == "none":
        return []
    if post_action == "reset":
        return ["-rst"]
    if post_action == "hardware_reset":
        return ["-hardRst"]
    return ["--go"]


def build_flash_arguments(
    file_path: str,
    address: str | None = None,
    *,
    sectors: Sequence[str] | None = None,
    incremental: bool = False,
    verify_mode: VerifyMode = "legacy",
    post_action: PostDownloadAction = "go",
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


def build_erase_arguments(sectors: Sequence[str] | None = None) -> list[str]:
    arguments = ["--erase"]
    if sectors:
        arguments.extend(normalize_tokens(sectors))
    else:
        arguments.append("all")
    return arguments


def build_verify_arguments(verify_mode: VerifyMode = "legacy") -> list[str]:
    if verify_mode == "none":
        return []
    if verify_mode == "fast":
        return ["--verify", "fast"]
    return ["--verify"]


def build_reset_arguments(reset_kind: ResetKind = "software") -> list[str]:
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


def build_read_memory_arguments(width: MemoryWidth, address: str, size: int) -> list[str]:
    return [f"-r{width}", address, str(size)]


def build_write_memory_arguments(
    width: MemoryWidth,
    address: str,
    data: Sequence[int],
    *,
    verify: bool = True,
) -> list[str]:
    arguments = [f"-w{width}", address, *normalize_tokens(data)]
    if not verify:
        arguments.append("--noverify")
    return arguments


def build_go_arguments(address: str | None = None) -> list[str]:
    arguments = ["--go"]
    if address is not None:
        arguments.append(address)
    return arguments


def run_cli_command(command: list[str], timeout_seconds: int) -> dict[str, object]:
    try:
        completed = subprocess.run(
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


def llm_recovery_enabled() -> bool:
    raw_value = os.environ.get("STM32CUBEP_MCP_ENABLE_LLM_RECOVERY", "true").strip().lower()
    return raw_value not in {"0", "false", "no", "off", "disable", "disabled"}


def llm_recovery_max_attempts() -> int:
    raw_value = os.environ.get(
        "STM32CUBEP_MCP_LLM_RECOVERY_MAX_ATTEMPTS",
        str(DEFAULT_LLM_RECOVERY_MAX_ATTEMPTS),
    ).strip()
    try:
        return max(1, min(10, int(raw_value)))
    except ValueError:
        return DEFAULT_LLM_RECOVERY_MAX_ATTEMPTS


def truncate_recovery_text(value: object, limit: int = RECOVERY_TEXT_LIMIT) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[truncated]"


def summarize_result_for_recovery(result: dict[str, object]) -> dict[str, object]:
    return {
        "success": bool(result.get("success")),
        "message": result.get("message"),
        "operation": result.get("operation"),
        "exit_code": result.get("exit_code"),
        "log_file": result.get("log_file"),
        "connect_parameters": result.get("connect_parameters"),
        "action_arguments": result.get("action_arguments"),
        "stdout": truncate_recovery_text(result.get("stdout", "")),
        "stderr": truncate_recovery_text(result.get("stderr", "")),
    }


def extract_sampling_text(sampling_result: object) -> str:
    content = getattr(sampling_result, "content", "")
    blocks = content if isinstance(content, list) else [content]
    parts: list[str] = []

    for block in blocks:
        if hasattr(block, "text"):
            parts.append(str(getattr(block, "text")))
        elif isinstance(block, dict) and "text" in block:
            parts.append(str(block["text"]))
        elif block is not None:
            parts.append(str(block))

    return "\n".join(part for part in parts if part).strip()


def extract_json_object(text: str) -> str:
    start_index = text.find("{")
    end_index = text.rfind("}")
    if start_index == -1 or end_index == -1 or end_index <= start_index:
        raise ValueError("LLM recovery response did not contain a JSON object.")
    return text[start_index : end_index + 1]


def sanitize_connect_overrides(overrides: object) -> dict[str, object]:
    if not isinstance(overrides, dict):
        return {}
    return {
        str(key): value
        for key, value in overrides.items()
        if str(key) in RECOVERY_CONNECT_OVERRIDE_KEYS and value is not None
    }


def parse_recovery_suggestion(response_text: str, allowed_actions: Sequence[str]) -> dict[str, object]:
    payload = json.loads(extract_json_object(response_text))
    if not isinstance(payload, dict):
        raise ValueError("LLM recovery response must be a JSON object.")

    action = payload.get("action")
    if not isinstance(action, str) or action not in allowed_actions:
        raise ValueError(f"Unsupported LLM recovery action: {action!r}")

    parameters = payload.get("parameters")
    if parameters is not None and not isinstance(parameters, dict):
        raise ValueError("LLM recovery parameters must be an object when provided.")

    suggestion: dict[str, object] = {
        "summary": str(payload.get("summary", "")).strip(),
        "action": action,
        "reason": str(payload.get("reason", "")).strip(),
        "connect_overrides": sanitize_connect_overrides(payload.get("connect_overrides")),
        "parameters": parameters or {},
        "user_action": str(payload.get("user_action", "")).strip(),
    }
    return suggestion


def build_recovery_prompt(
    *,
    operation: str,
    result: dict[str, object],
    action_arguments: Sequence[str],
    connect_kwargs: dict[str, object],
    recovery_history: list[dict[str, object]],
    allowed_actions: Sequence[str],
) -> str:
    schema = {
        "summary": "short status summary",
        "action": allowed_actions[0],
        "reason": "why this is the next best step",
        "connect_overrides": {
            "mode": "HOTPLUG",
            "reset": "HWrst",
            "frequency_khz": 1000,
        },
        "parameters": {
            "reset_kind": "hardware",
            "address": "0x08000000",
        },
        "user_action": "what the user should do if no safe automated step remains",
    }
    return (
        "You are assisting an STM32CubeProgrammer MCP server with automated recovery.\n"
        "Return exactly one JSON object and no markdown.\n"
        f"Allowed actions: {', '.join(allowed_actions)}\n"
        "Action meanings:\n"
        "- retry_operation: rerun the original failed STM32 operation, optionally with connect_overrides\n"
        "- core_status: run core status on the currently attached target\n"
        "- reset: run stm32 reset, optionally with parameters.reset_kind = software|hardware|bootloader\n"
        "- halt: halt the core\n"
        "- go: run the core, optionally with parameters.address\n"
        "- list_interfaces: list available STM32 interfaces\n"
        "- programmer_version: read STM32CubeProgrammer version\n"
        "- ask_user: stop automated recovery and explain the exact next manual action\n"
        "Rules:\n"
        "- Pick exactly one next step.\n"
        "- Prefer the least destructive action that increases confidence.\n"
        "- Never invent new action names.\n"
        "- Use connect_overrides only for actual connection changes.\n"
        "- If no safe automated step remains, use ask_user.\n"
        f"Response schema example: {json.dumps(schema, indent=2)}\n"
        f"Original operation: {operation}\n"
        f"Current connect parameters: {json.dumps(connect_kwargs, indent=2, default=str)}\n"
        f"Original action arguments: {json.dumps(list(action_arguments), indent=2)}\n"
        f"Current failure result: {json.dumps(summarize_result_for_recovery(result), indent=2, default=str)}\n"
        f"Recovery history so far: {json.dumps(recovery_history, indent=2, default=str)}"
    )


async def request_llm_recovery_step(
    ctx: Context,
    *,
    operation: str,
    result: dict[str, object],
    action_arguments: Sequence[str],
    connect_kwargs: dict[str, object],
    recovery_history: list[dict[str, object]],
    allowed_actions: Sequence[str],
) -> dict[str, object]:
    prompt = build_recovery_prompt(
        operation=operation,
        result=result,
        action_arguments=action_arguments,
        connect_kwargs=connect_kwargs,
        recovery_history=recovery_history,
        allowed_actions=allowed_actions,
    )
    sampling_result = await ctx.session.create_message(
        messages=[
            mcp_types.SamplingMessage(
                role="user",
                content=mcp_types.TextContent(type="text", text=prompt),
            )
        ],
        max_tokens=500,
        system_prompt=(
            "You are a careful STM32 debugging planner. Respond with exactly one JSON object that selects one safe next action."
        ),
        temperature=0,
    )
    return parse_recovery_suggestion(extract_sampling_text(sampling_result), allowed_actions)


def execute_llm_recovery_action(
    *,
    recovery_kind: Literal["connect", "connected"],
    suggestion: dict[str, object],
    timeout_seconds: int,
    connect_kwargs: dict[str, object],
    retry_operation: Callable[[dict[str, object]], dict[str, object]],
) -> tuple[dict[str, object] | None, dict[str, object]]:
    merged_connect_kwargs = dict(connect_kwargs)
    merged_connect_kwargs.update(suggestion.get("connect_overrides", {}))
    parameters = suggestion.get("parameters", {})
    action = str(suggestion["action"])
    recovery_timeout = min(timeout_seconds, 45)

    if action == "retry_operation":
        return retry_operation(merged_connect_kwargs), merged_connect_kwargs

    if action == "list_interfaces":
        return (
            execute_global_command(
                operation="recovery_list_interfaces",
                log_prefix="recovery_list",
                command_arguments=["--list"],
                timeout_seconds=recovery_timeout,
                success_message="Listed STM32 communication interfaces.",
                failure_message="Unable to list STM32 communication interfaces.",
            ),
            merged_connect_kwargs,
        )

    if action == "programmer_version":
        return (
            execute_global_command(
                operation="recovery_programmer_version",
                log_prefix="recovery_version",
                command_arguments=["--version"],
                timeout_seconds=min(recovery_timeout, 20),
                success_message="Retrieved STM32CubeProgrammer version.",
                failure_message="Unable to retrieve STM32CubeProgrammer version.",
            ),
            merged_connect_kwargs,
        )

    if recovery_kind == "connect" or action == "ask_user":
        return None, merged_connect_kwargs

    if action == "core_status":
        return (
            execute_connected_operation(
                operation="recovery_core_status",
                log_prefix="recovery_score",
                action_arguments=["-score"],
                timeout_seconds=recovery_timeout,
                **merged_connect_kwargs,
            ),
            merged_connect_kwargs,
        )

    if action == "reset":
        reset_kind = str(parameters.get("reset_kind", "software"))
        return (
            execute_connected_operation(
                operation="recovery_reset",
                log_prefix="recovery_reset",
                action_arguments=build_reset_arguments(reset_kind),
                timeout_seconds=recovery_timeout,
                **merged_connect_kwargs,
            ),
            merged_connect_kwargs,
        )

    if action == "halt":
        return (
            execute_connected_operation(
                operation="recovery_halt",
                log_prefix="recovery_halt",
                action_arguments=["-halt"],
                timeout_seconds=recovery_timeout,
                **merged_connect_kwargs,
            ),
            merged_connect_kwargs,
        )

    if action == "go":
        address = parameters.get("address")
        return (
            execute_connected_operation(
                operation="recovery_go",
                log_prefix="recovery_go",
                action_arguments=build_go_arguments(str(address) if address is not None else None),
                timeout_seconds=recovery_timeout,
                **merged_connect_kwargs,
            ),
            merged_connect_kwargs,
        )

    raise ValueError(f"Unsupported LLM recovery action: {action}")


async def maybe_run_llm_recovery(
    result: dict[str, object],
    ctx: Context | None,
    *,
    operation: str,
    recovery_kind: Literal["connect", "connected"],
    action_arguments: Sequence[str],
    connect_kwargs: dict[str, object],
    timeout_seconds: int,
    retry_operation: Callable[[dict[str, object]], dict[str, object]],
    allowed_actions: Sequence[str],
) -> dict[str, object]:
    recovery_info: dict[str, object] = {
        "enabled": llm_recovery_enabled(),
        "attempted": False,
        "attempts_used": 0,
        "max_attempts": llm_recovery_max_attempts(),
        "status": "not_needed" if result.get("success") else "skipped",
        "history": [],
    }
    result["llm_recovery"] = recovery_info

    if result.get("success") or ctx is None or not llm_recovery_enabled():
        if ctx is None and not result.get("success"):
            recovery_info["status"] = "context_unavailable"
        elif not llm_recovery_enabled() and not result.get("success"):
            recovery_info["status"] = "disabled"
        return result

    current_result = result
    recovery_info["attempted"] = True

    for attempt_index in range(1, llm_recovery_max_attempts() + 1):
        recovery_info["attempts_used"] = attempt_index
        try:
            suggestion = await request_llm_recovery_step(
                ctx,
                operation=operation,
                result=current_result,
                action_arguments=action_arguments,
                connect_kwargs=connect_kwargs,
                recovery_history=recovery_info["history"],
                allowed_actions=allowed_actions,
            )
        except Exception as exc:
            recovery_info["status"] = "sampling_unavailable"
            recovery_info["error"] = str(exc)
            current_result["message"] = (
                f"{current_result.get('message')} Automatic LLM-guided recovery is unavailable with the current MCP client."
            ).strip()
            return current_result

        if suggestion["action"] == "ask_user":
            recovery_info["status"] = "ask_user"
            recovery_info["history"].append(
                {
                    "attempt": attempt_index,
                    "suggestion": suggestion,
                    "result": None,
                }
            )
            if suggestion.get("user_action"):
                current_result["message"] = str(suggestion["user_action"])
                current_result["recovery_user_action"] = suggestion["user_action"]
            else:
                current_result["message"] = (
                    f"{current_result.get('message')} Automatic recovery stopped and needs user action."
                ).strip()
            return current_result

        step_result, updated_connect_kwargs = execute_llm_recovery_action(
            recovery_kind=recovery_kind,
            suggestion=suggestion,
            timeout_seconds=timeout_seconds,
            connect_kwargs=connect_kwargs,
            retry_operation=retry_operation,
        )
        connect_kwargs = updated_connect_kwargs
        recovery_info["history"].append(
            {
                "attempt": attempt_index,
                "suggestion": suggestion,
                "result": summarize_result_for_recovery(step_result) if step_result is not None else None,
            }
        )

        if step_result is not None and step_result.get("success"):
            if suggestion["action"] == "retry_operation":
                recovery_info["status"] = "resolved"
                step_result["recovered"] = True
                step_result["recovery_origin"] = summarize_result_for_recovery(result)
                step_result["llm_recovery"] = recovery_info
                step_result["message"] = (
                    f"{step_result.get('message')} Automatic LLM-guided recovery resolved the failure."
                ).strip()
                return step_result
        if step_result is not None and not step_result.get("success") and suggestion["action"] == "retry_operation":
            current_result = step_result
            current_result["llm_recovery"] = recovery_info

    recovery_info["status"] = "gave_up"
    current_result["message"] = (
        f"{current_result.get('message')} Automatic LLM-guided recovery could not resolve the error after {recovery_info['attempts_used']} attempts. Ask the user to inspect the log file and target setup."
    ).strip()
    return current_result


def write_operation_log(
    log_path: Path,
    *,
    operation: str,
    attempts: list[dict[str, object]],
    selected_attempt: dict[str, object] | None,
) -> None:
    lines = [
        f"timestamp={datetime.now().isoformat(timespec='seconds')}",
        f"operation={operation}",
        f"success={selected_attempt is not None}",
        f"attempt_count={len(attempts)}",
        "",
    ]

    if selected_attempt is not None:
        lines.extend(
            [
                "selected_attempt:",
                f"  exit_code={selected_attempt['exit_code']}",
                f"  connect_parameters={selected_attempt['connect_parameters']}",
                f"  action_arguments={selected_attempt['action_arguments']}",
                "",
            ]
        )

    for index, attempt in enumerate(attempts, start=1):
        lines.extend(
            [
                f"attempt_{index}:",
                f"  command={' '.join(attempt['command'])}",
                f"  exit_code={attempt['exit_code']}",
                f"  success={attempt['success']}",
                f"  connect_parameters={attempt['connect_parameters']}",
                f"  action_arguments={attempt['action_arguments']}",
                "  stdout:",
                *([f"    {line}" for line in attempt['stdout'].splitlines()] or ["    <empty>"]),
                "  stderr:",
                *([f"    {line}" for line in attempt['stderr'].splitlines()] or ["    <empty>"]),
                "",
            ]
        )

    log_path.write_text("\n".join(lines), encoding="utf-8")


def finalize_operation_result(
    *,
    operation: str,
    attempts: list[dict[str, object]],
    selected_attempt: dict[str, object] | None,
    log_path: Path,
    used_defaults: bool,
    success_message: str,
    failure_message: str,
) -> dict[str, object]:
    if selected_attempt is not None:
        return {
            **selected_attempt,
            "attempts": attempts,
            "log_file": str(log_path),
            "used_defaults": used_defaults,
            "operation": operation,
            "message": success_message,
        }

    last_attempt = attempts[-1]
    return {
        **last_attempt,
        "attempts": attempts,
        "log_file": str(log_path),
        "used_defaults": used_defaults,
        "operation": operation,
        "message": failure_message,
    }


def execute_with_retry(
    *,
    operation: str,
    log_prefix: str,
    action_arguments: Sequence[str],
    timeout_seconds: int = 30,
    success_message: str,
    failure_message: str,
    **connect_kwargs: object,
) -> dict[str, object]:
    sanitized_kwargs = {key: value for key, value in connect_kwargs.items() if value is not None}
    attempts_to_run = build_fallback_attempts(sanitized_kwargs)
    attempt_results: list[dict[str, object]] = []
    selected_attempt: dict[str, object] | None = None
    log_path = create_log_path(log_prefix)
    action_tokens = normalize_tokens(action_arguments)

    for parameters in attempts_to_run:
        command = [resolve_cli_path(), *build_connect_arguments(**parameters), *action_tokens]
        attempt_result = run_cli_command(command, timeout_seconds)
        attempt_result["connect_parameters"] = parameters
        attempt_result["action_arguments"] = action_tokens
        attempt_results.append(attempt_result)

        if attempt_result["success"]:
            selected_attempt = attempt_result
            break

    write_operation_log(
        log_path,
        operation=operation,
        attempts=attempt_results,
        selected_attempt=selected_attempt,
    )

    return finalize_operation_result(
        operation=operation,
        attempts=attempt_results,
        selected_attempt=selected_attempt,
        log_path=log_path,
        used_defaults=sanitized_kwargs == {},
        success_message=success_message,
        failure_message=failure_message,
    )


def execute_global_command(
    *,
    operation: str,
    log_prefix: str,
    command_arguments: Sequence[str],
    timeout_seconds: int = 30,
    success_message: str,
    failure_message: str,
) -> dict[str, object]:
    action_tokens = normalize_tokens(command_arguments)
    log_path = create_log_path(log_prefix)
    attempt_result = run_cli_command([resolve_cli_path(), *action_tokens], timeout_seconds)
    attempt_result["connect_parameters"] = {}
    attempt_result["action_arguments"] = action_tokens
    attempts = [attempt_result]
    selected_attempt = attempt_result if attempt_result["success"] else None

    write_operation_log(
        log_path,
        operation=operation,
        attempts=attempts,
        selected_attempt=selected_attempt,
    )

    return finalize_operation_result(
        operation=operation,
        attempts=attempts,
        selected_attempt=selected_attempt,
        log_path=log_path,
        used_defaults=False,
        success_message=success_message,
        failure_message=failure_message,
    )


def execute_connect(*, timeout_seconds: int = 30, **connect_kwargs: object) -> dict[str, object]:
    return execute_with_retry(
        operation="connect",
        log_prefix="connect",
        action_arguments=[],
        timeout_seconds=timeout_seconds,
        success_message="Connected to attached stm32 device.",
        failure_message="Unable to connect to the attached stm32 device with the default retry strategy. Ask the user for the correct connection parameters.",
        **connect_kwargs,
    )


def connected_operation_messages(operation: str) -> tuple[str, str]:
    title = operation.replace("_", " ")
    return (
        f"STM32 {title} completed successfully.",
        f"STM32 {title} failed. If the default connection settings are wrong, ask the user for the correct stm32 device connection parameters.",
    )


def execute_connected_operation(
    *,
    operation: str,
    log_prefix: str,
    action_arguments: Sequence[str],
    timeout_seconds: int = 30,
    **connect_kwargs: object,
) -> dict[str, object]:
    success_message, failure_message = connected_operation_messages(operation)
    return execute_with_retry(
        operation=operation,
        log_prefix=log_prefix,
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        success_message=success_message,
        failure_message=failure_message,
        **connect_kwargs,
    )


def apply_runtime_target_check(
    result: dict[str, object],
    *,
    firmware_path: Path,
    post_action: PostDownloadAction,
    timeout_seconds: int,
    connect_kwargs: dict[str, object],
) -> dict[str, object]:
    if post_action != "go" or not result.get("success"):
        return result

    runtime_check = execute_connected_operation(
        operation="runtime_check",
        log_prefix="runtime",
        action_arguments=["-score"],
        timeout_seconds=min(timeout_seconds, 30),
        **connect_kwargs,
    )
    result["post_action_check"] = runtime_check

    mismatch = detect_target_mismatch(firmware_path, result, runtime_check)
    if mismatch is not None:
        result["success"] = False
        result["target_mismatch"] = mismatch
        result["message"] = mismatch["reason"]
    return result


async def finalize_connect_tool_result(
    result: dict[str, object],
    ctx: Context | None,
    *,
    timeout_seconds: int,
    connect_kwargs: dict[str, object],
) -> dict[str, object]:
    def retry_operation(updated_connect_kwargs: dict[str, object]) -> dict[str, object]:
        return execute_connect(timeout_seconds=timeout_seconds, **updated_connect_kwargs)

    return await maybe_run_llm_recovery(
        result,
        ctx,
        operation="connect",
        recovery_kind="connect",
        action_arguments=[],
        connect_kwargs=connect_kwargs,
        timeout_seconds=timeout_seconds,
        retry_operation=retry_operation,
        allowed_actions=RECOVERY_CONNECT_ACTIONS,
    )


async def finalize_connected_tool_result(
    result: dict[str, object],
    ctx: Context | None,
    *,
    operation: str,
    log_prefix: str,
    action_arguments: Sequence[str],
    timeout_seconds: int,
    connect_kwargs: dict[str, object],
    post_process: Callable[[dict[str, object], dict[str, object]], dict[str, object]] | None = None,
) -> dict[str, object]:
    processed_result = post_process(result, connect_kwargs) if post_process is not None else result

    def retry_operation(updated_connect_kwargs: dict[str, object]) -> dict[str, object]:
        retried_result = execute_connected_operation(
            operation=operation,
            log_prefix=log_prefix,
            action_arguments=action_arguments,
            timeout_seconds=timeout_seconds,
            **updated_connect_kwargs,
        )
        if post_process is not None:
            retried_result = post_process(retried_result, updated_connect_kwargs)
        return retried_result

    return await maybe_run_llm_recovery(
        processed_result,
        ctx,
        operation=operation,
        recovery_kind="connected",
        action_arguments=action_arguments,
        connect_kwargs=connect_kwargs,
        timeout_seconds=timeout_seconds,
        retry_operation=retry_operation,
        allowed_actions=RECOVERY_CONNECTED_ACTIONS,
    )


@mcp.tool(description="Connect to attached stm32 device. Defaults to SWD, 4000 KHz, NORMAL mode, writes a timestamped log file, and retries common fallback options automatically.")
async def stm32_connect(
    port: str = "SWD",
    serial_number: str | None = None,
    usb_product_id: str | None = None,
    usb_vendor_id: str | None = None,
    baudrate: int | None = None,
    parity: Parity | None = None,
    data_bits: int | None = None,
    stop_bits: str | None = None,
    flow_control: FlowControl | None = None,
    rts: LevelState | None = None,
    dtr: LevelState | None = None,
    no_init_bits: int | None = None,
    enable_console: bool = False,
    frequency_khz: int | None = 4000,
    probe_index: int | None = None,
    access_port: int | None = None,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    shared_mode: bool = False,
    tcp_port: int | None = None,
    low_power_mode: LowPowerMode = "inherit",
    get_auth_id: bool = False,
    speed: SpeedMode | None = None,
    target_sel: str | None = None,
    timeout_seconds: int = 30,
    ctx: Context | None = None,
) -> dict[str, object]:
    connect_kwargs = {
        "port": port,
        "serial_number": serial_number,
        "usb_product_id": usb_product_id,
        "usb_vendor_id": usb_vendor_id,
        "baudrate": baudrate,
        "parity": parity,
        "data_bits": data_bits,
        "stop_bits": stop_bits,
        "flow_control": flow_control,
        "rts": rts,
        "dtr": dtr,
        "no_init_bits": no_init_bits,
        "enable_console": enable_console,
        "frequency_khz": frequency_khz,
        "probe_index": probe_index,
        "access_port": access_port,
        "mode": mode,
        "reset": reset,
        "shared_mode": shared_mode,
        "tcp_port": tcp_port,
        "low_power_mode": low_power_mode,
        "get_auth_id": get_auth_id,
        "speed": speed,
        "target_sel": target_sel,
    }
    result = execute_connect(
        port=port,
        serial_number=serial_number,
        usb_product_id=usb_product_id,
        usb_vendor_id=usb_vendor_id,
        baudrate=baudrate,
        parity=parity,
        data_bits=data_bits,
        stop_bits=stop_bits,
        flow_control=flow_control,
        rts=rts,
        dtr=dtr,
        no_init_bits=no_init_bits,
        enable_console=enable_console,
        frequency_khz=frequency_khz,
        probe_index=probe_index,
        access_port=access_port,
        mode=mode,
        reset=reset,
        shared_mode=shared_mode,
        tcp_port=tcp_port,
        low_power_mode=low_power_mode,
        get_auth_id=get_auth_id,
        speed=speed,
        target_sel=target_sel,
        timeout_seconds=timeout_seconds,
    )
    return await finalize_connect_tool_result(
        result,
        ctx,
        timeout_seconds=timeout_seconds,
        connect_kwargs={key: value for key, value in connect_kwargs.items() if value is not None},
    )


@mcp.tool(description="Connect to attached stm32 device using default SWD settings and automatic fallback attempts. Use this when the user says stm32 device without extra parameters.")
async def connect_to_attached_stm32_device(timeout_seconds: int = 30, ctx: Context | None = None) -> dict[str, object]:
    result = execute_connect(timeout_seconds=timeout_seconds)
    return await finalize_connect_tool_result(
        result,
        ctx,
        timeout_seconds=timeout_seconds,
        connect_kwargs=default_connect_settings(),
    )


@mcp.tool(description="Discover STM32 host-side configuration files, schema locations, and STM32CubeProgrammer CLI candidate paths for the current machine.")
def stm32_discover_host_tools() -> dict[str, object]:
    return collect_host_tool_discovery()


@mcp.tool(description="Report whether this host can actually run the currently supported STM32 workflows by probing STM32CubeProgrammer availability and version.")
def stm32_report_host_capabilities(timeout_seconds: int = 10) -> dict[str, object]:
    return collect_host_capabilities(timeout_seconds=timeout_seconds)


@mcp.tool(description="Show the STM32CubeProgrammer version and write a timestamped log file.")
def stm32_programmer_version(timeout_seconds: int = 15) -> dict[str, object]:
    return execute_global_command(
        operation="programmer_version",
        log_prefix="version",
        command_arguments=["--version"],
        timeout_seconds=timeout_seconds,
        success_message="Retrieved STM32CubeProgrammer version.",
        failure_message="Unable to retrieve STM32CubeProgrammer version.",
    )


@mcp.tool(description="List STM32 communication interfaces or connected ST-LINK probes and write a timestamped log file.")
def stm32_list_interfaces(
    interface: InterfaceName | None = None,
    shared: bool = False,
    timeout_seconds: int = 20,
) -> dict[str, object]:
    arguments = ["--list"]
    if interface is not None:
        arguments.append(interface)
    if shared:
        arguments.append("shared")
    return execute_global_command(
        operation="list_interfaces",
        log_prefix="list",
        command_arguments=arguments,
        timeout_seconds=timeout_seconds,
        success_message="Listed STM32 communication interfaces.",
        failure_message="Unable to list STM32 communication interfaces.",
    )


@mcp.tool(description="Erase STM32 flash memory. Defaults to erase all sectors after connecting to the attached stm32 device.")
async def stm32_erase(
    sectors: list[str] | None = None,
    timeout_seconds: int = 60,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_erase_arguments(sectors)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="erase",
        log_prefix="erase",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="erase",
        log_prefix="erase",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Download a firmware file to STM32 flash memory. By default it verifies after programming and writes a timestamped log file.")
async def stm32_download(
    file_path: str,
    address: str | None = None,
    incremental: bool = False,
    skip_erase: bool = False,
    verify_mode: VerifyMode = "legacy",
    post_action: PostDownloadAction = "none",
    timeout_seconds: int = 180,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    firmware_path = validate_download_inputs(file_path, address)
    action_arguments = [
        *build_download_arguments(
            str(firmware_path),
            address,
            incremental=incremental,
            skip_erase=skip_erase,
            verify_mode=verify_mode,
        ),
        *build_post_download_arguments(post_action),
    ]
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="download",
        log_prefix="download",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="download",
        log_prefix="download",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
        post_process=lambda current_result, current_connect_kwargs: apply_runtime_target_check(
            current_result,
            firmware_path=firmware_path,
            post_action=post_action,
            timeout_seconds=timeout_seconds,
            connect_kwargs=current_connect_kwargs,
        ),
    )


@mcp.tool(description="Production-style STM32 flashing flow: erase, download, verify, then optionally go or reset. Uses the default attached stm32 device connection behavior and writes a timestamped log file.")
async def stm32_flash_firmware(
    file_path: str,
    address: str | None = None,
    sectors: list[str] | None = None,
    incremental: bool = False,
    verify_mode: VerifyMode = "legacy",
    post_action: PostDownloadAction = "go",
    timeout_seconds: int = 240,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    firmware_path = validate_download_inputs(file_path, address)
    action_arguments = build_flash_arguments(
        str(firmware_path),
        address,
        sectors=sectors,
        incremental=incremental,
        verify_mode=verify_mode,
        post_action=post_action,
    )
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="flash_firmware",
        log_prefix="flash",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="flash_firmware",
        log_prefix="flash",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
        post_process=lambda current_result, current_connect_kwargs: apply_runtime_target_check(
            current_result,
            firmware_path=firmware_path,
            post_action=post_action,
            timeout_seconds=timeout_seconds,
            connect_kwargs=current_connect_kwargs,
        ),
    )


@mcp.tool(description="Run STM32 verify after connecting to the attached stm32 device.")
async def stm32_verify(
    verify_mode: VerifyMode = "legacy",
    timeout_seconds: int = 120,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_verify_arguments(verify_mode)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="verify",
        log_prefix="verify",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="verify",
        log_prefix="verify",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Read a memory checksum from the connected stm32 device.")
async def stm32_checksum(
    address: str | None = None,
    size: int | None = None,
    timeout_seconds: int = 60,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_checksum_arguments(address, size)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="checksum",
        log_prefix="checksum",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="checksum",
        log_prefix="checksum",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Read device memory and save it to a file.")
async def stm32_upload(
    address: str,
    size: int,
    file_path: str,
    timeout_seconds: int = 180,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_upload_arguments(address, size, file_path)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="upload",
        log_prefix="upload",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="upload",
        log_prefix="upload",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Read 8, 16, or 32-bit values from STM32 memory.")
async def stm32_read_memory(
    address: str,
    size: int,
    width: MemoryWidth = 32,
    timeout_seconds: int = 60,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_read_memory_arguments(width, address, size)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="read_memory",
        log_prefix="read",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="read_memory",
        log_prefix="read",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Write 8, 16, or 32-bit values into STM32 memory.")
async def stm32_write_memory(
    address: str,
    data: list[int],
    width: MemoryWidth = 32,
    verify: bool = True,
    timeout_seconds: int = 60,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_write_memory_arguments(width, address, data, verify=verify)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="write_memory",
        log_prefix="write",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="write_memory",
        log_prefix="write",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Reset the connected stm32 device in software, hardware, or bootloader mode.")
async def stm32_reset(
    reset_kind: ResetKind = "software",
    timeout_seconds: int = 30,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_reset_arguments(reset_kind)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="reset",
        log_prefix="reset",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="reset",
        log_prefix="reset",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Run code on the connected stm32 device at an optional start address.")
async def stm32_go(
    address: str | None = None,
    timeout_seconds: int = 30,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = build_go_arguments(address)
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="go",
        log_prefix="go",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="go",
        log_prefix="go",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Halt the connected stm32 core.")
async def stm32_halt(
    timeout_seconds: int = 30,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = ["-halt"]
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="halt",
        log_prefix="halt",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="halt",
        log_prefix="halt",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Run the connected stm32 core after a halt.")
async def stm32_run_core(
    timeout_seconds: int = 30,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = ["-run"]
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="run_core",
        log_prefix="run",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="run_core",
        log_prefix="run",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Step the connected stm32 core once.")
async def stm32_step_core(
    timeout_seconds: int = 30,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = ["-step"]
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="step_core",
        log_prefix="step",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="step_core",
        log_prefix="step",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Read the connected stm32 core status.")
async def stm32_core_status(
    timeout_seconds: int = 30,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    action_arguments = ["-score"]
    connect_kwargs = {
        "port": port,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "reset": reset,
    }
    result = execute_connected_operation(
        operation="core_status",
        log_prefix="score",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        **connect_kwargs,
    )
    return await finalize_connected_tool_result(
        result,
        ctx,
        operation="core_status",
        log_prefix="score",
        action_arguments=action_arguments,
        timeout_seconds=timeout_seconds,
        connect_kwargs=connect_kwargs,
    )


@mcp.tool(description="Run a custom STM32CubeProgrammer command. Use include_connect=true for device commands that need the default stm32 device connection behavior.")
async def stm32_custom_command(
    command_arguments: list[str],
    include_connect: bool = True,
    timeout_seconds: int = 120,
    port: str = "SWD",
    frequency_khz: int | None = 4000,
    mode: ConnectionMode | None = "NORMAL",
    reset: ResetMode | None = "SWrst",
    ctx: Context | None = None,
) -> dict[str, object]:
    if include_connect:
        connect_kwargs = {
            "port": port,
            "frequency_khz": frequency_khz,
            "mode": mode,
            "reset": reset,
        }
        result = execute_connected_operation(
            operation="custom_command",
            log_prefix="custom",
            action_arguments=command_arguments,
            timeout_seconds=timeout_seconds,
            **connect_kwargs,
        )
        return await finalize_connected_tool_result(
            result,
            ctx,
            operation="custom_command",
            log_prefix="custom",
            action_arguments=command_arguments,
            timeout_seconds=timeout_seconds,
            connect_kwargs=connect_kwargs,
        )

    return execute_global_command(
        operation="custom_command",
        log_prefix="custom",
        command_arguments=command_arguments,
        timeout_seconds=timeout_seconds,
        success_message="STM32 custom command completed successfully.",
        failure_message="STM32 custom command failed.",
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
