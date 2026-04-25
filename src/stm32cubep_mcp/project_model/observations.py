from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


def _clone_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return deepcopy(value)


def _clone_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@dataclass
class Observation:
    stage: str | None = None
    source: str | None = None
    severity: str = "info"
    summary: str = ""
    details: dict[str, object] = field(default_factory=dict)
    log_path: str | None = None
    facts: dict[str, object] = field(default_factory=dict)
    repair_hints: list[str] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: object) -> "Observation":
        if not isinstance(payload, dict):
            return cls()

        known_keys = {
            "stage",
            "source",
            "severity",
            "summary",
            "details",
            "log_path",
            "facts",
            "repair_hints",
        }
        return cls(
            stage=payload.get("stage") if isinstance(payload.get("stage"), str) else None,
            source=payload.get("source") if isinstance(payload.get("source"), str) else None,
            severity=str(payload.get("severity") or "info"),
            summary=str(payload.get("summary") or ""),
            details=_clone_mapping(payload.get("details")),
            log_path=payload.get("log_path") if isinstance(payload.get("log_path"), str) else None,
            facts=_clone_mapping(payload.get("facts")),
            repair_hints=_clone_string_list(payload.get("repair_hints")),
            extra={key: deepcopy(value) for key, value in payload.items() if key not in known_keys},
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "stage": self.stage,
            "source": self.source,
            "severity": self.severity,
            "summary": self.summary,
            "details": deepcopy(self.details),
            "log_path": self.log_path,
            "facts": deepcopy(self.facts),
            "repair_hints": list(self.repair_hints),
        }
        payload.update(deepcopy(self.extra))
        return payload
