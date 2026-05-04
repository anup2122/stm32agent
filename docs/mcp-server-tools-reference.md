# MCP Server Tools Reference

This document lists the MCP servers exposed by this repository and the tools each server exports through @mcp.tool(...).

It adds four things for each server: the script entry point, the concrete source module, each exported tool signature, and the decorator description that explains the tool's purpose.

For the stitched runtime sequence across these servers, see [end-to-end-call-chain.md](end-to-end-call-chain.md).

## How To Choose A Tool

Use `stm32orchestrator` first when the input is a natural-language goal such as build this project, flash the board, answer a debug question, or implement a feature from a prompt. It is the Copilot-facing routing layer and decides which tool-domain server should handle the request.

Use a tool-domain server directly when the intent is already explicit and narrowly scoped. Choose `stm32cubeprogrammer` for connect, flash, erase, memory, and core-control operations; `stm32build` for headless CubeIDE builds; `stm32debug` for managed GDB server launch and live target inspection; `stm32cubemx` for IOC parsing and regeneration; `stm32-requirements-mcp` for prompt-to-contract decomposition; and `stm32-ioc-builder-mcp` for deterministic IOC planning or application from a validated contract.

As a rule, call the highest-level tool that matches the user request. If the user says what outcome they want but not which subsystem to use, prefer an orchestrator tool. If they name a concrete operation such as `stm32_build_project` or `stm32_cubemx_parse_ioc`, call that domain tool directly.

## Server Entry Points

| Script entry point | Python entry point | Server module | Notes |
| --- | --- | --- | --- |
| stm32cubep-mcp | stm32cubep_mcp.cube_programmer.server:main | src/stm32cubep_mcp/cube_programmer/server.py | Compatibility launcher name for the STM32CubeProgrammer server. |
| stm32cubeprogrammer-mcp | stm32cubep_mcp.cube_programmer.server:main | src/stm32cubep_mcp/cube_programmer/server.py | Canonical STM32CubeProgrammer server launcher. |
| stm32-build-mcp | stm32cubep_mcp.build.server:main | src/stm32cubep_mcp/build/server.py | Build server. |
| stm32-debug-mcp | stm32cubep_mcp.debug.server:main | src/stm32cubep_mcp/debug/server.py | Debug server. |
| stm32-cubemx-mcp | stm32cubep_mcp.cubemx.server:main | src/stm32cubep_mcp/cubemx/server.py | CubeMX server. |
| stm32-orchestrator-mcp | stm32cubep_mcp.orchestrator.server:main | src/stm32cubep_mcp/orchestrator/server.py | Orchestration server. |
| stm32-requirements-mcp | stm32cubep_mcp.requirements.server:main | src/stm32cubep_mcp/requirements/server.py | Requirements decomposition server. |
| stm32-ioc-builder-mcp | stm32cubep_mcp.ioc_builder.server:main | src/stm32cubep_mcp/ioc_builder/server.py | IOC builder server. |

## STM32CubeProgrammer Server

Source: src/stm32cubep_mcp/cube_programmer/server.py

