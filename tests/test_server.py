from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from stm32cubep_mcp import server


class BuildConnectCommandTests(unittest.TestCase):
    @patch("stm32cubep_mcp.server.resolve_cli_path", return_value=r"C:\tool\STM32_Programmer_CLI.exe")
    def test_builds_expected_swd_command(self, _resolve_cli_path: object) -> None:
        command = server.build_connect_command(
            port="SWD",
            frequency_khz=4000,
            mode="NORMAL",
            reset="SWrst",
            probe_index=1,
            serial_number="ABC123",
            shared_mode=True,
        )

        self.assertEqual(
            command,
            [
                r"C:\tool\STM32_Programmer_CLI.exe",
                "--connect",
                "port=SWD",
                "sn=ABC123",
                "freq=4000",
                "index=1",
                "mode=NORMAL",
                "reset=SWrst",
                "shared",
            ],
        )


class CommandBuilderTests(unittest.TestCase):
    def test_build_download_arguments_defaults_to_verify(self) -> None:
        arguments = server.build_download_arguments("firmware.bin", "0x08000000")

        self.assertEqual(arguments, ["--download", "firmware.bin", "0x08000000", "--verify"])

    def test_build_write_memory_arguments_can_disable_verify(self) -> None:
        arguments = server.build_write_memory_arguments(16, "0x20000000", [1, 2, 3], verify=False)

        self.assertEqual(arguments, ["-w16", "0x20000000", "1", "2", "3", "--noverify"])


class FallbackAttemptTests(unittest.TestCase):
    def test_builds_default_fallback_sequence(self) -> None:
        attempts = server.build_fallback_attempts({})

        self.assertEqual(
            attempts,
            [
                {"port": "SWD", "frequency_khz": 4000, "mode": "NORMAL", "reset": "SWrst"},
                {"port": "SWD", "frequency_khz": 4000, "mode": "HOTPLUG", "reset": "SWrst"},
                {"port": "SWD", "frequency_khz": 4000, "mode": "UR", "reset": "HWrst"},
                {"port": "SWD", "frequency_khz": 1000, "mode": "NORMAL", "reset": "HWrst"},
                {"port": "SWD", "frequency_khz": 1000, "mode": "HOTPLUG", "reset": "HWrst"},
            ],
        )

    def test_user_parameters_override_fallback_defaults(self) -> None:
        attempts = server.build_fallback_attempts({"port": "JTAG", "frequency_khz": 9000})

        self.assertEqual(attempts[0]["port"], "JTAG")
        self.assertEqual(attempts[0]["frequency_khz"], 9000)


class ExecuteConnectTests(unittest.TestCase):
    @patch("stm32cubep_mcp.server.build_connect_command")
    @patch("stm32cubep_mcp.server.subprocess.run")
    def test_returns_first_successful_attempt(self, subprocess_run: object, build_connect_command: object) -> None:
        build_connect_command.side_effect = lambda **kwargs: ["tool", "--connect", f"mode={kwargs['mode']}"]
        subprocess_run.side_effect = [
            subprocess.CompletedProcess(args=["tool"], returncode=1, stdout="", stderr="first failed\n"),
            subprocess.CompletedProcess(args=["tool"], returncode=0, stdout="connected\n", stderr=""),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                result = server.execute_connect(timeout_seconds=15)
                self.assertTrue(Path(result["log_file"]).is_file())

        self.assertTrue(result["success"])
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "connected")
        self.assertEqual(len(result["attempts"]), 2)

    @patch("stm32cubep_mcp.server.build_connect_command")
    @patch("stm32cubep_mcp.server.subprocess.run")
    def test_returns_failure_message_after_all_attempts_fail(self, subprocess_run: object, build_connect_command: object) -> None:
        build_connect_command.side_effect = lambda **kwargs: ["tool", "--connect", f"mode={kwargs['mode']}"]
        subprocess_run.side_effect = [
            subprocess.CompletedProcess(args=["tool"], returncode=1, stdout="", stderr="failed\n"),
            subprocess.CompletedProcess(args=["tool"], returncode=1, stdout="", stderr="failed\n"),
            subprocess.CompletedProcess(args=["tool"], returncode=1, stdout="", stderr="failed\n"),
            subprocess.CompletedProcess(args=["tool"], returncode=1, stdout="", stderr="failed\n"),
            subprocess.CompletedProcess(args=["tool"], returncode=1, stdout="", stderr="failed\n"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                result = server.execute_connect(timeout_seconds=15)
                self.assertTrue(Path(result["log_file"]).is_file())

        self.assertFalse(result["success"])
        self.assertIn("Ask the user for the correct connection parameters", result["message"])
        self.assertEqual(len(result["attempts"]), 5)


class ExecuteGlobalCommandTests(unittest.TestCase):
    @patch("stm32cubep_mcp.server.subprocess.run")
    @patch("stm32cubep_mcp.server.resolve_cli_path", return_value=r"C:\tool\STM32_Programmer_CLI.exe")
    def test_returns_version_result(self, _resolve_cli_path: object, subprocess_run: object) -> None:
        subprocess_run.return_value = subprocess.CompletedProcess(
            args=["tool", "--version"],
            returncode=0,
            stdout="v2.21.0\n",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                result = server.execute_global_command(
                    operation="programmer_version",
                    log_prefix="version",
                    command_arguments=["--version"],
                    success_message="ok",
                    failure_message="fail",
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["stdout"], "v2.21.0")
        self.assertEqual(result["action_arguments"], ["--version"])


class ExecuteConnectedOperationTests(unittest.TestCase):
    @patch("stm32cubep_mcp.server.resolve_cli_path", return_value=r"C:\tool\STM32_Programmer_CLI.exe")
    @patch("stm32cubep_mcp.server.subprocess.run")
    def test_combines_connect_and_action_arguments(self, subprocess_run: object, _resolve_cli_path: object) -> None:
        subprocess_run.return_value = subprocess.CompletedProcess(
            args=["tool"],
            returncode=0,
            stdout="done\n",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                result = server.execute_connected_operation(
                    operation="download",
                    log_prefix="download",
                    action_arguments=server.build_download_arguments("firmware.bin"),
                )

        self.assertTrue(result["success"])
        self.assertIn("--connect", result["command"])
        self.assertIn("--download", result["command"])


if __name__ == "__main__":
    unittest.main()
