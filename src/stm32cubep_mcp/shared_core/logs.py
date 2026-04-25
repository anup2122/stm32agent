from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .constants import DEFAULT_LOGS_DIR


def log_directory() -> Path:
    logs_dir = Path(os.environ.get("STM32CUBEP_MCP_LOG_DIR", DEFAULT_LOGS_DIR))
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def create_log_path(prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_directory() / f"{prefix}_{timestamp}.log"
