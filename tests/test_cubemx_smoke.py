from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

from stm32cubep_mcp.cubemx import server


class CubeMxSmokeTests(unittest.TestCase):
    def sample_project_descriptor(self) -> str:
        return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<projectDescription>
    <name>UART_TwoBoards_ComPolling</name>
    <linkedResources>
        <link>
            <name>Application/User/Core/main.c</name>
            <type>1</type>
            <locationURI>PARENT-1-PROJECT_LOC/Core/Src/main.c</locationURI>
        </link>
        <link>
            <name>Application/User/Core/stm32l4xx_hal_msp.c</name>
            <type>1</type>
            <locationURI>PARENT-1-PROJECT_LOC/Core/Src/stm32l4xx_hal_msp.c</locationURI>
        </link>
        <link>
            <name>Application/User/Core/stm32l4xx_it.c</name>
            <type>1</type>
            <locationURI>PARENT-1-PROJECT_LOC/Core/Src/stm32l4xx_it.c</locationURI>
        </link>
    </linkedResources>
</projectDescription>
"""

    def sample_tools_config(self, tool_path: str) -> dict[str, object]:
        return {
            "data": {
                "tools": {
                    "cubemx": {
                        "env_var": "STM32CUBEMX_PATH",
                        "executable_name": "STM32CubeMX.exe",
                        "candidates": {
                            "windows": [tool_path],
                        },
                    },
                    "cubeide": {
                        "env_var": "STM32CUBEIDE_CLI_PATH",
                        "executable_name": "stm32cubeidec.exe",
                        "candidates": {
                            "windows": [str(Path(tool_path).with_name("stm32cubeidec.exe"))],
                        },
                    },
                }
            }
        }

    def sample_project_metadata(self, ioc_path: str, workspace: str, project_path: str) -> dict[str, object]:
        cubemx_project_path = str(Path(project_path).parent)
        return {
            "data": {
                "firmware": {
                    "ioc_path": ioc_path,
                },
                "cubemx": {
                    "project_name": "UART_TwoBoards_ComPolling",
                    "project_toolchain": "STM32CubeIDE",
                    "project_path": cubemx_project_path,
                    "script_path": str(Path(cubemx_project_path) / "script.txt"),
                },
                "build": {
                    "system": "cubeide",
                    "workspace": workspace,
                    "project_path": project_path,
                    "project_name": "UART_TwoBoards_ComPolling",
                    "artifact": str(Path(project_path) / "Release" / "UART_TwoBoards_ComPolling.elf"),
                },
            }
        }

    def sample_ioc_text(self) -> str:
        return """#MicroXplorer Configuration settings - do not modify
