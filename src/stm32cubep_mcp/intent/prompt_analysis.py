from __future__ import annotations

import re

from .classifiers import SUPPORTED_PROMPT_FAMILIES, looks_like_engineering_feature_spec
from .policy import derive_execution_policy
from ..project_model import IntentBundle

GENERIC_ENGINEERING_FEATURE_ID = "core-generic-engineering-spec"
GENERIC_ENGINEERING_HINT_PATTERN = re.compile(
    r"\b(?:TIM\d+|LPTIM\d*|USART\d+|UART\d+|SPI\d+|I2C\d+|ADC\d+|DAC|DMA|PWM|GPIO|EXTI|RCC|PWR|LPRUN|OPAMP|PGA|SYSCLK|SystemCoreClock|PLL|MSI|HSI|MCO1|MCO|WWDG|watchdog|Hardfault|RTC|Alarm|LSI|LSE)\b|low[- ]power run|STOP mode",
    re.IGNORECASE,
)
GENERIC_CLOCK_HINT_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*mhz\b", re.IGNORECASE)
RUN_MODE_CLOCK_HINT_PATTERN = re.compile(r"\bsystem clock is set to\s+(\d+(?:\.\d+)?)\s*mhz\b", re.IGNORECASE)
LOW_POWER_MSI_HINT_PATTERN = re.compile(r"\bMSI\s*(?:Range\s*)?0\b.*?\b(\d+(?:\.\d+)?)\s*KHz\b|\b(\d+(?:\.\d+)?)\s*KHz\b.*?\bMSI\s*(?:Range\s*)?0\b", re.IGNORECASE | re.DOTALL)
ENTER_LOW_POWER_AFTER_SECONDS_PATTERN = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*seconds?\s+after\s+start[- ]up\b", re.IGNORECASE)
DAC_OUTPUT_PATTERN = re.compile(r"\b(DAC_OUT\d+)\s*\((P[A-Z]\d+)\)", re.IGNORECASE)
OPAMP_OUTPUT_PATTERN = re.compile(r"\b(OPAMP\d+).*?\bon\s+(P[A-Z]\d+)", re.IGNORECASE | re.DOTALL)
OPAMP_GAIN_PATTERN = re.compile(r"\bgain\s*(?:=|of either)?\s*(\d+)\b", re.IGNORECASE)
OPAMP_GAIN_EITHER_PATTERN = re.compile(r"\bgain\s+of\s+either\s+(\d+)\s+or\s+(\d+)\b", re.IGNORECASE)
LPTIM_AUTORELOAD_PATTERN = re.compile(r"\bAuto(?:reload|relaod)\s+equal\s+to\s+(\d+)\b", re.IGNORECASE)
LPTIM_PULSE_PATTERN = re.compile(r"\bPulse\s+value\s+equal\s+to\s+(\d+)\b", re.IGNORECASE)
TIMER_INSTANCE_PATTERN = re.compile(r"\b(TIM\d+)\b", re.IGNORECASE)
CHANNEL_PATTERN = re.compile(r"\bchannel\s*(\d+)\b", re.IGNORECASE)
FREQUENCY_PATTERN = re.compile(r"\bfrequency(?:\s+equal\s+to|\s+of)?\s*(\d+(?:\.\d+)?)\s*(khz|hz)\b", re.IGNORECASE)
PRESCALER_PATTERN = re.compile(r"\bprescaler\s*=\s*(\d+)\b", re.IGNORECASE)
REPETITION_COUNTER_PATTERN = re.compile(r"\bcounter repetition\s*=\s*(\d+)\b", re.IGNORECASE)
COMPARE_REGISTER_PATTERN = re.compile(r"(?:\b|_)CCR(\d+)\b", re.IGNORECASE)
DMA_UPDATE_PERIOD_PATTERN = re.compile(r"\beach\s+(\d+)\s+update requests\b", re.IGNORECASE)
DEBUG_UART_TEST_PATTERN = re.compile(
    r"\b(send messages?|print statements?|uart|serial|vcp)\b.*\b(host|pc)\b|\b(host|pc)\b.*\b(uart|serial|vcp)\b",
    re.IGNORECASE,
)
WWDG_TIMEOUT_MS_PATTERN = re.compile(r"\bWWDG timeout is set\b.*?\bto\s+(\d+(?:[.,]\d+)?)\s*ms\b", re.IGNORECASE | re.DOTALL)
WWDG_REFRESH_INTERVAL_MS_PATTERN = re.compile(
    r"\brefreshed each\s+(\d+(?:[.,]\d+)?)\s*ms\b|\bwait\s+(\d+(?:[.,]\d+)?)\s*ms\b.*?\bbefore writing again counter\b",
    re.IGNORECASE | re.DOTALL,
)
WWDG_RESET_COUNTER_PATTERN = re.compile(r"\bfalls to\s+0x([0-9a-f]+)\b", re.IGNORECASE)
RESET_LED_HOLD_SECONDS_PATTERN = re.compile(r"\bturned ON for\s+(\d+(?:[.,]\d+)?)\s*seconds\b", re.IGNORECASE)
RTC_INITIAL_TIME_PATTERN = re.compile(
    r"\btime\s+is\s+set\s+to\s+(\d{2}):(\d{2}):(\d{2})\b",
    re.IGNORECASE,
)
RTC_ALARM_TIME_PATTERN = re.compile(
    r"\balarm\b.*?\bon\s+(\d{2}):(\d{2}):(\d{2})\b",
    re.IGNORECASE | re.DOTALL,
)
RTC_ALARM_AFTER_SECONDS_PATTERN = re.compile(
    r"\balarm\b.*?\bafter\s+(\d+)\s+seconds\b",
    re.IGNORECASE | re.DOTALL,
)


