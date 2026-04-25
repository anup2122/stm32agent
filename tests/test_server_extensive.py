from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from stm32cubep_mcp import server


class ResolveCliPathTests(unittest.TestCase):
    def test_uses_environment_override_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_cli = Path(temp_dir) / "STM32_Programmer_CLI.exe"
            fake_cli.write_text("stub", encoding="utf-8")

            with patch.dict(os.environ, {"STM32_PROGRAMMER_CLI_PATH": str(fake_cli)}):
                self.assertEqual(server.resolve_cli_path(), str(fake_cli))

    def test_raises_when_cli_is_missing(self) -> None:
        with patch(
            "stm32cubep_mcp.server.discover_cube_programmer",
            return_value={
                "resolved_path": None,
                "checked_candidates": [{"path": r"C:\missing\tool.exe", "exists": False, "source": "environment"}],
                "env_var": "STM32_PROGRAMMER_CLI_PATH",
                "path_hint": "STM32_Programmer_CLI.exe",
                "config_error": None,
            },
        ):
            with self.assertRaises(FileNotFoundError):
                server.resolve_cli_path()

    def test_uses_config_candidate_when_env_override_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_cli = Path(temp_dir) / "STM32_Programmer_CLI.exe"
            fake_cli.write_text("stub", encoding="utf-8")
            config_path = Path(temp_dir) / "stm32-tools.local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "tools": {
                            "cube_programmer": {
                                "candidates": {
                                    "windows": [str(fake_cli)],
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"STM32_TOOLS_LOCAL_JSON": str(config_path)}, clear=False):
                with patch("stm32cubep_mcp.server.shutil.which", return_value=None):
                    self.assertEqual(server.resolve_cli_path(), str(fake_cli))


