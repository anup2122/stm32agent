from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

from mcp.server.fastmcp import FastMCP

from .. import shared
from ..build import server as build_server
from ..tools import cubemx_adapter

DEFAULT_CUBEMX_ENV_VAR = cubemx_adapter.DEFAULT_CUBEMX_ENV_VAR
DEFAULT_CUBEMX_EXECUTABLE_NAME = cubemx_adapter.DEFAULT_CUBEMX_EXECUTABLE_NAME
DEFAULT_CUBEMX_CANDIDATES = cubemx_adapter.DEFAULT_CUBEMX_CANDIDATES
IOC_SIGNAL_KEY_PATTERN = re.compile(r"^(P[A-Z]\d+(?:-[A-Z0-9_]+)?)\.Signal$")
IOC_GPIO_LABEL_KEY_PATTERN = re.compile(r"^(P[A-Z]\d+(?:-[A-Z0-9_]+)?)\.GPIO_Label$")
GENERATED_INCLUDE_DIR = Path("Inc")
GENERATED_SOURCE_DIR = Path("Src")
CORE_INCLUDE_DIR = Path("Core") / "Inc"
CORE_SOURCE_DIR = Path("Core") / "Src"

mcp = FastMCP("stm32cubemx")


def load_firmware_metadata() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    firmware = project_data.get("firmware", {}) if isinstance(project_data, dict) else {}
    return firmware if isinstance(firmware, dict) else {}


def load_build_metadata() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    build = project_data.get("build", {}) if isinstance(project_data, dict) else {}
    return build if isinstance(build, dict) else {}


def load_cubemx_metadata() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    cubemx = project_data.get("cubemx", {}) if isinstance(project_data, dict) else {}
    return cubemx if isinstance(cubemx, dict) else {}


def configured_cubemx_log_path() -> Path | None:
    cubemx_metadata = load_cubemx_metadata()
    log_path = cubemx_metadata.get("log_path")
    if not isinstance(log_path, str) or not log_path.strip():
        return None
    return Path(log_path).expanduser().resolve()


def cubemx_tool_entry() -> dict[str, object]:
    return cubemx_adapter.cubemx_tool_entry(shared.load_tools_local_config)


def configured_ioc_path() -> str | None:
    firmware = load_firmware_metadata()
    ioc_path = firmware.get("ioc_path")
    if isinstance(ioc_path, str) and ioc_path.strip():
        return str((Path.cwd() / ioc_path).resolve())
    return None


def read_ioc_project_manager_value(ioc_path: Path | None, key: str) -> str | None:
    if ioc_path is None or not ioc_path.is_file():
        return None

    prefix = f"ProjectManager.{key}="
    for raw_line in ioc_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw_line.startswith(prefix):
            return raw_line.partition("=")[2].strip()
    return None


def cubeide_project_dir_candidates(project_root: Path | None, ioc_path: Path | None, project_name: str | None = None) -> list[Path]:
    if project_root is None:
        return []

    configured_project_dir = project_root / "STM32CubeIDE"
    toolchain_location = read_ioc_project_manager_value(ioc_path, "ToolChainLocation")
    if toolchain_location:
        configured_project_dir = project_root / toolchain_location / "STM32CubeIDE"

    return [configured_project_dir.resolve()]


def resolve_completion_marker(project_root: Path | None, ioc_path: Path | None, project_name: str | None = None) -> Path | None:
    candidates = cubeide_project_dir_candidates(project_root, ioc_path, project_name)
    if not candidates:
        return None

    for project_dir in candidates:
        marker_path = project_dir / ".project"
        if marker_path.is_file():
            return marker_path
    return candidates[0] / ".project"


def resolve_completion_markers(project_root: Path | None, ioc_path: Path | None, project_name: str | None = None) -> list[Path]:
    markers: list[Path] = []
    for project_dir in cubeide_project_dir_candidates(project_root, ioc_path, project_name):
        markers.append(project_dir / ".project")
        markers.append(project_dir / ".cproject")
    return markers


def discover_ioc_path(ioc_path: str | None = None) -> dict[str, object]:
    explicit_path = Path(ioc_path).resolve() if isinstance(ioc_path, str) and ioc_path.strip() else None
    configured_path = Path(configured_ioc_path()).resolve() if configured_ioc_path() else None

    if explicit_path is not None:
        return {
            "requested_path": str(explicit_path),
            "configured_path": str(configured_path) if configured_path else None,
            "resolved_path": str(explicit_path) if explicit_path.is_file() else None,
            "resolution_source": "requested" if explicit_path.is_file() else None,
            "discovered_ioc_files": [],
            "search_roots": [],
        }

    if configured_path is not None and configured_path.is_file():
        return {
            "requested_path": None,
            "configured_path": str(configured_path),
            "resolved_path": str(configured_path),
            "resolution_source": "project_config",
            "discovered_ioc_files": [],
            "search_roots": [],
        }

    return {
        "requested_path": str(explicit_path) if explicit_path else None,
        "configured_path": str(configured_path) if configured_path else None,
        "resolved_path": None,
        "resolution_source": None,
        "discovered_ioc_files": [],
        "search_roots": [],
    }


