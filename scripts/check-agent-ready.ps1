param(
    [switch]$Json,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
$mcpConfigPath = Join-Path $workspaceRoot ".vscode\mcp.json"
$toolsConfigPath = Join-Path $workspaceRoot "config\stm32-tools.local.json"
$projectConfigPath = Join-Path $workspaceRoot "config\stm32-project.json"

function New-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [string]$Detail
    )

    [pscustomobject]@{
        name = $Name
        ok = $Ok
        detail = $Detail
    }
}

function Test-CommandSuccess {
    param([scriptblock]$Command)

    try {
        & $Command | Out-Null
        return $LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE
    }
    catch {
        return $false
    }
}

function Resolve-ConfigPath {
    param(
        [string]$Value,
        [string]$BasePath
    )

    if (-not $Value) {
        return $null
    }

    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $Value))
}

$checks = New-Object System.Collections.Generic.List[object]

$checks.Add((New-Check "workspace" (Test-Path $workspaceRoot) $workspaceRoot))
$checks.Add((New-Check "virtualenv" (Test-Path $venvPython) $venvPython))
$checks.Add((New-Check "mcp_config" (Test-Path $mcpConfigPath) $mcpConfigPath))
$checks.Add((New-Check "tools_config" (Test-Path $toolsConfigPath) $toolsConfigPath))
$checks.Add((New-Check "project_config" (Test-Path $projectConfigPath) $projectConfigPath))

if (Test-Path $venvPython) {
    $importOk = Test-CommandSuccess {
        & $venvPython -c "import stm32cubep_mcp.server, stm32cubep_mcp.orchestrator.server, stm32cubep_mcp.build.server, stm32cubep_mcp.debug.server, stm32cubep_mcp.cubemx.server"
    }
    $checks.Add((New-Check "python_imports" $importOk "Import programmer, orchestrator, build, debug, and cubemx servers"))

    $entrypoints = @(
        "stm32cubep-mcp.exe",
        "stm32-orchestrator-mcp.exe",
        "stm32-build-mcp.exe",
        "stm32-debug-mcp.exe",
        "stm32-cubemx-mcp.exe",
        "stm32-requirements-mcp.exe",
        "stm32-ioc-builder-mcp.exe"
    )
    foreach ($entrypoint in $entrypoints) {
        $path = Join-Path $workspaceRoot ".venv\Scripts\$entrypoint"
        $checks.Add((New-Check "entrypoint:$entrypoint" (Test-Path $path) $path))
    }
}

if (Test-Path $toolsConfigPath) {
    try {
        $toolsConfig = Get-Content $toolsConfigPath -Raw | ConvertFrom-Json
        foreach ($toolName in @("cube_programmer", "cubeide", "stlink_gdb_server", "arm_gdb", "cubemx")) {
            $tool = $toolsConfig.tools.$toolName
            $candidates = @()
            if ($tool -and $tool.candidates -and $tool.candidates.windows) {
                $candidates = @($tool.candidates.windows)
            }
            $found = $false
            $foundPath = ""
            foreach ($candidate in $candidates) {
                if (Test-Path $candidate) {
                    $found = $true
                    $foundPath = $candidate
                    break
                }
            }
            $detail = if ($found) { $foundPath } else { "No configured Windows candidate exists on disk" }
            $checks.Add((New-Check "tool:$toolName" $found $detail))
        }
    }
    catch {
        $checks.Add((New-Check "tools_config_parse" $false $_.Exception.Message))
    }
}

if (Test-Path $projectConfigPath) {
    try {
        $projectConfig = Get-Content $projectConfigPath -Raw | ConvertFrom-Json
        $projectName = [string]$projectConfig.project_name
        $checks.Add((New-Check "project_name" ([bool]$projectName) $projectName))

        $iocPath = Resolve-ConfigPath ([string]$projectConfig.firmware.ioc_path) $workspaceRoot
        if ($iocPath) {
            $checks.Add((New-Check "firmware_ioc" (Test-Path $iocPath) $iocPath))
        }
        else {
            $checks.Add((New-Check "firmware_ioc" $false "firmware.ioc_path is not configured"))
        }

        $buildPath = Resolve-ConfigPath ([string]$projectConfig.build.project_path) $workspaceRoot
        if ($buildPath) {
            $checks.Add((New-Check "build_project_path" (Test-Path $buildPath) $buildPath))
        }
        else {
            $checks.Add((New-Check "build_project_path" $false "build.project_path is not configured"))
        }
    }
    catch {
        $checks.Add((New-Check "project_config_parse" $false $_.Exception.Message))
    }
}

$summary = [pscustomobject]@{
    workspace = $workspaceRoot
    ready = -not ($checks | Where-Object { -not $_.ok })
    checks = $checks
}

if ($Json) {
    $summary | ConvertTo-Json -Depth 8
}
else {
    Write-Host "STM32 agent readiness: $(if ($summary.ready) { 'ready' } else { 'not ready' })"
    foreach ($check in $checks) {
        $mark = if ($check.ok) { "OK " } else { "ERR" }
        Write-Host ("[{0}] {1} - {2}" -f $mark, $check.name, $check.detail)
    }
}

if ($Strict -and -not $summary.ready) {
    exit 1
}