class HelperFunctionTests(unittest.TestCase):
    def test_normalize_tokens_converts_all_values_to_strings(self) -> None:
        self.assertEqual(server.normalize_tokens(["--flag", 12, "abc"]), ["--flag", "12", "abc"])

    def test_create_log_path_uses_prefix_and_log_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                log_path = server.create_log_path("verify")

        self.assertEqual(log_path.parent.name, Path(temp_dir).name)
        self.assertTrue(log_path.name.startswith("verify_"))
        self.assertEqual(log_path.suffix, ".log")

    def test_connected_operation_messages_use_operation_name(self) -> None:
        success, failure = server.connected_operation_messages("read_memory")

        self.assertIn("read memory", success)
        self.assertIn("connection parameters", failure)

    def test_load_tools_local_config_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "stm32-tools.local.json"
            config_path.write_text("{not-json", encoding="utf-8")

            with patch.dict(os.environ, {"STM32_TOOLS_LOCAL_JSON": str(config_path)}, clear=False):
                result = server.load_tools_local_config()

        self.assertEqual(result["status"], "invalid")
        self.assertTrue(result["errors"])

    def test_load_project_metadata_reports_loaded_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "stm32-project.json"
            project_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "project_name": "demo",
                        "board": {"name": "NUCLEO-L476RG", "connect_defaults": {"port": "SWD"}},
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"STM32_PROJECT_JSON": str(project_path)}, clear=False):
                result = server.load_project_metadata()

        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["path"], str(project_path))

    def test_load_project_metadata_derives_runtime_paths_from_top_level_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir) / "stm32-project.json"
            project_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "_comment": "Top-level user inputs only.",
                        "project_name": "demo-app",
                        "generated_root": "generated",
                        "project_toolchain": "STM32CubeIDE",
                        "build_system": "cubeide",
                        "default_configuration": "Debug",
                        "board": {"name": "NUCLEO-L476RG", "connect_defaults": {"port": "SWD"}},
                        "firmware": {"format": "elf"},
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"STM32_PROJECT_JSON": str(project_path)}, clear=False):
                with patch("stm32cubep_mcp.shared.Path.cwd", return_value=Path(temp_dir)):
                    result = server.load_project_metadata()

        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["raw_data"]["project_name"], "demo-app")
        self.assertEqual(result["data"]["cubemx"]["project_name"], "demo-app")
        self.assertEqual(result["data"]["firmware"]["ioc_path"], "generated/demo-app/demo-app.ioc")
        self.assertTrue(result["data"]["build"]["project_path"].endswith("generated\\demo-app\\Projects\\STM32CubeIDE"))
        self.assertTrue(result["data"]["debug"]["elf_path"].endswith("generated\\demo-app\\Projects\\STM32CubeIDE\\Debug\\demo-app.elf"))

        def test_load_project_metadata_accepts_jsonc_comments(self) -> None:
                with tempfile.TemporaryDirectory() as temp_dir:
                        project_path = Path(temp_dir) / "stm32-project.json"
                        project_path.write_text(
                                """{
    // Top-level project identity.
    \"version\": 1,
    \"project_name\": \"demo-app\",
    \"generated_root\": \"generated\",
    \"board\": {
        \"name\": \"NUCLEO-L476RG\",
        /* Host defaults */
        \"connect_defaults\": {\"port\": \"SWD\"}
    }
}
""",
                                encoding="utf-8",
                        )

                        with patch.dict(os.environ, {"STM32_PROJECT_JSON": str(project_path)}, clear=False):
                                result = server.load_project_metadata()

                self.assertEqual(result["status"], "loaded")
                self.assertEqual(result["raw_data"]["project_name"], "demo-app")

        def test_load_tools_local_config_accepts_jsonc_comments(self) -> None:
                with tempfile.TemporaryDirectory() as temp_dir:
                        config_path = Path(temp_dir) / "stm32-tools.local.json"
                        config_path.write_text(
                                """{
    \"version\": 1,
    \"tools\": {
        // Machine-local override.
        \"cube_programmer\": {
            \"candidates\": {
                \"windows\": [\"C:/tool/STM32_Programmer_CLI.exe\"]
            }
        }
    }
}
""",
                                encoding="utf-8",
                        )

                        with patch.dict(os.environ, {"STM32_TOOLS_LOCAL_JSON": str(config_path)}, clear=False):
                                result = server.load_tools_local_config()

                self.assertEqual(result["status"], "loaded")
                self.assertEqual(result["data"]["tools"]["cube_programmer"]["candidates"]["windows"][0], "C:/tool/STM32_Programmer_CLI.exe")


