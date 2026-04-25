from __future__ import annotations

import re

from .ioc_model import IocModel

NUMBERED_KEY_PATTERN = re.compile(r"^(?P<prefix>Mcu\.(?:IP|Pin))(?P<index>\d+)$")


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


def upsert_property(lines: list[str], key: str, value: object) -> str:
    rendered = f"{key}={value}"
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        existing_key, _, existing_value = stripped.partition("=")
        if existing_key.strip() != key:
            continue
        if existing_value.strip() == str(value):
            return "unchanged"
        lines[index] = rendered
        return "updated"
    lines.append(rendered)
    return "added"


def synthesize_change_set_from_model(model: IocModel) -> dict[str, object]:
    ioc_properties: list[dict[str, object]] = [
        {"key": "Mcu.Name", "value": model.target_mcu},
        {"key": "ProjectManager.ToolChain", "value": model.toolchain},
        {"key": "ProjectManager.TargetToolchain", "value": model.toolchain},
        {"key": "ProjectManager.ToolChainLocation", "value": "Projects"},
        {"key": "ProjectManager.MainLocation", "value": "Src"},
        {"key": "ProjectManager.ProjectStructure", "value": ""},
        {"key": "ProjectManager.UnderRoot", "value": "false"},
    ]
    for binding in model.bindings:
        labels = binding.get("labels", {})
        signals = binding.get("signals", {})
        modes = binding.get("modes", {})
        if isinstance(signals, dict):
            for pin_name, signal in signals.items():
                if pin_name in labels:
                    ioc_properties.append({"key": f"{pin_name}.GPIOParameters", "value": "GPIO_Label"})
                    ioc_properties.append({"key": f"{pin_name}.GPIO_Label", "value": labels[pin_name]})
                ioc_properties.append({"key": f"{pin_name}.Signal", "value": signal})
                if pin_name in modes:
                    ioc_properties.append({"key": f"{pin_name}.Mode", "value": modes[pin_name]})

        instance = binding.get("instance")
        peripheral_properties = binding.get("peripheral_properties", {})
        if isinstance(instance, str) and isinstance(peripheral_properties, dict):
            for property_name, property_value in peripheral_properties.items():
                ioc_properties.append({"key": f"{instance}.{property_name}", "value": property_value})

        shared_properties = binding.get("shared_properties", {})
        if isinstance(shared_properties, dict):
            for property_name, property_value in shared_properties.items():
                ioc_properties.append({"key": property_name, "value": property_value})

    return {
        "enabled_peripherals": sorted(dict.fromkeys(model.required_peripherals)),
        "used_pins": sorted(dict.fromkeys(model.used_pins)),
        "ioc_properties": ioc_properties,
        "codegen_hints": list(model.codegen_hints),
    }