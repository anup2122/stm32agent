from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ...requirements_ioc_contract import list_contract_increments


def with_effective_ioc_path(cubemx_request: dict[str, object], ioc_path: object) -> dict[str, object]:
    if not isinstance(ioc_path, str) or not ioc_path.strip():
        return dict(cubemx_request)
    updated_request = dict(cubemx_request)
    updated_request["ioc_path"] = ioc_path
    return updated_request


def ioc_plan_details(ioc_result: dict[str, object], mode: str) -> dict[str, object]:
    details: dict[str, object] = {
        "ioc_path": ioc_result.get("ioc_path"),
        "mode": mode,
    }
    cubemx_validation = ioc_result.get("cubemx_validation")
    if isinstance(cubemx_validation, dict):
        details["cubemx_validation"] = cubemx_validation
    return details


def summarize_ioc_validation(ioc_result: dict[str, object], mode: str) -> dict[str, object] | None:
    cubemx_validation = ioc_result.get("cubemx_validation")
    if not isinstance(cubemx_validation, dict):
        return None
    return {
        "mode": mode,
        "ioc_path": ioc_result.get("ioc_path"),
        "status": cubemx_validation.get("validation"),
        "success": bool(cubemx_validation.get("success")),
        "message": cubemx_validation.get("message"),
    }


def reusable_cubemx_result_from_ioc_validation(
    ioc_result: dict[str, object],
    effective_cubemx_request: dict[str, object],
) -> dict[str, object] | None:
    cubemx_validation = ioc_result.get("cubemx_validation")
    if not isinstance(cubemx_validation, dict):
        return None
    if not bool(cubemx_validation.get("success")) or cubemx_validation.get("validation") != "accepted":
        return None

    cubemx_result = cubemx_validation.get("cubemx_result")
    if not isinstance(cubemx_result, dict) or not bool(cubemx_result.get("success")):
        return None

    expected_project_path = str(effective_cubemx_request.get("project_path") or "")
    result_project_path = str(cubemx_result.get("project_path") or "")
    if expected_project_path and result_project_path and Path(expected_project_path).resolve() != Path(result_project_path).resolve():
        return None

    return cubemx_result


def summarize_execution_policy(contract: dict[str, object]) -> dict[str, object] | None:
    execution_policy = contract.get("execution_policy")
    if not isinstance(execution_policy, dict):
        return None
    return {
        "mode": execution_policy.get("mode"),
        "ioc_cubemx_validation": execution_policy.get("ioc_cubemx_validation"),
        "build_after_each_increment": execution_policy.get("build_after_each_increment"),
        "flash_after_successful_build": execution_policy.get("flash_after_successful_build"),
        "runtime_check_after_flash": execution_policy.get("runtime_check_after_flash"),
        "ask_user_on_repeated_failures": execution_policy.get("ask_user_on_repeated_failures"),
    }


def contract_feature_ids(contract: dict[str, object]) -> set[str]:
    feature_ids: set[str] = set()
    for key in ("core_features", "pluggable_features"):
        features = contract.get(key)
        if not isinstance(features, list):
            continue
        for feature in features:
            if not isinstance(feature, dict):
                continue
            feature_id = feature.get("id")
            if isinstance(feature_id, str) and feature_id.strip():
                feature_ids.add(feature_id.strip())
    return feature_ids


def contract_feature_lookup(contract: dict[str, object]) -> dict[str, dict[str, object]]:
    features: dict[str, dict[str, object]] = {}
    for key in ("core_features", "pluggable_features"):
        group = contract.get(key)
        if not isinstance(group, list):
            continue
        for feature in group:
            if not isinstance(feature, dict):
                continue
            feature_id = feature.get("id")
            if isinstance(feature_id, str) and feature_id.strip():
                features[feature_id] = feature
    return features


def contract_increment_records(contract: dict[str, object]) -> list[dict[str, object]]:
    increments = list_contract_increments(contract)
    if increments:
        return increments

    current_increment = contract.get("current_increment")
    if isinstance(current_increment, dict):
        return [deepcopy(current_increment)]
    return []


def interface_intent_lookup(contract: dict[str, object]) -> dict[str, dict[str, object]]:
    intents = contract.get("interface_intents")
    lookup: dict[str, dict[str, object]] = {}
    if not isinstance(intents, list):
        return lookup
    for intent in intents:
        if not isinstance(intent, dict):
            continue
        intent_id = intent.get("id")
        if isinstance(intent_id, str) and intent_id.strip():
            lookup[intent_id] = intent
    return lookup


def contract_for_increment(contract: dict[str, object], increment: dict[str, object]) -> dict[str, object]:
    increment_feature_ids = increment.get("feature_ids")
    selected_feature_ids = (
        {feature_id for feature_id in increment_feature_ids if isinstance(feature_id, str) and feature_id.strip()}
        if isinstance(increment_feature_ids, list)
        else set()
    )
    feature_lookup = contract_feature_lookup(contract)
    intent_lookup = interface_intent_lookup(contract)
    if not selected_feature_ids:
        contract_increments = contract_increment_records(contract)
        if len(contract_increments) <= 1:
            selected_feature_ids = set(feature_lookup.keys())

    selected_core_features: list[dict[str, object]] = []
    selected_pluggable_features: list[dict[str, object]] = []
    selected_intent_ids: set[str] = set()

    for feature_id in selected_feature_ids:
        feature = deepcopy(feature_lookup.get(feature_id, {"id": feature_id}))
        intent_ids = feature.get("interface_intent_ids")
        if isinstance(intent_ids, list):
            for intent_id in intent_ids:
                if isinstance(intent_id, str) and intent_id.strip():
                    selected_intent_ids.add(intent_id)
        if feature.get("kind") == "core":
            selected_core_features.append(feature)
        else:
            selected_pluggable_features.append(feature)

    increment_intent_ids = increment.get("interface_intent_ids")
    if isinstance(increment_intent_ids, list):
        for intent_id in increment_intent_ids:
            if isinstance(intent_id, str) and intent_id.strip():
                selected_intent_ids.add(intent_id)

    selected_interface_intents = [
        deepcopy(intent_lookup[intent_id])
        for intent_id in selected_intent_ids
        if intent_id in intent_lookup
    ]

    increment_contract = deepcopy(contract)
    increment_contract["core_features"] = selected_core_features
    increment_contract["pluggable_features"] = selected_pluggable_features
    increment_contract["interface_intents"] = selected_interface_intents
    increment_contract["increments"] = [deepcopy(increment)]
    increment_contract["current_increment"] = deepcopy(increment)
    return increment_contract


def _coerce_increment_records(value: object) -> list[dict[str, object]]:
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


def next_pending_increment(plan_state: dict[str, object] | None, contract: dict[str, object]) -> list[dict[str, object]]:
    if isinstance(plan_state, dict):
        plan_increments = _coerce_increment_records(plan_state.get("increments"))
        if plan_increments:
            return [increment for increment in plan_increments if increment.get("status") != "completed"]
    return contract_increment_records(contract)
