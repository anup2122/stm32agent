from __future__ import annotations

from pathlib import Path


# Write a structured CubeMX regeneration log that captures the script, process result, file changes, and optional validation summaries.
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
    sections = [
        f"ioc_path={ioc_path}",
        f"tool_path={launcher.get('tool_path')}",
        f"launch_kind={launcher.get('launch_kind')}",
        f"command={' '.join(str(token) for token in command)}",
        f"script_path={script_path}",
        "",
        "script:",
        *[f"  {line}" for line in script_contents.splitlines()],
        "",
        "regeneration:",
        f"  success={regeneration_result['success']}",
        f"  exit_code={regeneration_result['exit_code']}",
        "  stdout:",
        *([f"    {line}" for line in str(regeneration_result["stdout"]).splitlines()] or ["    <empty>"]),
        "  stderr:",
        *([f"    {line}" for line in str(regeneration_result["stderr"]).splitlines()] or ["    <empty>"]),
    ]
    if completion_wait is not None:
        sections.extend([
            "",
            "completion_wait:",
            f"  success={completion_wait.get('success')}",
            f"  marker_path={completion_wait.get('marker_path')}",
            f"  status={completion_wait.get('status')}",
            f"  message={completion_wait.get('message')}",
        ])
    sections.extend([
        "",
        "affected_files:",
        f"  new_files={len(affected_files['new_files'])}",
        f"  deleted_files={len(affected_files['deleted_files'])}",
        f"  modified_files={len(affected_files['modified_files'])}",
    ])
    if output_review is not None:
        sections.extend([
            "",
            "output_review:",
            f"  message={output_review.get('message')}",
            f"  top_level_entries={len(output_review.get('top_level_entries', []))}",
            f"  mismatches={len(output_review.get('mismatches', []))}",
        ])
    if build_validation is not None:
        sections.extend([
            "",
            "build_validation:",
            f"  success={build_validation.get('success')}",
            f"  message={build_validation.get('message')}",
        ])
    log_path.write_text("\n".join(sections), encoding="utf-8")
