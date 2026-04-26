from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

from mcp.server.fastmcp import FastMCP

from ..application.services import (
    cubemx_host_service,
    cubemx_log_service,
    cubemx_runtime_service,
    cubemx_tool_service,
)
from .. import shared
from ..build import server as build_server
from ..ioc import metadata as ioc_metadata
from ..ioc import output_review as ioc_output_review
from ..ioc import project_paths as ioc_project_paths
from ..ioc import script_builder as ioc_script_builder
from ..tools import cubemx_adapter, cubemx_monitor

DEFAULT_CUBEMX_ENV_VAR = cubemx_adapter.DEFAULT_CUBEMX_ENV_VAR
DEFAULT_CUBEMX_EXECUTABLE_NAME = cubemx_adapter.DEFAULT_CUBEMX_EXECUTABLE_NAME
DEFAULT_CUBEMX_CANDIDATES = cubemx_adapter.DEFAULT_CUBEMX_CANDIDATES
IOC_SIGNAL_KEY_PATTERN = ioc_metadata.IOC_SIGNAL_KEY_PATTERN
IOC_GPIO_LABEL_KEY_PATTERN = ioc_metadata.IOC_GPIO_LABEL_KEY_PATTERN

mcp = FastMCP("stm32cubemx")


def load_firmware_metadata() -> dict[str, object]:
    return cubemx_host_service.load_firmware_metadata(load_project_metadata_fn=shared.load_project_metadata)


def load_build_metadata() -> dict[str, object]:
    return cubemx_host_service.load_build_metadata(load_project_metadata_fn=shared.load_project_metadata)


def load_cubemx_metadata() -> dict[str, object]:
    return cubemx_host_service.load_cubemx_metadata(load_project_metadata_fn=shared.load_project_metadata)


def configured_cubemx_log_path() -> Path | None:
    return cubemx_host_service.configured_cubemx_log_path(load_cubemx_metadata_fn=load_cubemx_metadata)


def cubemx_tool_entry() -> dict[str, object]:
    return cubemx_host_service.cubemx_tool_entry(load_tools_local_config_fn=shared.load_tools_local_config)


def configured_ioc_path() -> str | None:
    return ioc_project_paths.configured_ioc_path(load_firmware_metadata)


def read_ioc_project_manager_value(ioc_path: Path | None, key: str) -> str | None:
    return ioc_project_paths.read_ioc_project_manager_value(ioc_path, key)


def cubeide_project_dir_candidates(project_root: Path | None, ioc_path: Path | None, project_name: str | None = None) -> list[Path]:
    return ioc_project_paths.cubeide_project_dir_candidates(
        project_root,
        ioc_path,
        project_name,
        read_ioc_project_manager_value_fn=read_ioc_project_manager_value,
    )


def resolve_completion_marker(project_root: Path | None, ioc_path: Path | None, project_name: str | None = None) -> Path | None:
    return ioc_project_paths.resolve_completion_marker(
        project_root,
        ioc_path,
        project_name,
        cubeide_project_dir_candidates_fn=cubeide_project_dir_candidates,
    )


def resolve_completion_markers(project_root: Path | None, ioc_path: Path | None, project_name: str | None = None) -> list[Path]:
    return ioc_project_paths.resolve_completion_markers(
        project_root,
        ioc_path,
        project_name,
        cubeide_project_dir_candidates_fn=cubeide_project_dir_candidates,
    )


def discover_ioc_path(ioc_path: str | None = None) -> dict[str, object]:
    return ioc_project_paths.discover_ioc_path(
        ioc_path,
        configured_ioc_path_fn=configured_ioc_path,
    )


def default_ioc_path() -> str | None:
    return ioc_project_paths.default_ioc_path(discover_ioc_path_fn=discover_ioc_path)


def normalize_project_toolchain(value: object) -> str | None:
    return ioc_script_builder.normalize_project_toolchain(value)


def resolve_project_path(candidate: object) -> Path | None:
    return ioc_script_builder.resolve_project_path(candidate)