def default_ioc_path() -> str | None:
    resolved = discover_ioc_path().get("resolved_path")
    return str(resolved) if isinstance(resolved, str) else None


def normalize_project_toolchain(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    lowered = value.strip().lower()
    if lowered in {"cubeide", "stm32cubeide"}:
        return "STM32CubeIDE"
    return value.strip()


def resolve_project_path(candidate: object) -> Path | None:
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    return Path(candidate).expanduser().resolve()


def resolve_cubemx_project_inputs(
    *,
    ioc_path: str | None = None,
    project_name: str | None = None,
    project_toolchain: str | None = None,
    project_path: str | None = None,
    script_path: str | None = None,
    output_root: str | None = None,
) -> dict[str, object]:
    ioc_discovery = discover_ioc_path(ioc_path)
    resolved_ioc_path = ioc_discovery.get("resolved_path")
    resolved_ioc = Path(resolved_ioc_path).resolve() if isinstance(resolved_ioc_path, str) else None

    cubemx_metadata = load_cubemx_metadata()
    build_metadata = load_build_metadata()
    resolved_project_name = (
        project_name
        or str(cubemx_metadata.get("project_name") or "").strip()
        or str(build_metadata.get("project_name") or "").strip()
        or (resolved_ioc.stem if resolved_ioc is not None else "")
    )
    resolved_toolchain = normalize_project_toolchain(
        project_toolchain
        or cubemx_metadata.get("project_toolchain")
        or build_metadata.get("system")
    )
    resolved_project_root = (
        resolve_project_path(project_path)
        or resolve_project_path(cubemx_metadata.get("project_path"))
        or resolve_project_path(output_root)
    )
    resolved_script_path = (
        resolve_project_path(script_path)
        or resolve_project_path(cubemx_metadata.get("script_path"))
        or ((resolved_project_root / "script.txt") if resolved_project_root is not None else None)
    )
    completion_marker = resolve_completion_marker(resolved_project_root, resolved_ioc, resolved_project_name)
    completion_markers = resolve_completion_markers(resolved_project_root, resolved_ioc, resolved_project_name)

    missing_fields: list[str] = []
    if resolved_ioc is None:
        missing_fields.append("ioc_path")
    if not resolved_project_name:
        missing_fields.append("project_name")
    if resolved_toolchain is None:
        missing_fields.append("project_toolchain")
    if resolved_project_root is None:
        missing_fields.append("project_path")

    return {
        "ioc_discovery": ioc_discovery,
        "ioc_path": str(resolved_ioc) if resolved_ioc is not None else None,
        "project_name": resolved_project_name or None,
        "project_toolchain": resolved_toolchain,
        "project_path": str(resolved_project_root) if resolved_project_root is not None else None,
        "script_path": str(resolved_script_path) if resolved_script_path is not None else None,
        "completion_marker": str(completion_marker) if completion_marker is not None else None,
        "completion_markers": [str(marker) for marker in completion_markers],
        "missing_fields": missing_fields,
    }


def derive_cubemx_candidates() -> list[Path]:
    return cubemx_adapter.derive_cubemx_candidates(build_server.resolve_cubeide_path)


def derive_java_candidates() -> list[Path]:
    return cubemx_adapter.derive_java_candidates(build_server.resolve_cubeide_path, shared.host_platform_name())


def resolve_java_path() -> str | None:
    return cubemx_adapter.resolve_java_path(build_server.resolve_cubeide_path, shared.host_platform_name())


def discover_cubemx() -> dict[str, object]:
    return cubemx_adapter.discover_cubemx(
        host_platform=shared.host_platform_name(),
        load_tools_local_config=shared.load_tools_local_config,
        resolve_candidate_path=lambda candidate, config_path: shared.resolve_candidate_path(candidate, base_path=config_path),
        resolve_cubeide_path=build_server.resolve_cubeide_path,
    )


def resolve_cubemx_launcher() -> dict[str, object]:
    return cubemx_adapter.resolve_cubemx_launcher(discover_cubemx())


def parse_ioc_properties(ioc_path: Path) -> dict[str, str]:
    properties: dict[str, str] = {}
    for raw_line in ioc_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip():
            properties[key.strip()] = value.strip()
    return properties


def normalize_signal_peripheral(signal: str) -> str | None:
    normalized = signal.strip().upper()
    if not normalized or normalized in {"GPIO", "GPXTI", "EVENTOUT", "RESET_STATE", "FREE", "ANALOG", "UNUSED"}:
        return None
    token = normalized.split("_")[0]
    if token in {"SYS", "DEBUG", "RCC", "PWR", "NVIC"}:
        return token
    if re.match(r"^[A-Z]+\d+$", token):
        return token
    return None


def summarize_ioc(ioc_path: Path, properties: dict[str, str]) -> dict[str, object]:
    pin_signals: list[dict[str, str]] = []
    gpio_labels: dict[str, str] = {}
    peripherals: set[str] = set()

    for key, value in properties.items():
        signal_match = IOC_SIGNAL_KEY_PATTERN.match(key)
        if signal_match:
            pin_name = signal_match.group(1)
            pin_signals.append({"pin": pin_name, "signal": value})
            peripheral_name = normalize_signal_peripheral(value)
            if peripheral_name:
                peripherals.add(peripheral_name)
            continue

        label_match = IOC_GPIO_LABEL_KEY_PATTERN.match(key)
        if label_match and value:
            gpio_labels[label_match.group(1)] = value
            continue

        if re.match(r"^IP\d+$", key) and value:
            peripherals.add(value.upper())

    ordered_pins = sorted(pin_signals, key=lambda item: item["pin"])
    ordered_peripherals = sorted(peripherals)
    return {
        "ioc_path": str(ioc_path),
        "ioc_file": ioc_path.name,
        "file_version": properties.get("File.Version"),
        "mx_version": properties.get("MxCube.Version"),
        "mcu": {
            "name": properties.get("Mcu.Name"),
            "package": properties.get("Mcu.Package"),
            "family": properties.get("Mcu.Family"),
            "user_name": properties.get("Mcu.UserName"),
        },
        "project": {
            "name": properties.get("ProjectManager.ProjectName") or properties.get("ProjectManager.ProjectFileName"),
            "toolchain": properties.get("ProjectManager.ToolChain"),
            "target_toolchain": properties.get("ProjectManager.TargetToolchain"),
        },
        "counts": {
            "properties": len(properties),
            "pins": len(ordered_pins),
            "gpio_labels": len(gpio_labels),
            "peripherals": len(ordered_peripherals),
        },
        "peripherals": ordered_peripherals,
        "pins": ordered_pins,
        "gpio_labels": gpio_labels,
    }


def resolve_generation_root(ioc_path: Path, output_root: str | None = None, project_path: str | None = None) -> Path:
    if isinstance(project_path, str) and project_path.strip():
        return Path(project_path).expanduser().resolve()
    if isinstance(output_root, str) and output_root.strip():
        return Path(output_root).expanduser().resolve()
    configured_project_path = load_cubemx_metadata().get("project_path")
    if isinstance(configured_project_path, str) and configured_project_path.strip():
        return Path(configured_project_path).expanduser().resolve()
    raise ValueError("CubeMX project_path is required. Set cubemx.project_path in config/stm32-project.json.")


def build_cubemx_script(ioc_path: Path, project_name: str, project_toolchain: str, project_path: Path) -> str:
    return "\n".join([
        f'config load "{ioc_path}"',
        f'project name "{project_name}"',
        f'project toolchain "{project_toolchain}"',
        f'project path "{project_path}"',
        "project generate",
        "exit_mx",
        "",
    ])


def wait_for_completion_marker(
    marker_path: Path,
    *,
    timeout_seconds: int,
    initial_exists: bool,
    initial_mtime: float | None,
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
    poll_interval_seconds: float = 2.0,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    started_at = time.monotonic()
    while True:
        if marker_path.is_file():
            try:
                current_mtime = marker_path.stat().st_mtime
            except OSError:
                current_mtime = None

            if not initial_exists:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "created",
                }
            if initial_mtime is None or current_mtime is None or current_mtime > initial_mtime:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "updated",
                }

        if tree_root is not None and initial_tree_state is not None:
            current_tree_state = collect_tree_state(tree_root)
            affected_files = diff_tree_state(initial_tree_state, current_tree_state)
            if (initial_exists or marker_path.is_file()) and any(affected_files.values()):
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "tree_changed",
                    "message": "CubeMX generated files changed even though the completion marker timestamp did not.",
                    "affected_files": affected_files,
                }

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "cubemx_wait",
                    "message": "CubeMX is still running or the generated project marker has not updated yet.",
                    "marker_path": str(marker_path),
                    "marker_exists": marker_path.is_file(),
                    "elapsed_seconds": round(time.monotonic() - started_at, 1),
                    "remaining_seconds": round(remaining, 1),
                }
            )
        time.sleep(min(poll_interval_seconds, remaining))

    return {
        "success": False,
        "marker_path": str(marker_path),
        "status": "timeout",
        "message": f"CubeMX did not create or update {marker_path} within {timeout_seconds} seconds.",
    }


