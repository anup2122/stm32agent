"""Legacy compatibility module.

The STM32CubeProgrammer MCP server now lives in ``stm32cubep_mcp.cube_programmer.server``.
This module is intentionally no longer an MCP server entrypoint and no longer re-exports
the programmer tool surface.
"""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "stm32cubep_mcp.server is no longer an MCP server entrypoint. "
        "Use stm32cubep_mcp.cube_programmer.server instead."
    )


if __name__ == "__main__":
    main()