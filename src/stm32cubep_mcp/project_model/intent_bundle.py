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


def _clone_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(item) for item in value if isinstance(item, dict)]


@dataclass
class IntentBundle:
    intent_kind: str | None = None
    confidence: float | None = None
    core_requirements: list[dict[str, object]] = field(default_factory=list)
    optional_requirements: list[dict[str, object]] = field(default_factory=list)
    interface_intents: list[dict[str, object]] = field(default_factory=list)
    runtime_expectations: dict[str, object] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: object) -> "IntentBundle":
        if not isinstance(payload, dict):
            return cls()

        known_keys = {
            "intent_kind",
            "confidence",
            "core_requirements",
            "optional_requirements",
            "interface_intents",
            "runtime_expectations",
            "assumptions",
            "open_questions",
        }
        raw_confidence = payload.get("confidence")
        confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float)) else None
        return cls(
            intent_kind=payload.get("intent_kind") if isinstance(payload.get("intent_kind"), str) else None,
            confidence=confidence,
            core_requirements=_clone_dict_list(payload.get("core_requirements")),
            optional_requirements=_clone_dict_list(payload.get("optional_requirements")),
            interface_intents=_clone_dict_list(payload.get("interface_intents")),
            runtime_expectations=_clone_mapping(payload.get("runtime_expectations")),
            assumptions=_clone_string_list(payload.get("assumptions")),
            open_questions=_clone_string_list(payload.get("open_questions")),
            extra={key: deepcopy(value) for key, value in payload.items() if key not in known_keys},
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "intent_kind": self.intent_kind,
            "confidence": self.confidence,
            "core_requirements": deepcopy(self.core_requirements),
            "optional_requirements": deepcopy(self.optional_requirements),
            "interface_intents": deepcopy(self.interface_intents),
            "runtime_expectations": deepcopy(self.runtime_expectations),
            "assumptions": list(self.assumptions),
            "open_questions": list(self.open_questions),
        }
        payload.update(deepcopy(self.extra))
        return payload
