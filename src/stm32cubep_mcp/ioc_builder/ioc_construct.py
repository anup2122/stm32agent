from __future__ import annotations

from pathlib import Path

from .ioc_mutate import upsert_property
from .st_seed_catalog import get_board_seed_lines


REFERENCE_IOC_FILENAMES = {
    "NUCLEO-L476RG": "B60_Nucleo_NUCLEO-L476RG2_STM32L476RG_Board_AllConfig.ioc",
}


def load_reference_ioc_lines(board_id: str) -> list[str] | None:
    reference_filename = REFERENCE_IOC_FILENAMES.get(board_id)
    if reference_filename is None:
        return None

    repo_root = Path(__file__).resolve().parents[3]
    reference_path = repo_root / "config" / "reference-ioc" / board_id / reference_filename
    if not reference_path.is_file():
        return None

    return reference_path.read_text(encoding="utf-8").splitlines()


def construct_initial_ioc_lines(board_id: str, toolchain: str, target_mcu: str) -> tuple[list[str] | None, str]:
    reference_lines = load_reference_ioc_lines(board_id)
    if reference_lines is not None:
        lines = list(reference_lines)
        upsert_property(lines, "Mcu.Name", target_mcu)
        upsert_property(lines, "ProjectManager.ToolChain", toolchain)
        upsert_property(lines, "ProjectManager.TargetToolchain", toolchain)
        return lines, "reference_ioc"

    return construct_seeded_ioc_lines(board_id, toolchain, target_mcu), "embedded_seed"


def construct_seeded_ioc_lines(board_id: str, toolchain: str, target_mcu: str) -> list[str] | None:
    seed_lines = get_board_seed_lines(board_id)
    if seed_lines is None:
        return None
    lines = list(seed_lines)
    upsert_property(lines, "Mcu.Name", target_mcu)
    upsert_property(lines, "ProjectManager.ToolChain", toolchain)
    upsert_property(lines, "ProjectManager.TargetToolchain", toolchain)
    return lines