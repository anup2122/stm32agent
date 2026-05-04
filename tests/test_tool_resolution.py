from __future__ import annotations

import unittest
from pathlib import Path

from stm32cubep_mcp.tools import cube_programmer_adapter, stlink_gdb_adapter, tool_resolution


class ToolResolutionCacheTests(unittest.TestCase):
    def tearDown(self) -> None:
        tool_resolution.clear_resolution_cache()

    def test_cached_resolution_invokes_resolver_once_per_key(self) -> None:
        calls: list[str] = []

        def resolver() -> dict[str, object]:
            calls.append("hit")
            return {"resolved_path": r"C:\tool\STM32_Programmer_CLI.exe"}

        first = tool_resolution.cached_resolution("cube_programmer", ("same",), resolver)
        second = tool_resolution.cached_resolution("cube_programmer", ("same",), resolver)

        self.assertEqual(calls, ["hit"])
        self.assertIs(first, second)

    def test_clear_resolution_cache_scopes_by_tool_name(self) -> None:
        tool_resolution.cached_resolution("cube_programmer", ("k1",), lambda: {"tool": "programmer"})
        tool_resolution.cached_resolution("arm_gdb", ("k1",), lambda: {"tool": "gdb"})

        tool_resolution.clear_resolution_cache("cube_programmer")

        programmer_calls: list[str] = []
        arm_calls: list[str] = []
        tool_resolution.cached_resolution("cube_programmer", ("k1",), lambda: programmer_calls.append("x") or {"tool": "programmer"})
        tool_resolution.cached_resolution("arm_gdb", ("k1",), lambda: arm_calls.append("x") or {"tool": "gdb"})

        self.assertEqual(programmer_calls, ["x"])
        self.assertEqual(arm_calls, [])


class CubeProgrammerAdapterBuilderTests(unittest.TestCase):
    def test_build_flash_arguments_composes_expected_sequence(self) -> None:
        arguments = cube_programmer_adapter.build_flash_arguments(
            "firmware.bin",
            "0x08000000",
            sectors=["bank_1"],
            incremental=True,
            verify_mode="fast",
            post_action="reset",
        )

        self.assertEqual(
            arguments,
            [
                "--erase",
                "bank_1",
                "--skipErase",
                "--download",
                "firmware.bin",
                "0x08000000",
                "incremental",
                "--verify",
                "fast",
                "-rst",
            ],
        )

    def test_build_write_memory_arguments_stringifies_tokens(self) -> None:
        arguments = cube_programmer_adapter.build_write_memory_arguments(8, "0x20000000", [1, 16, 255], verify=False)

        self.assertEqual(arguments, ["-w8", "0x20000000", "1", "16", "255", "--noverify"])


class StlinkAdapterBuilderTests(unittest.TestCase):
    def test_build_list_debuggers_command_includes_cube_programmer_hint(self) -> None:
        command = stlink_gdb_adapter.build_list_debuggers_command(
            r"C:\tool\ST-LINK_gdbserver.exe",
            cube_programmer_path=r"C:\tool\STM32CubeProgrammer\bin",
        )

        self.assertEqual(
            command,
            [
                r"C:\tool\ST-LINK_gdbserver.exe",
                "-cp",
                r"C:\tool\STM32CubeProgrammer\bin",
                "-q",
            ],
        )

    def test_build_stlink_gdb_server_command_can_include_incremental_flag(self) -> None:
        command = stlink_gdb_adapter.build_stlink_gdb_server_command(
            r"C:\tool\ST-LINK_gdbserver.exe",
            port_number=61234,
            persistent=True,
            server_log_path=Path(r"C:\logs\stlink.log"),
            incremental=True,
        )

        self.assertIn("--incremental", command)

    def test_launch_stlink_gdb_server_process_uses_windows_creationflags(self) -> None:
        captured: dict[str, object] = {}

        class FakePopen:
            pass

        class FakeSubprocessModule:
            CREATE_NO_WINDOW = 128
            STDOUT = object()

            @staticmethod
            def Popen(command: list[str], **kwargs: object) -> FakePopen:
                captured["command"] = command
                captured.update(kwargs)
                return FakePopen()

        output_handle = object()
        process = stlink_gdb_adapter.launch_stlink_gdb_server_process(
            ["tool", "-p", "61234"],
            output_handle=output_handle,
            working_directory=r"C:\workspace",
            host_platform="windows",
            subprocess_module=FakeSubprocessModule,
        )

        self.assertIsInstance(process, FakePopen)
        self.assertEqual(captured["command"], ["tool", "-p", "61234"])
        self.assertEqual(captured["stdout"], output_handle)
        self.assertEqual(captured["stderr"], FakeSubprocessModule.STDOUT)
        self.assertEqual(captured["cwd"], r"C:\workspace")
        self.assertEqual(captured["creationflags"], 128)