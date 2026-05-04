"""STM32 debug MCP server.

This module owns runtime inspection and managed debug-session control. It sits
beside the programmer server: the programmer server handles CLI connect/flash
operations, while this server manages ST-LINK GDB server processes, ARM GDB
batch commands, SVD-backed register decoding, and structured runtime snapshots.

Exact managed launch chain:

`stm32_debug_launch(...)`
-> `resolve_stlink_gdb_server_path()`
-> `resolve_swo_launch_port(...)` and `select_launch_ports(...)`
-> `build_stlink_gdb_server_command(...)`
-> `subprocess.Popen(...)`
-> wait until `is_tcp_port_open(...)` reports readiness
-> store `DebugSession` in `ACTIVE_DEBUG_SESSIONS`
-> return session summary plus log paths

Exact one-shot GDB inspection chain:

`stm32_debug_run_gdb_commands(...)` or `stm32_debug_snapshot(...)`
-> resolve active `DebugSession`
-> `run_gdb_batch(...)`
-> `build_gdb_batch_command(...)`
-> `run_debug_command(...)`
-> optional parsing such as `parse_register_output(...)` or
    `parse_section_lines(...)`
-> structured MCP result payload

Exact peripheral-inspection chain:

`stm32_debug_inspect_peripheral(...)`
-> `inspect_peripheral_registers_from_svd(...)`
-> `resolve_svd_path()`
-> `parse_svd_device(...)`
-> `run_gdb_batch(...)` to read live register values
-> SVD-aware decoding into peripheral/register fields
-> structured inspection result

The architectural boundary here is deliberate: this module does not decide
whether a project should be built, flashed, or regenerated. It assumes a target
is already prepared and focuses on live runtime observability.
"""

from __future__ import annotations

import atexit
from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import TextIO
import xml.etree.ElementTree as ET

from mcp.server.fastmcp import FastMCP

from .. import shared
from ..build import server as build_server
from ..tools import arm_gdb_adapter, stlink_gdb_adapter

mcp = FastMCP("stm32debug")

DEFAULT_STLINK_GDB_SERVER_ENV_VAR = stlink_gdb_adapter.DEFAULT_STLINK_GDB_SERVER_ENV_VAR
DEFAULT_ARM_GDB_ENV_VAR = arm_gdb_adapter.DEFAULT_ARM_GDB_ENV_VAR
DEFAULT_SVD_PATH_ENV_VAR = "STM32_SVD_PATH"
DEFAULT_STLINK_GDB_SERVER_CANDIDATES = stlink_gdb_adapter.DEFAULT_STLINK_GDB_SERVER_CANDIDATES
DEFAULT_ARM_GDB_CANDIDATES = arm_gdb_adapter.DEFAULT_ARM_GDB_CANDIDATES
ACTIVE_DEBUG_SESSIONS: dict[str, "DebugSession"] = {}
SVD_CACHE: dict[str, dict[str, object]] = {}
STM32L4_RCC_BASE = 0x40021000
STM32L4_RCC_CR = STM32L4_RCC_BASE + 0x00
STM32L4_RCC_CFGR = STM32L4_RCC_BASE + 0x08
STM32L4_RCC_PLLCFGR = STM32L4_RCC_BASE + 0x0C
STM32L4_RCC_CCIPR = STM32L4_RCC_BASE + 0x88
STM32L4_USART_BASES = {
    "USART1": 0x40013800,
    "USART2": 0x40004400,
    "USART3": 0x40004800,
    "UART4": 0x40004C00,
    "UART5": 0x40005000,
}
MSI_RANGE_FREQUENCIES_HZ = {
    0: 100_000,
    1: 200_000,
    2: 400_000,
    3: 800_000,
    4: 1_000_000,
    5: 2_000_000,
    6: 4_000_000,
    7: 8_000_000,
    8: 16_000_000,
    9: 24_000_000,
    10: 32_000_000,
    11: 48_000_000,
}


@dataclass
class DebugSession:
    session_name: str
    process: subprocess.Popen[str]
    command: list[str]
    console_log_path: Path
    server_log_path: Path
    port_number: int
    swo_port: int | None
    serial_number: str | None
    started_at: str
    output_handle: TextIO


def load_debug_metadata() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    debug_section = project_data.get("debug", {}) if isinstance(project_data, dict) else {}
    return debug_section if isinstance(debug_section, dict) else {}


def load_board_metadata() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    board_section = project_data.get("board", {}) if isinstance(project_data, dict) else {}
    return board_section if isinstance(board_section, dict) else {}


def configured_mcu_name() -> str | None:
    board_metadata = load_board_metadata()
    mcu_name = board_metadata.get("mcu")
    return mcu_name.strip() if isinstance(mcu_name, str) and mcu_name.strip() else None


def candidate_svd_names(mcu_name: str) -> list[str]:
    normalized = mcu_name.strip().upper()
    if not normalized:
        return []

    candidates: list[str] = []

    def add_candidate(name: str) -> None:
        if name and name not in candidates:
            candidates.append(name)

    add_candidate(f"{normalized}.svd")
    if normalized.startswith("STM32"):
        device_code = normalized[5:]
        if len(device_code) >= 4:
            add_candidate(f"STM32{device_code[:4]}.svd")
            add_candidate(f"STM32{device_code[0]}{device_code[1]}x{device_code[3]}.svd")
        if len(device_code) >= 5:
            add_candidate(f"STM32{device_code[:5]}.svd")
    return candidates


def derive_svd_search_roots() -> list[Path]:
    roots: list[Path] = []

    def add_root(path: Path) -> None:
        if path.is_dir() and path not in roots:
            roots.append(path)

    env_path = os.environ.get(DEFAULT_SVD_PATH_ENV_VAR)
    if env_path:
        resolved = Path(env_path).expanduser()
        if resolved.is_file():
            add_root(resolved.parent)
        else:
            add_root(resolved)

    debug_metadata = load_debug_metadata()
    configured_svd_path = debug_metadata.get("svd_path")
    if isinstance(configured_svd_path, str) and configured_svd_path.strip():
        resolved = Path(configured_svd_path).expanduser()
        if resolved.is_file():
            add_root(resolved.parent)
        else:
            add_root(resolved)

    for root in Path("C:/ST").glob("STM32CubeCLT_*/STMicroelectronics_CMSIS_SVD"):
        add_root(root)

    return roots


def resolve_svd_path() -> str:
    env_path = os.environ.get(DEFAULT_SVD_PATH_ENV_VAR)
    if env_path:
        resolved = Path(env_path).expanduser()
        if resolved.is_file():
            return str(resolved)

    debug_metadata = load_debug_metadata()
    configured_svd_path = debug_metadata.get("svd_path")
    if isinstance(configured_svd_path, str) and configured_svd_path.strip():
        resolved = Path(configured_svd_path).expanduser()
        if resolved.is_file():
            return str(resolved)

    mcu_name = configured_mcu_name()
    if not mcu_name:
        raise FileNotFoundError("No board.mcu value is configured in stm32-project.json, so an SVD file could not be resolved automatically.")

    candidate_names = candidate_svd_names(mcu_name)
    checked_paths: list[str] = []
    for root in derive_svd_search_roots():
        for candidate_name in candidate_names:
            candidate_path = root / candidate_name
            checked_paths.append(str(candidate_path))
            if candidate_path.is_file():
                return str(candidate_path)

    raise FileNotFoundError(
        f"No SVD file was found for MCU '{mcu_name}'. Checked: {checked_paths}. Set {DEFAULT_SVD_PATH_ENV_VAR} to the correct file if needed."
    )


