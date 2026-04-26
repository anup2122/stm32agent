from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .. import shared
from ..application.services import ioc_builder_service
from ..ioc import baseline_selector, compiler as ioc_compiler, db_index as ioc_db_index, mutator as ioc_mutator, validator as ioc_validator
from ..ioc.board_catalog import get_board_profile
from ..ioc.mcu_catalog import resolve_mcu_metadata
from ..requirements_ioc_contract import CONTRACT_VERSION, DEFAULT_TOOLCHAIN
from .ioc_model import build_ioc_model

mcp = FastMCP("stm32iocbuilder")


def load_firmware_metadata() -> dict[str, object]:
    project_config = shared.load_project_metadata()
    project_data = project_config.get("data")
    firmware = project_data.get("firmware", {}) if isinstance(project_data, dict) else {}
    return firmware if isinstance(firmware, dict) else {}


def resolve_ioc_path(ioc_path: str | None = None) -> Path | None:
    candidate = ioc_path
    if not isinstance(candidate, str) or not candidate.strip():
        firmware = load_firmware_metadata()
        configured = firmware.get("ioc_path")
        candidate = configured if isinstance(configured, str) else None
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    path = Path(candidate).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


def parse_ioc_lines(ioc_path: Path) -> list[str]:
    return ioc_path.read_text(encoding="utf-8", errors="replace").splitlines()


def cubemx_db_cache_root() -> Path:
    return ioc_db_index.cubemx_db_cache_root()


def local_cubemx_db_index() -> dict[str, object]:
    return ioc_db_index.local_cubemx_db_index()


def load_local_board_ioc_lines(board_id: str, mcu_name: str) -> dict[str, object]:
    return baseline_selector.load_local_board_ioc_lines(board_id, mcu_name)


def find_github_board_ioc(board_id: str, mcu_name: str) -> dict[str, object]:
    return baseline_selector.find_github_board_ioc(board_id, mcu_name)


def download_github_ioc_lines(board_id: str, mcu_name: str) -> dict[str, object]:
    return baseline_selector.download_github_ioc_lines(board_id, mcu_name)


def copy_existing_ioc_lines(source_ioc_path: Path) -> dict[str, object]:
    return baseline_selector.copy_existing_ioc_lines(source_ioc_path)


def resolve_contract_project_context(contract: dict[str, object]) -> dict[str, object]:
    return baseline_selector.resolve_contract_project_context(contract)


def resolve_source_ioc_path(contract: dict[str, object], source_ioc_path: str | None = None) -> Path | None:
    return baseline_selector.resolve_source_ioc_path(contract, source_ioc_path=source_ioc_path)


def load_base_ioc_lines(
    contract: dict[str, object],
    *,
    source_ioc_path: str | None = None,
) -> dict[str, object]:
    return baseline_selector.load_base_ioc_lines(
        contract,
        source_ioc_path=source_ioc_path,
        load_local_board_ioc_lines_fn=load_local_board_ioc_lines,
        download_github_ioc_lines_fn=download_github_ioc_lines,
    )


def apply_project_manager_defaults(lines: list[str], *, project_name: str, toolchain: str, target_mcu: str) -> None:
    ioc_mutator.apply_project_manager_defaults(lines, project_name=project_name, toolchain=toolchain, target_mcu=target_mcu)


def synthesize_ioc_change_set(contract: dict[str, object]) -> dict[str, object]:
    return ioc_compiler.compile_contract_to_ioc_plan(contract)


def validate_ioc_with_cubemx(ioc_path: str, project_name: str, project_toolchain: str) -> dict[str, object]:
    return ioc_validator.validate_ioc_with_cubemx(ioc_path, project_name, project_toolchain)


def _rebuild_ioc_model(contract: dict[str, object]):
    target = contract["target"]
    board_profile = get_board_profile(str(target["board_id"])) or {}
    mcu_metadata = resolve_mcu_metadata(str(target["board_id"]), str(target["mcu"])) or {}
    return build_ioc_model(contract, board_profile, mcu_metadata)


