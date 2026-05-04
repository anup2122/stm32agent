"""CubeMX regeneration workflows.

This module contains both the high-level orchestration entry for CubeMX-only
regeneration and the lower-level regeneration workflow used by the CubeMX MCP
server and the feature-delivery pipeline.

Exact ``orchestrate_cubemx_regeneration()`` chain:

1. ``configured_cubemx_request()`` resolves the effective CubeMX request from
    shared project metadata.
2. Required metadata is checked.
3. ``regenerate_project(...)`` is called with the resolved IOC path, project
    name, toolchain, project path, optional script path, and timeout values.

Exact ``regenerate_project_workflow()`` chain:

1. ``resolve_cubemx_project_inputs_fn(...)`` resolves IOC/project/script paths
    and completion markers.
2. ``resolve_cubemx_launcher_fn()`` resolves how CubeMX will actually be
    launched on the host.
3. ``resolve_generation_root_fn(...)`` and ``build_cubemx_script_fn(...)``
    prepare the output root and the CubeMX script contents.
4. ``collect_tree_state_fn(...)`` snapshots the file tree before generation.
5. ``run_cubemx_command_fn(...)`` launches CubeMX with the generated script.
6. ``wait_for_completion_markers_fn(...)`` waits for completion markers or file
    tree changes that prove generation finished.
7. ``diff_tree_state_fn(...)`` computes affected files.
8. ``collect_output_review_fn(...)`` reviews the generated output layout.
9. ``build_project_fn(...)`` optionally validates the generated project build.
10. ``write_cubemx_log_fn(...)`` records the full run, script, results, and
     file deltas to a log file.

The returned result becomes the CubeMX stage payload used by both standalone
CubeMX operations and the broader feature-delivery workflow.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable


def orchestrate_cubemx_regeneration(
    *,
    validate_build: bool,
    timeout_seconds: int,
    build_timeout_seconds: int,
    configured_cubemx_request: Callable[[], dict[str, object]],
    regenerate_project: Callable[..., dict[str, object]],
) -> dict[str, object]:
    cubemx_request = configured_cubemx_request()
    missing_fields = list(cubemx_request.get("missing_fields", [])) if isinstance(cubemx_request.get("missing_fields"), list) else []
    if missing_fields:
        return {
            "server": "orchestrator",
            "workflow": "cubemx_regeneration",
            "success": False,
            "cubemx_request": cubemx_request,
            "message": "Missing required CubeMX project metadata in stm32-project.jsonc: " + ", ".join(missing_fields),
        }

    result = regenerate_project(
        ioc_path=str(cubemx_request["ioc_path"]),
        project_name=str(cubemx_request["project_name"]),
        project_toolchain=str(cubemx_request["project_toolchain"]),
        project_path=str(cubemx_request["project_path"]),
        script_path=str(cubemx_request["script_path"]) if isinstance(cubemx_request.get("script_path"), str) else None,
        validate_build=validate_build,
        timeout_seconds=timeout_seconds,
        build_timeout_seconds=build_timeout_seconds,
    )
    return {
        "server": "orchestrator",
        "workflow": "cubemx_regeneration",
        "cubemx_request": cubemx_request,
        "result": result,
        "success": bool(result.get("success")),
    }


def regenerate_project_workflow(
    *,
    ioc_path: str | None,
    project_name: str | None,
    project_toolchain: str | None,
    project_path: str | None,
    script_path: str | None,
    output_root: str | None,
    validate_build: bool,
    timeout_seconds: int,
    build_timeout_seconds: int,
    progress_callback: Callable[[dict[str, object]], None] | None,
    resolve_cubemx_project_inputs_fn: Callable[..., dict[str, object]],
    resolve_cubemx_launcher_fn: Callable[[], dict[str, object]],
    resolve_generation_root_fn: Callable[[Path, str | None, str | None], Path],
    build_cubemx_script_fn: Callable[[Path, str, str, Path], str],
    regeneration_root_fn: Callable[[Path, str | None, str | None], Path | None],
    collect_tree_state_fn: Callable[[Path | None], dict[str, float]],
    diff_tree_state_fn: Callable[[dict[str, float], dict[str, float]], dict[str, list[str]]],
    run_cubemx_command_fn: Callable[..., dict[str, object]],
    wait_for_completion_markers_fn: Callable[..., dict[str, object]],
    collect_output_review_fn: Callable[[Path, Path], dict[str, object]],
    collect_build_layout_summary_fn: Callable[[Path], dict[str, object]],
    build_project_fn: Callable[..., dict[str, object]],
    create_log_path_fn: Callable[[str], Path],
    write_cubemx_log_fn: Callable[..., None],
) -> dict[str, object]:
    project_inputs = resolve_cubemx_project_inputs_fn(
        ioc_path=ioc_path,
        project_name=project_name,
        project_toolchain=project_toolchain,
        project_path=project_path,
        script_path=script_path,
        output_root=output_root,
    )
    ioc_discovery = project_inputs["ioc_discovery"]
    resolved_path = project_inputs.get("ioc_path")
    missing_fields = list(project_inputs.get("missing_fields", [])) if isinstance(project_inputs.get("missing_fields"), list) else []
    if not isinstance(resolved_path, str) or missing_fields:
        return {
            "success": False,
            "implemented": True,
            "server": "cubemx",
            "operation": "regenerate_project",
            "ioc_path": ioc_path,
            "ioc_discovery": ioc_discovery,
            "project_inputs": project_inputs,
            "message": (
                "Missing required CubeMX project metadata: " + ", ".join(missing_fields)
                if missing_fields
                else "No IOC file could be resolved for regeneration."
            ),
        }

    try:
        launcher = resolve_cubemx_launcher_fn()
    except FileNotFoundError as exc:
        return {
            "success": False,
            "implemented": True,
            "server": "cubemx",
            "operation": "regenerate_project",
            "ioc_path": resolved_path,
            "ioc_discovery": ioc_discovery,
            "message": str(exc),
        }

    resolved_ioc = Path(resolved_path)
    resolved_project_name = str(project_inputs["project_name"])
    resolved_project_toolchain = str(project_inputs["project_toolchain"])
    resolved_project_path = str(project_inputs["project_path"])
    resolved_script_path = str(project_inputs["script_path"])
    completion_marker_path = Path(str(project_inputs["completion_marker"]))
    completion_marker_paths = [
        Path(str(marker_path))
        for marker_path in project_inputs.get("completion_markers", [])
        if isinstance(marker_path, str) and marker_path.strip()
    ]
    if not completion_marker_paths:
        completion_marker_paths = [completion_marker_path]
    generation_root = resolve_generation_root_fn(resolved_ioc, output_root, resolved_project_path)
    generation_root.mkdir(parents=True, exist_ok=True)
    script_contents = build_cubemx_script_fn(
        resolved_ioc,
        resolved_project_name,
        resolved_project_toolchain,
        generation_root,
    )
    tree_root = regeneration_root_fn(resolved_ioc, output_root, resolved_project_path)
    before_state = collect_tree_state_fn(tree_root)
    persisted_script_path = Path(resolved_script_path)
    persisted_script_path.parent.mkdir(parents=True, exist_ok=True)
    marker_states_before = {
        marker_path.resolve(): (
            marker_path.is_file(),
            marker_path.stat().st_mtime if marker_path.is_file() else None,
        )
        for marker_path in completion_marker_paths
    }
    marker_exists_before = any(exists for exists, _ in marker_states_before.values())
    command = [*list(launcher["command_prefix"]), "-q", str(persisted_script_path)]
    completion_wait: dict[str, object] | None = None
    after_state: dict[str, float] | None = None
    affected_files: dict[str, list[str]] | None = None
    started_at = time.monotonic()
    try:
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "cubemx_launch",
                    "message": "Writing the CubeMX script and launching CubeMX.",
                    "script_path": str(persisted_script_path),
                    "marker_path": str(completion_marker_path),
                }
            )
        persisted_script_path.write_text(script_contents, encoding="utf-8")
        regeneration_result = run_cubemx_command_fn(
            command,
            timeout_seconds,
            progress_callback=progress_callback,
            completion_markers=completion_marker_paths,
            completion_tree_root=tree_root,
        )
        remaining_timeout = max(1, timeout_seconds - int(time.monotonic() - started_at))
        if regeneration_result.get("success"):
            if progress_callback is not None:
                progress_callback(
                    {
                        "stage": "cubemx_wait",
                        "message": "CubeMX returned successfully; waiting for the generated project marker.",
                        "marker_path": str(completion_marker_path),
                        "remaining_seconds": remaining_timeout,
                    }
                )
            completion_wait = wait_for_completion_markers_fn(
                completion_marker_paths,
                timeout_seconds=remaining_timeout,
                initial_states=marker_states_before,
                tree_root=tree_root,
                initial_tree_state=before_state,
                progress_callback=progress_callback,
            )
            if not completion_wait.get("success"):
                after_state = collect_tree_state_fn(tree_root)
                affected_files = diff_tree_state_fn(before_state, after_state)
                tree_changed = any(affected_files.values())
                if tree_changed and (marker_exists_before or any(marker_path.is_file() for marker_path in completion_marker_paths)):
                    completion_wait = {
                        "success": True,
                        "marker_path": str(completion_marker_path),
                        "checked_marker_paths": [str(path) for path in completion_marker_paths],
                        "status": "tree_changed",
                        "message": "CubeMX returned successfully and generated files changed even though the completion marker timestamp did not.",
                        "affected_files": affected_files,
                    }
                else:
                    regeneration_result = {
                        **regeneration_result,
                        "success": False,
                        "failure_reason": completion_wait.get("message"),
                    }
    except OSError as exc:
        regeneration_result = {
            "success": False,
            "exit_code": -3,
            "command": command,
            "stdout": "",
            "stderr": str(exc),
            "failure_reason": f"CubeMX script file could not be created: {exc}",
        }

    if progress_callback is not None:
        progress_callback(
            {
                "stage": "cubemx_complete",
                "message": "CubeMX regeneration stage finished.",
                "success": bool(regeneration_result.get("success")),
            }
        )

    if after_state is None:
        after_state = collect_tree_state_fn(tree_root)
    if affected_files is None:
        affected_files = diff_tree_state_fn(before_state, after_state)
    output_review: dict[str, object] | None = None
    if regeneration_result.get("success"):
        output_review = collect_output_review_fn(resolved_ioc, generation_root)
    build_validation: dict[str, object] | None = None
    if regeneration_result.get("success") and validate_build:
        build_validation = build_project_fn(timeout_seconds=build_timeout_seconds)

    log_path = create_log_path_fn("cubemx_regenerate")
    write_cubemx_log_fn(
        log_path,
        ioc_path=resolved_ioc,
        launcher=launcher,
        command=command,
        script_path=persisted_script_path,
        script_contents=script_contents,
        regeneration_result=regeneration_result,
        completion_wait=completion_wait,
        affected_files=affected_files,
        output_review=output_review,
        build_validation=build_validation,
    )
    return {
        "success": bool(regeneration_result.get("success")),
        "implemented": True,
        "server": "cubemx",
        "operation": "regenerate_project",
        "ioc_path": str(resolved_ioc),
        "output_root": str(generation_root),
        "project_name": resolved_project_name,
        "project_toolchain": resolved_project_toolchain,
        "project_path": resolved_project_path,
        "script_path": str(persisted_script_path),
        "completion_wait": completion_wait,
        "project_inputs": project_inputs,
        "ioc_discovery": ioc_discovery,
        "tool_path": launcher.get("tool_path"),
        "launch_kind": launcher.get("launch_kind"),
        "regeneration_result": regeneration_result,
        "output_review": output_review,
        "build_layout": collect_build_layout_summary_fn(generation_root),
        "build_validation": build_validation,
        "affected_files": affected_files,
        "log_file": str(log_path),
        "message": (
            f"CubeMX regeneration succeeded for {resolved_ioc.name}."
            if regeneration_result.get("success")
            else str(regeneration_result.get("failure_reason") or f"CubeMX regeneration failed for {resolved_ioc.name}. Inspect the CubeMX log for details.")
        ),
    }