def parse_svd_field(field_node: ET.Element) -> dict[str, object]:
    enumerated_values: dict[int, str] = {}
    for enum_node in field_node.findall("{*}enumeratedValues/{*}enumeratedValue"):
        enum_name = enum_node.findtext("{*}name")
        enum_value = enum_node.findtext("{*}value")
        if not enum_name or not enum_value:
            continue
        try:
            enumerated_values[int(enum_value, 0)] = enum_name.strip()
        except ValueError:
            continue

    bit_offset_text = field_node.findtext("{*}bitOffset")
    bit_width_text = field_node.findtext("{*}bitWidth")
    bit_range_text = field_node.findtext("{*}bitRange")
    bit_offset = int(bit_offset_text, 0) if bit_offset_text else None
    bit_width = int(bit_width_text, 0) if bit_width_text else None
    if bit_range_text and bit_range_text.startswith("[") and ":" in bit_range_text:
        msb_text, lsb_text = bit_range_text.strip("[]").split(":", maxsplit=1)
        msb = int(msb_text, 0)
        lsb = int(lsb_text, 0)
        bit_offset = lsb
        bit_width = (msb - lsb) + 1

    return {
        "name": (field_node.findtext("{*}name") or "").strip(),
        "description": (field_node.findtext("{*}description") or "").strip() or None,
        "bit_offset": bit_offset,
        "bit_width": bit_width,
        "enumerated_values": enumerated_values,
    }


def parse_svd_device(path: str) -> dict[str, object]:
    cached = SVD_CACHE.get(path)
    if cached is not None:
        return cached

    root = ET.parse(path).getroot()
    raw_peripherals: dict[str, dict[str, object]] = {}
    for peripheral_node in root.findall(".//{*}peripheral"):
        peripheral_name = (peripheral_node.findtext("{*}name") or "").strip()
        if not peripheral_name:
            continue
        registers: dict[str, dict[str, object]] = {}
        registers_node = peripheral_node.find("{*}registers")
        if registers_node is not None:
            for register_node in registers_node.findall("{*}register"):
                register_name = (register_node.findtext("{*}name") or "").strip()
                if not register_name:
                    continue
                fields: dict[str, dict[str, object]] = {}
                fields_node = register_node.find("{*}fields")
                if fields_node is not None:
                    for field_node in fields_node.findall("{*}field"):
                        field_definition = parse_svd_field(field_node)
                        field_name = str(field_definition.get("name") or "").upper()
                        if field_name:
                            fields[field_name] = field_definition

                offset_text = register_node.findtext("{*}addressOffset")
                size_text = register_node.findtext("{*}size")
                registers[register_name.upper()] = {
                    "name": register_name,
                    "description": (register_node.findtext("{*}description") or "").strip() or None,
                    "address_offset": int(offset_text, 0) if offset_text else 0,
                    "size": int(size_text, 0) if size_text else 32,
                    "fields": fields,
                    "derived_from": register_node.attrib.get("derivedFrom"),
                }

        base_address_text = peripheral_node.findtext("{*}baseAddress")
        raw_peripherals[peripheral_name.upper()] = {
            "name": peripheral_name,
            "description": (peripheral_node.findtext("{*}description") or "").strip() or None,
            "base_address": int(base_address_text, 0) if base_address_text else None,
            "registers": registers,
            "derived_from": peripheral_node.attrib.get("derivedFrom"),
        }

    resolved_peripherals: dict[str, dict[str, object]] = {}

    def resolve_register(register_name: str, register_map: dict[str, dict[str, object]]) -> dict[str, object]:
        register = register_map[register_name]
        derived_from = register.get("derived_from")
        if not isinstance(derived_from, str) or derived_from.upper() not in register_map:
            return {
                **register,
                "fields": dict(register.get("fields", {})),
            }

        base_register = resolve_register(derived_from.upper(), register_map)
        merged_fields = dict(base_register.get("fields", {}))
        merged_fields.update(register.get("fields", {}))
        return {
            **base_register,
            **register,
            "fields": merged_fields,
        }

    def resolve_peripheral(peripheral_name: str) -> dict[str, object]:
        if peripheral_name in resolved_peripherals:
            return resolved_peripherals[peripheral_name]

        peripheral = raw_peripherals[peripheral_name]
        derived_from = peripheral.get("derived_from")
        if isinstance(derived_from, str) and derived_from.upper() in raw_peripherals:
            base_peripheral = resolve_peripheral(derived_from.upper())
            merged_registers = dict(base_peripheral.get("registers", {}))
        else:
            base_peripheral = {}
            merged_registers = {}

        raw_registers = dict(peripheral.get("registers", {}))
        for register_name in raw_registers:
            merged_registers[register_name] = resolve_register(register_name, raw_registers)

        resolved = {
            **base_peripheral,
            **peripheral,
            "registers": merged_registers,
        }
        resolved_peripherals[peripheral_name] = resolved
        return resolved

    for peripheral_name in raw_peripherals:
        resolve_peripheral(peripheral_name)

    parsed = {
        "device_name": (root.findtext("{*}name") or "").strip() or Path(path).stem,
        "path": path,
        "peripherals": resolved_peripherals,
    }
    SVD_CACHE[path] = parsed
    return parsed


def decode_register_fields(register_value: int, register_definition: dict[str, object]) -> dict[str, dict[str, object]]:
    fields = register_definition.get("fields")
    if not isinstance(fields, dict):
        return {}

    decoded: dict[str, dict[str, object]] = {}
    for field_name, field_definition in fields.items():
        if not isinstance(field_definition, dict):
            continue
        bit_offset = field_definition.get("bit_offset")
        bit_width = field_definition.get("bit_width")
        if not isinstance(bit_offset, int) or not isinstance(bit_width, int) or bit_width <= 0:
            continue
        mask = (1 << bit_width) - 1
        field_value = (register_value >> bit_offset) & mask
        enum_name = None
        enumerated_values = field_definition.get("enumerated_values")
        if isinstance(enumerated_values, dict):
            enum_name = enumerated_values.get(field_value)
        decoded[str(field_name)] = {
            "value": field_value,
            "hex": hex(field_value),
            "bit_offset": bit_offset,
            "bit_width": bit_width,
            "description": field_definition.get("description"),
            "enumerated_name": enum_name,
        }
    return decoded


def peripheral_family_name(peripheral: str) -> str:
    normalized = normalize_uart_peripheral_name(peripheral)
    if normalized.startswith("USART") or normalized.startswith("UART"):
        return "uart"
    if normalized.startswith("SPI"):
        return "spi"
    if normalized.startswith("I2C"):
        return "i2c"
    if normalized.startswith("TIM"):
        return "timer"
    if normalized.startswith("GPIO"):
        return "gpio"
    if normalized.startswith("ADC"):
        return "adc"
    if normalized == "RCC":
        return "rcc"
    return "other"


def extract_gpio_pin_number(question: str, peripheral: str) -> int | None:
    port_suffix = peripheral.strip().upper().replace("GPIO", "")[:1].lower()
    explicit_pin = re.search(r"\bpin\s*(1[0-5]|[0-9])\b", question)
    if explicit_pin:
        return int(explicit_pin.group(1))
    if port_suffix:
        compact_pin = re.search(rf"\bp{port_suffix}(1[0-5]|[0-9])\b", question)
        if compact_pin:
            return int(compact_pin.group(1))
    return None