def validate_constructed_ioc_lines(lines: list[str], contract: dict[str, object]) -> list[str]:
    return ioc_validator.validate_ioc_lines(lines, _rebuild_ioc_model(contract))


def apply_ioc_change_set(contract: dict[str, object], ioc_path: str | None = None) -> dict[str, object]:
    return ioc_builder_service.apply_ioc_change_set(
        contract=contract,
        ioc_path=ioc_path,
        synthesize_ioc_change_set_fn=synthesize_ioc_change_set,
        resolve_ioc_path_fn=resolve_ioc_path,
        apply_ioc_operations_fn=ioc_mutator.apply_ioc_operations,
        validate_ioc_with_cubemx_fn=validate_ioc_with_cubemx,
        default_toolchain=DEFAULT_TOOLCHAIN,
    )


def construct_ioc_file(
    contract: dict[str, object],
    ioc_path: str | None = None,
    overwrite: bool = False,
    source_ioc_path: str | None = None,
) -> dict[str, object]:
    return ioc_builder_service.construct_ioc_file(
        contract=contract,
        ioc_path=ioc_path,
        overwrite=overwrite,
        source_ioc_path=source_ioc_path,
        synthesize_ioc_change_set_fn=synthesize_ioc_change_set,
        resolve_ioc_path_fn=resolve_ioc_path,
        load_base_ioc_lines_fn=load_base_ioc_lines,
        apply_project_manager_defaults_fn=lambda lines, project_name, toolchain, target_mcu: apply_project_manager_defaults(
            lines,
            project_name=project_name,
            toolchain=toolchain,
            target_mcu=target_mcu,
        ),
        apply_ioc_operations_fn=ioc_mutator.apply_ioc_operations,
        validate_ioc_lines_fn=validate_constructed_ioc_lines,
        validate_ioc_with_cubemx_fn=validate_ioc_with_cubemx,
        default_toolchain=DEFAULT_TOOLCHAIN,
    )


def collect_ioc_builder_capabilities() -> dict[str, object]:
    return ioc_builder_service.collect_ioc_builder_capabilities(
        supported_board_profiles=["NUCLEO-L476RG"],
        supported_contract_version=CONTRACT_VERSION,
        notes=[
            "The IOC Synthesis Agent is deterministic by design.",
            "Supported mappings currently include UART host console, LED blink, and user button event for NUCLEO-L476RG.",
            "Construction mode prefers official local STM32CubeMX board IOCs for new projects, falls back to STMicroelectronics/STM32_open_pin_data when needed, and copies an existing IOC for running projects.",
            "The internal IOC path now compiles contracts into generic IOC operations before mutating the managed IOC copy.",
        ],
    )


@mcp.tool(description="Report the current deterministic IOC Synthesis Agent scope and supported board profiles.")
def stm32_ioc_builder_capabilities() -> dict[str, object]:
    return collect_ioc_builder_capabilities()


@mcp.tool(description="Convert a validated requirements contract into a deterministic IOC operation plan for the current feature increment.")
def stm32_ioc_builder_plan(contract: dict[str, object]) -> dict[str, object]:
    return ioc_builder_service.compile_ioc_plan(
        contract=contract,
        compile_contract_to_ioc_plan_fn=synthesize_ioc_change_set,
    )


@mcp.tool(description="Apply a deterministic IOC operation plan to the configured IOC file before CubeMX regeneration.")
def stm32_ioc_builder_apply(contract: dict[str, object], ioc_path: str | None = None) -> dict[str, object]:
    return apply_ioc_change_set(contract, ioc_path=ioc_path)


@mcp.tool(description="Construct a managed IOC working copy from an official local CubeMX board IOC when available, otherwise from GitHub board data for new projects, or from an existing IOC copy for running projects, then apply the deterministic IOC operation plan for the current feature increment.")
def stm32_ioc_builder_construct(
    contract: dict[str, object],
    ioc_path: str | None = None,
    overwrite: bool = False,
    source_ioc_path: str | None = None,
) -> dict[str, object]:
    return construct_ioc_file(contract, ioc_path=ioc_path, overwrite=overwrite, source_ioc_path=source_ioc_path)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
