from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree.ElementTree import ParseError

from ..knowledge.cubemx_db import find_board_baseline
from .db_index import local_cubemx_db_index

GITHUB_BOARD_INDEX_URL = "https://api.github.com/repos/STMicroelectronics/STM32_open_pin_data/contents/boards?ref=master"
GITHUB_API_ACCEPT = "application/vnd.github+json"
GITHUB_USER_AGENT = "stm32cubep-mcp"


def parse_ioc_lines(ioc_path: Path) -> list[str]:
    return ioc_path.read_text(encoding="utf-8", errors="replace").splitlines()


def normalized_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def normalized_mcu_candidates(mcu_name: str) -> list[str]:
    normalized = normalized_identifier(mcu_name)
    candidates: list[str] = []
    for candidate in (normalized, normalized[:-1], normalized[:-2]):
        if len(candidate) >= 8 and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def load_local_board_ioc_lines(board_id: str, mcu_name: str) -> dict[str, object]:
    try:
        index = local_cubemx_db_index()
    except (FileNotFoundError, OSError, json.JSONDecodeError, ParseError) as exc:
        return {
            "success": False,
            "message": f"Unable to index the local STM32CubeMX database: {exc}",
        }

    match = find_board_baseline(index, board_id)
    if not isinstance(match, dict):
        return {
            "success": False,
            "message": f"No local STM32CubeMX board IOC was found for board '{board_id}'.",
        }

    baseline_mcu_name = match.get("mcu_name")
    if isinstance(baseline_mcu_name, str) and baseline_mcu_name.strip() and mcu_name.strip():
        baseline_normalized = normalized_identifier(baseline_mcu_name)
        requested_candidates = normalized_mcu_candidates(mcu_name)
        if requested_candidates and not any(candidate in baseline_normalized or baseline_normalized in candidate for candidate in requested_candidates):
            return {
                "success": False,
                "message": (
                    f"The local STM32CubeMX board IOC for '{board_id}' targets MCU '{baseline_mcu_name}', "
                    f"which did not match requested MCU '{mcu_name}'."
                ),
                "match": match,
            }

    ioc_path = match.get("ioc_path")
    if not isinstance(ioc_path, str) or not ioc_path.strip():
        return {
            "success": False,
            "message": "The matched local STM32CubeMX board IOC did not provide a file path.",
            "match": match,
        }

    resolved_ioc_path = Path(ioc_path).expanduser().resolve()
    if not resolved_ioc_path.is_file():
        return {
            "success": False,
            "message": f"The matched local STM32CubeMX board IOC file was not found: {resolved_ioc_path}",
            "match": match,
        }

    lines = parse_ioc_lines(resolved_ioc_path)
    if not lines or not any(line.startswith("Mcu.Name=") for line in lines):
        return {
            "success": False,
            "message": f"The matched local STM32CubeMX board IOC did not look valid: {resolved_ioc_path}",
            "match": match,
        }

    return {
        "success": True,
        "match": match,
        "ioc_path": str(resolved_ioc_path),
        "lines": lines,
    }


def github_board_ioc_catalog() -> tuple[dict[str, str], ...]:
    request = Request(
        GITHUB_BOARD_INDEX_URL,
        headers={
            "Accept": GITHUB_API_ACCEPT,
            "User-Agent": GITHUB_USER_AGENT,
        },
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    entries: list[dict[str, str]] = []
    if not isinstance(payload, list):
        return tuple()

    for entry in payload:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        download_url = entry.get("download_url")
        if not isinstance(name, str) or not name.endswith(".ioc"):
            continue
        if not isinstance(download_url, str) or not download_url.strip():
            continue
        entries.append(
            {
                "name": name,
                "download_url": download_url,
            }
        )
    return tuple(entries)


def find_github_board_ioc(board_id: str, mcu_name: str) -> dict[str, object]:
    try:
        catalog = github_board_ioc_catalog()
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "message": f"Unable to query the STM32_open_pin_data GitHub catalog: {exc}",
        }

    board_token = board_id.upper().strip()
    board_normalized = normalized_identifier(board_token)
    mcu_candidates = normalized_mcu_candidates(mcu_name)
    best_match: dict[str, object] | None = None
    best_score = -1

    for entry in catalog:
        name = str(entry["name"])
        upper_name = name.upper()
        normalized_name = normalized_identifier(name)
        score = 0
        if re.search(rf"(^|_){re.escape(board_token)}(_|\.|$)", upper_name):
            score += 100
        elif board_normalized and board_normalized in normalized_name:
            score += 40

        for index, candidate in enumerate(mcu_candidates):
            if not candidate:
                continue
            if candidate in normalized_name:
                score += max(5, 30 - (index * 10))
                break

        if upper_name.endswith("_BOARD_ALLCONFIG.IOC"):
            score += 5

        if score > best_score:
            best_score = score
            best_match = {
                "name": name,
                "download_url": entry["download_url"],
                "score": score,
            }

    if best_match is None or best_score <= 0:
        return {
            "success": False,
            "message": f"No matching STM32_open_pin_data IOC was found for board '{board_id}' and MCU '{mcu_name}'.",
        }

    return {
        "success": True,
        "match": best_match,
        "catalog_entries": len(catalog),
    }


