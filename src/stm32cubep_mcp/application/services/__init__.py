"""Shared application services."""

from .artifact_service import select_flash_artifact
from .project_config_service import (
    configured_cubemx_request,
    configured_firmware_artifact,
    derived_project_paths,
    ensure_project_metadata_for_feature_contract,
    inferred_project_name,
    inferred_project_toolchain,
    merge_project_metadata_with_prompt_fallback,
    normalize_cubemx_toolchain,
    normalize_project_config,
    workspace_project_metadata_path,
)
from .routing_service import WorkflowRoute, classify_prompt, extract_file_path, is_debug_question
from .workflow_state import (
    contract_feature_ids,
    contract_feature_lookup,
    contract_for_increment,
    contract_increment_records,
    interface_intent_lookup,
    ioc_plan_details,
    next_pending_increment,
    reusable_cubemx_result_from_ioc_validation,
    summarize_execution_policy,
    summarize_ioc_validation,
    with_effective_ioc_path,
)

__all__ = [
    "WorkflowRoute",
    "classify_prompt",
    "extract_file_path",
    "is_debug_question",
    "select_flash_artifact",
    "normalize_cubemx_toolchain",
    "workspace_project_metadata_path",
    "derived_project_paths",
    "inferred_project_name",
    "inferred_project_toolchain",
    "merge_project_metadata_with_prompt_fallback",
    "ensure_project_metadata_for_feature_contract",
    "normalize_project_config",
    "configured_cubemx_request",
    "configured_firmware_artifact",
    "with_effective_ioc_path",
    "ioc_plan_details",
    "summarize_ioc_validation",
    "reusable_cubemx_result_from_ioc_validation",
    "summarize_execution_policy",
    "contract_feature_ids",
    "contract_feature_lookup",
    "contract_increment_records",
    "interface_intent_lookup",
    "contract_for_increment",
    "next_pending_increment",
]
