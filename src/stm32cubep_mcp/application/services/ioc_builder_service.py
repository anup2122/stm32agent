"""IOC builder application services.

These functions are the application-layer bridge between a validated feature
contract and the concrete IOC file mutations that CubeMX can consume later.

Exact ``apply_ioc_change_set()`` chain:

1. ``synthesize_ioc_change_set_fn(contract)`` produces a deterministic IOC plan.
2. ``resolve_ioc_path_fn(ioc_path)`` resolves the target IOC file.
3. The IOC file is loaded into ``lines``.
4. ``_apply_plan_operations(...)`` converts the synthesized plan into concrete
    IOC operations and calls ``apply_ioc_operations_fn(...)``.
5. The mutated IOC content is written back to disk.
6. ``validate_ioc_with_cubemx_fn(...)`` checks whether CubeMX accepts the
    resulting IOC according to the execution policy.

Exact ``construct_ioc_file()`` chain:

1. ``synthesize_ioc_change_set_fn(contract)`` produces the deterministic plan.
2. ``resolve_ioc_path_fn(ioc_path)`` resolves where the managed IOC file should
    be created.
3. ``load_base_ioc_lines_fn(...)`` fetches the starting IOC text, either from a
    copied existing IOC, an official board baseline, or another configured base.
4. ``apply_project_manager_defaults_fn(...)`` injects project/toolchain/MCU
    defaults into the base IOC.
5. ``_apply_plan_operations(...)`` mutates the IOC text with the synthesized
    operations.
6. ``validate_ioc_lines_fn(...)`` performs structural validation before write.
7. The managed IOC file is written to disk.
8. ``validate_ioc_with_cubemx_fn(...)`` performs CubeMX acceptance validation.

Both paths return a rich result payload containing changed keys, used pins,
enabled peripherals, the synthesized plan, and the CubeMX validation result so
the calling workflow can decide whether to continue into regeneration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def _operations_from_plan(plan: dict[str, object]) -> list[dict[str, object]]:
    operations = plan.get("operations")
    if isinstance(operations, list):
        return operations

    synthesized_operations: list[dict[str, object]] = []
    for peripheral in plan.get("enabled_peripherals", []):
        if isinstance(peripheral, str):
            synthesized_operations.append(
                {
                    "op_id": f"ensure-peripheral-{peripheral.lower()}",
                    "kind": "ensure_peripheral_enabled",
                    "target": {"peripheral": peripheral},
                    "value": peripheral,
                }
            )
    for pin_name in plan.get("used_pins", []):
        if isinstance(pin_name, str):
            synthesized_operations.append(
                {
                    "op_id": f"ensure-pin-{pin_name.lower()}",
                    "kind": "ensure_pin_used",
                    "target": {"pin": pin_name},
                    "value": pin_name,
                }
            )
    for property_entry in plan.get("ioc_properties", []):
        if not isinstance(property_entry, dict):
            continue
        key = property_entry.get("key")
        if not isinstance(key, str) or not key.strip():
            continue
        synthesized_operations.append(
            {
                "op_id": f"set-property-{len(synthesized_operations)}",
                "kind": "set_property",
                "target": {"key": key},
                "value": property_entry.get("value"),
            }
        )
    return synthesized_operations


def _apply_plan_operations(
    lines: list[str],
    plan: dict[str, object],
    *,
    apply_ioc_operations_fn: Callable[[list[str], list[dict[str, object]]], dict[str, object]],
) -> dict[str, object]:
    return apply_ioc_operations_fn(lines, _operations_from_plan(plan))


def collect_ioc_builder_capabilities(
    *,
    supported_board_profiles: list[str],
    supported_contract_version: str,
    notes: list[str],
) -> dict[str, object]:
    return {
        "server": "ioc_builder",
        "implemented": True,
        "supported_board_profiles": supported_board_profiles,
        "supported_contract_version": supported_contract_version,
        "notes": notes,
    }


def compile_ioc_plan(
    *,
    contract: dict[str, object],
    compile_contract_to_ioc_plan_fn: Callable[[dict[str, object]], dict[str, object]],
) -> dict[str, object]:
    return compile_contract_to_ioc_plan_fn(contract)


def apply_ioc_change_set(
    *,
    contract: dict[str, object],
    ioc_path: str | None,
    synthesize_ioc_change_set_fn: Callable[[dict[str, object]], dict[str, object]],
    resolve_ioc_path_fn: Callable[[str | None], Path | None],
    apply_ioc_operations_fn: Callable[[list[str], list[dict[str, object]]], dict[str, object]],
    validate_ioc_with_cubemx_fn: Callable[[str, str, str], dict[str, object]],
    default_toolchain: str,
) -> dict[str, object]:
    synthesized = synthesize_ioc_change_set_fn(contract)
    if not synthesized.get("success"):
        return synthesized

    resolved_ioc_path = resolve_ioc_path_fn(ioc_path)
    if resolved_ioc_path is None:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "No IOC path was available to apply the synthesized change set.",
            "validation_errors": [],
        }
    if not resolved_ioc_path.is_file():
        return {
            "server": "ioc_builder",
            "success": False,
            "message": f"The IOC file was not found: {resolved_ioc_path}",
            "validation_errors": [],
        }

    lines = resolved_ioc_path.read_text(encoding="utf-8", errors="replace").splitlines()
    try:
        applied = _apply_plan_operations(
            lines,
            synthesized,
            apply_ioc_operations_fn=apply_ioc_operations_fn,
        )
    except ValueError as exc:
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "plan": synthesized,
            "message": str(exc),
            "validation_errors": [],
        }

    resolved_ioc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    validation_policy = str(contract.get("execution_policy", {}).get("ioc_cubemx_validation") or "best_effort")
    cubemx_validation = validate_ioc_with_cubemx_fn(
        str(resolved_ioc_path),
        project_name=resolved_ioc_path.stem,
        project_toolchain=str(contract.get("defaults", {}).get("toolchain") or default_toolchain),
    )
    validation_required_and_skipped = validation_policy == "required" and cubemx_validation.get("validation") == "skipped"
    if not cubemx_validation.get("success") or validation_required_and_skipped:
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "changed_keys": applied["changed_keys"],
            "unchanged_keys": applied["unchanged_keys"],
            "enabled_peripherals": applied["enabled_peripherals"],
            "used_pins": applied["used_pins"],
            "plan": synthesized,
            "cubemx_validation": cubemx_validation,
            "message": (
                "The synthesized IOC change set was written, but CubeMX validation was required and unavailable on this host."
                if validation_required_and_skipped
                else "The synthesized IOC change set was written, but CubeMX rejected the resulting IOC file."
            ),
        }
    return {
        "server": "ioc_builder",
        "success": True,
        "ioc_path": str(resolved_ioc_path),
        "changed_keys": applied["changed_keys"],
        "unchanged_keys": applied["unchanged_keys"],
        "enabled_peripherals": applied["enabled_peripherals"],
        "used_pins": applied["used_pins"],
        "plan": synthesized,
        "cubemx_validation": cubemx_validation,
        "message": "The synthesized IOC change set was applied to the configured IOC file.",
    }


def construct_ioc_file(
    *,
    contract: dict[str, object],
    ioc_path: str | None,
    overwrite: bool,
    source_ioc_path: str | None,
    synthesize_ioc_change_set_fn: Callable[[dict[str, object]], dict[str, object]],
    resolve_ioc_path_fn: Callable[[str | None], Path | None],
    load_base_ioc_lines_fn: Callable[..., dict[str, object]],
    apply_project_manager_defaults_fn: Callable[[list[str], str, str, str], None],
    apply_ioc_operations_fn: Callable[[list[str], list[dict[str, object]]], dict[str, object]],
    validate_ioc_lines_fn: Callable[[list[str], dict[str, object]], list[str]],
    validate_ioc_with_cubemx_fn: Callable[[str, str, str], dict[str, object]],
    default_toolchain: str,
) -> dict[str, object]:
    synthesized = synthesize_ioc_change_set_fn(contract)
    if not synthesized.get("success"):
        return synthesized

    resolved_ioc_path = resolve_ioc_path_fn(ioc_path)
    if resolved_ioc_path is None:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "No IOC path was available to construct the IOC file.",
            "validation_errors": [],
        }
    if resolved_ioc_path.exists() and not overwrite:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": f"The IOC file already exists: {resolved_ioc_path}",
            "validation_errors": [],
        }

    base_ioc = load_base_ioc_lines_fn(contract, source_ioc_path=source_ioc_path)
    if not base_ioc.get("success"):
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "message": str(base_ioc.get("message") or "No base IOC file could be prepared."),
            "validation_errors": [],
            "base_ioc": base_ioc,
        }

    toolchain = str(contract.get("defaults", {}).get("toolchain") or default_toolchain)
    target = contract["target"]
    lines = list(base_ioc.get("lines", [])) if isinstance(base_ioc.get("lines"), list) else []
    if not lines:
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "message": "The prepared base IOC did not contain any lines to mutate.",
            "validation_errors": [],
            "base_ioc": base_ioc,
        }

    construction_source = str(base_ioc.get("construction_source") or "unknown")
    project_name = resolved_ioc_path.stem
    apply_project_manager_defaults_fn(lines, project_name, toolchain, str(target["mcu"]))
    try:
        applied = _apply_plan_operations(
            lines,
            synthesized,
            apply_ioc_operations_fn=apply_ioc_operations_fn,
        )
    except ValueError as exc:
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "message": str(exc),
            "validation_errors": [],
            "plan": synthesized,
            "base_ioc": base_ioc,
        }

    validation_errors = validate_ioc_lines_fn(lines, contract)
    if validation_errors:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "The constructed IOC file failed structural validation.",
            "validation_errors": validation_errors,
            "plan": synthesized,
            "base_ioc": base_ioc,
        }

    resolved_ioc_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_ioc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    validation_policy = str(contract.get("execution_policy", {}).get("ioc_cubemx_validation") or "best_effort")
    cubemx_validation = validate_ioc_with_cubemx_fn(
        str(resolved_ioc_path),
        project_name=resolved_ioc_path.stem,
        project_toolchain=toolchain,
    )
    validation_required_and_skipped = validation_policy == "required" and cubemx_validation.get("validation") == "skipped"
    if not cubemx_validation.get("success") or validation_required_and_skipped:
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "changed_keys": applied["changed_keys"],
            "unchanged_keys": applied["unchanged_keys"],
            "enabled_peripherals": applied["enabled_peripherals"],
            "used_pins": applied["used_pins"],
            "plan": synthesized,
            "cubemx_validation": cubemx_validation,
            "base_ioc": base_ioc,
            "message": (
                "The IOC file was constructed, but CubeMX validation was required and unavailable on this host."
                if validation_required_and_skipped
                else "The IOC file was constructed, but CubeMX rejected the resulting IOC file."
            ),
        }
    return {
        "server": "ioc_builder",
        "success": True,
        "ioc_path": str(resolved_ioc_path),
        "changed_keys": applied["changed_keys"],
        "unchanged_keys": applied["unchanged_keys"],
        "enabled_peripherals": applied["enabled_peripherals"],
        "used_pins": applied["used_pins"],
        "plan": synthesized,
        "construction_source": construction_source,
        "base_ioc": base_ioc,
        "cubemx_validation": cubemx_validation,
        "message": (
            "The IOC file was materialized from an official local STM32CubeMX board baseline and deterministic change set."
            if construction_source == "local_board_ioc"
            else "The IOC file was materialized from the STM32_open_pin_data GitHub board template and deterministic change set."
            if construction_source == "github_board_ioc"
            else "The IOC file was materialized from an existing project IOC copy and deterministic change set."
        ),
    }
