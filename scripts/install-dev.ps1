$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $workspaceRoot ".venv"
$mcpTemplatePath = Join-Path $workspaceRoot "config\mcp.example.json"
$mcpConfigPath = Join-Path $workspaceRoot ".vscode\mcp.json"

function Resolve-Python {
    $candidates = @(
        $env:STM32AGENT_PYTHON,
        "C:\Program Files\Python312\python.exe",
        "C:\Python313\python.exe",
        "C:\Python312\python.exe"
    ) | Where-Object { $_ -and $_.Trim() }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return $pyLauncher.Source
    }

    throw "Python was not found. Install Python 3.11+ or set STM32AGENT_PYTHON to a python.exe path."
}

$basePython = Resolve-Python

if (-not (Test-Path $venvPath)) {
    if ((Split-Path -Leaf $basePython) -ieq "py.exe") {
        & $basePython -3 -m venv $venvPath
    }
    else {
        & $basePython -m venv $venvPath
    }
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"

if ((Test-Path $mcpTemplatePath) -and -not (Test-Path $mcpConfigPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $mcpConfigPath) | Out-Null
    Copy-Item -Path $mcpTemplatePath -Destination $mcpConfigPath
}

Push-Location $workspaceRoot
try {
    & $venvPython -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install setuptools wheel
    & $venvPython -m pip install -e ".[dev]"
    & $venvPython -m build --no-isolation
}
finally {
    Pop-Location
}

Write-Host "Installation and build complete."
