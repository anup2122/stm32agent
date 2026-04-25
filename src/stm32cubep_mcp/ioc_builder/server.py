from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from xml.etree.ElementTree import ParseError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

from ..knowledge.cubemx_db import INDEX_VERSION as CUBEMX_DB_INDEX_VERSION
from ..knowledge.cubemx_db import build_cubemx_db_index, find_board_baseline
from .. import shared
from ..requirements_ioc_contract import CONTRACT_VERSION, DEFAULT_TOOLCHAIN, validate_contract
from .ioc_model import build_ioc_model
from .ioc_mutate import collect_numbered_values, parse_ioc_properties_from_lines, synthesize_change_set_from_model, upsert_property
from .ioc_validate import validate_ioc_lines, validate_ioc_model, validate_ioc_with_cubemx
from .st_mcu_catalog import resolve_mcu_metadata
from .st_seed_catalog import get_board_profile

mcp = FastMCP("stm32iocbuilder")

GITHUB_BOARD_INDEX_URL = "https://api.github.com/repos/STMicroelectronics/STM32_open_pin_data/contents/boards?ref=master"
GITHUB_API_ACCEPT = "application/vnd.github+json"
GITHUB_USER_AGENT = "stm32cubep-mcp"


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


def normalized_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def normalized_mcu_candidates(mcu_name: str) -> list[str]:
    normalized = normalized_identifier(mcu_name)
    candidates: list[str] = []
    for candidate in (normalized, normalized[:-1], normalized[:-2]):
        if len(candidate) >= 8 and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def cubemx_db_cache_root() -> Path:
    return (Path.cwd() / "generated" / "_cache" / "cubemx_db" / CUBEMX_DB_INDEX_VERSION).resolve()


@lru_cache(maxsize=1)
def local_cubemx_db_index() -> dict[str, object]:
    return build_cubemx_db_index(cache_root=cubemx_db_cache_root())


def load_local_board_ioc_lines(board_id: str, mcu_name: str) -> dict[str, object]:
    try:
        index = local_cubemx_db_index()
    except (FileNotFoundError, OSError, json.JSONDecodeError, ParseError) as exc:
        return {
            "success": False,
            "message": f"Unable to index the local STM32CubeMX database: {exc}",
        }

    match = find_board_baseline(index, board_id)
    if not isinstance(match, dict):
        return {
            "success": False,
            "message": f"No local STM32CubeMX board IOC was found for board '{board_id}'.",
        }

    baseline_mcu_name = match.get("mcu_name")
    if isinstance(baseline_mcu_name, str) and baseline_mcu_name.strip() and mcu_name.strip():
        baseline_normalized = normalized_identifier(baseline_mcu_name)
        requested_candidates = normalized_mcu_candidates(mcu_name)
        if requested_candidates and not any(candidate in baseline_normalized or baseline_normalized in candidate for candidate in requested_candidates):
            return {
                "success": False,
                "message": (
                    f"The local STM32CubeMX board IOC for '{board_id}' targets MCU '{baseline_mcu_name}', "
                    f"which did not match requested MCU '{mcu_name}'."
                ),
                "match": match,
            }

    ioc_path = match.get("ioc_path")
    if not isinstance(ioc_path, str) or not ioc_path.strip():
        return {
            "success": False,
            "message": "The matched local STM32CubeMX board IOC did not provide a file path.",
            "match": match,
        }

    resolved_ioc_path = Path(ioc_path).expanduser().resolve()
    if not resolved_ioc_path.is_file():
        return {
            "success": False,
            "message": f"The matched local STM32CubeMX board IOC file was not found: {resolved_ioc_path}",
            "match": match,
        }

    lines = parse_ioc_lines(resolved_ioc_path)
    if not lines or not any(line.startswith("Mcu.Name=") for line in lines):
        return {
            "success": False,
            "message": f"The matched local STM32CubeMX board IOC did not look valid: {resolved_ioc_path}",
            "match": match,
        }

    return {
        "success": True,
        "match": match,
        "ioc_path": str(resolved_ioc_path),
        "lines": lines,
    }


