from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import floor
import re


@dataclass(slots=True)
class IocModel:
    board_id: str
    target_mcu: str
    grouped_mcu_name: str
    grouped_xml_filename: str
    toolchain: str
    required_peripherals: list[str] = field(default_factory=list)
    used_pins: list[str] = field(default_factory=list)
    reserved_board_pins: list[str] = field(default_factory=list)
    generated_labels: dict[str, str] = field(default_factory=dict)
    clock_requirements: list[str] = field(default_factory=list)
    interrupt_requirements: list[str] = field(default_factory=list)
    bindings: list[dict[str, object]] = field(default_factory=list)
    codegen_hints: list[str] = field(default_factory=list)
    compile_errors: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, object]:
        payload = asdict(self)
        payload["used_pins"] = sorted(dict.fromkeys(self.used_pins))
        payload["required_peripherals"] = sorted(dict.fromkeys(self.required_peripherals))
        return payload


def _append_unique(sequence: list[str], value: str) -> None:
    if value not in sequence:
        sequence.append(value)


# Read the engineering-spec clock target from contract metadata and normalize it into hertz.
def _engineering_clock_hz(contract: dict[str, object]) -> int | None:
    intent_metadata = contract.get("intent_metadata")
    if not isinstance(intent_metadata, dict):
        return None
    engineering_spec = intent_metadata.get("engineering_spec")
    if not isinstance(engineering_spec, dict):
        return None
    clock_mhz = engineering_spec.get("clock_mhz")
    if not isinstance(clock_mhz, (int, float)) or float(clock_mhz) <= 0:
        return None
    return int(float(clock_mhz) * 1_000_000)


# Return the MCU pin candidates advertised for one signal name in the grouped CubeMX metadata.
def _signal_pin_candidates(mcu_metadata: dict[str, object], signal_name: str) -> list[str]:
    signal_pins = mcu_metadata.get("signal_pins")
    if not isinstance(signal_pins, dict):
        return []
    candidates = signal_pins.get(signal_name)
    if not isinstance(candidates, list):
        return []
    return [pin_name for pin_name in candidates if isinstance(pin_name, str) and pin_name.strip()]


# Choose the best available pin candidate by preferring pins that are neither board-reserved nor already used.
def _select_pin_candidate(
    candidates: list[str],
    *,
    reserved_board_pins: list[str],
    used_pins: list[str],
) -> str | None:
    if not candidates:
        return None

    reserved = {pin_name.upper() for pin_name in reserved_board_pins}
    used = {pin_name.upper() for pin_name in used_pins}

    for pin_name in candidates:
        if pin_name.upper() not in reserved and pin_name.upper() not in used:
            return pin_name
    for pin_name in candidates:
        if pin_name.upper() not in used:
            return pin_name
    return candidates[0]


def _timer_channel_mode_name(channel: int, *, complementary_output: bool) -> str:
    return (
        f"PWM Generation{channel} CH{channel} CH{channel}N"
        if complementary_output
        else f"PWM Generation{channel} CH{channel}"
    )


def _timer_channel_property_name(channel: int, *, complementary_output: bool) -> str:
    return f"Channel-{_timer_channel_mode_name(channel, complementary_output=complementary_output)}"


# Derive the timer auto-reload period that best matches the requested output frequency and prescaler.
def _derive_timer_period(clock_hz: int | None, frequency_hz: float | None, prescaler: int) -> int | None:
    if not isinstance(clock_hz, int) or clock_hz <= 0:
        return None
    if not isinstance(frequency_hz, (int, float)) or float(frequency_hz) <= 0:
        return None
    counter_clock_hz = float(clock_hz) / float(prescaler + 1)
    period = floor((counter_clock_hz / float(frequency_hz)) - 1.0)
    if period < 0:
        return None
    return int(period)


def _default_pwm_pulse(period: int | None) -> int | None:
    if not isinstance(period, int) or period <= 1:
        return None
    return int((75 * (period - 1)) / 100)


# Merge IOC IP parameter lists while preserving order and removing duplicates.
def _merge_ip_parameters(existing: object, additions: list[str]) -> str:
    merged: list[str] = []
    if isinstance(existing, str):
        for item in existing.split(","):
            candidate = item.strip()
            if candidate and candidate not in merged:
                merged.append(candidate)
    for item in additions:
        if item and item not in merged:
            merged.append(item)
    return ",".join(merged)


