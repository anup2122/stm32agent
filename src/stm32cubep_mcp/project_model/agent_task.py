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
class AgentTask:
    task_id: str | None = None
    task_kind: str | None = None
    source_prompt: str | None = None
    board_id: str | None = None
    mcu: str | None = None
    project_context_kind: str | None = None
    existing_project_path: str | None = None
    requested_actions: list[str] = field(default_factory=list)
    constraints: dict[str, object] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: object) -> "AgentTask":
        if not isinstance(payload, dict):
            return cls()

        known_keys = {
            "task_id",
            "task_kind",
            "source_prompt",
            "board_id",
            "mcu",
            "project_context_kind",
            "existing_project_path",
            "requested_actions",
            "constraints",
        }
        return cls(
            task_id=payload.get("task_id") if isinstance(payload.get("task_id"), str) else None,
            task_kind=payload.get("task_kind") if isinstance(payload.get("task_kind"), str) else None,
            source_prompt=payload.get("source_prompt") if isinstance(payload.get("source_prompt"), str) else None,
            board_id=payload.get("board_id") if isinstance(payload.get("board_id"), str) else None,
            mcu=payload.get("mcu") if isinstance(payload.get("mcu"), str) else None,
            project_context_kind=payload.get("project_context_kind") if isinstance(payload.get("project_context_kind"), str) else None,
            existing_project_path=payload.get("existing_project_path") if isinstance(payload.get("existing_project_path"), str) else None,
            requested_actions=_clone_string_list(payload.get("requested_actions")),
            constraints=_clone_mapping(payload.get("constraints")),
            extra={key: deepcopy(value) for key, value in payload.items() if key not in known_keys},
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "task_id": self.task_id,
            "task_kind": self.task_kind,
            "source_prompt": self.source_prompt,
            "board_id": self.board_id,
            "mcu": self.mcu,
            "project_context_kind": self.project_context_kind,
            "existing_project_path": self.existing_project_path,
            "requested_actions": list(self.requested_actions),
            "constraints": deepcopy(self.constraints),
        }
        payload.update(deepcopy(self.extra))
        return payload
