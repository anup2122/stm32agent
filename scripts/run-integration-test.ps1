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

$env:STM32CUBEP_RUN_INTEGRATION = "1"
$env:STM32CUBEP_TEST_FIRMWARE = $firmwarePath

Push-Location $workspaceRoot
try {
    & $venvPython -m unittest tests.test_server_integration -v
}
finally {
    Pop-Location
    Remove-Item Env:STM32CUBEP_RUN_INTEGRATION -ErrorAction SilentlyContinue
    Remove-Item Env:STM32CUBEP_TEST_FIRMWARE -ErrorAction SilentlyContinue
}

Write-Host "Integration test complete."