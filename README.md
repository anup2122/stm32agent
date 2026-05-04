# stm32cubep-mcp

Python MCP server workspace for the STM32 Agent Toolchain.

## Release Summary 0.8.0

- Preserved the existing STM32CubeProgrammer MCP server as the current fully implemented tool-domain server.
- Implemented the first real Build MCP backend for STM32CubeIDE headless import and build flows using shared JSON metadata and file-based logs.
- Kept Debug and CubeMX as structural MCP server scaffolds so the codebase still matches the planned tool-domain architecture.
- Added an orchestration MCP server that owns shared configuration and routes high-level requests to the appropriate tool-domain server scaffold.
- Moved active shared configuration into `config/` so `stm32-tools.local.jsonc` and `stm32-project.jsonc` are no longer conceptually attached to the programmer server.
- Kept the existing programmer functionality, tests, and CLI wrappers intact while exposing a cleaner multi-server layout.

For the formal version history, see [CHANGELOG.md](CHANGELOG.md).

## Quick Start

Use this path when you want the shortest working setup.

1. Install the workspace tools:

```powershell
.\scripts\install-dev.ps1
```

2. Register the MCP servers locally by using [config/mcp.example.json](config/mcp.example.json) as the template for [.vscode/mcp.json](.vscode/mcp.json).

3. Run a quick readiness check:

```powershell
.\scripts\smoke-test.ps1
```

4. Start with the orchestrator server in Copilot and use a high-level request such as:

```text
Use stm32_orchestrate_prompt with prompt="build the current STM32 project"
```

For a fuller operator guide, direct-tool examples, and debug-oriented flows, see [docs/QUICKSTART.md](docs/QUICKSTART.md).

## Docs Index

- [docs/QUICKSTART.md](docs/QUICKSTART.md): operator-oriented setup and example prompts
- [docs/mcp-server-tools-reference.md](docs/mcp-server-tools-reference.md): all MCP servers, tools, signatures, and source locations
- [docs/end-to-end-call-chain.md](docs/end-to-end-call-chain.md): stitched architecture flow and Mermaid diagrams
- [docs/design.md](docs/design.md): design-level architecture and workflow intent
- [docs/stm32-agent-toolchain-plan.md](docs/stm32-agent-toolchain-plan.md): roadmap and planning history

## Repository Structure

- `config/`: shared host and project configuration for the full STM32 workflow
- [src/stm32cubep_mcp/cube_programmer/server.py](src/stm32cubep_mcp/cube_programmer/server.py): STM32CubeProgrammer MCP server implementation
- [src/stm32cubep_mcp/server.py](src/stm32cubep_mcp/server.py): legacy compatibility stub that is no longer used as an MCP entrypoint
- [src/stm32cubep_mcp/build/](src/stm32cubep_mcp/build/): CubeIDE Build MCP server
- [src/stm32cubep_mcp/debug/](src/stm32cubep_mcp/debug/): ST-LINK GDB server Phase 1 MCP
- [src/stm32cubep_mcp/cubemx/](src/stm32cubep_mcp/cubemx/): dummy CubeMX MCP server scaffold
- [src/stm32cubep_mcp/orchestrator/](src/stm32cubep_mcp/orchestrator/): orchestration MCP server scaffold

## Current scope

STM32CubeProgrammer, CubeIDE Build, and a Phase 1 plus Phase 2 ST-LINK GDB server MCP are implemented domain servers. CubeMX now has a Part 1 backend for IOC discovery, IOC parsing, CubeMX host discovery, and deterministic regeneration plumbing against an existing IOC file.

## How it works

1. VS Code starts the MCP server over stdio.
2. The server exposes connection, erase, download, verify, checksum, upload, read, write, reset, go, halt, run, step, core-status, list, version, and custom-command tools.
3. The simplest workflow is plain attached-device connect with SWD defaults.
4. Connected commands prepend a default STM32 device connection and retry common fallback combinations automatically.
5. Every command run writes a mandatory timestamped log file.
6. The CLI result is returned to the caller as structured JSON.

## Default STM32 CLI path

The server uses this default executable path:

`C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe`

You can override it with the `STM32_PROGRAMMER_CLI_PATH` environment variable.

## Setup

Run the install script from PowerShell:

```powershell
.\scripts\install-dev.ps1
```

For a shorter operator-oriented guide, see [docs/QUICKSTART.md](docs/QUICKSTART.md).

For a complete inventory of MCP servers, exported tools, signatures, and source locations, see [docs/mcp-server-tools-reference.md](docs/mcp-server-tools-reference.md).