def _time_tuple_from_match(match: re.Match[str] | None) -> tuple[int, int, int] | None:
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _decimal_number(value: str | None) -> float | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace(",", ".")
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _contains_token(lowered: str, token: str) -> bool:
    if " " in token:
        return token in lowered
    return bool(re.search(rf"\b{re.escape(token)}\b", lowered))


def _contains_any_token(lowered: str, tokens: tuple[str, ...]) -> bool:
    return any(_contains_token(lowered, token) for token in tokens)


def _extract_engineering_spec_metadata(prompt: str) -> dict[str, object]:
    hints = [match.group(0).upper() for match in GENERIC_ENGINEERING_HINT_PATTERN.finditer(prompt)]
    unique_hints: list[str] = []
    for hint in hints:
        if hint not in unique_hints:
            unique_hints.append(hint)

    clock_match = GENERIC_CLOCK_HINT_PATTERN.search(prompt)
    clock_mhz = float(clock_match.group(1)) if clock_match is not None else None

    return {
        "spec_kind": "generic_engineering_spec",
        "prompt_hints": unique_hints,
        "clock_mhz": clock_mhz,
        "raw_prompt": prompt,
    }


def _frequency_hz_from_prompt(prompt: str) -> float | None:
    match = FREQUENCY_PATTERN.search(prompt)
    if match is None:
        return None
    magnitude = float(match.group(1))
    unit = match.group(2).lower()
    return magnitude * 1000.0 if unit == "khz" else magnitude