def candidate_field_names(question: str, peripheral: str) -> list[str]:
    family = peripheral_family_name(peripheral)
    lowered = question.lower()
    candidates: list[str] = []

    def add(*names: str) -> None:
        for name in names:
            upper_name = name.upper()
            if upper_name not in candidates:
                candidates.append(upper_name)

    if family == "spi":
        if "master" in lowered or "slave" in lowered:
            add("MSTR")
        if "prescaler" in lowered or "baud" in lowered:
            add("BR")
        if "cpol" in lowered or "clock polarity" in lowered:
            add("CPOL")
        if "cpha" in lowered or "clock phase" in lowered:
            add("CPHA")
        if "enable" in lowered:
            add("SPE")
        if "data size" in lowered or "datasize" in lowered:
            add("DS")
    elif family == "i2c":
        if "timing" in lowered:
            add("PRESC", "SCLDEL", "SDADEL", "SCLH", "SCLL")
        if "prescaler" in lowered:
            add("PRESC")
        if "enable" in lowered:
            add("PE")
        if "address" in lowered:
            add("OA1")
        if "clock source" in lowered or "clock" in lowered:
            add("PRESC")
    elif family == "timer":
        if "prescaler" in lowered:
            add("PSC")
        if "auto reload" in lowered or "autoreload" in lowered or "period" in lowered:
            add("ARR")
        if "enable" in lowered or "running" in lowered or "counter" in lowered:
            add("CEN")
        if "direction" in lowered:
            add("DIR")
    elif family == "gpio":
        if "mode" in lowered:
            add("MODER")
        if "pull" in lowered:
            add("PUPDR")
        if "output type" in lowered or "push-pull" in lowered or "open-drain" in lowered:
            add("OT")
        if "state" in lowered or "level" in lowered or "input" in lowered:
            add("IDR", "ODR")
        if "alternate" in lowered or "af" in lowered:
            add("AFRL", "AFRH")
    elif family == "adc":
        if "resolution" in lowered:
            add("RES")
        if "enable" in lowered or "enabled" in lowered:
            add("ADEN")
    elif family == "rcc":
        if "clock source" in lowered or "sysclk" in lowered or "system clock" in lowered:
            add("SWS")
        if "ahb" in lowered or "hclk" in lowered:
            add("HPRE")
        if "apb1" in lowered or "pclk1" in lowered:
            add("PPRE1")
        if "apb2" in lowered or "pclk2" in lowered:
            add("PPRE2")

    explicit_field = re.findall(r"\b[a-z][a-z0-9_]{1,15}\b", lowered)
    for field_name in explicit_field:
        if field_name.upper() in {
            "CPOL", "CPHA", "MSTR", "BR", "SPE", "DS", "PE", "PRESC", "SCLDEL", "SDADEL", "SCLH", "SCLL",
            "PSC", "ARR", "CEN", "DIR", "RES", "ADEN", "SWS", "HPRE", "PPRE1", "PPRE2", "MODER", "PUPDR",
            "IDR", "ODR", "AFRL", "AFRH", "OA1",
        }:
            add(field_name)

    return candidates


def format_field_value(register_name: str, field_name: str, field_data: dict[str, object]) -> str:
    value = field_data.get("value")
    enumerated_name = field_data.get("enumerated_name")
    if enumerated_name:
        return f"{register_name}.{field_name} = {value} ({enumerated_name})"
    return f"{register_name}.{field_name} = {value}"


def format_register_value(register_name: str, register_data: dict[str, object]) -> str:
    return f"{register_name} = {register_data.get('value')}"


def answer_semantic_peripheral_question(question: str, peripheral: str, registers: dict[str, object]) -> dict[str, object] | None:
    family = peripheral_family_name(peripheral)
    candidate_fields = candidate_field_names(question, peripheral)
    if not candidate_fields:
        return None

    gpio_pin = extract_gpio_pin_number(question.lower(), peripheral) if family == "gpio" else None
    matches: list[dict[str, object]] = []
    lowered = question.lower()

    for register_name, register_data in registers.items():
        if not isinstance(register_data, dict):
            continue
        if register_name in candidate_fields:
            match = {
                "register": register_name,
                "field": None,
                "value": register_data.get("value"),
                "hex": register_data.get("hex"),
                "enumerated_name": None,
                "description": register_data.get("description"),
            }
            if match not in matches:
                matches.append(match)
        fields = register_data.get("fields")
        if not isinstance(fields, dict):
            continue

        for candidate in candidate_fields:
            if family == "gpio" and gpio_pin is not None:
                field_names = [name for name in fields if name == f"{candidate}{gpio_pin}" or name.startswith(candidate) and name.endswith(str(gpio_pin))]
            else:
                field_names = [name for name in fields if name == candidate]

            for field_name in field_names:
                field_data = fields.get(field_name)
                if not isinstance(field_data, dict):
                    continue
                match = {
                    "register": register_name,
                    "field": field_name,
                    "value": field_data.get("value"),
                    "hex": field_data.get("hex"),
                    "enumerated_name": field_data.get("enumerated_name"),
                    "description": field_data.get("description"),
                }
                if match not in matches:
                    matches.append(match)

    if not matches:
        return None

    if family == "gpio" and gpio_pin is not None and any(token in lowered for token in ("state", "level")):
        output_match = next((match for match in matches if str(match["field"]).startswith("ODR")), None)
        input_match = next((match for match in matches if str(match["field"]).startswith("IDR")), None)
        preferred = output_match or input_match
        if preferred is not None:
            answer = f"Live {peripheral} pin {gpio_pin} state: {preferred['register']}.{preferred['field']} = {preferred['value']}."
            return {"answer": answer, "matches": [preferred]}

    summary_parts: list[str] = []
    for match in matches[:4]:
        if match.get("field") is None:
            summary_parts.append(format_register_value(str(match["register"]), match))
        else:
            summary_parts.append(format_field_value(str(match["register"]), str(match["field"]), match))
    summary = "; ".join(summary_parts)
    answer = f"Live {peripheral} field values: {summary}."
    return {"answer": answer, "matches": matches}


def inspect_peripheral_registers_from_svd(
    *,
    session: DebugSession,
    peripheral_name: str,
    register_name: str | None,
    timeout_seconds: int,
) -> dict[str, object]:
    svd_path = resolve_svd_path()
    svd_device = parse_svd_device(svd_path)
    peripherals = svd_device.get("peripherals")
    normalized_peripheral = peripheral_name.strip().upper().replace(" ", "")
    if not isinstance(peripherals, dict) or normalized_peripheral not in peripherals:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "inspect_peripheral",
            "session_name": session.session_name,
            "peripheral": normalized_peripheral,
            "message": f"Peripheral '{peripheral_name}' was not found in SVD file {svd_path}.",
        }

    peripheral_definition = peripherals[normalized_peripheral]
    all_registers = peripheral_definition.get("registers")
    if not isinstance(all_registers, dict) or not all_registers:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "inspect_peripheral",
            "session_name": session.session_name,
            "peripheral": normalized_peripheral,
            "svd_path": svd_path,
            "message": f"Peripheral '{normalized_peripheral}' does not have register definitions in the resolved SVD file.",
        }

    requested_register_names = [register_name.strip().upper()] if isinstance(register_name, str) and register_name.strip() else sorted(all_registers.keys())
    missing = [name for name in requested_register_names if name not in all_registers]
    if missing:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "inspect_peripheral",
            "session_name": session.session_name,
            "peripheral": normalized_peripheral,
            "svd_path": svd_path,
            "message": f"Registers {missing} were not found under peripheral '{normalized_peripheral}'.",
        }

    commands = ["echo === REGISTERS ===\\n"]
    for requested_register_name in requested_register_names:
        register_definition = all_registers[requested_register_name]
        address = int(peripheral_definition.get("base_address", 0)) + int(register_definition.get("address_offset", 0))
        commands.append(f'printf "{requested_register_name}=0x%08x\\n", *(unsigned int *){address:#010x}')

    batch_result = run_gdb_batch(session=session, commands=commands, timeout_seconds=timeout_seconds)
    if not batch_result.get("success"):
        batch_result.update(
            {
                "operation": "inspect_peripheral",
                "session_name": session.session_name,
                "peripheral": normalized_peripheral,
                "svd_path": svd_path,
            }
        )
        return batch_result

    raw_values = parse_named_values(str(batch_result.get("stdout", "")), "REGISTERS")
    registers: dict[str, object] = {}
    for requested_register_name in requested_register_names:
        register_definition = all_registers[requested_register_name]
        register_value = raw_values.get(requested_register_name)
        if register_value is None:
            continue
        size_bits = int(register_definition.get("size", 32))
        masked_value = register_value & ((1 << min(size_bits, 32)) - 1)
        registers[requested_register_name] = {
            "name": register_definition.get("name") or requested_register_name,
            "description": register_definition.get("description"),
            "value": masked_value,
            "hex": f"0x{masked_value:08x}",
            "address": hex(int(peripheral_definition.get("base_address", 0)) + int(register_definition.get("address_offset", 0))),
            "fields": decode_register_fields(masked_value, register_definition),
        }

    return {
        "success": True,
        "implemented": True,
        "server": "debug",
        "operation": "inspect_peripheral",
        "session_name": session.session_name,
        "device": svd_device.get("device_name"),
        "svd_path": svd_path,
        "peripheral": peripheral_definition.get("name") or normalized_peripheral,
        "description": peripheral_definition.get("description"),
        "registers": registers,
        "transcript": batch_result.get("stdout"),
    }