class CommandArgumentBuilderTests(unittest.TestCase):
    def test_build_connect_arguments_includes_optional_flags(self) -> None:
        arguments = server.build_connect_arguments(
            port="SWD",
            serial_number="ABC123",
            enable_console=True,
            frequency_khz=2400,
            mode="HOTPLUG",
            reset="HWrst",
            low_power_mode="enable",
            get_auth_id=True,
        )

        self.assertEqual(
            arguments,
            [
                "--connect",
                "port=SWD",
                "sn=ABC123",
                "console",
                "freq=2400",
                "mode=HOTPLUG",
                "reset=HWrst",
                "LPM",
                "getAuthID",
            ],
        )

    def test_build_download_arguments_supports_incremental_fast_verify_and_skip_erase(self) -> None:
        arguments = server.build_download_arguments(
            "firmware.bin",
            "0x08000000",
            incremental=True,
            skip_erase=True,
            verify_mode="fast",
        )

        self.assertEqual(
            arguments,
            ["--skipErase", "--download", "firmware.bin", "0x08000000", "incremental", "--verify", "fast"],
        )

    def test_validate_download_inputs_accepts_existing_axf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "image.axf"
            firmware.write_text("stub", encoding="utf-8")

            result = server.validate_download_inputs(str(firmware))

        self.assertEqual(result, firmware)

    def test_validate_download_inputs_rejects_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            server.validate_download_inputs(r"C:\missing\image.axf")

    def test_validate_download_inputs_requires_address_for_bin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "image.bin"
            firmware.write_text("stub", encoding="utf-8")

            with self.assertRaises(ValueError):
                server.validate_download_inputs(str(firmware))

    def test_extract_target_families_from_text(self) -> None:
        families = server.extract_target_families_from_text("Board : NUCLEO-L476RG and firmware STM32F103RB")

        self.assertEqual(families, {"L476", "F103"})

    def test_extract_attached_target_families_from_output_ignores_firmware_filename_lines(self) -> None:
        output = "Board       : NUCLEO-L476RG\nOpening and parsing file: XNUCLEO-F103RB-binary.axf\nDevice name : STM32L4x1/STM32L475xx/STM32L476xx/STM32L486xx"

        families = server.extract_attached_target_families_from_output(output)

        self.assertEqual(families, {"L475", "L476", "L486"})

    def test_extract_target_families_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "XNUCLEO-F103RB-binary.axf"
            firmware.write_text("startup for STM32F103RB target", encoding="utf-8")

            families = server.extract_target_families_from_file(firmware)

        self.assertEqual(families, {"F103"})

    def test_build_post_download_arguments(self) -> None:
        self.assertEqual(server.build_post_download_arguments("none"), [])
        self.assertEqual(server.build_post_download_arguments("reset"), ["-rst"])
        self.assertEqual(server.build_post_download_arguments("hardware_reset"), ["-hardRst"])
        self.assertEqual(server.build_post_download_arguments("go"), ["--go"])

    def test_build_flash_arguments_creates_production_sequence(self) -> None:
        arguments = server.build_flash_arguments(
            "firmware.axf",
            sectors=["all"],
            verify_mode="fast",
            post_action="go",
        )

        self.assertEqual(
            arguments,
            ["--erase", "all", "--skipErase", "--download", "firmware.axf", "--verify", "fast", "--go"],
        )

    def test_build_erase_arguments_defaults_to_all(self) -> None:
        self.assertEqual(server.build_erase_arguments(), ["--erase", "all"])

    def test_build_erase_arguments_accepts_specific_sectors(self) -> None:
        self.assertEqual(server.build_erase_arguments(["0", "1", "2"]), ["--erase", "0", "1", "2"])

    def test_build_verify_arguments_handles_modes(self) -> None:
        self.assertEqual(server.build_verify_arguments("legacy"), ["--verify"])
        self.assertEqual(server.build_verify_arguments("fast"), ["--verify", "fast"])
        self.assertEqual(server.build_verify_arguments("none"), [])

    def test_build_reset_arguments_maps_all_supported_reset_kinds(self) -> None:
        self.assertEqual(server.build_reset_arguments("software"), ["-rst"])
        self.assertEqual(server.build_reset_arguments("hardware"), ["-hardRst"])
        self.assertEqual(server.build_reset_arguments("bootloader"), ["-rstbl"])

    def test_build_upload_arguments(self) -> None:
        self.assertEqual(server.build_upload_arguments("0x08000000", 256, "dump.bin"), ["--upload", "0x08000000", "256", "dump.bin"])

    def test_build_checksum_arguments(self) -> None:
        self.assertEqual(server.build_checksum_arguments(), ["--checksum"])
        self.assertEqual(server.build_checksum_arguments("0x08000000", 128), ["--checksum", "0x08000000", "128"])

    def test_build_read_memory_arguments(self) -> None:
        self.assertEqual(server.build_read_memory_arguments(32, "0x20000000", 4), ["-r32", "0x20000000", "4"])

    def test_build_write_memory_arguments_defaults_to_verify(self) -> None:
        self.assertEqual(server.build_write_memory_arguments(8, "0x20000000", [170, 85]), ["-w8", "0x20000000", "170", "85"])

    def test_build_go_arguments(self) -> None:
        self.assertEqual(server.build_go_arguments(), ["--go"])
        self.assertEqual(server.build_go_arguments("0x08001000"), ["--go", "0x08001000"])


