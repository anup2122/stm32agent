from __future__ import annotations

import re

from .operation_ir import IocOperation

NUMBERED_KEY_PATTERN = re.compile(r"^(?P<prefix>Mcu\.(?:IP|Pin))(?P<index>\d+)$")
MERGED_PROPERTY_KEYS = ("IPParameters", "IPParametersWithoutCheck")


def parse_ioc_properties_from_lines(lines: list[str]) -> dict[str, str]:
    properties: dict[str, str] = {}
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip():
            properties[key.strip()] = value.strip()
    return properties


def collect_numbered_values(properties: dict[str, str], prefix: str) -> list[str]:
    indexed_values: list[tuple[int, str]] = []
    for key, value in properties.items():
        match = NUMBERED_KEY_PATTERN.match(key)
        if match and match.group("prefix") == prefix and value:
            indexed_values.append((int(match.group("index")), value))
    return [value for _, value in sorted(indexed_values)]


def merge_csv_property(existing: str, additions: str) -> str:
    merged: list[str] = []
    for raw_value in [existing, additions]:
        for item in raw_value.split(","):
            candidate = item.strip()
            if candidate and candidate not in merged:
                merged.append(candidate)
    return ",".join(merged)


def upsert_property(lines: list[str], key: str, value: object) -> str:
    rendered_value = str(value)
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        existing_key, _, existing_value = stripped.partition("=")
        if existing_key.strip() != key:
            continue
        if key.endswith(MERGED_PROPERTY_KEYS):
            rendered_value = merge_csv_property(existing_value.strip(), rendered_value)
        if existing_value.strip() == rendered_value:
            return "unchanged"
        lines[index] = f"{key}={rendered_value}"
        return "updated"
    lines.append(f"{key}={rendered_value}")
    return "added"


def legacy_ioc_properties_from_operations(operations: list[dict[str, object]] | list[IocOperation]) -> list[dict[str, object]]:
    properties: list[dict[str, object]] = []
    for raw_operation in operations:
        operation = raw_operation if isinstance(raw_operation, IocOperation) else IocOperation.from_dict(raw_operation)
        if operation.kind != "set_property":
            continue
        key = operation.target.get("key")
        if not isinstance(key, str) or not key.strip():
            continue
        properties.append({"key": key, "value": operation.value})
    return properties


def apply_project_manager_defaults(lines: list[str], *, project_name: str, toolchain: str, target_mcu: str) -> None:
    project_manager_defaults: list[tuple[str, object]] = [
        ("ProjectManager.ProjectName", project_name),
        ("ProjectManager.ProjectFileName", f"{project_name}.ioc"),
        ("ProjectManager.DeviceId", target_mcu),
        ("ProjectManager.ToolChain", toolchain),
        ("ProjectManager.TargetToolchain", toolchain),
        ("ProjectManager.KeepUserCode", "true"),
        ("ProjectManager.DeletePrevious", "true"),
    ]
    for key, value in project_manager_defaults:
        upsert_property(lines, key, value)
    lines[:] = [line for line in lines if not line.startswith("ProjectManager.ToolChainLocation=")]


def apply_ioc_operations(lines: list[str], operations: list[dict[str, object]] | list[IocOperation]) -> dict[str, object]:
    properties = parse_ioc_properties_from_lines(lines)
    existing_peripherals = collect_numbered_values(properties, "Mcu.IP")
    merged_peripherals = existing_peripherals[:]
    existing_pins = collect_numbered_values(properties, "Mcu.Pin")
    merged_pins = existing_pins[:]

    changed_keys: list[str] = []
    unchanged_keys: list[str] = []
    unsupported_operations: list[dict[str, object]] = []

    for raw_operation in operations:
        operation = raw_operation if isinstance(raw_operation, IocOperation) else IocOperation.from_dict(raw_operation)
        if operation.kind == "set_property":
            key = operation.target.get("key")
            if not isinstance(key, str) or not key.strip():
                unsupported_operations.append(operation.to_dict())
                continue
            outcome = upsert_property(lines, key, operation.value)
            if outcome == "unchanged":
                unchanged_keys.append(key)
            else:
                changed_keys.append(key)
            continue
        if operation.kind == "ensure_peripheral_enabled":
            peripheral = operation.target.get("peripheral") or operation.value
            if isinstance(peripheral, str) and peripheral not in merged_peripherals:
                merged_peripherals.append(peripheral)
            continue
        if operation.kind == "ensure_pin_used":
            pin_name = operation.target.get("pin") or operation.value
            if isinstance(pin_name, str) and pin_name not in merged_pins:
                merged_pins.append(pin_name)
            continue
        unsupported_operations.append(operation.to_dict())

    if unsupported_operations:
        raise ValueError(f"Unsupported IOC operations were provided: {unsupported_operations}")

    for index, peripheral in enumerate(merged_peripherals):
        upsert_property(lines, f"Mcu.IP{index}", peripheral)
    upsert_property(lines, "Mcu.IPNb", len(merged_peripherals))

    for index, pin_name in enumerate(merged_pins):
        upsert_property(lines, f"Mcu.Pin{index}", pin_name)
    upsert_property(lines, "Mcu.PinsNb", len(merged_pins))

    return {
        "changed_keys": changed_keys,
        "unchanged_keys": unchanged_keys,
        "enabled_peripherals": merged_peripherals,
        "used_pins": merged_pins,
    }