def wait_for_completion_markers(
    marker_paths: list[Path],
    *,
    timeout_seconds: int,
    initial_states: dict[Path, tuple[bool, float | None]],
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
    poll_interval_seconds: float = 2.0,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    unique_marker_paths: list[Path] = []
    for marker_path in marker_paths:
        resolved = marker_path.resolve()
        if resolved not in unique_marker_paths:
            unique_marker_paths.append(resolved)

    if not unique_marker_paths:
        return {
            "success": False,
            "marker_path": None,
            "status": "timeout",
            "message": "CubeMX did not have a valid completion marker path to monitor.",
        }

    deadline = time.monotonic() + timeout_seconds
    started_at = time.monotonic()
    while True:
        for marker_path in unique_marker_paths:
            initial_exists, initial_mtime = initial_states.get(marker_path, (False, None))
            if marker_path.is_file():
                try:
                    current_mtime = marker_path.stat().st_mtime
                except OSError:
                    current_mtime = None

                if not initial_exists:
                    return {
                        "success": True,
                        "marker_path": str(marker_path),
                        "checked_marker_paths": [str(path) for path in unique_marker_paths],
                        "status": "created",
                    }
                if initial_mtime is None or current_mtime is None or current_mtime > initial_mtime:
                    return {
                        "success": True,
                        "marker_path": str(marker_path),
                        "checked_marker_paths": [str(path) for path in unique_marker_paths],
                        "status": "updated",
                    }

        if tree_root is not None and initial_tree_state is not None:
            current_tree_state = collect_tree_state(tree_root)
            affected_files = diff_tree_state(initial_tree_state, current_tree_state)
            if any(affected_files.values()):
                existing_marker = next((path for path in unique_marker_paths if path.is_file()), None)
                marker_existed_before = any(initial_exists for initial_exists, _ in initial_states.values())
                if marker_existed_before or existing_marker is not None:
                    return {
                        "success": True,
                        "marker_path": str(existing_marker or unique_marker_paths[0]),
                        "checked_marker_paths": [str(path) for path in unique_marker_paths],
                        "status": "tree_changed",
                        "message": "CubeMX generated files changed even though the completion marker timestamp did not.",
                        "affected_files": affected_files,
                    }

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "cubemx_wait",
                    "message": "CubeMX is still running or the generated project marker has not updated yet.",
                    "marker_path": str(unique_marker_paths[0]),
                    "checked_marker_paths": [str(path) for path in unique_marker_paths],
                    "marker_exists": any(path.is_file() for path in unique_marker_paths),
                    "elapsed_seconds": round(time.monotonic() - started_at, 1),
                    "remaining_seconds": round(remaining, 1),
                }
            )
        time.sleep(min(poll_interval_seconds, remaining))

    return {
        "success": False,
        "marker_path": str(unique_marker_paths[0]),
        "checked_marker_paths": [str(path) for path in unique_marker_paths],
        "status": "timeout",
        "message": f"CubeMX did not create or update any expected completion marker within {timeout_seconds} seconds.",
    }


