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
class PlanIncrementRecord:
    id: str | None = None
    title: str | None = None
    feature_ids: list[str] = field(default_factory=list)
    kind: str | None = None
    interface_intent_ids: list[str] = field(default_factory=list)
    sequence: int = 0
    status: str = "pending"
    attempt_count: int = 0
    failure_count: int = 0
    started_utc: str | None = None
    completed_utc: str | None = None
    failed_utc: str | None = None
    last_stage: str | None = None
    last_message: str | None = None
    last_details: dict[str, object] | None = None
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: object) -> "PlanIncrementRecord":
        if not isinstance(payload, dict):
            return cls()

        known_keys = {
            "id",
            "title",
            "feature_ids",
            "kind",
            "interface_intent_ids",
            "sequence",
            "status",
            "attempt_count",
            "failure_count",
            "started_utc",
            "completed_utc",
            "failed_utc",
            "last_stage",
            "last_message",
            "last_details",
        }
        return cls(
            id=payload.get("id") if isinstance(payload.get("id"), str) else None,
            title=payload.get("title") if isinstance(payload.get("title"), str) else None,
            feature_ids=_clone_string_list(payload.get("feature_ids")),
            kind=payload.get("kind") if isinstance(payload.get("kind"), str) else None,
            interface_intent_ids=_clone_string_list(payload.get("interface_intent_ids")),
            sequence=int(payload.get("sequence", 0) or 0),
            status=str(payload.get("status") or "pending"),
            attempt_count=int(payload.get("attempt_count", 0) or 0),
            failure_count=int(payload.get("failure_count", 0) or 0),
            started_utc=payload.get("started_utc") if isinstance(payload.get("started_utc"), str) else None,
            completed_utc=payload.get("completed_utc") if isinstance(payload.get("completed_utc"), str) else None,
            failed_utc=payload.get("failed_utc") if isinstance(payload.get("failed_utc"), str) else None,
            last_stage=payload.get("last_stage") if isinstance(payload.get("last_stage"), str) else None,
            last_message=payload.get("last_message") if isinstance(payload.get("last_message"), str) else None,
            last_details=_clone_mapping(payload.get("last_details")) if isinstance(payload.get("last_details"), dict) else None,
            extra={key: deepcopy(value) for key, value in payload.items() if key not in known_keys},
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "feature_ids": list(self.feature_ids),
            "kind": self.kind,
            "interface_intent_ids": list(self.interface_intent_ids),
            "sequence": self.sequence,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "failure_count": self.failure_count,
            "started_utc": self.started_utc,
            "completed_utc": self.completed_utc,
            "failed_utc": self.failed_utc,
            "last_stage": self.last_stage,
            "last_message": self.last_message,
            "last_details": deepcopy(self.last_details) if isinstance(self.last_details, dict) else self.last_details,
        }
        payload.update(deepcopy(self.extra))
        return payload