| Tool | Signature | Purpose | Source |
| --- | --- | --- | --- |
| stm32_connect | port: str = 'SWD', serial_number: str \| None = None, usb_product_id: str \| None = None, usb_vendor_id: str \| None = None, baudrate: int \| None = None, parity: Parity \| None = None, data_bits: int \| None = None, stop_bits: str \| None = None, flow_control: FlowControl \| None = None, rts: LevelState \| None = None, dtr: LevelState \| None = None, no_init_bits: int \| None = None, enable_console: bool = False, frequency_khz: int \| None = 4000, probe_index: int \| None = None, access_port: int \| None = None, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst', shared_mode: bool = False, tcp_port: int \| None = None, low_power_mode: LowPowerMode = 'inherit', get_auth_id: bool = False, speed: SpeedMode \| None = None, target_sel: str \| None = None, timeout_seconds: int = 30 | Connect to attached stm32 device. Defaults to SWD, 4000 KHz, NORMAL mode, writes a timestamped log file, and retries common fallback options automatically. | [src/stm32cubep_mcp/cube_programmer/server.py#L1481](src/stm32cubep_mcp/cube_programmer/server.py#L1481) |
| connect_to_attached_stm32_device | timeout_seconds: int = 30 | Connect to attached stm32 device using default SWD settings and automatic fallback attempts. Use this when the user says stm32 device without extra parameters. | [src/stm32cubep_mcp/cube_programmer/server.py#L1571](src/stm32cubep_mcp/cube_programmer/server.py#L1571) |
| stm32_discover_host_tools |  | Discover STM32 host-side configuration files, schema locations, and STM32CubeProgrammer CLI candidate paths for the current machine. | [src/stm32cubep_mcp/cube_programmer/server.py#L1582](src/stm32cubep_mcp/cube_programmer/server.py#L1582) |
| stm32_report_host_capabilities | timeout_seconds: int = 10 | Report whether this host can actually run the currently supported STM32 workflows by probing STM32CubeProgrammer availability and version. | [src/stm32cubep_mcp/cube_programmer/server.py#L1587](src/stm32cubep_mcp/cube_programmer/server.py#L1587) |
| stm32_programmer_version | timeout_seconds: int = 15 | Show the STM32CubeProgrammer version and write a timestamped log file. | [src/stm32cubep_mcp/cube_programmer/server.py#L1592](src/stm32cubep_mcp/cube_programmer/server.py#L1592) |
| stm32_list_interfaces | interface: InterfaceName \| None = None, shared: bool = False, timeout_seconds: int = 20 | List STM32 communication interfaces or connected ST-LINK probes and write a timestamped log file. | [src/stm32cubep_mcp/cube_programmer/server.py#L1604](src/stm32cubep_mcp/cube_programmer/server.py#L1604) |
| stm32_erase | sectors: list[str] \| None = None, timeout_seconds: int = 60, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Erase STM32 flash memory. Defaults to erase all sectors after connecting to the attached stm32 device. | [src/stm32cubep_mcp/cube_programmer/server.py#L1625](src/stm32cubep_mcp/cube_programmer/server.py#L1625) |
| stm32_download | file_path: str, address: str \| None = None, incremental: bool = False, skip_erase: bool = False, verify_mode: VerifyMode = 'legacy', post_action: PostDownloadAction = 'none', timeout_seconds: int = 180, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Download a firmware file to STM32 flash memory. By default it verifies after programming and writes a timestamped log file. | [src/stm32cubep_mcp/cube_programmer/server.py#L1660](src/stm32cubep_mcp/cube_programmer/server.py#L1660) |
| stm32_flash_firmware | file_path: str, address: str \| None = None, sectors: list[str] \| None = None, incremental: bool = False, verify_mode: VerifyMode = 'legacy', post_action: PostDownloadAction = 'go', timeout_seconds: int = 240, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Production-style STM32 flashing flow: erase, download, verify, then optionally go or reset. Uses the default attached stm32 device connection behavior and writes a timestamped log file. | [src/stm32cubep_mcp/cube_programmer/server.py#L1717](src/stm32cubep_mcp/cube_programmer/server.py#L1717) |
| stm32_verify | verify_mode: VerifyMode = 'legacy', timeout_seconds: int = 120, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Run STM32 verify after connecting to the attached stm32 device. | [src/stm32cubep_mcp/cube_programmer/server.py#L1772](src/stm32cubep_mcp/cube_programmer/server.py#L1772) |
| stm32_checksum | address: str \| None = None, size: int \| None = None, timeout_seconds: int = 60, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Read a memory checksum from the connected stm32 device. | [src/stm32cubep_mcp/cube_programmer/server.py#L1807](src/stm32cubep_mcp/cube_programmer/server.py#L1807) |
| stm32_upload | address: str, size: int, file_path: str, timeout_seconds: int = 180, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Read device memory and save it to a file. | [src/stm32cubep_mcp/cube_programmer/server.py#L1843](src/stm32cubep_mcp/cube_programmer/server.py#L1843) |
| stm32_read_memory | address: str, size: int, width: MemoryWidth = 32, timeout_seconds: int = 60, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Read 8, 16, or 32-bit values from STM32 memory. | [src/stm32cubep_mcp/cube_programmer/server.py#L1880](src/stm32cubep_mcp/cube_programmer/server.py#L1880) |
| stm32_write_memory | address: str, data: list[int], width: MemoryWidth = 32, verify: bool = True, timeout_seconds: int = 60, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Write 8, 16, or 32-bit values into STM32 memory. | [src/stm32cubep_mcp/cube_programmer/server.py#L1917](src/stm32cubep_mcp/cube_programmer/server.py#L1917) |
| stm32_reset | reset_kind: ResetKind = 'software', timeout_seconds: int = 30, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Reset the connected stm32 device in software, hardware, or bootloader mode. | [src/stm32cubep_mcp/cube_programmer/server.py#L1955](src/stm32cubep_mcp/cube_programmer/server.py#L1955) |
| stm32_go | address: str \| None = None, timeout_seconds: int = 30, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Run code on the connected stm32 device at an optional start address. | [src/stm32cubep_mcp/cube_programmer/server.py#L1990](src/stm32cubep_mcp/cube_programmer/server.py#L1990) |
| stm32_halt | timeout_seconds: int = 30, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Halt the connected stm32 core. | [src/stm32cubep_mcp/cube_programmer/server.py#L2025](src/stm32cubep_mcp/cube_programmer/server.py#L2025) |
| stm32_run_core | timeout_seconds: int = 30, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Run the connected stm32 core after a halt. | [src/stm32cubep_mcp/cube_programmer/server.py#L2059](src/stm32cubep_mcp/cube_programmer/server.py#L2059) |
| stm32_step_core | timeout_seconds: int = 30, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Step the connected stm32 core once. | [src/stm32cubep_mcp/cube_programmer/server.py#L2093](src/stm32cubep_mcp/cube_programmer/server.py#L2093) |
| stm32_core_status | timeout_seconds: int = 30, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Read the connected stm32 core status. | [src/stm32cubep_mcp/cube_programmer/server.py#L2127](src/stm32cubep_mcp/cube_programmer/server.py#L2127) |
| stm32_custom_command | command_arguments: list[str], include_connect: bool = True, timeout_seconds: int = 120, port: str = 'SWD', frequency_khz: int \| None = 4000, mode: ConnectionMode \| None = 'NORMAL', reset: ResetMode \| None = 'SWrst' | Run a custom STM32CubeProgrammer command. Use include_connect=true for device commands that need the default stm32 device connection behavior. | [src/stm32cubep_mcp/cube_programmer/server.py#L2161](src/stm32cubep_mcp/cube_programmer/server.py#L2161) |

## Build Server

Source: src/stm32cubep_mcp/build/server.py

| Tool | Signature | Purpose | Source |
| --- | --- | --- | --- |
| stm32_build_capabilities |  | Report the configured build backend and the placeholder build command that this future STM32 build MCP server will own. | [src/stm32cubep_mcp/build/server.py#L406](src/stm32cubep_mcp/build/server.py#L406) |
| stm32_build_project | backend: str \| None = None, target: str \| None = None, clean: bool = False, timeout_seconds: int = 600 | Build an STM32 project through STM32CubeIDE headless build using the shared project metadata and file-based build logs. | [src/stm32cubep_mcp/build/server.py#L411](src/stm32cubep_mcp/build/server.py#L411) |

## Debug Server

Source: src/stm32cubep_mcp/debug/server.py

| Tool | Signature | Purpose | Source |
| --- | --- | --- | --- |
| stm32_debug_uart_configuration | session_name: str = 'default', peripheral: str = 'USART1', timeout_seconds: int = 20 | Read live UART or USART configuration directly from the attached STM32 target through a managed debug session and estimate the active baud rate from peripheral registers. | [src/stm32cubep_mcp/debug/server.py#L1225](src/stm32cubep_mcp/debug/server.py#L1225) |
| stm32_debug_capabilities |  | Report the current ST-LINK GDB server capabilities and resolved debug metadata from stm32-project.json. | [src/stm32cubep_mcp/debug/server.py#L1582](src/stm32cubep_mcp/debug/server.py#L1582) |
| stm32_debug_server_version | timeout_seconds: int = 10 | Report the installed ST-LINK GDB server version when the executable is available on the current host. | [src/stm32cubep_mcp/debug/server.py#L1587](src/stm32cubep_mcp/debug/server.py#L1587) |
| stm32_debug_gdb_version | timeout_seconds: int = 10 | Report the installed ARM GDB client version used for Phase 2 runtime inspection when the executable is available on the current host. | [src/stm32cubep_mcp/debug/server.py#L1613](src/stm32cubep_mcp/debug/server.py#L1613) |
| stm32_debug_list_debuggers | timeout_seconds: int = 10 | List ST-LINK serial numbers visible to the ST-LINK GDB server executable on the current host. | [src/stm32cubep_mcp/debug/server.py#L1639](src/stm32cubep_mcp/debug/server.py#L1639) |
| stm32_debug_launch | session_name: str = 'default', port_number: int \| None = None, swo_port: int \| None = None, enable_swo: bool = True, serial_number: str \| None = None, frequency_khz: int \| None = None, attach: bool = False, persistent: bool = True, shared_mode: bool = False, verify: bool = False, incremental: bool = False, erase_all: bool = False, verbose: bool = False, log_level: int \| None = None, refresh_delay: int \| None = None, initialize_reset: bool = False, apid: int \| None = None, halt: bool = False, timeout_seconds: int = 15 | Launch the STM32CubeIDE ST-LINK GDB server as a managed background session and return the listening port plus log paths. | [src/stm32cubep_mcp/debug/server.py#L1671](src/stm32cubep_mcp/debug/server.py#L1671) |
| stm32_debug_status | session_name: str = 'default' | Report the current lifecycle state of a managed ST-LINK GDB server session. | [src/stm32cubep_mcp/debug/server.py#L1862](src/stm32cubep_mcp/debug/server.py#L1862) |
| stm32_debug_sessions |  | List all managed ST-LINK GDB server sessions currently known to the MCP process. | [src/stm32cubep_mcp/debug/server.py#L1885](src/stm32cubep_mcp/debug/server.py#L1885) |
| stm32_debug_run_gdb_commands | session_name: str = 'default', commands: list[str] \| None = None, timeout_seconds: int = 20 | Run one-shot ARM GDB commands against a managed ST-LINK GDB server session and return the batch transcript. | [src/stm32cubep_mcp/debug/server.py#L1896](src/stm32cubep_mcp/debug/server.py#L1896) |
| stm32_debug_inspect_peripheral | session_name: str = 'default', peripheral: str = 'USART1', register: str \| None = None, timeout_seconds: int = 20 | Inspect a live peripheral or a specific register directly on the attached STM32 target using SVD metadata plus a managed debug session. | [src/stm32cubep_mcp/debug/server.py#L1916](src/stm32cubep_mcp/debug/server.py#L1916) |
| stm32_debug_answer_question | question: str, session_name: str = 'default', timeout_seconds: int = 20 | Answer a natural-language peripheral or register question by inspecting live target state through the managed debug session. | [src/stm32cubep_mcp/debug/server.py#L1954](src/stm32cubep_mcp/debug/server.py#L1954) |
| stm32_debug_stop | session_name: str = 'default', force: bool = False, timeout_seconds: int = 10 | Stop a managed ST-LINK GDB server session and return its final logs and exit code. | [src/stm32cubep_mcp/debug/server.py#L2018](src/stm32cubep_mcp/debug/server.py#L2018) |
| stm32_debug_snapshot | snapshot_name: str = 'current', session_name: str = 'default', stack_words: int = 16, timeout_seconds: int = 20 | Capture a structured runtime snapshot through an ARM GDB client attached to a managed ST-LINK GDB server session. | [src/stm32cubep_mcp/debug/server.py#L2056](src/stm32cubep_mcp/debug/server.py#L2056) |

## CubeMX Server

Source: src/stm32cubep_mcp/cubemx/server.py

| Tool | Signature | Purpose | Source |
| --- | --- | --- | --- |
| stm32_cubemx_capabilities |  | Report CubeMX Part 1 host readiness, IOC discovery state, and whether deterministic IOC inspection/regeneration backends are available. | [src/stm32cubep_mcp/cubemx/server.py#L406](src/stm32cubep_mcp/cubemx/server.py#L406) |
| stm32_cubemx_parse_ioc | ioc_path: str \| None = None | Inspect an existing CubeMX IOC file by loading its properties-style metadata, peripheral list, pins, and project/toolchain summary. | [src/stm32cubep_mcp/cubemx/server.py#L417](src/stm32cubep_mcp/cubemx/server.py#L417) |
| stm32_cubemx_regenerate_project | ioc_path: str \| None = None, project_name: str \| None = None, project_toolchain: str \| None = None, project_path: str \| None = None, script_path: str \| None = None, output_root: str \| None = None, validate_build: bool = True, timeout_seconds: int = 900, build_timeout_seconds: int = 600 | Run deterministic CubeMX regeneration for an existing IOC file, record affected files, and optionally validate the regenerated project with the existing Build MCP. | [src/stm32cubep_mcp/cubemx/server.py#L467](src/stm32cubep_mcp/cubemx/server.py#L467) |

## Orchestrator Server

Source: src/stm32cubep_mcp/orchestrator/server.py

| Tool | Signature | Purpose | Source |
| --- | --- | --- | --- |
| stm32_normalize_project_config | write_changes: bool = True | Normalize stm32-project.json into the concise JSONC format with real comments and derived-path duplication removed. | [src/stm32cubep_mcp/orchestrator/server.py#L91](src/stm32cubep_mcp/orchestrator/server.py#L91) |
| stm32_orchestrate_feature_prompt | prompt: str, build_timeout_seconds: int = 600, flash_timeout_seconds: int = 240, cubemx_timeout_seconds: int = 900, verify_mode: programmer_server.VerifyMode = 'legacy', post_action: programmer_server.PostDownloadAction = 'go' | High-level orchestration workflow that converts a supported feature prompt into IOC changes, regenerates the project, builds it, and flashes the resulting firmware. | [src/stm32cubep_mcp/orchestrator/server.py#L211](src/stm32cubep_mcp/orchestrator/server.py#L211) |
| stm32_orchestrate_feature_status | plan_file: str | Read the current live status of a persisted feature-delivery plan artifact so callers can poll progress during long-running workflows. | [src/stm32cubep_mcp/orchestrator/server.py#L230](src/stm32cubep_mcp/orchestrator/server.py#L230) |
| stm32_orchestrate_cubemx_regeneration | validate_build: bool = True, timeout_seconds: int = 900, build_timeout_seconds: int = 600 | High-level orchestration entry point for deterministic CubeMX regeneration using the shared stm32-project.json metadata. | [src/stm32cubep_mcp/orchestrator/server.py#L240](src/stm32cubep_mcp/orchestrator/server.py#L240) |
| stm32_orchestrate_build_then_flash | target: str \| None = None, clean: bool = False, file_path: str \| None = None, build_timeout_seconds: int = 600, flash_timeout_seconds: int = 240, verify_mode: programmer_server.VerifyMode = 'legacy', post_action: programmer_server.PostDownloadAction = 'go' | High-level orchestration workflow that builds the configured STM32 project and then flashes the resulting artifact in one step. | [src/stm32cubep_mcp/orchestrator/server.py#L255](src/stm32cubep_mcp/orchestrator/server.py#L255) |
| stm32_orchestrate_debug_session | session_name: str = 'default', reset_before_launch: bool = True, timeout_seconds: int = 60, port_number: int \| None = None, swo_port: int \| None = None, enable_swo: bool = True, serial_number: str \| None = None, frequency_khz: int \| None = None, attach: bool = False, persistent: bool = True, shared_mode: bool = False, verify: bool = False, incremental: bool = False, erase_all: bool = False, verbose: bool = False, log_level: int \| None = None, refresh_delay: int \| None = None, initialize_reset: bool = False, apid: int \| None = None, halt: bool = False | High-level orchestration workflow that resets the attached STM32 target and launches a managed ST-LINK GDB server session for runtime diagnosis. | [src/stm32cubep_mcp/orchestrator/server.py#L279](src/stm32cubep_mcp/orchestrator/server.py#L279) |
| stm32_orchestration_status |  | Report the shared configuration state and summarize the tool-domain MCP servers that the STM32 orchestration layer coordinates. | [src/stm32cubep_mcp/orchestrator/server.py#L344](src/stm32cubep_mcp/orchestrator/server.py#L344) |
| stm32_orchestrate_prompt | prompt: str, timeout_seconds: int = 120, mode: PromptMode = 'auto' | Route a natural-language STM32 workflow request to the most appropriate tool-domain MCP server scaffold and return the normalized result. | [src/stm32cubep_mcp/orchestrator/server.py#L349](src/stm32cubep_mcp/orchestrator/server.py#L349) |
| stm32_orchestrate_build | timeout_seconds: int = 600 | High-level orchestration entry point for a project build using the shared stm32-project.json metadata. | [src/stm32cubep_mcp/orchestrator/server.py#L372](src/stm32cubep_mcp/orchestrator/server.py#L372) |
| stm32_orchestrate_debug | timeout_seconds: int = 60 | High-level orchestration entry point for reset-first ST-LINK GDB server launch using the shared STM32 project metadata. | [src/stm32cubep_mcp/orchestrator/server.py#L382](src/stm32cubep_mcp/orchestrator/server.py#L382) |
| stm32_orchestrate_debug_question | prompt: str, session_name: str = 'agentic-inspect', timeout_seconds: int = 60 | High-level orchestration workflow that ensures a managed debug session exists and then answers a live peripheral or register question from target state. | [src/stm32cubep_mcp/orchestrator/server.py#L392](src/stm32cubep_mcp/orchestrator/server.py#L392) |
| stm32_orchestrate_flash | timeout_seconds: int = 240 | High-level orchestration entry point for flashing the configured default firmware artifact from stm32-project.json. | [src/stm32cubep_mcp/orchestrator/server.py#L408](src/stm32cubep_mcp/orchestrator/server.py#L408) |

## Requirements Server

Source: src/stm32cubep_mcp/requirements/server.py

| Tool | Signature | Purpose | Source |
| --- | --- | --- | --- |
| stm32_requirements_capabilities |  | Report the current Requirement Decomposition Agent scope and the deterministic contract version exposed to the IOC synthesis layer. | [src/stm32cubep_mcp/requirements/server.py#L703](src/stm32cubep_mcp/requirements/server.py#L703) |
| stm32_requirements_decompose | prompt: str, persist_plan: bool = False | Convert a supported STM32 feature prompt into the first deterministic contract consumed by the IOC Synthesis Agent. | [src/stm32cubep_mcp/requirements/server.py#L708](src/stm32cubep_mcp/requirements/server.py#L708) |
| stm32_requirements_update_plan | plan_file: str, stage: str, status: str, message: str | Append a stage transition to the current Phase 2 plan artifact used by the Requirement Decomposition Agent. | [src/stm32cubep_mcp/requirements/server.py#L747](src/stm32cubep_mcp/requirements/server.py#L747) |
| stm32_requirements_heartbeat_plan | plan_file: str, stage: str, message: str | Refresh the live status fields of the current Phase 2 plan artifact without appending a new history event. | [src/stm32cubep_mcp/requirements/server.py#L757](src/stm32cubep_mcp/requirements/server.py#L757) |
| stm32_requirements_plan_status | plan_file: str | Read the current live state of the Phase 2 plan artifact so callers can poll workflow progress during long operations. | [src/stm32cubep_mcp/requirements/server.py#L766](src/stm32cubep_mcp/requirements/server.py#L766) |

## IOC Builder Server

Source: src/stm32cubep_mcp/ioc_builder/server.py

| Tool | Signature | Purpose | Source |
| --- | --- | --- | --- |
| stm32_ioc_builder_capabilities |  | Report the current deterministic IOC Synthesis Agent scope and supported board profiles. | [src/stm32cubep_mcp/ioc_builder/server.py#L164](src/stm32cubep_mcp/ioc_builder/server.py#L164) |
| stm32_ioc_builder_plan | contract: dict[str, object] | Convert a validated requirements contract into a deterministic IOC operation plan for the current feature increment. | [src/stm32cubep_mcp/ioc_builder/server.py#L169](src/stm32cubep_mcp/ioc_builder/server.py#L169) |
| stm32_ioc_builder_apply | contract: dict[str, object], ioc_path: str \| None = None | Apply a deterministic IOC operation plan to the configured IOC file before CubeMX regeneration. | [src/stm32cubep_mcp/ioc_builder/server.py#L177](src/stm32cubep_mcp/ioc_builder/server.py#L177) |
| stm32_ioc_builder_construct | contract: dict[str, object], ioc_path: str \| None = None, overwrite: bool = False, source_ioc_path: str \| None = None | Construct a managed IOC working copy from an official local CubeMX board IOC when available, otherwise from GitHub board data for new projects, or from an existing IOC copy for running projects, then apply the deterministic IOC operation plan for the current feature increment. | [src/stm32cubep_mcp/ioc_builder/server.py#L182](src/stm32cubep_mcp/ioc_builder/server.py#L182) |
