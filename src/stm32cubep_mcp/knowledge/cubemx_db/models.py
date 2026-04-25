from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class BoardBaselineEntry:
    board_id: str
    ioc_filename: str
    ioc_path: str
    mcu_name: str | None = None
    variant: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "board_id": self.board_id,
            "ioc_filename": self.ioc_filename,
            "ioc_path": self.ioc_path,
            "mcu_name": self.mcu_name,
            "variant": self.variant,
        }


@dataclass
class McuCatalogEntry:
    refname: str
    family: str | None = None
    line: str | None = None
    package: str | None = None
    grouped_xml_filename: str | None = None
    ips: list[str] = field(default_factory=list)
    pin_signals: dict[str, list[str]] = field(default_factory=dict)
    signal_pins: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "refname": self.refname,
            "family": self.family,
            "line": self.line,
            "package": self.package,
            "grouped_xml_filename": self.grouped_xml_filename,
            "ips": list(self.ips),
            "pin_signals": deepcopy(self.pin_signals),
            "signal_pins": deepcopy(self.signal_pins),
        }
