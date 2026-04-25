from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .. import shared
from .policy import derive_execution_policy
from ..requirements_ioc_contract import CONTRACT_VERSION, DEFAULT_PLAN_FILE_NAME, DEFAULT_TOOLCHAIN, PLAN_VERSION, make_contract, validate_contract

mcp = FastMCP("stm32requirements")

SUPPORTED_PROMPT_FAMILIES = [
    "NUCLEO-L476RG device-to-PC serial transmit",
    "NUCLEO-L476RG LED blink",
    "NUCLEO-L476RG button event to PC",
]

PLAN_STATE_START = "<!-- plan-state:start -->"
PLAN_STATE_END = "<!-- plan-state:end -->"


def detect_target(prompt: str) -> tuple[str | None, str | None]:
    lowered = prompt.strip().lower()
    if any(token in lowered for token in ("nucleo-l476rg", "stm32l476rg", "stm32l476rg nucleo", "stm32l476rg nucleo device")):
        return "NUCLEO-L476RG", "STM32L476RGTx"
    return None, None


def plan_feature_split(prompt: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[str], list[str]]:
    lowered = prompt.strip().lower()
    core_features: list[dict[str, object]] = []
    pluggable_features: list[dict[str, object]] = []
    interface_intents: list[dict[str, object]] = []
    assumptions: list[str] = []
    open_questions: list[str] = []

    if any(token in lowered for token in ("blink", "led", "toggle")):
        core_features.append(
            {
                "id": "core-led-blink",
                "title": "Blink user LED",
                "kind": "core",
                "summary": "Drive the on-board LED through a GPIO output for visible runtime behavior.",
            }
        )
        interface_intents.append(
            {
                "id": "iface-led-pa5",
                "type": "gpio",
                "role": "led_output",
                "pin": "PA5",
                "label": "LD2 [green Led]",
                "signal": "GPIO_Output",
            }
        )
        assumptions.append("PA5 is the default user LED output pin on NUCLEO-L476RG.")

    if "pc" in lowered and any(token in lowered for token in ("send data", "send", "transmit", "printf", "uart", "serial")):
        core_features.append(
            {
                "id": "core-uart-device-to-pc",
                "title": "Send data to PC",
                "kind": "core",
                "summary": "Transmit device data to the host PC over the board's default serial path.",
            }
        )
        interface_intents.append(
            {
                "id": "iface-uart-host-console",
                "type": "uart",
                "role": "device_to_pc_tx",
                "instance_preference": "USART2",
                "baud_rate": 115200,
                "reason": "Default host serial path for NUCLEO-L476RG prompts that ask for device-to-PC output.",
            }
        )
        assumptions.append("USART2 over the ST-LINK virtual COM path is the default device-to-PC transport for NUCLEO-L476RG.")
    if any(token in lowered for token in ("button", "pushbutton", "blue button", "user button")):
        pluggable_features.append(
            {
                "id": "pluggable-user-button-event",
                "title": "User button event",
                "kind": "pluggable",
                "summary": "Capture the on-board button input so firmware can react to a human-triggered event.",
            }
        )
        interface_intents.append(
            {
                "id": "iface-button-pc13",
                "type": "gpio_exti",
                "role": "user_button",
                "pin": "PC13",
                "label": "B1 [Blue PushButton]",
                "signal": "GPXTI13",
            }
        )
        assumptions.append("PC13 is the default user button input pin on NUCLEO-L476RG.")

    if not core_features and not interface_intents:
        open_questions.append("The initial Phase 2 scaffold only recognizes the first supported device-to-PC serial prompt family.")

    if any(token in lowered for token in ("test", "run and test", "verify", "validate")):
        pluggable_features.append(
            {
                "id": "pluggable-runtime-check",
                "title": "Runtime verification",
                "kind": "pluggable",
                "summary": "Run flash-time and post-flash verification after the core serial output feature succeeds.",
            }
        )

    return core_features, pluggable_features, interface_intents, assumptions, open_questions


def resolve_plan_path(plan_file: str) -> Path:
    candidate = Path(plan_file).expanduser()
    if candidate.is_absolute():
        return candidate
    return (Path.cwd() / candidate).resolve()


