$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$distDir = Join-Path $workspaceRoot "dist"
$archivePath = Join-Path $distDir "stm32cubep-mcp-0.6.0-project.zip"

New-Item -ItemType Directory -Path $distDir -Force | Out-Null

if (Test-Path $archivePath) {
    Remove-Item $archivePath -Force
}

$pathsToArchive = @(
    (Join-Path $workspaceRoot "config"),
    (Join-Path $workspaceRoot ".vscode"),
    (Join-Path $workspaceRoot "scripts"),
    (Join-Path $workspaceRoot "src"),
    (Join-Path $workspaceRoot "tests"),
    (Join-Path $workspaceRoot "pyproject.toml"),
    (Join-Path $workspaceRoot "QUICKSTART.md"),
    (Join-Path $workspaceRoot "CHANGELOG.md"),
    (Join-Path $workspaceRoot "README.md"),
    (Join-Path $workspaceRoot "readme.txt"),
    (Join-Path $workspaceRoot ".gitignore"),
    (Join-Path $workspaceRoot "UART_ReceptionToIdle_CircularDMA.axf"),
    (Join-Path $workspaceRoot "XNUCLEO-F103RB-binary.axf"),
    (Join-Path $workspaceRoot "um2237-stm32cubeprogrammer-software-description-stmicroelectronics.pdf")
)

Compress-Archive -Path $pathsToArchive -DestinationPath $archivePath -CompressionLevel Optimal

Write-Host "Created archive: $archivePath"