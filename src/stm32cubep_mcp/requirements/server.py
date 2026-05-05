"""Requirement decomposition MCP server.

Readme-style call chain for this module:

1. The installed console script `stm32-requirements-mcp` is declared in
    `pyproject.toml` and points to `stm32cubep_mcp.requirements.server:main`.
2. Starting `stm32-requirements-mcp` calls `main()` in this module.
3. `main()` calls `mcp.run(transport="stdio")` to start the FastMCP server.
4. An MCP client connects and invokes the `stm32_requirements_decompose` tool.
5. `stm32_requirements_decompose(prompt, persist_plan=False)` calls
    `build_requirements_contract(prompt)`.
6. `build_requirements_contract(prompt)` assembles the deterministic planning
    contract by calling, in order:
    - `detect_target(prompt)`
    - `build_intent_bundle(prompt)`
    - `legacy_requirements_dict_from_intent_bundle(intent_bundle)`
    - `detect_project_context(prompt)`
    - `build_feature_increments(core_features, pluggable_features)`
    - `current_increment_from_increments(increments)`
    - `make_contract(...)`
    - `default_plan_file(project_context)` as part of the `make_contract(...)`
      arguments

This means `stm32_requirements_decompose` is the first prompt-handling MCP tool
for the requirements workflow, but it is not the process startup entrypoint.
The process entrypoint is `main()`.

Exact prompt-to-contract chain inside this file:

`stm32_requirements_decompose(prompt, persist_plan=False)`
-> `build_requirements_contract(prompt)`
-> `detect_target(prompt)`
-> `build_intent_bundle(prompt)`
-> `legacy_requirements_dict_from_intent_bundle(intent_bundle)`
-> `detect_project_context(prompt)`
-> `build_feature_increments(core_features, pluggable_features)`
-> `current_increment_from_increments(increments)`
-> `make_contract(...)`
-> `validate_contract(contract)` back in `stm32_requirements_decompose(...)`
-> optional `persist_plan_artifact(contract)` when `persist_plan=True`

Concrete tested prompt example:

`I have attached STM32L476Rg Nucleo device. write a project that will send
data from the device to pc and run and test it`

For that prompt, the contract path in this module resolves target
`NUCLEO-L476RG`, recognizes a new-device project context, selects the core
feature `core-uart-device-to-pc`, creates increment `increment-core-001`, and
returns a validated deterministic contract for the IOC builder workflow.

How an MCP client knows to call this tool:

1. The client does not infer the callable tool from the description text alone.
2. After `main()` starts the FastMCP server through `mcp.run(...)`, the client
    asks the server for its advertised tool list.
3. The server exposes this function as the tool
    `stm32_requirements_decompose` because the `@mcp.tool(...)` decorator wraps
    the function and no alternate exported name is provided.
4. The advertised tool definition includes the tool name, the human-readable
    description, and the input schema derived from the function signature:
    `prompt: str` and `persist_plan: bool = False`.
5. The client then chooses the tool by using the advertised tool metadata as a
    whole. The description helps selection, but the binding is by tool name and
    schema, not by description text alone.

In practice there are two common calling modes:

- Deterministic code can call the tool explicitly by its exported name
  `stm32_requirements_decompose` after discovery.
- An LLM-driven client can choose the tool from the advertised list using the
  tool name, description, argument schema, and the active user request.

Repo-specific note:

Some internal flows in this repository bypass MCP discovery entirely and call
the Python function directly. In those flows, there is no tool-selection step;
the caller already decided to invoke `stm32_requirements_decompose(...)`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .. import shared
from ..application.services import plan_service
from ..intent import (
    ENGINEERING_SPEC_TOKENS as INTENT_ENGINEERING_SPEC_TOKENS,
    EXISTING_PROJECT_TOKENS as INTENT_EXISTING_PROJECT_TOKENS,
    NEW_DEVICE_TOKENS as INTENT_NEW_DEVICE_TOKENS,
    NEW_PROJECT_TOKENS as INTENT_NEW_PROJECT_TOKENS,
    SUPPORTED_PROMPT_FAMILIES as INTENT_SUPPORTED_PROMPT_FAMILIES,
    build_intent_bundle as analyze_prompt_intent,
    configured_ioc_path as resolve_configured_ioc_path,
    detect_project_context as detect_project_context_impl,
    detect_target as detect_target_impl,
    looks_like_engineering_feature_spec as looks_like_engineering_feature_spec_impl,
)
from ..project_model import legacy_requirements_dict_from_intent_bundle
from ..requirements_ioc_contract import (
    CONTRACT_VERSION,
    DEFAULT_PLAN_FILE_NAME,
    DEFAULT_TOOLCHAIN,
    PLAN_VERSION,
    list_contract_increments,
    make_contract,
    validate_contract,
)

mcp = FastMCP("stm32requirements")

SUPPORTED_PROMPT_FAMILIES = [
    *INTENT_SUPPORTED_PROMPT_FAMILIES,
]

EXISTING_PROJECT_TOKENS = INTENT_EXISTING_PROJECT_TOKENS
NEW_PROJECT_TOKENS = INTENT_NEW_PROJECT_TOKENS
NEW_DEVICE_TOKENS = INTENT_NEW_DEVICE_TOKENS
ENGINEERING_SPEC_TOKENS = INTENT_ENGINEERING_SPEC_TOKENS

PLAN_STATE_START = "<!-- plan-state:start -->"
PLAN_STATE_END = "<!-- plan-state:end -->"
PLANNING_ONLY_FEATURE_IDS = {"pluggable-runtime-check"}


def detect_target(prompt: str) -> tuple[str | None, str | None]:
    return detect_target_impl(prompt, project_metadata_loader=shared.load_project_metadata)


def looks_like_engineering_feature_spec(prompt: str) -> bool:
    return looks_like_engineering_feature_spec_impl(prompt)


def plan_feature_split(prompt: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[str], list[str]]:
    legacy = legacy_requirements_dict_from_intent_bundle(build_intent_bundle(prompt))
    return (
        legacy["core_features"],
        legacy["pluggable_features"],
        legacy["interface_intents"],
        legacy["assumptions"],
        legacy["open_questions"],
    )


def build_intent_bundle(prompt: str):
    return analyze_prompt_intent(prompt)


def resolve_plan_path(plan_file: str) -> Path:
    candidate = Path(plan_file).expanduser()
    if candidate.is_absolute():
        return candidate
    return (Path.cwd() / candidate).resolve()


def configured_ioc_path() -> Path | None:
    return resolve_configured_ioc_path(project_metadata_loader=shared.load_project_metadata, cwd_resolver=Path.cwd)


def detect_project_context(prompt: str) -> dict[str, object]:
    return detect_project_context_impl(
        prompt,
        project_metadata_loader=shared.load_project_metadata,
        cwd_resolver=Path.cwd,
    )


def default_plan_file(project_context: dict[str, object] | None = None) -> str:
    context = project_context if isinstance(project_context, dict) else {}
    if not context:
        ioc_path = configured_ioc_path()
        if ioc_path is not None:
            return str((ioc_path.parent / DEFAULT_PLAN_FILE_NAME).resolve())

    if context.get("kind") == "existing_project":
        configured_source = context.get("configured_source_ioc_path")
        if isinstance(configured_source, str) and configured_source.strip():
            return str((Path(configured_source).resolve().parent / DEFAULT_PLAN_FILE_NAME).resolve())

    ioc_path = configured_ioc_path()
    if ioc_path is not None and context.get("kind") == "existing_project":
        return str((ioc_path.parent / DEFAULT_PLAN_FILE_NAME).resolve())
    return str((Path.cwd() / "generated" / DEFAULT_PLAN_FILE_NAME).resolve())


def build_feature_increments(
    core_features: list[dict[str, object]],
    pluggable_features: list[dict[str, object]],
) -> list[dict[str, object]]:
    increments: list[dict[str, object]] = []
    kind_counters = {
        "core": 0,
        "pluggable": 0,
    }

    for feature in [*core_features, *pluggable_features]:
        if not isinstance(feature, dict):
            continue
        feature_id = feature.get("id")
        if not isinstance(feature_id, str) or not feature_id.strip():
            continue
        if feature_id in PLANNING_ONLY_FEATURE_IDS:
            continue

        kind = str(feature.get("kind") or "pluggable").strip() or "pluggable"
        if kind not in kind_counters:
            kind_counters[kind] = 0
        kind_counters[kind] += 1

        interface_intent_ids = feature.get("interface_intent_ids")
        normalized_intent_ids = (
            [intent_id for intent_id in interface_intent_ids if isinstance(intent_id, str) and intent_id.strip()]
            if isinstance(interface_intent_ids, list)
            else []
        )
        title = str(feature.get("title") or feature_id).strip() or feature_id
        increments.append(
            {
                "id": f"increment-{kind}-{kind_counters[kind]:03d}",
                "title": f"Implement {title}",
                "feature_ids": [feature_id],
                "kind": kind,
                "interface_intent_ids": normalized_intent_ids,
                "sequence": len(increments) + 1,
            }
        )
    return increments


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
    if not isinstance(value, list):
        return []

    records: list[dict[str, object]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        feature_ids = item.get("feature_ids")
        if not isinstance(feature_ids, list):
            feature_ids = []
        interface_intent_ids = item.get("interface_intent_ids")
        if not isinstance(interface_intent_ids, list):
            interface_intent_ids = []
        records.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "feature_ids": [feature_id for feature_id in feature_ids if isinstance(feature_id, str)],
                "kind": item.get("kind"),
                "interface_intent_ids": [intent_id for intent_id in interface_intent_ids if isinstance(intent_id, str)],
                "sequence": item.get("sequence", index),
                "status": item.get("status", "pending"),
                "attempt_count": int(item.get("attempt_count", 0) or 0),
                "failure_count": int(item.get("failure_count", 0) or 0),
                "started_utc": item.get("started_utc"),
                "completed_utc": item.get("completed_utc"),
                "failed_utc": item.get("failed_utc"),
                "last_stage": item.get("last_stage"),
                "last_message": item.get("last_message"),
                "last_details": item.get("last_details"),
            }
        )
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

    existing_increment_ids = [record.get("id") for record in coerce_increment_records(existing.get("increments"))]
    contract_increment_ids = [increment.get("id") for increment in list_contract_increments(contract)]
    return existing_increment_ids == contract_increment_ids


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
        record["last_details"] = details
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
    created_at = datetime.now(timezone.utc).isoformat()
    increments = initial_increment_records(contract)
    current_increment = current_increment_from_increments(list_contract_increments(contract))
    repeated_failure_threshold = (
        int(contract["execution_policy"].get("repeated_failure_threshold", 2) or 2)
        if isinstance(contract.get("execution_policy"), dict)
        else 2
    )
    return {
        "plan_version": PLAN_VERSION,
        "contract_version": contract["contract_version"],
        "source_prompt": contract["source_prompt"],
        "target": contract["target"],
        "project_context": contract["project_context"],
        "defaults": contract["defaults"],
        "planning": contract["planning"],
        "increments": increments,
        "current_increment": current_increment,
        "active_increment_id": current_increment.get("id"),
        "completed_increment_ids": [],
        "failed_increment_ids": [],
        "core_features": contract["core_features"],
        "pluggable_features": contract["pluggable_features"],
        "execution_policy": contract["execution_policy"],
        "assumptions": contract["assumptions"],
        "open_questions": contract["open_questions"],
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


def render_plan_markdown(artifact: dict[str, object]) -> str:
    target = artifact.get("target") if isinstance(artifact.get("target"), dict) else {}
    project_context = artifact.get("project_context") if isinstance(artifact.get("project_context"), dict) else {}
    current_increment = artifact.get("current_increment") if isinstance(artifact.get("current_increment"), dict) else {}
    increments = coerce_increment_records(artifact.get("increments"))
    execution_policy = artifact.get("execution_policy") if isinstance(artifact.get("execution_policy"), dict) else {}
    open_questions = artifact.get("open_questions") if isinstance(artifact.get("open_questions"), list) else []
    assumptions = artifact.get("assumptions") if isinstance(artifact.get("assumptions"), list) else []
    stage_history = artifact.get("stage_history") if isinstance(artifact.get("stage_history"), list) else []

    lines = [
        "# Workflow Plan",
        "",
        "## Summary",
        f"- Workflow status: `{artifact.get('workflow_status', 'unknown')}`",
        f"- Current stage: `{artifact.get('current_stage', 'unknown')}`",
        f"- Active increment: `{artifact.get('active_increment_id', 'unknown')}`",
        f"- Board: `{target.get('board_id', 'unknown')}`",
        f"- MCU: `{target.get('mcu', 'unknown')}`",
        f"- Project context: `{project_context.get('kind', 'unknown')}` via `{project_context.get('ioc_handling', 'unknown')}`",
        f"- Needs user review: `{artifact.get('needs_user_review', False)}`",
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
        f"- Repeated failure threshold: `{artifact.get('repeated_failure_threshold', 'unknown')}`",
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
                lines.append(f"- `{event.get('timestamp_utc', 'unknown')}` `{event.get('stage', 'unknown')}` `{event.get('status', 'unknown')}`: {event.get('message', '')}")
    else:
        lines.append("- No recorded stage transitions yet.")

    lines.extend([
        "",
        PLAN_STATE_START,
        "```json",
        json.dumps(artifact, indent=2),
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
    return json.loads(payload)


def serialize_plan_artifact(plan_path: Path, artifact: dict[str, object]) -> str:
    if plan_path.suffix.lower() == ".md":
        return render_plan_markdown(artifact)
    return json.dumps(artifact, indent=2)


def deserialize_plan_artifact(plan_path: Path, text: str) -> dict[str, object]:
    if plan_path.suffix.lower() == ".md":
        return parse_plan_markdown(text)
    return json.loads(text)


def write_plan_artifact(plan_path: Path, artifact: dict[str, object]) -> None:
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = plan_path.with_name(f"{plan_path.name}.tmp")
    temp_path.write_text(serialize_plan_artifact(plan_path, artifact), encoding="utf-8")
    os.replace(temp_path, plan_path)


def fallback_plan_artifact(stage: str, status: str, message: str, details: dict[str, object] | None = None) -> dict[str, object]:
    created_at = datetime.now(timezone.utc).isoformat()
    return {
        "plan_version": PLAN_VERSION,
        "workflow_status": status,
        "current_stage": stage,
        "current_stage_message": message,
        "current_stage_details": details or {},
        "failure_count": 0,
        "stage_history": [],
        "created_utc": created_at,
        "last_updated_utc": created_at,
        "last_heartbeat_utc": created_at,
    }


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
    return plan_service.persist_plan_artifact(contract)


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
    return plan_service.update_plan_status(
        plan_file,
        stage=stage,
        status=status,
        message=message,
        details=details,
        increment_id=increment_id,
        append_history=append_history,
    )


def heartbeat_plan_status(
    plan_file: str,
    *,
    stage: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return plan_service.heartbeat_plan_status(plan_file, stage=stage, message=message, details=details)


def read_plan_status(plan_file: str) -> dict[str, object]:
    return plan_service.read_plan_status(plan_file)
"""
I’m pulling the exact line range around the function so I can explain its behavior with concrete references instead of paraphrasing the whole file.