def resolve_cubemx_project_inputs(
    *,
    ioc_path: str | None = None,
    project_name: str | None = None,
    project_toolchain: str | None = None,
    project_path: str | None = None,
    script_path: str | None = None,
    output_root: str | None = None,
) -> dict[str, object]:
    return ioc_script_builder.resolve_cubemx_project_inputs(
        ioc_path=ioc_path,
        project_name=project_name,
        project_toolchain=project_toolchain,
        project_path=project_path,
        script_path=script_path,
        output_root=output_root,
        discover_ioc_path_fn=discover_ioc_path,
        load_cubemx_metadata_fn=load_cubemx_metadata,
        load_build_metadata_fn=load_build_metadata,
        resolve_completion_marker_fn=resolve_completion_marker,
        resolve_completion_markers_fn=resolve_completion_markers,
    )


def derive_cubemx_candidates() -> list[Path]:
    return cubemx_host_service.derive_cubemx_candidates(resolve_cubeide_path_fn=build_server.resolve_cubeide_path)


def derive_java_candidates() -> list[Path]:
    return cubemx_host_service.derive_java_candidates(
        resolve_cubeide_path_fn=build_server.resolve_cubeide_path,
        host_platform=shared.host_platform_name(),
    )


def resolve_java_path() -> str | None:
    return cubemx_host_service.resolve_java_path(
        resolve_cubeide_path_fn=build_server.resolve_cubeide_path,
        host_platform=shared.host_platform_name(),
    )


def discover_cubemx() -> dict[str, object]:
    return cubemx_host_service.discover_cubemx(
        host_platform=shared.host_platform_name(),
        load_tools_local_config_fn=shared.load_tools_local_config,
        resolve_candidate_path_fn=lambda candidate, config_path: shared.resolve_candidate_path(candidate, base_path=config_path),
        resolve_cubeide_path_fn=build_server.resolve_cubeide_path,
    )


def resolve_cubemx_launcher() -> dict[str, object]:
    return cubemx_host_service.resolve_cubemx_launcher(discover_cubemx_fn=discover_cubemx)


def parse_ioc_properties(ioc_path: Path) -> dict[str, str]:
    return ioc_metadata.parse_ioc_properties(ioc_path)


def normalize_signal_peripheral(signal: str) -> str | None:
    return ioc_metadata.normalize_signal_peripheral(signal)


def summarize_ioc(ioc_path: Path, properties: dict[str, str]) -> dict[str, object]:
    return ioc_metadata.summarize_ioc(ioc_path, properties)


def resolve_generation_root(ioc_path: Path, output_root: str | None = None, project_path: str | None = None) -> Path:
    return ioc_script_builder.resolve_generation_root(
        ioc_path,
        output_root,
        project_path,
        load_cubemx_metadata_fn=load_cubemx_metadata,
    )


def build_cubemx_script(ioc_path: Path, project_name: str, project_toolchain: str, project_path: Path) -> str:
    return ioc_script_builder.build_cubemx_script(ioc_path, project_name, project_toolchain, project_path)