class CommandExecutionTests(unittest.TestCase):
    @patch("stm32cubep_mcp.server.subprocess.run")
    def test_run_cli_command_returns_success_result(self, subprocess_run: object) -> None:
        subprocess_run.return_value = subprocess.CompletedProcess(
            args=["tool", "--version"],
            returncode=0,
            stdout="ok\n",
            stderr="",
        )

        result = server.run_cli_command(["tool", "--version"], 10)

        self.assertTrue(result["success"])
        self.assertEqual(result["stdout"], "ok")
        self.assertEqual(result["exit_code"], 0)

    @patch("stm32cubep_mcp.server.subprocess.run")
    def test_run_cli_command_returns_timeout_result(self, subprocess_run: object) -> None:
        subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd=["tool", "--version"],
            timeout=5,
            output="partial output",
            stderr="partial error",
        )

        result = server.run_cli_command(["tool", "--version"], 5)

        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], -1)
        self.assertIn("timed out", result["stderr"])
        self.assertEqual(result["stdout"], "partial output")

    @patch("stm32cubep_mcp.server.subprocess.run")
    def test_run_cli_command_returns_missing_executable_result(self, subprocess_run: object) -> None:
        subprocess_run.side_effect = FileNotFoundError("missing executable")

        result = server.run_cli_command(["missing-tool", "--version"], 5)

        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], -2)
        self.assertIn("missing executable", result["stderr"])


class LoggingTests(unittest.TestCase):
    def test_write_operation_log_writes_attempt_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "op.log"
            attempts = [
                {
                    "success": True,
                    "exit_code": 0,
                    "command": ["tool", "--version"],
                    "stdout": "done",
                    "stderr": "",
                    "connect_parameters": {"port": "SWD"},
                    "action_arguments": ["--version"],
                }
            ]

            server.write_operation_log(
                log_path,
                operation="programmer_version",
                attempts=attempts,
                selected_attempt=attempts[0],
            )

            contents = log_path.read_text(encoding="utf-8")

        self.assertIn("operation=programmer_version", contents)
        self.assertIn("command=tool --version", contents)
        self.assertIn("stdout:", contents)


