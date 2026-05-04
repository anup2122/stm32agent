"""Prompt-driven feature-delivery workflow.

This module owns the longest orchestrated path in the application layer. It is
called from ``orchestrator/server.py`` through this exact chain:

``stm32_orchestrate_feature_prompt``
-> ``run_feature_delivery_workflow``
-> ``orchestrate_feature_delivery``

Inside ``orchestrate_feature_delivery()``, the workflow proceeds in this order:

1. Call ``requirements_decompose(prompt, persist_plan=True)`` to convert the
    natural-language prompt into a deterministic requirements contract and plan
    artifact.
2. Call ``ensure_project_metadata_for_feature_contract(contract)`` to fill or
    normalize ``stm32-project.json`` fields required for the downstream flow.
3. Resolve the effective CubeMX request and derive the pending increments from
    the contract and current plan state.
4. For each pending increment, either:
    - construct a managed IOC file with ``construct_ioc_file(...)`` when no
      managed IOC exists yet, or
    - apply a deterministic change set with ``apply_ioc_change_set(...)`` when
      a managed IOC already exists.
5. Regenerate the CubeMX project with ``regenerate_project_internal(...)`` or
    reuse the CubeMX result already produced during IOC validation when possible.
6. Build the regenerated project with ``build_project(...)``.
7. Resolve the flash artifact with ``select_flash_artifact(...)``.
8. Flash the artifact with ``flash_firmware(...)``.
9. Optionally run post-flash runtime validation with
    ``run_runtime_validation_stage_fn(...)``.

Concrete tested prompt example:

``I have attached STM32L476Rg Nucleo device. write a project that will send
data from the device to pc and run and test it``

For that prompt, the requirements layer produces a contract targeting
``NUCLEO-L476RG`` with core feature ``core-uart-device-to-pc`` and first
increment ``increment-core-001``. This workflow then materializes the IOC,
regenerates the project, builds it, flashes it, and can continue into runtime
validation according to the execution policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable


PARTIAL_IOC_RECOVERY_MESSAGE = "could not complete the ioc file. use the partial ioc file, open in CubeMX and complete the remaining configuration. then call me again to complete the remaining process"


def _xml_references_from_ioc_result(ioc_result: dict[str, object]) -> list[dict[str, object]]:
    plan = ioc_result.get("plan")
    if not isinstance(plan, dict) and isinstance(ioc_result.get("ioc_result"), dict):
        nested_ioc_result = ioc_result["ioc_result"]
        plan = nested_ioc_result.get("plan") if isinstance(nested_ioc_result, dict) else None
    if not isinstance(plan, dict):
        return []
    references = plan.get("cubemx_xml_references")
    if not isinstance(references, list):
        return []
    return [reference for reference in references if isinstance(reference, dict)]


def partial_ioc_failure_details(
    *,
    ioc_path: object,
    result: dict[str, object],
    mode: str,
) -> dict[str, object]:
    return {
        "ioc_completion_status": "ioc_partial",
        "partial_ioc_path": ioc_path,
        "recovery_message": PARTIAL_IOC_RECOVERY_MESSAGE,
        "mode": mode,
        "cubemx_xml_references": _xml_references_from_ioc_result(result),
        "result": result,
    }


def firmware_behavior_gaps(increment_contract: dict[str, object]) -> list[str]:
    gaps: list[str] = []
    intents = increment_contract.get("interface_intents")
    if not isinstance(intents, list):
        return gaps

    for intent in intents:
        if not isinstance(intent, dict):
            continue
        intent_type = intent.get("type")
        intent_role = intent.get("role")
        gap: str | None = None
        if intent_type == "gpio" and intent_role == "led_output":
            gap = "IOC generation can configure the GPIO output, but requested LED runtime behavior needs firmware code in CubeMX user-code regions."
        elif intent_type == "gpio_exti":
            gap = "IOC generation can configure EXTI and NVIC, but requested button/event behavior needs firmware callback code in CubeMX user-code regions."
        elif intent_type == "uart" and intent_role in {"debug_console", "device_to_pc_tx"}:
            gap = "IOC generation can configure UART, but requested host-visible messages need firmware transmit code in CubeMX user-code regions."
        elif intent_type == "clock" and intent_role == "runtime_pll_source_switch":
            gap = "IOC generation can configure the clock baseline, but runtime PLL source switching needs firmware code in CubeMX user-code regions."
        elif intent_type == "power" and intent_role == "low_power_run":
            gap = "IOC generation can preserve the board baseline, but Low Power Run entry/exit, MSI range changes, regulator mode, and LED state behavior need firmware code in CubeMX user-code regions."
        elif intent_type == "analog" and intent_role == "opamp_pga_signal_chain":
            gap = "IOC generation currently preserves the board baseline, but OPAMP PGA, DAC waveform DMA, gain switching, low-power analog modes, and Cortex sleep sequencing need analog IOC mapping plus firmware code in CubeMX user-code regions."
        elif intent_type == "lptim" and intent_role == "external_counter_low_power_pwm":
            gap = "IOC generation currently preserves the board baseline, but LPTIM external-counter PWM, low-speed GPIO setup, STOP-mode entry, PC13 wakeup handling, and PWM stop behavior need LPTIM IOC mapping plus firmware code in CubeMX user-code regions."

        if gap is not None and gap not in gaps:
            gaps.append(gap)
    return gaps


async def orchestrate_feature_delivery(
    *,
    prompt: str,
    build_timeout_seconds: int,
    flash_timeout_seconds: int,
    cubemx_timeout_seconds: int,
    verify_mode: object,
    post_action: object,
    requirements_decompose: Callable[..., dict[str, object]],
    summarize_execution_policy: Callable[[dict[str, object]], dict[str, object] | None],
    ensure_project_metadata_for_feature_contract: Callable[[dict[str, object]], dict[str, object]],
    configured_cubemx_request: Callable[[], dict[str, object]],
    next_pending_increment: Callable[[dict[str, object] | None, dict[str, object]], list[dict[str, object]]],
    contract_for_increment: Callable[[dict[str, object], dict[str, object]], dict[str, object]],
    contract_feature_ids: Callable[[dict[str, object]], set[str]],
    ioc_plan_details: Callable[[dict[str, object], str], dict[str, object]],
    summarize_ioc_validation: Callable[[dict[str, object], str], dict[str, object] | None],
    with_effective_ioc_path: Callable[[dict[str, object], object], dict[str, object]],
    reusable_cubemx_result_from_ioc_validation: Callable[[dict[str, object], dict[str, object]], dict[str, object] | None],
    construct_ioc_file: Callable[..., dict[str, object]],
    apply_ioc_change_set: Callable[..., dict[str, object]],
    regenerate_project_internal: Callable[..., dict[str, object]],
    build_project: Callable[..., dict[str, object]],
    select_flash_artifact: Callable[[dict[str, object], str | None], tuple[str | None, str | None]],
    flash_firmware: Callable[..., Awaitable[dict[str, object]]],
    run_runtime_validation_stage_fn: Callable[..., Awaitable[dict[str, object]]],
    update_plan_status: Callable[..., dict[str, object]],
    read_plan_status: Callable[[str], dict[str, object]],
) -> dict[str, object]:
    requirements_result = requirements_decompose(prompt, persist_plan=True)
    contract = requirements_result.get("contract") if isinstance(requirements_result.get("contract"), dict) else None
    plan_artifact = requirements_result.get("plan_artifact") if isinstance(requirements_result.get("plan_artifact"), dict) else None
    plan_state = plan_artifact.get("plan") if isinstance(plan_artifact, dict) and isinstance(plan_artifact.get("plan"), dict) else None
    plan_file = str(contract.get("plan_file")) if isinstance(contract, dict) and isinstance(contract.get("plan_file"), str) else None
    execution_policy_summary = summarize_execution_policy(contract) if isinstance(contract, dict) else None

    if not requirements_result.get("success") or contract is None:
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": False,
            "stage": "requirements",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "message": "Requirements decomposition failed, so the workflow stopped before IOC synthesis.",
        }

    metadata_autofill = ensure_project_metadata_for_feature_contract(contract)
    cubemx_request = configured_cubemx_request()
    project_context = contract.get("project_context") if isinstance(contract.get("project_context"), dict) else {}
    configured_ioc_path = cubemx_request.get("ioc_path")
    effective_ioc_path = str(configured_ioc_path) if isinstance(configured_ioc_path, str) and configured_ioc_path.strip() else None
    source_ioc_path = (
        str(project_context.get("configured_source_ioc_path"))
        if isinstance(project_context.get("configured_source_ioc_path"), str) and str(project_context.get("configured_source_ioc_path")).strip()
        else None
    )
    execution_policy = contract.get("execution_policy") if isinstance(contract.get("execution_policy"), dict) else {}
    pending_increments = next_pending_increment(plan_state, contract)
    if not pending_increments:
        if plan_file:
            update_plan_status(
                plan_file,
                stage="workflow",
                status="completed",
                message="All planned increments were already completed for this prompt.",
                details={"completed_increment_ids": plan_state.get("completed_increment_ids") if isinstance(plan_state, dict) else []},
            )
        latest_plan_status = read_plan_status(plan_file) if plan_file else None
        return {
            "server": "orchestrator",
            "workflow": "feature_delivery",
            "success": True,
            "stage": "completed",
            "requirements_result": requirements_result,
            "execution_policy_summary": execution_policy_summary,
            "metadata_autofill": metadata_autofill,
            "increment_results": [],
            "plan_artifact": latest_plan_status.get("plan") if isinstance(latest_plan_status, dict) and latest_plan_status.get("success") else plan_state,
            "message": "The iterative workflow plan was already complete, so no additional increments were executed.",
        }

    def latest_plan_snapshot() -> dict[str, object] | None:
        if not plan_file:
            return plan_state
        status = read_plan_status(plan_file)
        if isinstance(status, dict) and status.get("success") and isinstance(status.get("plan"), dict):
            return status["plan"]
        return plan_state

    increment_results: list[dict[str, object]] = []
    last_ioc_result: dict[str, object] | None = None
    last_cubemx_result: dict[str, object] | None = None
    last_firmware_patch_result: dict[str, object] | None = None
    last_build_result: dict[str, object] | None = None
    last_flash_result: dict[str, object] | None = None
    last_runtime_validation_result: dict[str, object] | None = None
    last_ioc_validation_summary: dict[str, object] | None = None
    last_artifact_path: str | None = None
    last_artifact_source: str | None = None
    flash_skipped = False

    for increment in pending_increments:
        increment_id = str(increment.get("id") or "increment-unknown")
        increment_title = str(increment.get("title") or increment_id)
        increment_contract = contract_for_increment(contract, increment)
        increment_feature_ids = contract_feature_ids(increment_contract)
        managed_ioc_exists = bool(effective_ioc_path) and Path(str(effective_ioc_path)).is_file()
        should_construct_ioc = not managed_ioc_exists
        ioc_mode = "construct" if should_construct_ioc else "apply"
        ioc_source = str(project_context.get("ioc_handling") or ("copy_existing_ioc" if source_ioc_path else "download_from_github"))

        if plan_file:
            update_plan_status(
                plan_file,
                stage="increment",
                status="in_progress",
                message=f"Starting {increment_title}.",
                details={"increment": increment},
                increment_id=increment_id,
            )
            update_plan_status(
                plan_file,
                stage="ioc_builder",
                status="in_progress",
                message=(
                    "Materializing the managed IOC working copy for the current increment."
                    if should_construct_ioc
                    else "Applying the deterministic IOC change set for the current increment."
                ),
                details={
                    "increment": increment,
                    "ioc_path": effective_ioc_path,
                    "mode": ioc_mode,
                    "project_context": project_context,
                    "ioc_source": ioc_source,
                    "source_ioc_path": source_ioc_path,
                },
                increment_id=increment_id,
            )

        ioc_result = (
            construct_ioc_file(
                increment_contract,
                ioc_path=effective_ioc_path,
                overwrite=True,
                source_ioc_path=source_ioc_path,
            )
            if should_construct_ioc
            else apply_ioc_change_set(increment_contract, ioc_path=effective_ioc_path)
        )
        last_ioc_result = ioc_result
        last_ioc_validation_summary = summarize_ioc_validation(ioc_result, mode=ioc_mode)
        if isinstance(ioc_result.get("ioc_path"), str) and str(ioc_result.get("ioc_path")).strip():
            effective_ioc_path = str(ioc_result["ioc_path"])

        def report_cubemx_progress(progress: dict[str, object]) -> None:
            if not plan_file:
                return
            stage_name = str(progress.get("stage") or "cubemx")
            message = str(progress.get("message") or "CubeMX work is still in progress.")
            details = {key: value for key, value in progress.items() if key not in {"stage", "message"}}
            update_plan_status(
                plan_file,
                stage="cubemx" if stage_name.startswith("cubemx") else stage_name,
                status="completed" if stage_name == "cubemx_complete" and progress.get("success") else "in_progress",
                message=message,
                details=details or None,
                increment_id=increment_id,
                append_history=stage_name == "cubemx_complete",
            )

        if not ioc_result.get("success"):
            failure_details = partial_ioc_failure_details(
                ioc_path=ioc_result.get("ioc_path") or effective_ioc_path,
                result=ioc_result,
                mode=ioc_mode,
            )
            if plan_file:
                update_plan_status(
                    plan_file,
                    stage="ioc_builder",
                    status="failed",
                    message=PARTIAL_IOC_RECOVERY_MESSAGE,
                    details={
                        **ioc_plan_details(ioc_result, mode=ioc_mode),
                        **failure_details,
                    },
                    increment_id=increment_id,
                )
            latest_plan = latest_plan_snapshot()
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "ioc_builder",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "metadata_autofill": metadata_autofill,
                "increment": increment,
                "increment_results": increment_results,
                "ioc_result": ioc_result,
                "ioc_validation_summary": last_ioc_validation_summary,
                "ioc_completion_status": "ioc_partial",
                "partial_ioc_path": failure_details.get("partial_ioc_path"),
                "recovery_message": PARTIAL_IOC_RECOVERY_MESSAGE,
                "plan_artifact": latest_plan,
                "message": PARTIAL_IOC_RECOVERY_MESSAGE,
            }

        if plan_file:
            update_plan_status(
                plan_file,
                stage="cubemx",
                status="in_progress",
                message="Running CubeMX regeneration for the updated IOC file.",
                details=ioc_plan_details(ioc_result, mode=ioc_mode),
                increment_id=increment_id,
            )

        effective_cubemx_request = with_effective_ioc_path(cubemx_request, effective_ioc_path)
        reused_cubemx_run_result = reusable_cubemx_result_from_ioc_validation(ioc_result, effective_cubemx_request)
        if reused_cubemx_run_result is not None:
            cubemx_run_result = reused_cubemx_run_result
            if plan_file:
                update_plan_status(
                    plan_file,
                    stage="cubemx",
                    status="completed",
                    message="Reused the CubeMX regeneration already performed during IOC validation.",
                    details={"result": cubemx_run_result, "reused_from_ioc_validation": True},
                    increment_id=increment_id,
                    append_history=True,
                )
        else:
            cubemx_run_result = regenerate_project_internal(
                ioc_path=str(effective_cubemx_request["ioc_path"]),
                project_name=str(effective_cubemx_request["project_name"]),
                project_toolchain=str(effective_cubemx_request["project_toolchain"]),
                project_path=str(effective_cubemx_request["project_path"]),
                script_path=str(effective_cubemx_request["script_path"]) if isinstance(effective_cubemx_request.get("script_path"), str) else None,
                validate_build=False,
                timeout_seconds=cubemx_timeout_seconds,
                build_timeout_seconds=build_timeout_seconds,
                progress_callback=report_cubemx_progress,
            )
        cubemx_result = {
            "server": "orchestrator",
            "workflow": "cubemx_regeneration",
            "cubemx_request": effective_cubemx_request,
            "result": cubemx_run_result,
            "success": bool(cubemx_run_result.get("success")),
            "reused_from_ioc_validation": reused_cubemx_run_result is not None,
        }
        last_cubemx_result = cubemx_result
        if not cubemx_result.get("success"):
            failure_details = partial_ioc_failure_details(
                ioc_path=effective_cubemx_request.get("ioc_path") or effective_ioc_path,
                result={"ioc_result": ioc_result, "cubemx_result": cubemx_result},
                mode=ioc_mode,
            )
            if plan_file:
                update_plan_status(
                    plan_file,
                    stage="cubemx",
                    status="failed",
                    message=PARTIAL_IOC_RECOVERY_MESSAGE,
                    details=failure_details,
                    increment_id=increment_id,
                )
            latest_plan = latest_plan_snapshot()
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "cubemx",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "metadata_autofill": metadata_autofill,
                "increment": increment,
                "increment_results": increment_results,
                "ioc_result": ioc_result,
                "ioc_validation_summary": last_ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "ioc_completion_status": "ioc_partial",
                "partial_ioc_path": failure_details.get("partial_ioc_path"),
                "recovery_message": PARTIAL_IOC_RECOVERY_MESSAGE,
                "plan_artifact": latest_plan,
                "message": PARTIAL_IOC_RECOVERY_MESSAGE,
            }

        firmware_patch_result: dict[str, object] | None = None
        last_firmware_patch_result = firmware_patch_result

        if plan_file:
            update_plan_status(
                plan_file,
                stage="build",
                status="in_progress",
                message="Building the regenerated CubeIDE project for the current increment.",
                increment_id=increment_id,
            )

        build_result = build_project(timeout_seconds=build_timeout_seconds)
        last_build_result = build_result
        if not build_result.get("success"):
            if plan_file:
                update_plan_status(
                    plan_file,
                    stage="build",
                    status="failed",
                    message="Build failed after CubeMX regeneration.",
                    details={"result": build_result},
                    increment_id=increment_id,
                )
            latest_plan = latest_plan_snapshot()
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "build",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "metadata_autofill": metadata_autofill,
                "increment": increment,
                "increment_results": increment_results,
                "ioc_result": ioc_result,
                "ioc_validation_summary": last_ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "build_result": build_result,
                "plan_artifact": latest_plan,
                "message": "Build failed after regeneration, so the workflow stopped at the current increment.",
            }

        artifact_path, artifact_source = select_flash_artifact(build_result, None)
        last_artifact_path = artifact_path
        last_artifact_source = artifact_source
        if not artifact_path:
            if plan_file:
                update_plan_status(
                    plan_file,
                    stage="artifact_resolution",
                    status="failed",
                    message="Build succeeded but no artifact was available for flashing.",
                    details={"build_result": build_result},
                    increment_id=increment_id,
                )
            latest_plan = latest_plan_snapshot()
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "artifact_resolution",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "metadata_autofill": metadata_autofill,
                "increment": increment,
                "increment_results": increment_results,
                "ioc_result": ioc_result,
                "ioc_validation_summary": last_ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "build_result": build_result,
                "plan_artifact": latest_plan,
                "message": "Build succeeded, but no flash artifact could be resolved for the current increment.",
            }

        should_flash = bool(execution_policy.get("flash_after_successful_build", True))
        if not should_flash:
            flash_skipped = True
            if plan_file:
                update_plan_status(
                    plan_file,
                    stage="build",
                    status="completed",
                    message="Build completed and flash was skipped by execution policy.",
                    details={"artifact_path": artifact_path, "artifact_source": artifact_source, "flash_after_successful_build": False},
                    increment_id=increment_id,
                    append_history=True,
                )
                update_plan_status(
                    plan_file,
                    stage="increment",
                    status="completed",
                    message=f"{increment_title} completed successfully.",
                    details={"artifact_path": artifact_path, "artifact_source": artifact_source, "flash_skipped": True},
                    increment_id=increment_id,
                )

            increment_results.append(
                {
                    "increment": increment,
                    "ioc_result": ioc_result,
                    "ioc_validation_summary": last_ioc_validation_summary,
                    "cubemx_result": cubemx_result,
                    "firmware_patch_result": firmware_patch_result,
                    "build_result": build_result,
                    "artifact_path": artifact_path,
                    "artifact_source": artifact_source,
                    "flash_skipped": True,
                    "flash_result": None,
                    "runtime_validation_result": None,
                }
            )
            continue

        if plan_file:
            update_plan_status(
                plan_file,
                stage="flash",
                status="in_progress",
                message="Flashing the newly built artifact to the attached device.",
                details={"artifact_path": artifact_path, "artifact_source": artifact_source},
                increment_id=increment_id,
            )

        flash_result = await flash_firmware(
            file_path=artifact_path,
            timeout_seconds=flash_timeout_seconds,
            verify_mode=verify_mode,
            post_action=post_action,
        )
        last_flash_result = flash_result
        runtime_validation_enabled = bool(execution_policy.get("runtime_check_after_flash"))
        if plan_file:
            update_plan_status(
                plan_file,
                stage="flash",
                status="completed" if flash_result.get("success") else "failed",
                message=(
                    "Flash completed and runtime validation will start next."
                    if flash_result.get("success") and runtime_validation_enabled
                    else "Feature delivery completed successfully for the current increment."
                    if flash_result.get("success")
                    else "Flashing failed after a successful build."
                ),
                details={"result": flash_result},
                increment_id=increment_id,
            )

        if not flash_result.get("success"):
            latest_plan = latest_plan_snapshot()
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "flash",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "metadata_autofill": metadata_autofill,
                "increment": increment,
                "increment_results": increment_results,
                "ioc_result": ioc_result,
                "ioc_validation_summary": last_ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "build_result": build_result,
                "flash_result": flash_result,
                "artifact_source": artifact_source,
                "flash_skipped": False,
                "plan_artifact": latest_plan,
                "message": "The workflow reached the flash stage, but flashing failed for the current increment.",
            }

        runtime_validation_result: dict[str, object] | None = None
        if runtime_validation_enabled:
            runtime_validation_result = await run_runtime_validation_stage_fn(
                plan_file=plan_file,
                increment_id=increment_id,
                flash_timeout_seconds=flash_timeout_seconds,
            )
            if not runtime_validation_result.get("success"):
                last_runtime_validation_result = runtime_validation_result
                latest_plan = latest_plan_snapshot()
                return {
                    "server": "orchestrator",
                    "workflow": "feature_delivery",
                    "success": False,
                    "stage": "runtime_validation",
                    "requirements_result": requirements_result,
                    "execution_policy_summary": execution_policy_summary,
                    "increment": increment,
                    "increment_results": increment_results,
                    "ioc_result": ioc_result,
                    "ioc_validation_summary": last_ioc_validation_summary,
                    "cubemx_result": cubemx_result,
                    "build_result": build_result,
                    "flash_result": flash_result,
                    "runtime_validation_result": runtime_validation_result,
                    "artifact_source": artifact_source,
                    "flash_skipped": False,
                    "plan_artifact": latest_plan,
                    "message": "Flash succeeded, but runtime validation failed for the current increment.",
                }
        last_runtime_validation_result = runtime_validation_result

        behavior_gaps = firmware_behavior_gaps(increment_contract)
        if behavior_gaps:
            if plan_file:
                update_plan_status(
                    plan_file,
                    stage="firmware_behavior",
                    status="failed",
                    message="The IOC/CubeMX flow completed, but required firmware behavior is not implemented by IOC generation alone.",
                    details={"gaps": behavior_gaps},
                    increment_id=increment_id,
                )
            latest_plan = latest_plan_snapshot()
            return {
                "server": "orchestrator",
                "workflow": "feature_delivery",
                "success": False,
                "stage": "firmware_behavior",
                "requirements_result": requirements_result,
                "execution_policy_summary": execution_policy_summary,
                "increment": increment,
                "increment_results": increment_results,
                "ioc_result": ioc_result,
                "ioc_validation_summary": last_ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "build_result": build_result,
                "flash_result": flash_result,
                "runtime_validation_result": runtime_validation_result,
                "firmware_behavior_gaps": behavior_gaps,
                "artifact_source": artifact_source,
                "flash_skipped": False,
                "plan_artifact": latest_plan,
                "message": "The workflow reached hardware, but the requested behavior still needs a firmware-code generation path beyond IOC mutation.",
            }

        if plan_file:
            update_plan_status(
                plan_file,
                stage="increment",
                status="completed",
                message=f"{increment_title} completed successfully.",
                details={"artifact_path": artifact_path, "artifact_source": artifact_source},
                increment_id=increment_id,
            )

        increment_results.append(
            {
                "increment": increment,
                "ioc_result": ioc_result,
                "ioc_validation_summary": last_ioc_validation_summary,
                "cubemx_result": cubemx_result,
                "firmware_patch_result": firmware_patch_result,
                "build_result": build_result,
                "artifact_path": artifact_path,
                "artifact_source": artifact_source,
                "flash_skipped": False,
                "flash_result": flash_result,
                "runtime_validation_result": runtime_validation_result,
            }
        )

    if plan_file:
        update_plan_status(
            plan_file,
            stage="workflow",
            status="completed",
            message="All planned increments completed successfully.",
            details={"completed_increment_ids": [result["increment"]["id"] for result in increment_results]},
        )

    latest_plan = latest_plan_snapshot()
    return {
        "server": "orchestrator",
        "workflow": "feature_delivery",
        "success": True,
        "stage": "completed",
        "requirements_result": requirements_result,
        "execution_policy_summary": execution_policy_summary,
        "metadata_autofill": metadata_autofill,
        "increment_results": increment_results,
        "ioc_result": last_ioc_result,
        "ioc_validation_summary": last_ioc_validation_summary,
        "cubemx_result": last_cubemx_result,
        "firmware_patch_result": last_firmware_patch_result,
        "build_result": last_build_result,
        "artifact_path": last_artifact_path,
        "artifact_source": last_artifact_source,
        "flash_result": last_flash_result,
        "runtime_validation_result": last_runtime_validation_result,
        "flash_skipped": flash_skipped,
        "plan_artifact": latest_plan,
        "message": "The iterative feature delivery workflow completed successfully across all planned increments.",
    }