Read [](file:///c%3A/agent_dev_v1/mcp-server-stm32cubep/src/stm32cubep_mcp/requirements/server.py#650-650), lines 650 to 710

server.py is the prompt-to-contract assembler for the requirements server. It takes one freeform STM32 prompt string and turns it into the deterministic contract object that the rest of the workflow uses.

At a high level, it does six things:

1. It detects the hardware target from the prompt by calling `detect_target(prompt)`, which gives it `board_id` and `mcu`.
2. It analyzes the prompt intent with `build_intent_bundle(prompt)`, then converts that bundle into the older normalized structure with `legacy_requirements_dict_from_intent_bundle(...)`.
3. From that normalized structure it extracts the main planning inputs: `core_features`, `pluggable_features`, `interface_intents`, `assumptions`, and `open_questions`.
4. It detects project context with `detect_project_context(prompt)`, so the contract knows whether this looks like a new project, existing IOC-backed project, and so on.
5. If no board or MCU was recognized, it does not fail immediately. Instead, it appends an open question, substitutes `"unknown"` placeholders, and keeps building a contract anyway.
6. It derives delivery increments with `build_feature_increments(...)`, picks the current increment with `current_increment_from_increments(...)`, and then calls `make_contract(...)` to assemble the final structured contract.

The important output shape is created in the `make_contract(...)` call inside server.py. That is where the function packages:
- the original prompt
- target board and MCU
- project context
- core and pluggable features
- interface intents
- defaults such as toolchain and project style
- execution policy
- assumptions and open questions
- the default plan file path

One useful detail is that this function is intentionally permissive. It tries to produce a contract even for partial or weakly recognized prompts. That is why it inserts `"unknown"` target values and adds an open question instead of throwing an error. Validation is deferred to the caller. In this module, that caller is `stm32_requirements_decompose(...)`, which runs `validate_contract(contract)` after this function returns.

What it does not do:
- it does not validate the contract
- it does not persist a plan artifact
- it does not decide success/failure for the tool result

Those happen one layer up in the MCP tool function after server.py returns.

A simple mental model is:

`prompt -> target detection + intent extraction + project context -> feature increments -> make_contract(...) -> contract dict`

If you want, I can also walk through this function line by line using one concrete prompt example and show the exact intermediate values it would produce.
"""

# Assemble the deterministic requirements contract from prompt-derived target, intent, project-context, and increment data.
def build_requirements_contract(prompt: str) -> dict[str, object]:
    board_id, mcu = detect_target(prompt)
    intent_bundle = build_intent_bundle(prompt)
    legacy_intent = legacy_requirements_dict_from_intent_bundle(intent_bundle)
    core_features = legacy_intent["core_features"]
    pluggable_features = legacy_intent["pluggable_features"]
    interface_intents = legacy_intent["interface_intents"]
    assumptions = legacy_intent["assumptions"]
    open_questions = legacy_intent["open_questions"]
    project_context = detect_project_context(prompt)

    if not board_id or not mcu:
        open_questions.append("A supported board or MCU identifier is required. Phase 2 currently supports NUCLEO-L476RG prompt decomposition only.")
        board_id = board_id or "unknown"
        mcu = mcu or "unknown"

    increments = build_feature_increments(core_features, pluggable_features)
    current_increment = current_increment_from_increments(increments)
    contract = make_contract(
        source_prompt=prompt,
        board_id=board_id,
        mcu=mcu,
        project_context=project_context,
        core_features=core_features,
        pluggable_features=pluggable_features,
        increments=increments,
        current_increment=current_increment,
        interface_intents=interface_intents,
        defaults={
            "toolchain": DEFAULT_TOOLCHAIN,
            "project_style": "ioc_incremental",
        },
        execution_policy=legacy_intent["execution_policy"],
        assumptions=assumptions,
        open_questions=open_questions,
        plan_file=default_plan_file(project_context),
    )
    intent_metadata = legacy_intent.get("intent_metadata")
    if isinstance(intent_metadata, dict) and intent_metadata:
        contract["intent_metadata"] = intent_metadata
    return contract


def has_supported_delivery_increments(contract: dict[str, object]) -> bool:
    return bool(list_contract_increments(contract)) and bool(contract.get("increments"))


# Report the current requirements agent scope, contract version, and planning-related capability notes.
def collect_requirements_capabilities() -> dict[str, object]:
    return {
        "server": "requirements",
        "implemented": True,
        "supported_prompt_families": SUPPORTED_PROMPT_FAMILIES,
        "contract_version": CONTRACT_VERSION,
        "default_toolchain": DEFAULT_TOOLCHAIN,
        "notes": [
            "This Phase 2 scaffold produces a deterministic contract for IOC synthesis.",
            "Board-targeted engineering specifications now enter the generic IOC baseline workflow even before feature-specific translation is complete.",
            "LLM-backed prompt interpretation can be layered on top of this contract later.",
            "A Markdown plan artifact writer is available so orchestrated workflows can persist stage progress and failures.",
        ],
    }


@mcp.tool(description="Report the current Requirement Decomposition Agent scope and the deterministic contract version exposed to the IOC synthesis layer.")
def stm32_requirements_capabilities() -> dict[str, object]:
    return collect_requirements_capabilities()


"""
Anup: critical. 

This is the main tool function that clients call to convert a freeform STM32 prompt into a structured deterministic contract for IOC synthesis. The contract it produces is the main output of Phase 2 and the main input to the IOC builder workflow. The success of this function determines whether the rest of the workflow can run or not, so it's critical that it produces a valid contract for supported prompts and fails gracefully for unsupported prompts.

"""

@mcp.tool(description="Convert a supported STM32 feature prompt into the first deterministic contract consumed by the IOC Synthesis Agent.")
# Convert a prompt into a validated requirements-tool result and optionally persist the plan artifact when requested.
def stm32_requirements_decompose(prompt: str, persist_plan: bool = False) -> dict[str, object]:
    contract = build_requirements_contract(prompt)
    validation_errors = validate_contract(contract)
    supported_delivery = has_supported_delivery_increments(contract)
    result = {
        "server": "requirements",
        "success": not validation_errors and supported_delivery,
        "prompt": prompt,
        "contract": contract,
        "validation_errors": validation_errors,
        "message": (
            "Prompt decomposition produced a deterministic contract for IOC synthesis."
            if not validation_errors and supported_delivery
            else "Prompt decomposition recognized the board target but could not map the request to a supported feature family yet."
            if not validation_errors
            else "Prompt decomposition produced an invalid contract."
        ),
    }
    if persist_plan and not validation_errors:
        result["plan_artifact"] = persist_plan_artifact(contract)
        if not supported_delivery:
            requirements_failure = update_plan_status(
                str(contract["plan_file"]),
                stage="requirements",
                status="failed",
                message="The request targets a supported board, but this feature family is not implemented by the requirements agent yet.",
                details={
                    "open_questions": contract.get("open_questions"),
                    "supported_prompt_families": SUPPORTED_PROMPT_FAMILIES,
                },
            )
            result["plan_artifact"] = {
                "plan_path": requirements_failure["plan_path"],
                "plan": requirements_failure["plan"],
            }
    return result


@mcp.tool(description="Append a stage transition to the current Phase 2 plan artifact used by the Requirement Decomposition Agent.")
def stm32_requirements_update_plan(
    plan_file: str,
    stage: str,
    status: str,
    message: str,
) -> dict[str, object]:
    return update_plan_status(plan_file, stage=stage, status=status, message=message)


@mcp.tool(description="Refresh the live status fields of the current Phase 2 plan artifact without appending a new history event.")
def stm32_requirements_heartbeat_plan(
    plan_file: str,
    stage: str,
    message: str,
) -> dict[str, object]:
    return heartbeat_plan_status(plan_file, stage=stage, message=message)


@mcp.tool(description="Read the current live state of the Phase 2 plan artifact so callers can poll workflow progress during long operations.")
def stm32_requirements_plan_status(plan_file: str) -> dict[str, object]:
    return read_plan_status(plan_file)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