class RetryExecutionTests(unittest.TestCase):
    @patch("stm32cubep_mcp.server.resolve_cli_path", return_value=r"C:\tool\STM32_Programmer_CLI.exe")
    @patch("stm32cubep_mcp.server.run_cli_command")
    def test_execute_with_retry_marks_used_defaults_false_when_overridden(self, run_cli_command: object, _resolve_cli_path: object) -> None:
        run_cli_command.return_value = {
            "success": True,
            "exit_code": 0,
            "command": ["tool", "--connect"],
            "stdout": "ok",
            "stderr": "",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                result = server.execute_with_retry(
                    operation="connect",
                    log_prefix="connect",
                    action_arguments=[],
                    success_message="ok",
                    failure_message="fail",
                    port="JTAG",
                )

        self.assertTrue(result["success"])
        self.assertFalse(result["used_defaults"])
        self.assertEqual(result["connect_parameters"]["port"], "JTAG")

    @patch("stm32cubep_mcp.server.resolve_cli_path", return_value=r"C:\tool\STM32_Programmer_CLI.exe")
    @patch("stm32cubep_mcp.server.run_cli_command")
    def test_execute_global_command_records_failure(self, run_cli_command: object, _resolve_cli_path: object) -> None:
        run_cli_command.return_value = {
            "success": False,
            "exit_code": 2,
            "command": ["tool", "--version"],
            "stdout": "",
            "stderr": "failed",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                result = server.execute_global_command(
                    operation="programmer_version",
                    log_prefix="version",
                    command_arguments=["--version"],
                    success_message="ok",
                    failure_message="fail",
                )

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "fail")
        self.assertEqual(result["action_arguments"], ["--version"])


class DiscoveryAndCapabilitiesTests(unittest.TestCase):
    def test_discover_cube_programmer_prefers_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_cli = Path(temp_dir) / "STM32_Programmer_CLI.exe"
            fake_cli.write_text("stub", encoding="utf-8")

            with patch.dict(os.environ, {"STM32_PROGRAMMER_CLI_PATH": str(fake_cli)}, clear=False):
                with patch("stm32cubep_mcp.server.shutil.which", return_value=None):
                    result = server.discover_cube_programmer()

        self.assertEqual(result["resolved_path"], str(fake_cli))
        self.assertEqual(result["resolution_source"], "environment")

    def test_discover_cube_programmer_uses_config_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_cli = Path(temp_dir) / "STM32_Programmer_CLI.exe"
            fake_cli.write_text("stub", encoding="utf-8")
            config_path = Path(temp_dir) / "stm32-tools.local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "tools": {
                            "cube_programmer": {
                                "env_var": "STM32_PROGRAMMER_CLI_PATH",
                                "candidates": {
                                    "windows": [str(fake_cli)],
                                },
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"STM32_TOOLS_LOCAL_JSON": str(config_path), "STM32_PROGRAMMER_CLI_PATH": ""},
                clear=False,
            ):
                with patch("stm32cubep_mcp.server.shutil.which", return_value=None):
                    result = server.discover_cube_programmer()

        self.assertEqual(result["resolved_path"], str(fake_cli))
        self.assertEqual(result["resolution_source"], "config")

    @patch("stm32cubep_mcp.server.collect_host_tool_discovery")
    @patch("stm32cubep_mcp.server.run_cli_command")
    def test_collect_host_capabilities_turns_off_device_flows_when_version_probe_fails(
        self,
        run_cli_command: object,
        collect_host_tool_discovery: object,
    ) -> None:
        collect_host_tool_discovery.return_value = {
            "host": {"platform": "windows", "workspace_root": "C:/workspace"},
            "schemas": {"stm32_tools_local": "tools.json", "stm32_project": "project.json"},
            "configurations": {
                "stm32_tools_local": {"status": "loaded", "path": "tools.json", "schema_path": "schema", "errors": [], "searched_paths": []},
                "stm32_project": {"status": "loaded", "path": "project.json", "schema_path": "schema", "errors": [], "searched_paths": []},
            },
            "tools": {
                "cube_programmer": {
                    "resolved_path": "C:/tool/STM32_Programmer_CLI.exe",
                    "checked_candidates": [],
                }
            },
        }
        run_cli_command.return_value = {
            "success": False,
            "exit_code": 1,
            "command": ["tool", "--version"],
            "stdout": "",
            "stderr": "failed",
        }

        result = server.collect_host_capabilities(timeout_seconds=3)

        self.assertFalse(result["tools"]["cube_programmer"]["runnable"])
        self.assertFalse(result["capabilities"]["device_connect"])
        self.assertFalse(result["capabilities"]["flash"])
        self.assertTrue(result["capabilities"]["project_metadata_loaded"])

    @patch("stm32cubep_mcp.server.collect_host_capabilities", return_value={"capabilities": {"flash": True}})
    def test_stm32_report_host_capabilities_routes_to_collector(self, collect_host_capabilities: object) -> None:
        result = server.stm32_report_host_capabilities(timeout_seconds=6)

        collect_host_capabilities.assert_called_once_with(timeout_seconds=6)
        self.assertTrue(result["capabilities"]["flash"])

    @patch("stm32cubep_mcp.server.collect_host_tool_discovery", return_value={"tools": {"cube_programmer": {}}})
    def test_stm32_discover_host_tools_routes_to_collector(self, collect_host_tool_discovery: object) -> None:
        result = server.stm32_discover_host_tools()

        collect_host_tool_discovery.assert_called_once_with()
        self.assertIn("tools", result)


