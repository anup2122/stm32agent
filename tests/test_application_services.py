from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from stm32cubep_mcp.application.services import artifact_service, project_config_service, routing_service
from stm32cubep_mcp.application.workflows import cubemx_regeneration, debug_question, prompt_router


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


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