def capture_completion_marker_state(marker_paths: list[Path]) -> dict[Path, tuple[bool, float | None]]:
    state: dict[Path, tuple[bool, float | None]] = {}
    for marker_path in marker_paths:
        exists = marker_path.is_file()
        mtime: float | None = None
        if exists:
            try:
                mtime = marker_path.stat().st_mtime
            except OSError:
                mtime = None
        state[marker_path.resolve()] = (exists, mtime)
    return state


def check_completion_markers(
    marker_paths: list[Path],
    initial_states: dict[Path, tuple[bool, float | None]],
    *,
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
) -> dict[str, object] | None:
    unique_marker_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for marker_path in marker_paths:
        resolved_marker = marker_path.resolve()
        if resolved_marker not in seen_paths:
            seen_paths.add(resolved_marker)
            unique_marker_paths.append(resolved_marker)

    if not unique_marker_paths:
        return None

    for marker_path in unique_marker_paths:
        initial_exists, initial_mtime = initial_states.get(marker_path, (False, None))
        if marker_path.is_file():
            try:
                current_mtime = marker_path.stat().st_mtime
            except OSError:
                current_mtime = None

            if not initial_exists:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "checked_marker_paths": [str(path) for path in unique_marker_paths],
                    "status": "created",
                }
            if initial_mtime is None or current_mtime is None or current_mtime > initial_mtime:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "checked_marker_paths": [str(path) for path in unique_marker_paths],
                    "status": "updated",
                }

    return None


def terminate_cubemx_process(process: subprocess.Popen[str]) -> None:
    cubemx_adapter.terminate_cubemx_process(
        process,
        host_platform=shared.host_platform_name(),
        subprocess_module=subprocess,
    )


def cubemx_script_reports_success(output_text: str) -> bool:
    return cubemx_adapter.cubemx_script_reports_success(output_text)


def cubemx_failure_reason(stdout: str, stderr: str) -> str | None:
    return cubemx_adapter.cubemx_failure_reason(stdout, stderr)


def run_cubemx_command(command: list[str], timeout_seconds: int) -> dict[str, object]:
    return run_cubemx_command_with_progress(command, timeout_seconds, progress_callback=None)


def run_cubemx_command_with_progress(
    command: list[str],
    timeout_seconds: int,
    *,
    progress_callback: Callable[[dict[str, object]], None] | None,
    completion_markers: list[Path] | None = None,
    completion_tree_root: Path | None = None,
    poll_interval_seconds: float = 2.0,
) -> dict[str, object]:
    return cubemx_adapter.run_cubemx_command_with_progress(
        command,
        timeout_seconds,
        progress_callback=progress_callback,
        completion_markers=completion_markers,
        completion_tree_root=completion_tree_root,
        poll_interval_seconds=poll_interval_seconds,
        open_process=lambda invocation: subprocess.Popen(
            invocation,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ),
        terminate_process=terminate_cubemx_process,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
        configured_cubemx_log_path_resolver=configured_cubemx_log_path,
        capture_completion_marker_state_fn=capture_completion_marker_state,
        check_completion_markers_fn=check_completion_markers,
        collect_tree_state_fn=collect_tree_state,
        failure_reason_fn=cubemx_failure_reason,
    )