def download_github_ioc_lines(board_id: str, mcu_name: str) -> dict[str, object]:
    lookup = find_github_board_ioc(board_id, mcu_name)
    if not lookup.get("success"):
        return lookup

    match = lookup.get("match") if isinstance(lookup.get("match"), dict) else {}
    download_url = match.get("download_url")
    if not isinstance(download_url, str) or not download_url.strip():
        return {
            "success": False,
            "message": "The matching GitHub IOC entry did not provide a download URL.",
        }

    request = Request(
        download_url,
        headers={
            "Accept": "text/plain",
            "User-Agent": GITHUB_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {
            "success": False,
            "message": f"Unable to download the GitHub IOC template from {download_url}: {exc}",
            "match": match,
        }

    if "Mcu.Name=" not in text:
        return {
            "success": False,
            "message": f"The downloaded IOC template from {download_url} did not look valid.",
            "match": match,
        }

    return {
        "success": True,
        "match": match,
        "lines": text.splitlines(),
    }


def copy_existing_ioc_lines(source_ioc_path: Path) -> dict[str, object]:
    if not source_ioc_path.is_file():
        return {
            "success": False,
            "message": f"The source IOC file was not found: {source_ioc_path}",
        }

    lines = parse_ioc_lines(source_ioc_path)
    if not lines:
        return {
            "success": False,
            "message": f"The source IOC file is empty: {source_ioc_path}",
        }

    return {
        "success": True,
        "source_ioc_path": str(source_ioc_path),
        "lines": lines,
    }


def resolve_contract_project_context(contract: dict[str, object]) -> dict[str, object]:
    project_context = contract.get("project_context")
    return project_context if isinstance(project_context, dict) else {}


def resolve_source_ioc_path(contract: dict[str, object], source_ioc_path: str | None = None) -> Path | None:
    candidate = source_ioc_path
    if not isinstance(candidate, str) or not candidate.strip():
        project_context = resolve_contract_project_context(contract)
        configured = project_context.get("configured_source_ioc_path")
        candidate = configured if isinstance(configured, str) else None
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    path = Path(candidate).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def load_base_ioc_lines(
    contract: dict[str, object],
    *,
    source_ioc_path: str | None = None,
    load_local_board_ioc_lines_fn=load_local_board_ioc_lines,
    download_github_ioc_lines_fn=download_github_ioc_lines,
) -> dict[str, object]:
    project_context = resolve_contract_project_context(contract)
    target = contract.get("target") if isinstance(contract.get("target"), dict) else {}
    board_id = str(target.get("board_id") or "").strip()
    mcu_name = str(target.get("mcu") or "").strip()
    ioc_handling = str(project_context.get("ioc_handling") or "")

    if ioc_handling == "copy_existing_ioc":
        resolved_source = resolve_source_ioc_path(contract, source_ioc_path=source_ioc_path)
        if resolved_source is None:
            return {
                "success": False,
                "message": "The workflow selected existing-project IOC reuse, but no source IOC path was available.",
            }
        copied = copy_existing_ioc_lines(resolved_source)
        if not copied.get("success"):
            return copied
        return {
            "success": True,
            "construction_source": "existing_ioc_copy",
            "source_ioc_path": copied.get("source_ioc_path"),
            "lines": copied["lines"],
        }

    local_board_ioc = load_local_board_ioc_lines_fn(board_id, mcu_name)
    if local_board_ioc.get("success"):
        return {
            "success": True,
            "construction_source": "local_board_ioc",
            "local_match": local_board_ioc.get("match"),
            "source_ioc_path": local_board_ioc.get("ioc_path"),
            "lines": local_board_ioc["lines"],
        }

    downloaded = download_github_ioc_lines_fn(board_id, mcu_name)
    if not downloaded.get("success"):
        return {
            **downloaded,
            "local_board_ioc": local_board_ioc,
        }
    return {
        "success": True,
        "construction_source": "github_board_ioc",
        "github_match": downloaded.get("match"),
        "local_board_ioc": local_board_ioc,
        "lines": downloaded["lines"],
    }
