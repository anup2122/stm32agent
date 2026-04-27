from __future__ import annotations

from pathlib import Path
import re
from xml.etree import ElementTree as ET


def _normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def list_board_iocs(index: dict[str, object]) -> list[dict[str, object]]:
    boards = index.get("boards")
    if not isinstance(boards, list):
        return []
    return [board for board in boards if isinstance(board, dict)]


def find_board_baseline(index: dict[str, object], board_id: str) -> dict[str, object] | None:
    normalized = _normalize_key(board_id)
    candidates: list[tuple[int, dict[str, object]]] = []
    for board in list_board_iocs(index):
        board_value = board.get("board_id")
        if not isinstance(board_value, str) or _normalize_key(board_value) != normalized:
            continue

        score = 0
        if str(board.get("variant") or "").lower() == "all_config":
            score += 10
        filename = board.get("ioc_filename")
        if isinstance(filename, str) and filename.upper().endswith("ALLCONFIG.IOC"):
            score += 5
        candidates.append((score, board))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def find_mcu(index: dict[str, object], refname: str) -> dict[str, object] | None:
    catalog = index.get("mcu_catalog")
    if not isinstance(catalog, dict):
        return None

    normalized = _normalize_key(refname)
    for key, value in catalog.items():
        if isinstance(key, str) and _normalize_key(key) == normalized and isinstance(value, dict):
            return value
    return None


def signals_for_pin(index: dict[str, object], mcu_refname: str, pin_name: str) -> list[str]:
    entry = find_mcu(index, mcu_refname)
    if not isinstance(entry, dict):
        return []
    pin_signals = entry.get("pin_signals")
    if not isinstance(pin_signals, dict):
        return []
    for key, value in pin_signals.items():
        if isinstance(key, str) and key.upper() == pin_name.upper() and isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
    return []


def pins_for_signal(index: dict[str, object], mcu_refname: str, signal_name: str) -> list[str]:
    entry = find_mcu(index, mcu_refname)
    if not isinstance(entry, dict):
        return []
    signal_pins = entry.get("signal_pins")
    if not isinstance(signal_pins, dict):
        return []
    for key, value in signal_pins.items():
        if isinstance(key, str) and key.upper() == signal_name.upper() and isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
    return []


def list_family_config_files(index: dict[str, object], family_key: str) -> list[str]:
    mapping = index.get("family_config_index")
    if not isinstance(mapping, dict):
        return []
    for key, value in mapping.items():
        if isinstance(key, str) and key.upper() == family_key.upper() and isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
    return []


def dma_request_mappings(index: dict[str, object], family_key: str) -> list[dict[str, object]]:
    mapping = index.get("dma_ll_mapping")
    if not isinstance(mapping, dict):
        return []
    for key, value in mapping.items():
        if isinstance(key, str) and key.upper() == family_key.upper() and isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _family_key_for_ip(index: dict[str, object], entry: dict[str, object], ip_name: str) -> str | None:
    mapping = index.get("family_config_index")
    if not isinstance(mapping, dict):
        return None

    family_hint = _normalize_key(str(entry.get("family") or ""))
    line_hint = _normalize_key(str(entry.get("line") or ""))
    candidates: list[tuple[int, str]] = []
    for family_key, filenames in mapping.items():
        if not isinstance(family_key, str) or not isinstance(filenames, list):
            continue
        expected_filename = f"{ip_name}-{family_key}_Configs.xml"
        if not any(isinstance(name, str) and name.upper() == expected_filename.upper() for name in filenames):
            continue

        normalized_family_key = _normalize_key(family_key)
        score = 0
        if family_hint and (family_hint.startswith(normalized_family_key) or normalized_family_key.startswith(family_hint)):
            score += 2
        if line_hint and (line_hint.startswith(normalized_family_key) or normalized_family_key.startswith(line_hint)):
            score += 1
        candidates.append((score, family_key))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][1]


def cubemx_xml_references_for_ip(
    index: dict[str, object],
    mcu_refname: str,
    ip_instance_name: str,
) -> list[dict[str, object]]:
    """Return local CubeMX XML files that define an MCU IP's modes/configs."""
    entry = find_mcu(index, mcu_refname)
    db_root = index.get("db_root")
    if not isinstance(entry, dict) or not isinstance(db_root, str) or not db_root.strip():
        return []

    grouped_filename = entry.get("grouped_xml_filename")
    if not isinstance(grouped_filename, str) or not grouped_filename.strip():
        return []

    mcu_xml_path = Path(db_root) / "mcu" / grouped_filename
    references: list[dict[str, object]] = []
    if mcu_xml_path.is_file():
        references.append(
            {
                "kind": "mcu",
                "ip": ip_instance_name,
                "path": str(mcu_xml_path.resolve()),
            }
        )

    ip_name: str | None = None
    ip_version: str | None = None
    if mcu_xml_path.is_file():
        root = ET.fromstring(mcu_xml_path.read_text(encoding="utf-8", errors="replace"))
        for child in root:
            if _local_name(child.tag) != "IP":
                continue
            if child.attrib.get("InstanceName") != ip_instance_name:
                continue
            ip_name = child.attrib.get("Name") or ip_instance_name
            ip_version = child.attrib.get("Version")
            break

    family_key = _family_key_for_ip(index, entry, ip_name) if isinstance(ip_name, str) else None

    if isinstance(ip_name, str) and isinstance(family_key, str):
        config_path = Path(db_root) / "mcu" / "config" / f"{ip_name}-{family_key}_Configs.xml"
        if config_path.is_file():
            references.append(
                {
                    "kind": "ip_config",
                    "ip": ip_instance_name,
                    "path": str(config_path.resolve()),
                }
            )

        ll_mapping_path = Path(db_root) / "mcu" / "config" / "llConfig" / f"{ip_name}-{family_key}_DefMapping.xml"
        if ll_mapping_path.is_file():
            references.append(
                {
                    "kind": "ll_def_mapping",
                    "ip": ip_instance_name,
                    "path": str(ll_mapping_path.resolve()),
                }
            )

        ll_config_path = Path(db_root) / "mcu" / "config" / "llConfig" / f"{ip_name}-{family_key}_LLConfigs.xml"
        if ll_config_path.is_file():
            references.append(
                {
                    "kind": "ll_config",
                    "ip": ip_instance_name,
                    "path": str(ll_config_path.resolve()),
                }
            )

    line = entry.get("line")
    if isinstance(ip_name, str) and isinstance(ip_version, str) and isinstance(line, str):
        suffix = ip_version
        for prefix_value in (line, entry.get("family")):
            if not isinstance(prefix_value, str) or not prefix_value.strip():
                continue
            prefix = f"{prefix_value}_"
            if suffix.startswith(prefix):
                suffix = suffix[len(prefix) :]
                break
        modes_path = Path(db_root) / "mcu" / "IP" / f"{ip_name}-{line}_{suffix}_Modes.xml"
        if modes_path.is_file():
            references.append(
                {
                    "kind": "ip_modes",
                    "ip": ip_instance_name,
                    "path": str(modes_path.resolve()),
                }
            )

    return references
