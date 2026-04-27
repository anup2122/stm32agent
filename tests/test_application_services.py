from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from stm32cubep_mcp.application.services import (
    artifact_service,
    cubemx_host_service,
    cubemx_inspection_service,
    cubemx_log_service,
    cubemx_runtime_service,
    cubemx_tool_service,
    ioc_builder_service,
    project_config_service,
    routing_service,
)
from stm32cubep_mcp.application.workflows import cubemx_regeneration, debug_question, live_debug, prompt_router


class RoutingServiceTests(unittest.TestCase):
    def test_classify_prompt_routes_engineering_spec_to_requirements(self) -> None:
        prompt = (
            "This project has to be tested with NUCLEO-L476RG Rev C. "
            "The objective is to configure TIM1 channel 3 complementary PWM with DMA at 80 MHz."
        )

        self.assertEqual(routing_service.classify_prompt(prompt), "requirements")

    def test_extract_file_path_strips_quotes(self) -> None:
        self.assertEqual(routing_service.extract_file_path('flash with file_path="firmware.axf"'), "firmware.axf")


class ArtifactServiceTests(unittest.TestCase):
    def test_select_flash_artifact_prefers_build_then_project_config(self) -> None:
        configured = lambda: "configured.elf"

        artifact_path, source = artifact_service.select_flash_artifact(
            {"artifact": "build.elf"},
            configured_firmware_artifact=configured,
        )
        self.assertEqual((artifact_path, source), ("build.elf", "build"))

        artifact_path, source = artifact_service.select_flash_artifact(
            {},
            configured_firmware_artifact=configured,
        )
        self.assertEqual((artifact_path, source), ("configured.elf", "project_config"))


class ProjectConfigServiceTests(unittest.TestCase):
    def test_configured_cubemx_request_reads_shared_fields(self) -> None:
        result = project_config_service.configured_cubemx_request(
            load_project_metadata=lambda: {
                "data": {
                    "firmware": {"ioc_path": "board.ioc"},
                    "build": {"project_name": "board-app", "system": "cubeide"},
                    "cubemx": {
                        "project_name": "board-app",
                        "project_toolchain": "STM32CubeIDE",
                        "project_path": "C:/work/board",
                        "script_path": "C:/work/board/script.txt",
                    },
                }
            },
            summarize_config_status=lambda payload: {"status": payload.get("status", "loaded")},
        )

        self.assertEqual(result["ioc_path"], "board.ioc")
        self.assertEqual(result["project_name"], "board-app")
        self.assertEqual(result["project_toolchain"], "STM32CubeIDE")
        self.assertFalse(result["missing_fields"])


class CubeMxInspectionServiceTests(unittest.TestCase):
    def test_build_cubemx_capabilities_aggregates_discovery_and_config_status(self) -> None:
        result = cubemx_inspection_service.build_cubemx_capabilities(
            discover_cubemx_fn=lambda: {"resolved_path": "C:/tools/STM32CubeMX.exe"},
            discover_ioc_path_fn=lambda: {"resolved_path": "C:/work/board.ioc"},
            load_project_metadata_fn=lambda: {"status": "loaded"},
            load_tools_local_config_fn=lambda: {"status": "loaded"},
            summarize_config_status_fn=lambda payload: {"status": payload.get("status")},
        )

        self.assertEqual(result["server"], "cubemx")
        self.assertEqual(result["tool_discovery"]["resolved_path"], "C:/tools/STM32CubeMX.exe")
        self.assertEqual(result["default_ioc_path"], "C:/work/board.ioc")

    def test_parse_ioc_summary_returns_summary_when_ioc_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "board.ioc"
            ioc_path.write_text("stub", encoding="utf-8")

            result = cubemx_inspection_service.parse_ioc_summary(
                ioc_path=None,
                discover_ioc_path_fn=lambda requested: {
                    "resolved_path": str(ioc_path),
                    "requested_path": requested,
                },
                parse_ioc_properties_fn=lambda resolved_ioc: {"ProjectManager.ProjectName": "board"},
                summarize_ioc_fn=lambda resolved_ioc, properties: {"project": {"name": properties["ProjectManager.ProjectName"]}},
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["project"]["name"], "board")