class MismatchDetectionTests(unittest.TestCase):
    def test_detect_target_mismatch_reports_disjoint_families_when_runtime_halts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "XNUCLEO-F103RB-binary.axf"
            firmware.write_text("Built for STM32F103RB", encoding="utf-8")

            mismatch = server.detect_target_mismatch(
                firmware,
                {"success": True, "stdout": "Board       : NUCLEO-L476RG"},
                {"stdout": "Core is halted"},
            )

        self.assertIsNotNone(mismatch)
        self.assertEqual(mismatch["reason"], "this does not match to the attached target")
        self.assertEqual(mismatch["firmware_families"], ["F103"])
        self.assertEqual(mismatch["attached_families"], ["L476"])

    @patch("stm32cubep_mcp.server.execute_connected_operation")
    def test_apply_runtime_target_check_turns_success_into_mismatch_failure(self, execute_connected_operation: object) -> None:
        execute_connected_operation.return_value = {
            "success": True,
            "stdout": "Core is halted\nBoard       : NUCLEO-L476RG",
            "operation": "runtime_check",
            "log_file": "runtime.log",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "XNUCLEO-F103RB-binary.axf"
            firmware.write_text("Built for STM32F103RB", encoding="utf-8")
            result = {
                "success": True,
                "stdout": "Board       : NUCLEO-L476RG",
                "message": "ok",
            }

            checked = server.apply_runtime_target_check(
                result,
                firmware_path=firmware,
                post_action="go",
                timeout_seconds=30,
                connect_kwargs={"port": "SWD", "frequency_khz": 4000, "mode": "NORMAL", "reset": "SWrst"},
            )

        self.assertFalse(checked["success"])
        self.assertEqual(checked["message"], "this does not match to the attached target")
        self.assertIn("target_mismatch", checked)


class ToolWrapperTests(unittest.TestCase):
    @patch("stm32cubep_mcp.server.execute_connect", return_value={"success": True})
    def test_connect_to_attached_stm32_device_routes_to_execute_connect(self, execute_connect: object) -> None:
        result = asyncio.run(server.connect_to_attached_stm32_device(timeout_seconds=11))

        execute_connect.assert_called_once_with(timeout_seconds=11)
        self.assertTrue(result["success"])

    @patch("stm32cubep_mcp.server.execute_global_command", return_value={"success": True})
    def test_stm32_list_interfaces_builds_expected_global_command(self, execute_global_command: object) -> None:
        server.stm32_list_interfaces(interface="stlink-only", shared=True, timeout_seconds=7)

        execute_global_command.assert_called_once_with(
            operation="list_interfaces",
            log_prefix="list",
            command_arguments=["--list", "stlink-only", "shared"],
            timeout_seconds=7,
            success_message="Listed STM32 communication interfaces.",
            failure_message="Unable to list STM32 communication interfaces.",
        )

    @patch("stm32cubep_mcp.server.apply_runtime_target_check", return_value={"success": True})
    @patch("stm32cubep_mcp.server.execute_connected_operation", return_value={"success": True})
    def test_stm32_download_routes_to_connected_operation(
        self,
        execute_connected_operation: object,
        apply_runtime_target_check: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "firmware.bin"
            firmware.write_text("stub", encoding="utf-8")

            asyncio.run(
                server.stm32_download(
                    file_path=str(firmware),
                    address="0x08000000",
                    incremental=True,
                    skip_erase=True,
                    verify_mode="fast",
                    post_action="go",
                    timeout_seconds=99,
                )
            )

        execute_connected_operation.assert_called_once_with(
            operation="download",
            log_prefix="download",
            action_arguments=["--skipErase", "--download", str(firmware), "0x08000000", "incremental", "--verify", "fast", "--go"],
            timeout_seconds=99,
            port="SWD",
            frequency_khz=4000,
            mode="NORMAL",
            reset="SWrst",
        )
        apply_runtime_target_check.assert_called_once()

    @patch("stm32cubep_mcp.server.apply_runtime_target_check", return_value={"success": True})
    @patch("stm32cubep_mcp.server.execute_connected_operation", return_value={"success": True})
    def test_stm32_flash_firmware_routes_to_connected_operation(
        self,
        execute_connected_operation: object,
        apply_runtime_target_check: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "firmware.axf"
            firmware.write_text("stub", encoding="utf-8")

            asyncio.run(
                server.stm32_flash_firmware(
                    file_path=str(firmware),
                    verify_mode="legacy",
                    post_action="go",
                    timeout_seconds=123,
                )
            )

        execute_connected_operation.assert_called_once_with(
            operation="flash_firmware",
            log_prefix="flash",
            action_arguments=["--erase", "all", "--skipErase", "--download", str(firmware), "--verify", "--go"],
            timeout_seconds=123,
            port="SWD",
            frequency_khz=4000,
            mode="NORMAL",
            reset="SWrst",
        )
        apply_runtime_target_check.assert_called_once()

    @patch("stm32cubep_mcp.server.apply_runtime_target_check", return_value={"success": True})
    @patch("stm32cubep_mcp.server.execute_connected_operation", return_value={"success": True})
    def test_stm32_flash_firmware_applies_runtime_target_check(
        self,
        execute_connected_operation: object,
        apply_runtime_target_check: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "firmware.axf"
            firmware.write_text("stub", encoding="utf-8")

            asyncio.run(server.stm32_flash_firmware(file_path=str(firmware), post_action="go"))

        apply_runtime_target_check.assert_called_once()

    @patch("stm32cubep_mcp.server.execute_connected_operation", return_value={"success": True})
    def test_stm32_reset_uses_requested_reset_kind(self, execute_connected_operation: object) -> None:
        asyncio.run(server.stm32_reset(reset_kind="hardware", timeout_seconds=22))

        execute_connected_operation.assert_called_once_with(
            operation="reset",
            log_prefix="reset",
            action_arguments=["-hardRst"],
            timeout_seconds=22,
            port="SWD",
            frequency_khz=4000,
            mode="NORMAL",
            reset="SWrst",
        )

    @patch("stm32cubep_mcp.server.execute_connected_operation", return_value={"success": True})
    @patch("stm32cubep_mcp.server.execute_global_command", return_value={"success": True})
    def test_stm32_custom_command_switches_between_connected_and_global_modes(
        self,
        execute_global_command: object,
        execute_connected_operation: object,
    ) -> None:
        asyncio.run(server.stm32_custom_command(["--blankcheck"], include_connect=True, timeout_seconds=33))
        asyncio.run(server.stm32_custom_command(["--version"], include_connect=False, timeout_seconds=44))

        execute_connected_operation.assert_called_once_with(
            operation="custom_command",
            log_prefix="custom",
            action_arguments=["--blankcheck"],
            timeout_seconds=33,
            port="SWD",
            frequency_khz=4000,
            mode="NORMAL",
            reset="SWrst",
        )
        execute_global_command.assert_called_once_with(
            operation="custom_command",
            log_prefix="custom",
            command_arguments=["--version"],
            timeout_seconds=44,
            success_message="STM32 custom command completed successfully.",
            failure_message="STM32 custom command failed.",
        )


class LlmRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_recovery_suggestion_extracts_json(self) -> None:
        suggestion = server.parse_recovery_suggestion(
            "```json\n{\"summary\":\"retry with hotplug\",\"action\":\"retry_operation\",\"reason\":\"connect mode may be wrong\",\"connect_overrides\":{\"mode\":\"HOTPLUG\"}}\n```",
            server.RECOVERY_CONNECTED_ACTIONS,
        )

        self.assertEqual(suggestion["action"], "retry_operation")
        self.assertEqual(suggestion["connect_overrides"], {"mode": "HOTPLUG"})

    def test_parse_recovery_suggestion_rejects_unknown_action(self) -> None:
        with self.assertRaises(ValueError):
            server.parse_recovery_suggestion('{"action":"erase_everything"}', server.RECOVERY_CONNECTED_ACTIONS)

    @patch("stm32cubep_mcp.server.request_llm_recovery_step", new_callable=AsyncMock)
    async def test_maybe_run_llm_recovery_resolves_on_retry(self, request_llm_recovery_step: AsyncMock) -> None:
        request_llm_recovery_step.return_value = {
            "summary": "retry with lower speed",
            "action": "retry_operation",
            "reason": "signal quality may be marginal",
            "connect_overrides": {"frequency_khz": 1000, "mode": "HOTPLUG"},
            "parameters": {},
            "user_action": "",
        }

        initial_result = {
            "success": False,
            "message": "STM32 erase failed.",
            "stdout": "",
            "stderr": "Cannot connect to target",
            "operation": "erase",
        }
        retried_result = {
            "success": True,
            "message": "STM32 erase completed successfully.",
            "stdout": "done",
            "stderr": "",
            "operation": "erase",
        }

        result = await server.maybe_run_llm_recovery(
            initial_result,
            ctx=object(),
            operation="erase",
            recovery_kind="connected",
            action_arguments=["--erase", "all"],
            connect_kwargs={"port": "SWD", "frequency_khz": 4000, "mode": "NORMAL", "reset": "SWrst"},
            timeout_seconds=60,
            retry_operation=lambda updated_connect_kwargs: {**retried_result, "connect_parameters": updated_connect_kwargs},
            allowed_actions=server.RECOVERY_CONNECTED_ACTIONS,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["recovered"])
        self.assertEqual(result["llm_recovery"]["status"], "resolved")
        self.assertEqual(result["connect_parameters"]["frequency_khz"], 1000)

    @patch("stm32cubep_mcp.server.request_llm_recovery_step", new_callable=AsyncMock)
    async def test_maybe_run_llm_recovery_stops_and_asks_user(self, request_llm_recovery_step: AsyncMock) -> None:
        request_llm_recovery_step.return_value = {
            "summary": "manual intervention required",
            "action": "ask_user",
            "reason": "target power state must be fixed",
            "connect_overrides": {},
            "parameters": {},
            "user_action": "Check target power, boot mode, and cable orientation, then retry.",
        }

        initial_result = {
            "success": False,
            "message": "STM32 connect failed.",
            "stdout": "",
            "stderr": "No target found",
            "operation": "connect",
        }

        result = await server.maybe_run_llm_recovery(
            initial_result,
            ctx=object(),
            operation="connect",
            recovery_kind="connect",
            action_arguments=[],
            connect_kwargs={"port": "SWD", "frequency_khz": 4000, "mode": "NORMAL", "reset": "SWrst"},
            timeout_seconds=30,
            retry_operation=lambda updated_connect_kwargs: {**initial_result, "connect_parameters": updated_connect_kwargs},
            allowed_actions=server.RECOVERY_CONNECT_ACTIONS,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["llm_recovery"]["status"], "ask_user")
        self.assertIn("Check target power", result["message"])

    @patch("stm32cubep_mcp.server.request_llm_recovery_step", new_callable=AsyncMock)
    async def test_maybe_run_llm_recovery_handles_sampling_unavailable(self, request_llm_recovery_step: AsyncMock) -> None:
        request_llm_recovery_step.side_effect = RuntimeError("sampling unavailable")

        initial_result = {
            "success": False,
            "message": "STM32 go failed.",
            "stdout": "",
            "stderr": "device error",
            "operation": "go",
        }

        result = await server.maybe_run_llm_recovery(
            initial_result,
            ctx=object(),
            operation="go",
            recovery_kind="connected",
            action_arguments=["--go"],
            connect_kwargs={"port": "SWD", "frequency_khz": 4000, "mode": "NORMAL", "reset": "SWrst"},
            timeout_seconds=30,
            retry_operation=lambda updated_connect_kwargs: {**initial_result, "connect_parameters": updated_connect_kwargs},
            allowed_actions=server.RECOVERY_CONNECTED_ACTIONS,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["llm_recovery"]["status"], "sampling_unavailable")
        self.assertIn("Automatic LLM-guided recovery is unavailable", result["message"])


if __name__ == "__main__":
    unittest.main()