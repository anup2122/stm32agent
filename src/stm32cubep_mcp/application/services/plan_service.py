from __future__ import annotations

from copy import deepcopy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from ...project_model import legacy_artifact_from_plan_state, plan_state_from_legacy_artifact
from ...requirements_ioc_contract import PLAN_VERSION, list_contract_increments

PLAN_STATE_START = "<!-- plan-state:start -->"
PLAN_STATE_END = "<!-- plan-state:end -->"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_plan_path(plan_file: str) -> Path:
    candidate = Path(plan_file).expanduser()
    if candidate.is_absolute():
        return candidate
    return (Path.cwd() / candidate).resolve()


def current_increment_from_increments(increments: list[dict[str, object]]) -> dict[str, object]:
    if increments:
        return dict(increments[0])
    return {
        "id": "increment-placeholder-001",
        "title": "No concrete delivery increment was recognized",
        "feature_ids": ["placeholder-feature"],
        "kind": "core",
        "interface_intent_ids": [],
        "sequence": 1,
    }


def initial_increment_records(contract: dict[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for increment in list_contract_increments(contract):
        record = {
            **increment,
            "status": "pending",
            "attempt_count": 0,
            "failure_count": 0,
            "started_utc": None,
            "completed_utc": None,
            "failed_utc": None,
            "last_stage": None,
            "last_message": None,
            "last_details": None,
        }
        records.append(record)
    return records


def coerce_increment_records(value: object) -> list[dict[str, object]]:
    plan_state = plan_state_from_legacy_artifact({"increments": value} if isinstance(value, list) else {"increments": []})
    records: list[dict[str, object]] = []
    for index, record in enumerate(plan_state.increments, start=1):
        payload = record.to_dict()
        payload["sequence"] = int(payload.get("sequence", index) or index)
        records.append(payload)
    return records


def sync_increment_summary_fields(artifact: dict[str, object]) -> None:
    records = coerce_increment_records(artifact.get("increments"))
    artifact["increments"] = records

    active_increment_id = artifact.get("active_increment_id")
    active_record = next(
        (
            record
            for record in records
            if record.get("id") == active_increment_id and record.get("status") != "completed"
        ),
        None,
    )
    if active_record is None:
        active_record = next(
            (record for record in records if record.get("status") != "completed"),
            records[0] if records else None,
        )

    artifact["active_increment_id"] = active_record.get("id") if isinstance(active_record, dict) else None
    artifact["current_increment"] = dict(active_record) if isinstance(active_record, dict) else {}
    artifact["completed_increment_ids"] = [
        str(record["id"])
        for record in records
        if isinstance(record.get("id"), str) and record.get("status") == "completed"
    ]
    artifact["failed_increment_ids"] = [
        str(record["id"])
        for record in records
        if isinstance(record.get("id"), str) and record.get("status") == "failed"
    ]


def can_resume_existing_plan(existing: dict[str, object], contract: dict[str, object]) -> bool:
    if not isinstance(existing, dict):
        return False
    if existing.get("source_prompt") != contract.get("source_prompt"):
        return False

    existing_target = existing.get("target") if isinstance(existing.get("target"), dict) else {}
    contract_target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    if existing_target.get("board_id") != contract_target.get("board_id") or existing_target.get("mcu") != contract_target.get("mcu"):
        return False

    existing_increments = coerce_increment_records(existing.get("increments"))
    contract_increments = list_contract_increments(contract)
    if len(existing_increments) != len(contract_increments):
        return False
    for existing_increment, contract_increment in zip(existing_increments, contract_increments):
        if existing_increment.get("id") != contract_increment.get("id"):
            return False
        if existing_increment.get("feature_ids") != contract_increment.get("feature_ids"):
            return False
        if existing_increment.get("interface_intent_ids") != contract_increment.get("interface_intent_ids"):
            return False
    return True


def merge_existing_plan_artifact(existing: dict[str, object], contract: dict[str, object]) -> dict[str, object]:
    artifact = initial_plan_artifact(contract)
    if not can_resume_existing_plan(existing, contract):
        return artifact

    artifact["created_utc"] = existing.get("created_utc", artifact["created_utc"])
    artifact["failure_count"] = int(existing.get("failure_count", 0) or 0)
    artifact["stage_history"] = list(existing.get("stage_history", [])) if isinstance(existing.get("stage_history"), list) else []
    artifact["needs_user_review"] = bool(existing.get("needs_user_review"))
    artifact["review_request_reason"] = existing.get("review_request_reason")

    existing_records = {
        record.get("id"): record
        for record in coerce_increment_records(existing.get("increments"))
        if isinstance(record.get("id"), str)
    }
    merged_records: list[dict[str, object]] = []
    for record in coerce_increment_records(artifact.get("increments")):
        increment_id = record.get("id")
        existing_record = existing_records.get(increment_id)
        if existing_record is None:
            merged_records.append(record)
            continue
        if not _can_preserve_increment_progress(record, existing_record):
            merged_records.append(record)
            continue
        merged_records.append(
            {
                **record,
                "status": existing_record.get("status", record["status"]),
                "attempt_count": int(existing_record.get("attempt_count", record["attempt_count"]) or 0),
                "failure_count": int(existing_record.get("failure_count", record["failure_count"]) or 0),
                "started_utc": existing_record.get("started_utc"),
                "completed_utc": existing_record.get("completed_utc"),
                "failed_utc": existing_record.get("failed_utc"),
                "last_stage": existing_record.get("last_stage"),
                "last_message": existing_record.get("last_message"),
                "last_details": existing_record.get("last_details"),
            }
        )
    artifact["increments"] = merged_records
    artifact["active_increment_id"] = existing.get("active_increment_id")
    sync_increment_summary_fields(artifact)
    return artifact


def _can_preserve_increment_progress(record: dict[str, object], existing_record: dict[str, object]) -> bool:
    if existing_record.get("status") != "completed":
        return True

    title = record.get("title")
    last_message = existing_record.get("last_message")
    if not isinstance(title, str) or not title.strip():
        return True
    if not isinstance(last_message, str) or not last_message.strip():
        return False
    if not last_message.startswith("Implement ") or " completed successfully" not in last_message:
        return True
    return title in last_message


def update_increment_record(
    artifact: dict[str, object],
    *,
    increment_id: str,
    stage: str,
    status: str,
    message: str,
    details: dict[str, object] | None,
    timestamp_utc: str,
) -> None:
    records = coerce_increment_records(artifact.get("increments"))
    for record in records:
        if record.get("id") != increment_id:
            continue

        artifact["active_increment_id"] = increment_id
        record["last_stage"] = stage
        record["last_message"] = message
        record["last_details"] = deepcopy(details) if isinstance(details, dict) else details
        if status == "in_progress":
            if stage == "increment":
                record["attempt_count"] = int(record.get("attempt_count", 0) or 0) + 1
            if record.get("status") != "completed":
                record["status"] = "in_progress"
            if record.get("started_utc") is None:
                record["started_utc"] = timestamp_utc
        elif status == "completed" and stage == "increment":
            record["status"] = "completed"
            record["completed_utc"] = timestamp_utc
        elif status == "failed":
            record["status"] = "failed"
            record["failed_utc"] = timestamp_utc
            record["failure_count"] = int(record.get("failure_count", 0) or 0) + 1
        break

    artifact["increments"] = records
    sync_increment_summary_fields(artifact)


def initial_plan_artifact(contract: dict[str, object]) -> dict[str, object]:
    created_at = utc_now_iso()
    increments = initial_increment_records(contract)
    current_increment = current_increment_from_increments(list_contract_increments(contract))
    repeated_failure_threshold = (
        int(contract["execution_policy"].get("repeated_failure_threshold", 2) or 2)
        if isinstance(contract.get("execution_policy"), dict)
        else 2
    )
    artifact = {
        "plan_version": PLAN_VERSION,
        "contract_version": contract["contract_version"],
        "source_prompt": contract["source_prompt"],
        "target": deepcopy(contract["target"]),
        "project_context": deepcopy(contract["project_context"]),
        "defaults": deepcopy(contract["defaults"]),
        "planning": deepcopy(contract["planning"]),
        "increments": increments,
        "current_increment": current_increment,
        "active_increment_id": current_increment.get("id"),
        "completed_increment_ids": [],
        "failed_increment_ids": [],
        "core_features": deepcopy(contract["core_features"]),
        "pluggable_features": deepcopy(contract["pluggable_features"]),
        "execution_policy": deepcopy(contract["execution_policy"]),
        "assumptions": list(contract["assumptions"]),
        "open_questions": list(contract["open_questions"]),
        "workflow_status": "planned",
        "current_stage": "requirements",
        "current_stage_message": "Requirements decomposition created the iterative deterministic contract.",
        "current_stage_details": {
            "current_increment": current_increment,
        },
        "failure_count": 0,
        "needs_user_review": False,
        "review_request_reason": None,
        "repeated_failure_threshold": repeated_failure_threshold,
        "stage_history": [],
        "created_utc": created_at,
        "last_updated_utc": created_at,
        "last_heartbeat_utc": created_at,
    }
    return legacy_artifact_from_plan_state(plan_state_from_legacy_artifact(artifact))


def render_plan_markdown(artifact: dict[str, object]) -> str:
    normalized = legacy_artifact_from_plan_state(plan_state_from_legacy_artifact(artifact))
    target = normalized.get("target") if isinstance(normalized.get("target"), dict) else {}
    project_context = normalized.get("project_context") if isinstance(normalized.get("project_context"), dict) else {}
    current_increment = normalized.get("current_increment") if isinstance(normalized.get("current_increment"), dict) else {}
    increments = coerce_increment_records(normalized.get("increments"))
    execution_policy = normalized.get("execution_policy") if isinstance(normalized.get("execution_policy"), dict) else {}
    open_questions = normalized.get("open_questions") if isinstance(normalized.get("open_questions"), list) else []
    assumptions = normalized.get("assumptions") if isinstance(normalized.get("assumptions"), list) else []
    stage_history = normalized.get("stage_history") if isinstance(normalized.get("stage_history"), list) else []

    lines = [
        "# Workflow Plan",
        "",
        "## Summary",
        f"- Workflow status: `{normalized.get('workflow_status', 'unknown')}`",
        f"- Current stage: `{normalized.get('current_stage', 'unknown')}`",
        f"- Active increment: `{normalized.get('active_increment_id', 'unknown')}`",
        f"- Board: `{target.get('board_id', 'unknown')}`",
        f"- MCU: `{target.get('mcu', 'unknown')}`",
        f"- Project context: `{project_context.get('kind', 'unknown')}` via `{project_context.get('ioc_handling', 'unknown')}`",
        f"- Needs user review: `{normalized.get('needs_user_review', False)}`",
        "",
        "## Current Increment",
        f"- ID: `{current_increment.get('id', 'unknown')}`",
        f"- Title: {current_increment.get('title', 'n/a')}",
        f"- Feature IDs: {', '.join(current_increment.get('feature_ids', [])) if isinstance(current_increment.get('feature_ids'), list) else 'n/a'}",
        "",
        "## Increment Queue",
    ]
    if increments:
        for increment in increments:
            lines.append(
                f"- `{increment.get('id', 'unknown')}` `{increment.get('status', 'pending')}`: {increment.get('title', 'n/a')}"
            )
    else:
        lines.append("- No delivery increments were recorded.")

    lines.extend([
        "",
        "## Execution Policy",
        f"- Mode: `{execution_policy.get('mode', 'unknown')}`",
        f"- IOC CubeMX validation: `{execution_policy.get('ioc_cubemx_validation', 'unknown')}`",
        f"- Flash after successful build: `{execution_policy.get('flash_after_successful_build', 'unknown')}`",
        f"- Runtime check after flash: `{execution_policy.get('runtime_check_after_flash', 'unknown')}`",
        f"- Ask user on repeated failures: `{execution_policy.get('ask_user_on_repeated_failures', 'unknown')}`",
        f"- Repeated failure threshold: `{normalized.get('repeated_failure_threshold', 'unknown')}`",
        "",
        "## Open Questions",
    ])
    if open_questions:
        lines.extend(f"- {question}" for question in open_questions)
    else:
        lines.append("- None")

    lines.extend(["", "## Assumptions"])
    if assumptions:
        lines.extend(f"- {assumption}" for assumption in assumptions)
    else:
        lines.append("- None")

    lines.extend(["", "## Stage History"])
    if stage_history:
        for event in stage_history[-10:]:
            if isinstance(event, dict):
                lines.append(
                    f"- `{event.get('timestamp_utc', 'unknown')}` `{event.get('stage', 'unknown')}` `{event.get('status', 'unknown')}`: {event.get('message', '')}"
                )
    else:
        lines.append("- No recorded stage transitions yet.")

    lines.extend([
        "",
        PLAN_STATE_START,
        "```json",
        json.dumps(normalized, indent=2),
        "```",
        PLAN_STATE_END,
        "",
    ])
    return "\n".join(lines)


def parse_plan_markdown(text: str) -> dict[str, object]:
    start_index = text.find(PLAN_STATE_START)
    end_index = text.find(PLAN_STATE_END)
    if start_index < 0 or end_index < 0 or end_index <= start_index:
        raise json.JSONDecodeError("Embedded plan state markers were not found.", text, 0)

    payload = text[start_index + len(PLAN_STATE_START):end_index].strip()
    if payload.startswith("```json"):
        payload = payload[len("```json"):].strip()
    if payload.endswith("```"):
        payload = payload[:-3].strip()
    return legacy_artifact_from_plan_state(plan_state_from_legacy_artifact(json.loads(payload)))


def serialize_plan_artifact(plan_path: Path, artifact: dict[str, object]) -> str:
    normalized = legacy_artifact_from_plan_state(plan_state_from_legacy_artifact(artifact))
    if plan_path.suffix.lower() == ".md":
        return render_plan_markdown(normalized)
    return json.dumps(normalized, indent=2)


def deserialize_plan_artifact(plan_path: Path, text: str) -> dict[str, object]:
    if plan_path.suffix.lower() == ".md":
        return parse_plan_markdown(text)
    return legacy_artifact_from_plan_state(plan_state_from_legacy_artifact(json.loads(text)))


def write_plan_artifact(plan_path: Path, artifact: dict[str, object]) -> None:
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = plan_path.with_name(f"{plan_path.name}.tmp")
    temp_path.write_text(serialize_plan_artifact(plan_path, artifact), encoding="utf-8")
    os.replace(temp_path, plan_path)


def fallback_plan_artifact(stage: str, status: str, message: str, details: dict[str, object] | None = None) -> dict[str, object]:
    created_at = utc_now_iso()
    artifact = {
        "plan_version": PLAN_VERSION,
        "workflow_status": status,
        "current_stage": stage,
        "current_stage_message": message,
        "current_stage_details": deepcopy(details) if isinstance(details, dict) else {},
        "failure_count": 0,
        "stage_history": [],
        "created_utc": created_at,
        "last_updated_utc": created_at,
        "last_heartbeat_utc": created_at,
    }
    return legacy_artifact_from_plan_state(plan_state_from_legacy_artifact(artifact))


def load_plan_artifact(
    plan_path: Path,
    *,
    default_stage: str,
    default_status: str,
    default_message: str,
    default_details: dict[str, object] | None = None,
) -> dict[str, object]:
    if not plan_path.is_file():
        return fallback_plan_artifact(default_stage, default_status, default_message, default_details)

    try:
        return deserialize_plan_artifact(plan_path, plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback_plan_artifact(default_stage, default_status, default_message, default_details)


def persist_plan_artifact(contract: dict[str, object]) -> dict[str, object]:
    plan_path = resolve_plan_path(str(contract["plan_file"]))
    existing_artifact = load_plan_artifact(
        plan_path,
        default_stage="requirements",
        default_status="planned",
        default_message="Requirements decomposition has not started yet.",
    )
    artifact = merge_existing_plan_artifact(existing_artifact, contract)
    requirements_message = (
        "Requirements decomposition refreshed the iterative contract and preserved prior increment progress."
        if can_resume_existing_plan(existing_artifact, contract)
        else "Requirements decomposition completed and produced the initial iterative contract."
    )
    artifact["workflow_status"] = "planned"
    artifact["current_stage"] = "requirements"
    artifact["current_stage_message"] = requirements_message
    artifact["current_stage_details"] = {
        "current_increment": deepcopy(artifact.get("current_increment")),
    }
    artifact["last_updated_utc"] = utc_now_iso()
    artifact["last_heartbeat_utc"] = artifact["last_updated_utc"]
    artifact.setdefault("stage_history", []).append(
        {
            "stage": "requirements",
            "status": "completed",
            "message": requirements_message,
            "timestamp_utc": artifact["last_updated_utc"],
        }
    )
    write_plan_artifact(plan_path, artifact)
    normalized = load_plan_artifact(
        plan_path,
        default_stage="requirements",
        default_status="planned",
        default_message=requirements_message,
    )
    return {
        "plan_path": str(plan_path),
        "plan": normalized,
    }


def update_plan_status(
    plan_file: str,
    *,
    stage: str,
    status: str,
    message: str,
    details: dict[str, object] | None = None,
    increment_id: str | None = None,
    append_history: bool = True,
) -> dict[str, object]:
    plan_path = resolve_plan_path(plan_file)
    artifact = load_plan_artifact(
        plan_path,
        default_stage=stage,
        default_status=status,
        default_message=message,
        default_details=details,
    )

    artifact["workflow_status"] = status
    artifact["current_stage"] = stage
    artifact["current_stage_message"] = message
    artifact["current_stage_details"] = deepcopy(details) if isinstance(details, dict) else {}
    artifact["last_updated_utc"] = utc_now_iso()
    artifact["last_heartbeat_utc"] = artifact["last_updated_utc"]
    if status == "failed":
        artifact["failure_count"] = int(artifact.get("failure_count", 0) or 0) + 1

    if isinstance(increment_id, str) and increment_id.strip():
        update_increment_record(
            artifact,
            increment_id=increment_id.strip(),
            stage=stage,
            status=status,
            message=message,
            details=details,
            timestamp_utc=artifact["last_updated_utc"],
        )
    else:
        sync_increment_summary_fields(artifact)

    execution_policy = artifact.get("execution_policy") if isinstance(artifact.get("execution_policy"), dict) else {}
    repeated_failure_threshold = int(artifact.get("repeated_failure_threshold", 2) or 2)
    should_ask_user = bool(execution_policy.get("ask_user_on_repeated_failures", False))
    if status == "failed" and should_ask_user and int(artifact.get("failure_count", 0) or 0) >= repeated_failure_threshold:
        artifact["needs_user_review"] = True
        artifact["review_request_reason"] = (
            f"Workflow recorded {artifact['failure_count']} failures. Review the plan file before retrying the current increment."
        )
        artifact["workflow_status"] = "needs_user_review"

    event: dict[str, object] = {
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp_utc": artifact["last_updated_utc"],
    }
    if increment_id is not None:
        event["increment_id"] = increment_id
    if details is not None:
        event["details"] = deepcopy(details)
    if append_history:
        artifact.setdefault("stage_history", []).append(event)
    write_plan_artifact(plan_path, artifact)
    normalized = load_plan_artifact(
        plan_path,
        default_stage=stage,
        default_status=status,
        default_message=message,
        default_details=details,
    )
    return {
        "plan_path": str(plan_path),
        "plan": normalized,
        "event": event,
    }


def heartbeat_plan_status(
    plan_file: str,
    *,
    stage: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return update_plan_status(
        plan_file,
        stage=stage,
        status="in_progress",
        message=message,
        details=details,
        append_history=False,
    )


def read_plan_status(plan_file: str) -> dict[str, object]:
    plan_path = resolve_plan_path(plan_file)
    if not plan_path.is_file():
        return {
            "success": False,
            "plan_path": str(plan_path),
            "message": "Plan artifact was not found.",
        }

    try:
        plan = deserialize_plan_artifact(plan_path, plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "success": False,
            "plan_path": str(plan_path),
            "message": "Plan artifact exists but is not valid in its declared format.",
        }
    return {
        "success": True,
        "plan_path": str(plan_path),
        "workflow_status": plan.get("workflow_status"),
        "current_stage": plan.get("current_stage"),
        "current_stage_message": plan.get("current_stage_message"),
        "current_stage_details": plan.get("current_stage_details"),
        "last_updated_utc": plan.get("last_updated_utc"),
        "last_heartbeat_utc": plan.get("last_heartbeat_utc"),
        "failure_count": plan.get("failure_count"),
        "active_increment_id": plan.get("active_increment_id"),
        "completed_increment_ids": plan.get("completed_increment_ids"),
        "failed_increment_ids": plan.get("failed_increment_ids"),
        "needs_user_review": plan.get("needs_user_review"),
        "review_request_reason": plan.get("review_request_reason"),
        "stage_history_count": len(plan.get("stage_history", [])) if isinstance(plan.get("stage_history"), list) else 0,
        "plan": plan,
    }