class CubeMxHostServiceTests(unittest.TestCase):
    def test_load_cubemx_metadata_reads_project_section(self) -> None:
        result = cubemx_host_service.load_cubemx_metadata(
            load_project_metadata_fn=lambda: {
                "data": {
                    "cubemx": {
                        "project_name": "board-app",
                        "log_path": "C:/logs/cubemx.log",
                    }
                }
            }
        )

        self.assertEqual(result["project_name"], "board-app")

    def test_configured_cubemx_log_path_resolves_absolute_path(self) -> None:
        result = cubemx_host_service.configured_cubemx_log_path(
            load_cubemx_metadata_fn=lambda: {"log_path": "C:/logs/cubemx.log"}
        )

        self.assertEqual(result, Path("C:/logs/cubemx.log").resolve())


class CubeMxLogServiceTests(unittest.TestCase):
    def test_write_cubemx_log_writes_expected_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "cubemx.log"

            cubemx_log_service.write_cubemx_log(
                log_path,
                ioc_path=Path("C:/work/board.ioc"),
                launcher={"tool_path": "C:/tools/STM32CubeMX.exe", "launch_kind": "executable"},
                command=["C:/tools/STM32CubeMX.exe", "-q", "script.txt"],
                script_path=Path("C:/work/script.txt"),
                script_contents="project generate\nexit_mx\n",
                regeneration_result={"success": True, "exit_code": 0, "stdout": "ok", "stderr": ""},
                completion_wait={"success": True, "marker_path": "C:/work/.project", "status": "created", "message": "done"},
                affected_files={"new_files": ["a"], "deleted_files": [], "modified_files": ["b"]},
                output_review={"message": "reviewed", "top_level_entries": ["STM32CubeIDE/"], "mismatches": []},
                build_validation={"success": True, "message": "build ok"},
            )

            content = log_path.read_text(encoding="utf-8")

        self.assertIn(f"ioc_path={Path('C:/work/board.ioc')}", content)
        self.assertIn("script:", content)
        self.assertIn("completion_wait:", content)
        self.assertIn("build_validation:", content)


class CubeMxRuntimeServiceTests(unittest.TestCase):
    def test_cubemx_failure_reason_detects_script_failure(self) -> None:
        result = cubemx_runtime_service.cubemx_failure_reason("KO", "")
        self.assertIn("command-script failure", result)

    def test_run_cubemx_command_returns_missing_executable_result(self) -> None:
        result = cubemx_runtime_service.run_cubemx_command(
            ["STM32CubeMX.exe", "-q", "script.txt"],
            5,
            host_platform="windows",
            configured_cubemx_log_path_resolver=lambda: None,
            capture_completion_marker_state_fn=lambda paths: {},
            check_completion_markers_fn=lambda *args, **kwargs: None,
            collect_tree_state_fn=lambda root: {},
            open_process_fn=lambda invocation: (_ for _ in ()).throw(FileNotFoundError("missing")),
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], -2)


