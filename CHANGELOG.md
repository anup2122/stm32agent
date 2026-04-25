# Changelog

All notable changes to this package are documented in this file.

## [Unreleased]

### Added

- CubeMX Part 1 backend support in `src/stm32cubep_mcp/cubemx/server.py` for IOC discovery, IOC parsing, CubeMX tool discovery, deterministic regeneration scripting, and optional Build MCP validation.
- Focused CubeMX smoke coverage in `tests/test_cubemx_smoke.py`.

### Changed

- `config/stm32-tools.local.json` now defines `cubemx` using the same structured tool schema as the other host tools.
- CubeMX discovery now falls back to the bundled `STM32CubeMX.jar` and bundled JRE plugins inside STM32CubeIDE when the standalone executable is not installed.

## [0.8.0] - 2026-04-16

### Added

- Phase 2 ARM GDB client discovery in `src/stm32cubep_mcp/debug/server.py`.
- New debug tools `stm32_debug_gdb_version` and `stm32_debug_run_gdb_commands`.
- Structured runtime snapshot collection through `stm32_debug_snapshot` using a batch ARM GDB client connection to a managed ST-LINK GDB server session.
- Generic SVD-backed live peripheral/register inspection through `stm32_debug_inspect_peripheral`.
- Natural-language live debug questions through `stm32_debug_answer_question`, including live UART baud-rate estimation from target registers.
- Broader semantic live debug questions for RCC, SPI, I2C, TIM, GPIO, and ADC field-level inspection.
- Shared local tool config support for `arm_gdb` in `config/stm32-tools.local.json` and `src/stm32cubep_mcp/schemas/stm32-tools.local.schema.json`.
- Focused Phase 2 smoke coverage for GDB client discovery and snapshot parsing in `tests/test_debug_smoke.py`.

### Changed

- `stm32_debug_capabilities` now reports GDB client discovery and runtime-inspection readiness.
- Debug snapshots are no longer a placeholder; they now return registers, backtrace, stack lines, and the raw transcript when a managed debug session is active.
- The orchestrator now routes peripheral/register questions such as UART baud-rate queries into the debug agent's live inspection path.
- The debug question path now returns semantic live answers for clock-source, mode, timing, prescaler, GPIO pin, and ADC resolution prompts instead of only raw register dumps.

### Notes

- Breakpoints, interactive stepping, and long-lived GDB control remain future work beyond this first Phase 2 increment.

## [0.7.0] - 2026-04-16

### Added

- Phase 1 ST-LINK GDB server MCP implementation in `src/stm32cubep_mcp/debug/server.py`.
- Managed debug tools for version, debugger discovery, launch, status, session listing, and stop operations.
- Shared tool config support for `stlink_gdb_server` in `config/stm32-tools.local.json` and `src/stm32cubep_mcp/schemas/stm32-tools.local.schema.json`.
- Focused debug smoke coverage in `tests/test_debug_smoke.py`.

### Changed

- Debug MCP is no longer a pure scaffold; it now manages the STM32CubeIDE ST-LINK GDB server process lifecycle.
- Example project debug metadata now includes default GDB and SWO ports.
- Debug launch now avoids Windows-excluded port ranges by selecting bindable fallback ports when the requested ports are unavailable.

### Verified

- Focused validation passed with `python -m unittest tests.test_debug_smoke tests.test_architecture tests.test_build_smoke -v` => 18 tests OK.
- Real host validation succeeded for debug-server version and ST-LINK discovery.
- Real reset-plus-launch validation succeeded for the ST-LINK GDB server on ports `55001/55002`, followed by successful status and stop checks.

### Notes

- Structured debug snapshots, registers, memory inspection, breakpoints, and backtraces still require a Phase 2 GDB client control layer.

## [0.6.0] - 2026-04-15

### Added

- Real STM32CubeIDE headless build execution in `src/stm32cubep_mcp/build/server.py`.
- Shared config fields for CubeIDE workspace, project path, project name, default configuration, available configurations, and build behavior.
- Smoke-level Build MCP tests in `tests/test_build_smoke.py`.

### Changed

- `config/stm32-tools.local.json` now carries the exact CubeIDE CLI path from the provided batch workflow.
- `config/stm32-project.json` now reflects the external `CORTEXM_SysTick` CubeIDE project and configurations from the provided batch workflow.
- Build logs are now written under `logs/` for CubeIDE runs and can be used later for diagnosis and repair loops.

### Verified

- Real Build MCP validation succeeded for `CORTEXM_SysTick/Release` using `C:/ST/STM32CubeIDE_1.14.1/STM32CubeIDE/stm32cubeidec.exe`.

## [0.5.0] - 2026-04-15

### Added

- New package structure for multi-server STM32 workflows:
  - `src/stm32cubep_mcp/build/`
  - `src/stm32cubep_mcp/debug/`
  - `src/stm32cubep_mcp/cubemx/`
  - `src/stm32cubep_mcp/orchestrator/`
  - `src/stm32cubep_mcp/cube_programmer/`
- Shared active configuration directory at `config/` with:
  - `config/stm32-tools.local.json`
  - `config/stm32-project.json`
  - `config/README.md`
