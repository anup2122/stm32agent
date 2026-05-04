# STM32 Agent Toolchain

## Purpose

Create a complete STM32 Copilot workflow that can understand project context, build firmware, flash images, debug running code, and support fix-and-retest loops through MCP-integrated tools.

## Working Principles

- Keep tool integrations modular by domain.
- Prefer non-intrusive setup with no admin-right requirement from the Copilot workflow.
- Use cross-platform host behavior where possible: Windows, Linux, macOS.
- Keep machine-local tool paths out of instructions and in local JSON.
- Keep project-specific facts in structured project metadata.
- Expose high-level STM32 workflows through an orchestration layer.

## Configuration Model

### Local host tools

- File: `stm32-tools.local.json`
- Scope: machine-local, shared by all STM32 projects on that machine
- Purpose: store executable paths, overrides, and host-specific discovery hints
- Characteristics: optional, non-intrusive, no elevation required, cross-platform schema

### Project metadata

- File: `stm32-project.json`
- Scope: project-specific
- Purpose: board, MCU, build system, output artifacts, debug profile, and project facts

### Copilot behavior

- File: `copilot-instructions.md`
- Scope: workflow and policy only
- Purpose: tell Copilot how to use the metadata and which MCP workflows to prefer

## Architecture Direction

### Tool-domain MCP servers

- STM32CubeProgrammer MCP for connect, erase, flash, verify, reset, memory, and diagnostics
- Build MCP for CubeIDE, CMake, Make, and later other build backends
- Debug MCP for debug server launch, GDB attach, breakpoints, registers, memory, and snapshots
- Optional CubeMX MCP for `.ioc` parsing and project generation/regeneration

### Orchestration MCP server

- Main Copilot-facing server for STM32 workflows
- Reads `stm32-tools.local.json` and `stm32-project.json`
- Selects the right backend tools
- Normalizes results and workflow state
- Exposes higher-level tools such as build, flash, debug, diagnose, and repair loops

## Recommended Interaction Model

- Copilot should primarily call the STM32 orchestration MCP server
- Low-level MCP servers should remain available for expert or manual use
- Multi-step workflows should not rely on prompt-only reasoning across many raw tool APIs

## Near-Term Roadmap

1. Define the schema for `stm32-tools.local.json` - completed in `src/stm32cubep_mcp/schemas/stm32-tools.local.schema.json`
2. Define the schema for `stm32-project.json` - completed in `src/stm32cubep_mcp/schemas/stm32-project.schema.json`
3. Add host tool discovery and capability reporting - completed through `stm32_discover_host_tools` and `stm32_report_host_capabilities`
4. Add build MCP support - started with real CubeIDE headless build execution in `src/stm32cubep_mcp/build/server.py`
5. Add debug MCP support with structured debug snapshots - started with a Phase 1 ST-LINK GDB server MCP in `src/stm32cubep_mcp/debug/server.py`
6. Add orchestration MCP workflows that combine build, flash, debug, and diagnosis

## Resume Context

When resuming this work later, use this project name:

- `STM32 Agent Toolchain`

Current saved state:

- Shared config now lives under `config/` and is owned by the orchestration layer.
- Implemented domain servers:
	- STM32CubeProgrammer MCP in `src/stm32cubep_mcp/cube_programmer/server.py`
	- CubeIDE Build MCP in `src/stm32cubep_mcp/build/server.py`
- Partially implemented domain servers:
	- Debug MCP in `src/stm32cubep_mcp/debug/server.py` with ST-LINK GDB server discovery, version, debugger listing, launch, status, and stop support
- Scaffolded domain servers:
	- CubeMX MCP in `src/stm32cubep_mcp/cubemx/server.py`
- Orchestration MCP exists in `src/stm32cubep_mcp/orchestrator/server.py`, includes a native build-then-flash workflow, and now routes debug prompts into the Phase 1 Debug MCP launch entry point.
- Build MCP is validated against the external `CORTEXM_SysTick` CubeIDE project configured in `config/stm32-project.json`.
- Latest real build validation succeeded for `CORTEXM_SysTick/Release`.
- Latest build-to-device validation succeeded for `CORTEXM_SysTick/Release` through the orchestrator.
- Latest debug-host validation found `ST-LINK_gdbserver.exe` version, ST-LINK probe discovery, reset, launch, status, and stop all working after moving debug ports off the Windows excluded `61217-61316` range.
- Latest focused test status: `18` tests passed across debug, architecture, and build smoke coverage.

Useful resume prompts:

- `Resume the STM32 Agent Toolchain project and review the current plan.`
- `Continue the STM32 Agent Toolchain work from the roadmap in stm32-agent-toolchain-plan.md.`
- `For the STM32 Agent Toolchain project, implement the next roadmap item.`
- `Resume the STM32 Agent Toolchain project from the saved state in stm32-agent-toolchain-plan.md and continue after the ST-LINK firmware blocker.`

## Current Decisions

- Use `stm32-tools.local.json` for machine-local tool definitions
- Do not use instructions as the main storage for tool paths
- Keep the setup non-intrusive and avoid requiring elevation
- Target Windows, Linux, and macOS as host operating systems
- Favor a layered architecture: tool MCP servers plus one STM32 orchestration MCP server
- Store active shared JSON configuration under `config/` so it is owned by the orchestration layer rather than any single tool-domain server