from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .. import shared
from ..requirements_ioc_contract import CONTRACT_VERSION, DEFAULT_TOOLCHAIN, validate_contract
from .ioc_construct import construct_initial_ioc_lines
from .ioc_model import build_ioc_model
from .ioc_mutate import collect_numbered_values, parse_ioc_properties_from_lines, synthesize_change_set_from_model, upsert_property
from .ioc_validate import validate_ioc_lines, validate_ioc_model, validate_ioc_with_cubemx
from .st_mcu_catalog import resolve_mcu_metadata
from .st_seed_catalog import get_board_profile

mcp = FastMCP("stm32iocbuilder")


def load_firmware_metadata() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    firmware = project_data.get("firmware", {}) if isinstance(project_data, dict) else {}
    return firmware if isinstance(firmware, dict) else {}


def resolve_ioc_path(ioc_path: str | None = None) -> Path | None:
    candidate = ioc_path
    if not isinstance(candidate, str) or not candidate.strip():
        firmware = load_firmware_metadata()
        configured = firmware.get("ioc_path")
        candidate = configured if isinstance(configured, str) else None
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    path = Path(candidate).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def parse_ioc_lines(ioc_path: Path) -> list[str]:
    return ioc_path.read_text(encoding="utf-8", errors="replace").splitlines()


def synthesize_ioc_change_set(contract: dict[str, object]) -> dict[str, object]:
    validation_errors = validate_contract(contract)
    if validation_errors:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "The requirements-to-IOC contract is invalid.",
            "validation_errors": validation_errors,
        }

    target = contract["target"]
    board_id = str(target["board_id"])
    board_profile = get_board_profile(board_id)
    if board_profile is None:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": f"Board profile '{board_id}' is not supported by the IOC Synthesis Agent yet.",
            "validation_errors": [],
        }

    mcu_metadata = resolve_mcu_metadata(board_id, str(target["mcu"]))
    if mcu_metadata is None:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": f"MCU metadata for board '{board_id}' is not supported by the IOC Builder yet.",
            "validation_errors": [],
        }

    model = build_ioc_model(contract, board_profile, mcu_metadata)
    model_errors = validate_ioc_model(model, mcu_metadata)
    if model_errors:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "The canonical IOC model is invalid for the selected board and MCU metadata.",
            "validation_errors": model_errors,
        }

    synthesized = synthesize_change_set_from_model(model)
    return {
        "server": "ioc_builder",
        "success": True,
        "builder_strategy": "seed_plus_mutate",
        "board_profile": board_id,
        "seed_selection": {
            "board_id": board_id,
            "source": "embedded_official_board_seed",
        },
        "mcu_metadata": {
            "requested_mcu": mcu_metadata.get("requested_mcu"),
            "grouped_mcu_name": mcu_metadata.get("grouped_mcu_name"),
            "grouped_xml_filename": mcu_metadata.get("grouped_xml_filename"),
        },
        "ioc_model": model.to_summary(),
        "current_increment": contract["current_increment"],
        "enabled_peripherals": synthesized["enabled_peripherals"],
        "used_pins": synthesized["used_pins"],
        "ioc_properties": synthesized["ioc_properties"],
        "codegen_hints": synthesized["codegen_hints"],
        "message": "The IOC change set was synthesized deterministically from the requirements contract.",
    }


