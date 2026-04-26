from __future__ import annotations

import time
from pathlib import Path
from typing import Callable


def collect_tree_state(root: Path | None) -> dict[str, float]:
    if root is None or not root.is_dir():
        return {}
    state: dict[str, float] = {}
    for file_path in root.rglob("*"):
        if file_path.is_file():
            try:
                state[str(file_path)] = file_path.stat().st_mtime
            except OSError:
                continue
    return state


def diff_tree_state(before: dict[str, float], after: dict[str, float]) -> dict[str, list[str]]:
    before_keys = set(before)
    after_keys = set(after)
    return {
        "new_files": sorted(after_keys - before_keys),
        "deleted_files": sorted(before_keys - after_keys),
        "modified_files": sorted(path for path in before_keys & after_keys if before[path] != after[path]),
    }


def capture_completion_marker_state(marker_paths: list[Path]) -> dict[Path, tuple[bool, float | None]]:
    state: dict[Path, tuple[bool, float | None]] = {}
    for marker_path in marker_paths:
        exists = marker_path.is_file()
        mtime: float | None = None
        if exists:
            try:
                mtime = marker_path.stat().st_mtime
            except OSError:
                mtime = None
        state[marker_path.resolve()] = (exists, mtime)
    return state


def check_completion_markers(
    marker_paths: list[Path],
    initial_states: dict[Path, tuple[bool, float | None]],
    *,
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
    collect_tree_state_fn: Callable[[Path | None], dict[str, float]] = collect_tree_state,
    diff_tree_state_fn: Callable[[dict[str, float], dict[str, float]], dict[str, list[str]]] = diff_tree_state,
) -> dict[str, object] | None:
    unique_marker_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for marker_path in marker_paths:
        resolved_marker = marker_path.resolve()
        if resolved_marker not in seen_paths:
            seen_paths.add(resolved_marker)
            unique_marker_paths.append(resolved_marker)

    if not unique_marker_paths:
        return None

    for marker_path in unique_marker_paths:
        initial_exists, initial_mtime = initial_states.get(marker_path, (False, None))
        if marker_path.is_file():
            try:
                current_mtime = marker_path.stat().st_mtime
            except OSError:
                current_mtime = None

            if not initial_exists:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "checked_marker_paths": [str(path) for path in unique_marker_paths],
                    "status": "created",
                }
            if initial_mtime is None or current_mtime is None or current_mtime > initial_mtime:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "checked_marker_paths": [str(path) for path in unique_marker_paths],
                    "status": "updated",
                }

    if tree_root is not None and initial_tree_state is not None:
        current_tree_state = collect_tree_state_fn(tree_root)
        affected_files = diff_tree_state_fn(initial_tree_state, current_tree_state)
        if any(affected_files.values()):
            existing_marker = next((path for path in unique_marker_paths if path.is_file()), None)
            marker_existed_before = any(initial_exists for initial_exists, _ in initial_states.values())
            if marker_existed_before or existing_marker is not None:
                return {
                    "success": True,
                    "marker_path": str(existing_marker or unique_marker_paths[0]),
                    "checked_marker_paths": [str(path) for path in unique_marker_paths],
                    "status": "tree_changed",
                    "message": "CubeMX generated files changed even though the completion marker timestamp did not.",
                    "affected_files": affected_files,
                }

    return None


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
    collect_tree_state_fn: Callable[[Path | None], dict[str, float]] = collect_tree_state,
    diff_tree_state_fn: Callable[[dict[str, float], dict[str, float]], dict[str, list[str]]] = diff_tree_state,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    deadline = monotonic_fn() + timeout_seconds
    started_at = monotonic_fn()
    while True:
        if marker_path.is_file():
            try:
                current_mtime = marker_path.stat().st_mtime
            except OSError:
                current_mtime = None

            if not initial_exists:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "created",
                }
            if initial_mtime is None or current_mtime is None or current_mtime > initial_mtime:
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "updated",
                }

        if tree_root is not None and initial_tree_state is not None:
            current_tree_state = collect_tree_state_fn(tree_root)
            affected_files = diff_tree_state_fn(initial_tree_state, current_tree_state)
            if (initial_exists or marker_path.is_file()) and any(affected_files.values()):
                return {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "tree_changed",
                    "message": "CubeMX generated files changed even though the completion marker timestamp did not.",
                    "affected_files": affected_files,
                }

        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            break
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "cubemx_wait",
                    "message": "CubeMX is still running or the generated project marker has not updated yet.",
                    "marker_path": str(marker_path),
                    "marker_exists": marker_path.is_file(),
                    "elapsed_seconds": round(monotonic_fn() - started_at, 1),
                    "remaining_seconds": round(remaining, 1),
                }
            )
        sleep_fn(min(poll_interval_seconds, remaining))

    return {
        "success": False,
        "marker_path": str(marker_path),
        "status": "timeout",
        "message": f"CubeMX did not create or update {marker_path} within {timeout_seconds} seconds.",
    }


def wait_for_completion_markers(
    marker_paths: list[Path],
    *,
    timeout_seconds: int,
    initial_states: dict[Path, tuple[bool, float | None]],
    tree_root: Path | None = None,
    initial_tree_state: dict[str, float] | None = None,
    poll_interval_seconds: float = 2.0,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
    collect_tree_state_fn: Callable[[Path | None], dict[str, float]] = collect_tree_state,
    diff_tree_state_fn: Callable[[dict[str, float], dict[str, float]], dict[str, list[str]]] = diff_tree_state,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    unique_marker_paths: list[Path] = []
    for marker_path in marker_paths:
        resolved = marker_path.resolve()
        if resolved not in unique_marker_paths:
            unique_marker_paths.append(resolved)

    if not unique_marker_paths:
        return {
            "success": False,
            "marker_path": None,
            "status": "timeout",
            "message": "CubeMX did not have a valid completion marker path to monitor.",
        }

    deadline = monotonic_fn() + timeout_seconds
    started_at = monotonic_fn()
    while True:
        completion_status = check_completion_markers(
            unique_marker_paths,
            initial_states,
            tree_root=tree_root,
            initial_tree_state=initial_tree_state,
            collect_tree_state_fn=collect_tree_state_fn,
            diff_tree_state_fn=diff_tree_state_fn,
        )
        if completion_status is not None:
            return completion_status

        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            break
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "cubemx_wait",
                    "message": "CubeMX is still running or the generated project marker has not updated yet.",
                    "marker_path": str(unique_marker_paths[0]),
                    "checked_marker_paths": [str(path) for path in unique_marker_paths],
                    "marker_exists": any(path.is_file() for path in unique_marker_paths),
                    "elapsed_seconds": round(monotonic_fn() - started_at, 1),
                    "remaining_seconds": round(remaining, 1),
                }
            )
        sleep_fn(min(poll_interval_seconds, remaining))

    return {
        "success": False,
        "marker_path": str(unique_marker_paths[0]),
        "checked_marker_paths": [str(path) for path in unique_marker_paths],
        "status": "timeout",
        "message": f"CubeMX did not create or update any expected completion marker within {timeout_seconds} seconds.",
    }
