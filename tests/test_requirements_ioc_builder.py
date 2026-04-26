from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stm32cubep_mcp.application.services import workflow_state
from stm32cubep_mcp.ioc_builder import server as ioc_builder_server
from stm32cubep_mcp.requirements.policy import derive_execution_policy
from stm32cubep_mcp.requirements import server as requirements_server
from stm32cubep_mcp.requirements_ioc_contract import CONTRACT_VERSION, validate_contract


class RequirementPhase2Tests(unittest.TestCase):
    def sample_base_ioc_text(self) -> str:
        return "\n".join([
            "#MicroXplorer Configuration settings - do not modify",
            "File.Version=6",
            "Mcu.Name=STM32L476RGTx",
            "Mcu.Package=LQFP64",
            "ProjectManager.ToolChain=STM32CubeIDE",
            "ProjectManager.TargetToolchain=STM32CubeIDE",
            "Mcu.IP0=NVIC",
            "Mcu.IP1=RCC",
            "Mcu.IP2=SYS",
            "Mcu.IPNb=3",
            "Mcu.Pin0=PA13",
            "Mcu.Pin1=PA14",
            "Mcu.PinsNb=2",
            "",
        ])

    def sample_l476_tim1_index(self) -> dict[str, object]:
        return {
            "mcu_catalog": {
                "STM32L476R(C-E-G)Tx": {
                    "refname": "STM32L476R(C-E-G)Tx",
                    "family": "STM32L4",
                    "line": "STM32L4x6",
                    "package": "LQFP64",
                    "ips": ["RCC", "SYS", "NVIC", "TIM1", "USART2", "DMA"],
                    "pin_signals": {
                        "PA10": ["TIM1_CH3"],
                        "PB1": ["TIM1_CH3N"],
                        "PB15": ["TIM1_CH3N"],
                    },
                    "signal_pins": {
                        "TIM1_CH3": ["PA10"],
                        "TIM1_CH3N": ["PB1", "PB15"],
                    },
                }
            },
            "family_config_index": {
                "STM32L4xx": ["TIM-STM32L4xx_Configs.xml", "DMA-STM32L4xx_Configs.xml"],
            },
            "dma_ll_mapping": {
                "STM32L4xx": [
                    {"Value": "DMA_REQUEST_TIM1_UP"},
                    {"Value": "DMA_REQUEST_TIM1_CH3"},
                ]
            },
        }

    def test_policy_classifier_distinguishes_strict_build_only_prompt(self) -> None:
        policy = derive_execution_policy("Create a NUCLEO-L476RG project, build only, do not flash, and run and test it later")

        self.assertEqual(policy["ioc_cubemx_validation"], "required")
        self.assertNotIn("ask_user_on_repeated_failures", policy)
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
        self.assertEqual(contract["planning"]["increment_strategy"], "feature_by_feature")
        self.assertEqual(contract["execution_policy"]["ioc_cubemx_validation"], "required")
        self.assertTrue(contract["execution_policy"]["ask_user_on_repeated_failures"])
        self.assertEqual(contract["project_context"]["kind"], "new_device")
        self.assertEqual(contract["project_context"]["ioc_handling"], "download_from_github")
        self.assertEqual(contract["core_features"][0]["id"], "core-uart-device-to-pc")
        self.assertEqual(contract["increments"][0]["id"], "increment-core-001")
        self.assertEqual(contract["interface_intents"][0]["instance_preference"], "USART2")
        self.assertIn("pluggable-runtime-check", [feature["id"] for feature in contract["pluggable_features"]])
        self.assertEqual(Path(contract["plan_file"]), (Path.cwd() / "generated" / "plan.md").resolve())
        self.assertEqual(validate_contract(contract), [])

    def test_requirements_detect_existing_project_context_from_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_ioc = Path(temp_dir) / "existing" / "board.ioc"
            source_ioc.parent.mkdir(parents=True)
            source_ioc.write_text(self.sample_base_ioc_text(), encoding="utf-8")

            with patch(
                "stm32cubep_mcp.requirements.server.shared.load_project_metadata",
                return_value={"data": {"board": {"name": "NUCLEO-L476RG", "mcu": "STM32L476RGTx"}, "firmware": {"ioc_path": str(source_ioc)}}},
            ):
                contract = requirements_server.build_requirements_contract("Update the current project to blink the LED")

        self.assertEqual(contract["project_context"]["kind"], "existing_project")
        self.assertEqual(contract["project_context"]["ioc_handling"], "copy_existing_ioc")
        self.assertEqual(contract["project_context"]["configured_source_ioc_path"], str(source_ioc.resolve()))

    def test_requirements_default_plan_file_follows_ioc_directory(self) -> None:
        with patch(
            "stm32cubep_mcp.requirements.server.shared.load_project_metadata",
            return_value={"data": {"firmware": {"ioc_path": "generated/demo-project/demo.ioc"}}},
        ):
            plan_file = requirements_server.default_plan_file()

        self.assertEqual(Path(plan_file), (Path.cwd() / "generated" / "demo-project" / "plan.md").resolve())

    def test_requirements_detect_target_can_fall_back_to_project_metadata(self) -> None:
        with patch(
            "stm32cubep_mcp.requirements.server.shared.load_project_metadata",
            return_value={"data": {"board": {"name": "NUCLEO-L476RG", "mcu": "STM32L476RGTx"}}},
        ):
            board_id, mcu = requirements_server.detect_target("Update the current project to blink the LED")

        self.assertEqual(board_id, "NUCLEO-L476RG")
        self.assertEqual(mcu, "STM32L476RGTx")

    def test_requirements_engineering_spec_defaults_to_new_project_context(self) -> None:
        with patch(
            "stm32cubep_mcp.requirements.server.shared.load_project_metadata",
            return_value={"data": {"firmware": {"ioc_path": "generated/existing/existing.ioc"}}},
        ):
            context = requirements_server.detect_project_context(
                "This project has to be tested with NUCLEO-L476RG Rev C. The objective is to configure TIM1 PWM with DMA."
            )

        self.assertEqual(context["kind"], "new_project")
        self.assertEqual(context["ioc_handling"], "download_from_github")

    def test_requirements_decompose_keeps_best_effort_validation_for_non_strict_prompt(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")

        self.assertEqual(contract["execution_policy"]["ioc_cubemx_validation"], "best_effort")
        self.assertTrue(contract["execution_policy"]["ask_user_on_repeated_failures"])

    def test_requirements_decompose_fails_cleanly_for_unsupported_complex_pwm_dma_prompt(self) -> None:
        prompt = (
            "This project has to be tested with NUCLEO-L476RG Rev C. "
            "The objective is to configure TIM1 channel 3 complementary PWM with DMA updating CCR3 at 80 MHz."
        )
        result = requirements_server.stm32_requirements_decompose(prompt, persist_plan=False)

        self.assertTrue(result["success"])
        self.assertEqual(result["contract"]["project_context"]["kind"], "new_project")
        self.assertEqual(
            [increment["feature_ids"] for increment in result["contract"]["increments"]],
            [["core-clock-80000000"], ["core-tim1-ch3-complementary-pwm"], ["pluggable-tim1-ccr3-dma-update"]],
        )
        self.assertCountEqual(
            result["contract"]["intent_metadata"]["engineering_spec"]["prompt_hints"],
            ["TIM1", "PWM", "DMA"],
        )

    def test_requirements_decompose_does_not_confuse_displayed_with_led_feature(self) -> None:
        prompt = (
            "Write a program for NUCLEO-L476RG Rev C that configures TIM1 channel 3 complementary PWM with DMA, "
            "and note that the PWM waveform can be displayed using an oscilloscope."
        )
        result = requirements_server.stm32_requirements_decompose(prompt, persist_plan=False)

        self.assertTrue(result["success"])
        self.assertIn("core-tim1-ch3-complementary-pwm", [feature["id"] for feature in result["contract"]["core_features"]])
        self.assertNotIn("core-led-blink", [feature["id"] for feature in result["contract"]["core_features"]])

    def test_requirements_decompose_breaks_wwdg_prompt_into_core_and_pluggable_increments(self) -> None:
        prompt = (
            "Write a program for NUCLEO-L476RG Rev C with SystemClock configured to 80 MHz. "
            "Configure the WWDG so it is refreshed every 20 ms, LED2 toggles while running, "
            "and pressing the user push-button on PC.13 triggers an EXTI fault path. "
            "Where required for testing send messages to host over uart using stm32 vcp. "
            "This example must be tested in standalone mode and not in debug."
        )

        result = requirements_server.stm32_requirements_decompose(prompt, persist_plan=False)

        self.assertTrue(result["success"])
        self.assertEqual(
            [increment["feature_ids"] for increment in result["contract"]["increments"]],
            [
                ["core-clock-80000000"],
                ["core-led2-status-output"],
                ["core-wwdg-supervision"],
                ["pluggable-user-button-fault-trigger"],
                ["pluggable-host-debug-uart"],
            ],
        )
        intent_ids = [intent["id"] for intent in result["contract"]["interface_intents"]]
        self.assertIn("iface-wwdg-supervision", intent_ids)
        self.assertIn("iface-button-pc13", intent_ids)
        self.assertIn("iface-host-debug-uart", intent_ids)

    def test_requirements_decompose_breaks_rtc_alarm_prompt_into_core_and_pluggable_increments(self) -> None:
        prompt = (
            "Write a program with below requirements, build the program, download it to attached device and test it when possible. "
            "Where requried for testing send messages from device to host over uart and read them on Host side using stm32 vcp. "
            "This project has to be tested with NUCLEO-L476RG Rev C and the clock is set to 80 MHz. "
            "Configuration and generation of an RTC alarm using the RTC HAL API. "
            "The Time is set to 02:20:00 and the Alarm must be generated after 30 seconds on 02:20:30. "
            "LED2 is turned ON when the RTC Alarm is generated correctly. In case of error, LED2 is toggled with a period of one second."
        )

        result = requirements_server.stm32_requirements_decompose(prompt, persist_plan=False)

        self.assertTrue(result["success"])
        self.assertEqual(
            [increment["feature_ids"] for increment in result["contract"]["increments"]],
            [
                ["core-clock-80000000"],
                ["core-led2-status-output"],
                ["core-rtc-alarm"],
                ["pluggable-host-debug-uart"],
            ],
        )
        intent_by_id = {intent["id"]: intent for intent in result["contract"]["interface_intents"]}
        self.assertIn("iface-rtc-alarm-a", intent_by_id)
        self.assertEqual(intent_by_id["iface-rtc-alarm-a"]["clock_source"], "LSI")
        self.assertEqual(intent_by_id["iface-rtc-alarm-a"]["initial_time_hms"], (2, 20, 0))
        self.assertEqual(intent_by_id["iface-rtc-alarm-a"]["alarm_time_hms"], (2, 20, 30))
        self.assertEqual(intent_by_id["iface-rtc-alarm-a"]["alarm_after_seconds"], 30)
        self.assertIn("iface-host-debug-uart", intent_by_id)

    def test_ioc_builder_can_construct_baseline_for_clock_only_engineering_spec_prompt(self) -> None:
        prompt = (
            "This project has to be tested with NUCLEO-L476RG Rev C and SystemCoreClock is set to 80 MHz."
        )
        contract = requirements_server.build_requirements_contract(prompt)
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "generic-spec.ioc"

            with patch(
                "stm32cubep_mcp.ioc_builder.server.load_local_board_ioc_lines",
                return_value={
                    "success": True,
                    "match": {"board_id": "NUCLEO-L476RG", "ioc_filename": "B40_Nucleo_NUCLEO-L476RG_STM32L476RG_Board_AllConfig.ioc"},
                    "ioc_path": str((Path(temp_dir) / "local-board.ioc").resolve()),
                    "lines": self.sample_base_ioc_text().splitlines(),
                },
            ):
                with patch("stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx", return_value={"success": True, "validation": "accepted"}):
                    result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(ioc_path))
                    constructed_text = ioc_path.read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertEqual(result["construction_source"], "local_board_ioc")
        self.assertIn("ProjectManager.ProjectFileName=generic-spec.ioc", constructed_text)
        self.assertIn("ProjectManager.ProjectName=generic-spec", constructed_text)
        self.assertNotIn("PA5.Signal=GPIO_Output", constructed_text)
        self.assertNotIn("PA2.Signal=USART2_TX", constructed_text)

    def test_ioc_builder_compiles_timer_core_increment_and_dma_increment(self) -> None:
        prompt = (
            "This project has to be tested with NUCLEO-L476RG Rev C. "
            "The objective is to configure TIM1 channel 3 complementary PWM with DMA updating CCR3 at 80 MHz."
        )
        contract = requirements_server.build_requirements_contract(prompt)
        timer_increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][1])
        dma_increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][2])

        with patch(
            "stm32cubep_mcp.ioc_builder.st_mcu_catalog.local_cubemx_db_index",
            return_value=self.sample_l476_tim1_index(),
        ):
            timer_result = ioc_builder_server.synthesize_ioc_change_set(timer_increment_contract)
            dma_result = ioc_builder_server.synthesize_ioc_change_set(dma_increment_contract)

        self.assertTrue(timer_result["success"])
        self.assertIn({"key": "TIM1.Channel-PWM Generation3 CH3 CH3N", "value": "TIM_CHANNEL_3"}, timer_result["ioc_properties"])
        self.assertTrue(dma_result["success"])
        self.assertIn({"key": "Dma.Request0", "value": "TIM1_CH3"}, dma_result["ioc_properties"])
        self.assertIn({"key": "Dma.TIM1_CH3.0.Instance", "value": "DMA1_Channel7"}, dma_result["ioc_properties"])
        self.assertIn(
            {"key": "NVIC.DMA1_Channel7_IRQn", "value": "true\\:0\\:0\\:false\\:false\\:true\\:false\\:true"},
            dma_result["ioc_properties"],
        )

    def test_ioc_builder_compiles_wwdg_increment(self) -> None:
        prompt = (
            "Write a program for NUCLEO-L476RG Rev C with SystemClock configured to 80 MHz. "
            "Configure the WWDG so it is refreshed every 20 ms and resets after the counter falls to 0x3F. "
            "LED2 is toggling while running and this example must be tested in standalone mode."
        )
        contract = requirements_server.build_requirements_contract(prompt)
        wwdg_increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][2])

        with patch(
            "stm32cubep_mcp.ioc_builder.st_mcu_catalog.local_cubemx_db_index",
            return_value={"mcu_catalog": {}, "family_config_index": {}, "dma_ll_mapping": {}},
        ):
            result = ioc_builder_server.synthesize_ioc_change_set(wwdg_increment_contract)

        self.assertTrue(result["success"])
        self.assertIn("WWDG", result["enabled_peripherals"])
        self.assertIn("VP_WWDG_VS_WWDG", result["used_pins"])
        self.assertIn({"key": "VP_WWDG_VS_WWDG.Signal", "value": "WWDG_VS_WWDG"}, result["ioc_properties"])
        self.assertIn({"key": "VP_WWDG_VS_WWDG.Mode", "value": "WWDG_Activate"}, result["ioc_properties"])
        self.assertTrue(
            any(
                item["key"] == "WWDG.Prescaler" and str(item["value"]).startswith("WWDG_PRESCALER_")
                for item in result["ioc_properties"]
            )
        )
        self.assertTrue(any(item["key"] == "WWDG.Counter" for item in result["ioc_properties"]))
        self.assertTrue(any(item["key"] == "WWDG.Window" for item in result["ioc_properties"]))
        self.assertIn({"key": "WWDG.EWIMode", "value": "WWDG_EWI_DISABLE"}, result["ioc_properties"])

    def test_requirements_extracts_dma_target_from_timx_ccr_notation(self) -> None:
        prompt = (
            "Use DMA with TIMER Update request to transfer data from memory to TIMER Capture Compare Register 3 (TIMx_CCR3). "
            "This project has to be tested with NUCLEO-L476RG Rev C and configure TIM1 channel 3 PWM."
        )

        contract = requirements_server.build_requirements_contract(prompt)

        dma_feature = next(feature for feature in contract["pluggable_features"] if feature["id"].startswith("pluggable-tim1-ccr"))
        self.assertEqual(dma_feature["id"], "pluggable-tim1-ccr3-dma-update")

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
        self.assertIn("Ask user on repeated failures: `True`", persisted_text)

    def test_requirements_builds_core_then_pluggable_increment_queue(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Create a NUCLEO-L476RG project that blinks the LED, sends data to PC, and reacts to the user button"
        )

        increment_ids = [increment["id"] for increment in contract["increments"]]
        increment_feature_ids = [increment["feature_ids"] for increment in contract["increments"]]

        self.assertEqual(
            increment_ids,
            ["increment-core-001", "increment-core-002", "increment-pluggable-001"],
        )
        self.assertEqual(
            increment_feature_ids,
            [["core-led-blink"], ["core-uart-device-to-pc"], ["pluggable-user-button-event"]],
        )
        self.assertEqual(contract["current_increment"]["id"], "increment-core-001")

    def test_requirements_plan_artifact_preserves_completed_increment_progress_on_refresh(self) -> None:
        prompt = "Create a NUCLEO-L476RG project that blinks the LED and sends data to PC"
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            contract = requirements_server.build_requirements_contract(prompt)
            contract["plan_file"] = str(plan_file)

            first_persist = requirements_server.persist_plan_artifact(contract)
            requirements_server.update_plan_status(
                str(plan_file),
                stage="increment",
                status="completed",
                message="The first increment completed.",
                increment_id="increment-core-001",
            )

            refreshed = requirements_server.persist_plan_artifact(contract)

        first_plan = first_persist["plan"]
        refreshed_plan = refreshed["plan"]
        self.assertEqual(first_plan["active_increment_id"], "increment-core-001")
        self.assertIn("increment-core-001", refreshed_plan["completed_increment_ids"])
        self.assertEqual(refreshed_plan["active_increment_id"], "increment-core-002")

    def test_requirements_plan_requests_user_review_after_repeated_failures(self) -> None:
        prompt = "Create a NUCLEO-L476RG project that sends data to PC"
        with tempfile.TemporaryDirectory() as temp_dir:
            plan_file = Path(temp_dir) / "plan.md"
            contract = requirements_server.build_requirements_contract(prompt)
            contract["plan_file"] = str(plan_file)
            requirements_server.persist_plan_artifact(contract)

            requirements_server.update_plan_status(
                str(plan_file),
                stage="build",
                status="failed",
                message="First build failed.",
                increment_id="increment-core-001",
            )
            result = requirements_server.update_plan_status(
                str(plan_file),
                stage="build",
                status="failed",
                message="Second build failed.",
                increment_id="increment-core-001",
            )

        self.assertTrue(result["plan"]["needs_user_review"])
        self.assertEqual(result["plan"]["workflow_status"], "needs_user_review")
        self.assertIn("Review the plan file", result["plan"]["review_request_reason"])

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
        self.assertIn({"key": "NVIC.EXTI15_10_IRQn", "value": "true\\:0\\:0\\:false\\:false\\:true\\:true\\:true"}, result["ioc_properties"])
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

    def test_ioc_builder_construct_prefers_local_board_ioc_for_new_project(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            with patch(
                "stm32cubep_mcp.ioc_builder.server.load_local_board_ioc_lines",
                return_value={
                    "success": True,
                    "match": {"board_id": "NUCLEO-L476RG", "ioc_filename": "B40_Nucleo_NUCLEO-L476RG_STM32L476RG_Board_AllConfig.ioc"},
                    "ioc_path": str((Path(temp_dir) / "local-board.ioc").resolve()),
                    "lines": self.sample_base_ioc_text().splitlines(),
                },
            ) as load_local_board_ioc_lines:
                with patch(
                    "stm32cubep_mcp.ioc_builder.server.download_github_ioc_lines",
                    return_value={
                        "success": True,
                        "match": {"name": "B40_Nucleo_NUCLEO-L476RG_STM32L476RG_Board_AllConfig.ioc"},
                        "lines": self.sample_base_ioc_text().splitlines(),
                    },
                ) as download_github_ioc_lines:
                    with patch("stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx", return_value={"success": True, "validation": "accepted"}):
                        result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(ioc_path))
                        constructed_text = ioc_path.read_text(encoding="utf-8")

        load_local_board_ioc_lines.assert_called_once()
        download_github_ioc_lines.assert_not_called()
        self.assertTrue(result["success"])
        self.assertEqual(result["construction_source"], "local_board_ioc")
        self.assertIn("ProjectManager.ProjectFileName=constructed.ioc", constructed_text)
        self.assertIn("ProjectManager.ProjectName=constructed", constructed_text)
        self.assertNotIn("ProjectManager.ToolChainLocation=", constructed_text)
        self.assertIn("PA2.Signal=USART2_TX", constructed_text)
        self.assertIn("PA3.Signal=USART2_RX", constructed_text)
        self.assertIn("PA5.Signal=GPIO_Output", constructed_text)
        self.assertEqual(result["cubemx_validation"]["validation"], "accepted")

    def test_ioc_builder_construct_falls_back_to_github_when_local_board_ioc_is_unavailable(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            with patch(
                "stm32cubep_mcp.ioc_builder.server.load_local_board_ioc_lines",
                return_value={"success": False, "message": "local board baseline unavailable"},
            ) as load_local_board_ioc_lines:
                with patch(
                    "stm32cubep_mcp.ioc_builder.server.download_github_ioc_lines",
                    return_value={
                        "success": True,
                        "match": {"name": "B40_Nucleo_NUCLEO-L476RG_STM32L476RG_Board_AllConfig.ioc"},
                        "lines": self.sample_base_ioc_text().splitlines(),
                    },
                ) as download_github_ioc_lines:
                    with patch("stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx", return_value={"success": True, "validation": "accepted"}):
                        result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(ioc_path))
                        constructed_text = ioc_path.read_text(encoding="utf-8")

        load_local_board_ioc_lines.assert_called_once()
        download_github_ioc_lines.assert_called_once()
        self.assertTrue(result["success"])
        self.assertEqual(result["construction_source"], "github_board_ioc")
        self.assertIn("ProjectManager.ProjectFileName=constructed.ioc", constructed_text)
        self.assertIn("ProjectManager.ProjectName=constructed", constructed_text)
        self.assertNotIn("ProjectManager.ToolChainLocation=", constructed_text)
        self.assertIn("PA2.Signal=USART2_TX", constructed_text)
        self.assertIn("PA3.Signal=USART2_RX", constructed_text)
        self.assertIn("PA5.Signal=GPIO_Output", constructed_text)
        self.assertEqual(result["cubemx_validation"]["validation"], "accepted")

    def test_ioc_builder_construct_copies_existing_ioc_for_running_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_ioc = Path(temp_dir) / "source" / "existing.ioc"
            source_ioc.parent.mkdir(parents=True)
            source_ioc.write_text(self.sample_base_ioc_text(), encoding="utf-8")
            target_ioc = Path(temp_dir) / "managed" / "copied.ioc"

            with patch(
                "stm32cubep_mcp.requirements.server.shared.load_project_metadata",
                return_value={"data": {"board": {"name": "NUCLEO-L476RG", "mcu": "STM32L476RGTx"}, "firmware": {"ioc_path": str(source_ioc)}}},
            ):
                contract = requirements_server.build_requirements_contract("Update the current project to blink the LED and send data to PC")

            with patch("stm32cubep_mcp.ioc_builder.server.validate_ioc_with_cubemx", return_value={"success": True, "validation": "accepted"}):
                result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(target_ioc), source_ioc_path=str(source_ioc))
                constructed_text = target_ioc.read_text(encoding="utf-8")

        self.assertTrue(result["success"])
        self.assertEqual(result["construction_source"], "existing_ioc_copy")
        self.assertEqual(result["base_ioc"]["source_ioc_path"], str(source_ioc.resolve()))
        self.assertIn("ProjectManager.ProjectFileName=copied.ioc", constructed_text)
        self.assertIn("PA2.Signal=USART2_TX", constructed_text)
        self.assertIn("PA3.Signal=USART2_RX", constructed_text)
        self.assertIn("PA5.Signal=GPIO_Output", constructed_text)

    def test_ioc_builder_construct_fails_when_github_ioc_lookup_fails(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            with patch(
                "stm32cubep_mcp.ioc_builder.server.load_local_board_ioc_lines",
                return_value={"success": False, "message": "local board baseline unavailable"},
            ):
                with patch(
                    "stm32cubep_mcp.ioc_builder.server.download_github_ioc_lines",
                    return_value={"success": False, "message": "lookup failed"},
                ):
                    result = ioc_builder_server.construct_ioc_file(contract, ioc_path=str(ioc_path))

        self.assertFalse(result["success"])
        self.assertIn("lookup failed", result["message"])

    def test_ioc_builder_construct_fails_when_cubemx_rejects_ioc(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that blinks the LED and sends data to PC")
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "constructed.ioc"

            with patch(
                "stm32cubep_mcp.ioc_builder.server.load_local_board_ioc_lines",
                return_value={"success": False, "message": "local board baseline unavailable"},
            ):
                with patch(
                    "stm32cubep_mcp.ioc_builder.server.download_github_ioc_lines",
                    return_value={
                        "success": True,
                        "match": {"name": "B40_Nucleo_NUCLEO-L476RG_STM32L476RG_Board_AllConfig.ioc"},
                        "lines": self.sample_base_ioc_text().splitlines(),
                    },
                ):
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
                "stm32cubep_mcp.ioc_builder.server.load_local_board_ioc_lines",
                return_value={"success": False, "message": "local board baseline unavailable"},
            ):
                with patch(
                    "stm32cubep_mcp.ioc_builder.server.download_github_ioc_lines",
                    return_value={
                        "success": True,
                        "match": {"name": "B40_Nucleo_NUCLEO-L476RG_STM32L476RG_Board_AllConfig.ioc"},
                        "lines": self.sample_base_ioc_text().splitlines(),
                    },
                ):
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