def _engineering_spec_details(prompt: str, metadata: dict[str, object]) -> dict[str, object]:
    lowered = prompt.lower()
    timer_match = TIMER_INSTANCE_PATTERN.search(prompt)
    channel_match = CHANNEL_PATTERN.search(prompt)
    compare_register_match = COMPARE_REGISTER_PATTERN.search(prompt)
    prescaler_match = PRESCALER_PATTERN.search(prompt)
    repetition_counter_match = REPETITION_COUNTER_PATTERN.search(prompt)
    dma_update_period_match = DMA_UPDATE_PERIOD_PATTERN.search(prompt)
    wwdg_timeout_match = WWDG_TIMEOUT_MS_PATTERN.search(prompt)
    wwdg_refresh_interval_match = WWDG_REFRESH_INTERVAL_MS_PATTERN.search(prompt)
    wwdg_reset_counter_match = WWDG_RESET_COUNTER_PATTERN.search(prompt)
    reset_led_hold_match = RESET_LED_HOLD_SECONDS_PATTERN.search(prompt)
    rtc_initial_time_match = RTC_INITIAL_TIME_PATTERN.search(prompt)
    rtc_alarm_time_match = RTC_ALARM_TIME_PATTERN.search(prompt)
    rtc_alarm_after_seconds_match = RTC_ALARM_AFTER_SECONDS_PATTERN.search(prompt)
    run_mode_clock_match = RUN_MODE_CLOCK_HINT_PATTERN.search(prompt)
    low_power_msi_match = LOW_POWER_MSI_HINT_PATTERN.search(prompt)
    enter_low_power_after_match = ENTER_LOW_POWER_AFTER_SECONDS_PATTERN.search(prompt)
    dac_output_match = DAC_OUTPUT_PATTERN.search(prompt)
    opamp_output_match = OPAMP_OUTPUT_PATTERN.search(prompt)
    lptim_autoreload_match = LPTIM_AUTORELOAD_PATTERN.search(prompt)
    lptim_pulse_match = LPTIM_PULSE_PATTERN.search(prompt)

    clock_mhz = metadata.get("clock_mhz")
    clock_hz = int(float(clock_mhz) * 1_000_000) if isinstance(clock_mhz, (int, float)) else None
    run_mode_clock_mhz = _decimal_number(run_mode_clock_match.group(1)) if run_mode_clock_match is not None else None
    low_power_msi_khz = None
    if low_power_msi_match is not None:
        low_power_msi_khz = _decimal_number(low_power_msi_match.group(1) or low_power_msi_match.group(2))
    opamp_gain_values = {int(match.group(1)) for match in OPAMP_GAIN_PATTERN.finditer(prompt)}
    for match in OPAMP_GAIN_EITHER_PATTERN.finditer(prompt):
        opamp_gain_values.add(int(match.group(1)))
        opamp_gain_values.add(int(match.group(2)))
    refresh_interval_match_value = None
    if wwdg_refresh_interval_match is not None:
        refresh_interval_match_value = wwdg_refresh_interval_match.group(1) or wwdg_refresh_interval_match.group(2)

    return {
        "timer_instance": timer_match.group(1).upper() if timer_match is not None else None,
        "channel": int(channel_match.group(1)) if channel_match is not None else None,
        "frequency_hz": _frequency_hz_from_prompt(prompt),
        "prescaler": int(prescaler_match.group(1)) if prescaler_match is not None else None,
        "repetition_counter": int(repetition_counter_match.group(1)) if repetition_counter_match is not None else None,
        "compare_register": f"CCR{compare_register_match.group(1)}" if compare_register_match is not None else None,
        "dma_update_period": int(dma_update_period_match.group(1)) if dma_update_period_match is not None else None,
        "clock_hz": clock_hz,
        "complementary_output": "complementary pwm" in lowered or "complementary output" in lowered,
        "requires_dma": "dma" in lowered,
        "requires_host_debug_uart": DEBUG_UART_TEST_PATTERN.search(prompt) is not None,
        "requires_wwdg": "wwdg" in lowered or "window watchdog" in lowered,
        "requires_rtc_alarm": "rtc" in lowered and "alarm" in lowered,
        "requires_rcc_clockconfig": (
            "rcc_clockconfig" in lowered
            or ("pll" in lowered and "msi" in lowered and "hsi" in lowered and ("mco" in lowered or "mco1" in lowered))
        ),
        "requires_low_power_run": "pwr_lprun" in lowered or "low power run" in lowered or "low-power run" in lowered or "lp run" in lowered,
        "requires_opamp_pga": "opamp_pga" in lowered or ("opamp" in lowered and "pga" in lowered),
        "requires_lptim_external_counter_pwm": "lptim" in lowered and "pwm" in lowered and "external counter" in lowered,
        "requires_led_status": "led2" in lowered or "toggling" in lowered or "turned on for" in lowered,
        "requires_user_button_exti": "exti line" in lowered or "user push-button" in lowered or "pc.13" in lowered,
        "fault_injection_hardfault": "hardfault" in lowered or "invalid address" in lowered,
        "standalone_required": (
            "standalone mode" in lowered
            or "not in debug" in lowered
            or "cannot be used in debug" in lowered
            or "can not be used in debug" in lowered
        ),
        "wwdg_timeout_ms": _decimal_number(wwdg_timeout_match.group(1)) if wwdg_timeout_match is not None else None,
        "wwdg_refresh_interval_ms": _decimal_number(refresh_interval_match_value),
        "wwdg_reset_counter_hex": f"0x{wwdg_reset_counter_match.group(1).upper()}" if wwdg_reset_counter_match is not None else None,
        "reset_led_hold_seconds": _decimal_number(reset_led_hold_match.group(1)) if reset_led_hold_match is not None else None,
        "rtc_clock_source": "LSE" if "use also lse as rtc clock source" in lowered or "use lse as rtc clock source" in lowered else "LSI",
        "rtc_initial_time_hms": _time_tuple_from_match(rtc_initial_time_match),
        "rtc_alarm_time_hms": _time_tuple_from_match(rtc_alarm_time_match),
        "rtc_alarm_after_seconds": int(rtc_alarm_after_seconds_match.group(1)) if rtc_alarm_after_seconds_match is not None else None,
        "run_mode_clock_hz": int(float(run_mode_clock_mhz) * 1_000_000) if isinstance(run_mode_clock_mhz, (int, float)) else None,
        "low_power_clock_hz": int(float(low_power_msi_khz) * 1000) if isinstance(low_power_msi_khz, (int, float)) else None,
        "enter_low_power_after_seconds": _decimal_number(enter_low_power_after_match.group(1)) if enter_low_power_after_match is not None else None,
        "dac_output_signal": dac_output_match.group(1).upper() if dac_output_match is not None else None,
        "dac_output_pin": dac_output_match.group(2).upper() if dac_output_match is not None else None,
        "opamp_output_instance": opamp_output_match.group(1).upper() if opamp_output_match is not None else None,
        "opamp_output_pin": opamp_output_match.group(2).upper() if opamp_output_match is not None else None,
        "opamp_gain_values": sorted(opamp_gain_values),
        "requires_dac_dma_sine": "sine" in lowered and "dac" in lowered and "dma" in lowered,
        "requires_cortex_sleep": "cortex" in lowered and "sleep mode" in lowered,
        "requires_no_dma_interrupt_handling": "no dma interrupt handling" in lowered or "no it handled by cortex" in lowered,
        "lptim_autoreload": int(lptim_autoreload_match.group(1)) if lptim_autoreload_match is not None else None,
        "lptim_pulse": int(lptim_pulse_match.group(1)) if lptim_pulse_match is not None else None,
        "requires_stop_mode": "stop mode" in lowered,
        "requires_low_speed_gpio": "gpio" in lowered and "low speed" in lowered,
    }