def debug_tool_entry() -> dict[str, object]:
    tools_config = shared.load_tools_local_config()
    config_data = tools_config.get("data")
    if not isinstance(config_data, dict):
        return {}
    tools = config_data.get("tools")
    if not isinstance(tools, dict):
        return {}
    tool_entry = tools.get("stlink_gdb_server")
    return tool_entry if isinstance(tool_entry, dict) else {}


def arm_gdb_tool_entry() -> dict[str, object]:
    tools_config = shared.load_tools_local_config()
    config_data = tools_config.get("data")
    if not isinstance(config_data, dict):
        return {}
    tools = config_data.get("tools")
    if not isinstance(tools, dict):
        return {}
    tool_entry = tools.get("arm_gdb")
    return tool_entry if isinstance(tool_entry, dict) else {}


def default_stlink_gdb_server_executable_name() -> str:
    return stlink_gdb_adapter.default_stlink_gdb_server_executable_name(shared.host_platform_name())


def default_arm_gdb_executable_name() -> str:
    return arm_gdb_adapter.default_arm_gdb_executable_name(shared.host_platform_name())


def derive_stlink_gdb_server_candidates() -> list[Path]:
    return stlink_gdb_adapter.derive_stlink_gdb_server_candidates(
        resolve_cubeide_path=build_server.resolve_cubeide_path,
        host_platform=shared.host_platform_name(),
    )


def derive_arm_gdb_candidates() -> list[Path]:
    return arm_gdb_adapter.derive_arm_gdb_candidates(
        resolve_cubeide_path=build_server.resolve_cubeide_path,
        host_platform=shared.host_platform_name(),
    )


def discover_stlink_gdb_server() -> dict[str, object]:
    return stlink_gdb_adapter.discover_stlink_gdb_server(
        host_platform=shared.host_platform_name(),
        load_tools_local_config=shared.load_tools_local_config,
        resolve_candidate_path=shared.resolve_candidate_path,
        resolve_cubeide_path=build_server.resolve_cubeide_path,
        which_resolver=shutil.which,
    )


def discover_arm_gdb() -> dict[str, object]:
    return arm_gdb_adapter.discover_arm_gdb(
        host_platform=shared.host_platform_name(),
        load_tools_local_config=shared.load_tools_local_config,
        resolve_candidate_path=shared.resolve_candidate_path,
        resolve_cubeide_path=build_server.resolve_cubeide_path,
        which_resolver=shutil.which,
    )


def resolve_stlink_gdb_server_path() -> str:
    return stlink_gdb_adapter.resolve_stlink_gdb_server_path(discover_stlink_gdb_server())


def resolve_arm_gdb_path() -> str:
    return arm_gdb_adapter.resolve_arm_gdb_path(discover_arm_gdb())


