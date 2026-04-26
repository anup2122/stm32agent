from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

GENERATED_INCLUDE_DIR = Path("Inc")
GENERATED_SOURCE_DIR = Path("Src")
CORE_INCLUDE_DIR = Path("Core") / "Inc"
CORE_SOURCE_DIR = Path("Core") / "Src"


def source_project_root(ioc_path: Path) -> Path:
    return ioc_path.parent.resolve()


def list_relative_directory_entries(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    entries: list[str] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        relative = path.relative_to(root).as_posix()
        entries.append(f"{relative}/" if path.is_dir() else relative)
    return entries


def parse_mxproject_paths(mxproject_path: Path) -> dict[str, object]:
    if not mxproject_path.is_file():
        return {
            "exists": False,
            "advanced_folder_structure": None,
            "header_paths": [],
            "source_paths": [],
        }

    header_paths: list[str] = []
    source_paths: list[str] = []
    advanced_folder_structure: bool | None = None
    for raw_line in mxproject_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("AdvancedFolderStructure="):
            advanced_folder_structure = stripped.partition("=")[2].strip().lower() == "true"
        elif stripped.startswith("HeaderPath#"):
            header_paths.append(stripped.partition("=")[2].strip())
        elif stripped.startswith("SourcePath#"):
            source_paths.append(stripped.partition("=")[2].strip())

    return {
        "exists": True,
        "advanced_folder_structure": advanced_folder_structure,
        "header_paths": header_paths,
        "source_paths": source_paths,
    }


def parse_cproject_include_paths(cproject_path: Path) -> list[str]:
    if not cproject_path.is_file():
        return []

    root = ET.parse(cproject_path).getroot()
    include_paths: set[str] = set()
    for option in root.findall(".//option[@valueType='includePath']"):
        for value in option.findall("listOptionValue"):
            path_value = value.get("value")
            if path_value:
                include_paths.add(path_value)
    return sorted(include_paths)


def parse_project_link_locations(project_path: Path) -> list[str]:
    if not project_path.is_file():
        return []

    root = ET.parse(project_path).getroot()
    locations: list[str] = []
    for link in root.findall(".//linkedResources/link"):
        location = link.findtext("locationURI")
        if location:
            locations.append(location)
    return sorted(locations)


def collect_output_review(ioc_path: Path, generation_root: Path) -> dict[str, object]:
    source_root = source_project_root(ioc_path)
    direct_include_dir = generation_root / GENERATED_INCLUDE_DIR
    direct_source_dir = generation_root / GENERATED_SOURCE_DIR
    core_include_dir = generation_root / CORE_INCLUDE_DIR
    core_source_dir = generation_root / CORE_SOURCE_DIR

    generated_headers = sorted(path.name for path in direct_include_dir.glob("*.h")) if direct_include_dir.is_dir() else []
    generated_sources = sorted(path.name for path in direct_source_dir.glob("*.c")) if direct_source_dir.is_dir() else []
    mxproject = parse_mxproject_paths(source_root / ".mxproject")
    cproject_include_paths = parse_cproject_include_paths(generation_root / "STM32CubeIDE" / ".cproject")
    project_link_locations = parse_project_link_locations(generation_root / "STM32CubeIDE" / ".project")

    mismatches: list[str] = []
    if source_root.resolve() != generation_root.resolve() and mxproject.get("advanced_folder_structure"):
        if direct_include_dir.is_dir() and not core_include_dir.is_dir():
            mismatches.append(
                "CubeMX generated headers in Inc/, but the reference .mxproject declares advanced header paths under Core/Inc."
            )
        if direct_source_dir.is_dir() and not core_source_dir.is_dir():
            mismatches.append(
                "CubeMX generated sources in Src/, but the reference .mxproject declares advanced source paths under Core/Src."
            )
    if any("../../Core/Inc" == include_path for include_path in cproject_include_paths) and direct_include_dir.is_dir():
        mismatches.append(
            "The external .cproject include paths still point to ../../Core/Inc while direct CubeMX output was written to Inc/."
        )
    if any("PARENT-1-PROJECT_LOC/Core/Src/" in location for location in project_link_locations) and direct_source_dir.is_dir():
        mismatches.append(
            "The external .project source links still point to Core/Src while direct CubeMX output was written to Src/."
        )

    return {
        "generation_root": str(generation_root),
        "top_level_entries": list_relative_directory_entries(generation_root),
        "direct_output": {
            "include_dir": str(direct_include_dir),
            "source_dir": str(direct_source_dir),
            "include_dir_exists": direct_include_dir.is_dir(),
            "source_dir_exists": direct_source_dir.is_dir(),
            "generated_headers": generated_headers,
            "generated_sources": generated_sources,
        },
        "core_layout_present": {
            "include_dir": str(core_include_dir),
            "source_dir": str(core_source_dir),
            "include_dir_exists": core_include_dir.is_dir(),
            "source_dir_exists": core_source_dir.is_dir(),
        },
        "source_project_expectations": {
            "source_root": str(source_root),
            "mxproject": mxproject,
        },
        "external_build_expectations": {
            "cproject_include_paths": cproject_include_paths,
            "project_link_locations": project_link_locations,
        },
        "mismatches": mismatches,
        "message": "Direct CubeMX output was preserved without structural alignment. Review the reported mismatches before rewiring the external build metadata.",
    }


def collect_build_layout_summary(
    generation_root: Path,
    *,
    load_build_metadata_fn: Callable[[], dict[str, object]],
) -> dict[str, object]:
    build_metadata = load_build_metadata_fn()
    return {
        "generation_root": str(generation_root),
        "structure": {
            "generated_include_dir": str(generation_root / GENERATED_INCLUDE_DIR),
            "generated_source_dir": str(generation_root / GENERATED_SOURCE_DIR),
            "core_include_dir": str(generation_root / CORE_INCLUDE_DIR),
            "core_source_dir": str(generation_root / CORE_SOURCE_DIR),
            "cubeide_project_dir": str(generation_root / "STM32CubeIDE"),
        },
        "build": {
            "workspace": build_metadata.get("workspace"),
            "project_path": build_metadata.get("project_path"),
            "project_name": build_metadata.get("project_name"),
            "artifact": build_metadata.get("artifact"),
            "default_configuration": build_metadata.get("default_configuration"),
        },
    }