- Dummy Build, Debug, and CubeMX MCP servers with stable stdio entry points.
- An orchestration MCP server with high-level routing and status tools.
- Additional package entry points for each server role.

### Changed

- VS Code MCP registration now exposes the orchestration server plus the tool-domain server scaffolds.
- Shared config lookup now prefers the top-level `config/` directory.

### Notes

- STM32CubeProgrammer and CubeIDE Build are implemented domain servers.
- Debug, CubeMX, and Orchestrator remain scaffolds intended to stabilize structure before deeper backend implementation work begins.

## [0.4.0] - 2026-04-15

### Added

- Formal packaged JSON schemas for `stm32-tools.local.json` and `stm32-project.json`.
- Example `.github/stm32-project.json` metadata for this workspace.
- Host discovery support that searches environment overrides, workspace config files, PATH, and built-in candidates for STM32CubeProgrammer.
- New MCP tools:
  - `stm32_discover_host_tools`
  - `stm32_report_host_capabilities`

### Changed

- `resolve_cli_path()` now honors `stm32-tools.local.json` discovery candidates instead of only checking the environment override and hardcoded default path.
- `run_cli_command()` now returns structured failures for missing executables.
- Packaging now includes the JSON schema files in both source distributions and wheels.

### Recommended Next Work

- Add build MCP support and connect it to `stm32-project.json` build metadata.
- Add debug MCP support with structured debug snapshots.

## [0.3.0] - 2026-03-24

### Added

- Python MCP server built with FastMCP and stdio transport for GitHub Copilot in VS Code.
- Natural-language connect support through `connect_to_attached_stm32_device`.
- Explicit `stm32_connect` support with validated connection arguments.
- Default SWD connection settings: `port=SWD`, `frequency_khz=4000`, `mode=NORMAL`.
- Automatic fallback retries for common SWD connection combinations.
- Mandatory timestamped log files for every command attempt in `logs/`.
- First-class wrappers for the main STM32CubeProgrammer flows:
  - `stm32_programmer_version`
  - `stm32_list_interfaces`
  - `stm32_erase`
  - `stm32_download`
  - `stm32_flash_firmware`
  - `stm32_verify`
  - `stm32_checksum`
  - `stm32_upload`
  - `stm32_read_memory`
  - `stm32_write_memory`
  - `stm32_reset`
  - `stm32_go`
  - `stm32_halt`
  - `stm32_run_core`
  - `stm32_step_core`
  - `stm32_core_status`
  - `stm32_custom_command`
- One-shot production flash flow through `stm32_flash_firmware`.
- Download validation and post-action handling for flash workflows.
- Runtime wrong-target detection for firmware that programs successfully but halts after launch.
- Mismatch reporting with the message `this does not match to the attached target`.
- Extraction of attached target families from STM32CubeProgrammer board and device output.
- Firmware family inference from file content and filename hints.
- VS Code MCP registration in `.vscode/mcp.json`.
- Install, smoke-test, integration-test, production-flash, and zip-packaging PowerShell scripts.
- Quick operator guide in `QUICKSTART.md`.
- Extensive unit coverage for builders, retries, logging, wrappers, and mismatch detection.
- Hardware integration tests using:
  - `UART_ReceptionToIdle_CircularDMA.axf` for valid-target testing
  - `XNUCLEO-F103RB-binary.axf` for wrong-target testing
- Bounded LLM-guided recovery for failed STM32 device operations when the MCP client supports sampling.

### Changed

- Packaging now includes the formal changelog.
- README now contains a version `0.3.0` release summary and documents the assisted recovery loop.

### Verified

- Connect to an attached NUCLEO-L476RG board through ST-LINK.
- Erase, download, verify, reset, and run valid firmware.
- Detect a wrong-target firmware case that is not rejected during program and verify but fails at runtime.
- Return structured JSON results suitable for Copilot tool use.

### Known Limitations

- No first-class wrappers yet for `--blankcheck`.
- No first-class wrappers yet for option-byte operations.
- No first-class wrappers yet for readout-protection flows.
- No first-class wrappers yet for wireless, RSS, HSM, provisioning, or secure-programming command families.
- No persistent device session state between MCP tool calls beyond per-command connect behavior.
- No board database or explicit MCU compatibility table beyond family-hint inference from firmware and CLI output.
- Wrong-target detection is strongest on flows that include `go` or another runtime validation step.
- No dedicated binary, intel-hex, or ELF metadata parser beyond the current text and filename heuristics.
- No mock CLI fixture layer for replaying full STM32CubeProgrammer transcripts across many hardware variants.
- Hardware integration tests are environment-gated and require STM32 hardware, ST-LINK access, and STM32CubeProgrammer installation.
- No CI pipeline has been set up in this package yet.
- No signed release artifacts or installer package are provided.
- LLM-guided recovery depends on MCP sampling support in the connected client and is intentionally limited to a constrained action set.

### Recommended Next Work

- Add first-class support for blank check.
- Add first-class support for option-byte read and write flows.
- Add first-class support for readout-protection and unprotect flows.
- Extend mismatch detection to more run and reset scenarios.
- Add stronger firmware metadata inspection for ELF, AXF, HEX, and BIN formats.
- Add CI automation for unit tests, packaging, and optional hardware-gated stages.