def configured_ioc_path() -> Path | None:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    if not isinstance(project_data, dict):
        return None
    firmware = project_data.get("firmware")
    if not isinstance(firmware, dict):
        return None
    ioc_path = firmware.get("ioc_path")
    if not isinstance(ioc_path, str) or not ioc_path.strip():
        return None
    candidate = Path(ioc_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (Path.cwd() / candidate).resolve()


def default_plan_file() -> str:
    ioc_path = configured_ioc_path()
    if ioc_path is not None:
        return str((ioc_path.parent / DEFAULT_PLAN_FILE_NAME).resolve())
    return str((Path.cwd() / "generated" / DEFAULT_PLAN_FILE_NAME).resolve())


def initial_plan_artifact(contract: dict[str, object]) -> dict[str, object]:
    created_at = datetime.now(timezone.utc).isoformat()
    return {
        "plan_version": PLAN_VERSION,
        "contract_version": contract["contract_version"],
        "source_prompt": contract["source_prompt"],
        "target": contract["target"],
        "defaults": contract["defaults"],
        "planning": contract["planning"],
        "current_increment": contract["current_increment"],
        "core_features": contract["core_features"],
        "pluggable_features": contract["pluggable_features"],
        "execution_policy": contract["execution_policy"],
        "assumptions": contract["assumptions"],
        "open_questions": contract["open_questions"],
        "workflow_status": "planned",
        "current_stage": "requirements",
        "current_stage_message": "Requirements decomposition created the first deterministic contract.",
        "current_stage_details": {
            "current_increment": contract["current_increment"],
        },
        "failure_count": 0,
        "stage_history": [],
        "created_utc": created_at,
        "last_updated_utc": created_at,
        "last_heartbeat_utc": created_at,
    }


def render_plan_markdown(artifact: dict[str, object]) -> str:
    target = artifact.get("target") if isinstance(artifact.get("target"), dict) else {}
    current_increment = artifact.get("current_increment") if isinstance(artifact.get("current_increment"), dict) else {}
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
        f"- Board: `{target.get('board_id', 'unknown')}`",
        f"- MCU: `{target.get('mcu', 'unknown')}`",
        "",
        "## Current Increment",
        f"- ID: `{current_increment.get('id', 'unknown')}`",
        f"- Title: {current_increment.get('title', 'n/a')}",
        f"- Feature IDs: {', '.join(current_increment.get('feature_ids', [])) if isinstance(current_increment.get('feature_ids'), list) else 'n/a'}",
        "",
        "## Execution Policy",
        f"- Mode: `{execution_policy.get('mode', 'unknown')}`",
        f"- IOC CubeMX validation: `{execution_policy.get('ioc_cubemx_validation', 'unknown')}`",
        f"- Flash after successful build: `{execution_policy.get('flash_after_successful_build', 'unknown')}`",
        f"- Runtime check after flash: `{execution_policy.get('runtime_check_after_flash', 'unknown')}`",
        f"- Ask user on repeated failures: `{execution_policy.get('ask_user_on_repeated_failures', 'unknown')}`",
        "",
        "## Open Questions",
    ]
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
    plan_path = resolve_plan_path(str(contract["plan_file"]))
    artifact = initial_plan_artifact(contract)
    artifact["stage_history"].append(
        {
            "stage": "requirements",
            "status": "completed",
            "message": "Requirements decomposition completed and produced the initial deterministic contract.",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    write_plan_artifact(plan_path, artifact)
    return {
        "plan_path": str(plan_path),
        "plan": artifact,
    }


def update_plan_status(
    plan_file: str,
    *,
    stage: str,
    status: str,
    message: str,
    details: dict[str, object] | None = None,
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
    artifact["current_stage_details"] = details or {}
    artifact["last_updated_utc"] = datetime.now(timezone.utc).isoformat()
    artifact["last_heartbeat_utc"] = artifact["last_updated_utc"]
    if status == "failed":
        artifact["failure_count"] = int(artifact.get("failure_count", 0)) + 1

    event: dict[str, object] = {
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp_utc": artifact["last_updated_utc"],
    }
    if details is not None:
        event["details"] = details
    if append_history:
        artifact.setdefault("stage_history", []).append(event)
    write_plan_artifact(plan_path, artifact)
    return {
        "plan_path": str(plan_path),
        "plan": artifact,
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
        "stage_history_count": len(plan.get("stage_history", [])) if isinstance(plan.get("stage_history"), list) else 0,
        "plan": plan,
    }


def build_requirements_contract(prompt: str) -> dict[str, object]:
    board_id, mcu = detect_target(prompt)
    core_features, pluggable_features, interface_intents, assumptions, open_questions = plan_feature_split(prompt)

    if not board_id or not mcu:
        open_questions.append("A supported board or MCU identifier is required. Phase 2 currently supports NUCLEO-L476RG prompt decomposition only.")
        board_id = board_id or "unknown"
        mcu = mcu or "unknown"

    current_increment = {
        "id": "increment-core-001",
        "title": "Enable the first core feature increment",
        "feature_ids": [feature["id"] for feature in core_features],
        "kind": "core",
    }
    contract = make_contract(
        source_prompt=prompt,
        board_id=board_id,
        mcu=mcu,
        core_features=core_features,
        pluggable_features=pluggable_features,
        current_increment=current_increment,
        interface_intents=interface_intents,
        defaults={
            "toolchain": DEFAULT_TOOLCHAIN,
            "project_style": "ioc_incremental",
        },
        execution_policy=derive_execution_policy(prompt),
        assumptions=assumptions,
        open_questions=open_questions,
        plan_file=default_plan_file(),
    )
    return contract


def collect_requirements_capabilities() -> dict[str, object]:
    return {
        "server": "requirements",
        "implemented": True,
        "supported_prompt_families": SUPPORTED_PROMPT_FAMILIES,
        "contract_version": CONTRACT_VERSION,
        "default_toolchain": DEFAULT_TOOLCHAIN,
        "notes": [
            "This Phase 2 scaffold produces a deterministic contract for IOC synthesis.",
            "LLM-backed prompt interpretation can be layered on top of this contract later.",
            "A Markdown plan artifact writer is available so orchestrated workflows can persist stage progress and failures.",
        ],
    }


@mcp.tool(description="Report the current Requirement Decomposition Agent scope and the deterministic contract version exposed to the IOC synthesis layer.")
def stm32_requirements_capabilities() -> dict[str, object]:
    return collect_requirements_capabilities()


@mcp.tool(description="Convert a supported STM32 feature prompt into the first deterministic contract consumed by the IOC Synthesis Agent.")
def stm32_requirements_decompose(prompt: str, persist_plan: bool = False) -> dict[str, object]:
    contract = build_requirements_contract(prompt)
    validation_errors = validate_contract(contract)
    result = {
        "server": "requirements",
        "success": not validation_errors,
        "prompt": prompt,
        "contract": contract,
        "validation_errors": validation_errors,
        "message": (
            "Prompt decomposition produced a deterministic contract for IOC synthesis."
            if not validation_errors
            else "Prompt decomposition produced an invalid contract."
        ),
    }
    if persist_plan and not validation_errors:
        result["plan_artifact"] = persist_plan_artifact(contract)
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