class CubeMxToolServiceTests(unittest.TestCase):
    def test_report_cubemx_capabilities_uses_inspection_contract(self) -> None:
        result = cubemx_tool_service.report_cubemx_capabilities(
            discover_cubemx_fn=lambda: {"resolved_path": "C:/tools/STM32CubeMX.exe"},
            discover_ioc_path_fn=lambda: {"resolved_path": "C:/work/board.ioc"},
            load_project_metadata_fn=lambda: {"status": "loaded"},
            load_tools_local_config_fn=lambda: {"status": "loaded"},
            summarize_config_status_fn=lambda payload: {"status": payload.get("status")},
        )

        self.assertEqual(result["server"], "cubemx")
        self.assertEqual(result["default_ioc_path"], "C:/work/board.ioc")

    def test_regenerate_cubemx_project_delegates_to_regeneration_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "generated"
            project_root.mkdir()
            script_path = project_root / "script.txt"
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text("stub", encoding="utf-8")
            marker_path = project_root / "STM32CubeIDE" / ".project"

            result = cubemx_tool_service.regenerate_cubemx_project(
                ioc_path=str(ioc_path),
                project_name="board-app",
                project_toolchain="STM32CubeIDE",
                project_path=str(project_root),
                script_path=str(script_path),
                output_root=str(project_root),
                validate_build=False,
                timeout_seconds=120,
                build_timeout_seconds=300,
                progress_callback=None,
                resolve_cubemx_project_inputs_fn=lambda **kwargs: {
                    "ioc_discovery": {"resolved_path": str(ioc_path)},
                    "ioc_path": str(ioc_path),
                    "project_name": "board-app",
                    "project_toolchain": "STM32CubeIDE",
                    "project_path": str(project_root),
                    "script_path": str(script_path),
                    "completion_marker": str(marker_path),
                    "completion_markers": [str(marker_path)],
                    "missing_fields": [],
                },
                resolve_cubemx_launcher_fn=lambda: {
                    "command_prefix": ["cubemx"],
                    "tool_path": "cubemx",
                    "launch_kind": "executable",
                },
                resolve_generation_root_fn=lambda resolved_ioc, output_root, resolved_project_path: Path(str(output_root)),
                build_cubemx_script_fn=lambda resolved_ioc, project_name, project_toolchain, generation_root: "project generate\nexit_mx\n",
                regeneration_root_fn=lambda resolved_ioc, output_root, resolved_project_path: Path(str(output_root)),
                collect_tree_state_fn=lambda root: {},
                diff_tree_state_fn=lambda before, after: {"new_files": [], "deleted_files": [], "modified_files": []},
                run_cubemx_command_fn=lambda *args, **kwargs: {
                    "success": True,
                    "exit_code": 0,
                    "stdout": "ok",
                    "stderr": "",
                    "failure_reason": None,
                },
                wait_for_completion_markers_fn=lambda *args, **kwargs: {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "created",
                },
                collect_output_review_fn=lambda resolved_ioc, generation_root: {"mismatches": [], "top_level_entries": []},
                collect_build_layout_summary_fn=lambda generation_root: {"generation_root": str(generation_root)},
                build_project_fn=lambda **kwargs: {"success": True, **kwargs},
                create_log_path_fn=lambda prefix: project_root / f"{prefix}.log",
                write_cubemx_log_fn=lambda *args, **kwargs: None,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["project_name"], "board-app")
            self.assertEqual(script_path.read_text(encoding="utf-8"), "project generate\nexit_mx\n")

    def test_orchestrate_cubemx_regeneration_uses_configured_request(self) -> None:
        recorded: dict[str, object] = {}

        def regenerate_project(**kwargs: object) -> dict[str, object]:
            recorded.update(kwargs)
            return {"success": True, "server": "cubemx"}

        result = cubemx_tool_service.orchestrate_cubemx_regeneration(
            validate_build=True,
            timeout_seconds=120,
            build_timeout_seconds=600,
            configured_cubemx_request_fn=lambda: {
                "ioc_path": "board.ioc",
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": "C:/work/board",
                "script_path": "C:/work/board/script.txt",
                "missing_fields": [],
            },
            regenerate_project_fn=regenerate_project,
        )

        self.assertTrue(result["success"])
        self.assertEqual(recorded["ioc_path"], "board.ioc")
        self.assertEqual(recorded["project_name"], "board-app")