@lru_cache(maxsize=1)
def github_board_ioc_catalog() -> tuple[dict[str, str], ...]:
    request = Request(
        GITHUB_BOARD_INDEX_URL,
        headers={
            "Accept": GITHUB_API_ACCEPT,
            "User-Agent": GITHUB_USER_AGENT,
        },
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    entries: list[dict[str, str]] = []
    if not isinstance(payload, list):
        return tuple()

    for entry in payload:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        download_url = entry.get("download_url")
        if not isinstance(name, str) or not name.endswith(".ioc"):
            continue
        if not isinstance(download_url, str) or not download_url.strip():
            continue
        entries.append(
            {
                "name": name,
                "download_url": download_url,
            }
        )
    return tuple(entries)


def find_github_board_ioc(board_id: str, mcu_name: str) -> dict[str, object]:
    try:
        catalog = github_board_ioc_catalog()
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "message": f"Unable to query the STM32_open_pin_data GitHub catalog: {exc}",
        }

    board_token = board_id.upper().strip()
    board_normalized = normalized_identifier(board_token)
    mcu_candidates = normalized_mcu_candidates(mcu_name)
    best_match: dict[str, object] | None = None
    best_score = -1

    for entry in catalog:
        name = str(entry["name"])
        upper_name = name.upper()
        normalized_name = normalized_identifier(name)
        score = 0
        if re.search(rf"(^|_){re.escape(board_token)}(_|\.|$)", upper_name):
            score += 100
        elif board_normalized and board_normalized in normalized_name:
            score += 40

        for index, candidate in enumerate(mcu_candidates):
            if not candidate:
                continue
            if candidate in normalized_name:
                score += max(5, 30 - (index * 10))
                break

        if upper_name.endswith("_BOARD_ALLCONFIG.IOC"):
            score += 5

        if score > best_score:
            best_score = score
            best_match = {
                "name": name,
                "download_url": entry["download_url"],
                "score": score,
            }

    if best_match is None or best_score <= 0:
        return {
            "success": False,
            "message": f"No matching STM32_open_pin_data IOC was found for board '{board_id}' and MCU '{mcu_name}'.",
        }

    return {
        "success": True,
        "match": best_match,
        "catalog_entries": len(catalog),
    }


