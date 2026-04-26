from __future__ import annotations

import unittest
from unittest.mock import patch

from stm32cubep_mcp.ioc import compiler as ioc_compiler
from stm32cubep_mcp.ioc import mutator as ioc_mutator
from stm32cubep_mcp.application.services import workflow_state
from stm32cubep_mcp.project_model import IocOperation
from stm32cubep_mcp.requirements import server as requirements_server


class IocOperationCompilerTests(unittest.TestCase):
    def sample_base_ioc_text(self) -> str:
        return "\n".join(
            [
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
            ]
        )

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
                        "PA2": ["USART2_TX"],
                        "PA3": ["USART2_RX"],
                    },
                    "signal_pins": {
                        "TIM1_CH3": ["PA10"],
                        "TIM1_CH3N": ["PB1", "PB15"],
                        "USART2_TX": ["PA2"],
                        "USART2_RX": ["PA3"],
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

    def test_compile_contract_to_ioc_plan_emits_generic_operations(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Create a NUCLEO-L476RG project that blinks the LED and sends data to PC"
        )

        result = ioc_compiler.compile_contract_to_ioc_plan(contract)

        self.assertTrue(result["success"])
        operations = [IocOperation.from_dict(payload) for payload in result["operations"]]
        self.assertTrue(any(operation.kind == "ensure_peripheral_enabled" and operation.value == "USART2" for operation in operations))
        self.assertTrue(any(operation.kind == "ensure_pin_used" and operation.value == "PA2" for operation in operations))
        self.assertTrue(
            any(
                operation.kind == "set_property"
                and operation.target.get("key") == "USART2.BaudRate"
                and operation.value == 115200
                for operation in operations
            )
        )
        self.assertEqual(result["builder_strategy"], "seed_plus_mutate")
        self.assertEqual(result["operation_strategy"], "operation_ir_plus_mutate")

    def test_apply_ioc_operations_mutates_lines_and_updates_numbered_lists(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Create a NUCLEO-L476RG project that blinks the LED and sends data to PC"
        )
        plan = ioc_compiler.compile_contract_to_ioc_plan(contract)
        lines = self.sample_base_ioc_text().splitlines()

        applied = ioc_mutator.apply_ioc_operations(lines, plan["operations"])

        updated_text = "\n".join(lines)
        self.assertIn("PA2.Signal=USART2_TX", updated_text)
        self.assertIn("PA3.Signal=USART2_RX", updated_text)
        self.assertIn("PA5.Signal=GPIO_Output", updated_text)
        self.assertIn("USART2.BaudRate=115200", updated_text)
        properties = ioc_mutator.parse_ioc_properties_from_lines(lines)
        recorded_pins = ioc_mutator.collect_numbered_values(properties, "Mcu.Pin")
        recorded_peripherals = ioc_mutator.collect_numbered_values(properties, "Mcu.IP")
        self.assertIn("USART2", recorded_peripherals)
        self.assertIn("PA5", recorded_pins)
        self.assertIn("PA2", recorded_pins)
        self.assertIn("PA3", recorded_pins)
        self.assertIn("USART2", applied["enabled_peripherals"])
        self.assertIn("PA2", applied["used_pins"])

    def test_legacy_ioc_properties_can_be_recovered_from_operations(self) -> None:
        contract = requirements_server.build_requirements_contract("Create a NUCLEO-L476RG project that sends data to PC")
        plan = ioc_compiler.compile_contract_to_ioc_plan(contract)

        properties = ioc_mutator.legacy_ioc_properties_from_operations(plan["operations"])

        self.assertIn({"key": "PA2.Signal", "value": "USART2_TX"}, properties)
        self.assertIn({"key": "PA3.Signal", "value": "USART2_RX"}, properties)
        self.assertIn({"key": "USART2.BaudRate", "value": 115200}, properties)

    def test_compile_contract_to_ioc_plan_supports_tim1_complementary_pwm_increment(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "This project has to be tested with NUCLEO-L476RG Rev C. "
            "SystemCoreClock is set to 80 MHz, Counter repetition = 3, Prescaler = 0, "
            "and the objective is to configure TIM1 channel 3 complementary PWM with DMA updating CCR3 "
            "at a frequency equal to 17.57 KHz."
        )
        increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][1])

        with patch(
            "stm32cubep_mcp.ioc_builder.st_mcu_catalog.local_cubemx_db_index",
            return_value=self.sample_l476_tim1_index(),
        ):
            result = ioc_compiler.compile_contract_to_ioc_plan(increment_contract)

        self.assertTrue(result["success"])
        self.assertIn("TIM1", result["enabled_peripherals"])
        self.assertIn("PA10", result["used_pins"])
        self.assertIn("PB1", result["used_pins"])
        self.assertIn({"key": "PA10.Signal", "value": "S_TIM1_CH3"}, result["ioc_properties"])
        self.assertIn({"key": "PB1.Signal", "value": "TIM1_CH3N"}, result["ioc_properties"])
        self.assertIn({"key": "PB1.Mode", "value": "PWM Generation3 CH3 CH3N"}, result["ioc_properties"])
        self.assertIn({"key": "SH.S_TIM1_CH3.0", "value": "TIM1_CH3,PWM Generation3 CH3 CH3N"}, result["ioc_properties"])
        self.assertIn({"key": "TIM1.Channel-PWM Generation3 CH3 CH3N", "value": "TIM_CHANNEL_3"}, result["ioc_properties"])
        self.assertIn({"key": "TIM1.Prescaler", "value": 0}, result["ioc_properties"])
        self.assertIn({"key": "TIM1.RepetitionCounter", "value": 3}, result["ioc_properties"])
        self.assertIn({"key": "TIM1.Period", "value": 4552}, result["ioc_properties"])

    def test_compile_contract_to_ioc_plan_supports_tim1_dma_increment(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "This project has to be tested with NUCLEO-L476RG Rev C. "
            "SystemCoreClock is set to 80 MHz, Counter repetition = 3, Prescaler = 0, "
            "and the objective is to configure TIM1 channel 3 complementary PWM with DMA updating CCR3 "
            "at a frequency equal to 17.57 KHz."
        )
        increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][2])

        with patch(
            "stm32cubep_mcp.ioc_builder.st_mcu_catalog.local_cubemx_db_index",
            return_value=self.sample_l476_tim1_index(),
        ):
            result = ioc_compiler.compile_contract_to_ioc_plan(increment_contract)

        self.assertTrue(result["success"])
        self.assertIn("DMA", result["enabled_peripherals"])
        self.assertIn("TIM1", result["enabled_peripherals"])
        self.assertIn({"key": "Dma.Request0", "value": "TIM1_CH3"}, result["ioc_properties"])
        self.assertIn({"key": "Dma.RequestsNb", "value": 1}, result["ioc_properties"])
        self.assertIn({"key": "Dma.TIM1_CH3.0.Instance", "value": "DMA1_Channel7"}, result["ioc_properties"])
        self.assertIn({"key": "Dma.TIM1_CH3.0.Mode", "value": "DMA_CIRCULAR"}, result["ioc_properties"])
        self.assertIn(
            {"key": "NVIC.DMA1_Channel7_IRQn", "value": "true\\:0\\:0\\:false\\:false\\:true\\:false\\:true"},
            result["ioc_properties"],
        )

    def test_compile_contract_to_ioc_plan_supports_debug_uart_increment(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Write a program for NUCLEO-L476RG Rev C that configures TIM1 channel 3 complementary PWM with DMA, "
            "and where required for testing send messages from device to host over uart and read them on Host side using stm32 vcp."
        )
        increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][-1])

        with patch(
            "stm32cubep_mcp.ioc_builder.st_mcu_catalog.local_cubemx_db_index",
            return_value=self.sample_l476_tim1_index(),
        ):
            result = ioc_compiler.compile_contract_to_ioc_plan(increment_contract)

        self.assertTrue(result["success"])
        self.assertIn("USART2", result["enabled_peripherals"])
        self.assertIn({"key": "PA2.Signal", "value": "USART2_TX"}, result["ioc_properties"])
        self.assertIn({"key": "PA3.Signal", "value": "USART2_RX"}, result["ioc_properties"])
        self.assertIn({"key": "USART2.BaudRate", "value": 115200}, result["ioc_properties"])

    def test_compile_contract_to_ioc_plan_supports_wwdg_increment(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Write a program for NUCLEO-L476RG Rev C with SystemClock configured to 80 MHz. "
            "Configure the WWDG so it is refreshed every 20 ms and resets after the counter falls to 0x3F. "
            "LED2 is toggling while running and this example must be tested in standalone mode."
        )
        increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][2])

        with patch(
            "stm32cubep_mcp.ioc_builder.st_mcu_catalog.local_cubemx_db_index",
            return_value={"mcu_catalog": {}, "family_config_index": {}, "dma_ll_mapping": {}},
        ):
            result = ioc_compiler.compile_contract_to_ioc_plan(increment_contract)

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

    def test_compile_contract_to_ioc_plan_supports_rtc_alarm_increment(self) -> None:
        contract = requirements_server.build_requirements_contract(
            "Write a program for NUCLEO-L476RG Rev C with the clock set to 80 MHz. "
            "Configuration and generation of an RTC alarm using the RTC HAL API. "
            "The Time is set to 02:20:00 and the Alarm must be generated after 30 seconds on 02:20:30. "
            "LED2 is turned ON when the RTC Alarm is generated correctly."
        )
        increment_contract = workflow_state.contract_for_increment(contract, contract["increments"][2])

        with patch(
            "stm32cubep_mcp.ioc_builder.st_mcu_catalog.local_cubemx_db_index",
            return_value={"mcu_catalog": {}, "family_config_index": {}, "dma_ll_mapping": {}},
        ):
            result = ioc_compiler.compile_contract_to_ioc_plan(increment_contract)

        self.assertTrue(result["success"])
        self.assertIn("RTC", result["enabled_peripherals"])
        self.assertIn("VP_RTC_VS_RTC_Activate", result["used_pins"])
        self.assertIn("VP_RTC_VS_RTC_Alarm_A_Intern", result["used_pins"])
        self.assertIn({"key": "VP_RTC_VS_RTC_Activate.Signal", "value": "RTC_VS_RTC_Activate"}, result["ioc_properties"])
        self.assertIn({"key": "VP_RTC_VS_RTC_Activate.Mode", "value": "RTC_Enabled"}, result["ioc_properties"])
        self.assertIn({"key": "VP_RTC_VS_RTC_Alarm_A_Intern.Signal", "value": "RTC_VS_RTC_Alarm_A_Intern"}, result["ioc_properties"])
        self.assertIn({"key": "VP_RTC_VS_RTC_Alarm_A_Intern.Mode", "value": "Alarm A"}, result["ioc_properties"])
        self.assertIn({"key": "RTC.HourFormat", "value": "RTC_HOURFORMAT_24"}, result["ioc_properties"])
        self.assertIn({"key": "RCC.RTCClockSelection", "value": "RCC_RTCCLKSOURCE_LSI"}, result["ioc_properties"])
        self.assertIn({"key": "NVIC.RTC_Alarm_IRQn", "value": "true\\:0\\:0\\:false\\:false\\:true\\:true\\:true"}, result["ioc_properties"])

    def test_apply_ioc_operations_merges_rcc_ipparameters_instead_of_replacing_them(self) -> None:
        lines = [
            "RCC.IPParameters=MSIClockRange,SysClockFreq_VALUE",
            "RCC.SysClockFreq_VALUE=80000000",
        ]
        operations = [
            IocOperation(
                kind="set_property",
                target={"key": "RCC.IPParameters"},
                value="RTCClockSelection,RTCFreq_Value",
            )
        ]

        ioc_mutator.apply_ioc_operations(lines, operations)

        self.assertEqual(
            lines[0],
            "RCC.IPParameters=MSIClockRange,SysClockFreq_VALUE,RTCClockSelection,RTCFreq_Value",
        )


if __name__ == "__main__":
    unittest.main()