For a short repo-wide sequence view that stitches the main MCP servers together, see [docs/end-to-end-call-chain.md](docs/end-to-end-call-chain.md).

Machine-local host tooling lives in [config/stm32-tools.local.jsonc](config/stm32-tools.local.jsonc) or an override file referenced by `STM32_TOOLS_LOCAL_JSON`.

Project metadata lives in [config/stm32-project.jsonc](config/stm32-project.jsonc) or an override file referenced by `STM32_PROJECT_JSON`.

For completed work, current gaps, and release history, see [CHANGELOG.md](CHANGELOG.md).

To run the hardware integration test against `UART_ReceptionToIdle_CircularDMA.axf`, use [scripts/run-integration-test.ps1](scripts/run-integration-test.ps1).

To run a one-shot production flash cycle against `UART_ReceptionToIdle_CircularDMA.axf`, use [scripts/run-production-flash-cycle.ps1](scripts/run-production-flash-cycle.ps1).

## Smoke test

```powershell
.\scripts\smoke-test.ps1
```

## VS Code integration

The workspace contains [.vscode/mcp.json](.vscode/mcp.json) that registers:

- `stm32orchestrator`
- `stm32cubeprogrammer`
- `stm32build`
- `stm32debug`
- `stm32cubemx`

## Orchestration

The main Copilot-facing server should now be `stm32orchestrator`.

It reads the shared config files, selects a domain server scaffold based on workflow intent, and normalizes the result shape.

Current orchestration tools:

- `stm32_orchestration_status`
- `stm32_orchestrate_prompt`
- `stm32_orchestrate_build`
- `stm32_orchestrate_build_then_flash`
- `stm32_orchestrate_debug`
- `stm32_orchestrate_debug_session`
- `stm32_orchestrate_flash`

## Build MCP

The Build MCP server executes STM32CubeIDE headless builds using the settings in [config/stm32-project.jsonc](config/stm32-project.jsonc) and the tool path in [config/stm32-tools.local.jsonc](config/stm32-tools.local.jsonc).

Current build tools:

- `stm32_build_capabilities`
- `stm32_build_project`

The current implementation:

- resolves `stm32cubeidec.exe`
- imports the configured CubeIDE project into the configured workspace
- runs `-cleanBuild` or `-build` for the selected configuration
- writes timestamped build logs under `logs/`

## Debug MCP

The Debug MCP server manages STM32CubeIDE's `ST-LINK_gdbserver.exe` process as a Phase 1 backend.

Current debug tools:

- `stm32_debug_capabilities`
- `stm32_debug_server_version`
- `stm32_debug_gdb_version`
- `stm32_debug_list_debuggers`
- `stm32_debug_launch`
- `stm32_debug_status`
- `stm32_debug_sessions`
- `stm32_debug_run_gdb_commands`
- `stm32_debug_inspect_peripheral`
- `stm32_debug_answer_question`
- `stm32_debug_uart_configuration`
- `stm32_debug_stop`
- `stm32_debug_snapshot`

The current implementation:

- resolves `ST-LINK_gdbserver.exe` from shared config, PATH, or the CubeIDE plugin tree
- resolves `arm-none-eabi-gdb` from shared config, PATH, or the CubeIDE plugin tree
- resolves the MCU SVD file automatically from STM32CubeCLT for generic register metadata
- derives the STM32CubeProgrammer `bin` path automatically for `-cp`
- avoids unusable local ports by falling back to bindable GDB/SWO ports when needed
- lists attached ST-LINK debuggers
- launches and stops managed debug-server sessions with structured log files
- exposes session status, port state, recent log tails, one-shot GDB command execution, structured runtime snapshots, and live SVD-backed peripheral/register inspection

Interactive breakpoints and stepping still need deeper GDB control work, but the debug agent can now answer live peripheral questions from target state when a debug session is available. Current question coverage includes UART baud/configuration, RCC clock-source questions, SPI mode and prescaler questions, I2C timing-field questions, timer prescaler and auto-reload questions, GPIO mode/pull/state questions, and ADC resolution or enable-state questions.

Example live debug prompts:

- `what is baudrate set in uart1`
- `what is the clock source in rcc`
- `what is spi1 cpol and cpha`
- `show i2c1 timing prescaler`
- `what is tim2 prescaler`
- `what is gpioa pin 5 mode`
- `what is gpioa pin 5 state`
- `what is adc1 resolution`

## CubeMX MCP

The CubeMX MCP server now supports the first deterministic backend slice for IOC-driven work.

