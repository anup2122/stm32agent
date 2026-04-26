from __future__ import annotations

import re
from pathlib import Path


IOC_SIGNAL_KEY_PATTERN = re.compile(r"^(P[A-Z]\d+(?:-[A-Z0-9_]+)?)\.Signal$")
IOC_GPIO_LABEL_KEY_PATTERN = re.compile(r"^(P[A-Z]\d+(?:-[A-Z0-9_]+)?)\.GPIO_Label$")


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
