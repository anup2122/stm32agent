from __future__ import annotations

from copy import deepcopy

CONTRACT_VERSION = "2026-04-24.phase3.v1"
PLAN_VERSION = "2026-04-24.phase3.plan.v1"
DEFAULT_PLAN_FILE_NAME = "plan.md"
DEFAULT_TOOLCHAIN = "STM32CubeIDE"


def default_execution_policy() -> dict[str, object]:
    return {
        "mode": "incremental",
        "build_after_each_increment": True,
        "fix_build_before_proceeding": True,
        "flash_after_successful_build": True,
        "runtime_check_after_flash": True,
        "fix_runtime_before_next_increment": True,
        "ask_user_on_repeated_failures": True,
        "ioc_cubemx_validation": "best_effort",
    }


def default_planning_policy() -> dict[str, object]:
    return {
        "horizon": "long_horizon",
        "core_first": True,
        "increment_strategy": "single_slice",
        "feature_progression": "core_then_pluggable",
        "plan_format": "markdown_embedded_json",
        "status_file": DEFAULT_PLAN_FILE_NAME,
    }


def make_contract(
    *,
    source_prompt: str,
    board_id: str,
    mcu: str,
    core_features: list[dict[str, object]],
    pluggable_features: list[dict[str, object]],
    current_increment: dict[str, object],
    interface_intents: list[dict[str, object]],
    defaults: dict[str, object] | None = None,
    execution_policy: dict[str, object] | None = None,
    assumptions: list[str] | None = None,
    open_questions: list[str] | None = None,
    plan_file: str,
) -> dict[str, object]:
    normalized_defaults = {
        "toolchain": DEFAULT_TOOLCHAIN,
        "project_style": "ioc_incremental",
        "language": "c",
        **(defaults or {}),
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "source_prompt": source_prompt,
        "target": {
            "board_id": board_id,
            "mcu": mcu,
        },
        "defaults": normalized_defaults,
        "planning": default_planning_policy(),
        "execution_policy": {
            **default_execution_policy(),
            **(execution_policy or {}),
        },
        "core_features": deepcopy(core_features),
        "pluggable_features": deepcopy(pluggable_features),
        "current_increment": deepcopy(current_increment),
        "interface_intents": deepcopy(interface_intents),
        "assumptions": list(assumptions or []),
        "open_questions": list(open_questions or []),
        "plan_file": plan_file,
    }


def validate_contract(contract: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(contract, dict):
        return ["Contract must be a dictionary."]

    if contract.get("contract_version") != CONTRACT_VERSION:
        errors.append(f"contract_version must be '{CONTRACT_VERSION}'.")

    source_prompt = contract.get("source_prompt")
    if not isinstance(source_prompt, str) or not source_prompt.strip():
        errors.append("source_prompt is required.")

    target = contract.get("target")
    if not isinstance(target, dict):
        errors.append("target is required.")
    else:
        board_id = target.get("board_id")
        if not isinstance(board_id, str) or not board_id.strip():
            errors.append("target.board_id is required.")
        mcu = target.get("mcu")
        if not isinstance(mcu, str) or not mcu.strip():
            errors.append("target.mcu is required.")

    defaults = contract.get("defaults")
    if not isinstance(defaults, dict):
        errors.append("defaults is required.")
    else:
        toolchain = defaults.get("toolchain")
        if not isinstance(toolchain, str) or not toolchain.strip():
            errors.append("defaults.toolchain is required.")

    planning = contract.get("planning")
    if not isinstance(planning, dict):
        errors.append("planning is required.")
    else:
        horizon = planning.get("horizon")
        if not isinstance(horizon, str) or not horizon.strip():
            errors.append("planning.horizon is required.")
        increment_strategy = planning.get("increment_strategy")
        if not isinstance(increment_strategy, str) or not increment_strategy.strip():
            errors.append("planning.increment_strategy is required.")

    execution_policy = contract.get("execution_policy")
    if not isinstance(execution_policy, dict):
        errors.append("execution_policy is required.")
    else:
        ioc_cubemx_validation = execution_policy.get("ioc_cubemx_validation")
        if ioc_cubemx_validation not in {"best_effort", "required"}:
            errors.append("execution_policy.ioc_cubemx_validation must be 'best_effort' or 'required'.")

    for field_name in ("core_features", "pluggable_features", "interface_intents"):
        value = contract.get(field_name)
        if not isinstance(value, list):
            errors.append(f"{field_name} must be a list.")

    current_increment = contract.get("current_increment")
    if not isinstance(current_increment, dict):
        errors.append("current_increment is required.")
    else:
        increment_id = current_increment.get("id")
        if not isinstance(increment_id, str) or not increment_id.strip():
            errors.append("current_increment.id is required.")
        feature_ids = current_increment.get("feature_ids")
        if not isinstance(feature_ids, list) or not all(isinstance(item, str) and item.strip() for item in feature_ids):
            errors.append("current_increment.feature_ids must be a non-empty string list.")

    assumptions = contract.get("assumptions")
    if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
        errors.append("assumptions must be a list of strings.")

    open_questions = contract.get("open_questions")
    if not isinstance(open_questions, list) or not all(isinstance(item, str) for item in open_questions):
        errors.append("open_questions must be a list of strings.")

    plan_file = contract.get("plan_file")
    if not isinstance(plan_file, str) or not plan_file.strip():
        errors.append("plan_file is required.")

    return errors