def parse_debug_server_version(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if "st-link gdb server" in line.strip().lower():
            return line.strip()
    for line in stdout.splitlines():
        if line.strip():
            return line.strip()
    return None


def parse_gdb_version(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.strip():
            return line.strip()
    return None


def run_debug_command(command: list[str], timeout_seconds: int) -> dict[str, object]:
    return stlink_gdb_adapter.run_debug_command(
        command,
        timeout_seconds=timeout_seconds,
        subprocess_module=subprocess,
    )


def parse_register_output(stdout: str) -> dict[str, str]:
    registers: dict[str, str] = {}
    in_registers = False
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped == "=== REGISTERS ===":
            in_registers = True
            continue
        if stripped.startswith("=== ") and stripped.endswith(" ==="):
            in_registers = False
        if not in_registers or not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 2:
            registers[parts[0]] = parts[1]
    return registers


def parse_section_lines(stdout: str, section_name: str) -> list[str]:
    marker = f"=== {section_name} ==="
    collected: list[str] = []
    in_section = False
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped == marker:
            in_section = True
            continue
        if in_section and stripped.startswith("=== ") and stripped.endswith(" ==="):
            break
        if in_section and stripped:
            collected.append(stripped)
    return collected


def parse_named_values(stdout: str, section_name: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in parse_section_lines(stdout, section_name):
        if "=" not in line:
            continue
        name, _, raw_value = line.partition("=")
        key = name.strip()
        value_text = raw_value.strip()
        if not key or not value_text:
            continue
        try:
            values[key] = int(value_text, 0)
        except ValueError:
            continue
    return values


def normalize_uart_peripheral_name(peripheral: str) -> str:
    normalized = peripheral.strip().upper().replace(" ", "")
    aliases = {
        "UART1": "USART1",
        "UART2": "USART2",
        "UART3": "USART3",
        "USART4": "UART4",
        "USART5": "UART5",
    }
    return aliases.get(normalized, normalized)


def decode_ahb_prescaler(bits: int) -> int:
    if bits < 0b1000:
        return 1
    return {
        0b1000: 2,
        0b1001: 4,
        0b1010: 8,
        0b1011: 16,
        0b1100: 64,
        0b1101: 128,
        0b1110: 256,
        0b1111: 512,
    }.get(bits, 1)


def decode_apb_prescaler(bits: int) -> int:
    if bits < 0b100:
        return 1
    return {
        0b100: 2,
        0b101: 4,
        0b110: 8,
        0b111: 16,
    }.get(bits, 1)


def decode_word_length(cr1: int) -> str:
    m0 = (cr1 >> 12) & 0x1
    m1 = (cr1 >> 28) & 0x1
    return {
        (0, 0): "8-bit",
        (0, 1): "7-bit",
        (1, 0): "9-bit",
    }.get((m0, m1), "reserved")


def decode_stop_bits(cr2: int) -> str:
    stop_bits = (cr2 >> 12) & 0x3
    return {
        0b00: "1",
        0b01: "0.5",
        0b10: "2",
        0b11: "1.5",
    }.get(stop_bits, "unknown")


def decode_parity(cr1: int) -> str:
    parity_enabled = ((cr1 >> 10) & 0x1) == 1
    if not parity_enabled:
        return "none"
    return "odd" if ((cr1 >> 9) & 0x1) == 1 else "even"


def decode_uart_mode(cr1: int) -> str:
    transmitter_enabled = ((cr1 >> 3) & 0x1) == 1
    receiver_enabled = ((cr1 >> 2) & 0x1) == 1
    if transmitter_enabled and receiver_enabled:
        return "tx_rx"
    if transmitter_enabled:
        return "tx"
    if receiver_enabled:
        return "rx"
    return "disabled"


def estimate_baud_rate(clock_hz: int | None, *, brr: int, over8: bool) -> int | None:
    if clock_hz is None or brr <= 0:
        return None
    if over8:
        usart_div = (brr & 0xFFF0) | ((brr & 0x0007) << 1)
        if usart_div <= 0:
            return None
        return int(round((2 * clock_hz) / usart_div))
    return int(round(clock_hz / brr))


def compute_stm32l4_clock_tree(rcc_values: dict[str, int], peripheral: str) -> dict[str, object]:
    cr = rcc_values.get("RCC_CR", 0)
    cfgr = rcc_values.get("RCC_CFGR", 0)
    pllcfgr = rcc_values.get("RCC_PLLCFGR", 0)
    ccipr = rcc_values.get("RCC_CCIPR", 0)

    msi_range = (cr >> 4) & 0xF
    msi_hz = MSI_RANGE_FREQUENCIES_HZ.get(msi_range)
    hsi16_hz = 16_000_000
    lse_hz = 32_768

    sysclk_source_bits = (cfgr >> 2) & 0x3
    pll_source_bits = pllcfgr & 0x3
    pll_m = ((pllcfgr >> 4) & 0x7) + 1
    pll_n = (pllcfgr >> 8) & 0x7F
    pll_r = (((pllcfgr >> 25) & 0x3) + 1) * 2

    pll_source_name = {0: "none", 1: "msi", 2: "hsi16", 3: "hse"}.get(pll_source_bits, "unknown")
    pll_input_hz = {
        "msi": msi_hz,
        "hsi16": hsi16_hz,
        "hse": None,
        "none": None,
    }.get(pll_source_name)
    pll_r_hz = None
    if pll_input_hz is not None and pll_m > 0 and pll_n > 0 and pll_r > 0:
        pll_r_hz = int((pll_input_hz / pll_m) * pll_n / pll_r)

    sysclk_source_name = {0: "msi", 1: "hsi16", 2: "hse", 3: "pll"}.get(sysclk_source_bits, "unknown")
    sysclk_hz = {
        "msi": msi_hz,
        "hsi16": hsi16_hz,
        "hse": None,
        "pll": pll_r_hz,
    }.get(sysclk_source_name)

    ahb_divider = decode_ahb_prescaler((cfgr >> 4) & 0xF)
    apb1_divider = decode_apb_prescaler((cfgr >> 8) & 0x7)
    apb2_divider = decode_apb_prescaler((cfgr >> 11) & 0x7)
    hclk_hz = int(sysclk_hz / ahb_divider) if sysclk_hz is not None else None
    pclk1_hz = int(hclk_hz / apb1_divider) if hclk_hz is not None else None
    pclk2_hz = int(hclk_hz / apb2_divider) if hclk_hz is not None else None

    peripheral_selector = {
        "USART1": ((ccipr >> 0) & 0x3, "pclk2"),
        "USART2": ((ccipr >> 2) & 0x3, "pclk1"),
        "USART3": ((ccipr >> 4) & 0x3, "pclk1"),
        "UART4": ((ccipr >> 6) & 0x3, "pclk1"),
        "UART5": ((ccipr >> 8) & 0x3, "pclk1"),
    }
    selector_bits, default_bus = peripheral_selector.get(peripheral, (0, "pclk2"))
    selected_clock_name = {
        0: default_bus,
        1: "sysclk",
        2: "hsi16",
        3: "lse",
    }.get(selector_bits, default_bus)
    peripheral_clock_hz = {
        "pclk1": pclk1_hz,
        "pclk2": pclk2_hz,
        "sysclk": sysclk_hz,
        "hsi16": hsi16_hz,
        "lse": lse_hz,
    }.get(selected_clock_name)

    return {
        "sysclk_source": sysclk_source_name,
        "sysclk_hz": sysclk_hz,
        "hclk_hz": hclk_hz,
        "pclk1_hz": pclk1_hz,
        "pclk2_hz": pclk2_hz,
        "pll_source": pll_source_name,
        "pll_r_hz": pll_r_hz,
        "msi_range": msi_range,
        "msi_hz": msi_hz,
        "peripheral_clock_source": selected_clock_name,
        "peripheral_clock_hz": peripheral_clock_hz,
    }


def build_gdb_batch_command(gdb_path: str, *, elf_path: str | None, port_number: int, commands: list[str]) -> list[str]:
    return arm_gdb_adapter.build_gdb_batch_command(
        gdb_path,
        elf_path=elf_path,
        port_number=port_number,
        commands=commands,
    )


def run_gdb_batch(*, session: DebugSession, commands: list[str], timeout_seconds: int) -> dict[str, object]:
    elf_path = resolve_debug_elf_path()

    try:
        gdb_path = resolve_arm_gdb_path()
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "gdb_batch",
            "session_name": session.session_name,
            "message": str(exc),
        }

    command = build_gdb_batch_command(gdb_path, elf_path=elf_path, port_number=session.port_number, commands=commands)
    result = run_debug_command(command, timeout_seconds)
    result.update(
        {
            "implemented": True,
            "server": "debug",
            "operation": "gdb_batch",
            "session_name": session.session_name,
            "gdb_path": gdb_path,
            "elf_path": elf_path,
            "port_number": session.port_number,
            "commands": commands,
        }
    )
    return result


@mcp.tool(description="Read live UART or USART configuration directly from the attached STM32 target through a managed debug session and estimate the active baud rate from peripheral registers.")
def stm32_debug_uart_configuration(
    session_name: str = "default",
    peripheral: str = "USART1",
    timeout_seconds: int = 20,
) -> dict[str, object]:
    normalized_peripheral = normalize_uart_peripheral_name(peripheral)
    register_result = stm32_debug_inspect_peripheral(
        session_name=session_name,
        peripheral=normalized_peripheral,
        register=None,
        timeout_seconds=timeout_seconds,
    )
    if not register_result.get("success"):
        register_result.update(
            {
                "operation": "uart_configuration",
                "session_name": session_name,
                "peripheral": normalized_peripheral,
            }
        )
        return register_result

    if normalized_peripheral not in STM32L4_USART_BASES:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "uart_configuration",
            "peripheral": normalized_peripheral,
            "message": f"Peripheral '{peripheral}' is not supported yet for live UART inspection.",
        }

    session = ACTIVE_DEBUG_SESSIONS.get(session_name)
    if session is None:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "uart_configuration",
            "session_name": session_name,
            "peripheral": normalized_peripheral,
            "message": f"Debug session '{session_name}' is not running.",
        }

    batch_result = run_gdb_batch(
        session=session,
        commands=[
            "echo === RCC ===\\n",
            f'printf "RCC_CR=0x%08x\\n", *(unsigned int *){STM32L4_RCC_CR:#010x}',
            f'printf "RCC_CFGR=0x%08x\\n", *(unsigned int *){STM32L4_RCC_CFGR:#010x}',
            f'printf "RCC_PLLCFGR=0x%08x\\n", *(unsigned int *){STM32L4_RCC_PLLCFGR:#010x}',
            f'printf "RCC_CCIPR=0x%08x\\n", *(unsigned int *){STM32L4_RCC_CCIPR:#010x}',
        ],
        timeout_seconds=timeout_seconds,
    )
    if not batch_result.get("success"):
        batch_result.update(
            {
                "operation": "uart_configuration",
                "session_name": session_name,
                "peripheral": normalized_peripheral,
            }
        )
        return batch_result

    stdout = str(batch_result.get("stdout", ""))
    rcc_values = parse_named_values(stdout, "RCC")
    register_map = register_result.get("registers") if isinstance(register_result.get("registers"), dict) else {}
    cr1 = int(register_map.get("CR1", {}).get("value", 0)) if isinstance(register_map.get("CR1"), dict) else 0
    cr2 = int(register_map.get("CR2", {}).get("value", 0)) if isinstance(register_map.get("CR2"), dict) else 0
    cr3 = int(register_map.get("CR3", {}).get("value", 0)) if isinstance(register_map.get("CR3"), dict) else 0
    brr = int(register_map.get("BRR", {}).get("value", 0)) if isinstance(register_map.get("BRR"), dict) else 0
    over8 = ((cr1 >> 15) & 0x1) == 1
    clock_tree = compute_stm32l4_clock_tree(rcc_values, normalized_peripheral)
    estimated_baud_rate = estimate_baud_rate(clock_tree.get("peripheral_clock_hz"), brr=brr, over8=over8)

    return {
        "success": True,
        "implemented": True,
        "server": "debug",
        "operation": "uart_configuration",
        "session_name": session_name,
        "peripheral": normalized_peripheral,
        "registers": register_result.get("registers"),
        "clock_tree": clock_tree,
        "configuration": {
            "baud_rate": estimated_baud_rate,
            "oversampling": 8 if over8 else 16,
            "word_length": decode_word_length(cr1),
            "stop_bits": decode_stop_bits(cr2),
            "parity": decode_parity(cr1),
            "mode": decode_uart_mode(cr1),
            "hardware_flow_control": "enabled" if (cr3 & 0x300) else "disabled",
        },
        "transcript": f"{register_result.get('transcript', '')}\n{stdout}".strip(),
        "message": (
            f"Live {normalized_peripheral} configuration was read from the target. Estimated baud rate is {estimated_baud_rate}."
            if estimated_baud_rate is not None
            else f"Live {normalized_peripheral} configuration was read from the target, but the baud rate could not be estimated from the current clock settings."
        ),
    }


