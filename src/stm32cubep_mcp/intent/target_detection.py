from __future__ import annotations

from typing import Callable


def _load_project_data(project_metadata_loader: Callable[[], dict[str, object]] | None) -> dict[str, object]:
    if project_metadata_loader is None:
        return {}
    project_config = project_metadata_loader()
    if not isinstance(project_config, dict):
        return {}
    project_data = project_config.get("data")
    return project_data if isinstance(project_data, dict) else {}


def detect_target(
    prompt: str,
    *,
    project_metadata_loader: Callable[[], dict[str, object]] | None = None,
) -> tuple[str | None, str | None]:
    lowered = prompt.strip().lower()
    if any(token in lowered for token in ("nucleo-l476rg", "stm32l476rg", "stm32l476rg nucleo", "stm32l476rg nucleo device")):
        return "NUCLEO-L476RG", "STM32L476RGTx"

    project_data = _load_project_data(project_metadata_loader)
    board = project_data.get("board")
    if not isinstance(board, dict):
        return None, None

    board_name = board.get("name")
    board_mcu = board.get("mcu")
    resolved_board_id = board_name.strip() if isinstance(board_name, str) and board_name.strip() else None
    resolved_mcu = board_mcu.strip() if isinstance(board_mcu, str) and board_mcu.strip() else None
    if resolved_board_id or resolved_mcu:
        return resolved_board_id, resolved_mcu
    return None, None
