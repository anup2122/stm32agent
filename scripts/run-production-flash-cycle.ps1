$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
$firmwarePath = Join-Path $workspaceRoot "UART_ReceptionToIdle_CircularDMA.axf"

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found. Run scripts/install-dev.ps1 first."
}

if (-not (Test-Path $firmwarePath)) {
    throw "Firmware file not found: $firmwarePath"
}

Push-Location $workspaceRoot
try {
    & $venvPython -c "from stm32cubep_mcp.cube_programmer.server import stm32_flash_firmware; import json; result = stm32_flash_firmware(file_path=r'$firmwarePath', timeout_seconds=300); print(json.dumps(result, indent=2))"
}
finally {
    Pop-Location
}

Write-Host "Production flash cycle complete."