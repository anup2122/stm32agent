# STM32 Toolchain Config

This directory holds the shared STM32 Agent Toolchain configuration files.

- `stm32-tools.local.json`: machine-local tool paths and host-specific discovery hints
- `stm32-project.json`: project metadata consumed by the orchestration and domain servers

The orchestration server owns these configuration files. Tool-domain servers read them but should not define their own private copies.