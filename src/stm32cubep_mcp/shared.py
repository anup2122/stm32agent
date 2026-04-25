from __future__ import annotations

import json
import os
import platform
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

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
PROJECT_METADATA_ENV_VAR = "STM32_PROJECT_JSON"
DEFAULT_GENERATED_ROOT = "generated"
DEFAULT_PROJECT_TOOLCHAIN = "STM32CubeIDE"
DEFAULT_BUILD_SYSTEM = "cubeide"
DEFAULT_BUILD_CONFIGURATION = "Debug"
LOCAL_TOOLS_CONFIG_PATHS = (
    "config/stm32-tools.local.json",
    "stm32-tools.local.json",
    ".vscode/stm32-tools.local.json",
    ".github/stm32-tools.local.json",
)
PROJECT_METADATA_PATHS = (
    "config/stm32-project.json",
    "stm32-project.json",
    ".vscode/stm32-project.json",
    ".github/stm32-project.json",
)
TOOLS_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "stm32-tools.local.schema.json"
PROJECT_SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "stm32-project.schema.json"
DEFAULT_LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"


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


def validate_project_metadata_schema(payload: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Document must be a JSON object."]

    version = payload.get("version")
    if not isinstance(version, int):
        errors.append("version must be an integer.")

    project_name = payload.get("project_name")
    if project_name is not None and not isinstance(project_name, str):
        errors.append("project_name must be a string when provided.")

    for field_name in ("_comment", "generated_root", "project_toolchain", "build_system", "default_configuration"):
        value = payload.get(field_name)
        if value is not None and not isinstance(value, str):
            errors.append(f"{field_name} must be a string when provided.")

    board = payload.get("board")
    if board is not None and not isinstance(board, dict):
        errors.append("board must be an object when provided.")
    elif isinstance(board, dict):
        comment = board.get("_comment")
        if comment is not None and not isinstance(comment, str):
            errors.append("board._comment must be a string when provided.")
        for field_name in ("name", "mcu", "interface"):
            if field_name in board and not isinstance(board[field_name], str):
                errors.append(f"board.{field_name} must be a string when provided.")

    for section_name in ("firmware", "build", "debug"):
        section = payload.get(section_name)
        if section is not None and not isinstance(section, dict):
            errors.append(f"{section_name} must be an object when provided.")
        elif isinstance(section, dict):
            comment = section.get("_comment")
            if comment is not None and not isinstance(comment, str):
                errors.append(f"{section_name}._comment must be a string when provided.")

    cubemx = payload.get("cubemx")
    if cubemx is not None and not isinstance(cubemx, dict):
        errors.append("cubemx must be an object when provided.")
    elif isinstance(cubemx, dict):
        comment = cubemx.get("_comment")
        if comment is not None and not isinstance(comment, str):
            errors.append("cubemx._comment must be a string when provided.")

    connect_defaults = board.get("connect_defaults") if isinstance(board, dict) else None
    if connect_defaults is not None and not isinstance(connect_defaults, dict):
        errors.append("board.connect_defaults must be an object when provided.")

    return errors


def cloned_json_object(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    return json.loads(json.dumps(payload))


def strip_jsonc_comments(document_text: str) -> str:
    result: list[str] = []
    in_string = False
    string_delimiter = '"'
    in_line_comment = False
    in_block_comment = False
    escaping = False
    index = 0

    while index < len(document_text):
        char = document_text[index]
        next_char = document_text[index + 1] if index + 1 < len(document_text) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
                result.append(char)
            else:
                result.append(" ")
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                result.extend((" ", " "))
                in_block_comment = False
                index += 2
                continue
            result.append(char if char in "\r\n" else " ")
            index += 1
            continue

        if in_string:
            result.append(char)
            if escaping:
                escaping = False
            elif char == "\\":
                escaping = True
            elif char == string_delimiter:
                in_string = False
            index += 1
            continue

        if char in {'"', "'"}:
            in_string = True
            string_delimiter = char
            result.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            result.extend((" ", " "))
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            result.extend((" ", " "))
            in_block_comment = True
            index += 2
            continue

        result.append(char)
        index += 1

    return "".join(result)


def parse_jsonc_document(document_text: str) -> object:
    return json.loads(strip_jsonc_comments(document_text))


def normalize_project_toolchain(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_PROJECT_TOOLCHAIN
    lowered = value.strip().lower()
    if lowered in {"cubeide", "stm32cubeide"}:
        return DEFAULT_PROJECT_TOOLCHAIN
    return value.strip()


def normalize_build_system(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_BUILD_SYSTEM
    return value.strip().lower()


def compact_project_metadata(payload: object) -> dict[str, object]:
    raw = cloned_json_object(payload)
    derived = derive_project_metadata(raw)

    normalized: dict[str, object] = {
        "version": int(raw.get("version") or 1),
        "project_name": str(derived.get("project_name") or "").strip(),
        "generated_root": str(derived.get("generated_root") or DEFAULT_GENERATED_ROOT),
        "project_toolchain": str(derived.get("project_toolchain") or DEFAULT_PROJECT_TOOLCHAIN),
        "build_system": str(derived.get("build_system") or DEFAULT_BUILD_SYSTEM),
        "default_configuration": str(derived.get("default_configuration") or DEFAULT_BUILD_CONFIGURATION),
    }

    board = cloned_json_object(raw.get("board")) if isinstance(raw.get("board"), dict) else {}
    firmware = cloned_json_object(raw.get("firmware")) if isinstance(raw.get("firmware"), dict) else {}
    cubemx = cloned_json_object(raw.get("cubemx")) if isinstance(raw.get("cubemx"), dict) else {}
    build = cloned_json_object(raw.get("build")) if isinstance(raw.get("build"), dict) else {}
    debug = cloned_json_object(raw.get("debug")) if isinstance(raw.get("debug"), dict) else {}

    derived_firmware = derived.get("firmware") if isinstance(derived.get("firmware"), dict) else {}
    derived_cubemx = derived.get("cubemx") if isinstance(derived.get("cubemx"), dict) else {}
    derived_build = derived.get("build") if isinstance(derived.get("build"), dict) else {}
    derived_debug = derived.get("debug") if isinstance(derived.get("debug"), dict) else {}

    if firmware.get("ioc_path") == derived_firmware.get("ioc_path"):
        firmware.pop("ioc_path", None)
    if firmware.get("default_artifact") == derived_firmware.get("default_artifact"):
        firmware.pop("default_artifact", None)

    if cubemx.get("project_name") == derived_cubemx.get("project_name"):
        cubemx.pop("project_name", None)
    if cubemx.get("project_toolchain") == derived_cubemx.get("project_toolchain"):
        cubemx.pop("project_toolchain", None)
    if cubemx.get("project_path") == derived_cubemx.get("project_path"):
        cubemx.pop("project_path", None)
    if cubemx.get("script_path") == derived_cubemx.get("script_path"):
        cubemx.pop("script_path", None)

    if build.get("system") == derived_build.get("system"):
        build.pop("system", None)
    if build.get("workspace") == derived_build.get("workspace"):
        build.pop("workspace", None)
    if build.get("project_path") == derived_build.get("project_path"):
        build.pop("project_path", None)
    if build.get("project_name") == derived_build.get("project_name"):
        build.pop("project_name", None)
    if build.get("default_configuration") == derived_build.get("default_configuration"):
        build.pop("default_configuration", None)
    if build.get("configurations") == derived_build.get("configurations"):
        build.pop("configurations", None)
    if build.get("artifact") == derived_build.get("artifact"):
        build.pop("artifact", None)

    if debug.get("elf_path") == derived_debug.get("elf_path"):
        debug.pop("elf_path", None)

    normalized["board"] = board
    normalized["firmware"] = firmware
    normalized["cubemx"] = cubemx
    normalized["build"] = build
    normalized["debug"] = debug

    for key, value in raw.items():
        if key not in normalized and key not in {"board", "firmware", "cubemx", "build", "debug"}:
            normalized[key] = value

    return normalized


def _ordered_mapping_items(mapping: dict[str, object], preferred_order: Sequence[str]) -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = []
    seen: set[str] = set()
    for key in preferred_order:
        if key in mapping:
            items.append((key, mapping[key]))
            seen.add(key)
    for key, value in mapping.items():
        if key not in seen:
            items.append((key, value))
    return items


def _render_jsonc_value(value: object, indent_level: int = 0, preferred_order: Sequence[str] = ()) -> list[str]:
    indent = "  " * indent_level
    child_indent = "  " * (indent_level + 1)

    if isinstance(value, dict):
        if not value:
            return ["{}"]
        lines = ["{"]
        items = _ordered_mapping_items(value, preferred_order)
        for index, (key, nested_value) in enumerate(items):
            nested_lines = _render_jsonc_value(nested_value, indent_level + 1)
            suffix = "," if index < len(items) - 1 else ""
            if len(nested_lines) == 1:
                lines.append(f"{child_indent}{json.dumps(key)}: {nested_lines[0]}{suffix}")
            else:
                lines.append(f"{child_indent}{json.dumps(key)}: {nested_lines[0]}")
                lines.extend(nested_lines[1:-1])
                lines.append(f"{nested_lines[-1]}{suffix}")
        lines.append(f"{indent}}}")
        return lines

    if isinstance(value, list):
        if not value:
            return ["[]"]
        lines = ["["]
        for index, item in enumerate(value):
            nested_lines = _render_jsonc_value(item, indent_level + 1)
            suffix = "," if index < len(value) - 1 else ""
            if len(nested_lines) == 1:
                lines.append(f"{child_indent}{nested_lines[0]}{suffix}")
            else:
                lines.append(f"{child_indent}{nested_lines[0]}")
                lines.extend(nested_lines[1:-1])
                lines.append(f"{nested_lines[-1]}{suffix}")
        lines.append(f"{indent}]")
        return lines

    return [json.dumps(value)]


def render_project_metadata_jsonc(payload: object) -> str:
    compacted = compact_project_metadata(payload)
    lines = ["{"]

    top_level_comments = {
        "project_name": "Actual STM32 project name. Keep this single source of truth.",
        "generated_root": "Generated project root folder relative to the workspace.",
        "project_toolchain": "Default CubeMX toolchain when no section override is needed.",
        "build_system": "Default build backend used by the build server.",
        "default_configuration": "Default build configuration used for ELF and build output paths.",
        "board": "Board identity and connection defaults supplied by the user.",
        "firmware": "Optional firmware overrides. Derived IOC and ELF paths are omitted unless you want to override them.",
        "cubemx": "Optional CubeMX overrides. Derived project_name, project_path, and script_path are omitted unless overridden.",
        "build": "Optional build overrides. Derived workspace, project_path, project_name, artifact, and configurations are omitted unless overridden.",
        "debug": "Optional debug overrides. Derived elf_path is omitted unless overridden.",
    }
    top_level_order = (
        "version",
        "project_name",
        "generated_root",
        "project_toolchain",
        "build_system",
        "default_configuration",
        "board",
        "firmware",
        "cubemx",
        "build",
        "debug",
    )
    section_orders = {
        "board": ("name", "mcu", "interface", "connect_defaults"),
        "firmware": ("format", "flash_address", "ioc_path", "default_artifact"),
        "cubemx": ("log_path", "project_name", "project_toolchain", "project_path", "script_path"),
        "build": (
            "import_project",
            "default_clean",
            "command",
            "cwd",
            "system",
            "workspace",
            "project_path",
            "project_name",
            "default_configuration",
            "configurations",
            "artifact",
        ),
        "debug": ("server", "gdb", "gdb_port", "swo_port", "elf_path"),
    }

    items = _ordered_mapping_items(compacted, top_level_order)
    for index, (key, value) in enumerate(items):
        comment = top_level_comments.get(key)
        if comment:
            lines.append(f"  // {comment}")
        preferred_order = section_orders.get(key, ()) if isinstance(value, dict) else ()
        rendered = _render_jsonc_value(value, 1, preferred_order)
        suffix = "," if index < len(items) - 1 else ""
        if len(rendered) == 1:
            lines.append(f"  {json.dumps(key)}: {rendered[0]}{suffix}")
        else:
            lines.append(f"  {json.dumps(key)}: {rendered[0]}")
            lines.extend(rendered[1:-1])
            lines.append(f"{rendered[-1]}{suffix}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def derive_project_metadata(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}

    derived = cloned_json_object(payload)
    firmware = derived.get("firmware") if isinstance(derived.get("firmware"), dict) else {}
    cubemx = derived.get("cubemx") if isinstance(derived.get("cubemx"), dict) else {}
    build = derived.get("build") if isinstance(derived.get("build"), dict) else {}
    debug = derived.get("debug") if isinstance(derived.get("debug"), dict) else {}

    project_name = str(
        derived.get("project_name")
        or cubemx.get("project_name")
        or build.get("project_name")
        or ""
    ).strip()
    generated_root = str(derived.get("generated_root") or DEFAULT_GENERATED_ROOT).strip() or DEFAULT_GENERATED_ROOT
    project_toolchain = normalize_project_toolchain(derived.get("project_toolchain") or cubemx.get("project_toolchain"))
    build_system = normalize_build_system(derived.get("build_system") or build.get("system"))
    default_configuration = str(derived.get("default_configuration") or build.get("default_configuration") or DEFAULT_BUILD_CONFIGURATION).strip() or DEFAULT_BUILD_CONFIGURATION

    derived["project_name"] = project_name or derived.get("project_name")
    derived["generated_root"] = generated_root
    derived["project_toolchain"] = project_toolchain
    derived["build_system"] = build_system
    derived["default_configuration"] = default_configuration

    if project_name:
        generated_root_path = Path(generated_root)
        project_root = (Path.cwd() / generated_root_path / project_name).resolve()
        cubeide_root = (project_root / "Projects" / "STM32CubeIDE").resolve()
        artifact_path = (cubeide_root / default_configuration / f"{project_name}.elf").resolve()

        firmware.setdefault("ioc_path", str((generated_root_path / project_name / f"{project_name}.ioc").as_posix()))
        firmware.setdefault("default_artifact", str(artifact_path))

        cubemx.setdefault("project_name", project_name)
        cubemx.setdefault("project_toolchain", project_toolchain)
        cubemx.setdefault("project_path", str(project_root))
        cubemx.setdefault("script_path", str((project_root / "script.txt").resolve()))

        build.setdefault("system", build_system)
        build.setdefault("workspace", str((Path.cwd() / generated_root_path / ".cubeide-workspace").resolve()))
        build.setdefault("project_path", str(cubeide_root))
        build.setdefault("project_name", project_name)
        build.setdefault("default_configuration", default_configuration)
        build.setdefault("configurations", [default_configuration])
        build.setdefault("artifact", str(artifact_path))

        debug.setdefault("elf_path", str(artifact_path))

    derived["firmware"] = firmware
    derived["cubemx"] = cubemx
    derived["build"] = build
    derived["debug"] = debug
    return derived


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
            payload = parse_jsonc_document(candidate_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "status": "invalid",
                "path": str(candidate_path),
                "searched_paths": [str(path) for path in searched_paths],
                "schema_path": str(schema_path),
                "errors": [f"Invalid JSON or JSONC: {exc.msg} at line {exc.lineno}, column {exc.colno}."],
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


def load_project_metadata() -> dict[str, object]:
    result = load_optional_json_config(
        env_var=PROJECT_METADATA_ENV_VAR,
        relative_paths=PROJECT_METADATA_PATHS,
        schema_path=PROJECT_SCHEMA_PATH,
        validator=validate_project_metadata_schema,
    )
    raw_data = result.get("data")
    if not isinstance(raw_data, dict):
        return result
    return {
        **result,
        "raw_data": cloned_json_object(raw_data),
        "data": derive_project_metadata(raw_data),
    }


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


def summarize_config_status(config_result: dict[str, object]) -> dict[str, object]:
    return {
        "status": config_result.get("status"),
        "path": config_result.get("path"),
        "schema_path": config_result.get("schema_path"),
        "errors": list(config_result.get("errors", [])),
        "searched_paths": list(config_result.get("searched_paths", [])),
    }


def log_directory() -> Path:
    logs_dir = Path(os.environ.get("STM32CUBEP_MCP_LOG_DIR", DEFAULT_LOGS_DIR))
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def create_log_path(prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_directory() / f"{prefix}_{timestamp}.log"