$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$basePython = "C:\Program Files\Python312\python.exe"
$venvPath = Join-Path $workspaceRoot ".venv"

if (-not (Test-Path $venvPath)) {
    & $basePython -m venv $venvPath
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"

Push-Location $workspaceRoot
try {
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install setuptools wheel
    & $venvPython -m pip install -e ".[dev]"
    & $venvPython -m build --no-isolation
}
finally {
    Pop-Location
}

Write-Host "Installation and build complete."
