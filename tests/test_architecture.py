from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from stm32cubep_mcp.build import server as build_server
from stm32cubep_mcp.cubemx import server as cubemx_server
from stm32cubep_mcp.orchestrator import server as orchestrator_server


class BuildServerStructureTests(unittest.TestCase):
    @patch("stm32cubep_mcp.build.server.shared.load_project_metadata")
    def test_detect_build_backend_uses_project_metadata(self, load_project_metadata: object) -> None:
        load_project_metadata.return_value = {
            "data": {
                "build": {
                    "system": "cubeide",
                }
            }
        }

        self.assertEqual(build_server.detect_build_backend(), "cubeide")


class CubeMxStructureTests(unittest.TestCase):
    @patch("stm32cubep_mcp.cubemx.server.shared.load_project_metadata")
    def test_cubemx_capabilities_reads_project_config(self, load_project_metadata: object) -> None:
        load_project_metadata.return_value = {
            "data": {
                "firmware": {
                    "ioc_path": "board.ioc",
                }
            }
        }

        result = cubemx_server.stm32_cubemx_capabilities()

        self.assertEqual(result["server"], "cubemx")
        self.assertTrue(result["capabilities"]["ioc_parse"])


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def test_merge_project_metadata_with_prompt_fallback_prefers_config_and_fills_missing_fields(self) -> None:
        contract = {
            "target": {"board_id": "NUCLEO-L476RG"},
            "defaults": {"toolchain": "STM32CubeIDE"},
            "core_features": [{"id": "core-uart-device-to-pc"}],
            "pluggable_features": [],
        }
        project_config = {
            "status": "loaded",
            "path": "config/stm32-project.json",
            "data": {
                "version": 1,
                "firmware": {},
                "cubemx": {},
                "build": {},
                "debug": {},
            },
        }

        merged, autofilled_fields = orchestrator_server.merge_project_metadata_with_prompt_fallback(project_config, contract)

        self.assertEqual(merged["project_name"], "NUCLEO-L476RG-UART2-printf")
        self.assertEqual(merged["generated_root"], "generated")
        self.assertEqual(merged["project_toolchain"], "STM32CubeIDE")
        self.assertEqual(merged["build_system"], "cubeide")
        self.assertEqual(merged["default_configuration"], "Debug")
        self.assertEqual(merged["firmware"], {})
        self.assertEqual(merged["cubemx"], {})
        self.assertEqual(merged["build"], {})
        self.assertEqual(merged["debug"], {})
        self.assertIn("project_name", autofilled_fields)
        self.assertIn("generated_root", autofilled_fields)
        self.assertIn("project_toolchain", autofilled_fields)

    def test_ensure_project_metadata_for_feature_contract_writes_missing_fields(self) -> None:
        contract = {
            "target": {"board_id": "NUCLEO-L476RG"},
            "defaults": {"toolchain": "STM32CubeIDE"},
            "core_features": [{"id": "core-uart-device-to-pc"}],
            "pluggable_features": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_path = Path(temp_dir) / "config" / "stm32-project.json"

            def fake_load_project_metadata() -> dict[str, object]:
                if metadata_path.is_file():
                    return {
                        "status": "loaded",
                        "path": str(metadata_path),
                        "data": json.loads(metadata_path.read_text(encoding="utf-8")),
                    }
                return {
                    "status": "not_found",
                    "path": str(metadata_path),
                    "data": None,
                }

            with patch("stm32cubep_mcp.orchestrator.server.shared.load_project_metadata", side_effect=fake_load_project_metadata):
                result = orchestrator_server.ensure_project_metadata_for_feature_contract(contract)

            persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertTrue(result["autofilled_fields"])
            self.assertEqual(persisted["project_name"], "NUCLEO-L476RG-UART2-printf")
            self.assertEqual(persisted["generated_root"], "generated")
            self.assertEqual(persisted["project_toolchain"], "STM32CubeIDE")
            self.assertEqual(persisted["build_system"], "cubeide")
            self.assertEqual(persisted["default_configuration"], "Debug")

    def test_normalize_project_config_rewrites_verbose_fields_to_jsonc(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_path = Path(temp_dir) / "config" / "stm32-project.json"
            metadata_path.parent.mkdir(parents=True)
            metadata_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "project_name": "NUCLEO-L476RG-UART2-printf",
                        "generated_root": "generated",
                        "project_toolchain": "STM32CubeIDE",
                        "build_system": "cubeide",
                        "default_configuration": "Debug",
                        "board": {"name": "NUCLEO-L476RG", "connect_defaults": {"port": "SWD"}},
                        "firmware": {
                            "format": "elf",
                            "ioc_path": "generated/NUCLEO-L476RG-UART2-printf/NUCLEO-L476RG-UART2-printf.ioc",
                            "default_artifact": str((Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf" / "Projects" / "STM32CubeIDE" / "Debug" / "NUCLEO-L476RG-UART2-printf.elf").resolve()),
                        },
                        "cubemx": {
                            "project_name": "NUCLEO-L476RG-UART2-printf",
                            "project_toolchain": "STM32CubeIDE",
                            "project_path": str((Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf").resolve()),
                            "script_path": str((Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf" / "script.txt").resolve()),
                        },
                        "build": {
                            "system": "cubeide",
                            "workspace": str((Path(temp_dir) / "generated" / ".cubeide-workspace").resolve()),
                            "project_path": str((Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf" / "Projects" / "STM32CubeIDE").resolve()),
                            "project_name": "NUCLEO-L476RG-UART2-printf",
                            "default_configuration": "Debug",
                            "configurations": ["Debug"],
                            "artifact": str((Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf" / "Projects" / "STM32CubeIDE" / "Debug" / "NUCLEO-L476RG-UART2-printf.elf").resolve()),
                            "import_project": True,
                        },
                        "debug": {
                            "server": "stlink-gdb-server",
                            "gdb_port": 55001,
                            "swo_port": 55002,
                            "elf_path": str((Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf" / "Projects" / "STM32CubeIDE" / "Debug" / "NUCLEO-L476RG-UART2-printf.elf").resolve()),
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("stm32cubep_mcp.orchestrator.server.shared.load_project_metadata", return_value={
                "status": "loaded",
                "path": str(metadata_path),
                "raw_data": json.loads(metadata_path.read_text(encoding="utf-8")),
                "data": json.loads(metadata_path.read_text(encoding="utf-8")),
            }):
                result = orchestrator_server.stm32_normalize_project_config()

            normalized_text = metadata_path.read_text(encoding="utf-8")
            self.assertTrue(result["success"])
            self.assertTrue(result["changed"])
            self.assertIn("// Actual STM32 project name.", normalized_text)
            self.assertIn('"project_name": "NUCLEO-L476RG-UART2-printf"', normalized_text)
            self.assertNotIn('"ioc_path"', normalized_text)
            self.assertNotIn('"project_path"', normalized_text)
            self.assertIn('"import_project": true', normalized_text)

    def test_apply_uart_device_to_pc_firmware_patch_injects_transmit_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "generated-project"
            source_dir = project_root / "Src"
            source_dir.mkdir(parents=True)
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text("stub", encoding="utf-8")
            main_source = source_dir / "main.c"
            main_source.write_text(
                """#include \"main.h\"\n\n/* USER CODE BEGIN Includes */\n\n/* USER CODE END Includes */\n\n/* USER CODE BEGIN PV */\n\n/* USER CODE END PV */\n\nint main(void)\n{\n  /* USER CODE BEGIN 2 */\n\n  /* USER CODE END 2 */\n\n  /* USER CODE BEGIN WHILE */\n  while (1)\n  {\n    /* USER CODE END WHILE */\n\n    /* USER CODE BEGIN 3 */\n  }\n  /* USER CODE END 3 */\n}\n""",
                encoding="utf-8",
            )

            result = orchestrator_server.apply_uart_device_to_pc_firmware_patch(str(ioc_path))

            patched = main_source.read_text(encoding="utf-8")
            self.assertTrue(result["success"])
            self.assertIn("#include <string.h>", patched)
            self.assertIn("STM32CubeP USART2 telemetry ready", patched)
            self.assertIn("HAL_UART_Transmit(&huart2", patched)
            self.assertIn("HAL_Delay(1000);", patched)
            self.assertIn(
                "while (1)\n  {\n    /* USER CODE END WHILE */\n\n    HAL_UART_Transmit(&huart2, (uint8_t *)uart_message, strlen(uart_message), HAL_MAX_DELAY);\n    HAL_Delay(1000);\n    /* USER CODE BEGIN 3 */\n  }\n  /* USER CODE END 3 */",
                patched,
            )

    def test_classify_prompt_routes_known_domains(self) -> None:
        self.assertEqual(orchestrator_server.classify_prompt("build the project"), "build")
        self.assertEqual(orchestrator_server.classify_prompt("build and flash the current project"), "build_flash")
        self.assertEqual(orchestrator_server.classify_prompt("take a debug snapshot"), "debug")
        self.assertEqual(orchestrator_server.classify_prompt("parse the .ioc file"), "cubemx")
        self.assertEqual(orchestrator_server.classify_prompt("flash this firmware"), "cube_programmer")
        self.assertEqual(orchestrator_server.classify_prompt("Create a NUCLEO-L476RG project that will send data to PC"), "requirements")

    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_debug_session", new_callable=AsyncMock)
    async def test_orchestrate_prompt_routes_debug_requests(self, stm32_orchestrate_debug_session: AsyncMock) -> None:
        stm32_orchestrate_debug_session.return_value = {"server": "orchestrator", "success": True}

        result = await orchestrator_server.stm32_orchestrate_prompt("start a debug session for runtime diagnosis", timeout_seconds=45)

        stm32_orchestrate_debug_session.assert_awaited_once_with(timeout_seconds=45)
        self.assertEqual(result["selected_domain"], "debug")

    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_debug_question", new_callable=AsyncMock)
    async def test_orchestrate_prompt_routes_debug_questions(self, stm32_orchestrate_debug_question: AsyncMock) -> None:
        stm32_orchestrate_debug_question.return_value = {"server": "orchestrator", "success": True}

        result = await orchestrator_server.stm32_orchestrate_prompt("what is baudrate set in uart1", timeout_seconds=45)

        stm32_orchestrate_debug_question.assert_awaited_once_with(prompt="what is baudrate set in uart1", timeout_seconds=45)
        self.assertEqual(result["selected_domain"], "debug")

    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_build_then_flash", new_callable=AsyncMock)
    async def test_orchestrate_prompt_routes_combined_requests(self, stm32_orchestrate_build_then_flash: AsyncMock) -> None:
        stm32_orchestrate_build_then_flash.return_value = {"server": "orchestrator", "success": True}

        result = await orchestrator_server.stm32_orchestrate_prompt("build and flash the current project", timeout_seconds=45)

        stm32_orchestrate_build_then_flash.assert_awaited_once_with(file_path=None, build_timeout_seconds=45, flash_timeout_seconds=45)
        self.assertEqual(result["selected_domain"], "build_flash")

    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_feature_prompt", new_callable=AsyncMock)
    async def test_orchestrate_prompt_routes_feature_requests(self, stm32_orchestrate_feature_prompt: AsyncMock) -> None:
        stm32_orchestrate_feature_prompt.return_value = {"server": "orchestrator", "success": True}

        result = await orchestrator_server.stm32_orchestrate_prompt(
            "Create a NUCLEO-L476RG project that will send data to PC and flash it",
            timeout_seconds=45,
        )

        stm32_orchestrate_feature_prompt.assert_awaited_once_with(
            prompt="Create a NUCLEO-L476RG project that will send data to PC and flash it",
            build_timeout_seconds=45,
            flash_timeout_seconds=45,
            cubemx_timeout_seconds=300,
        )
        self.assertEqual(result["selected_domain"], "requirements")

    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.stm32_cubemx_regenerate_project")
    @patch("stm32cubep_mcp.orchestrator.server.shared.load_project_metadata")
    def test_orchestrate_cubemx_regeneration_passes_project_json_payload(
        self,
        load_project_metadata: object,
        stm32_cubemx_regenerate_project: object,
    ) -> None:
        load_project_metadata.return_value = {
            "status": "loaded",
            "path": "config/stm32-project.json",
            "data": {
                "firmware": {
                    "ioc_path": "board/board.ioc",
                },
                "build": {
                    "project_name": "board-app",
                    "system": "cubeide",
                },
                "cubemx": {
                    "project_name": "board-app",
                    "project_toolchain": "STM32CubeIDE",
                    "project_path": "C:/work/board",
                    "script_path": "C:/work/board/script.txt",
                },
            },
        }
        stm32_cubemx_regenerate_project.return_value = {"success": True, "server": "cubemx"}

        result = orchestrator_server.stm32_orchestrate_cubemx_regeneration(timeout_seconds=120)

        stm32_cubemx_regenerate_project.assert_called_once_with(
            ioc_path="board/board.ioc",
            project_name="board-app",
            project_toolchain="STM32CubeIDE",
            project_path="C:/work/board",
            script_path="C:/work/board/script.txt",
            validate_build=True,
            timeout_seconds=120,
            build_timeout_seconds=600,
        )
        self.assertTrue(result["success"])

    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    async def test_orchestrate_prompt_routes_build_requests(self, stm32_build_project: object) -> None:
        stm32_build_project.return_value = {"server": "build", "implemented": False}

        result = await orchestrator_server.stm32_orchestrate_prompt("build the current project")

        stm32_build_project.assert_called_once()
        self.assertEqual(result["selected_domain"], "build")

    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    async def test_orchestrate_prompt_routes_flash_requests_with_file_path(self, stm32_flash_firmware: AsyncMock) -> None:
        stm32_flash_firmware.return_value = {"server": "cube_programmer", "success": True}

        result = await orchestrator_server.stm32_orchestrate_prompt(
            'flash the board with file_path="firmware.axf"',
            timeout_seconds=30,
        )

        stm32_flash_firmware.assert_awaited_once_with(file_path="firmware.axf", timeout_seconds=30)
        self.assertEqual(result["selected_domain"], "cube_programmer")

    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    async def test_build_then_flash_uses_build_artifact(
        self,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "artifact.axf"
            firmware.write_text("stub", encoding="utf-8")
            stm32_build_project.return_value = {"success": True, "artifact": str(firmware)}
            stm32_flash_firmware.return_value = {"success": True, "server": "cube_programmer"}

            result = await orchestrator_server.stm32_orchestrate_build_then_flash(
                target="Release",
                clean=True,
                build_timeout_seconds=300,
                flash_timeout_seconds=120,
            )

        stm32_build_project.assert_called_once_with(target="Release", clean=True, timeout_seconds=300)
        stm32_flash_firmware.assert_awaited_once_with(
            file_path=str(firmware),
            timeout_seconds=120,
            verify_mode="legacy",
            post_action="go",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["artifact_source"], "build")

    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    async def test_build_then_flash_skips_flash_when_build_fails(
        self,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
    ) -> None:
        stm32_build_project.return_value = {"success": False, "message": "build failed"}

        result = await orchestrator_server.stm32_orchestrate_build_then_flash()

        stm32_flash_firmware.assert_not_awaited()
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "build")

    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.update_plan_status")
    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_debug_session", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    @patch("stm32cubep_mcp.orchestrator.server.configured_cubemx_request")
    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.regenerate_project_internal")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.construct_ioc_file")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.apply_ioc_change_set")
    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.stm32_requirements_decompose")
    async def test_feature_delivery_workflow_runs_full_chain(
        self,
        stm32_requirements_decompose: object,
        apply_ioc_change_set: object,
        construct_ioc_file: object,
        regenerate_project_internal: object,
        configured_cubemx_request: object,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
        stm32_orchestrate_debug_session: AsyncMock,
        update_plan_status: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "firmware.elf"
            artifact.write_text("stub", encoding="utf-8")
            source_dir = Path(temp_dir) / "Src"
            source_dir.mkdir()
            (source_dir / "main.c").write_text(
                """#include \"main.h\"\n\n/* USER CODE BEGIN Includes */\n\n/* USER CODE END Includes */\n\n/* USER CODE BEGIN PV */\n\n/* USER CODE END PV */\n\nint main(void)\n{\n  /* USER CODE BEGIN 2 */\n\n  /* USER CODE END 2 */\n\n  /* USER CODE BEGIN WHILE */\n  while (1)\n  {\n    /* USER CODE END WHILE */\n\n    /* USER CODE BEGIN 3 */\n  }\n  /* USER CODE END 3 */\n}\n""",
                encoding="utf-8",
            )
            stm32_requirements_decompose.return_value = {
                "success": True,
                "contract": {
                    "plan_file": str(Path(temp_dir) / "requirement-plan.json"),
                    "current_increment": {"id": "increment-core-001"},
                    "core_features": [{"id": "core-uart-device-to-pc"}],
                    "execution_policy": {
                        "mode": "incremental",
                        "ioc_cubemx_validation": "best_effort",
                        "build_after_each_increment": True,
                        "flash_after_successful_build": True,
                        "runtime_check_after_flash": True,
                        "ask_user_on_repeated_failures": True,
                    },
                },
                "plan_artifact": {"plan_path": str(Path(temp_dir) / "requirement-plan.json")},
            }
            apply_ioc_change_set.return_value = {
                "success": True,
                "ioc_path": str(Path(temp_dir) / "board.ioc"),
                "cubemx_validation": {"success": True, "validation": "accepted", "message": "CubeMX accepted the IOC."},
            }
            construct_ioc_file.return_value = {
                "success": True,
                "ioc_path": str(Path(temp_dir) / "board.ioc"),
                "cubemx_validation": {"success": True, "validation": "accepted", "message": "CubeMX accepted the IOC."},
            }
            board_ioc = Path(temp_dir) / "board.ioc"
            board_ioc.write_text("stub", encoding="utf-8")
            configured_cubemx_request.return_value = {
                "ioc_path": str(board_ioc),
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": str(Path(temp_dir) / "generated-project"),
                "script_path": str(Path(temp_dir) / "generated-project" / "script.txt"),
            }
            regenerate_project_internal.return_value = {"success": True, "server": "cubemx"}
            stm32_build_project.return_value = {"success": True, "artifact": str(artifact)}
            stm32_flash_firmware.return_value = {"success": True, "server": "cube_programmer"}
            stm32_orchestrate_debug_session.return_value = {"success": True, "workflow": "debug_session"}

            result = await orchestrator_server.stm32_orchestrate_feature_prompt(
                prompt="Create a NUCLEO-L476RG project that sends data to PC",
                build_timeout_seconds=300,
                flash_timeout_seconds=120,
                cubemx_timeout_seconds=600,
            )

        stm32_requirements_decompose.assert_called_once_with("Create a NUCLEO-L476RG project that sends data to PC", persist_plan=True)
        apply_ioc_change_set.assert_called_once()
        construct_ioc_file.assert_not_called()
        regenerate_project_internal.assert_called_once()
        stm32_build_project.assert_called_once_with(timeout_seconds=300)
        stm32_flash_firmware.assert_awaited_once_with(
            file_path=str(artifact),
            timeout_seconds=120,
            verify_mode="legacy",
            post_action="go",
        )
        self.assertTrue(update_plan_status.called)
        self.assertTrue(result["success"])
        self.assertEqual(result["execution_policy_summary"]["ioc_cubemx_validation"], "best_effort")
        self.assertTrue(result["execution_policy_summary"]["ask_user_on_repeated_failures"])
        self.assertEqual(result["ioc_validation_summary"]["status"], "accepted")
        self.assertEqual(result["ioc_validation_summary"]["mode"], "apply")
        self.assertTrue(result["firmware_patch_result"]["success"])
        stm32_orchestrate_debug_session.assert_awaited_once_with(
            session_name="feature-runtime-validation",
            reset_before_launch=False,
            timeout_seconds=60,
        )
        self.assertTrue(result["runtime_validation_result"]["success"])
        cubemx_in_progress_call = next(
            call
            for call in update_plan_status.call_args_list
            if call.kwargs.get("stage") == "cubemx" and call.kwargs.get("status") == "in_progress"
        )
        self.assertEqual(cubemx_in_progress_call.kwargs["details"]["cubemx_validation"]["validation"], "accepted")

    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.update_plan_status")
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    @patch("stm32cubep_mcp.orchestrator.server.configured_cubemx_request")
    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.regenerate_project_internal")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.construct_ioc_file")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.apply_ioc_change_set")
    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.stm32_requirements_decompose")
    async def test_feature_delivery_workflow_reuses_cubemx_result_from_ioc_validation(
        self,
        stm32_requirements_decompose: object,
        apply_ioc_change_set: object,
        construct_ioc_file: object,
        regenerate_project_internal: object,
        configured_cubemx_request: object,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
        update_plan_status: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "firmware.elf"
            artifact.write_text("stub", encoding="utf-8")
            board_ioc = Path(temp_dir) / "board.ioc"
            board_ioc.write_text("stub", encoding="utf-8")
            project_root = Path(temp_dir) / "generated-project"
            validation_cubemx_result = {
                "success": True,
                "server": "cubemx",
                "project_path": str(project_root),
            }
            stm32_requirements_decompose.return_value = {
                "success": True,
                "contract": {
                    "plan_file": str(Path(temp_dir) / "plan.md"),
                    "current_increment": {"id": "increment-core-001"},
                    "execution_policy": {
                        "mode": "incremental",
                        "ioc_cubemx_validation": "required",
                        "build_after_each_increment": True,
                        "flash_after_successful_build": False,
                        "runtime_check_after_flash": False,
                        "ask_user_on_repeated_failures": False,
                    },
                },
                "plan_artifact": {"plan_path": str(Path(temp_dir) / "plan.md")},
            }
            apply_ioc_change_set.return_value = {
                "success": True,
                "ioc_path": str(board_ioc),
                "cubemx_validation": {
                    "success": True,
                    "validation": "accepted",
                    "message": "CubeMX accepted the IOC.",
                    "cubemx_result": validation_cubemx_result,
                },
            }
            construct_ioc_file.return_value = {"success": True, "ioc_path": str(board_ioc)}
            configured_cubemx_request.return_value = {
                "ioc_path": str(board_ioc),
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": str(project_root),
                "script_path": str(project_root / "script.txt"),
            }
            stm32_build_project.return_value = {"success": True, "artifact": str(artifact)}

            result = await orchestrator_server.stm32_orchestrate_feature_prompt(
                prompt="Create a NUCLEO-L476RG project that sends data to PC but build only and do not flash",
                build_timeout_seconds=300,
                flash_timeout_seconds=120,
                cubemx_timeout_seconds=600,
            )

        regenerate_project_internal.assert_not_called()
        stm32_flash_firmware.assert_not_awaited()
        self.assertTrue(result["success"])
        self.assertTrue(result["cubemx_result"]["reused_from_ioc_validation"])

    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.update_plan_status")
    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_debug_session", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    @patch("stm32cubep_mcp.orchestrator.server.configured_cubemx_request")
    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.regenerate_project_internal")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.construct_ioc_file")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.apply_ioc_change_set")
    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.stm32_requirements_decompose")
    async def test_feature_delivery_workflow_constructs_ioc_when_missing(
        self,
        stm32_requirements_decompose: object,
        apply_ioc_change_set: object,
        construct_ioc_file: object,
        regenerate_project_internal: object,
        configured_cubemx_request: object,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
        stm32_orchestrate_debug_session: AsyncMock,
        update_plan_status: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_ioc_path = Path(temp_dir) / "missing-board.ioc"
            artifact = Path(temp_dir) / "firmware.elf"
            artifact.write_text("stub", encoding="utf-8")
            source_dir = Path(temp_dir) / "Src"
            source_dir.mkdir()
            (source_dir / "main.c").write_text(
                """#include \"main.h\"\n\n/* USER CODE BEGIN Includes */\n\n/* USER CODE END Includes */\n\n/* USER CODE BEGIN PV */\n\n/* USER CODE END PV */\n\nint main(void)\n{\n  /* USER CODE BEGIN 2 */\n\n  /* USER CODE END 2 */\n\n  /* USER CODE BEGIN WHILE */\n  while (1)\n  {\n    /* USER CODE END WHILE */\n\n    /* USER CODE BEGIN 3 */\n  }\n  /* USER CODE END 3 */\n}\n""",
                encoding="utf-8",
            )
            stm32_requirements_decompose.return_value = {
                "success": True,
                "contract": {
                    "plan_file": str(Path(temp_dir) / "plan.md"),
                    "current_increment": {"id": "increment-core-001"},
                    "core_features": [{"id": "core-uart-device-to-pc"}],
                    "execution_policy": {
                        "mode": "incremental",
                        "ioc_cubemx_validation": "required",
                        "build_after_each_increment": True,
                        "flash_after_successful_build": True,
                        "runtime_check_after_flash": True,
                        "ask_user_on_repeated_failures": False,
                    },
                },
                "plan_artifact": {"plan_path": str(Path(temp_dir) / "plan.md")},
            }
            configured_cubemx_request.return_value = {
                "ioc_path": str(missing_ioc_path),
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": str(Path(temp_dir) / "generated-project"),
                "script_path": str(Path(temp_dir) / "generated-project" / "script.txt"),
            }
            construct_ioc_file.return_value = {
                "success": True,
                "ioc_path": str(missing_ioc_path),
                "cubemx_validation": {"success": True, "validation": "accepted", "message": "CubeMX accepted the IOC."},
            }
            regenerate_project_internal.return_value = {"success": True, "server": "cubemx"}
            stm32_build_project.return_value = {"success": True, "artifact": str(artifact)}
            stm32_flash_firmware.return_value = {"success": True, "server": "cube_programmer"}
            stm32_orchestrate_debug_session.return_value = {"success": True, "workflow": "debug_session"}

            result = await orchestrator_server.stm32_orchestrate_feature_prompt(
                prompt="Create a NUCLEO-L476RG project that sends data to PC",
                build_timeout_seconds=300,
                flash_timeout_seconds=120,
                cubemx_timeout_seconds=600,
            )

        apply_ioc_change_set.assert_not_called()
        construct_ioc_file.assert_called_once()
        regenerate_project_internal.assert_called_once()
        stm32_build_project.assert_called_once_with(timeout_seconds=300)
        stm32_flash_firmware.assert_awaited_once()
        self.assertTrue(update_plan_status.called)
        self.assertTrue(result["success"])
        self.assertEqual(result["execution_policy_summary"]["ioc_cubemx_validation"], "required")
        self.assertFalse(result["execution_policy_summary"]["ask_user_on_repeated_failures"])
        self.assertEqual(result["ioc_validation_summary"]["status"], "accepted")
        self.assertEqual(result["ioc_validation_summary"]["mode"], "construct")
        self.assertTrue(result["firmware_patch_result"]["success"])
        cubemx_in_progress_call = next(
            call
            for call in update_plan_status.call_args_list
            if call.kwargs.get("stage") == "cubemx" and call.kwargs.get("status") == "in_progress"
        )
        self.assertEqual(cubemx_in_progress_call.kwargs["details"]["cubemx_validation"]["validation"], "accepted")

    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.update_plan_status")
    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_debug_session", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    @patch("stm32cubep_mcp.orchestrator.server.configured_cubemx_request")
    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.regenerate_project_internal")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.construct_ioc_file")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.apply_ioc_change_set")
    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.stm32_requirements_decompose")
    async def test_feature_delivery_workflow_skips_flash_when_policy_disables_it(
        self,
        stm32_requirements_decompose: object,
        apply_ioc_change_set: object,
        construct_ioc_file: object,
        regenerate_project_internal: object,
        configured_cubemx_request: object,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
        stm32_orchestrate_debug_session: AsyncMock,
        update_plan_status: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "firmware.elf"
            artifact.write_text("stub", encoding="utf-8")
            board_ioc = Path(temp_dir) / "board.ioc"
            board_ioc.write_text("stub", encoding="utf-8")
            stm32_requirements_decompose.return_value = {
                "success": True,
                "contract": {
                    "plan_file": str(Path(temp_dir) / "plan.md"),
                    "current_increment": {"id": "increment-core-001"},
                    "execution_policy": {
                        "mode": "incremental",
                        "ioc_cubemx_validation": "best_effort",
                        "build_after_each_increment": True,
                        "flash_after_successful_build": False,
                        "runtime_check_after_flash": False,
                        "ask_user_on_repeated_failures": True,
                    },
                },
                "plan_artifact": {"plan_path": str(Path(temp_dir) / "plan.md")},
            }
            apply_ioc_change_set.return_value = {
                "success": True,
                "ioc_path": str(board_ioc),
                "cubemx_validation": {"success": True, "validation": "accepted", "message": "CubeMX accepted the IOC."},
            }
            construct_ioc_file.return_value = {"success": True, "ioc_path": str(board_ioc)}
            configured_cubemx_request.return_value = {
                "ioc_path": str(board_ioc),
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": str(Path(temp_dir) / "generated-project"),
                "script_path": str(Path(temp_dir) / "generated-project" / "script.txt"),
            }
            regenerate_project_internal.return_value = {"success": True, "server": "cubemx"}
            stm32_build_project.return_value = {"success": True, "artifact": str(artifact)}

            result = await orchestrator_server.stm32_orchestrate_feature_prompt(
                prompt="Create a NUCLEO-L476RG project that sends data to PC but build only and do not flash",
                build_timeout_seconds=300,
                flash_timeout_seconds=120,
                cubemx_timeout_seconds=600,
            )

        stm32_flash_firmware.assert_not_awaited()
        stm32_orchestrate_debug_session.assert_not_awaited()
        self.assertTrue(result["success"])
        self.assertTrue(result["flash_skipped"])
        self.assertEqual(result["execution_policy_summary"]["flash_after_successful_build"], False)
        self.assertEqual(result["artifact_path"], str(artifact))

    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.update_plan_status")
    @patch("stm32cubep_mcp.orchestrator.server.stm32_orchestrate_debug_session", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    @patch("stm32cubep_mcp.orchestrator.server.configured_cubemx_request")
    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.regenerate_project_internal")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.construct_ioc_file")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.apply_ioc_change_set")
    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.stm32_requirements_decompose")
    async def test_feature_delivery_workflow_fails_when_runtime_validation_fails(
        self,
        stm32_requirements_decompose: object,
        apply_ioc_change_set: object,
        construct_ioc_file: object,
        regenerate_project_internal: object,
        configured_cubemx_request: object,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
        stm32_orchestrate_debug_session: AsyncMock,
        update_plan_status: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "firmware.elf"
            artifact.write_text("stub", encoding="utf-8")
            board_ioc = Path(temp_dir) / "board.ioc"
            board_ioc.write_text("stub", encoding="utf-8")
            stm32_requirements_decompose.return_value = {
                "success": True,
                "contract": {
                    "plan_file": str(Path(temp_dir) / "plan.md"),
                    "current_increment": {"id": "increment-core-001"},
                    "execution_policy": {
                        "mode": "incremental",
                        "ioc_cubemx_validation": "required",
                        "build_after_each_increment": True,
                        "flash_after_successful_build": True,
                        "runtime_check_after_flash": True,
                        "ask_user_on_repeated_failures": False,
                    },
                },
                "plan_artifact": {"plan_path": str(Path(temp_dir) / "plan.md")},
            }
            apply_ioc_change_set.return_value = {
                "success": True,
                "ioc_path": str(board_ioc),
                "cubemx_validation": {"success": True, "validation": "accepted", "message": "CubeMX accepted the IOC."},
            }
            construct_ioc_file.return_value = {"success": True, "ioc_path": str(board_ioc)}
            configured_cubemx_request.return_value = {
                "ioc_path": str(board_ioc),
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": str(Path(temp_dir) / "generated-project"),
                "script_path": str(Path(temp_dir) / "generated-project" / "script.txt"),
            }
            regenerate_project_internal.return_value = {"success": True, "server": "cubemx"}
            stm32_build_project.return_value = {"success": True, "artifact": str(artifact)}
            stm32_flash_firmware.return_value = {"success": True, "server": "cube_programmer"}
            stm32_orchestrate_debug_session.return_value = {"success": False, "workflow": "debug_session", "message": "launch failed"}

            result = await orchestrator_server.stm32_orchestrate_feature_prompt(
                prompt="Create a NUCLEO-L476RG project that sends data to PC and run and test it",
                build_timeout_seconds=300,
                flash_timeout_seconds=120,
                cubemx_timeout_seconds=600,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "runtime_validation")
        stm32_orchestrate_debug_session.assert_awaited_once()

    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.update_plan_status")
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    @patch("stm32cubep_mcp.orchestrator.server.configured_cubemx_request")
    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.regenerate_project_internal")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.construct_ioc_file")
    @patch("stm32cubep_mcp.orchestrator.server.ioc_builder_server.apply_ioc_change_set")
    @patch("stm32cubep_mcp.orchestrator.server.requirements_server.stm32_requirements_decompose")
    async def test_feature_delivery_workflow_uses_constructed_ioc_path_for_cubemx(
        self,
        stm32_requirements_decompose: object,
        apply_ioc_change_set: object,
        construct_ioc_file: object,
        regenerate_project_internal: object,
        configured_cubemx_request: object,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
        update_plan_status: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            configured_ioc_path = Path(temp_dir) / "missing-board.ioc"
            constructed_ioc_path = Path(temp_dir) / "generated" / "board.ioc"
            artifact = Path(temp_dir) / "firmware.elf"
            artifact.write_text("stub", encoding="utf-8")
            stm32_requirements_decompose.return_value = {
                "success": True,
                "contract": {
                    "plan_file": str(Path(temp_dir) / "plan.md"),
                    "current_increment": {"id": "increment-core-001"},
                },
                "plan_artifact": {"plan_path": str(Path(temp_dir) / "plan.md")},
            }
            configured_cubemx_request.return_value = {
                "ioc_path": str(configured_ioc_path),
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": str(Path(temp_dir) / "generated-project"),
                "script_path": str(Path(temp_dir) / "generated-project" / "script.txt"),
            }
            construct_ioc_file.return_value = {"success": True, "ioc_path": str(constructed_ioc_path)}
            regenerate_project_internal.return_value = {"success": True, "server": "cubemx"}
            stm32_build_project.return_value = {"success": True, "artifact": str(artifact)}
            stm32_flash_firmware.return_value = {"success": True, "server": "cube_programmer"}

            result = await orchestrator_server.stm32_orchestrate_feature_prompt(
                prompt="Create a NUCLEO-L476RG project that sends data to PC",
                build_timeout_seconds=300,
                flash_timeout_seconds=120,
                cubemx_timeout_seconds=600,
            )

        apply_ioc_change_set.assert_not_called()
        construct_ioc_file.assert_called_once()
        regenerate_project_internal.assert_called_once_with(
            ioc_path=str(constructed_ioc_path),
            project_name="board-app",
            project_toolchain="STM32CubeIDE",
            project_path=str(Path(temp_dir) / "generated-project"),
            script_path=str(Path(temp_dir) / "generated-project" / "script.txt"),
            validate_build=False,
            timeout_seconds=600,
            build_timeout_seconds=300,
            progress_callback=unittest.mock.ANY,
        )
        self.assertEqual(result["cubemx_result"]["cubemx_request"]["ioc_path"], str(constructed_ioc_path))
        self.assertTrue(update_plan_status.called)
        self.assertTrue(result["success"])

    @patch("stm32cubep_mcp.orchestrator.server.shared.load_project_metadata")
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_flash_firmware", new_callable=AsyncMock)
    @patch("stm32cubep_mcp.orchestrator.server.build_server.stm32_build_project")
    async def test_build_then_flash_falls_back_to_project_artifact(
        self,
        stm32_build_project: object,
        stm32_flash_firmware: AsyncMock,
        load_project_metadata: object,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            firmware = Path(temp_dir) / "configured.axf"
            firmware.write_text("stub", encoding="utf-8")
            stm32_build_project.return_value = {"success": True, "artifact": ""}
            stm32_flash_firmware.return_value = {"success": True, "server": "cube_programmer"}
            load_project_metadata.return_value = {
                "data": {
                    "firmware": {
                        "default_artifact": str(firmware),
                    }
                }
            }

            result = await orchestrator_server.stm32_orchestrate_build_then_flash()

        stm32_flash_firmware.assert_awaited_once_with(
            file_path=str(firmware),
            timeout_seconds=240,
            verify_mode="legacy",
            post_action="go",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["artifact_source"], "project_config")

    @patch("stm32cubep_mcp.orchestrator.server.debug_server.stm32_debug_launch")
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_reset", new_callable=AsyncMock)
    async def test_orchestrate_debug_session_resets_then_launches(
        self,
        stm32_reset: AsyncMock,
        stm32_debug_launch: object,
    ) -> None:
        stm32_reset.return_value = {"success": True, "operation": "reset"}
        stm32_debug_launch.return_value = {"success": True, "operation": "launch"}

        result = await orchestrator_server.stm32_orchestrate_debug_session(session_name="diag", timeout_seconds=30)

        stm32_reset.assert_awaited_once_with(timeout_seconds=30)
        stm32_debug_launch.assert_called_once_with(
            session_name="diag",
            port_number=None,
            swo_port=None,
            enable_swo=True,
            serial_number=None,
            frequency_khz=None,
            attach=False,
            persistent=True,
            shared_mode=False,
            verify=False,
            incremental=False,
            erase_all=False,
            verbose=False,
            log_level=None,
            refresh_delay=None,
            initialize_reset=False,
            apid=None,
            halt=False,
            timeout_seconds=30,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["stage"], "completed")

    @patch("stm32cubep_mcp.orchestrator.server.debug_server.stm32_debug_launch")
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.stm32_reset", new_callable=AsyncMock)
    async def test_orchestrate_debug_session_skips_launch_on_reset_failure(
        self,
        stm32_reset: AsyncMock,
        stm32_debug_launch: object,
    ) -> None:
        stm32_reset.return_value = {"success": False, "message": "reset failed"}

        result = await orchestrator_server.stm32_orchestrate_debug_session(timeout_seconds=25)

        stm32_reset.assert_awaited_once_with(timeout_seconds=25)
        stm32_debug_launch.assert_not_called()
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "reset")

    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.collect_host_capabilities")
    @patch("stm32cubep_mcp.orchestrator.server.build_server.collect_build_capabilities")
    @patch("stm32cubep_mcp.orchestrator.server.debug_server.collect_debug_capabilities")
    @patch("stm32cubep_mcp.orchestrator.server.cubemx_server.stm32_cubemx_capabilities")
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.load_tools_local_config")
    @patch("stm32cubep_mcp.orchestrator.server.shared.load_project_metadata")
    @patch("stm32cubep_mcp.orchestrator.server.programmer_server.summarize_config_status")
    def test_orchestration_status_aggregates_domains(
        self,
        summarize_config_status: object,
        load_project_metadata: object,
        load_tools_local_config: object,
        stm32_cubemx_capabilities: object,
        collect_debug_capabilities: object,
        collect_build_capabilities: object,
        collect_host_capabilities: object,
    ) -> None:
        summarize_config_status.side_effect = lambda value: {"status": value["status"]}
        load_project_metadata.return_value = {"status": "loaded"}
        load_tools_local_config.return_value = {"status": "loaded"}
        collect_host_capabilities.return_value = {"server": "cube_programmer"}
        collect_build_capabilities.return_value = {"server": "build"}
        collect_debug_capabilities.return_value = {"server": "debug"}
        stm32_cubemx_capabilities.return_value = {"server": "cubemx"}

        result = orchestrator_server.stm32_orchestration_status()

        self.assertEqual(result["domains"]["build"]["server"], "build")
        self.assertEqual(result["domains"]["debug"]["server"], "debug")
        self.assertEqual(result["domains"]["cubemx"]["server"], "cubemx")


if __name__ == "__main__":
    unittest.main()