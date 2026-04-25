from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


def _clone_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return deepcopy(value)


@dataclass
class ProjectState:
    project_name: str | None = None
    project_root: str | None = None
    managed_copy_root: str | None = None
    ioc_path: str | None = None
    script_path: str | None = None
    cubeide_project_path: str | None = None
    workspace_path: str | None = None
    build_artifact_path: str | None = None
    board_id: str | None = None
    mcu: str | None = None
    clock_summary: dict[str, object] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: object) -> "ProjectState":
        if not isinstance(payload, dict):
            return cls()

        known_keys = {
            "project_name",
            "project_root",
            "managed_copy_root",
            "ioc_path",
            "script_path",
            "cubeide_project_path",
            "workspace_path",
            "build_artifact_path",
            "board_id",
            "mcu",
            "clock_summary",
        }
        return cls(
            project_name=payload.get("project_name") if isinstance(payload.get("project_name"), str) else None,
            project_root=payload.get("project_root") if isinstance(payload.get("project_root"), str) else None,
            managed_copy_root=payload.get("managed_copy_root") if isinstance(payload.get("managed_copy_root"), str) else None,
            ioc_path=payload.get("ioc_path") if isinstance(payload.get("ioc_path"), str) else None,
            script_path=payload.get("script_path") if isinstance(payload.get("script_path"), str) else None,
            cubeide_project_path=payload.get("cubeide_project_path") if isinstance(payload.get("cubeide_project_path"), str) else None,
            workspace_path=payload.get("workspace_path") if isinstance(payload.get("workspace_path"), str) else None,
            build_artifact_path=payload.get("build_artifact_path") if isinstance(payload.get("build_artifact_path"), str) else None,
            board_id=payload.get("board_id") if isinstance(payload.get("board_id"), str) else None,
            mcu=payload.get("mcu") if isinstance(payload.get("mcu"), str) else None,
            clock_summary=_clone_mapping(payload.get("clock_summary")),
            extra={key: deepcopy(value) for key, value in payload.items() if key not in known_keys},
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "project_name": self.project_name,
            "project_root": self.project_root,
            "managed_copy_root": self.managed_copy_root,
            "ioc_path": self.ioc_path,
            "script_path": self.script_path,
            "cubeide_project_path": self.cubeide_project_path,
            "workspace_path": self.workspace_path,
            "build_artifact_path": self.build_artifact_path,
            "board_id": self.board_id,
            "mcu": self.mcu,
            "clock_summary": deepcopy(self.clock_summary),
        }
        payload.update(deepcopy(self.extra))
        return payload
