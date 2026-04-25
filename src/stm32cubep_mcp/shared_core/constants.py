from __future__ import annotations

from pathlib import Path

DEFAULT_CLI_PATH = (
    r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"
)
DEFAULT_CLI_CANDIDATES = {
    "windows": [DEFAULT_CLI_PATH],
    "linux": [
        "/opt/st/stm32cubeprogrammer/bin/STM32_Programmer_CLI",
        "/usr/local/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI",
    ],
    "darwin": [
        "/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/MacOs/bin/STM32_Programmer_CLI",
        "/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI",
    ],
}
DEFAULT_CLI_ENV_VAR = "STM32_PROGRAMMER_CLI_PATH"
LOCAL_TOOLS_CONFIG_ENV_VAR = "STM32_TOOLS_LOCAL_JSON"
PROJECT_METADATA_ENV_VAR = "STM32_PROJECT_JSON"
DEFAULT_GENERATED_ROOT = "generated"
DEFAULT_PROJECT_TOOLCHAIN = "STM32CubeIDE"
DEFAULT_BUILD_SYSTEM = "cubeide"
DEFAULT_BUILD_CONFIGURATION = "Debug"
LOCAL_TOOLS_CONFIG_PATHS = (
    "config/stm32-tools.local.json",
    "stm32-tools.local.json",
    ".vscode/stm32-tools.local.json",
    ".github/stm32-tools.local.json",
)
PROJECT_METADATA_PATHS = (
    "config/stm32-project.json",
    "stm32-project.json",
    ".vscode/stm32-project.json",
    ".github/stm32-project.json",
)
TOOLS_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "stm32-tools.local.schema.json"
PROJECT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "stm32-project.schema.json"
DEFAULT_LOGS_DIR = Path(__file__).resolve().parents[3] / "logs"
