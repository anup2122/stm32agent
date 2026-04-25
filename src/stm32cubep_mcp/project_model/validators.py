from __future__ import annotations

from .agent_task import AgentTask
from .intent_bundle import IntentBundle


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_agent_task(task: AgentTask | object) -> list[str]:
    normalized = task if isinstance(task, AgentTask) else AgentTask.from_dict(task)
    errors: list[str] = []

    if not _is_non_empty_string(normalized.task_kind):
        errors.append("task_kind is required.")
    if not _is_non_empty_string(normalized.source_prompt):
        errors.append("source_prompt is required.")
    if normalized.project_context_kind is not None and normalized.project_context_kind not in {
        "new_device",
        "new_project",
        "existing_project",
    }:
        errors.append("project_context_kind must be 'new_device', 'new_project', or 'existing_project' when provided.")
    return errors


def validate_intent_bundle(bundle: IntentBundle | object) -> list[str]:
    normalized = bundle if isinstance(bundle, IntentBundle) else IntentBundle.from_dict(bundle)
    errors: list[str] = []

    if not _is_non_empty_string(normalized.intent_kind):
        errors.append("intent_kind is required.")
    if normalized.confidence is not None and not 0.0 <= normalized.confidence <= 1.0:
        errors.append("confidence must be between 0.0 and 1.0 when provided.")
    if not isinstance(normalized.runtime_expectations, dict):
        errors.append("runtime_expectations must be a dictionary.")
    return errors
