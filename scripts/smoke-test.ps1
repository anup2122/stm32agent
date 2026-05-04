$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found. Run scripts/install-dev.ps1 first."
}

Push-Location $workspaceRoot
try {
    & $venvPython -m unittest discover -s tests -v
    & $venvPython -c "from stm32cubep_mcp.cube_programmer.server import build_connect_command, build_download_arguments, stm32_discover_host_tools; from stm32cubep_mcp.orchestrator.server import orchestration_status; print(build_connect_command(port='SWD')); print(build_download_arguments('firmware.bin')); print(stm32_discover_host_tools()['host']); print(orchestration_status()['server'])"
}
finally {
    Pop-Location
}

Write-Host "Smoke test complete."
