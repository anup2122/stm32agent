from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..workflows import cubemx_regeneration as cubemx_regeneration_workflow
from . import cubemx_inspection_service


def report_cubemx_capabilities(
    *,
    discover_cubemx_fn: Callable[[], dict[str, object]],
    discover_ioc_path_fn: Callable[[], dict[str, object]],
    load_project_metadata_fn: Callable[[], dict[str, object]],
    load_tools_local_config_fn: Callable[[], dict[str, object]],
    summarize_config_status_fn: Callable[[dict[str, object]], dict[str, object]],
) -> dict[str, object]:
    return cubemx_inspection_service.build_cubemx_capabilities(
        discover_cubemx_fn=discover_cubemx_fn,
        discover_ioc_path_fn=discover_ioc_path_fn,
        load_project_metadata_fn=load_project_metadata_fn,
        load_tools_local_config_fn=load_tools_local_config_fn,
        summarize_config_status_fn=summarize_config_status_fn,
    )


def parse_cubemx_ioc(
    *,
    ioc_path: str | None,
    discover_ioc_path_fn: Callable[[str | None], dict[str, object]],
    parse_ioc_properties_fn: Callable[[Path], dict[str, str]],
    summarize_ioc_fn: Callable[[Path, dict[str, str]], dict[str, object]],
) -> dict[str, object]:
    return cubemx_inspection_service.parse_ioc_summary(
        ioc_path=ioc_path,
        discover_ioc_path_fn=discover_ioc_path_fn,
        parse_ioc_properties_fn=parse_ioc_properties_fn,
        summarize_ioc_fn=summarize_ioc_fn,
    )


def regenerate_cubemx_project(
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
    return cubemx_regeneration_workflow.regenerate_project_workflow(
        ioc_path=ioc_path,
        project_name=project_name,
        project_toolchain=project_toolchain,
        project_path=project_path,
        script_path=script_path,
        output_root=output_root,
        validate_build=validate_build,
        timeout_seconds=timeout_seconds,
        build_timeout_seconds=build_timeout_seconds,
        progress_callback=progress_callback,
        resolve_cubemx_project_inputs_fn=resolve_cubemx_project_inputs_fn,
        resolve_cubemx_launcher_fn=resolve_cubemx_launcher_fn,
        resolve_generation_root_fn=resolve_generation_root_fn,
        build_cubemx_script_fn=build_cubemx_script_fn,
        regeneration_root_fn=regeneration_root_fn,
        collect_tree_state_fn=collect_tree_state_fn,
        diff_tree_state_fn=diff_tree_state_fn,
        run_cubemx_command_fn=run_cubemx_command_fn,
        wait_for_completion_markers_fn=wait_for_completion_markers_fn,
        collect_output_review_fn=collect_output_review_fn,
        collect_build_layout_summary_fn=collect_build_layout_summary_fn,
        build_project_fn=build_project_fn,
        create_log_path_fn=create_log_path_fn,
        write_cubemx_log_fn=write_cubemx_log_fn,
    )


def orchestrate_cubemx_regeneration(
    *,
    validate_build: bool,
    timeout_seconds: int,
    build_timeout_seconds: int,
    configured_cubemx_request_fn: Callable[[], dict[str, object]],
    regenerate_project_fn: Callable[..., dict[str, object]],
) -> dict[str, object]:
    return cubemx_regeneration_workflow.orchestrate_cubemx_regeneration(
        validate_build=validate_build,
        timeout_seconds=timeout_seconds,
        build_timeout_seconds=build_timeout_seconds,
        configured_cubemx_request=configured_cubemx_request_fn,
        regenerate_project=regenerate_project_fn,
    )