def default_debug_port() -> int:
    debug_metadata = load_debug_metadata()
    port_number = debug_metadata.get("gdb_port")
    return int(port_number) if isinstance(port_number, int) else 55001


def default_swo_port() -> int | None:
    debug_metadata = load_debug_metadata()
    swo_port = debug_metadata.get("swo_port")
    return int(swo_port) if isinstance(swo_port, int) else 55002


def resolve_swo_launch_port(swo_port: int | None, *, enable_swo: bool) -> int | None:
    if not enable_swo:
        return 0
    if swo_port is not None:
        return swo_port
    return default_swo_port()


def resolve_debug_elf_path() -> str | None:
    debug_metadata = load_debug_metadata()
    elf_path = debug_metadata.get("elf_path")
    if isinstance(elf_path, str) and elf_path.strip():
        return str((Path.cwd() / elf_path).resolve())

    build_metadata = build_server.load_build_metadata()
    artifact = build_metadata.get("artifact")
    if isinstance(artifact, str) and artifact.strip():
        return str(Path(artifact).expanduser().resolve())
    return None


def resolve_cube_programmer_installation_path() -> str | None:
    try:
        programmer_cli_path = Path(shared.resolve_cli_path()).resolve()
    except FileNotFoundError:
        return None

    install_root = programmer_cli_path.parent
    return str(install_root) if install_root.is_dir() else None


def read_log_tail(log_path: Path | None, max_lines: int = 20) -> list[str]:
    if log_path is None or not log_path.is_file():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-max_lines:]


def parse_debugger_serials(stdout: str) -> list[str]:
    serials: list[str] = []
    for match in re.findall(r"\b[0-9A-F]{12,}\b", stdout.upper()):
        if match not in serials:
            serials.append(match)
    return serials


def is_tcp_port_open(port_number: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port_number)) == 0


def can_bind_tcp_port(port_number: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port_number))
        except OSError:
            return False
    return True


def select_launch_ports(preferred_port: int, preferred_swo_port: int | None) -> tuple[int, int | None, bool]:
    if can_bind_tcp_port(preferred_port) and (preferred_swo_port is None or preferred_swo_port == 0 or can_bind_tcp_port(preferred_swo_port)):
        return preferred_port, preferred_swo_port, False

    for candidate_port in range(55001, 55101):
        if not can_bind_tcp_port(candidate_port):
            continue

        if preferred_swo_port is None:
            return candidate_port, None, True
        if preferred_swo_port == 0:
            return candidate_port, 0, True

        candidate_swo_port = candidate_port + 1
        if can_bind_tcp_port(candidate_swo_port):
            return candidate_port, candidate_swo_port, True

    return preferred_port, preferred_swo_port, False


def active_session_summary(session: DebugSession) -> dict[str, object]:
    exit_code = session.process.poll()
    running = exit_code is None
    return {
        "session_name": session.session_name,
        "running": running,
        "exit_code": exit_code,
        "pid": session.process.pid,
        "command": session.command,
        "port_number": session.port_number,
        "swo_port": session.swo_port,
        "serial_number": session.serial_number,
        "started_at": session.started_at,
        "console_log": str(session.console_log_path),
        "server_log": str(session.server_log_path),
        "port_open": is_tcp_port_open(session.port_number) if running else False,
        "console_log_tail": read_log_tail(session.console_log_path),
        "server_log_tail": read_log_tail(session.server_log_path),
    }


def cleanup_session(session_name: str) -> None:
    session = ACTIVE_DEBUG_SESSIONS.pop(session_name, None)
    if session is None:
        return
    if session.process.poll() is None:
        session.process.kill()
        try:
            session.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    session.output_handle.close()


def cleanup_all_sessions() -> None:
    for session_name in list(ACTIVE_DEBUG_SESSIONS):
        cleanup_session(session_name)


atexit.register(cleanup_all_sessions)


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
    return stlink_gdb_adapter.build_stlink_gdb_server_command(
        tool_path,
        port_number=port_number,
        persistent=persistent,
        server_log_path=server_log_path,
        log_level=log_level,
        verbose=verbose,
        refresh_delay=refresh_delay,
        verify=verify,
        swd=swd,
        swo_port=swo_port,
        cpu_clock_hz=cpu_clock_hz,
        swo_clock_div=swo_clock_div,
        initialize_reset=initialize_reset,
        serial_number=serial_number,
        apid=apid,
        attach=attach,
        shared_mode=shared_mode,
        erase_all=erase_all,
        cube_programmer_path=cube_programmer_path,
        frequency_khz=frequency_khz,
        halt=halt,
        incremental=incremental,
    )


def launch_stlink_gdb_server_process(command: list[str], *, output_handle: TextIO) -> subprocess.Popen[str]:
    return stlink_gdb_adapter.launch_stlink_gdb_server_process(
        command,
        output_handle=output_handle,
        working_directory=str(Path.cwd()),
        host_platform=shared.host_platform_name(),
        subprocess_module=subprocess,
    )


def collect_debug_capabilities() -> dict[str, object]:
    debug_metadata = load_debug_metadata()
    discovery = discover_stlink_gdb_server()
    gdb_discovery = discover_arm_gdb()
    version_result: dict[str, object] | None = None
    version_text: str | None = None
    gdb_version_result: dict[str, object] | None = None
    gdb_version_text: str | None = None
    resolved_path = discovery.get("resolved_path")
    if isinstance(resolved_path, str):
        version_result = run_debug_command(stlink_gdb_adapter.build_stlink_gdb_server_version_command(resolved_path), 10)
        version_text = parse_debug_server_version(str(version_result.get("stdout", "")))
    resolved_gdb_path = gdb_discovery.get("resolved_path")
    if isinstance(resolved_gdb_path, str):
        gdb_version_result = run_debug_command(arm_gdb_adapter.build_gdb_version_command(resolved_gdb_path), 10)
        gdb_version_text = parse_gdb_version(str(gdb_version_result.get("stdout", "")))
    try:
        svd_path = resolve_svd_path()
    except FileNotFoundError:
        svd_path = None

    return {
        "server": "debug",
        "implemented": isinstance(resolved_path, str),
        "capabilities": {
            "launch_server": isinstance(resolved_path, str),
            "list_debuggers": isinstance(resolved_path, str),
            "persistent_sessions": True,
            "attach_mode": True,
            "gdb_client": isinstance(resolved_gdb_path, str),
            "breakpoints": False,
            "registers": isinstance(resolved_gdb_path, str),
            "memory": isinstance(resolved_gdb_path, str),
            "snapshots": isinstance(resolved_gdb_path, str),
            "svd_register_inspection": isinstance(resolved_gdb_path, str) and isinstance(svd_path, str),
        },
        "debug": debug_metadata,
        "tool_path": resolved_path,
        "tool_discovery": discovery,
        "version": version_text,
        "version_check": version_result,
        "gdb_path": resolved_gdb_path,
        "gdb_discovery": gdb_discovery,
        "gdb_version": gdb_version_text,
        "gdb_version_check": gdb_version_result,
        "svd_path": svd_path,
        "active_sessions": [active_session_summary(session) for session in ACTIVE_DEBUG_SESSIONS.values()],
        "elf_path": resolve_debug_elf_path(),
        "project_config": shared.summarize_config_status(shared.load_project_metadata()),
        "tools_config": shared.summarize_config_status(shared.load_tools_local_config()),
    }