class IocBuilderServiceTests(unittest.TestCase):
    def test_apply_ioc_change_set_updates_ioc_and_validates(self) -> None:
        contract = {
            "defaults": {"toolchain": "STM32CubeIDE"},
            "execution_policy": {"ioc_cubemx_validation": "required"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "board.ioc"
            ioc_path.write_text("Mcu.Name=STM32L476RGTx\n", encoding="utf-8")

            result = ioc_builder_service.apply_ioc_change_set(
                contract=contract,
                ioc_path=str(ioc_path),
                synthesize_ioc_change_set_fn=lambda payload: {
                    "success": True,
                    "operations": [
                        {
                            "op_id": "set-usart2",
                            "kind": "set_property",
                            "target": {"key": "USART2.BaudRate"},
                            "value": 115200,
                        }
                    ],
                },
                resolve_ioc_path_fn=lambda requested: Path(str(requested)).resolve() if requested else None,
                apply_ioc_operations_fn=lambda lines, operations: (
                    lines.append("USART2.BaudRate=115200") or {
                        "changed_keys": ["USART2.BaudRate"],
                        "unchanged_keys": [],
                        "enabled_peripherals": ["USART2"],
                        "used_pins": ["PA2", "PA3"],
                    }
                ),
                validate_ioc_with_cubemx_fn=lambda ioc_path, project_name, project_toolchain: {
                    "success": True,
                    "validation": "accepted",
                },
                default_toolchain="STM32CubeIDE",
            )

            updated_text = ioc_path.read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertIn("USART2.BaudRate=115200", updated_text)
        self.assertEqual(result["cubemx_validation"]["validation"], "accepted")

    def test_construct_ioc_file_materializes_base_then_mutates(self) -> None:
        contract = {
            "target": {"mcu": "STM32L476RGTx"},
            "defaults": {"toolchain": "STM32CubeIDE"},
            "execution_policy": {"ioc_cubemx_validation": "best_effort"},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            result = ioc_builder_service.construct_ioc_file(
                contract=contract,
                ioc_path=str(ioc_path),
                overwrite=False,
                source_ioc_path=None,
                synthesize_ioc_change_set_fn=lambda payload: {
                    "success": True,
                    "operations": [
                        {
                            "op_id": "set-pa2",
                            "kind": "set_property",
                            "target": {"key": "PA2.Signal"},
                            "value": "USART2_TX",
                        }
                    ],
                },
                resolve_ioc_path_fn=lambda requested: Path(str(requested)).resolve() if requested else None,
                load_base_ioc_lines_fn=lambda payload, source_ioc_path=None: {
                    "success": True,
                    "construction_source": "local_board_ioc",
                    "lines": ["Mcu.Name=STM32L476RGTx", "ProjectManager.ToolChain=STM32CubeIDE"],
                },
                apply_project_manager_defaults_fn=lambda lines, project_name, toolchain, target_mcu: lines.extend(
                    [f"ProjectManager.ProjectName={project_name}", f"ProjectManager.DeviceId={target_mcu}"]
                ),
                apply_ioc_operations_fn=lambda lines, operations: (
                    lines.append("PA2.Signal=USART2_TX") or {
                        "changed_keys": ["PA2.Signal"],
                        "unchanged_keys": [],
                        "enabled_peripherals": ["USART2"],
                        "used_pins": ["PA2"],
                    }
                ),
                validate_ioc_lines_fn=lambda lines, payload: [],
                validate_ioc_with_cubemx_fn=lambda ioc_path, project_name, project_toolchain: {
                    "success": True,
                    "validation": "accepted",
                },
                default_toolchain="STM32CubeIDE",
            )

            constructed_text = ioc_path.read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertEqual(result["construction_source"], "local_board_ioc")
        self.assertIn("ProjectManager.ProjectName=constructed", constructed_text)
        self.assertIn("PA2.Signal=USART2_TX", constructed_text)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_validation_releases_debug_session(self) -> None:
        updates: list[dict[str, object]] = []
        stop_calls: list[dict[str, object]] = []

        result = await live_debug.run_runtime_validation_stage(
            plan_file="plan.md",
            increment_id="increment-1",
            flash_timeout_seconds=120,
            update_plan_status=lambda *args, **kwargs: updates.append({"args": args, "kwargs": kwargs}) or {"success": True},
            orchestrate_debug_session_fn=AsyncMock(return_value={"success": True, "workflow": "debug_session"}),
            stop_debug_session_fn=lambda **kwargs: stop_calls.append(kwargs) or {"success": True, "operation": "stop"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(stop_calls[0]["session_name"], "feature-runtime-validation")
        self.assertEqual(result["cleanup_result"]["operation"], "stop")
        self.assertEqual(updates[-1]["kwargs"]["status"], "completed")

    def test_cubemx_regeneration_calls_tool_with_resolved_request(self) -> None:
        recorded: dict[str, object] = {}

        def regenerate_project(**kwargs: object) -> dict[str, object]:
            recorded.update(kwargs)
            return {"success": True, "server": "cubemx"}

        result = cubemx_regeneration.orchestrate_cubemx_regeneration(
            validate_build=True,
            timeout_seconds=120,
            build_timeout_seconds=600,
            configured_cubemx_request=lambda: {
                "ioc_path": "board.ioc",
                "project_name": "board-app",
                "project_toolchain": "STM32CubeIDE",
                "project_path": "C:/work/board",
                "script_path": "C:/work/board/script.txt",
                "missing_fields": [],
            },
            regenerate_project=regenerate_project,
        )

        self.assertTrue(result["success"])
        self.assertEqual(recorded["ioc_path"], "board.ioc")
        self.assertEqual(recorded["project_name"], "board-app")
        self.assertEqual(recorded["script_path"], "C:/work/board/script.txt")

    def test_regenerate_project_workflow_writes_script_and_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "generated"
            project_root.mkdir()
            script_path = project_root / "script.txt"
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text("stub", encoding="utf-8")
            marker_path = project_root / "STM32CubeIDE" / ".project"

            result = cubemx_regeneration.regenerate_project_workflow(
                ioc_path=str(ioc_path),
                project_name="board-app",
                project_toolchain="STM32CubeIDE",
                project_path=str(project_root),
                script_path=str(script_path),
                output_root=str(project_root),
                validate_build=True,
                timeout_seconds=120,
                build_timeout_seconds=300,
                progress_callback=None,
                resolve_cubemx_project_inputs_fn=lambda **kwargs: {
                    "ioc_discovery": {"resolved_path": str(ioc_path)},
                    "ioc_path": str(ioc_path),
                    "project_name": "board-app",
                    "project_toolchain": "STM32CubeIDE",
                    "project_path": str(project_root),
                    "script_path": str(script_path),
                    "completion_marker": str(marker_path),
                    "completion_markers": [str(marker_path)],
                    "missing_fields": [],
                },
                resolve_cubemx_launcher_fn=lambda: {
                    "command_prefix": ["cubemx"],
                    "tool_path": "cubemx",
                    "launch_kind": "executable",
                },
                resolve_generation_root_fn=lambda resolved_ioc, output_root, resolved_project_path: Path(str(output_root)),
                build_cubemx_script_fn=lambda resolved_ioc, project_name, project_toolchain, generation_root: "project generate\nexit_mx\n",
                regeneration_root_fn=lambda resolved_ioc, output_root, resolved_project_path: Path(str(output_root)),
                collect_tree_state_fn=lambda root: {},
                diff_tree_state_fn=lambda before, after: {"new_files": [], "deleted_files": [], "modified_files": []},
                run_cubemx_command_fn=lambda *args, **kwargs: {
                    "success": True,
                    "exit_code": 0,
                    "stdout": "ok",
                    "stderr": "",
                    "failure_reason": None,
                },
                wait_for_completion_markers_fn=lambda *args, **kwargs: {
                    "success": True,
                    "marker_path": str(marker_path),
                    "status": "created",
                },
                collect_output_review_fn=lambda resolved_ioc, generation_root: {"mismatches": [], "top_level_entries": []},
                collect_build_layout_summary_fn=lambda generation_root: {"generation_root": str(generation_root)},
                build_project_fn=lambda **kwargs: {"success": True, **kwargs},
                create_log_path_fn=lambda prefix: project_root / f"{prefix}.log",
                write_cubemx_log_fn=lambda *args, **kwargs: None,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["build_validation"]["success"], True)
            self.assertEqual(script_path.read_text(encoding="utf-8"), "project generate\nexit_mx\n")

    async def test_debug_question_launches_session_when_missing(self) -> None:
        orchestrate_debug_session_fn = AsyncMock(return_value={"success": True, "workflow": "debug_session"})

        result = await debug_question.orchestrate_debug_question(
            prompt="what is baud rate?",
            session_name="inspect",
            timeout_seconds=30,
            debug_status=lambda **kwargs: {"success": False, "session_name": kwargs.get("session_name")},
            orchestrate_debug_session_fn=orchestrate_debug_session_fn,
            answer_question=lambda **kwargs: {"success": True, "answer": "115200", **kwargs},
        )

        orchestrate_debug_session_fn.assert_awaited_once_with(
            session_name="inspect",
            reset_before_launch=False,
            timeout_seconds=30,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "115200")

    async def test_prompt_router_routes_feature_requests(self) -> None:
        orchestrate_feature_prompt_fn = AsyncMock(return_value={"success": True, "workflow": "feature_delivery"})

        result = await prompt_router.route_prompt(
            prompt="Create a NUCLEO-L476RG project that sends data to PC",
            timeout_seconds=45,
            classify_prompt=routing_service.classify_prompt,
            resolve_prompt_mode=routing_service.resolve_prompt_mode,
            prompt_without_mode_prefix=routing_service.prompt_without_mode_prefix,
            extract_file_path=routing_service.extract_file_path,
            is_debug_question=routing_service.is_debug_question,
            orchestrate_build_then_flash_fn=AsyncMock(),
            build_project=lambda **kwargs: {"success": True, **kwargs},
            orchestrate_feature_prompt_fn=orchestrate_feature_prompt_fn,
            orchestrate_debug_question_fn=AsyncMock(),
            orchestrate_debug_session_fn=AsyncMock(),
            orchestrate_cubemx_regeneration_fn=lambda **kwargs: {"success": True, **kwargs},
            parse_ioc=lambda: {"success": True},
            flash_firmware=AsyncMock(),
            report_host_capabilities=lambda **kwargs: {"success": True, **kwargs},
        )

        orchestrate_feature_prompt_fn.assert_awaited_once_with(
            prompt="Create a NUCLEO-L476RG project that sends data to PC",
            build_timeout_seconds=45,
            flash_timeout_seconds=45,
            cubemx_timeout_seconds=300,
        )
        self.assertEqual(result["selected_domain"], "requirements")
        self.assertEqual(result["resolved_mode"], "firmware-delivery")

    async def test_prompt_router_defaults_agent_development_prompts_to_develop_agent(self) -> None:
        orchestrate_feature_prompt_fn = AsyncMock(return_value={"success": True, "workflow": "feature_delivery"})

        result = await prompt_router.route_prompt(
            prompt="add a new MCP tool for UART VCP detection",
            timeout_seconds=45,
            classify_prompt=routing_service.classify_prompt,
            resolve_prompt_mode=routing_service.resolve_prompt_mode,
            prompt_without_mode_prefix=routing_service.prompt_without_mode_prefix,
            extract_file_path=routing_service.extract_file_path,
            is_debug_question=routing_service.is_debug_question,
            orchestrate_build_then_flash_fn=AsyncMock(),
            build_project=lambda **kwargs: {"success": True, **kwargs},
            orchestrate_feature_prompt_fn=orchestrate_feature_prompt_fn,
            orchestrate_debug_question_fn=AsyncMock(),
            orchestrate_debug_session_fn=AsyncMock(),
            orchestrate_cubemx_regeneration_fn=lambda **kwargs: {"success": True, **kwargs},
            parse_ioc=lambda: {"success": True},
            flash_firmware=AsyncMock(),
            report_host_capabilities=lambda **kwargs: {"success": True, **kwargs},
        )

        orchestrate_feature_prompt_fn.assert_not_awaited()
        self.assertEqual(result["resolved_mode"], "develop-agent")
        self.assertEqual(result["selected_domain"], "develop_agent")
        self.assertIn("MCP server development", result["result"]["message"])

    async def test_prompt_router_test_only_blocks_firmware_generation(self) -> None:
        orchestrate_feature_prompt_fn = AsyncMock(return_value={"success": True, "workflow": "feature_delivery"})

        result = await prompt_router.route_prompt(
            prompt="test-only: Create a NUCLEO-L476RG project that sends data to PC",
            timeout_seconds=45,
            classify_prompt=routing_service.classify_prompt,
            resolve_prompt_mode=routing_service.resolve_prompt_mode,
            prompt_without_mode_prefix=routing_service.prompt_without_mode_prefix,
            extract_file_path=routing_service.extract_file_path,
            is_debug_question=routing_service.is_debug_question,
            orchestrate_build_then_flash_fn=AsyncMock(),
            build_project=lambda **kwargs: {"success": True, **kwargs},
            orchestrate_feature_prompt_fn=orchestrate_feature_prompt_fn,
            orchestrate_debug_question_fn=AsyncMock(),
            orchestrate_debug_session_fn=AsyncMock(),
            orchestrate_cubemx_regeneration_fn=lambda **kwargs: {"success": True, **kwargs},
            parse_ioc=lambda: {"success": True},
            flash_firmware=AsyncMock(),
            report_host_capabilities=lambda **kwargs: {"success": True, **kwargs},
        )

        orchestrate_feature_prompt_fn.assert_not_awaited()
        self.assertEqual(result["resolved_mode"], "test-only")
        self.assertEqual(result["selected_domain"], "requirements")
        self.assertFalse(result["result"]["success"])


if __name__ == "__main__":
    unittest.main()