Current CubeMX tools:

- `stm32_cubemx_capabilities`
- `stm32_cubemx_parse_ioc`
- `stm32_cubemx_regenerate_project`

The current implementation:

- resolves STM32CubeMX from shared config, standard install paths, or the bundled CubeMX JAR inside STM32CubeIDE
- resolves a Java runtime for the CubeMX JAR fallback from bundled STM32CubeIDE JRE plugins or `PATH`
- searches for an IOC file from `firmware.ioc_path` or the configured project tree when no IOC path is explicitly configured
- parses IOC metadata including MCU, toolchain, peripheral list, and pin signal assignments
- runs deterministic regeneration through a generated CubeMX script file
- records a regeneration log, affected files, and optional Build MCP validation results

CubeMX Part 1 is intentionally limited to existing IOC-backed projects. It does not yet implement freeform requirement decomposition or feature synthesis.

## Host Discovery

Use these tools before hardware operations when you need to understand host readiness:

- `stm32_discover_host_tools`
- `stm32_report_host_capabilities`

`stm32_discover_host_tools` reports which config files were found, where the packaged schemas live, and which STM32CubeProgrammer paths were checked.

`stm32_report_host_capabilities` additionally probes `--version` and reports whether connect, flash, memory, and core-control workflows are available on the current host.

## Example tool intent

Simple attached-device connect:

```text
Connect to attached stm32 device
```

Explicit SWD connect:

```text
Use stm32_connect with port=SWD, frequency_khz=4000, mode=NORMAL
```

Connect through UART:

```text
Use stm32_connect with port=COM5, baudrate=115200, parity=EVEN
```

Enable low-power debug explicitly when needed:

```text
Use stm32_connect with port=SWD, frequency_khz=4000, low_power_mode=enable
```

Program firmware:

```text
Use stm32_download with file_path=firmware.bin
```

Erase flash:

```text
Use stm32_erase
```

Read memory:

```text
Use stm32_read_memory with address=0x08000000, size=16, width=32
```

Run a custom unsupported CLI sequence:

```text
Use stm32_custom_command with command_arguments=["--blankcheck"]
```

## Retry behavior

If the default attempt fails, the server retries these common SWD variants:

1. `SWD`, `4000`, `NORMAL`, `SWrst`
2. `SWD`, `4000`, `HOTPLUG`, `SWrst`
3. `SWD`, `4000`, `UR`, `HWrst`
4. `SWD`, `1000`, `NORMAL`, `HWrst`
5. `SWD`, `1000`, `HOTPLUG`, `HWrst`

If all attempts fail, the result tells Copilot to ask the user for the correct connection parameters.

## Logs

Each command attempt writes a required log file in `logs/` named like `download_YYYYMMDD_HHMMSS.log` or `connect_YYYYMMDD_HHMMSS.log`.

If a firmware looks like it targets a different STM32 family and the post-run core status is halted, the server reports `this does not match to the attached target`.

## Assisted Recovery

When a connected STM32 command fails, the server can ask the attached MCP client LLM for one next recovery step at a time.

- The loop is bounded and stops after a configurable number of tries.
- The LLM can only choose from constrained recovery actions such as retrying the original operation with updated connect settings, reading core status, resetting, halting, going, listing interfaces, or stopping to ask the user.
- If the client does not support MCP sampling, the original command failure is returned unchanged except for recovery metadata.

Environment variables:

- `STM32CUBEP_MCP_ENABLE_LLM_RECOVERY=true|false`
- `STM32CUBEP_MCP_LLM_RECOVERY_MAX_ATTEMPTS=3`

## Supported tools

- `stm32_orchestration_status`
- `stm32_orchestrate_prompt`
- `stm32_orchestrate_build`
- `stm32_orchestrate_build_then_flash`
- `stm32_orchestrate_debug`
- `stm32_orchestrate_debug_session`
- `stm32_orchestrate_flash`
- `stm32_debug_capabilities`
- `stm32_debug_server_version`
- `stm32_debug_gdb_version`
- `stm32_debug_list_debuggers`
- `stm32_debug_run_gdb_commands`
- `stm32_debug_inspect_peripheral`
- `stm32_debug_answer_question`
- `stm32_debug_uart_configuration`
- `stm32_debug_launch`
- `stm32_debug_status`
- `stm32_debug_sessions`
- `stm32_debug_stop`
- `connect_to_attached_stm32_device`
- `stm32_connect`
- `stm32_discover_host_tools`
- `stm32_report_host_capabilities`
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
