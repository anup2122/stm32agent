from __future__ import annotations

import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from .cache import write_index_cache
from .models import BoardBaselineEntry, McuCatalogEntry
from .sources import boards_dir, config_dir, ll_config_dir, mcu_dir, resolve_cubemx_db_root

INDEX_VERSION = "2026-04-25.phase1.v1"
BOARD_NAME_PATTERN = re.compile(r"_(NUCLEO-[A-Z0-9]+|STM32[A-Z0-9_-]+)_", re.IGNORECASE)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _board_id_from_filename(ioc_path: Path) -> str:
    match = BOARD_NAME_PATTERN.search(ioc_path.name.upper())
    if match is not None:
        return match.group(1)
    stem = ioc_path.stem.upper()
    return stem


# Extract the minimal board-baseline catalog entry from a CubeMX board IOC file.
def extract_board_entry(ioc_path: Path) -> BoardBaselineEntry:
    mcu_name: str | None = None
    for raw_line in ioc_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw_line.startswith("Mcu.Name="):
            mcu_name = raw_line.partition("=")[2].strip() or None
            break
    variant = "all_config" if ioc_path.stem.upper().endswith("ALLCONFIG") else "board"
    return BoardBaselineEntry(
        board_id=_board_id_from_filename(ioc_path),
        ioc_filename=ioc_path.name,
        ioc_path=str(ioc_path.resolve()),
        mcu_name=mcu_name,
        variant=variant,
    )


# Extract the MCU catalog entry from grouped CubeMX XML, including IP instances and signal-to-pin mappings.
def extract_mcu_entry(xml_path: Path) -> McuCatalogEntry:
    root = ET.fromstring(xml_path.read_text(encoding="utf-8", errors="replace"))
    refname = str(root.attrib.get("RefName") or xml_path.stem)
    family = root.attrib.get("Family")
    line = root.attrib.get("Line")
    package = root.attrib.get("Package")

    ips: list[str] = []
    pin_signals: dict[str, list[str]] = {}
    signal_pins: dict[str, list[str]] = {}

    for child in root:
        child_name = _local_name(child.tag)
        if child_name == "IP":
            instance_name = child.attrib.get("InstanceName")
            if isinstance(instance_name, str) and instance_name:
                ips.append(instance_name)
            continue
        if child_name != "Pin":
            continue

        pin_name = child.attrib.get("Name")
        if not isinstance(pin_name, str) or not pin_name:
            continue

        signals: list[str] = []
        for pin_child in child:
            if _local_name(pin_child.tag) != "Signal":
                continue
            signal_name = pin_child.attrib.get("Name")
            if not isinstance(signal_name, str) or not signal_name:
                continue
            signals.append(signal_name)
            signal_pins.setdefault(signal_name, []).append(pin_name)

        if signals:
            pin_signals[pin_name] = signals

    return McuCatalogEntry(
        refname=refname,
        family=family,
        line=line,
        package=package,
        grouped_xml_filename=xml_path.name,
        ips=sorted(set(ips)),
        pin_signals=pin_signals,
        signal_pins=signal_pins,
    )


def _family_key_from_config_name(filename: str) -> str | None:
    match = re.match(r"^[A-Z0-9]+-(.+?)_(?:Configs|DefMapping)\.xml$", filename, re.IGNORECASE)
    if match is None:
        return None
    return match.group(1)


# Build the cached CubeMX DB index by scanning board IOCs, MCU XML catalogs, family config files, and DMA LL mappings.
def build_cubemx_db_index(db_root: str | Path | None = None, cache_root: str | Path | None = None) -> dict[str, object]:
    resolved_root = resolve_cubemx_db_root(db_root)
    if resolved_root is None or not resolved_root.is_dir():
        raise FileNotFoundError("CubeMX DB root was not found.")

    boards_root = boards_dir(resolved_root)
    mcu_root = mcu_dir(resolved_root)
    cfg_root = config_dir(resolved_root)
    ll_root = ll_config_dir(resolved_root)

    board_entries = []
    if boards_root is not None:
        board_entries = [extract_board_entry(ioc_path).to_dict() for ioc_path in sorted(boards_root.glob("*.ioc"))]

    mcu_entries: dict[str, dict[str, object]] = {}
    if mcu_root is not None:
        for xml_path in sorted(mcu_root.glob("*.xml")):
            entry = extract_mcu_entry(xml_path)
            mcu_entries[entry.refname] = entry.to_dict()

    family_config_index: dict[str, list[str]] = {}
    if cfg_root is not None:
        for xml_path in sorted(cfg_root.glob("*_Configs.xml")):
            family_key = _family_key_from_config_name(xml_path.name)
            if family_key is None:
                continue
            family_config_index.setdefault(family_key, []).append(xml_path.name)

    dma_ll_mapping: dict[str, list[dict[str, object]]] = {}
    if ll_root is not None:
        for xml_path in sorted(ll_root.glob("DMA-*_DefMapping.xml")):
            family_key = _family_key_from_config_name(xml_path.name)
            if family_key is None:
                continue
            entries: list[dict[str, object]] = []
            root = ET.fromstring(xml_path.read_text(encoding="utf-8", errors="replace"))
            for item in root.iter():
                if _local_name(item.tag) != "Item":
                    continue
                payload = {key: value for key, value in item.attrib.items()}
                if payload:
                    entries.append(payload)
            dma_ll_mapping[family_key] = entries

    index = {
        "index_version": INDEX_VERSION,
        "db_root": str(resolved_root),
        "boards": board_entries,
        "mcu_catalog": mcu_entries,
        "family_config_index": family_config_index,
        "dma_ll_mapping": dma_ll_mapping,
    }

    if cache_root is not None:
        cache_path = Path(cache_root).expanduser().resolve()
        write_index_cache(cache_path, "cubemx_db_index.json", index)
        write_index_cache(cache_path, "boards.json", board_entries)
        write_index_cache(cache_path, "mcu_catalog.json", mcu_entries)
        write_index_cache(cache_path, "family_config_index.json", family_config_index)
        write_index_cache(cache_path, "dma_ll_mapping.json", dma_ll_mapping)

    return json.loads(json.dumps(index))
