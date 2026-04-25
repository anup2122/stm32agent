from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stm32cubep_mcp.build import server


class CubeIdeBuildSmokeTests(unittest.TestCase):
    def sample_project_metadata(self, workspace: str, project_path: str) -> dict[str, object]:
        return {
            "data": {
                "build": {
                    "system": "cubeide",
                    "workspace": workspace,
                    "project_path": project_path,
                    "project_name": "CORTEXM_SysTick",
                    "default_configuration": "Release",
                    "configurations": ["Release", "Debug"],
                    "import_project": True,
                    "reset_workspace_on_import": True,
                    "default_clean": True,
                    "artifact": str(Path(project_path) / "Release" / "CORTEXM_SysTick.elf"),
                    "command": [
                        "stm32cubeidec",
                        "--launcher.suppressErrors",
                        "-nosplash",
                        "-consolelog",
                        "-application",
                        "org.eclipse.cdt.managedbuilder.core.headlessbuild",
                    ],
                }
            }
        }

    def sample_tools_config(self, tool_path: str) -> dict[str, object]:
        return {
            "data": {
                "tools": {
                    "cubeide": {
                        "env_var": "STM32CUBEIDE_CLI_PATH",
                        "executable_name": "stm32cubeidec.exe",
                        "candidates": {
                            "windows": [tool_path],
                        },
                    }
                }
            }
        }

    def test_resolve_cubeide_path_uses_tools_config_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "stm32cubeidec.exe"
            tool_path.write_text("stub", encoding="utf-8")

            with patch("stm32cubep_mcp.build.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                with patch("stm32cubep_mcp.build.server.shared.host_platform_name", return_value="windows"):
                    self.assertEqual(server.resolve_cubeide_path(), str(tool_path))

    def test_build_commands_match_cubeide_headless_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_path = Path(temp_dir) / "project"
            workspace.mkdir()
            project_path.mkdir()

            with patch(
                "stm32cubep_mcp.build.server.shared.load_project_metadata",
                return_value=self.sample_project_metadata(str(workspace), str(project_path)),
            ):
                import_command = server.build_import_command(r"C:\ST\STM32CubeIDE_1.14.1\STM32CubeIDE\stm32cubeidec.exe")
                build_command = server.build_clean_build_command(
                    r"C:\ST\STM32CubeIDE_1.14.1\STM32CubeIDE\stm32cubeidec.exe",
                    "Release",
                    True,
                )

        self.assertIn("-import", import_command)
        self.assertIn(str(project_path.resolve()), import_command)
        self.assertIn("-cleanBuild", build_command)
        self.assertIn("CORTEXM_SysTick/Release", build_command)

    def test_build_project_path_falls_back_to_ioc_toolchain_location_when_configured_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_root = Path(temp_dir) / "sample-project"
            configured_project_path = project_root / "STM32CubeIDE"
            alternate_project_path = project_root / "Projects" / "STM32CubeIDE"
            ioc_path = project_root / "sample.ioc"
            workspace.mkdir()
            project_root.mkdir()
            alternate_project_path.mkdir(parents=True)
            ioc_path.write_text("ProjectManager.ToolChainLocation=Projects\n", encoding="utf-8")

            metadata = self.sample_project_metadata(str(workspace), str(configured_project_path))
            metadata["data"]["firmware"] = {"ioc_path": str(ioc_path)}
            metadata["data"]["cubemx"] = {"project_path": str(project_root)}

            with patch("stm32cubep_mcp.build.server.shared.load_project_metadata", return_value=metadata):
                self.assertEqual(server.build_project_path(), alternate_project_path.resolve())

    def test_build_project_path_prefers_existing_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_root = Path(temp_dir) / "sample-project"
            configured_project_path = project_root / "STM32CubeIDE"
            alternate_project_path = project_root / "Projects" / "STM32CubeIDE"
            ioc_path = project_root / "sample.ioc"
            workspace.mkdir()
            configured_project_path.mkdir(parents=True)
            alternate_project_path.mkdir(parents=True)
            ioc_path.write_text("ProjectManager.ToolChainLocation=Projects\n", encoding="utf-8")

            metadata = self.sample_project_metadata(str(workspace), str(configured_project_path))
            metadata["data"]["firmware"] = {"ioc_path": str(ioc_path)}

            with patch("stm32cubep_mcp.build.server.shared.load_project_metadata", return_value=metadata):
                self.assertEqual(server.build_project_path(), configured_project_path.resolve())

    def test_build_project_path_rewrites_stale_nested_configured_path_to_toolchain_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            cubemx_project_root = Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf"
            configured_project_path = cubemx_project_root / "NUCLEO-L476RG-UART2-printf" / "STM32CubeIDE"
            ioc_path = Path(temp_dir) / "source-project" / "sample.ioc"
            workspace.mkdir(parents=True)
            ioc_path.parent.mkdir(parents=True)
            ioc_path.write_text("ProjectManager.ToolChainLocation=Projects\n", encoding="utf-8")

            metadata = self.sample_project_metadata(str(workspace), str(configured_project_path))
            metadata["data"]["build"]["project_name"] = "NUCLEO-L476RG-UART2-printf"
            metadata["data"]["firmware"] = {"ioc_path": str(ioc_path)}
            metadata["data"]["cubemx"] = {
                "project_path": str(cubemx_project_root),
                "project_name": "NUCLEO-L476RG-UART2-printf",
            }

            with patch("stm32cubep_mcp.build.server.shared.load_project_metadata", return_value=metadata):
                self.assertEqual(server.build_project_path(), (cubemx_project_root / "Projects" / "STM32CubeIDE").resolve())

    def test_stm32_build_project_writes_log_and_returns_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_path = Path(temp_dir) / "project"
            tool_path = Path(temp_dir) / "stm32cubeidec.exe"
            workspace.mkdir()
            project_path.mkdir()
            tool_path.write_text("stub", encoding="utf-8")

            metadata = self.sample_project_metadata(str(workspace), str(project_path))
            tools_config = self.sample_tools_config(str(tool_path))
            command_results = [
                {
                    "success": True,
                    "exit_code": 0,
                    "command": [str(tool_path), "-import"],
                    "stdout": "imported",
                    "stderr": "",
                },
                {
                    "success": True,
                    "exit_code": 0,
                    "command": [str(tool_path), "-cleanBuild", "CORTEXM_SysTick/Release"],
                    "stdout": "build ok",
                    "stderr": "",
                },
            ]

            with patch("stm32cubep_mcp.build.server.shared.load_project_metadata", return_value=metadata):
                with patch("stm32cubep_mcp.build.server.shared.load_tools_local_config", return_value=tools_config):
                    with patch("stm32cubep_mcp.build.server.shared.host_platform_name", return_value="windows"):
                        with patch("stm32cubep_mcp.build.server.run_build_command", side_effect=command_results):
                            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                                result = server.stm32_build_project(target="Release", timeout_seconds=120)
                                self.assertTrue(result["success"])
                                self.assertTrue(Path(str(result["log_file"])).is_file())
                                contents = Path(str(result["log_file"])).read_text(encoding="utf-8")
                                self.assertIn("configuration=Release", contents)
                                self.assertIn("build_step:", contents)
                                self.assertEqual(result["build_result"]["stdout"], "build ok")

    def test_stm32_build_project_continues_when_import_reports_existing_workspace_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_path = Path(temp_dir) / "project"
            tool_path = Path(temp_dir) / "stm32cubeidec.exe"
            workspace.mkdir()
            project_path.mkdir()
            tool_path.write_text("stub", encoding="utf-8")

            metadata = self.sample_project_metadata(str(workspace), str(project_path))
            tools_config = self.sample_tools_config(str(tool_path))
            command_results = [
                {
                    "success": False,
                    "exit_code": 1,
                    "command": [str(tool_path), "-import"],
                    "stdout": "",
                    "stderr": "Project: CORTEXM_SysTick already exists in the workspace!",
                },
                {
                    "success": True,
                    "exit_code": 0,
                    "command": [str(tool_path), "-cleanBuild", "CORTEXM_SysTick/Release"],
                    "stdout": "build ok",
                    "stderr": "",
                },
            ]

            with patch("stm32cubep_mcp.build.server.shared.load_project_metadata", return_value=metadata):
                with patch("stm32cubep_mcp.build.server.shared.load_tools_local_config", return_value=tools_config):
                    with patch("stm32cubep_mcp.build.server.shared.host_platform_name", return_value="windows"):
                        with patch("stm32cubep_mcp.build.server.run_build_command", side_effect=command_results):
                            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                                result = server.stm32_build_project(target="Release", timeout_seconds=120)

            self.assertTrue(result["success"])
            self.assertEqual(result["import_result"]["exit_code"], 1)
            self.assertEqual(result["build_result"]["stdout"], "build ok")

    def test_stm32_build_project_resets_workspace_before_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_path = Path(temp_dir) / "project"
            tool_path = Path(temp_dir) / "stm32cubeidec.exe"
            stale_file = workspace / ".metadata" / "stale.txt"
            workspace.mkdir(parents=True)
            stale_file.parent.mkdir(parents=True)
            stale_file.write_text("stale", encoding="utf-8")
            project_path.mkdir()
            tool_path.write_text("stub", encoding="utf-8")

            metadata = self.sample_project_metadata(str(workspace), str(project_path))
            tools_config = self.sample_tools_config(str(tool_path))
            command_results = [
                {
                    "success": True,
                    "exit_code": 0,
                    "command": [str(tool_path), "-import"],
                    "stdout": "imported",
                    "stderr": "",
                },
                {
                    "success": True,
                    "exit_code": 0,
                    "command": [str(tool_path), "-cleanBuild", "CORTEXM_SysTick/Release"],
                    "stdout": "build ok",
                    "stderr": "",
                },
            ]

            with patch("stm32cubep_mcp.build.server.shared.load_project_metadata", return_value=metadata):
                with patch("stm32cubep_mcp.build.server.shared.load_tools_local_config", return_value=tools_config):
                    with patch("stm32cubep_mcp.build.server.shared.host_platform_name", return_value="windows"):
                        with patch("stm32cubep_mcp.build.server.run_build_command", side_effect=command_results):
                            result = server.stm32_build_project(target="Release", timeout_seconds=120)

            self.assertTrue(result["success"])
            self.assertFalse(stale_file.exists())

    def test_cubeide_build_succeeded_rejects_skipped_build_output(self) -> None:
        self.assertFalse(
            server.cubeide_build_succeeded(
                {
                    "success": True,
                    "stderr": 'Project: NUCLEO-L476RG-UART2-printf doesn\'t appear to be a CDT project. Skipping...\nWARNING: No Config matched "NUCLEO-L476RG-UART2-printf/Debug". Skipping...',
                }
            )
        )

    def test_stm32_build_capabilities_reports_tool_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            project_path = Path(temp_dir) / "project"
            tool_path = Path(temp_dir) / "stm32cubeidec.exe"
            workspace.mkdir()
            project_path.mkdir()
            tool_path.write_text("stub", encoding="utf-8")

            metadata = self.sample_project_metadata(str(workspace), str(project_path))
            tools_config = self.sample_tools_config(str(tool_path))

            with patch("stm32cubep_mcp.build.server.shared.load_project_metadata", return_value=metadata):
                with patch("stm32cubep_mcp.build.server.shared.load_tools_local_config", return_value=tools_config):
                    with patch("stm32cubep_mcp.build.server.shared.host_platform_name", return_value="windows"):
                        with patch("stm32cubep_mcp.build.server.shared.summarize_config_status", side_effect=lambda value: {"status": "loaded" if value else "missing"}):
                            result = server.stm32_build_capabilities()

        self.assertTrue(result["implemented"])
        self.assertEqual(result["tool_path"], str(tool_path))


if __name__ == "__main__":
    unittest.main()