File.Version=6
MxCube.Version=6.10.0
Mcu.Name=STM32L476RGTx
Mcu.Package=LQFP64
ProjectManager.ProjectFileName=UART_TwoBoards_ComPolling.ioc
ProjectManager.ToolChain=STM32CubeIDE
ProjectManager.TargetToolchain=STM32CubeIDE
IP0=GPIO
IP1=USART1
PA9.Signal=USART1_TX
PA10.Signal=USART1_RX
PA5.Signal=GPIO_Output
PA5.GPIO_Label=LED_STATUS
"""

    def sample_ioc_text_with_toolchain_location(self, location: str) -> str:
        return self.sample_ioc_text() + f"ProjectManager.ToolChainLocation={location}\n"

    def test_stm32_cubemx_capabilities_reports_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "STM32CubeMX.exe"
            tool_path.write_text("stub", encoding="utf-8")
            ioc_path = Path(temp_dir) / "board.ioc"
            ioc_path.write_text(self.sample_ioc_text(), encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                with patch("stm32cubep_mcp.cubemx.server.shared.load_project_metadata", return_value=self.sample_project_metadata(str(ioc_path), temp_dir, temp_dir)):
                    with patch("stm32cubep_mcp.cubemx.server.shared.host_platform_name", return_value="windows"):
                        result = server.stm32_cubemx_capabilities()

        self.assertTrue(result["implemented"])
        self.assertEqual(result["tool_discovery"]["resolved_path"], str(tool_path))
        self.assertEqual(result["ioc_discovery"]["resolved_path"], str(ioc_path.resolve()))

    def test_stm32_cubemx_parse_ioc_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "board.ioc"
            ioc_path.write_text(self.sample_ioc_text(), encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.shared.load_project_metadata", return_value=self.sample_project_metadata(str(ioc_path), temp_dir, temp_dir)):
                result = server.stm32_cubemx_parse_ioc()

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["mcu"]["name"], "STM32L476RGTx")
        self.assertIn("USART1", result["summary"]["peripherals"])
        self.assertEqual(result["summary"]["counts"]["pins"], 3)

    def test_resolve_cubemx_project_inputs_uses_toolchain_location_for_completion_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "board-project"
            project_root.mkdir()
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text(self.sample_ioc_text_with_toolchain_location("Projects\\"), encoding="utf-8")

            result = server.resolve_cubemx_project_inputs(
                ioc_path=str(ioc_path),
                project_name="board",
                project_toolchain="STM32CubeIDE",
                project_path=str(project_root),
            )

        self.assertEqual(
            result["completion_marker"],
            str((project_root / "Projects" / "STM32CubeIDE" / ".project").resolve()),
        )
        self.assertEqual(
            result["completion_markers"],
            [
                str((project_root / "Projects" / "STM32CubeIDE" / ".project").resolve()),
                str((project_root / "Projects" / "STM32CubeIDE" / ".cproject").resolve()),
                str((project_root / "board" / "Projects" / "STM32CubeIDE" / ".project").resolve()),
                str((project_root / "board" / "Projects" / "STM32CubeIDE" / ".cproject").resolve()),
            ],
        )

    def test_stm32_cubemx_regenerate_project_runs_and_validates_build(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "STM32CubeMX.exe"
            tool_path.write_text("stub", encoding="utf-8")
            workspace_path = Path(temp_dir) / "workspace"
            workspace_path.mkdir()
            source_project_path = Path(temp_dir) / "source-project"
            source_project_path.mkdir()
            ioc_path = source_project_path / "board.ioc"
            ioc_path.write_text(self.sample_ioc_text(), encoding="utf-8")
            output_root = Path(temp_dir) / "generated-project"
            (output_root / "STM32CubeIDE").mkdir(parents=True)
            project_path = output_root / "STM32CubeIDE"
            (output_root / ".mxproject").write_text(
                "\n".join([
                    "[PreviousGenFiles]",
                    "AdvancedFolderStructure=true",
                    "HeaderPath#0=..\\Core\\Inc",
                    "SourcePath#0=..\\Core\\Src",
                    "",
                ]),
                encoding="utf-8",
            )
            (output_root / "STM32CubeIDE" / ".project").write_text(self.sample_project_descriptor(), encoding="utf-8")
            (output_root / "STM32CubeIDE" / ".cproject").write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<cproject>
    <option valueType=\"includePath\">
        <listOptionValue builtIn=\"false\" value=\"../../Core/Inc\"/>
    </option>
</cproject>
""",
                encoding="utf-8",
            )

            def fake_run_cubemx_command(
                command: list[str],
                timeout_seconds: int,
                progress_callback: object | None = None,
                completion_markers: object | None = None,
                completion_tree_root: object | None = None,
            ) -> dict[str, object]:
                script_path = Path(command[-1])
                script_contents = script_path.read_text(encoding="utf-8")
                self.assertIn(f'config load "{ioc_path}"', script_contents)
                self.assertIn('project name "UART_TwoBoards_ComPolling"', script_contents)
                self.assertIn('project toolchain "STM32CubeIDE"', script_contents)
                self.assertIn(f'project path "{output_root}"', script_contents)
                self.assertIn("project generate", script_contents)
                self.assertIn("exit_mx", script_contents)
                (output_root / "Inc").mkdir(parents=True)
                (output_root / "Src").mkdir(parents=True)
                (output_root / "Inc" / "main.h").write_text("#pragma once\n", encoding="utf-8")
                (output_root / "Inc" / "gpio.h").write_text("#pragma once\n", encoding="utf-8")
                (output_root / "Inc" / "usart.h").write_text("#pragma once\n", encoding="utf-8")
                (output_root / "Src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
                (output_root / "Src" / "gpio.c").write_text("void MX_GPIO_Init(void) {}\n", encoding="utf-8")
                (output_root / "Src" / "usart.c").write_text("void MX_USART2_UART_Init(void) {}\n", encoding="utf-8")
                (output_root / "Src" / "stm32l4xx_hal_msp.c").write_text("void HAL_UART_MspInit(void) {}\n", encoding="utf-8")
                (output_root / "Src" / "stm32l4xx_it.c").write_text("void SysTick_Handler(void) {}\n", encoding="utf-8")
                (output_root / "STM32CubeIDE" / ".project").write_text(self.sample_project_descriptor() + "\n", encoding="utf-8")
                return {
                    "success": True,
                    "exit_code": 0,
                    "command": command,
                    "stdout": "Code generation done",
                    "stderr": "",
                }

            with patch("stm32cubep_mcp.cubemx.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                with patch("stm32cubep_mcp.cubemx.server.shared.load_project_metadata", return_value=self.sample_project_metadata(str(ioc_path), str(workspace_path), str(project_path))):
                    with patch("stm32cubep_mcp.cubemx.server.shared.host_platform_name", return_value="windows"):
                        with patch("stm32cubep_mcp.cubemx.server.run_cubemx_command", side_effect=fake_run_cubemx_command):
                            with patch("stm32cubep_mcp.cubemx.server.build_server.stm32_build_project", return_value={"success": True, "message": "build ok"}):
                                result = server.stm32_cubemx_regenerate_project(output_root=str(output_root), validate_build=True)

            project_tree = ET.parse(output_root / "STM32CubeIDE" / ".project")
            linked_resources = project_tree.getroot().find("linkedResources")
            linked_names = [element.findtext("name") for element in linked_resources.findall("link")]
            direct_main_header_exists = (output_root / "Inc" / "main.h").is_file()
            direct_main_source_exists = (output_root / "Src" / "main.c").is_file()

        self.assertTrue(result["success"])
        self.assertEqual(result["launch_kind"], "executable")
        self.assertEqual(result["script_path"], str(output_root / "script.txt"))
        self.assertTrue(result["completion_wait"]["success"])
        self.assertTrue(result["output_review"]["direct_output"]["include_dir_exists"])
        self.assertTrue(result["output_review"]["direct_output"]["source_dir_exists"])
        self.assertIn("Inc/", result["output_review"]["top_level_entries"])
        self.assertIn("Src/", result["output_review"]["top_level_entries"])
        self.assertTrue(result["output_review"]["mismatches"])
        self.assertTrue(result["build_validation"]["success"])
        self.assertNotIn("Application/User/Core/gpio.c", linked_names)
        self.assertNotIn("Application/User/Core/usart.c", linked_names)
        self.assertTrue(direct_main_header_exists)
        self.assertTrue(direct_main_source_exists)

    def test_stm32_cubemx_regenerate_project_accepts_tree_change_when_marker_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "STM32CubeMX.exe"
            tool_path.write_text("stub", encoding="utf-8")
            workspace_path = Path(temp_dir) / "workspace"
            workspace_path.mkdir()
            source_project_path = Path(temp_dir) / "source-project"
            source_project_path.mkdir()
            ioc_path = source_project_path / "board.ioc"
            ioc_path.write_text(self.sample_ioc_text(), encoding="utf-8")
            output_root = Path(temp_dir) / "generated-project"
            (output_root / "STM32CubeIDE").mkdir(parents=True)
            project_path = output_root / "STM32CubeIDE"
            project_marker = output_root / "STM32CubeIDE" / ".project"
            project_marker.write_text(self.sample_project_descriptor(), encoding="utf-8")

            def fake_run_cubemx_command(
                command: list[str],
                timeout_seconds: int,
                progress_callback: object | None = None,
                completion_markers: object | None = None,
                completion_tree_root: object | None = None,
            ) -> dict[str, object]:
                (output_root / "Core" / "Src").mkdir(parents=True, exist_ok=True)
                (output_root / "Core" / "Src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
                return {
                    "success": True,
                    "exit_code": 0,
                    "command": command,
                    "stdout": "Code generation done",
                    "stderr": "",
                }

            with patch("stm32cubep_mcp.cubemx.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                with patch("stm32cubep_mcp.cubemx.server.shared.load_project_metadata", return_value=self.sample_project_metadata(str(ioc_path), str(workspace_path), str(project_path))):
                    with patch("stm32cubep_mcp.cubemx.server.shared.host_platform_name", return_value="windows"):
                        with patch("stm32cubep_mcp.cubemx.server.run_cubemx_command", side_effect=fake_run_cubemx_command):
                            with patch("stm32cubep_mcp.cubemx.server.wait_for_completion_marker", return_value={
                                "success": False,
                                "marker_path": str(project_marker),
                                "status": "timeout",
                                "message": "CubeMX did not create or update the completion marker.",
                            }):
                                result = server.stm32_cubemx_regenerate_project(output_root=str(output_root), validate_build=False)

        self.assertTrue(result["success"])
        self.assertEqual(result["completion_wait"]["status"], "tree_changed")
        self.assertIn(str(output_root / "Core" / "Src" / "main.c"), result["completion_wait"]["affected_files"]["new_files"])

    def test_run_cubemx_command_marks_ko_output_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "STM32CubeMX.exe"
            tool_path.write_text("stub", encoding="utf-8")

            class FakeProcess:
                def poll(self) -> int:
                    return 0

                def communicate(self) -> tuple[str, str]:
                    return ("KO\nThe version of the current IOC is too high.", "")

                def kill(self) -> None:
                    return None

            with patch("stm32cubep_mcp.cubemx.server.subprocess.Popen", return_value=FakeProcess()):
                result = server.run_cubemx_command([str(tool_path), "-q", "script.txt"], timeout_seconds=10)

        self.assertFalse(result["success"])
        self.assertIn("newer STM32CubeMX version", str(result["failure_reason"]))

    def test_run_cubemx_command_ignores_intermediate_project_path_ko_when_generate_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "STM32CubeMX.exe"
            tool_path.write_text("stub", encoding="utf-8")

            class FakeProcess:
                def poll(self) -> int:
                    return 0

                def communicate(self) -> tuple[str, str]:
                    return ("\n".join([
                        'OK',
                        'project name "board"',
                        'OK',
                        'project toolchain "STM32CubeIDE"',
                        'OK',
                        'project path "C:\\work\\board"',
                        'KO',
                        'project generate',
                        'Generated code: C:\\work\\board\\Core\\Src\\main.c',
                        'OK',
                        'exit_mx',
                    ]), "")

                def kill(self) -> None:
                    return None

            with patch("stm32cubep_mcp.cubemx.server.subprocess.Popen", return_value=FakeProcess()):
                result = server.run_cubemx_command([str(tool_path), "-q", "script.txt"], timeout_seconds=10)

        self.assertTrue(result["success"])
        self.assertIsNone(result["failure_reason"])

    def test_run_cubemx_command_reports_progress_while_process_runs(self) -> None:
        progress_callback = Mock()

        class FakeProcess:
            def __init__(self) -> None:
                self.poll_count = 0

            def poll(self) -> int | None:
                self.poll_count += 1
                return None if self.poll_count == 1 else 0

            def communicate(self) -> tuple[str, str]:
                return ("Code generation done", "")

            def kill(self) -> None:
                return None

        with patch("stm32cubep_mcp.cubemx.server.subprocess.Popen", return_value=FakeProcess()):
            with patch("stm32cubep_mcp.cubemx.server.time.sleep", return_value=None):
                result = server.run_cubemx_command(["STM32CubeMX.exe", "-q", "script.txt"], timeout_seconds=10, progress_callback=progress_callback)

        self.assertTrue(result["success"])
        progress_callback.assert_called()

    def test_run_cubemx_command_streams_cubemx_log_updates(self) -> None:
        progress_callback = Mock()

        class FakeProcess:
            def __init__(self) -> None:
                self.poll_count = 0

            def poll(self) -> int | None:
                self.poll_count += 1
                return None if self.poll_count == 1 else 0

            def communicate(self) -> tuple[str, str]:
                return ("Code generation done", "")

            def kill(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as temp_dir:
            cubemx_log_path = Path(temp_dir) / "STM32CubeMX.log"
            cubemx_log_path.write_text("existing\n", encoding="utf-8")

            def append_log(_: float) -> None:
                cubemx_log_path.write_text("existing\nnew log line\n", encoding="utf-8")

            metadata = {
                "data": {
                    "cubemx": {
                        "log_path": str(cubemx_log_path),
                    }
                }
            }

            with patch("stm32cubep_mcp.cubemx.server.shared.load_project_metadata", return_value=metadata):
                with patch("stm32cubep_mcp.cubemx.server.subprocess.Popen", return_value=FakeProcess()):
                    with patch("stm32cubep_mcp.cubemx.server.time.sleep", side_effect=append_log):
                        result = server.run_cubemx_command(["STM32CubeMX.exe", "-q", "script.txt"], timeout_seconds=10, progress_callback=progress_callback)

        self.assertTrue(result["success"])
        log_calls = [call.kwargs if call.kwargs else call.args[0] for call in progress_callback.call_args_list]
        log_event = next(event for event in log_calls if event.get("stage") == "cubemx_log")
        self.assertEqual(log_event["log_path"], str(cubemx_log_path.resolve()))
        self.assertIn("new log line", log_event["content"])

    def test_run_cubemx_command_completes_when_marker_appears_before_process_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "generated-project"
            marker_path = project_root / "board" / "Projects" / "STM32CubeIDE" / ".project"
            kill_calls: list[str] = []

            class FakeProcess:
                def poll(self) -> int | None:
                    return None

                def communicate(self) -> tuple[str, str]:
                    return ("", "")

                def kill(self) -> None:
                    kill_calls.append("kill")

                @property
                def pid(self) -> int:
                    return 1234

            def write_marker(_: float) -> None:
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text("ok", encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.subprocess.Popen", return_value=FakeProcess()):
                with patch("stm32cubep_mcp.cubemx.server.subprocess.run") as taskkill:
                    with patch("stm32cubep_mcp.cubemx.server.time.sleep", side_effect=write_marker):
                        with patch("stm32cubep_mcp.cubemx.server.shared.host_platform_name", return_value="windows"):
                            result = server.run_cubemx_command(
                                ["STM32CubeMX.exe", "-q", "script.txt"],
                                timeout_seconds=10,
                                completion_markers=[marker_path],
                                completion_tree_root=project_root,
                            )

        self.assertTrue(result["success"])
        self.assertTrue(result["completed_via_marker"])
        self.assertEqual(result["completion_marker"]["status"], "created")
        self.assertEqual(result["completion_marker"]["marker_path"], str(marker_path.resolve()))
        taskkill.assert_called_once()
        
    def test_run_cubemx_command_does_not_complete_early_on_tree_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "generated-project"
            marker_path = project_root / "board" / "Projects" / "STM32CubeIDE" / ".project"
            tree_file = project_root / "Core" / "Src" / "main.c"
            kill_calls: list[str] = []

            class FakeProcess:
                def __init__(self) -> None:
                    self.poll_count = 0

                def poll(self) -> int | None:
                    self.poll_count += 1
                    return None if self.poll_count < 3 else 0

                def communicate(self) -> tuple[str, str]:
                    return ("Code generation done", "")

                def kill(self) -> None:
                    kill_calls.append("kill")

            def mutate_tree(_: float) -> None:
                tree_file.parent.mkdir(parents=True, exist_ok=True)
                tree_file.write_text("int main(void) { return 0; }\n", encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.subprocess.Popen", return_value=FakeProcess()):
                with patch("stm32cubep_mcp.cubemx.server.time.sleep", side_effect=mutate_tree):
                    result = server.run_cubemx_command(
                        ["STM32CubeMX.exe", "-q", "script.txt"],
                        timeout_seconds=10,
                        completion_markers=[marker_path],
                        completion_tree_root=project_root,
                    )

        self.assertTrue(result["success"])
        self.assertNotIn("completed_via_marker", result)
        self.assertEqual(kill_calls, [])

    def test_wait_for_completion_marker_reports_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            marker_path = Path(temp_dir) / "STM32CubeIDE" / ".project"
            marker_path.parent.mkdir(parents=True)
            progress_callback = Mock()

            def write_marker(_: float) -> None:
                marker_path.write_text("ok", encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.time.sleep", side_effect=write_marker):
                result = server.wait_for_completion_marker(
                    marker_path,
                    timeout_seconds=5,
                    initial_exists=False,
                    initial_mtime=None,
                    poll_interval_seconds=0.01,
                    progress_callback=progress_callback,
                )

        self.assertTrue(result["success"])
        progress_callback.assert_called()

    def test_wait_for_completion_marker_accepts_tree_change_before_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tree_root = Path(temp_dir) / "generated-project"
            marker_path = tree_root / "STM32CubeIDE" / ".project"
            marker_path.parent.mkdir(parents=True)
            marker_path.write_text("existing", encoding="utf-8")
            initial_mtime = marker_path.stat().st_mtime
            initial_tree_state = server.collect_tree_state(tree_root)

            def create_generated_file(_: float) -> None:
                (tree_root / "Core" / "Src").mkdir(parents=True, exist_ok=True)
                (tree_root / "Core" / "Src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.time.sleep", side_effect=create_generated_file):
                result = server.wait_for_completion_marker(
                    marker_path,
                    timeout_seconds=5,
                    initial_exists=True,
                    initial_mtime=initial_mtime,
                    tree_root=tree_root,
                    initial_tree_state=initial_tree_state,
                    poll_interval_seconds=0.01,
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "tree_changed")
        self.assertIn(str(tree_root / "Core" / "Src" / "main.c"), result["affected_files"]["new_files"])

    def test_wait_for_completion_marker_rejects_tree_change_before_marker_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tree_root = Path(temp_dir) / "generated-project"
            tree_root.mkdir(parents=True)
            marker_path = tree_root / "Projects" / "STM32CubeIDE" / ".project"
            initial_tree_state = server.collect_tree_state(tree_root)

            def create_generated_file(_: float) -> None:
                (tree_root / "Core" / "Src").mkdir(parents=True, exist_ok=True)
                (tree_root / "Core" / "Src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.time.sleep", side_effect=create_generated_file):
                result = server.wait_for_completion_marker(
                    marker_path,
                    timeout_seconds=0,
                    initial_exists=False,
                    initial_mtime=None,
                    tree_root=tree_root,
                    initial_tree_state=initial_tree_state,
                    poll_interval_seconds=0.01,
                )

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "timeout")

    def test_wait_for_completion_markers_accepts_alternate_marker_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tree_root = Path(temp_dir) / "generated-project"
            tree_root.mkdir(parents=True)
            primary_marker = tree_root / "Projects" / "STM32CubeIDE" / ".project"
            alternate_marker = tree_root / "STM32CubeIDE" / ".project"

            def create_alternate_marker(_: float) -> None:
                alternate_marker.parent.mkdir(parents=True, exist_ok=True)
                alternate_marker.write_text("project", encoding="utf-8")

            with patch("stm32cubep_mcp.cubemx.server.time.sleep", side_effect=create_alternate_marker):
                result = server.wait_for_completion_markers(
                    [primary_marker, alternate_marker],
                    timeout_seconds=5,
                    initial_states={primary_marker.resolve(): (False, None), alternate_marker.resolve(): (False, None)},
                    tree_root=tree_root,
                    initial_tree_state=server.collect_tree_state(tree_root),
                    poll_interval_seconds=0.01,
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["marker_path"], str(alternate_marker.resolve()))

    def test_build_cubemx_script_includes_output_root(self) -> None:
        ioc_path = Path("C:/work/project/board.ioc")
        project_path = Path("C:/external/generated")

        script = server.build_cubemx_script(ioc_path, "board", "STM32CubeIDE", project_path)

        self.assertIn(f'config load "{ioc_path}"', script)
        self.assertIn('project name "board"', script)
        self.assertIn('project toolchain "STM32CubeIDE"', script)
        self.assertIn('project path "C:\\external\\generated"', script)
        self.assertIn("project generate", script)
        self.assertIn("exit_mx", script)

    def test_resolve_generation_root_prefers_explicit_output_root(self) -> None:
        ioc_path = Path("C:/work/project/board.ioc")

        result = server.resolve_generation_root(ioc_path, "C:/external/generated")

        self.assertEqual(result, Path("C:/external/generated").resolve())

    def test_wait_for_completion_marker_reports_created_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            marker_path = Path(temp_dir) / "STM32CubeIDE" / ".project"
            marker_path.parent.mkdir(parents=True)
            marker_path.write_text("project", encoding="utf-8")

            result = server.wait_for_completion_marker(
                marker_path,
                timeout_seconds=1,
                initial_exists=False,
                initial_mtime=None,
                poll_interval_seconds=0.01,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "created")

    def test_collect_output_review_reports_mismatch_against_core_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            project_root.mkdir()
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text(self.sample_ioc_text(), encoding="utf-8")
            (project_root / ".mxproject").write_text(
                "\n".join([
                    "[PreviousGenFiles]",
                    "AdvancedFolderStructure=true",
                    "HeaderPath#0=..\\Core\\Inc",
                    "SourcePath#0=..\\Core\\Src",
                    "",
                ]),
                encoding="utf-8",
            )
            output_root = Path(temp_dir) / "generated"
            (output_root / "Inc").mkdir(parents=True)
            (output_root / "Src").mkdir(parents=True)
            (output_root / "STM32CubeIDE").mkdir()
            (output_root / "STM32CubeIDE" / ".project").write_text(self.sample_project_descriptor(), encoding="utf-8")
            (output_root / "STM32CubeIDE" / ".cproject").write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<cproject>
    <option valueType=\"includePath\">
        <listOptionValue builtIn=\"false\" value=\"../../Core/Inc\"/>
    </option>
</cproject>
""",
                encoding="utf-8",
            )

            result = server.collect_output_review(ioc_path, output_root)

        self.assertIn("Inc/", result["top_level_entries"])
        self.assertIn("Src/", result["top_level_entries"])
        self.assertTrue(result["mismatches"])


if __name__ == "__main__":
    unittest.main()
