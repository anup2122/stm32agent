from __future__ import annotations

import platform


def host_platform_name() -> str:
    system_name = platform.system().lower()
    if system_name.startswith("win"):
        return "windows"
    if system_name.startswith("linux"):
        return "linux"
    if system_name.startswith("darwin"):
        return "darwin"
    return system_name or "unknown"


def default_cli_executable_name() -> str:
    return "STM32_Programmer_CLI.exe" if host_platform_name() == "windows" else "STM32_Programmer_CLI"