def download_github_ioc_lines(board_id: str, mcu_name: str) -> dict[str, object]:
    lookup = find_github_board_ioc(board_id, mcu_name)
    if not lookup.get("success"):
        return lookup

    match = lookup.get("match") if isinstance(lookup.get("match"), dict) else {}
    download_url = match.get("download_url")
    if not isinstance(download_url, str) or not download_url.strip():
        return {
            "success": False,
            "message": "The matching GitHub IOC entry did not provide a download URL.",
        }

    request = Request(
        download_url,
        headers={
            "Accept": "text/plain",
            "User-Agent": GITHUB_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {
            "success": False,
            "message": f"Unable to download the GitHub IOC template from {download_url}: {exc}",
            "match": match,
        }

    if "Mcu.Name=" not in text:
        return {
            "success": False,
            "message": f"The downloaded IOC template from {download_url} did not look valid.",
            "match": match,
        }

    return {
        "success": True,
        "match": match,
        "lines": text.splitlines(),
    }


def copy_existing_ioc_lines(source_ioc_path: Path) -> dict[str, object]:
    if not source_ioc_path.is_file():
        return {
            "success": False,
            "message": f"The source IOC file was not found: {source_ioc_path}",
        }

    lines = parse_ioc_lines(source_ioc_path)
    if not lines:
        return {
            "success": False,
            "message": f"The source IOC file is empty: {source_ioc_path}",
        }

    return {
        "success": True,
        "source_ioc_path": str(source_ioc_path),
        "lines": lines,
    }


def resolve_contract_project_context(contract: dict[str, object]) -> dict[str, object]:
    project_context = contract.get("project_context")
    return project_context if isinstance(project_context, dict) else {}


def resolve_source_ioc_path(contract: dict[str, object], source_ioc_path: str | None = None) -> Path | None:
    candidate = source_ioc_path
    if not isinstance(candidate, str) or not candidate.strip():
        project_context = resolve_contract_project_context(contract)
        configured = project_context.get("configured_source_ioc_path")
        candidate = configured if isinstance(configured, str) else None
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    path = Path(candidate).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def load_base_ioc_lines(
    contract: dict[str, object],
    *,
    source_ioc_path: str | None = None,
) -> dict[str, object]:
    project_context = resolve_contract_project_context(contract)
    target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    board_id = str(target.get("board_id") or "").strip()
    mcu_name = str(target.get("mcu") or "").strip()
    ioc_handling = str(project_context.get("ioc_handling") or "")

    if ioc_handling == "copy_existing_ioc":
        resolved_source = resolve_source_ioc_path(contract, source_ioc_path=source_ioc_path)
        if resolved_source is None:
            return {
                "success": False,
                "message": "The workflow selected existing-project IOC reuse, but no source IOC path was available.",
            }
        copied = copy_existing_ioc_lines(resolved_source)
        if not copied.get("success"):
            return copied
        return {
            "success": True,
            "construction_source": "existing_ioc_copy",
            "source_ioc_path": copied.get("source_ioc_path"),
            "lines": copied["lines"],
        }

    local_board_ioc = load_local_board_ioc_lines(board_id, mcu_name)
    if local_board_ioc.get("success"):
        return {
            "success": True,
            "construction_source": "local_board_ioc",
            "local_match": local_board_ioc.get("match"),
            "source_ioc_path": local_board_ioc.get("ioc_path"),
            "lines": local_board_ioc["lines"],
        }

    downloaded = download_github_ioc_lines(board_id, mcu_name)
    if not downloaded.get("success"):
        return {
            **downloaded,
            "local_board_ioc": local_board_ioc,
        }
    return {
        "success": True,
        "construction_source": "github_board_ioc",
        "github_match": downloaded.get("match"),
        "local_board_ioc": local_board_ioc,
        "lines": downloaded["lines"],
    }


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


def apply_synthesized_ioc_properties(lines: list[str], synthesized: dict[str, object]) -> dict[str, object]:
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

    return {
        "changed_keys": changed_keys,
        "unchanged_keys": unchanged_keys,
        "enabled_peripherals": merged_peripherals,
        "used_pins": merged_pins,
    }


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
    applied = apply_synthesized_ioc_properties(lines, synthesized)

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
    contract: dict[str, object],
    ioc_path: str | None = None,
    overwrite: bool = False,
    source_ioc_path: str | None = None,
) -> dict[str, object]:
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

    base_ioc = load_base_ioc_lines(contract, source_ioc_path=source_ioc_path)
    if not base_ioc.get("success"):
        return {
            "server": "ioc_builder",
            "success": False,
            "ioc_path": str(resolved_ioc_path),
            "message": str(base_ioc.get("message") or "No base IOC file could be prepared."),
            "validation_errors": [],
            "base_ioc": base_ioc,
        }

    toolchain = str(contract["defaults"].get("toolchain") or DEFAULT_TOOLCHAIN)
    target = contract["target"]
    lines = list(base_ioc["lines"]) if isinstance(base_ioc.get("lines"), list) else []
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
    apply_project_manager_defaults(lines, project_name=project_name, toolchain=toolchain, target_mcu=str(target["mcu"]))
    applied = apply_synthesized_ioc_properties(lines, synthesized)

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
            "base_ioc": base_ioc,
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
            else
            "The IOC file was materialized from the STM32_open_pin_data GitHub board template and deterministic change set."
            if construction_source == "github_board_ioc"
            else "The IOC file was materialized from an existing project IOC copy and deterministic change set."
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
            "Construction mode prefers official local STM32CubeMX board IOCs for new projects, falls back to STMicroelectronics/STM32_open_pin_data when needed, and copies an existing IOC for running projects.",
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


@mcp.tool(description="Construct a managed IOC working copy from an official local CubeMX board IOC when available, otherwise from GitHub board data for new projects, or from an existing IOC copy for running projects, then apply the deterministic change set for the current feature increment.")
def stm32_ioc_builder_construct(
    contract: dict[str, object],
    ioc_path: str | None = None,
    overwrite: bool = False,
    source_ioc_path: str | None = None,
) -> dict[str, object]:
    return construct_ioc_file(contract, ioc_path=ioc_path, overwrite=overwrite, source_ioc_path=source_ioc_path)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
