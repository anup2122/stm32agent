from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from stm32cubep_mcp import shared
from stm32cubep_mcp.application.services import project_config_service
from stm32cubep_mcp.application.workflows import live_debug
from stm32cubep_mcp.cube_programmer import server as programmer_server


class RuntimeDefaultsLoaderTests(unittest.TestCase):
    def test_load_runtime_defaults_accepts_jsonc_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "stm32-runtime-defaults.jsonc"
            config_path.write_text(
                """{
    // Runtime defaults used by tests.
    \"version\": 1,
    \"debug\": {
        \"default_session_name\": \"configured-session\"
    }
}
""",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"STM32_RUNTIME_DEFAULTS_JSON": str(config_path)}, clear=False):
                result = shared.load_runtime_defaults()

        self.assertEqual(result["status"], "loaded")
        self.assertEqual(result["data"]["debug"]["default_session_name"], "configured-session")


class RuntimeDefaultsConsumerTests(unittest.TestCase):
    def test_project_config_service_uses_runtime_project_defaults(self) -> None:
        contract = {
            "target": {"board_id": "NUCLEO-L476RG"},
            "core_features": [{"id": "custom-uart-feature"}],
        }

        with patch(
            "stm32cubep_mcp.application.services.project_config_service.shared.load_runtime_defaults",
            return_value={
                "data": {
                    "project": {
                        "uart_core_feature_id": "custom-uart-feature",
                        "generated_projects_dir": "out",
                    }
                }
            },
        ):
            project_name = project_config_service.inferred_project_name(contract)
            paths = project_config_service.derived_project_paths("demo-app", cwd=Path("C:/repo"))

        self.assertEqual(project_name, "NUCLEO-L476RG-UART2-printf")
        self.assertEqual(paths["ioc_path"], "out/demo-app/demo-app.ioc")

    def test_programmer_helpers_use_runtime_defaults(self) -> None:
        with patch(
            "stm32cubep_mcp.cube_programmer.server.shared.load_runtime_defaults",
            return_value={
                "data": {
                    "programmer": {
                        "llm_recovery_max_attempts": 4,
                        "recovery_text_limit": 5,
                        "programmer_version_timeout_cap_seconds": 9,
                        "runtime_check_timeout_cap_seconds": 11,
                    }
                }
            },
        ):
            self.assertEqual(programmer_server.llm_recovery_max_attempts(), 4)
            self.assertEqual(programmer_server.programmer_version_timeout_cap_seconds(), 9)
            self.assertEqual(programmer_server.runtime_check_timeout_cap_seconds(), 11)
            self.assertEqual(programmer_server.truncate_recovery_text("abcdef"), "abcde\n...[truncated]")


class LiveDebugRuntimeDefaultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_validation_stage_uses_runtime_defaults(self) -> None:
        stop_calls: list[dict[str, object]] = []
        orchestrate_debug_session_fn = AsyncMock(return_value={"success": True, "workflow": "debug_session"})

        with patch(
            "stm32cubep_mcp.application.workflows.live_debug.shared.load_runtime_defaults",
            return_value={
                "data": {
                    "debug": {
                        "runtime_validation_session_name": "configured-runtime-session",
                        "reset_timeout_cap_seconds": 25,
                        "cleanup_timeout_seconds": 7,
                    }
                }
            },
        ):
            result = await live_debug.run_runtime_validation_stage(
                plan_file=None,
                increment_id=None,
                flash_timeout_seconds=120,
                update_plan_status=lambda *args, **kwargs: {"success": True},
                orchestrate_debug_session_fn=orchestrate_debug_session_fn,
                stop_debug_session_fn=lambda **kwargs: stop_calls.append(kwargs) or {"success": True, "operation": "stop"},
            )

        self.assertTrue(result["success"])
        self.assertEqual(orchestrate_debug_session_fn.await_args.kwargs["session_name"], "configured-runtime-session")
        self.assertEqual(orchestrate_debug_session_fn.await_args.kwargs["timeout_seconds"], 25)
        self.assertEqual(stop_calls[0]["session_name"], "configured-runtime-session")
        self.assertEqual(stop_calls[0]["timeout_seconds"], 7)