# Generate the RCC property block for the standard MSI-to-PLL baseline used by the synthesized IOC model.
def _rcc_msi_pll_80mhz_properties(sysclk_hz: int | None) -> dict[str, object]:
    target_hz = sysclk_hz if isinstance(sysclk_hz, int) and sysclk_hz > 0 else 80_000_000
    vco_input_hz = 4_000_000
    pll_r_divider = 2
    pll_n = max(8, min(86, int((target_hz * pll_r_divider) / vco_input_hz)))
    vco_output_hz = vco_input_hz * pll_n
    pllclk_hz = int(vco_output_hz / pll_r_divider)
    bus_hz = target_hz if pllclk_hz == target_hz else pllclk_hz

    rcc_parameters = [
        "ADCFreq_Value",
        "AHBFreq_Value",
        "APB1Freq_Value",
        "APB1TimFreq_Value",
        "APB2Freq_Value",
        "APB2TimFreq_Value",
        "CortexFreq_Value",
        "DFSDMFreq_Value",
        "FCLKCortexFreq_Value",
        "FamilyName",
        "HCLKFreq_Value",
        "HSE_VALUE",
        "HSI_VALUE",
        "I2C1Freq_Value",
        "I2C2Freq_Value",
        "I2C3Freq_Value",
        "LPTIM1Freq_Value",
        "LPTIM2Freq_Value",
        "LPUART1Freq_Value",
        "LSCOPinFreq_Value",
        "LSI_VALUE",
        "MCO1PinFreq_Value",
        "MSI_VALUE",
        "PLLN",
        "PLLPoutputFreq_Value",
        "PLLQoutputFreq_Value",
        "PLLRCLKFreq_Value",
        "PLLSAI1PoutputFreq_Value",
        "PLLSAI1QoutputFreq_Value",
        "PLLSAI1RoutputFreq_Value",
        "PLLSAI2PoutputFreq_Value",
        "PLLSAI2RoutputFreq_Value",
        "PLLSourceVirtual",
        "PREFETCH_ENABLE",
        "PWRFreq_Value",
        "RCC_MCO1Source",
        "RCC_MCODiv",
        "RNGFreq_Value",
        "SAI1Freq_Value",
        "SAI2Freq_Value",
        "SDMMCFreq_Value",
        "SWPMI1Freq_Value",
        "SYSCLKFreq_VALUE",
        "SYSCLKSource",
        "UART4Freq_Value",
        "UART5Freq_Value",
        "USART1Freq_Value",
        "USART2Freq_Value",
        "USART3Freq_Value",
        "USBFreq_Value",
        "VCOInputFreq_Value",
        "VCOOutputFreq_Value",
        "VCOSAI1OutputFreq_Value",
        "VCOSAI2OutputFreq_Value",
    ]

    return {
        "RCC.IPParameters": ",".join(rcc_parameters),
        "RCC.ADCFreq_Value": 64_000_000,
        "RCC.AHBFreq_Value": bus_hz,
        "RCC.APB1Freq_Value": bus_hz,
        "RCC.APB1TimFreq_Value": bus_hz,
        "RCC.APB2Freq_Value": bus_hz,
        "RCC.APB2TimFreq_Value": bus_hz,
        "RCC.CortexFreq_Value": bus_hz,
        "RCC.DFSDMFreq_Value": bus_hz,
        "RCC.FCLKCortexFreq_Value": bus_hz,
        "RCC.HCLKFreq_Value": bus_hz,
        "RCC.I2C1Freq_Value": bus_hz,
        "RCC.I2C2Freq_Value": bus_hz,
        "RCC.I2C3Freq_Value": bus_hz,
        "RCC.LPTIM1Freq_Value": bus_hz,
        "RCC.LPTIM2Freq_Value": bus_hz,
        "RCC.LPUART1Freq_Value": bus_hz,
        "RCC.MCO1PinFreq_Value": bus_hz,
        "RCC.PLLN": pll_n,
        "RCC.PLLPoutputFreq_Value": vco_output_hz / 7,
        "RCC.PLLQoutputFreq_Value": vco_output_hz / 2,
        "RCC.PLLRCLKFreq_Value": bus_hz,
        "RCC.PLLSAI1PoutputFreq_Value": 18_285_714.285714287,
        "RCC.PLLSAI1QoutputFreq_Value": 64_000_000,
        "RCC.PLLSAI1RoutputFreq_Value": 64_000_000,
        "RCC.PLLSAI2PoutputFreq_Value": 18_285_714.285714287,
        "RCC.PLLSAI2RoutputFreq_Value": 64_000_000,
        "RCC.PLLSourceVirtual": "RCC_PLLSOURCE_MSI",
        "RCC.PWRFreq_Value": bus_hz,
        "RCC.RCC_MCO1Source": "RCC_MCO1SOURCE_SYSCLK",
        "RCC.RCC_MCODiv": "RCC_MCODIV_1",
        "RCC.RNGFreq_Value": 64_000_000,
        "RCC.SAI1Freq_Value": 18_285_714.285714287,
        "RCC.SAI2Freq_Value": 18_285_714.285714287,
        "RCC.SDMMCFreq_Value": 64_000_000,
        "RCC.SWPMI1Freq_Value": bus_hz,
        "RCC.SYSCLKFreq_VALUE": bus_hz,
        "RCC.SYSCLKSource": "RCC_SYSCLKSOURCE_PLLCLK",
        "RCC.UART4Freq_Value": bus_hz,
        "RCC.UART5Freq_Value": bus_hz,
        "RCC.USART1Freq_Value": bus_hz,
        "RCC.USART2Freq_Value": bus_hz,
        "RCC.USART3Freq_Value": bus_hz,
        "RCC.USBFreq_Value": 64_000_000,
        "RCC.VCOInputFreq_Value": vco_input_hz,
        "RCC.VCOOutputFreq_Value": vco_output_hz,
        "RCC.VCOSAI1OutputFreq_Value": 128_000_000,
        "RCC.VCOSAI2OutputFreq_Value": 128_000_000,
    }