@dataclass
class PlanState:
    plan_version: str | None = None
    contract_version: str | None = None
    source_prompt: str | None = None
    target: dict[str, object] = field(default_factory=dict)
    project_context: dict[str, object] = field(default_factory=dict)
    defaults: dict[str, object] = field(default_factory=dict)
    planning: dict[str, object] = field(default_factory=dict)
    increments: list[PlanIncrementRecord] = field(default_factory=list)
    current_increment: dict[str, object] = field(default_factory=dict)
    active_increment_id: str | None = None
    completed_increment_ids: list[str] = field(default_factory=list)
    failed_increment_ids: list[str] = field(default_factory=list)
    core_features: list[dict[str, object]] = field(default_factory=list)
    pluggable_features: list[dict[str, object]] = field(default_factory=list)
    execution_policy: dict[str, object] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    workflow_status: str = "planned"
    current_stage: str = "requirements"
    current_stage_message: str = ""
    current_stage_details: dict[str, object] = field(default_factory=dict)
    failure_count: int = 0
    needs_user_review: bool = False
    review_request_reason: str | None = None
    repeated_failure_threshold: int = 2
    stage_history: list[dict[str, object]] = field(default_factory=list)
    created_utc: str | None = None
    last_updated_utc: str | None = None
    last_heartbeat_utc: str | None = None
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: object) -> "PlanState":
        if not isinstance(payload, dict):
            return cls()

        known_keys = {
            "plan_version",
            "contract_version",
            "source_prompt",
            "target",
            "project_context",
            "defaults",
            "planning",
            "increments",
            "current_increment",
            "active_increment_id",
            "completed_increment_ids",
            "failed_increment_ids",
            "core_features",
            "pluggable_features",
            "execution_policy",
            "assumptions",
            "open_questions",
            "workflow_status",
            "current_stage",
            "current_stage_message",
            "current_stage_details",
            "failure_count",
            "needs_user_review",
            "review_request_reason",
            "repeated_failure_threshold",
            "stage_history",
            "created_utc",
            "last_updated_utc",
            "last_heartbeat_utc",
        }
        increments = payload.get("increments")
        return cls(
            plan_version=payload.get("plan_version") if isinstance(payload.get("plan_version"), str) else None,
            contract_version=payload.get("contract_version") if isinstance(payload.get("contract_version"), str) else None,
            source_prompt=payload.get("source_prompt") if isinstance(payload.get("source_prompt"), str) else None,
            target=_clone_mapping(payload.get("target")),
            project_context=_clone_mapping(payload.get("project_context")),
            defaults=_clone_mapping(payload.get("defaults")),
            planning=_clone_mapping(payload.get("planning")),
            increments=[PlanIncrementRecord.from_dict(item) for item in increments] if isinstance(increments, list) else [],
            current_increment=_clone_mapping(payload.get("current_increment")),
            active_increment_id=payload.get("active_increment_id") if isinstance(payload.get("active_increment_id"), str) else None,
            completed_increment_ids=_clone_string_list(payload.get("completed_increment_ids")),
            failed_increment_ids=_clone_string_list(payload.get("failed_increment_ids")),
            core_features=_clone_dict_list(payload.get("core_features")),
            pluggable_features=_clone_dict_list(payload.get("pluggable_features")),
            execution_policy=_clone_mapping(payload.get("execution_policy")),
            assumptions=_clone_string_list(payload.get("assumptions")),
            open_questions=_clone_string_list(payload.get("open_questions")),
            workflow_status=str(payload.get("workflow_status") or "planned"),
            current_stage=str(payload.get("current_stage") or "requirements"),
            current_stage_message=str(payload.get("current_stage_message") or ""),
            current_stage_details=_clone_mapping(payload.get("current_stage_details")),
            failure_count=int(payload.get("failure_count", 0) or 0),
            needs_user_review=bool(payload.get("needs_user_review")),
            review_request_reason=payload.get("review_request_reason") if isinstance(payload.get("review_request_reason"), str) else None,
            repeated_failure_threshold=int(payload.get("repeated_failure_threshold", 2) or 2),
            stage_history=_clone_dict_list(payload.get("stage_history")),
            created_utc=payload.get("created_utc") if isinstance(payload.get("created_utc"), str) else None,
            last_updated_utc=payload.get("last_updated_utc") if isinstance(payload.get("last_updated_utc"), str) else None,
            last_heartbeat_utc=payload.get("last_heartbeat_utc") if isinstance(payload.get("last_heartbeat_utc"), str) else None,
            extra={key: deepcopy(value) for key, value in payload.items() if key not in known_keys},
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "plan_version": self.plan_version,
            "contract_version": self.contract_version,
            "source_prompt": self.source_prompt,
            "target": deepcopy(self.target),
            "project_context": deepcopy(self.project_context),
            "defaults": deepcopy(self.defaults),
            "planning": deepcopy(self.planning),
            "increments": [record.to_dict() for record in self.increments],
            "current_increment": deepcopy(self.current_increment),
            "active_increment_id": self.active_increment_id,
            "completed_increment_ids": list(self.completed_increment_ids),
            "failed_increment_ids": list(self.failed_increment_ids),
            "core_features": deepcopy(self.core_features),
            "pluggable_features": deepcopy(self.pluggable_features),
            "execution_policy": deepcopy(self.execution_policy),
            "assumptions": list(self.assumptions),
            "open_questions": list(self.open_questions),
            "workflow_status": self.workflow_status,
            "current_stage": self.current_stage,
            "current_stage_message": self.current_stage_message,
            "current_stage_details": deepcopy(self.current_stage_details),
            "failure_count": self.failure_count,
            "needs_user_review": self.needs_user_review,
            "review_request_reason": self.review_request_reason,
            "repeated_failure_threshold": self.repeated_failure_threshold,
            "stage_history": deepcopy(self.stage_history),
            "created_utc": self.created_utc,
            "last_updated_utc": self.last_updated_utc,
            "last_heartbeat_utc": self.last_heartbeat_utc,
        }
        payload.update(deepcopy(self.extra))
        return payload
