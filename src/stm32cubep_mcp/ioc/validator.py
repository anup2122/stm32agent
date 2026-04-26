from __future__ import annotations

import tempfile
from pathlib import Path

from ..cubemx import server as cubemx_server
from ..ioc_builder.ioc_model import IocModel
from .mutator import collect_numbered_values, parse_ioc_properties_from_lines


def _signal_supported_on_pin(pin_capabilities: dict[str, object], pin_name: str, signal_name: str) -> bool:
    supported_signals = pin_capabilities.get(pin_name, [])
    if not isinstance(supported_signals, list):
        return False
    normalized_supported_signals = {
        candidate
        for candidate in supported_signals
        if isinstance(candidate, str) and candidate.strip()
    }
    if signal_name in normalized_supported_signals:
        return True
    if signal_name.startswith("S_") and signal_name[2:] in normalized_supported_signals:
        return True
    return False


def validate_ioc_model(model: IocModel, mcu_metadata: dict[str, object]) -> list[str]:
    errors: list[str] = list(model.compile_errors)
    peripherals = mcu_metadata.get("peripherals", {}) if isinstance(mcu_metadata.get("peripherals"), dict) else {}
    pin_capabilities = mcu_metadata.get("pin_capabilities", {}) if isinstance(mcu_metadata.get("pin_capabilities"), dict) else {}

    for peripheral in model.required_peripherals:
        if peripheral not in peripherals:
            errors.append(f"Peripheral '{peripheral}' is not supported by the current MCU metadata.")

    if len(model.used_pins) != len(set(model.used_pins)):
        errors.append("used_pins contains duplicate entries.")

    for binding in model.bindings:
        signals = binding.get("signals", {})
        if not isinstance(signals, dict):
            continue
        for pin_name, signal_name in signals.items():
            if not _signal_supported_on_pin(pin_capabilities, pin_name, signal_name):
                errors.append(f"Signal '{signal_name}' is not supported on pin '{pin_name}'.")

    return errors


def validate_ioc_lines(lines: list[str], model: IocModel) -> list[str]:
    errors: list[str] = []
    properties = parse_ioc_properties_from_lines(lines)

    if not properties.get("Mcu.Name"):
        errors.append("Mcu.Name is required.")
    if not properties.get("ProjectManager.ToolChain"):
        errors.append("ProjectManager.ToolChain is required.")
    if not properties.get("ProjectManager.TargetToolchain"):
        errors.append("ProjectManager.TargetToolchain is required.")

    recorded_pins = collect_numbered_values(properties, "Mcu.Pin")
    recorded_peripherals = collect_numbered_values(properties, "Mcu.IP")
    for pin_name in model.used_pins:
        if pin_name not in recorded_pins:
            errors.append(f"Pin '{pin_name}' is missing from the numbered Mcu.Pin list.")
        if f"{pin_name}.Signal" not in properties:
            errors.append(f"Signal assignment for pin '{pin_name}' is missing.")
    for peripheral in model.required_peripherals:
        if peripheral not in recorded_peripherals:
            errors.append(f"Peripheral '{peripheral}' is missing from the numbered Mcu.IP list.")

    return errors


def validate_ioc_with_cubemx(ioc_path: str, project_name: str, project_toolchain: str) -> dict[str, object]:
    try:
        resolved_ioc_path = Path(ioc_path).resolve()
        launcher = cubemx_server.resolve_cubemx_launcher()
    except FileNotFoundError as exc:
        return {
            "success": True,
            "validation": "skipped",
            "message": str(exc),
        }

    configured_inputs = cubemx_server.resolve_cubemx_project_inputs(
        ioc_path=str(resolved_ioc_path),
        project_name=project_name,
        project_toolchain=project_toolchain,
    )
    configured_project_path = configured_inputs.get("project_path") if isinstance(configured_inputs.get("project_path"), str) else None
    configured_script_path = configured_inputs.get("script_path") if isinstance(configured_inputs.get("script_path"), str) else None

    if configured_project_path and configured_script_path:
        result = cubemx_server.regenerate_project_internal(
            ioc_path=str(resolved_ioc_path),
            project_name=project_name,
            project_toolchain=project_toolchain,
            project_path=configured_project_path,
            script_path=configured_script_path,
            validate_build=False,
            timeout_seconds=180,
            build_timeout_seconds=60,
        )
        return {
            "success": bool(result.get("success")),
            "validation": "accepted" if result.get("success") else "rejected",
            "message": str(result.get("message") or "CubeMX acceptance validation completed."),
            "tool_path": launcher.get("tool_path"),
            "launch_kind": launcher.get("launch_kind"),
            "cubemx_result": result,
        }

    with tempfile.TemporaryDirectory(prefix="stm32cubep-cubemx-validate-") as temp_dir:
        temp_root = Path(temp_dir)
        generation_root = temp_root / "generated-project"
        project_path = generation_root / project_name
        script_path = temp_root / "validate.ioc.script.txt"
        result = cubemx_server.regenerate_project_internal(
            ioc_path=str(resolved_ioc_path),
            project_name=project_name,
            project_toolchain=project_toolchain,
            project_path=str(project_path),
            script_path=str(script_path),
            validate_build=False,
            timeout_seconds=180,
            build_timeout_seconds=60,
        )

    return {
        "success": bool(result.get("success")),
        "validation": "accepted" if result.get("success") else "rejected",
        "message": str(result.get("message") or "CubeMX acceptance validation completed."),
        "tool_path": launcher.get("tool_path"),
        "launch_kind": launcher.get("launch_kind"),
        "cubemx_result": result,
    }
