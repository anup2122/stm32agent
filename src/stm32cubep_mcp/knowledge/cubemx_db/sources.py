from __future__ import annotations

from pathlib import Path


DEFAULT_CUBEMX_DB_CANDIDATES = [
    Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db"),
    Path(r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeMX\db"),
    Path(r"C:\ST\STM32CubeMX\db"),
    Path(r"C:\stm\STM32CubeMX\db"),
]


def default_cubemx_db_root() -> Path | None:
    for candidate in DEFAULT_CUBEMX_DB_CANDIDATES:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def resolve_cubemx_db_root(db_root: str | Path | None = None) -> Path | None:
    if isinstance(db_root, Path):
        return db_root.expanduser().resolve()
    if isinstance(db_root, str) and db_root.strip():
        return Path(db_root).expanduser().resolve()
    return default_cubemx_db_root()


def boards_dir(db_root: str | Path | None = None) -> Path | None:
    root = resolve_cubemx_db_root(db_root)
    if root is None:
        return None
    candidate = root / "plugins" / "boardmanager" / "boards"
    return candidate if candidate.is_dir() else None


def mcu_dir(db_root: str | Path | None = None) -> Path | None:
    root = resolve_cubemx_db_root(db_root)
    if root is None:
        return None
    candidate = root / "mcu"
    return candidate if candidate.is_dir() else None


def config_dir(db_root: str | Path | None = None) -> Path | None:
    root = mcu_dir(db_root)
    if root is None:
        return None
    candidate = root / "config"
    return candidate if candidate.is_dir() else None


def ll_config_dir(db_root: str | Path | None = None) -> Path | None:
    root = config_dir(db_root)
    if root is None:
        return None
    candidate = root / "llConfig"
    return candidate if candidate.is_dir() else None
