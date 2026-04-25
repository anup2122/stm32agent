from __future__ import annotations

from copy import deepcopy

from .agent_task import AgentTask
from .intent_bundle import IntentBundle
from .observations import Observation
from .plan_state import PlanState
from .project_state import ProjectState


def plan_state_from_legacy_artifact(artifact: object) -> PlanState:
    return PlanState.from_dict(artifact)


def legacy_artifact_from_plan_state(plan_state: PlanState | object) -> dict[str, object]:
    if isinstance(plan_state, PlanState):
        return plan_state.to_dict()
    return PlanState.from_dict(plan_state).to_dict()


def observation_from_legacy_dict(payload: object) -> Observation:
    return Observation.from_dict(payload)


def legacy_dict_from_observation(observation: Observation | object) -> dict[str, object]:
    if isinstance(observation, Observation):
        return observation.to_dict()
    return Observation.from_dict(observation).to_dict()


def intent_bundle_from_legacy_parts(
    *,
    core_features: list[dict[str, object]] | None = None,
    pluggable_features: list[dict[str, object]] | None = None,
    interface_intents: list[dict[str, object]] | None = None,
    execution_policy: dict[str, object] | None = None,
    assumptions: list[str] | None = None,
    open_questions: list[str] | None = None,
    intent_kind: str = "feature_delivery",
    confidence: float | None = None,
) -> IntentBundle:
    return IntentBundle(
        intent_kind=intent_kind,
        confidence=confidence,
        core_requirements=deepcopy(core_features or []),
        optional_requirements=deepcopy(pluggable_features or []),
        interface_intents=deepcopy(interface_intents or []),
        runtime_expectations=deepcopy(execution_policy or {}),
        assumptions=list(assumptions or []),
        open_questions=list(open_questions or []),
    )


def legacy_requirements_dict_from_intent_bundle(bundle: IntentBundle | object) -> dict[str, object]:
    normalized = bundle if isinstance(bundle, IntentBundle) else IntentBundle.from_dict(bundle)
    return {
        "core_features": deepcopy(normalized.core_requirements),
        "pluggable_features": deepcopy(normalized.optional_requirements),
        "interface_intents": deepcopy(normalized.interface_intents),
        "execution_policy": deepcopy(normalized.runtime_expectations),
        "assumptions": list(normalized.assumptions),
        "open_questions": list(normalized.open_questions),
        "intent_kind": normalized.intent_kind,
        "confidence": normalized.confidence,
    }


def agent_task_from_legacy_contract(contract: object) -> AgentTask:
    if not isinstance(contract, dict):
        return AgentTask()

    target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    project_context = contract.get("project_context") if isinstance(contract.get("project_context"), dict) else {}
    execution_policy = contract.get("execution_policy") if isinstance(contract.get("execution_policy"), dict) else {}
    requested_actions = ["build"]
    if execution_policy.get("flash_after_successful_build", True):
        requested_actions.append("flash")
    if execution_policy.get("runtime_check_after_flash", True):
        requested_actions.append("runtime_check")

    return AgentTask(
        task_kind="feature_delivery",
        source_prompt=contract.get("source_prompt") if isinstance(contract.get("source_prompt"), str) else None,
        board_id=target.get("board_id") if isinstance(target.get("board_id"), str) else None,
        mcu=target.get("mcu") if isinstance(target.get("mcu"), str) else None,
        project_context_kind=project_context.get("kind") if isinstance(project_context.get("kind"), str) else None,
        existing_project_path=project_context.get("configured_source_ioc_path")
        if isinstance(project_context.get("configured_source_ioc_path"), str)
        else None,
        requested_actions=requested_actions,
        constraints={
            "toolchain": deepcopy(contract.get("defaults")),
            "execution_policy": deepcopy(execution_policy),
        },
    )


def project_state_from_project_metadata(project_metadata: object) -> ProjectState:
    if not isinstance(project_metadata, dict):
        return ProjectState()

    project_data = project_metadata.get("data") if isinstance(project_metadata.get("data"), dict) else project_metadata
    if not isinstance(project_data, dict):
        return ProjectState()

    board = project_data.get("board") if isinstance(project_data.get("board"), dict) else {}
    firmware = project_data.get("firmware") if isinstance(project_data.get("firmware"), dict) else {}
    cubemx = project_data.get("cubemx") if isinstance(project_data.get("cubemx"), dict) else {}
    build = project_data.get("build") if isinstance(project_data.get("build"), dict) else {}

    clock_summary: dict[str, object] = {}
    for section in (board, firmware, cubemx, build):
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if isinstance(key, str) and key.lower().startswith("clock"):
                clock_summary[key] = deepcopy(value)

    return ProjectState(
        project_name=project_data.get("project_name") if isinstance(project_data.get("project_name"), str) else None,
        project_root=cubemx.get("project_path") if isinstance(cubemx.get("project_path"), str) else None,
        managed_copy_root=cubemx.get("project_path") if isinstance(cubemx.get("project_path"), str) else None,
        ioc_path=firmware.get("ioc_path") if isinstance(firmware.get("ioc_path"), str) else None,
        script_path=cubemx.get("script_path") if isinstance(cubemx.get("script_path"), str) else None,
        cubeide_project_path=build.get("project_path") if isinstance(build.get("project_path"), str) else None,
        workspace_path=build.get("workspace") if isinstance(build.get("workspace"), str) else None,
        build_artifact_path=build.get("artifact") if isinstance(build.get("artifact"), str) else firmware.get("default_artifact") if isinstance(firmware.get("default_artifact"), str) else None,
        board_id=board.get("name") if isinstance(board.get("name"), str) else None,
        mcu=board.get("mcu") if isinstance(board.get("mcu"), str) else None,
        clock_summary=clock_summary,
        extra={
            "project_toolchain": deepcopy(project_data.get("project_toolchain")),
            "build_system": deepcopy(project_data.get("build_system")),
            "default_configuration": deepcopy(project_data.get("default_configuration")),
        },
    )