def run_cubemx_command(
    command: list[str],
    timeout_seconds: int,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    completion_markers: list[Path] | None = None,
    completion_tree_root: Path | None = None,
) -> dict[str, object]:
    return run_cubemx_command_with_progress(
        command,
        timeout_seconds,
        progress_callback=progress_callback,
        completion_markers=completion_markers,
        completion_tree_root=completion_tree_root,
    )


def collect_tree_state(root: Path | None) -> dict[str, float]:
    if root is None or not root.is_dir():
        return {}
    state: dict[str, float] = {}
    for file_path in root.rglob("*"):
        if file_path.is_file():
            try:
                state[str(file_path)] = file_path.stat().st_mtime
            except OSError:
                continue
    return state


def diff_tree_state(before: dict[str, float], after: dict[str, float]) -> dict[str, list[str]]:
    before_keys = set(before)
    after_keys = set(after)
    return {
        "new_files": sorted(after_keys - before_keys),
        "deleted_files": sorted(before_keys - after_keys),
        "modified_files": sorted(path for path in before_keys & after_keys if before[path] != after[path]),
    }


def regeneration_root(ioc_path: Path, output_root: str | None = None, project_path: str | None = None) -> Path | None:
    explicit_root = resolve_generation_root(ioc_path, output_root, project_path)
    if explicit_root.exists():
        return explicit_root
    build_metadata = load_build_metadata()
    project_path = build_metadata.get("project_path")
    if isinstance(project_path, str) and Path(project_path).exists():
        return Path(project_path).resolve()
    return None


def source_project_root(ioc_path: Path) -> Path:
    return ioc_path.parent.resolve()


