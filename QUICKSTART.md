# Quick User Guide

## What This Server Does

This workspace now contains one orchestration MCP server and several tool-domain MCP servers.

The intended main entry point is the orchestration server, which reads `config/stm32-tools.local.json` and `config/stm32-project.json` and then routes the request to the right domain server.

The Build MCP server is now implemented for STM32CubeIDE headless builds.

The Debug MCP server now manages STM32CubeIDE ST-LINK GDB server sessions.

The default debug config now uses `55001` for GDB and `55002` for SWO, and the server can fall back automatically if the requested ports are blocked.

## Default Behavior

When you say `connect to attached stm32 device`, the server will:

1. Use `SWD`
2. Use `4000 KHz`
3. Use `NORMAL` mode
4. Retry a few common fallback options if the first connection fails
5. Create a log file automatically

## Basic Setup

From PowerShell in the project folder:

```powershell
.\scripts\install-dev.ps1
```

Optional check:

```powershell
.\scripts\smoke-test.ps1
```

## Simple Prompts To Use

Check orchestration status first:

```text
Use stm32_orchestration_status
```

Check host setup first:

```text
Use stm32_report_host_capabilities
```

Connect to the board:

```text
Connect to attached stm32 device
```

Erase flash:

```text
Use stm32_erase
```

Program a firmware file:

```text
Use stm32_download with file_path=firmware.bin
```

Route a high-level request through the orchestrator:

```text
Use stm32_orchestrate_prompt with prompt="build the current STM32 project"
```

Build through CubeIDE directly:

```text
Use stm32_build_project with target=Release
```

Launch the ST-LINK GDB server:

```text
Use stm32_debug_launch
```

Check the current debug server session:

```text
Use stm32_debug_status
```

List connected ST-LINK debuggers visible to the GDB server:

```text
Use stm32_debug_list_debuggers
```

Program the sample firmware already in this workspace:

```text
Use stm32_download with file_path=C:\agent_dev_v1\mcp-server-stm32cubep\UART_ReceptionToIdle_CircularDMA.axf
```

Run a production-style flash flow in one step:

```text
Use stm32_flash_firmware with file_path=C:\agent_dev_v1\mcp-server-stm32cubep\UART_ReceptionToIdle_CircularDMA.axf
```

Run a full orchestrated build-then-flash flow in one step:

```text
Use stm32_orchestrate_build_then_flash
```

Run a reset-first orchestrated debug session:

```text
Use stm32_orchestrate_debug
```

Run a prompt-routed runtime diagnosis request:

```text
Use stm32_orchestrate_prompt with prompt="start a runtime debug session for this stm32 target"
```

Check the Phase 2 ARM GDB client:

```text
Use stm32_debug_gdb_version
```

Capture a structured runtime snapshot from a running debug session:

```text
Use stm32_debug_snapshot with session_name=default
```

Run one-shot GDB commands against a running session:

```text
Use stm32_debug_run_gdb_commands with session_name=default, commands=["info registers", "bt"]
```

Inspect a live peripheral with SVD-backed register decoding:

```text
Use stm32_debug_inspect_peripheral with session_name=default, peripheral="USART1"
```

Ask the debug agent a live peripheral question:

```text
Use stm32_debug_answer_question with question="what is baudrate set in uart1", session_name=default
```

Additional live debug questions:

```text
Use stm32_debug_answer_question with question="what is the clock source in rcc", session_name=default
```

```text
Use stm32_debug_answer_question with question="what is spi1 cpol and cpha", session_name=default
```

```text
Use stm32_debug_answer_question with question="show i2c1 timing prescaler", session_name=default
```

```text
Use stm32_debug_answer_question with question="what is tim2 prescaler", session_name=default
```

```text
Use stm32_debug_answer_question with question="what is gpioa pin 5 mode", session_name=default
```

```text
Use stm32_debug_answer_question with question="what is gpioa pin 5 state", session_name=default
```

```text
Use stm32_debug_answer_question with question="what is adc1 resolution", session_name=default
```

Run the full prompt-driven agentic path:

```text
Use stm32_orchestrate_prompt with prompt="what is baudrate set in uart1"
```

Additional prompt-routed examples:

```text
Use stm32_orchestrate_prompt with prompt="what is the clock source in rcc"
```

```text
Use stm32_orchestrate_prompt with prompt="what is spi1 cpol and cpha"
```

```text
Use stm32_orchestrate_prompt with prompt="show i2c1 timing prescaler"
```

```text
Use stm32_orchestrate_prompt with prompt="what is tim2 prescaler"
```

```text
Use stm32_orchestrate_prompt with prompt="what is gpioa pin 5 mode"
```

```text
Use stm32_orchestrate_prompt with prompt="what is adc1 resolution"
```

Inspect CubeMX host readiness and IOC discovery state:

```text
Use stm32_cubemx_capabilities
```

Parse the current IOC file directly:

```text
Use stm32_cubemx_parse_ioc
```

Parse a specific IOC file directly:

```text
Use stm32_cubemx_parse_ioc with ioc_path="C:/path/to/project.ioc"
```

Run deterministic CubeMX regeneration for the current IOC and validate it with the Build MCP:

```text
Use stm32_cubemx_regenerate_project
```

Run deterministic CubeMX regeneration without build validation:

```text
Use stm32_cubemx_regenerate_project with validate_build=false
```

Reset the board:

```text
Use stm32_reset
```

Run the program:

```text
Use stm32_go
```

Read core status:

```text
Use stm32_core_status
```

## Logs

Every command writes a log file into `logs/`.

Examples:

- `connect_YYYYMMDD_HHMMSS.log`
- `download_YYYYMMDD_HHMMSS.log`
- `reset_YYYYMMDD_HHMMSS.log`

## Real Hardware Test

To run the hardware integration test against the attached board and the sample AXF in this workspace:

```powershell
.\scripts\run-integration-test.ps1
```

## Most Useful Commands

- `stm32_orchestration_status`
- `stm32_orchestrate_prompt`
- `stm32_orchestrate_build`
- `stm32_orchestrate_build_then_flash`
- `stm32_orchestrate_debug`
- `stm32_orchestrate_debug_session`
- `stm32_orchestrate_flash`
- `stm32_build_capabilities`
- `stm32_build_project`
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
- `stm32_cubemx_capabilities`
- `stm32_cubemx_parse_ioc`
- `stm32_cubemx_regenerate_project`
- `connect_to_attached_stm32_device`
- `stm32_connect`
- `stm32_discover_host_tools`
- `stm32_report_host_capabilities`
- `stm32_erase`
- `stm32_download`
- `stm32_flash_firmware`
- `stm32_verify`
- `stm32_reset`
- `stm32_go`
- `stm32_core_status`
- `stm32_custom_command`

## Production Flash Test

To run a production-style real hardware flash cycle with erase, download, verify, and go:

```powershell
.\scripts\run-production-flash-cycle.ps1
```

## If Connection Fails

1. Check that the board is powered
2. Check that ST-LINK is detected
3. Check the USB cable
4. If needed, give explicit parameters such as `port`, `frequency_khz`, `mode`, or `reset`

Example:

```text
Use stm32_connect with port=SWD, frequency_khz=1000, mode=HOTPLUG, reset=HWrst
```

If you need to check which config files or CLI paths are being used:

```text
Use stm32_discover_host_tools
```

## Wrong Firmware Detection

If a firmware file appears to target a different MCU family and the post-run core status comes back halted, the server reports:

```text
this does not match to the attached target
```

This is now covered by a real hardware test using `XNUCLEO-F103RB-binary.axf` against the attached L476 board.