def _target_register_channel(target_register: object) -> int | None:
    if not isinstance(target_register, str):
        return None
    match = re.fullmatch(r"CCR(?P<channel>\d+)", target_register.strip().upper())
    if match is None:
        return None
    return int(match.group("channel"))


def _dma_irq_property_value(priority: int = 0, subpriority: int = 0) -> str:
    return f"true\\:{priority}\\:{subpriority}\\:false\\:false\\:true\\:false\\:true"


def _reset_counter_hex_value(raw_value: object) -> int | None:
    if not isinstance(raw_value, str):
        return None
    candidate = raw_value.strip().upper()
    if not candidate.startswith("0X"):
        return None
    try:
        parsed = int(candidate, 16)
    except ValueError:
        return None
    if 0x3F <= parsed <= 0x7F:
        return parsed
    return None


# Search the watchdog timing space for the closest WWDG settings that satisfy the requested timeout and refresh behavior.
def _derive_wwdg_settings(
    *,
    clock_hz: int | None,
    timeout_ms: object,
    refresh_interval_ms: object,
    reset_counter_hex: object,
) -> dict[str, object]:
    default_settings = {
        "prescaler_enum": "WWDG_PRESCALER_8",
        "prescaler_divider": 8,
        "counter": 127,
        "window": 80,
        "ewi_mode": "WWDG_EWI_DISABLE",
        "assumed_apb1_divider": 2 if isinstance(clock_hz, int) and clock_hz >= 80_000_000 else 1,
    }

    if not isinstance(clock_hz, int) or clock_hz <= 0:
        return default_settings

    target_timeout_ms = float(timeout_ms) if isinstance(timeout_ms, (int, float)) and float(timeout_ms) > 0 else None
    target_refresh_ms = (
        float(refresh_interval_ms)
        if isinstance(refresh_interval_ms, (int, float)) and float(refresh_interval_ms) > 0
        else None
    )
    reset_counter = _reset_counter_hex_value(reset_counter_hex) or 0x3F

    best_candidate: dict[str, object] | None = None
    best_score = float("inf")
    for apb1_divider in (1, 2):
        pclk1_hz = clock_hz / float(apb1_divider)
        if pclk1_hz <= 0:
            continue
        for prescaler_divider in (1, 2, 4, 8):
            tick_ms = (4096.0 * prescaler_divider * 1000.0) / pclk1_hz
            for counter in range(max(reset_counter + 1, 0x40), 0x80):
                timeout_candidate_ms = float(counter + 1) * tick_ms
                for window in range(0x40, counter + 1):
                    refresh_candidate_ms = float(counter - window + 1) * tick_ms
                    score = 0.0
                    components = 0
                    if target_timeout_ms is not None:
                        score += abs(timeout_candidate_ms - target_timeout_ms) / max(target_timeout_ms, 1.0)
                        components += 1
                    if target_refresh_ms is not None:
                        score += abs(refresh_candidate_ms - target_refresh_ms) / max(target_refresh_ms, 1.0)
                        components += 1
                        if refresh_candidate_ms > target_refresh_ms:
                            score += 0.05
                    if components == 0:
                        score = abs(counter - 127) + abs(window - 103)
                    if score < best_score:
                        best_score = score
                        best_candidate = {
                            "prescaler_enum": f"WWDG_PRESCALER_{prescaler_divider}",
                            "prescaler_divider": prescaler_divider,
                            "counter": counter,
                            "window": window,
                            "ewi_mode": "WWDG_EWI_DISABLE",
                            "assumed_apb1_divider": apb1_divider,
                            "timeout_candidate_ms": round(timeout_candidate_ms, 3),
                            "refresh_candidate_ms": round(refresh_candidate_ms, 3),
                        }

    if best_candidate is not None:
        return best_candidate
    return default_settings


