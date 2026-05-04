# STM32 Toolchain Config

This directory holds the shared STM32 Agent Toolchain configuration files.

- `stm32-tools.local.jsonc`: machine-local tool paths and host-specific discovery hints
- `stm32-project.jsonc`: project metadata consumed by the orchestration and domain servers

The orchestration server owns these configuration files. Tool-domain servers read them but should not define their own private copies.

`mcp.example.json` is the tracked example MCP registration. Copy its contents to `.vscode/mcp.json` for local VS Code or compatible MCP-client registration; `.vscode/` is intentionally ignored as a machine-local folder.

## Developer readiness

Run the local bootstrap before trying to expose the MCP tools:

```powershell
.\scripts\install-dev.ps1
```

Then check whether the workspace is ready for agent-driven build, flash, and debug work:

```powershell
.\scripts\check-agent-ready.ps1
```

The readiness check reports the virtual environment, MCP registration file, local STM32 tool paths, and the currently selected project metadata. Use `-Strict` in CI or automation when a non-zero exit code is useful.