def wait_for_completion_marker(
    marker_path: Path,
    *,
    timeout_seconds: int,
    initial_exists: bool,
    initial_mtime: float | None,
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
    poll_interval_seconds: float = 2.0,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    return cubemx_monitor.wait_for_completion_marker(
        marker_path,
        timeout_seconds=timeout_seconds,
        initial_exists=initial_exists,
        initial_mtime=initial_mtime,
        tree_root=tree_root,
        initial_tree_state=initial_tree_state,
        poll_interval_seconds=poll_interval_seconds,
        progress_callback=progress_callback,
        collect_tree_state_fn=collect_tree_state,
        diff_tree_state_fn=diff_tree_state,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    )


def wait_for_completion_markers(
    marker_paths: list[Path],
    *,
    timeout_seconds: int,
    initial_states: dict[Path, tuple[bool, float | None]],
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
    poll_interval_seconds: float = 2.0,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    return cubemx_monitor.wait_for_completion_markers(
        marker_paths,
        timeout_seconds=timeout_seconds,
        initial_states=initial_states,
        tree_root=tree_root,
        initial_tree_state=initial_tree_state,
        poll_interval_seconds=poll_interval_seconds,
        progress_callback=progress_callback,
        collect_tree_state_fn=collect_tree_state,
        diff_tree_state_fn=diff_tree_state,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    )


def capture_completion_marker_state(marker_paths: list[Path]) -> dict[Path, tuple[bool, float | None]]:
    return cubemx_monitor.capture_completion_marker_state(marker_paths)


def check_completion_markers(
    marker_paths: list[Path],
    initial_states: dict[Path, tuple[bool, float | None]],
    *,
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
) -> dict[str, object] | None:
    return cubemx_monitor.check_completion_markers(
        marker_paths,
        initial_states,
        tree_root=tree_root,
        initial_tree_state=initial_tree_state,
        collect_tree_state_fn=collect_tree_state,
        diff_tree_state_fn=diff_tree_state,
    )


def terminate_cubemx_process(process: subprocess.Popen[str]) -> None:
    cubemx_runtime_service.terminate_cubemx_process(
        process,
        host_platform=shared.host_platform_name(),
        subprocess_module=subprocess,
    )


def cubemx_script_reports_success(output_text: str) -> bool:
    return cubemx_runtime_service.cubemx_script_reports_success(output_text)


def cubemx_failure_reason(stdout: str, stderr: str) -> str | None:
    return cubemx_runtime_service.cubemx_failure_reason(stdout, stderr)


def run_cubemx_command_with_progress(
    command: list[str],
    timeout_seconds: int,
    *,
    progress_callback: Callable[[dict[str, object]], None] | None,
    completion_markers: list[Path] | None = None,
    completion_tree_root: Path | None = None,
    poll_interval_seconds: float = 2.0,
) -> dict[str, object]:
    return cubemx_runtime_service.run_cubemx_command_with_progress(
        command,
        timeout_seconds,
        progress_callback=progress_callback,
        completion_markers=completion_markers,
        completion_tree_root=completion_tree_root,
        poll_interval_seconds=poll_interval_seconds,
        host_platform=shared.host_platform_name(),
        configured_cubemx_log_path_resolver=configured_cubemx_log_path,
        capture_completion_marker_state_fn=capture_completion_marker_state,
        check_completion_markers_fn=check_completion_markers,
        collect_tree_state_fn=collect_tree_state,
        subprocess_module=subprocess,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    )


def run_cubemx_command(
    command: list[str],
    timeout_seconds: int,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    completion_markers: list[Path] | None = None,
    completion_tree_root: Path | None = None,
) -> dict[str, object]:
    return cubemx_runtime_service.run_cubemx_command(
        command,
        timeout_seconds,
        progress_callback=progress_callback,
        completion_markers=completion_markers,
        completion_tree_root=completion_tree_root,
        host_platform=shared.host_platform_name(),
        configured_cubemx_log_path_resolver=configured_cubemx_log_path,
        capture_completion_marker_state_fn=capture_completion_marker_state,
        check_completion_markers_fn=check_completion_markers,
        collect_tree_state_fn=collect_tree_state,
        subprocess_module=subprocess,
        sleep_fn=time.sleep,
        monotonic_fn=time.monotonic,
    )


def collect_tree_state(root: Path | None) -> dict[str, float]:
    return cubemx_monitor.collect_tree_state(root)


def diff_tree_state(before: dict[str, float], after: dict[str, float]) -> dict[str, list[str]]:
    return cubemx_monitor.diff_tree_state(before, after)


def regeneration_root(ioc_path: Path, output_root: str | None = None, project_path: str | None = None) -> Path | None:
    return ioc_script_builder.regeneration_root(
        ioc_path,
        output_root,
        project_path,
        resolve_generation_root_fn=resolve_generation_root,
        load_build_metadata_fn=load_build_metadata,
    )


def source_project_root(ioc_path: Path) -> Path:
    return ioc_output_review.source_project_root(ioc_path)


def list_relative_directory_entries(root: Path) -> list[str]:
    return ioc_output_review.list_relative_directory_entries(root)


def parse_mxproject_paths(mxproject_path: Path) -> dict[str, object]:
    return ioc_output_review.parse_mxproject_paths(mxproject_path)


def parse_cproject_include_paths(cproject_path: Path) -> list[str]:
    return ioc_output_review.parse_cproject_include_paths(cproject_path)


def parse_project_link_locations(project_path: Path) -> list[str]:
    return ioc_output_review.parse_project_link_locations(project_path)


def collect_output_review(ioc_path: Path, generation_root: Path) -> dict[str, object]:
    return ioc_output_review.collect_output_review(ioc_path, generation_root)


def collect_build_layout_summary(generation_root: Path) -> dict[str, object]:
    return ioc_output_review.collect_build_layout_summary(
        generation_root,
        load_build_metadata_fn=load_build_metadata,
    )


def write_cubemx_log(
    log_path: Path,
    *,
    ioc_path: Path,
    launcher: dict[str, object],
    command: list[str],
    script_path: Path,
    script_contents: str,
    regeneration_result: dict[str, object],
    completion_wait: dict[str, object] | None,
    affected_files: dict[str, list[str]],
    output_review: dict[str, object] | None,
    build_validation: dict[str, object] | None,
) -> None:
    cubemx_log_service.write_cubemx_log(
        log_path,
        ioc_path=ioc_path,
        launcher=launcher,
        command=command,
        script_path=script_path,
        script_contents=script_contents,
        regeneration_result=regeneration_result,
        completion_wait=completion_wait,
        affected_files=affected_files,
        output_review=output_review,
        build_validation=build_validation,
    )


@mcp.tool(description="Report CubeMX Part 1 host readiness, IOC discovery state, and whether deterministic IOC inspection/regeneration backends are available.")
def stm32_cubemx_capabilities() -> dict[str, object]:
    return cubemx_tool_service.report_cubemx_capabilities(
        discover_cubemx_fn=discover_cubemx,
        discover_ioc_path_fn=discover_ioc_path,
        load_project_metadata_fn=shared.load_project_metadata,
        load_tools_local_config_fn=shared.load_tools_local_config,
        summarize_config_status_fn=shared.summarize_config_status,
    )


@mcp.tool(description="Inspect an existing CubeMX IOC file by loading its properties-style metadata, peripheral list, pins, and project/toolchain summary.")
def stm32_cubemx_parse_ioc(ioc_path: str | None = None) -> dict[str, object]:
    return cubemx_tool_service.parse_cubemx_ioc(
        ioc_path=ioc_path,
        discover_ioc_path_fn=discover_ioc_path,
        parse_ioc_properties_fn=parse_ioc_properties,
        summarize_ioc_fn=summarize_ioc,
    )


def regenerate_project_internal(
    ioc_path: str | None = None,
    project_name: str | None = None,
    project_toolchain: str | None = None,
    project_path: str | None = None,
    script_path: str | None = None,
    output_root: str | None = None,
    validate_build: bool = True,
    timeout_seconds: int = 900,
    build_timeout_seconds: int = 600,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    return cubemx_tool_service.regenerate_cubemx_project(
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
        resolve_cubemx_project_inputs_fn=resolve_cubemx_project_inputs,
        resolve_cubemx_launcher_fn=resolve_cubemx_launcher,
        resolve_generation_root_fn=resolve_generation_root,
        build_cubemx_script_fn=build_cubemx_script,
        regeneration_root_fn=regeneration_root,
        collect_tree_state_fn=collect_tree_state,
        diff_tree_state_fn=diff_tree_state,
        run_cubemx_command_fn=run_cubemx_command,
        wait_for_completion_markers_fn=wait_for_completion_markers,
        collect_output_review_fn=collect_output_review,
        collect_build_layout_summary_fn=collect_build_layout_summary,
        build_project_fn=build_server.stm32_build_project,
        create_log_path_fn=shared.create_log_path,
        write_cubemx_log_fn=write_cubemx_log,
    )


@mcp.tool(description="Run deterministic CubeMX regeneration for an existing IOC file, record affected files, and optionally validate the regenerated project with the existing Build MCP.")
def stm32_cubemx_regenerate_project(
    ioc_path: str | None = None,
    project_name: str | None = None,
    project_toolchain: str | None = None,
    project_path: str | None = None,
    script_path: str | None = None,
    output_root: str | None = None,
    validate_build: bool = True,
    timeout_seconds: int = 900,
    build_timeout_seconds: int = 600,
) -> dict[str, object]:
    return regenerate_project_internal(
        ioc_path=ioc_path,
        project_name=project_name,
        project_toolchain=project_toolchain,
        project_path=project_path,
        script_path=script_path,
        output_root=output_root,
        validate_build=validate_build,
        timeout_seconds=timeout_seconds,
        build_timeout_seconds=build_timeout_seconds,
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