def _rtc_prescalers(clock_source: object) -> tuple[int, int]:
    if isinstance(clock_source, str) and clock_source.strip().upper() == "LSE":
        return (127, 255)
    return (127, 249)


# Compile the contract, board profile, and MCU metadata into the deterministic IOC model used by later mutation stages.
def build_ioc_model(
    contract: dict[str, object],
    board_profile: dict[str, object],
    mcu_metadata: dict[str, object],
) -> IocModel:
    target = contract["target"]
    defaults = contract["defaults"]
    interface_intents = contract.get("interface_intents", [])
    model = IocModel(
        board_id=str(target["board_id"]),
        target_mcu=str(target["mcu"]),
        grouped_mcu_name=str(mcu_metadata["grouped_mcu_name"]),
        grouped_xml_filename=str(mcu_metadata["grouped_xml_filename"]),
        toolchain=str(defaults.get("toolchain") or "STM32CubeIDE"),
        reserved_board_pins=list(mcu_metadata.get("reserved_board_pins", [])),
    )

    for intent in interface_intents:
        if not isinstance(intent, dict):
            continue
        if intent.get("type") == "clock" and intent.get("role") in {
            "system_clock",
            "rcc_clockconfig_baseline",
            "runtime_pll_source_switch",
        }:
            sysclk_hz = intent.get("sysclk_hz")
            if isinstance(sysclk_hz, (int, float)):
                _append_unique(model.clock_requirements, f"SYSCLK={int(sysclk_hz)}")
                model.codegen_hints.append(
                    f"Confirm the clock tree is configured for {int(sysclk_hz)} Hz before validating later increments."
                )
            if intent.get("role") == "rcc_clockconfig_baseline":
                mco_pin = str(intent.get("mco_pin") or "PA8").strip() or "PA8"
                clock_hz = int(sysclk_hz) if isinstance(sysclk_hz, (int, float)) else 80_000_000
                _append_unique(model.used_pins, mco_pin)
                _append_unique(model.required_peripherals, "RCC")
                model.bindings.append(
                    {
                        "type": "clock",
                        "role": "rcc_clockconfig_baseline",
                        "signals": {
                            mco_pin: "RCC_MCO",
                        },
                        "modes": {
                            mco_pin: "Clock-out",
                        },
                        "shared_properties": _rcc_msi_pll_80mhz_properties(clock_hz),
                    }
                )
                model.codegen_hints.append(
                    "Generate PA8 as MCO1 and keep the initial PLL source as MSI for the RCC ClockConfig baseline."
                )
            elif intent.get("role") == "runtime_pll_source_switch":
                _append_unique(model.required_peripherals, "RCC")
                model.codegen_hints.append(
                    "Preserve the RCC ClockConfig baseline while firmware layers runtime PLL source switching on top."
                )
        elif intent.get("type") == "watchdog" and intent.get("role") == "window_watchdog":
            instance = str(intent.get("instance") or "WWDG").strip() or "WWDG"
            _append_unique(model.required_peripherals, instance)
            _append_unique(model.used_pins, "VP_WWDG_VS_WWDG")

            wwdg_settings = _derive_wwdg_settings(
                clock_hz=_engineering_clock_hz(contract),
                timeout_ms=intent.get("timeout_ms"),
                refresh_interval_ms=intent.get("refresh_interval_ms"),
                reset_counter_hex=intent.get("reset_counter_hex"),
            )
            model.bindings.append(
                {
                    "type": "watchdog",
                    "role": "window_watchdog",
                    "instance": instance,
                    "signals": {
                        "VP_WWDG_VS_WWDG": "WWDG_VS_WWDG",
                    },
                    "modes": {
                        "VP_WWDG_VS_WWDG": "WWDG_Activate",
                    },
                    "peripheral_properties": {
                        "IPParameters": "Prescaler,Window,Counter,EWIMode",
                        "IPParametersWithoutCheck": "Prescaler,Window,Counter,EWIMode",
                        "Prescaler": str(wwdg_settings["prescaler_enum"]),
                        "Window": int(wwdg_settings["window"]),
                        "Counter": int(wwdg_settings["counter"]),
                        "EWIMode": str(wwdg_settings["ewi_mode"]),
                    },
                }
            )
            target_timeout_ms = intent.get("timeout_ms")
            target_refresh_ms = intent.get("refresh_interval_ms")
            if isinstance(target_timeout_ms, (int, float)) and isinstance(target_refresh_ms, (int, float)):
                model.codegen_hints.append(
                    f"Keep {instance} configured close to the requested {float(target_timeout_ms):.2f} ms timeout and {float(target_refresh_ms):.2f} ms refresh window while preserving the standalone watchdog-reset path."
                )
            else:
                model.codegen_hints.append(
                    f"Keep {instance} enabled with a generated refresh window so the later firmware increment can implement the requested watchdog-reset behavior."
                )
        elif intent.get("type") == "rtc" and intent.get("role") == "alarm_a":
            instance = str(intent.get("instance") or "RTC").strip() or "RTC"
            clock_source = str(intent.get("clock_source") or "LSI").strip().upper() or "LSI"
            asynch_prediv, synch_prediv = _rtc_prescalers(clock_source)

            _append_unique(model.required_peripherals, instance)
            _append_unique(model.used_pins, "VP_RTC_VS_RTC_Activate")
            _append_unique(model.used_pins, "VP_RTC_VS_RTC_Alarm_A_Intern")
            _append_unique(model.interrupt_requirements, "RTC_Alarm_IRQn")

            model.bindings.append(
                {
                    "type": "rtc",
                    "role": "alarm_a",
                    "instance": instance,
                    "signals": {
                        "VP_RTC_VS_RTC_Activate": "RTC_VS_RTC_Activate",
                        "VP_RTC_VS_RTC_Alarm_A_Intern": "RTC_VS_RTC_Alarm_A_Intern",
                    },
                    "modes": {
                        "VP_RTC_VS_RTC_Activate": "RTC_Enabled",
                        "VP_RTC_VS_RTC_Alarm_A_Intern": "Alarm A",
                    },
                    "peripheral_properties": {
                        "IPParameters": "HourFormat,AsynchPrediv,SynchPrediv,OutPut,OutPutPolarity,OutPutType",
                        "HourFormat": "RTC_HOURFORMAT_24",
                        "AsynchPrediv": asynch_prediv,
                        "SynchPrediv": synch_prediv,
                        "OutPut": "RTC_OUTPUT_DISABLE",
                        "OutPutPolarity": "RTC_OUTPUT_POLARITY_HIGH",
                        "OutPutType": "RTC_OUTPUT_TYPE_OPENDRAIN",
                    },
                    "shared_properties": {
                        "RCC.IPParameters": "RTCClockSelection,RTCFreq_Value",
                        "RCC.RTCClockSelection": f"RCC_RTCCLKSOURCE_{clock_source}",
                        "RCC.RTCFreq_Value": 32768 if clock_source == "LSE" else 32000,
                        "NVIC.RTC_Alarm_IRQn": "true\\:0\\:0\\:false\\:false\\:true\\:true\\:true",
                    },
                }
            )
            model.codegen_hints.append(
                f"Generate MX_{instance}_Init with {clock_source} as the RTC clock source so firmware can program the requested alarm window on top of a valid RTC baseline."
            )
        elif intent.get("type") == "power" and intent.get("role") == "low_power_run":
            run_mode_clock_hz = intent.get("run_mode_clock_hz")
            low_power_clock_hz = intent.get("low_power_clock_hz")
            enter_after_seconds = intent.get("enter_after_seconds")
            if isinstance(run_mode_clock_hz, (int, float)):
                model.codegen_hints.append(
                    f"Preserve a RUN-mode clock target of {int(run_mode_clock_hz)} Hz before entering Low Power Run."
                )
            if isinstance(low_power_clock_hz, (int, float)):
                model.codegen_hints.append(
                    f"Firmware must switch MSI to approximately {int(low_power_clock_hz)} Hz for Low Power Run."
                )
            if isinstance(enter_after_seconds, (int, float)):
                model.codegen_hints.append(
                    f"Firmware must enter Low Power Run about {float(enter_after_seconds):.2f} seconds after startup and repeat the cycle after button wakeup."
                )
            model.codegen_hints.append(
                "Low Power Run mode is a firmware behavior over the generated board baseline; keep the IOC valid and implement PWR/HAL state changes only in CubeMX user-code regions."
            )
        elif intent.get("type") == "analog" and intent.get("role") == "opamp_pga_signal_chain":
            dac_output_signal = intent.get("dac_output_signal")
            dac_output_pin = intent.get("dac_output_pin")
            opamp_output_pin = intent.get("opamp_output_pin")
            gain_values = intent.get("gain_values")
            if isinstance(dac_output_signal, str) and isinstance(dac_output_pin, str):
                model.codegen_hints.append(
                    f"Preserve the requested DAC waveform output {dac_output_signal} on {dac_output_pin} for the OPAMP PGA chain."
                )
            if isinstance(opamp_output_pin, str):
                model.codegen_hints.append(
                    f"Preserve the requested OPAMP amplified output on {opamp_output_pin}."
                )
            if isinstance(gain_values, list) and gain_values:
                model.codegen_hints.append(
                    "Firmware must support on-the-fly OPAMP PGA gain changes for values "
                    + ", ".join(str(value) for value in gain_values if isinstance(value, int))
                    + "."
                )
            if intent.get("requires_dac_dma_sine"):
                model.codegen_hints.append(
                    "Firmware and IOC support must provide DAC sinewave samples through DMA circular mode before OPAMP validation."
                )
            if intent.get("requires_cortex_sleep"):
                model.codegen_hints.append(
                    "Firmware must sequence OPAMP/DAC low-power modes while the Cortex enters sleep mode as requested."
                )
            model.codegen_hints.append(
                "OPAMP PGA signal-chain delivery needs analog peripheral IOC mapping and firmware sequencing beyond the current baseline IOC mutation path."
            )
        elif intent.get("type") == "lptim" and intent.get("role") == "external_counter_low_power_pwm":
            autoreload = intent.get("autoreload")
            pulse = intent.get("pulse")
            divider = intent.get("output_frequency_divider")
            duty_cycle = intent.get("duty_cycle_percent")
            if isinstance(autoreload, int):
                model.codegen_hints.append(
                    f"Preserve the requested LPTIM autoreload value {autoreload} for external-counter PWM generation."
                )
            if isinstance(pulse, int):
                model.codegen_hints.append(
                    f"Preserve the requested LPTIM pulse value {pulse}."
                )
            if isinstance(divider, int):
                model.codegen_hints.append(
                    f"The requested PWM output frequency is the external counter clock divided by {divider}."
                )
            if isinstance(duty_cycle, (int, float)):
                model.codegen_hints.append(
                    f"The requested LPTIM duty cycle is approximately {float(duty_cycle):.1f}%."
                )
            if intent.get("requires_stop_mode"):
                model.codegen_hints.append(
                    "Firmware must enter STOP mode after starting LPTIM PWM and wake on the configured button EXTI event."
                )
            if intent.get("requires_low_speed_gpio"):
                model.codegen_hints.append(
                    "GPIOs used by this low-power LPTIM flow should be configured for Low Speed where applicable."
                )
            model.codegen_hints.append(
                "LPTIM external-counter PWM needs peripheral-specific IOC mapping and firmware STOP-mode sequencing beyond the current baseline IOC mutation path."
            )
        elif intent.get("type") == "timer_pwm" and intent.get("role") in {"pwm_output", "complementary_pwm_output"}:
            instance = str(intent.get("instance") or "").strip()
            channel = intent.get("channel")
            if not instance or not isinstance(channel, int) or channel <= 0:
                continue

            complementary_output = bool(intent.get("complementary_output"))
            main_signal = f"{instance}_CH{channel}"
            main_pin = _select_pin_candidate(
                _signal_pin_candidates(mcu_metadata, main_signal),
                reserved_board_pins=model.reserved_board_pins,
                used_pins=model.used_pins,
            )
            if main_pin is None:
                continue

            _append_unique(model.required_peripherals, instance)
            _append_unique(model.used_pins, main_pin)

            channel_mode_name = _timer_channel_mode_name(channel, complementary_output=complementary_output)
            channel_property_name = _timer_channel_property_name(channel, complementary_output=complementary_output)
            signals: dict[str, str] = {}
            modes: dict[str, str] = {}
            shared_properties: dict[str, object] = {}

            if complementary_output:
                signals[main_pin] = f"S_{main_signal}"
                shared_properties[f"SH.S_{main_signal}.0"] = f"{main_signal},{channel_mode_name}"
                shared_properties[f"SH.S_{main_signal}.ConfNb"] = 1

                complementary_signal = f"{instance}_CH{channel}N"
                complementary_pin = _select_pin_candidate(
                    _signal_pin_candidates(mcu_metadata, complementary_signal),
                    reserved_board_pins=model.reserved_board_pins,
                    used_pins=model.used_pins,
                )
                if complementary_pin is not None:
                    _append_unique(model.used_pins, complementary_pin)
                    signals[complementary_pin] = complementary_signal
                    modes[complementary_pin] = channel_mode_name
            else:
                signals[main_pin] = main_signal
                modes[main_pin] = channel_mode_name

            clock_hz = _engineering_clock_hz(contract)
            frequency_hz = intent.get("frequency_hz")
            prescaler = int(intent.get("prescaler") or 0)
            repetition_counter = intent.get("repetition_counter")
            period = _derive_timer_period(clock_hz, frequency_hz, prescaler)
            pulse = _default_pwm_pulse(period)

            peripheral_properties: dict[str, object] = {
                channel_property_name: f"TIM_CHANNEL_{channel}",
                "IPParameters": _merge_ip_parameters(
                    None,
                    [
                        channel_property_name,
                        "Prescaler",
                        "Period",
                        "CounterMode",
                        "ClockDivision",
                        "AutoReloadPreload",
                        "OCMode_PWM",
                        "Pulse_3" if channel == 3 else f"Pulse_{channel}",
                        f"OCPolarity_{channel}",
                        f"OCNPolarity_{channel}",
                        "OCFastMode_PWM",
                        f"OCIdleState_{channel}",
                        f"OCNIdleState_{channel}",
                        "RepetitionCounter",
                    ],
                ),
                "Prescaler": prescaler,
                "CounterMode": "TIM_COUNTERMODE_UP",
                "ClockDivision": "TIM_CLOCKDIVISION_DIV1",
                "AutoReloadPreload": "TIM_AUTORELOAD_PRELOAD_DISABLE",
                "OCMode_PWM": "TIM_OCMODE_PWM1",
                f"OCPolarity_{channel}": "TIM_OCPOLARITY_HIGH",
                f"OCNPolarity_{channel}": "TIM_OCNPOLARITY_HIGH",
                "OCFastMode_PWM": "TIM_OCFAST_DISABLE",
                f"OCIdleState_{channel}": "TIM_OCIDLESTATE_RESET",
                f"OCNIdleState_{channel}": "TIM_OCNIDLESTATE_RESET",
            }
            pulse_property_name = "Pulse_3" if channel == 3 else f"Pulse_{channel}"
            if isinstance(period, int):
                peripheral_properties["Period"] = period
            if isinstance(pulse, int):
                peripheral_properties[pulse_property_name] = pulse
            if isinstance(repetition_counter, int):
                peripheral_properties["RepetitionCounter"] = repetition_counter

            model.bindings.append(
                {
                    "type": "timer_pwm",
                    "role": str(intent.get("role")),
                    "instance": instance,
                    "signals": signals,
                    "modes": modes,
                    "peripheral_properties": peripheral_properties,
                    "shared_properties": shared_properties,
                }
            )
            if isinstance(frequency_hz, (int, float)):
                model.codegen_hints.append(
                    f"Keep {instance} channel {channel} running as the core PWM increment at approximately {float(frequency_hz):.2f} Hz before layering DMA modulation."
                )
            if complementary_output:
                model.codegen_hints.append(
                    f"Preserve the complementary {instance} channel {channel} IOC routing so a later DMA increment can reuse the same PWM foundation."
                )
        elif intent.get("type") == "dma_binding" and intent.get("role") == "memory_to_timer_compare":
            peripheral = str(intent.get("peripheral") or "").strip()
            target_register = str(intent.get("target_register") or "").strip().upper()
            channel = _target_register_channel(target_register)
            if not peripheral or channel is None:
                model.compile_errors.append(
                    "The DMA increment is missing the timer peripheral or compare-register channel needed to build the IOC mutation."
                )
                continue

            request_name = f"{peripheral}_CH{channel}"
            dma_profiles = mcu_metadata.get("timer_dma_bindings")
            dma_profile = dma_profiles.get(request_name) if isinstance(dma_profiles, dict) else None
            if not isinstance(dma_profile, dict):
                model.compile_errors.append(
                    f"The IOC Builder has no DMA IOC profile for request '{request_name}' on board '{model.board_id}'."
                )
                continue

            _append_unique(model.required_peripherals, peripheral)
            _append_unique(model.required_peripherals, "DMA")

            dma_irq = dma_profile.get("dma_irq")
            shared_properties: dict[str, object] = {
                "Dma.Request0": str(dma_profile.get("dma_request_name") or request_name),
                "Dma.RequestsNb": 1,
                f"Dma.{request_name}.0.Instance": str(dma_profile["dma_instance"]),
                f"Dma.{request_name}.0.Direction": str(dma_profile["direction"]),
                f"Dma.{request_name}.0.PeriphInc": str(dma_profile["periph_inc"]),
                f"Dma.{request_name}.0.MemInc": str(dma_profile["mem_inc"]),
                f"Dma.{request_name}.0.PeriphDataAlignment": str(dma_profile["periph_data_alignment"]),
                f"Dma.{request_name}.0.MemDataAlignment": str(dma_profile["mem_data_alignment"]),
                f"Dma.{request_name}.0.Mode": str(dma_profile["mode"]),
                f"Dma.{request_name}.0.Priority": str(dma_profile["priority"]),
                f"Dma.{request_name}.0.Polarity": str(dma_profile["polarity"]),
                f"Dma.{request_name}.0.RequestNumber": int(dma_profile["request_number"]),
                f"Dma.{request_name}.0.RequestParameters": str(dma_profile["request_parameters"]),
                f"Dma.{request_name}.0.SignalID": str(dma_profile["signal_id"]),
                f"Dma.{request_name}.0.SyncEnable": str(dma_profile["sync_enable"]),
                f"Dma.{request_name}.0.SyncPolarity": str(dma_profile["sync_polarity"]),
                f"Dma.{request_name}.0.SyncRequestNumber": int(dma_profile["sync_request_number"]),
                f"Dma.{request_name}.0.SyncSignalID": str(dma_profile["sync_signal_id"]),
                f"Dma.{request_name}.0.EventEnable": str(dma_profile["event_enable"]),
            }
            if isinstance(dma_irq, str) and dma_irq.strip():
                shared_properties[f"NVIC.{dma_irq}"] = _dma_irq_property_value()
                _append_unique(model.interrupt_requirements, dma_irq)

            model.bindings.append(
                {
                    "type": "dma_binding",
                    "role": str(intent.get("role")),
                    "instance": "Dma",
                    "shared_properties": shared_properties,
                }
            )
            reference = dma_profile.get("reference")
            if isinstance(reference, str) and reference.strip():
                model.codegen_hints.append(
                    f"Keep the DMA wiring aligned with the official {reference} request shape while layering CCR{channel} updates onto {peripheral}."
                )
            else:
                model.codegen_hints.append(
                    f"Keep the DMA wiring aligned with the established {request_name} request shape while layering compare-register updates onto {peripheral}."
                )
        elif intent.get("type") == "uart" and intent.get("role") in {"device_to_pc_tx", "debug_console"}:
            uart_profile = board_profile["uart_host_console"]
            instance = str(intent.get("instance_preference") or uart_profile["instance"])
            tx_pin = str(uart_profile["tx_pin"])
            rx_pin = str(uart_profile["rx_pin"])
            uart_role = str(intent.get("role"))
            _append_unique(model.required_peripherals, instance)
            _append_unique(model.used_pins, tx_pin)
            _append_unique(model.used_pins, rx_pin)
            model.generated_labels[tx_pin] = "USART_TX"
            model.generated_labels[rx_pin] = "USART_RX"
            model.bindings.append(
                {
                    "type": "uart",
                    "role": uart_role,
                    "instance": instance,
                    "signals": {
                        tx_pin: f"{instance}_TX",
                        rx_pin: f"{instance}_RX",
                    },
                    "modes": {
                        tx_pin: str(uart_profile["gpio_mode"]),
                        rx_pin: str(uart_profile["gpio_mode"]),
                    },
                    "labels": {
                        tx_pin: "USART_TX",
                        rx_pin: "USART_RX",
                    },
                    "peripheral_properties": {
                        "IPParameters": "VirtualMode-Asynchronous,BaudRate",
                        "VirtualMode-Asynchronous": "VM_ASYNC",
                        "BaudRate": int(intent.get("baud_rate") or 115200),
                    },
                }
            )
            if uart_role == "debug_console":
                model.codegen_hints.append(
                    f"Generate MX_{instance}_UART_Init so a later firmware increment can gate host-visible debug prints behind the requested macro guard."
                )
            else:
                model.codegen_hints.append(
                    f"Generate MX_{instance}_UART_Init and a simple transmit smoke path for host-side verification."
                )
        elif intent.get("type") == "gpio" and intent.get("role") == "led_output":
            led_profile = board_profile["user_led"]
            pin_name = str(intent.get("pin") or led_profile["pin"])
            _append_unique(model.used_pins, pin_name)
            model.generated_labels[pin_name] = str(intent.get("label") or led_profile["label"])
            model.bindings.append(
                {
                    "type": "gpio",
                    "role": "led_output",
                    "signals": {
                        pin_name: str(intent.get("signal") or led_profile["signal"]),
                    },
                    "labels": {
                        pin_name: str(intent.get("label") or led_profile["label"]),
                    },
                }
            )
            model.codegen_hints.append("Generate MX_GPIO_Init and drive the user LED from firmware as the first visible runtime check.")
        elif intent.get("type") == "gpio_exti" and intent.get("role") == "user_button":
            button_profile = board_profile["user_button"]
            pin_name = str(intent.get("pin") or button_profile["pin"])
            _append_unique(model.used_pins, pin_name)
            _append_unique(model.interrupt_requirements, "EXTI15_10_IRQn")
            model.generated_labels[pin_name] = str(intent.get("label") or button_profile["label"])
            model.bindings.append(
                {
                    "type": "gpio_exti",
                    "role": "user_button",
                    "signals": {
                        pin_name: str(intent.get("signal") or button_profile["signal"]),
                    },
                    "labels": {
                        pin_name: str(intent.get("label") or button_profile["label"]),
                    },
                    "shared_properties": {
                        "SH.GPXTI13.0": "GPIO_EXTI13",
                        "SH.GPXTI13.ConfNb": 1,
                        "NVIC.EXTI15_10_IRQn": "true\\:0\\:0\\:false\\:false\\:true\\:true\\:true",
                    },
                }
            )
            model.codegen_hints.append("Generate the EXTI user button path so firmware can react to a hardware event.")

    return model