def apply_ioc_change_set(contract: dict[str, object], ioc_path: str | None = None) -> dict[str, object]:
    synthesized = synthesize_ioc_change_set(contract)
    if not synthesized.get("success"):
        return synthesized

    resolved_ioc_path = resolve_ioc_path(ioc_path)
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

    lines = parse_ioc_lines(resolved_ioc_path)
    properties = parse_ioc_properties_from_lines(lines)

    existing_peripherals = collect_numbered_values(properties, "Mcu.IP")
    merged_peripherals = existing_peripherals[:]
    for peripheral in synthesized.get("enabled_peripherals", []):
        if isinstance(peripheral, str) and peripheral not in merged_peripherals:
            merged_peripherals.append(peripheral)

    existing_pins = collect_numbered_values(properties, "Mcu.Pin")
    merged_pins = existing_pins[:]
    for pin_name in synthesized.get("used_pins", []):
        if isinstance(pin_name, str) and pin_name not in merged_pins:
            merged_pins.append(pin_name)

    changed_keys: list[str] = []
    unchanged_keys: list[str] = []
    for property_entry in synthesized["ioc_properties"]:
        key = str(property_entry["key"])
        outcome = upsert_property(lines, key, property_entry["value"])
        if outcome == "unchanged":
            unchanged_keys.append(key)
        else:
            changed_keys.append(key)

    for index, peripheral in enumerate(merged_peripherals):
        upsert_property(lines, f"Mcu.IP{index}", peripheral)
    upsert_property(lines, "Mcu.IPNb", len(merged_peripherals))

    for index, pin_name in enumerate(merged_pins):
        upsert_property(lines, f"Mcu.Pin{index}", pin_name)
    upsert_property(lines, "Mcu.PinsNb", len(merged_pins))

    resolved_ioc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    validation_policy = str(contract.get("execution_policy", {}).get("ioc_cubemx_validation") or "best_effort")
    cubemx_validation = validate_ioc_with_cubemx(
        str(resolved_ioc_path),
        project_name=resolved_ioc_path.stem,
        project_toolchain=str(contract["defaults"].get("toolchain") or DEFAULT_TOOLCHAIN),
    )
    validation_required_and_skipped = validation_policy == "required" and cubemx_validation.get("validation") == "skipped"
    if not cubemx_validation.get("success") or validation_required_and_skipped:
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "changed_keys": changed_keys,
            "unchanged_keys": unchanged_keys,
            "enabled_peripherals": merged_peripherals,
            "used_pins": merged_pins,
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
        "changed_keys": changed_keys,
        "unchanged_keys": unchanged_keys,
        "enabled_peripherals": merged_peripherals,
        "used_pins": merged_pins,
        "plan": synthesized,
        "cubemx_validation": cubemx_validation,
        "message": "The synthesized IOC change set was applied to the configured IOC file.",
    }


