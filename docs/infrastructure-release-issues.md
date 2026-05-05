# Infrastructure Release Issues

Created: 2026-05-02

Purpose: capture non-core infrastructure issues to revisit after the core MCP/server code is stable.

## Current Assessment

The infrastructure layer is useful for local development, but it is not yet in product-release-grade shape.

## Issues To Revisit

### 1. install-dev.ps1 does not fail hard on native command errors

File: `scripts/install-dev.ps1`

Problem:

- The script runs native commands such as `pip` and `build`, but it does not explicitly check `$LASTEXITCODE` after each command.
- In PowerShell, `$ErrorActionPreference = "Stop"` does not reliably convert non-zero native process exits into terminating errors.
- The script always prints `Installation and build complete.` at the end, which can create a false-success outcome.

Why this matters:

- A release bootstrap path must fail deterministically.
- CI and user-facing setup flows cannot rely on best-effort success messages.

Suggested follow-up:

- Wrap native command execution in a helper that throws on non-zero exit.
- Only print the success banner if all steps completed successfully.

### 2. install-dev.ps1 does not select Python deterministically enough

File: `scripts/install-dev.ps1`

Problem:

- The package requires Python `>=3.11`, but the script may create the environment through `py -3`, which can resolve differently across machines.
- The version check happens after the virtual environment is created instead of before interpreter selection is finalized.

Why this matters:

- Release-grade setup should align interpreter selection with the declared package contract.
- Machine-dependent interpreter resolution increases setup variability.

Suggested follow-up:

- Probe interpreter candidates for version compatibility before venv creation.
- Prefer explicit Python 3.11+ resolution instead of generic `py -3`.

### 3. install-dev.ps1 copies MCP client config without verifying generated launchers

Files:

- `scripts/install-dev.ps1`
- `config/mcp.example.json`

Problem:

- The script copies the MCP registration template into `.vscode/mcp.json`.
- The copied config points to generated launchers such as `stm32cubeprogrammer-mcp.exe`.
- The script does not verify that those expected launchers actually exist after installation.

Why this matters:

- The client registration file is the user-facing launch contract.
- A copied config is not trustworthy if the referenced executables are not validated.

Suggested follow-up:

- Add post-install verification for all referenced MCP entry points.
- Fail the install if required launchers are missing.

### 4. smoke-test.ps1 can produce false-green results

File: `scripts/smoke-test.ps1`

Problem:

- The script runs tests and ad hoc Python commands, but it does not explicitly fail on native command exit codes.
- It always prints `Smoke test complete.` after execution.

Why this matters:

- Smoke tests should be trustworthy enough for automation and quick operator validation.
- A release-grade smoke check must return a reliable pass/fail signal.

Suggested follow-up:

- Use the same native-command failure handling strategy as the installer.
- Only print completion/success output after verified success.

### 5. Infrastructure scripts need a clearer product-vs-dev contract

Files:

- `scripts/install-dev.ps1`
- `scripts/check-agent-ready.ps1`
- `scripts/smoke-test.ps1`
- [README.md](../README.md)
- [QUICKSTART.md](QUICKSTART.md)

Problem:

- The current scripts are good enough for local development support.
- They are not yet strict enough to be treated as product-grade install/verification tooling.
- The documentation currently presents them as the main setup path, which can overstate their robustness.

Why this matters:

- Product-grade tooling needs deterministic behavior, explicit failure conditions, and validated outputs.
- If the scripts are still dev helpers, that should be clearly communicated.

Suggested follow-up:

- Decide whether these scripts are internal dev bootstrap tools or supported release install flows.
- Tighten behavior and docs to match that decision.

## Recommended Revisit Order

1. Harden `install-dev.ps1` native command failure handling.
2. Make Python 3.11+ selection deterministic before venv creation.
3. Align launcher verification with `config/mcp.example.json`.
4. Harden `check-agent-ready.ps1` and `smoke-test.ps1` to produce trustworthy pass/fail results.
5. Update setup documentation to match the intended support level.
