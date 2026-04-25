from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stm32cubep_mcp.ioc_builder import server as ioc_builder_server
from stm32cubep_mcp.requirements.policy import derive_execution_policy
from stm32cubep_mcp.requirements import server as requirements_server
from stm32cubep_mcp.requirements_ioc_contract import CONTRACT_VERSION, validate_contract


class RequirementPhase2Tests(unittest.TestCase):
    def test_policy_classifier_distinguishes_strict_build_only_prompt(self) -> None:
        policy = derive_execution_policy("Create a NUCLEO-L476RG project, build only, do not flash, and run and test it later")

        self.assertEqual(policy["ioc_cubemx_validation"], "required")
        self.assertFalse(policy["ask_user_on_repeated_failures"])
        self.assertFalse(policy["flash_after_successful_build"])
        self.assertFalse(policy["runtime_check_after_flash"])

    def test_requirements_decompose_creates_valid_contract_for_uart_prompt(self) -> None:
        prompt = "I have attached STM32L476Rg Nucleo device. write a project that will send data from the device to pc and run and test it"

        with patch(
            "stm32cubep_mcp.requirements.server.shared.load_project_metadata",
            return_value={"data": {"firmware": {"ioc_path": "NUCLEO-L476RG-UART2-printf/NUCLEO-L476RG-UART2-printf.ioc"}}},
        ):
            result = requirements_server.stm32_requirements_decompose(prompt)

        self.assertTrue(result["success"])
        contract = result["contract"]
        self.assertEqual(contract["contract_version"], CONTRACT_VERSION)
        self.assertEqual(contract["target"]["board_id"], "NUCLEO-L476RG")
        self.assertEqual(contract["defaults"]["toolchain"], "STM32CubeIDE")
        self.assertEqual(contract["planning"]["horizon"], "long_horizon")
        self.assertEqual(contract["execution_policy"]["ioc_cubemx_validation"], "required")
        self.assertFalse(contract["execution_policy"]["ask_user_on_repeated_failures"])
        self.assertEqual(contract["core_features"][0]["id"], "core-uart-device-to-pc")
        self.assertEqual(contract["interface_intents"][0]["instance_preference"], "USART2")
        self.assertIn("pluggable-runtime-check", [feature["id"] for feature in contract["pluggable_features"]])
        self.assertEqual(
            Path(contract["plan_file"]),
            (Path.cwd() / "NUCLEO-L476RG-UART2-printf" / "plan.md").resolve(),
        )
        self.assertEqual(validate_contract(contract), [])

    def test_requirements_default_plan_file_follows_ioc_directory(self) -> None:
        with patch(
            "stm32cubep_mcp.requirements.server.shared.load_project_metadata",
            return_value={"data": {"firmware": {"ioc_path": "generated/demo-project/demo.ioc"}}},
        ):
            plan_file = requirements_server.default_plan_file()

        self.assertEqual(Path(plan_file), (Path.cwd() / "generated" / "demo-project" / "plan.md").resolve())

    def test_requirements_decompose_keeps_best_effort_validation_for_non_strict_prompt(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")

        self.assertEqual(contract["execution_policy"]["ioc_cubemx_validation"], "best_effort")
        self.assertTrue(contract["execution_policy"]["ask_user_on_repeated_failures"])

    def test_requirements_decompose_can_disable_flash_for_build_only_prompt(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that sends data to PC but build only and do not flash")

        self.assertFalse(contract["execution_policy"]["flash_after_successful_build"])
        self.assertFalse(contract["execution_policy"]["runtime_check_after_flash"])

    def test_requirements_decompose_persists_plan_artifact(self) -> None:
        prompt = "Create a NUCLEO-L476RG project that will blink the LED and send data to PC"
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            contract = requirements_server.build_requirements_contract(prompt)
            contract["plan_file"] = str(plan_file)

            persisted = requirements_server.persist_plan_artifact(contract)
            self.assertEqual(Path(persisted["plan_path"]), plan_file)
            self.assertTrue(plan_file.is_file())
            persisted_text = plan_file.read_text(encoding="utf-8")
            self.assertIn("# Workflow Plan", persisted_text)
            self.assertIn("## Execution Policy", persisted_text)
            self.assertIn("IOC CubeMX validation: `best_effort`", persisted_text)
            self.assertIn("Ask user on repeated failures: `True`", persisted_text)
            self.assertIn("<!-- plan-state:start -->", persisted_text)

    def test_requirements_persisted_plan_shows_flash_disabled_for_build_only_prompt(self) -> None:
        prompt = "Create a NUCLEO-L476RG project that sends data to PC but build only and do not flash"
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            contract = requirements_server.build_requirements_contract(prompt)
            contract["plan_file"] = str(plan_file)

            requirements_server.persist_plan_artifact(contract)
            persisted_text = plan_file.read_text(encoding="utf-8")

        self.assertIn("Flash after successful build: `False`", persisted_text)
        self.assertIn("Runtime check after flash: `False`", persisted_text)

    def test_requirements_persisted_plan_shows_required_validation_for_strict_prompt(self) -> None:
        prompt = "Create a NUCLEO-L476RG project that sends data to PC and run and test it"
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            contract = requirements_server.build_requirements_contract(prompt)
            contract["plan_file"] = str(plan_file)

            requirements_server.persist_plan_artifact(contract)
            persisted_text = plan_file.read_text(encoding="utf-8")

        self.assertIn("IOC CubeMX validation: `required`", persisted_text)
        self.assertIn("Ask user on repeated failures: `False`", persisted_text)

    def test_requirements_plan_status_reads_live_state_fields(self) -> None:
        prompt = "Create a NUCLEO-L476RG project that will blink the LED and send data to PC"
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            contract = requirements_server.build_requirements_contract(prompt)
            contract["plan_file"] = str(plan_file)
            requirements_server.persist_plan_artifact(contract)
            requirements_server.update_plan_status(
                str(plan_file),
                stage="cubemx",
                status="in_progress",
                message="CubeMX is still running.",
                details={"elapsed_seconds": 12.0},
                append_history=False,
            )

            status = requirements_server.read_plan_status(str(plan_file))

        self.assertTrue(status["success"])
        self.assertEqual(status["current_stage"], "cubemx")
        self.assertEqual(status["current_stage_message"], "CubeMX is still running.")
        self.assertEqual(status["current_stage_details"]["elapsed_seconds"], 12.0)

    def test_update_plan_status_recovers_from_empty_plan_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            plan_file.write_text("", encoding="utf-8")

            result = requirements_server.update_plan_status(
                str(plan_file),
                stage="cubemx",
                status="in_progress",
                message="CubeMX is still running.",
                details={"elapsed_seconds": 4.0},
                append_history=False,
            )

        self.assertEqual(result["plan"]["current_stage"], "cubemx")
        self.assertEqual(result["plan"]["current_stage_details"]["elapsed_seconds"], 4.0)

    def test_read_plan_status_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            plan_file.write_text("# Invalid Plan\n", encoding="utf-8")

            status = requirements_server.read_plan_status(str(plan_file))

        self.assertFalse(status["success"])
        self.assertIn("not valid", status["message"])

    def test_requirements_expand_supported_prompt_families(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED when the button is pressed")

        feature_ids = [feature["id"] for feature in contract["core_features"]]
        pluggable_ids = [feature["id"] for feature in contract["pluggable_features"]]
        intent_ids = [intent["id"] for intent in contract["interface_intents"]]

        self.assertIn("core-led-blink", feature_ids)
        self.assertIn("pluggable-user-button-event", pluggable_ids)
        self.assertIn("iface-led-pa5", intent_ids)
        self.assertIn("iface-button-pc13", intent_ids)

    def test_contract_schema_file_tracks_current_contract_version(self) -> None:
        schema_path = Path("src/stm32cubep_mcp/schemas/requirements-ioc-contract.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(schema["properties"]["contract_version"]["const"], CONTRACT_VERSION)

    def test_ioc_builder_synthesizes_deterministic_uart_change_set(self) -> None:
        prompt = "I have attached STM32L476Rg Nucleo device. write a project that will send data from the device to pc and run and test it"
        contract = requirements_server.build_requirements_contract(prompt)

        result = ioc_builder_server.synthesize_ioc_change_set(contract)

        self.assertTrue(result["success"])
        self.assertEqual(result["builder_strategy"], "seed_plus_mutate")
        self.assertEqual(result["board_profile"], "NUCLEO-L476RG")
        self.assertIn("USART2", result["enabled_peripherals"])
        self.assertIn({"key": "PA2.Signal", "value": "USART2_TX"}, result["ioc_properties"])
        self.assertIn({"key": "PA3.Signal", "value": "USART2_RX"}, result["ioc_properties"])
        self.assertIn({"key": "USART2.BaudRate", "value": 115200}, result["ioc_properties"])
        self.assertEqual(result["mcu_metadata"]["grouped_xml_filename"], "STM32L476R(C-E-G)Tx.xml")

    def test_ioc_builder_synthesizes_led_and_button_change_set(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED when the button is pressed")

        result = ioc_builder_server.synthesize_ioc_change_set(contract)

        self.assertTrue(result["success"])
        self.assertIn({"key": "PA5.Signal", "value": "GPIO_Output"}, result["ioc_properties"])
        self.assertIn({"key": "PC13.Signal", "value": "GPXTI13"}, result["ioc_properties"])
        self.assertIn("PA5", result["used_pins"])
        self.assertIn("PC13", result["used_pins"])

    def test_ioc_builder_apply_updates_ioc_file(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "board.ioc"
            ioc_path.write_text(
                "\n".join([
                    "File.Version=6",
                    "Mcu.Name=STM32L476RGTx",
                    "Mcu.IP0=NVIC",
                    "Mcu.IP1=RCC",
                    "Mcu.IP2=SYS",
                    "Mcu.IPNb=3",
                    "Mcu.Pin0=PA13",
                    "Mcu.Pin1=PA14",
                    "Mcu.PinsNb=2",
                    "ProjectManager.ToolChain=STM32CubeIDE",
                    "ProjectManager.TargetToolchain=STM32CubeIDE",
                ]) + "\n",
                encoding="utf-8",
            )

            with patch("stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx", return_value={"success": True, "validation": "accepted"}):
                result = ioc_builder_server.apply_ioc_change_set(contract, ioc_path=str(ioc_path))
                updated_text = ioc_path.read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertIn("PA2.Signal=USART2_TX", updated_text)
        self.assertIn("PA3.Signal=USART2_RX", updated_text)
        self.assertIn("PA5.Signal=GPIO_Output", updated_text)
        self.assertIn("Mcu.IP3=USART2", updated_text)
        self.assertEqual(result["cubemx_validation"]["validation"], "accepted")

    def test_ioc_builder_construct_creates_reference_seeded_ioc_file(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            with patch("stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx", return_value={"success": True, "validation": "accepted"}):
                result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(ioc_path))
                constructed_text = ioc_path.read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertEqual(result["construction_source"], "reference_ioc")
        self.assertIn("#MicroXplorer Configuration settings - do not modify", constructed_text)
        self.assertIn("board=NUCLEO-L476RG2", constructed_text)
        self.assertIn("boardIOC=true", constructed_text)
        self.assertIn("ProjectManager.ToolChainLocation=Projects", constructed_text)
        self.assertIn("PA2.Signal=USART2_TX", constructed_text)
        self.assertIn("PA3.Signal=USART2_RX", constructed_text)
        self.assertIn("PA5.Signal=GPIO_Output", constructed_text)
        self.assertEqual(result["cubemx_validation"]["validation"], "accepted")

    def test_ioc_builder_construct_fails_when_cubemx_rejects_ioc(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            with patch(
                "stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx",
                return_value={"success": False, "validation": "rejected", "message": "CubeMX rejected the IOC."},
            ):
                result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(ioc_path))

        self.assertFalse(result["success"])
        self.assertEqual(result["cubemx_validation"]["validation"], "rejected")
        self.assertIn("CubeMX rejected", result["message"])

    def test_ioc_builder_construct_fails_when_cubemx_validation_is_required_but_skipped(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        contract["execution_policy"]["ioc_cubemx_validation"] = "required"
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            with patch(
                "stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx",
                return_value={"success": True, "validation": "skipped", "message": "STM32CubeMX was not found."},
            ):
                result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(ioc_path))

        self.assertFalse(result["success"])
        self.assertEqual(result["cubemx_validation"]["validation"], "skipped")
        self.assertIn("required and unavailable", result["message"])

    def test_validate_ioc_with_cubemx_prefers_configured_project_and_script_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "generated" / "NUCLEO-L476RG-UART2-printf" / "NUCLEO-L476RG-UART2-printf.ioc"
            ioc_path.parent.mkdir(parents=True)
            ioc_path.write_text("ProjectManager.ToolChain=STM32CubeIDE\n", encoding="utf-8")
            project_path = ioc_path.parent
            script_path = project_path / "script.txt"

            with patch(
                "stm32cubep_mcp.ioc_builder.ioc_validate.cubemx_server.resolve_cubemx_launcher",
                return_value={"tool_path": "C:/stm/STM32CubeMX.exe", "launch_kind": "executable"},
            ):
                with patch(
                    "stm32cubep_mcp.ioc_builder.ioc_validate.cubemx_server.resolve_cubemx_project_inputs",
                    return_value={
                        "project_path": str(project_path),
                        "script_path": str(script_path),
                    },
                ):
                    with patch(
                        "stm32cubep_mcp.ioc_builder.ioc_validate.cubemx_server.regenerate_project_internal",
                        return_value={"success": True, "message": "ok"},
                    ) as regenerate_project_internal:
                        result = ioc_builder_server.validate_ioc_with_cubemx(
                            str(ioc_path),
                            project_name="NUCLEO-L476RG-UART2-printf",
                            project_toolchain="STM32CubeIDE",
                        )

        self.assertTrue(result["success"])
        regenerate_project_internal.assert_called_once()
        self.assertEqual(regenerate_project_internal.call_args.kwargs["project_path"], str(project_path))
        self.assertEqual(regenerate_project_internal.call_args.kwargs["script_path"], str(script_path))

    def test_contract_validation_rejects_unknown_cubemx_validation_policy(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that sends data to PC")
        contract["execution_policy"]["ioc_cubemx_validation"] = "sometimes"

        errors = validate_contract(contract)

        self.assertIn("execution_policy.ioc_cubemx_validation must be 'best_effort' or 'required'.", errors)

    def test_ioc_builder_rejects_invalid_contract(self) -> None:
        result = ioc_builder_server.synthesize_ioc_change_set({"contract_version": "wrong"})

        self.assertFalse(result["success"])
        self.assertTrue(result["validation_errors"])