@mcp.tool(description="Report the current ST-LINK GDB server capabilities and resolved debug metadata from stm32-project.json.")
def stm32_debug_capabilities() -> dict[str, object]:
    return collect_debug_capabilities()


@mcp.tool(description="Report the installed ST-LINK GDB server version when the executable is available on the current host.")
def stm32_debug_server_version(timeout_seconds: int = 10) -> dict[str, object]:
    try:
        tool_path = resolve_stlink_gdb_server_path()
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "version",
            "message": str(exc),
        }

    result = run_debug_command(stlink_gdb_adapter.build_stlink_gdb_server_version_command(tool_path), timeout_seconds)
    result.update(
        {
            "implemented": True,
            "server": "debug",
            "operation": "version",
            "tool_path": tool_path,
            "version": parse_debug_server_version(str(result.get("stdout", ""))),
        }
    )
    return result


@mcp.tool(description="Report the installed ARM GDB client version used for Phase 2 runtime inspection when the executable is available on the current host.")
def stm32_debug_gdb_version(timeout_seconds: int = 10) -> dict[str, object]:
    try:
        tool_path = resolve_arm_gdb_path()
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "gdb_version",
            "message": str(exc),
        }

    result = run_debug_command(arm_gdb_adapter.build_gdb_version_command(tool_path), timeout_seconds)
    result.update(
        {
            "implemented": True,
            "server": "debug",
            "operation": "gdb_version",
            "tool_path": tool_path,
            "version": parse_gdb_version(str(result.get("stdout", ""))),
        }
    )
    return result


@mcp.tool(description="List ST-LINK serial numbers visible to the ST-LINK GDB server executable on the current host.")
def stm32_debug_list_debuggers(timeout_seconds: int = 10) -> dict[str, object]:
    try:
        tool_path = resolve_stlink_gdb_server_path()
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "list_debuggers",
            "message": str(exc),
        }

    cube_programmer_path = resolve_cube_programmer_installation_path()
    command = stlink_gdb_adapter.build_list_debuggers_command(
        tool_path,
        cube_programmer_path=cube_programmer_path,
    )
    result = run_debug_command(command, timeout_seconds)
    result.update(
        {
            "implemented": True,
            "server": "debug",
            "operation": "list_debuggers",
            "tool_path": tool_path,
            "cube_programmer_path": cube_programmer_path,
            "debuggers": parse_debugger_serials(str(result.get("stdout", ""))),
        }
    )
    return result


@mcp.tool(description="Launch the STM32CubeIDE ST-LINK GDB server as a managed background session and return the listening port plus log paths.")
def stm32_debug_launch(
    session_name: str = "default",
    port_number: int | None = None,
    swo_port: int | None = None,
    enable_swo: bool = True,
    serial_number: str | None = None,
    frequency_khz: int | None = None,
    attach: bool = False,
    persistent: bool = True,
    shared_mode: bool = False,
    verify: bool = False,
    incremental: bool = False,
    erase_all: bool = False,
    verbose: bool = False,
    log_level: int | None = None,
    refresh_delay: int | None = None,
    initialize_reset: bool = False,
    apid: int | None = None,
    halt: bool = False,
    timeout_seconds: int = 15,
) -> dict[str, object]:
    debug_metadata = load_debug_metadata()
    existing_session = ACTIVE_DEBUG_SESSIONS.get(session_name)
    if existing_session is not None and existing_session.process.poll() is None:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "launch",
            "session_name": session_name,
            "session": active_session_summary(existing_session),
            "message": f"Debug session '{session_name}' is already running.",
        }
    if existing_session is not None:
        cleanup_session(session_name)

    try:
        tool_path = resolve_stlink_gdb_server_path()
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "launch",
            "session_name": session_name,
            "debug_profile": debug_metadata,
            "message": str(exc),
        }

    requested_port = port_number or default_debug_port()
    requested_swo_port = resolve_swo_launch_port(swo_port, enable_swo=enable_swo)
    launch_port, launch_swo_port, used_fallback_port = select_launch_ports(requested_port, requested_swo_port)
    resolved_frequency = frequency_khz
    if resolved_frequency is None:
        project_data = shared.load_project_metadata().get("data")
        if isinstance(project_data, dict):
            board_info = project_data.get("board")
            if isinstance(board_info, dict):
                connect_defaults = board_info.get("connect_defaults")
                if isinstance(connect_defaults, dict):
                    default_frequency = connect_defaults.get("frequency_khz")
                    if isinstance(default_frequency, int):
                        resolved_frequency = default_frequency

    server_log_path = shared.create_log_path("stlink_gdbserver")
    command = build_stlink_gdb_server_command(
        tool_path,
        port_number=launch_port,
        persistent=persistent,
        server_log_path=server_log_path,
        log_level=log_level,
        verbose=verbose,
        refresh_delay=refresh_delay,
        verify=verify,
        swd=True,
        swo_port=launch_swo_port,
        initialize_reset=initialize_reset,
        serial_number=serial_number,
        apid=apid,
        attach=attach,
        shared_mode=shared_mode,
        erase_all=erase_all,
        cube_programmer_path=resolve_cube_programmer_installation_path(),
        frequency_khz=resolved_frequency,
        halt=halt,
        incremental=incremental,
    )

    console_log_path = shared.create_log_path("stlink_gdbserver_console")
    output_handle = console_log_path.open("w", encoding="utf-8")

    try:
        process = launch_stlink_gdb_server_process(
            command,
            output_handle=output_handle,
        )
    except OSError as exc:
        output_handle.close()
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "launch",
            "session_name": session_name,
            "command": command,
            "console_log": str(console_log_path),
            "server_log": str(server_log_path),
            "message": str(exc),
        }

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output_handle.close()
            return {
                "success": False,
                "implemented": True,
                "server": "debug",
                "operation": "launch",
                "session_name": session_name,
                "command": command,
                "exit_code": process.poll(),
                "console_log": str(console_log_path),
                "server_log": str(server_log_path),
                "console_log_tail": read_log_tail(console_log_path),
                "server_log_tail": read_log_tail(server_log_path),
                "message": "ST-LINK GDB server exited before the TCP port became ready.",
            }
        if is_tcp_port_open(launch_port):
            session = DebugSession(
                session_name=session_name,
                process=process,
                command=command,
                console_log_path=console_log_path,
                server_log_path=server_log_path,
                port_number=launch_port,
                swo_port=launch_swo_port,
                serial_number=serial_number,
                started_at=datetime.now().isoformat(timespec="seconds"),
                output_handle=output_handle,
            )
            ACTIVE_DEBUG_SESSIONS[session_name] = session
            return {
                "success": True,
                "implemented": True,
                "server": "debug",
                "operation": "launch",
                "session_name": session_name,
                "debug_profile": debug_metadata,
                "tool_path": tool_path,
                "requested_port_number": requested_port,
                "requested_swo_port": requested_swo_port,
                "used_fallback_port": used_fallback_port,
                "session": active_session_summary(session),
                "message": (
                    f"ST-LINK GDB server is running for session '{session_name}' on port {launch_port}."
                    if not used_fallback_port
                    else f"ST-LINK GDB server is running for session '{session_name}' on fallback port {launch_port}."
                ),
            }
        time.sleep(0.2)

    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    output_handle.close()
    return {
        "success": False,
        "implemented": True,
        "server": "debug",
        "operation": "launch",
        "session_name": session_name,
        "command": command,
        "console_log": str(console_log_path),
        "server_log": str(server_log_path),
        "console_log_tail": read_log_tail(console_log_path),
        "server_log_tail": read_log_tail(server_log_path),
        "message": f"ST-LINK GDB server did not become ready on port {launch_port} within {timeout_seconds} seconds.",
    }


