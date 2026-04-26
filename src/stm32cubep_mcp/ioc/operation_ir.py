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
class IocOperation:
    op_id: str | None = None
    kind: str | None = None
    target: dict[str, object] = field(default_factory=dict)
    value: object = None
    reason: str | None = None
    source_requirement_ids: list[str] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: object) -> "IocOperation":
        if not isinstance(payload, dict):
            return cls()

        known_keys = {"op_id", "kind", "target", "value", "reason", "source_requirement_ids"}
        return cls(
            op_id=payload.get("op_id") if isinstance(payload.get("op_id"), str) else None,
            kind=payload.get("kind") if isinstance(payload.get("kind"), str) else None,
            target=_clone_mapping(payload.get("target")),
            value=deepcopy(payload.get("value")),
            reason=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
            source_requirement_ids=_clone_string_list(payload.get("source_requirement_ids")),
            extra={key: deepcopy(value) for key, value in payload.items() if key not in known_keys},
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "op_id": self.op_id,
            "kind": self.kind,
            "target": deepcopy(self.target),
            "value": deepcopy(self.value),
            "reason": self.reason,
            "source_requirement_ids": list(self.source_requirement_ids),
        }
        payload.update(deepcopy(self.extra))
        return payload
