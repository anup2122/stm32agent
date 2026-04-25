from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stm32cubep_mcp.application.services import plan_service
from stm32cubep_mcp.project_model import (
    legacy_artifact_from_plan_state,
    plan_state_from_legacy_artifact,
    project_state_from_project_metadata,
)
from stm32cubep_mcp.requirements import server as requirements_server


class PlanServiceModelTests(unittest.TestCase):
    def test_plan_state_round_trip_preserves_increment_status_fields(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Create a NUCLEO-L476RG project that blinks the LED and sends data to PC"
        )
        artifact = plan_service.initial_plan_artifact(contract)
        artifact["active_increment_id"] = "increment-core-002"
        artifact["completed_increment_ids"] = ["increment-core-001"]
        artifact["failed_increment_ids"] = []
        artifact["increments"][0]["status"] = "completed"
        artifact["increments"][1]["status"] = "in_progress"
        artifact["current_stage"] = "build"

        state = plan_state_from_legacy_artifact(artifact)
        round_trip = legacy_artifact_from_plan_state(state)

        self.assertEqual(round_trip["active_increment_id"], "increment-core-002")
        self.assertEqual(round_trip["completed_increment_ids"], ["increment-core-001"])
        self.assertEqual(round_trip["increments"][0]["status"], "completed")
        self.assertEqual(round_trip["increments"][1]["status"], "in_progress")
        self.assertEqual(round_trip["current_stage"], "build")

    def test_plan_service_markdown_round_trip_uses_embedded_state(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Create a NUCLEO-L476RG project that sends data to PC and run and test it"
        )
        artifact = plan_service.initial_plan_artifact(contract)
        artifact["current_stage"] = "cubemx"
        artifact["current_stage_message"] = "CubeMX generation is in progress."

        markdown = plan_service.render_plan_markdown(artifact)
        parsed = plan_service.parse_plan_markdown(markdown)

        self.assertEqual(parsed["current_stage"], "cubemx")
        self.assertEqual(parsed["current_stage_message"], "CubeMX generation is in progress.")
        self.assertIn("<!-- plan-state:start -->", markdown)

    def test_plan_service_persist_and_read_status_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            contract = requirements_server.build_requirements_contract(
                "Create a NUCLEO-L476RG project that blinks the LED and sends data to PC"
            )
            contract["plan_file"] = str(plan_file)

            plan_service.persist_plan_artifact(contract)
            plan_service.update_plan_status(
                str(plan_file),
                stage="build",
                status="in_progress",
                message="CubeIDE build is running.",
                details={"configuration": "Debug"},
                increment_id="increment-core-001",
                append_history=False,
            )
            status = plan_service.read_plan_status(str(plan_file))

        self.assertTrue(status["success"])
        self.assertEqual(status["current_stage"], "build")
        self.assertEqual(status["current_stage_details"]["configuration"], "Debug")
        self.assertEqual(status["active_increment_id"], "increment-core-001")

    def test_project_state_adapter_extracts_current_metadata_fields(self) -> None:
        project_metadata = {
            "data": {
                "project_name": "demo-project",
                "project_toolchain": "STM32CubeIDE",
                "build_system": "cubeide",
                "default_configuration": "Debug",
                "board": {
                    "name": "NUCLEO-L476RG",
                    "mcu": "STM32L476RG",
                },
                "firmware": {
                    "ioc_path": "generated/demo-project/demo-project.ioc",
                    "default_artifact": "generated/demo-project/STM32CubeIDE/Debug/demo-project.elf",
                },
                "cubemx": {
                    "project_path": "generated/demo-project",
                    "script_path": "generated/demo-project/script.txt",
                },
                "build": {
                    "project_path": "generated/demo-project/STM32CubeIDE",
                    "workspace": "generated/.cubeide-workspace",
                    "artifact": "generated/demo-project/STM32CubeIDE/Debug/demo-project.elf",
                },
            }
        }

        state = project_state_from_project_metadata(project_metadata)

        self.assertEqual(state.project_name, "demo-project")
        self.assertEqual(state.board_id, "NUCLEO-L476RG")
        self.assertEqual(state.mcu, "STM32L476RG")
        self.assertEqual(state.ioc_path, "generated/demo-project/demo-project.ioc")
        self.assertEqual(state.cubeide_project_path, "generated/demo-project/STM32CubeIDE")
        self.assertEqual(state.build_artifact_path, "generated/demo-project/STM32CubeIDE/Debug/demo-project.elf")


if __name__ == "__main__":
    unittest.main()