@mcp.tool(description="Report the current lifecycle state of a managed ST-LINK GDB server session.")
def stm32_debug_status(session_name: str = "default") -> dict[str, object]:
    session = ACTIVE_DEBUG_SESSIONS.get(session_name)
    if session is None:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "status",
            "session_name": session_name,
            "message": f"Debug session '{session_name}' is not running.",
        }

    return {
        "success": True,
        "implemented": True,
        "server": "debug",
        "operation": "status",
        "session_name": session_name,
        "session": active_session_summary(session),
    }


@mcp.tool(description="List all managed ST-LINK GDB server sessions currently known to the MCP process.")
def stm32_debug_sessions() -> dict[str, object]:
    return {
        "success": True,
        "implemented": True,
        "server": "debug",
        "operation": "sessions",
        "sessions": [active_session_summary(session) for session in ACTIVE_DEBUG_SESSIONS.values()],
    }


@mcp.tool(description="Run one-shot ARM GDB commands against a managed ST-LINK GDB server session and return the batch transcript.")
def stm32_debug_run_gdb_commands(
    session_name: str = "default",
    commands: list[str] | None = None,
    timeout_seconds: int = 20,
) -> dict[str, object]:
    session = ACTIVE_DEBUG_SESSIONS.get(session_name)
    if session is None:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "gdb_batch",
            "session_name": session_name,
            "message": f"Debug session '{session_name}' is not running.",
        }

    return run_gdb_batch(session=session, commands=commands or ["info registers"], timeout_seconds=timeout_seconds)


@mcp.tool(description="Inspect a live peripheral or a specific register directly on the attached STM32 target using SVD metadata plus a managed debug session.")
def stm32_debug_inspect_peripheral(
    session_name: str = "default",
    peripheral: str = "USART1",
    register: str | None = None,
    timeout_seconds: int = 20,
) -> dict[str, object]:
    session = ACTIVE_DEBUG_SESSIONS.get(session_name)
    if session is None:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "inspect_peripheral",
            "session_name": session_name,
            "peripheral": peripheral,
            "message": f"Debug session '{session_name}' is not running.",
        }

    try:
        return inspect_peripheral_registers_from_svd(
            session=session,
            peripheral_name=peripheral,
            register_name=register,
            timeout_seconds=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "inspect_peripheral",
            "session_name": session_name,
            "peripheral": peripheral,
            "message": str(exc),
        }


@mcp.tool(description="Answer a natural-language peripheral or register question by inspecting live target state through the managed debug session.")
def stm32_debug_answer_question(
    question: str,
    session_name: str = "default",
    timeout_seconds: int = 20,
) -> dict[str, object]:
    lowered = question.strip().lower()
    peripheral_match = re.search(r"\b(usart\d+|uart\d+|spi\d+|i2c\d+|tim\d+|adc\d+|dac\d+|gpio[a-k]|rcc)\b", lowered)
    peripheral = peripheral_match.group(1).upper() if peripheral_match else None
    if peripheral is not None:
        peripheral = normalize_uart_peripheral_name(peripheral)

    if peripheral and "baud" in lowered:
        result = stm32_debug_uart_configuration(session_name=session_name, peripheral=peripheral, timeout_seconds=timeout_seconds)
        result.update(
            {
                "operation": "answer_question",
                "question": question,
                "answer": result.get("message"),
            }
        )
        return result

    if peripheral:
        register_match = re.search(r"\b(cr1|cr2|cr3|brr|isr|rdr|tdr|sr|dr|cfgr|ccipr|pllcfgr)\b", lowered)
        register = register_match.group(1).upper() if register_match else None
        result = stm32_debug_inspect_peripheral(
            session_name=session_name,
            peripheral=peripheral,
            register=register,
            timeout_seconds=timeout_seconds,
        )
        if result.get("success"):
            registers = result.get("registers") if isinstance(result.get("registers"), dict) else {}
            semantic_answer = answer_semantic_peripheral_question(question, peripheral, registers)
            if semantic_answer is not None:
                result.update(
                    {
                        "operation": "answer_question",
                        "question": question,
                        "answer": semantic_answer.get("answer"),
                        "matches": semantic_answer.get("matches"),
                    }
                )
                return result
            result.update(
                {
                    "operation": "answer_question",
                    "question": question,
                    "answer": f"Read live {peripheral}{'.' + register if register else ''} state from the target.",
                }
            )
        return result

    return {
        "success": False,
        "implemented": True,
        "server": "debug",
        "operation": "answer_question",
        "question": question,
        "message": "The question did not identify a peripheral or register I can inspect yet. Mention a peripheral such as USART1, SPI1, I2C1, GPIOA, TIM2, ADC1, or RCC.",
    }


@mcp.tool(description="Stop a managed ST-LINK GDB server session and return its final logs and exit code.")
def stm32_debug_stop(session_name: str = "default", force: bool = False, timeout_seconds: int = 10) -> dict[str, object]:
    session = ACTIVE_DEBUG_SESSIONS.get(session_name)
    if session is None:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "stop",
            "session_name": session_name,
            "message": f"Debug session '{session_name}' is not running.",
        }

    if session.process.poll() is None:
        if force:
            session.process.kill()
        else:
            session.process.terminate()
        try:
            session.process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            session.process.kill()
            session.process.wait(timeout=timeout_seconds)

    session_summary = active_session_summary(session)
    session.output_handle.close()
    ACTIVE_DEBUG_SESSIONS.pop(session_name, None)
    return {
        "success": True,
        "implemented": True,
        "server": "debug",
        "operation": "stop",
        "session_name": session_name,
        "session": session_summary,
        "message": f"Debug session '{session_name}' has been stopped.",
    }


@mcp.tool(description="Capture a structured runtime snapshot through an ARM GDB client attached to a managed ST-LINK GDB server session.")
def stm32_debug_snapshot(
    snapshot_name: str = "current",
    session_name: str = "default",
    stack_words: int = 16,
    timeout_seconds: int = 20,
) -> dict[str, object]:
    session = ACTIVE_DEBUG_SESSIONS.get(session_name)
    if session is None:
        return {
            "success": False,
            "implemented": True,
            "server": "debug",
            "operation": "snapshot",
            "snapshot_name": snapshot_name,
            "session_name": session_name,
            "elf_path": resolve_debug_elf_path(),
            "session": None,
            "message": f"Debug session '{session_name}' is not running.",
        }

    batch_result = run_gdb_batch(
        session=session,
        commands=[
            "echo === REGISTERS ===\\n",
            "info registers",
            "echo === BACKTRACE ===\\n",
            "bt",
            "echo === STACK ===\\n",
            f"x/{max(stack_words, 1)}wx $sp",
        ],
        timeout_seconds=timeout_seconds,
    )
    if not batch_result.get("success"):
        batch_result.update(
            {
                "operation": "snapshot",
                "snapshot_name": snapshot_name,
                "session": active_session_summary(session),
            }
        )
        return batch_result

    stdout = str(batch_result.get("stdout", ""))
    return {
        "success": True,
        "implemented": True,
        "server": "debug",
        "operation": "snapshot",
        "snapshot_name": snapshot_name,
        "session_name": session_name,
        "elf_path": batch_result.get("elf_path"),
        "gdb_path": batch_result.get("gdb_path"),
        "session": active_session_summary(session),
        "registers": parse_register_output(stdout),
        "backtrace": parse_section_lines(stdout, "BACKTRACE"),
        "stack": parse_section_lines(stdout, "STACK"),
        "transcript": stdout,
        "message": f"Collected snapshot '{snapshot_name}' from debug session '{session_name}'.",
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()