def construct_ioc_file(contract: dict[str, object], ioc_path: str | None = None, overwrite: bool = False) -> dict[str, object]:
    synthesized = synthesize_ioc_change_set(contract)
    if not synthesized.get("success"):
        return synthesized

    resolved_ioc_path = resolve_ioc_path(ioc_path)
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

    toolchain = str(contract["defaults"].get("toolchain") or DEFAULT_TOOLCHAIN)
    target = contract["target"]
    lines, construction_source = construct_initial_ioc_lines(str(target["board_id"]), toolchain, str(target["mcu"]))
    if lines is None:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": f"No reference IOC template or embedded seed is available for board '{target['board_id']}'.",
            "validation_errors": [],
        }

    project_name = resolved_ioc_path.stem
    project_manager_defaults: list[tuple[str, object]] = [
        ("ProjectManager.ProjectName", project_name),
        ("ProjectManager.ProjectFileName", f"{project_name}.ioc"),
        ("ProjectManager.DeviceId", str(target["mcu"])),
        ("ProjectManager.DeletePrevious", "true"),
        ("ProjectManager.KeepUserCode", "true"),
        ("ProjectManager.LibraryCopy", "0"),
        ("ProjectManager.MainLocation", "Src"),
        ("ProjectManager.NoMain", "false"),
        ("ProjectManager.ProjectBuild", "false"),
        ("ProjectManager.ProjectStructure", ""),
        ("ProjectManager.StackSize", "0x400"),
        ("ProjectManager.HeapSize", "0x200"),
        ("ProjectManager.ToolChainLocation", "Projects"),
        ("ProjectManager.UnderRoot", "false"),
        ("ProjectManager.UAScriptAfterPath", ""),
        ("ProjectManager.UAScriptBeforePath", ""),
        ("ProjectManager.RegisterCallBack", ""),
        ("ProjectManager.PreviousToolchain", ""),
    ]
    for key, value in project_manager_defaults:
        upsert_property(lines, key, value)

    properties = parse_ioc_properties_from_lines(lines)
    existing_peripherals = collect_numbered_values(properties, "Mcu.IP")
    merged_peripherals = existing_peripherals[:]
    for peripheral in synthesized.get("enabled_peripherals", []):
        if isinstance(peripheral, str) and peripheral not in merged_peripherals:
            merged_peripherals.append(peripheral)

    existing_pins = collect_numbered_values(properties, "Mcu.Pin")
    merged_pins = existing_pins[:]
    for pin_name in synthesized.get("used_pins", []):
        if isinstance(pin_name, str) and pin_name not in merged_pins:
            merged_pins.append(pin_name)

    changed_keys: list[str] = []
    unchanged_keys: list[str] = []
    for property_entry in synthesized["ioc_properties"]:
        key = str(property_entry["key"])
        outcome = upsert_property(lines, key, property_entry["value"])
        if outcome == "unchanged":
            unchanged_keys.append(key)
        else:
            changed_keys.append(key)

    for index, peripheral in enumerate(merged_peripherals):
        upsert_property(lines, f"Mcu.IP{index}", peripheral)
    upsert_property(lines, "Mcu.IPNb", len(merged_peripherals))

    for index, pin_name in enumerate(merged_pins):
        upsert_property(lines, f"Mcu.Pin{index}", pin_name)
    upsert_property(lines, "Mcu.PinsNb", len(merged_pins))

    model_summary = synthesized.get("ioc_model")
    validation_errors = []
    if isinstance(model_summary, dict):
        model = build_ioc_model(contract, get_board_profile(str(target["board_id"])) or {}, resolve_mcu_metadata(str(target["board_id"]), str(target["mcu"])) or {})
        validation_errors = validate_ioc_lines(lines, model)
    if validation_errors:
        return {
            "server": "ioc_builder",
            "success": False,
            "message": "The constructed IOC file failed structural validation.",
            "validation_errors": validation_errors,
            "plan": synthesized,
        }

    resolved_ioc_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_ioc_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    validation_policy = str(contract.get("execution_policy", {}).get("ioc_cubemx_validation") or "best_effort")
    cubemx_validation = validate_ioc_with_cubemx(
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
            "changed_keys": changed_keys,
            "unchanged_keys": unchanged_keys,
            "enabled_peripherals": merged_peripherals,
            "used_pins": merged_pins,
            "plan": synthesized,
            "cubemx_validation": cubemx_validation,
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
        "changed_keys": changed_keys,
        "unchanged_keys": unchanged_keys,
        "enabled_peripherals": merged_peripherals,
        "used_pins": merged_pins,
        "plan": synthesized,
        "construction_source": construction_source,
        "cubemx_validation": cubemx_validation,
        "message": (
            "The IOC file was constructed from the managed reference IOC template and deterministic change set."
            if construction_source == "reference_ioc"
            else "The IOC file was constructed from the embedded ST board seed and deterministic change set."
        ),
    }


def collect_ioc_builder_capabilities() -> dict[str, object]:
    return {
        "server": "ioc_builder",
        "implemented": True,
        "supported_board_profiles": ["NUCLEO-L476RG"],
        "supported_contract_version": CONTRACT_VERSION,
        "notes": [
            "The IOC Synthesis Agent is deterministic by design.",
            "Supported mappings currently include UART host console, LED blink, and user button event for NUCLEO-L476RG.",
            "Construction mode prefers a managed board reference IOC template before falling back to the embedded ST board seed.",
        ],
    }


@mcp.tool(description="Report the current deterministic IOC Synthesis Agent scope and supported board profiles.")
def stm32_ioc_builder_capabilities() -> dict[str, object]:
    return collect_ioc_builder_capabilities()


@mcp.tool(description="Convert a validated requirements contract into a deterministic IOC change set for the current feature increment.")
def stm32_ioc_builder_plan(contract: dict[str, object]) -> dict[str, object]:
    return synthesize_ioc_change_set(contract)


@mcp.tool(description="Apply a deterministic IOC change set to the configured IOC file before CubeMX regeneration.")
def stm32_ioc_builder_apply(contract: dict[str, object], ioc_path: str | None = None) -> dict[str, object]:
    return apply_ioc_change_set(contract, ioc_path=ioc_path)


@mcp.tool(description="Construct a new IOC file from a managed board reference IOC template, or fall back to an ST-derived seed, then apply the deterministic change set for the current feature increment.")
def stm32_ioc_builder_construct(contract: dict[str, object], ioc_path: str | None = None, overwrite: bool = False) -> dict[str, object]:
    return construct_ioc_file(contract, ioc_path=ioc_path, overwrite=overwrite)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()