def list_relative_directory_entries(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    entries: list[str] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        relative = path.relative_to(root).as_posix()
        entries.append(f"{relative}/" if path.is_dir() else relative)
    return entries


def parse_mxproject_paths(mxproject_path: Path) -> dict[str, object]:
    if not mxproject_path.is_file():
        return {
            "exists": False,
            "advanced_folder_structure": None,
            "header_paths": [],
            "source_paths": [],
        }

    header_paths: list[str] = []
    source_paths: list[str] = []
    advanced_folder_structure: bool | None = None
    for raw_line in mxproject_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("AdvancedFolderStructure="):
            advanced_folder_structure = stripped.partition("=")[2].strip().lower() == "true"
        elif stripped.startswith("HeaderPath#"):
            header_paths.append(stripped.partition("=")[2].strip())
        elif stripped.startswith("SourcePath#"):
            source_paths.append(stripped.partition("=")[2].strip())

    return {
        "exists": True,
        "advanced_folder_structure": advanced_folder_structure,
        "header_paths": header_paths,
        "source_paths": source_paths,
    }


def parse_cproject_include_paths(cproject_path: Path) -> list[str]:
    if not cproject_path.is_file():
        return []

    root = ET.parse(cproject_path).getroot()
    include_paths: set[str] = set()
    for option in root.findall(".//option[@valueType='includePath']"):
        for value in option.findall("listOptionValue"):
            path_value = value.get("value")
            if path_value:
                include_paths.add(path_value)
    return sorted(include_paths)


def parse_project_link_locations(project_path: Path) -> list[str]:
    if not project_path.is_file():
        return []

    root = ET.parse(project_path).getroot()
    locations: list[str] = []
    for link in root.findall(".//linkedResources/link"):
        location = link.findtext("locationURI")
        if location:
            locations.append(location)
    return sorted(locations)


def collect_output_review(ioc_path: Path, generation_root: Path) -> dict[str, object]:
    source_root = source_project_root(ioc_path)
    direct_include_dir = generation_root / GENERATED_INCLUDE_DIR
    direct_source_dir = generation_root / GENERATED_SOURCE_DIR
    core_include_dir = generation_root / CORE_INCLUDE_DIR
    core_source_dir = generation_root / CORE_SOURCE_DIR

    generated_headers = sorted(path.name for path in direct_include_dir.glob("*.h")) if direct_include_dir.is_dir() else []
    generated_sources = sorted(path.name for path in direct_source_dir.glob("*.c")) if direct_source_dir.is_dir() else []
    mxproject = parse_mxproject_paths(source_root / ".mxproject")
    cproject_include_paths = parse_cproject_include_paths(generation_root / "STM32CubeIDE" / ".cproject")
    project_link_locations = parse_project_link_locations(generation_root / "STM32CubeIDE" / ".project")

    mismatches: list[str] = []
    if source_root.resolve() != generation_root.resolve() and mxproject.get("advanced_folder_structure"):
        if direct_include_dir.is_dir() and not core_include_dir.is_dir():
            mismatches.append(
                "CubeMX generated headers in Inc/, but the reference .mxproject declares advanced header paths under Core/Inc."
            )
        if direct_source_dir.is_dir() and not core_source_dir.is_dir():
            mismatches.append(
                "CubeMX generated sources in Src/, but the reference .mxproject declares advanced source paths under Core/Src."
            )
    if any("../../Core/Inc" == include_path for include_path in cproject_include_paths) and direct_include_dir.is_dir():
        mismatches.append(
            "The external .cproject include paths still point to ../../Core/Inc while direct CubeMX output was written to Inc/."
        )
    if any("PARENT-1-PROJECT_LOC/Core/Src/" in location for location in project_link_locations) and direct_source_dir.is_dir():
        mismatches.append(
            "The external .project source links still point to Core/Src while direct CubeMX output was written to Src/."
        )

    return {
        "generation_root": str(generation_root),
        "top_level_entries": list_relative_directory_entries(generation_root),
        "direct_output": {
            "include_dir": str(direct_include_dir),
            "source_dir": str(direct_source_dir),
            "include_dir_exists": direct_include_dir.is_dir(),
            "source_dir_exists": direct_source_dir.is_dir(),
            "generated_headers": generated_headers,
            "generated_sources": generated_sources,
        },
        "core_layout_present": {
            "include_dir": str(core_include_dir),
            "source_dir": str(core_source_dir),
            "include_dir_exists": core_include_dir.is_dir(),
            "source_dir_exists": core_source_dir.is_dir(),
        },
        "source_project_expectations": {
            "source_root": str(source_root),
            "mxproject": mxproject,
        },
        "external_build_expectations": {
            "cproject_include_paths": cproject_include_paths,
            "project_link_locations": project_link_locations,
        },
        "mismatches": mismatches,
        "message": "Direct CubeMX output was preserved without structural alignment. Review the reported mismatches before rewiring the external build metadata.",
    }


def collect_build_layout_summary(generation_root: Path) -> dict[str, object]:
    build_metadata = load_build_metadata()
    return {
        "generation_root": str(generation_root),
        "structure": {
            "generated_include_dir": str(generation_root / GENERATED_INCLUDE_DIR),
            "generated_source_dir": str(generation_root / GENERATED_SOURCE_DIR),
            "core_include_dir": str(generation_root / CORE_INCLUDE_DIR),
            "core_source_dir": str(generation_root / CORE_SOURCE_DIR),
            "cubeide_project_dir": str(generation_root / "STM32CubeIDE"),
        },
        "build": {
            "workspace": build_metadata.get("workspace"),
            "project_path": build_metadata.get("project_path"),
            "project_name": build_metadata.get("project_name"),
            "artifact": build_metadata.get("artifact"),
            "default_configuration": build_metadata.get("default_configuration"),
        },
    }


def write_cubemx_log(
    log_path: Path,
    *,
    ioc_path: Path,
    launcher: dict[str, object],
    command: list[str],
    script_path: Path,
    script_contents: str,
    regeneration_result: dict[str, object],
    completion_wait: dict[str, object] | None,
    affected_files: dict[str, list[str]],
    output_review: dict[str, object] | None,
    build_validation: dict[str, object] | None,
) -> None:
    sections = [
        f"ioc_path={ioc_path}",
        f"tool_path={launcher.get('tool_path')}",
        f"launch_kind={launcher.get('launch_kind')}",
        f"command={' '.join(str(token) for token in command)}",
        f"script_path={script_path}",
        "",
        "script:",
        *[f"  {line}" for line in script_contents.splitlines()],
        "",
        "regeneration:",
        f"  success={regeneration_result['success']}",
        f"  exit_code={regeneration_result['exit_code']}",
        "  stdout:",
        *([f"    {line}" for line in str(regeneration_result['stdout']).splitlines()] or ["    <empty>"]),
        "  stderr:",
        *([f"    {line}" for line in str(regeneration_result['stderr']).splitlines()] or ["    <empty>"]),
    ]
    if completion_wait is not None:
        sections.extend([
            "",
            "completion_wait:",
            f"  success={completion_wait.get('success')}",
            f"  marker_path={completion_wait.get('marker_path')}",
            f"  status={completion_wait.get('status')}",
            f"  message={completion_wait.get('message')}",
        ])
    sections.extend([
        "",
        "affected_files:",
        f"  new_files={len(affected_files['new_files'])}",
        f"  deleted_files={len(affected_files['deleted_files'])}",
        f"  modified_files={len(affected_files['modified_files'])}",
    ])
    if output_review is not None:
        sections.extend([
            "",
            "output_review:",
            f"  message={output_review.get('message')}",
            f"  top_level_entries={len(output_review.get('top_level_entries', []))}",
            f"  mismatches={len(output_review.get('mismatches', []))}",
        ])
    if build_validation is not None:
        sections.extend([
            "",
            "build_validation:",
            f"  success={build_validation.get('success')}",
            f"  message={build_validation.get('message')}",
        ])
    log_path.write_text("\n".join(sections), encoding="utf-8")


@mcp.tool(description="Report CubeMX Part 1 host readiness, IOC discovery state, and whether deterministic IOC inspection/regeneration backends are available.")
def stm32_cubemx_capabilities() -> dict[str, object]:
    cubemx_discovery = discover_cubemx()
    ioc_discovery = discover_ioc_path()
    return {
        "server": "cubemx",
        "implemented": True,
        "capabilities": {
            "ioc_parse": True,
            "ioc_search": True,
            "project_regeneration": True,
            "build_validation": True,
        },
        "tool_discovery": cubemx_discovery,
        "ioc_discovery": ioc_discovery,
        "default_ioc_path": ioc_discovery.get("resolved_path"),
        "project_config": shared.summarize_config_status(shared.load_project_metadata()),
        "tools_config": shared.summarize_config_status(shared.load_tools_local_config()),
    }


@mcp.tool(description="Inspect an existing CubeMX IOC file by loading its properties-style metadata, peripheral list, pins, and project/toolchain summary.")
def stm32_cubemx_parse_ioc(ioc_path: str | None = None) -> dict[str, object]:
    ioc_discovery = discover_ioc_path(ioc_path)
    resolved_path = ioc_discovery.get("resolved_path")
    if not isinstance(resolved_path, str):
        return {
            "success": False,
            "implemented": True,
            "server": "cubemx",
            "operation": "parse_ioc",
            "ioc_path": ioc_path,
            "ioc_exists": False,
            "ioc_discovery": ioc_discovery,
            "message": "No IOC file could be resolved. Set firmware.ioc_path in config/stm32-project.json.",
        }

    resolved_ioc = Path(resolved_path)
    properties = parse_ioc_properties(resolved_ioc)
    summary = summarize_ioc(resolved_ioc, properties)
    return {
        "success": True,
        "implemented": True,
        "server": "cubemx",
        "operation": "parse_ioc",
        "ioc_path": str(resolved_ioc),
        "ioc_exists": True,
        "ioc_discovery": ioc_discovery,
        "summary": summary,
        "message": f"Parsed IOC metadata from {resolved_ioc.name}.",
    }


def regenerate_project_internal(
    ioc_path: str | None = None,
    project_name: str | None = None,
    project_toolchain: str | None = None,
    project_path: str | None = None,
    script_path: str | None = None,
    output_root: str | None = None,
    validate_build: bool = True,
    timeout_seconds: int = 900,
    build_timeout_seconds: int = 600,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    project_inputs = resolve_cubemx_project_inputs(
        ioc_path=ioc_path,
        project_name=project_name,
        project_toolchain=project_toolchain,
        project_path=project_path,
        script_path=script_path,
        output_root=output_root,
    )
    ioc_discovery = project_inputs["ioc_discovery"]
    resolved_path = project_inputs.get("ioc_path")
    missing_fields = list(project_inputs.get("missing_fields", [])) if isinstance(project_inputs.get("missing_fields"), list) else []
    if not isinstance(resolved_path, str) or missing_fields:
        return {
            "success": False,
            "implemented": True,
            "server": "cubemx",
            "operation": "regenerate_project",
            "ioc_path": ioc_path,
            "ioc_discovery": ioc_discovery,
            "project_inputs": project_inputs,
            "message": (
                "Missing required CubeMX project metadata: " + ", ".join(missing_fields)
                if missing_fields
                else "No IOC file could be resolved for regeneration."
            ),
        }

    try:
        launcher = resolve_cubemx_launcher()
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "cubemx",
            "operation": "regenerate_project",
            "ioc_path": resolved_path,
            "ioc_discovery": ioc_discovery,
            "message": str(exc),
        }

    resolved_ioc = Path(resolved_path)
    resolved_project_name = str(project_inputs["project_name"])
    resolved_project_toolchain = str(project_inputs["project_toolchain"])
    resolved_project_path = str(project_inputs["project_path"])
    resolved_script_path = str(project_inputs["script_path"])
    completion_marker_path = Path(str(project_inputs["completion_marker"]))
    completion_marker_paths = [
        Path(str(marker_path))
        for marker_path in project_inputs.get("completion_markers", [])
        if isinstance(marker_path, str) and marker_path.strip()
    ]
    if not completion_marker_paths:
        completion_marker_paths = [completion_marker_path]
    generation_root = resolve_generation_root(resolved_ioc, output_root, resolved_project_path)
    generation_root.mkdir(parents=True, exist_ok=True)
    script_contents = build_cubemx_script(
        resolved_ioc,
        resolved_project_name,
        resolved_project_toolchain,
        generation_root,
    )
    tree_root = regeneration_root(resolved_ioc, output_root, resolved_project_path)
    before_state = collect_tree_state(tree_root)
    persisted_script_path = Path(resolved_script_path)
    persisted_script_path.parent.mkdir(parents=True, exist_ok=True)
    marker_states_before = {
        marker_path.resolve(): (
            marker_path.is_file(),
            marker_path.stat().st_mtime if marker_path.is_file() else None,
        )
        for marker_path in completion_marker_paths
    }
    marker_exists_before = any(exists for exists, _ in marker_states_before.values())
    command = [*list(launcher["command_prefix"]), "-q", str(persisted_script_path)]
    completion_wait: dict[str, object] | None = None
    after_state: dict[str, float] | None = None
    affected_files: dict[str, list[str]] | None = None
    started_at = time.monotonic()
    try:
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "cubemx_launch",
                    "message": "Writing the CubeMX script and launching CubeMX.",
                    "script_path": str(persisted_script_path),
                    "marker_path": str(completion_marker_path),
                }
            )
        persisted_script_path.write_text(script_contents, encoding="utf-8")
        regeneration_result = run_cubemx_command(
            command,
            timeout_seconds,
            progress_callback=progress_callback,
            completion_markers=completion_marker_paths,
            completion_tree_root=tree_root,
        )
        remaining_timeout = max(1, timeout_seconds - int(time.monotonic() - started_at))
        if regeneration_result.get("success"):
            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "cubemx_wait",
                        "message": "CubeMX returned successfully; waiting for the generated project marker.",
                        "marker_path": str(completion_marker_path),
                        "remaining_seconds": remaining_timeout,
                    }
                )
            completion_wait = wait_for_completion_markers(
                completion_marker_paths,
                timeout_seconds=remaining_timeout,
                initial_states=marker_states_before,
                tree_root=tree_root,
                initial_tree_state=before_state,
                progress_callback=progress_callback,
            )
            if not completion_wait.get("success"):
                after_state = collect_tree_state(tree_root)
                affected_files = diff_tree_state(before_state, after_state)
                tree_changed = any(affected_files.values())
                if tree_changed and (marker_exists_before or any(marker_path.is_file() for marker_path in completion_marker_paths)):
                    completion_wait = {
                        "success": True,
                        "marker_path": str(completion_marker_path),
                        "checked_marker_paths": [str(path) for path in completion_marker_paths],
                        "status": "tree_changed",
                        "message": "CubeMX returned successfully and generated files changed even though the completion marker timestamp did not.",
                        "affected_files": affected_files,
                    }
                else:
                    regeneration_result = {
                        **regeneration_result,
                        "success": False,
                        "failure_reason": completion_wait.get("message"),
                    }
    except OSError as exc:
        regeneration_result = {
            "success": False,
            "exit_code": -3,
            "command": command,
            "stdout": "",
            "stderr": str(exc),
            "failure_reason": f"CubeMX script file could not be created: {exc}",
        }

    if progress_callback is not None:
        progress_callback(
            {
                "stage": "cubemx_complete",
                "message": "CubeMX regeneration stage finished.",
                "success": bool(regeneration_result.get("success")),
            }
        )

    if after_state is None:
        after_state = collect_tree_state(tree_root)
    if affected_files is None:
        affected_files = diff_tree_state(before_state, after_state)
    output_review: dict[str, object] | None = None
    if regeneration_result.get("success"):
        output_review = collect_output_review(resolved_ioc, generation_root)
    build_validation: dict[str, object] | None = None
    if regeneration_result.get("success") and validate_build:
        build_validation = build_server.stm32_build_project(timeout_seconds=build_timeout_seconds)

    log_path = shared.create_log_path("cubemx_regenerate")
    write_cubemx_log(
        log_path,
        ioc_path=resolved_ioc,
        launcher=launcher,
        command=command,
        script_path=persisted_script_path,
        script_contents=script_contents,
        regeneration_result=regeneration_result,
        completion_wait=completion_wait,
        affected_files=affected_files,
        output_review=output_review,
        build_validation=build_validation,
    )
    return {
        "success": bool(regeneration_result.get("success")),
        "implemented": True,
        "server": "cubemx",
        "operation": "regenerate_project",
        "ioc_path": str(resolved_ioc),
        "output_root": str(generation_root),
        "project_name": resolved_project_name,
        "project_toolchain": resolved_project_toolchain,
        "project_path": resolved_project_path,
        "script_path": str(persisted_script_path),
        "completion_wait": completion_wait,
        "project_inputs": project_inputs,
        "ioc_discovery": ioc_discovery,
        "tool_path": launcher.get("tool_path"),
        "launch_kind": launcher.get("launch_kind"),
        "regeneration_result": regeneration_result,
        "output_review": output_review,
        "build_layout": collect_build_layout_summary(generation_root),
        "build_validation": build_validation,
        "affected_files": affected_files,
        "log_file": str(log_path),
        "message": (
            f"CubeMX regeneration succeeded for {resolved_ioc.name}."
            if regeneration_result.get("success")
            else str(regeneration_result.get("failure_reason") or f"CubeMX regeneration failed for {resolved_ioc.name}. Inspect the CubeMX log for details.")
        ),
    }


@mcp.tool(description="Run deterministic CubeMX regeneration for an existing IOC file, record affected files, and optionally validate the regenerated project with the existing Build MCP.")
def stm32_cubemx_regenerate_project(
    ioc_path: str | None = None,
    project_name: str | None = None,
    project_toolchain: str | None = None,
    project_path: str | None = None,
    script_path: str | None = None,
    output_root: str | None = None,
    validate_build: bool = True,
    timeout_seconds: int = 900,
    build_timeout_seconds: int = 600,
) -> dict[str, object]:
    return regenerate_project_internal(
        ioc_path=ioc_path,
        project_name=project_name,
        project_toolchain=project_toolchain,
        project_path=project_path,
        script_path=script_path,
        output_root=output_root,
        validate_build=validate_build,
        timeout_seconds=timeout_seconds,
        build_timeout_seconds=build_timeout_seconds,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
