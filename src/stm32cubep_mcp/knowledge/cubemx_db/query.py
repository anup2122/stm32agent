from __future__ import annotations

import re


def _normalize_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


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