def _plan_engineering_spec_features(
    prompt: str,
    metadata: dict[str, object],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[str], list[str]]:
    details = _engineering_spec_details(prompt, metadata)
    core_features: list[dict[str, object]] = []
    pluggable_features: list[dict[str, object]] = []
    interface_intents: list[dict[str, object]] = []
    assumptions: list[str] = []
    open_questions: list[str] = []

    clock_hz = details.get("clock_hz")
    if isinstance(clock_hz, int) and clock_hz > 0:
        requires_rcc_clockconfig = bool(details.get("requires_rcc_clockconfig"))
        clock_feature_id = "core-rcc-clockconfig-baseline" if requires_rcc_clockconfig else f"core-clock-{clock_hz}"
        clock_feature_title = (
            "Configure RCC ClockConfig baseline"
            if requires_rcc_clockconfig
            else f"Configure system clock to {clock_hz} Hz"
        )
        clock_feature_summary = (
            "Configure SYSCLK at 80 MHz from PLL/MSI and expose SYSCLK on MCO1 PA8 before runtime switching is layered on."
            if requires_rcc_clockconfig
            else "Establish the requested system clock before peripheral feature delivery starts."
        )
        core_features.append(
            {
                "id": clock_feature_id,
                "title": clock_feature_title,
                "kind": "core",
                "summary": clock_feature_summary,
                "interface_intent_ids": ["iface-clock-system"],
                "spec": {
                    "clock_hz": clock_hz,
                    "initial_pll_source": "MSI" if requires_rcc_clockconfig else None,
                    "mco_pin": "PA8" if requires_rcc_clockconfig else None,
                },
            }
        )
        clock_intent = {
            "id": "iface-clock-system",
            "type": "clock",
            "role": "rcc_clockconfig_baseline" if requires_rcc_clockconfig else "system_clock",
            "sysclk_hz": clock_hz,
            "source": "engineering_spec",
        }
        if requires_rcc_clockconfig:
            clock_intent.update(
                {
                    "initial_pll_source": "MSI",
                    "mco_pin": "PA8",
                    "mco_source": "SYSCLK",
                }
            )
        interface_intents.append(clock_intent)
        assumptions.append("The engineering specification's system clock requirement should be satisfied before timer and DMA features are validated.")

        if requires_rcc_clockconfig:
            pluggable_features.append(
                {
                    "id": "pluggable-rcc-pll-source-switch",
                    "title": "Runtime PLL source switch",
                    "kind": "pluggable",
                    "summary": "Use the user button EXTI path to switch the PLL source between MSI and HSI at runtime after the baseline clock is working.",
                    "interface_intent_ids": ["iface-rcc-pll-source-switch", "iface-button-pc13"],
                    "spec": {
                        "initial_pll_source": "MSI",
                        "alternate_pll_source": "HSI",
                        "button_pin": "PC13",
                        "button_exti_line": 13,
                    },
                }
            )
            interface_intents.append(
                {
                    "id": "iface-rcc-pll-source-switch",
                    "type": "clock",
                    "role": "runtime_pll_source_switch",
                    "sysclk_hz": clock_hz,
                    "initial_pll_source": "MSI",
                    "alternate_pll_source": "HSI",
                    "button_pin": "PC13",
                    "button_exti_line": 13,
                    "source": "engineering_spec",
                }
            )
            interface_intents.append(
                {
                    "id": "iface-button-pc13",
                    "type": "gpio_exti",
                    "role": "user_button",
                    "pin": "PC13",
                    "label": "B1 [Blue PushButton]",
                    "signal": "GPXTI13",
                    "source": "engineering_spec",
                }
            )

    if details.get("requires_low_power_run"):
        core_features.append(
            {
                "id": "core-pwr-low-power-run",
                "title": "Low Power Run mode",
                "kind": "core",
                "summary": "Preserve the requested Low Power Run state machine as an explicit firmware behavior increment.",
                "interface_intent_ids": ["iface-pwr-low-power-run"],
                "spec": {
                    "run_mode_clock_hz": details.get("run_mode_clock_hz"),
                    "low_power_clock_hz": details.get("low_power_clock_hz"),
                    "msi_range": 0,
                    "enter_after_seconds": details.get("enter_low_power_after_seconds"),
                    "exit_button_pin": "PC13" if details.get("requires_user_button_exti") else None,
                    "regulator_mode": "low_power",
                    "voltage_range": 2,
                    "flash_wait_states": 0,
                    "debug_mode_supported": not bool(details.get("standalone_required")),
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-pwr-low-power-run",
                "type": "power",
                "role": "low_power_run",
                "run_mode_clock_hz": details.get("run_mode_clock_hz"),
                "low_power_clock_hz": details.get("low_power_clock_hz"),
                "msi_range": 0,
                "enter_after_seconds": details.get("enter_low_power_after_seconds"),
                "exit_button_pin": "PC13" if details.get("requires_user_button_exti") else None,
                "regulator_mode": "low_power",
                "voltage_range": 2,
                "flash_wait_states": 0,
                "debug_mode_supported": not bool(details.get("standalone_required")),
                "source": "engineering_spec",
            }
        )
        assumptions.append("Low Power Run behavior requires firmware state-machine code in CubeMX user-code regions; IOC can only preserve the surrounding board setup.")
        if details.get("standalone_required"):
            assumptions.append("Runtime validation should avoid debugger-dependent checks because the prompt states that this low-power example cannot be used in debug mode.")

    if details.get("requires_opamp_pga"):
        core_features.append(
            {
                "id": "core-opamp-pga-signal-chain",
                "title": "OPAMP PGA signal chain",
                "kind": "core",
                "summary": "Preserve the requested DAC-to-OPAMP programmable-gain analog signal chain as an explicit firmware behavior increment.",
                "interface_intent_ids": ["iface-opamp-pga-signal-chain"],
                "spec": {
                    "dac_output_signal": details.get("dac_output_signal"),
                    "dac_output_pin": details.get("dac_output_pin"),
                    "opamp_output_instance": details.get("opamp_output_instance"),
                    "opamp_output_pin": details.get("opamp_output_pin"),
                    "gain_values": details.get("opamp_gain_values"),
                    "requires_dac_dma_sine": bool(details.get("requires_dac_dma_sine")),
                    "uses_low_power_modes": "low power mode" in prompt.lower(),
                    "requires_cortex_sleep": bool(details.get("requires_cortex_sleep")),
                    "requires_no_dma_interrupt_handling": bool(details.get("requires_no_dma_interrupt_handling")),
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-opamp-pga-signal-chain",
                "type": "analog",
                "role": "opamp_pga_signal_chain",
                "dac_output_signal": details.get("dac_output_signal"),
                "dac_output_pin": details.get("dac_output_pin"),
                "opamp_instances": ["OPAMP1", "OPAMP2"],
                "opamp_output_instance": details.get("opamp_output_instance"),
                "opamp_output_pin": details.get("opamp_output_pin"),
                "gain_values": details.get("opamp_gain_values"),
                "requires_dac_dma_sine": bool(details.get("requires_dac_dma_sine")),
                "uses_low_power_modes": "low power mode" in prompt.lower(),
                "requires_cortex_sleep": bool(details.get("requires_cortex_sleep")),
                "requires_no_dma_interrupt_handling": bool(details.get("requires_no_dma_interrupt_handling")),
                "source": "engineering_spec",
            }
        )
        assumptions.append("OPAMP PGA prompts require analog peripheral IOC mapping plus firmware sequencing; unsupported pieces must be kept visible in the plan instead of collapsed into UART-only diagnostics.")

    if details.get("requires_lptim_external_counter_pwm"):
        autoreload = details.get("lptim_autoreload")
        pulse = details.get("lptim_pulse")
        duty_cycle_percent = None
        if isinstance(autoreload, int) and isinstance(pulse, int) and autoreload >= 0:
            duty_cycle_percent = round((1.0 - ((pulse + 1.0) / (autoreload + 1.0))) * 100.0, 3)
        core_features.append(
            {
                "id": "core-lptim-external-counter-low-power-pwm",
                "title": "LPTIM external-counter low-power PWM",
                "kind": "core",
                "summary": "Preserve the requested LPTIM external-counter PWM and STOP-mode wakeup flow as an explicit firmware behavior increment.",
                "interface_intent_ids": ["iface-lptim-external-counter-pwm"],
                "spec": {
                    "instance": "LPTIM",
                    "clock_source": "external_counter",
                    "autoreload": autoreload,
                    "pulse": pulse,
                    "output_frequency_divider": (autoreload + 1) if isinstance(autoreload, int) else None,
                    "duty_cycle_percent": duty_cycle_percent,
                    "requires_stop_mode": bool(details.get("requires_stop_mode")),
                    "requires_low_speed_gpio": bool(details.get("requires_low_speed_gpio")),
                    "wakeup_pin": "PC13" if details.get("requires_user_button_exti") else None,
                    "stop_pwm_on_wakeup": True,
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-lptim-external-counter-pwm",
                "type": "lptim",
                "role": "external_counter_low_power_pwm",
                "instance": "LPTIM",
                "clock_source": "external_counter",
                "autoreload": autoreload,
                "pulse": pulse,
                "output_frequency_divider": (autoreload + 1) if isinstance(autoreload, int) else None,
                "duty_cycle_percent": duty_cycle_percent,
                "requires_stop_mode": bool(details.get("requires_stop_mode")),
                "requires_low_speed_gpio": bool(details.get("requires_low_speed_gpio")),
                "wakeup_pin": "PC13" if details.get("requires_user_button_exti") else None,
                "stop_pwm_on_wakeup": True,
                "source": "engineering_spec",
            }
        )
        assumptions.append("LPTIM external-counter PWM prompts require peripheral-specific IOC mapping plus firmware STOP-mode sequencing; unsupported pieces must remain visible in the plan.")

    if details.get("requires_led_status"):
        core_features.append(
            {
                "id": "core-led2-status-output",
                "title": "Configure LED2 status output",
                "kind": "core",
                "summary": "Drive the on-board LED so the firmware can expose running, reset, and error status states.",
                "interface_intent_ids": ["iface-led-pa5"],
                "spec": {
                    "pin": "PA5",
                    "label": "LD2 [green Led]",
                    "signal": "GPIO_Output",
                    "reset_hold_seconds": details.get("reset_led_hold_seconds"),
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-led-pa5",
                "type": "gpio",
                "role": "led_output",
                "pin": "PA5",
                "label": "LD2 [green Led]",
                "signal": "GPIO_Output",
                "source": "engineering_spec",
            }
        )
        assumptions.append("PA5 is the default LED2 pin on NUCLEO-L476RG for run-state and reset-state indication.")

    if details.get("requires_wwdg"):
        core_features.append(
            {
                "id": "core-wwdg-supervision",
                "title": "Configure WWDG supervision",
                "kind": "core",
                "summary": "Enable the window watchdog so the firmware can refresh it during normal operation and allow a reset during a simulated failure.",
                "interface_intent_ids": ["iface-wwdg-supervision"],
                "spec": {
                    "timeout_ms": details.get("wwdg_timeout_ms"),
                    "refresh_interval_ms": details.get("wwdg_refresh_interval_ms"),
                    "reset_counter_hex": details.get("wwdg_reset_counter_hex"),
                    "standalone_required": bool(details.get("standalone_required")),
                    "fault_injection_hardfault": bool(details.get("fault_injection_hardfault")),
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-wwdg-supervision",
                "type": "watchdog",
                "role": "window_watchdog",
                "instance": "WWDG",
                "timeout_ms": details.get("wwdg_timeout_ms"),
                "refresh_interval_ms": details.get("wwdg_refresh_interval_ms"),
                "reset_counter_hex": details.get("wwdg_reset_counter_hex"),
                "standalone_required": bool(details.get("standalone_required")),
                "fault_injection_hardfault": bool(details.get("fault_injection_hardfault")),
                "source": "engineering_spec",
            }
        )
        if details.get("standalone_required"):
            assumptions.append("Runtime validation should respect the prompt's standalone-mode requirement and avoid depending on an attached debugger.")

    if details.get("requires_rtc_alarm"):
        core_features.append(
            {
                "id": "core-rtc-alarm",
                "title": "Configure RTC alarm",
                "kind": "core",
                "summary": "Enable the RTC base, set the requested time, and arm Alarm A in interrupt mode before optional host diagnostics are layered on.",
                "interface_intent_ids": ["iface-rtc-alarm-a"],
                "spec": {
                    "instance": "RTC",
                    "clock_source": details.get("rtc_clock_source"),
                    "initial_time_hms": details.get("rtc_initial_time_hms"),
                    "alarm_time_hms": details.get("rtc_alarm_time_hms"),
                    "alarm_after_seconds": details.get("rtc_alarm_after_seconds"),
                    "interrupt_mode": True,
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-rtc-alarm-a",
                "type": "rtc",
                "role": "alarm_a",
                "instance": "RTC",
                "clock_source": details.get("rtc_clock_source"),
                "initial_time_hms": details.get("rtc_initial_time_hms"),
                "alarm_time_hms": details.get("rtc_alarm_time_hms"),
                "alarm_after_seconds": details.get("rtc_alarm_after_seconds"),
                "interrupt_mode": True,
                "source": "engineering_spec",
            }
        )
        assumptions.append("The RTC alarm flow should use the board's default LSI clock source unless the prompt explicitly requires LSE.")
        if details.get("rtc_initial_time_hms") is None or details.get("rtc_alarm_time_hms") is None:
            assumptions.append("The prompt describes an RTC alarm scenario, but the firmware may need a deterministic fallback time if the requested alarm timestamps are incomplete.")

    timer_instance = details.get("timer_instance")
    channel = details.get("channel")
    frequency_hz = details.get("frequency_hz")
    if isinstance(timer_instance, str) and isinstance(channel, int):
        timer_intent_id = f"iface-{timer_instance.lower()}-ch{channel}-pwm"
        timer_feature_id = (
            f"core-{timer_instance.lower()}-ch{channel}-complementary-pwm"
            if details.get("complementary_output")
            else f"core-{timer_instance.lower()}-ch{channel}-pwm"
        )
        core_features.append(
            {
                "id": timer_feature_id,
                "title": f"Configure {timer_instance} channel {channel} PWM output",
                "kind": "core",
                "summary": "Create the requested timer PWM output before modulation and diagnostics are added.",
                "interface_intent_ids": [timer_intent_id],
                "spec": {
                    "instance": timer_instance,
                    "channel": channel,
                    "frequency_hz": frequency_hz,
                    "prescaler": details.get("prescaler"),
                    "repetition_counter": details.get("repetition_counter"),
                    "complementary_output": bool(details.get("complementary_output")),
                },
            }
        )
        interface_intents.append(
            {
                "id": timer_intent_id,
                "type": "timer_pwm",
                "role": "complementary_pwm_output" if details.get("complementary_output") else "pwm_output",
                "instance": timer_instance,
                "channel": channel,
                "frequency_hz": frequency_hz,
                "prescaler": details.get("prescaler"),
                "repetition_counter": details.get("repetition_counter"),
                "complementary_output": bool(details.get("complementary_output")),
                "target_compare_register": details.get("compare_register"),
                "source": "engineering_spec",
            }
        )

    if details.get("requires_dma") and isinstance(timer_instance, str):
        dma_intent_id = f"iface-{timer_instance.lower()}-dma-update"
        compare_register = details.get("compare_register") or "CCR?"
        pluggable_features.append(
            {
                "id": f"pluggable-{timer_instance.lower()}-{str(compare_register).lower()}-dma-update",
                "title": f"Add DMA-driven updates for {timer_instance} {compare_register}",
                "kind": "pluggable",
                "summary": "Layer DMA-based modulation onto the already working timer output.",
                "interface_intent_ids": [dma_intent_id],
                "spec": {
                    "instance": timer_instance,
                    "target_register": compare_register,
                    "trigger": "update",
                    "update_period": details.get("dma_update_period"),
                    "repetition_counter": details.get("repetition_counter"),
                },
            }
        )
        interface_intents.append(
            {
                "id": dma_intent_id,
                "type": "dma_binding",
                "role": "memory_to_timer_compare",
                "peripheral": timer_instance,
                "target_register": compare_register,
                "trigger": "update",
                "update_period": details.get("dma_update_period"),
                "repetition_counter": details.get("repetition_counter"),
                "source": "engineering_spec",
            }
        )

    if details.get("requires_user_button_exti") and not any(
        intent.get("id") == "iface-button-pc13" for intent in interface_intents if isinstance(intent, dict)
    ):
        pluggable_features.append(
            {
                "id": "pluggable-user-button-fault-trigger",
                "title": "User button fault trigger",
                "kind": "pluggable",
                "summary": "Capture the on-board user button as an EXTI trigger so firmware can simulate the requested software failure path.",
                "interface_intent_ids": ["iface-button-pc13"],
                "spec": {
                    "pin": "PC13",
                    "fault_injection_hardfault": bool(details.get("fault_injection_hardfault")),
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-button-pc13",
                "type": "gpio_exti",
                "role": "user_button",
                "pin": "PC13",
                "label": "B1 [Blue PushButton]",
                "signal": "GPXTI13",
                "fault_injection_hardfault": bool(details.get("fault_injection_hardfault")),
                "source": "engineering_spec",
            }
        )
        assumptions.append("PC13 is the default user button input pin on NUCLEO-L476RG for the EXTI-triggered fault path.")

    if details.get("requires_host_debug_uart"):
        pluggable_features.append(
            {
                "id": "pluggable-host-debug-uart",
                "title": "Host-side debug UART instrumentation",
                "kind": "pluggable",
                "summary": "Add optional host-visible debug prints guarded by _DEBUG_PRINT for testing and diagnosis.",
                "interface_intent_ids": ["iface-host-debug-uart"],
                "spec": {
                    "instance_preference": "USART2",
                    "baud_rate": 115200,
                    "macro_guard": "_DEBUG_PRINT",
                },
            }
        )
        interface_intents.append(
            {
                "id": "iface-host-debug-uart",
                "type": "uart",
                "role": "debug_console",
                "instance_preference": "USART2",
                "baud_rate": 115200,
                "macro_guard": "_DEBUG_PRINT",
                "source": "engineering_spec",
            }
        )
        assumptions.append("When runtime visibility is needed, the board's ST-LINK virtual COM path should be used for guarded debug prints.")

    if not core_features:
        core_features.append(
            {
                "id": GENERIC_ENGINEERING_FEATURE_ID,
                "title": "Translate engineering specification into an IOC baseline workflow",
                "kind": "core",
                "summary": "Start from the official board IOC baseline and preserve the engineering specification for later compiler passes.",
                "interface_intent_ids": [],
                "delivery_mode": "generic_engineering_spec",
            }
        )
        open_questions.append(
            "The engineering specification was recognized, but no concrete core feature could be extracted yet."
        )

    open_questions.append(
        "Downstream IOC compilation for advanced engineering intents is still being expanded increment by increment."
    )
    return core_features, pluggable_features, interface_intents, assumptions, open_questions


def plan_feature_split(
    prompt: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[str], list[str]]:
    lowered = prompt.strip().lower()
    if looks_like_engineering_feature_spec(prompt):
        engineering_metadata = _extract_engineering_spec_metadata(prompt)
        core_features, pluggable_features, interface_intents, assumptions, open_questions = _plan_engineering_spec_features(
            prompt,
            engineering_metadata,
        )
        if _contains_any_token(lowered, ("test", "run and test", "verify", "validate")):
            pluggable_features.append(
                {
                    "id": "pluggable-runtime-check",
                    "title": "Runtime verification",
                    "kind": "pluggable",
                    "summary": "Run flash-time and post-flash verification after the core delivery increments succeed.",
                    "interface_intent_ids": [],
                    "delivery_mode": "policy_only",
                }
            )
        assumptions.append("Board-targeted engineering specifications should enter the baseline IOC workflow even when later firmware increments still need implementation.")
        return core_features, pluggable_features, interface_intents, assumptions, open_questions

    core_features: list[dict[str, object]] = []
    pluggable_features: list[dict[str, object]] = []
    interface_intents: list[dict[str, object]] = []
    assumptions: list[str] = []
    open_questions: list[str] = []

    if _contains_any_token(lowered, ("blink", "led", "toggle")):
        core_features.append(
            {
                "id": "core-led-blink",
                "title": "Blink user LED",
                "kind": "core",
                "summary": "Drive the on-board LED through a GPIO output for visible runtime behavior.",
                "interface_intent_ids": ["iface-led-pa5"],
            }
        )
        interface_intents.append(
            {
                "id": "iface-led-pa5",
                "type": "gpio",
                "role": "led_output",
                "pin": "PA5",
                "label": "LD2 [green Led]",
                "signal": "GPIO_Output",
            }
        )
        assumptions.append("PA5 is the default user LED output pin on NUCLEO-L476RG.")

    if _contains_token(lowered, "pc") and _contains_any_token(
        lowered,
        ("send data", "sends data", "send", "sends", "sending", "transmit", "printf", "uart", "serial"),
    ):
        core_features.append(
            {
                "id": "core-uart-device-to-pc",
                "title": "Send data to PC",
                "kind": "core",
                "summary": "Transmit device data to the host PC over the board's default serial path.",
                "interface_intent_ids": ["iface-uart-host-console"],
            }
        )
        interface_intents.append(
            {
                "id": "iface-uart-host-console",
                "type": "uart",
                "role": "device_to_pc_tx",
                "instance_preference": "USART2",
                "baud_rate": 115200,
                "reason": "Default host serial path for NUCLEO-L476RG prompts that ask for device-to-PC output.",
            }
        )
        assumptions.append("USART2 over the ST-LINK virtual COM path is the default device-to-PC transport for NUCLEO-L476RG.")

    if _contains_any_token(lowered, ("button", "pushbutton", "blue button", "user button")):
        pluggable_features.append(
            {
                "id": "pluggable-user-button-event",
                "title": "User button event",
                "kind": "pluggable",
                "summary": "Capture the on-board button input so firmware can react to a human-triggered event.",
                "interface_intent_ids": ["iface-button-pc13"],
            }
        )
        interface_intents.append(
            {
                "id": "iface-button-pc13",
                "type": "gpio_exti",
                "role": "user_button",
                "pin": "PC13",
                "label": "B1 [Blue PushButton]",
                "signal": "GPXTI13",
            }
        )
        assumptions.append("PC13 is the default user button input pin on NUCLEO-L476RG.")

    if not core_features and not interface_intents:
        open_questions.append(
            "The initial Phase 2 scaffold only recognizes the first supported device-to-PC serial prompt family."
        )

    if _contains_any_token(lowered, ("test", "run and test", "verify", "validate")):
        pluggable_features.append(
            {
                "id": "pluggable-runtime-check",
                "title": "Runtime verification",
                "kind": "pluggable",
                "summary": "Run flash-time and post-flash verification after the core serial output feature succeeds.",
                "interface_intent_ids": [],
                "delivery_mode": "policy_only",
            }
        )

    return core_features, pluggable_features, interface_intents, assumptions, open_questions


def build_intent_bundle(prompt: str) -> IntentBundle:
    core_features, pluggable_features, interface_intents, assumptions, open_questions = plan_feature_split(prompt)
    has_supported_delivery = bool(core_features or interface_intents)
    extra: dict[str, object] = {"supported_prompt_families": list(SUPPORTED_PROMPT_FAMILIES)}
    if looks_like_engineering_feature_spec(prompt):
        extra["engineering_spec"] = _extract_engineering_spec_metadata(prompt)
    return IntentBundle(
        intent_kind="feature_delivery" if has_supported_delivery else "unsupported_feature_request",
        confidence=0.95 if has_supported_delivery else 0.35,
        core_requirements=core_features,
        optional_requirements=pluggable_features,
        interface_intents=interface_intents,
        runtime_expectations=derive_execution_policy(prompt),
        assumptions=assumptions,
        open_questions=open_questions,
        extra=extra,
    )
