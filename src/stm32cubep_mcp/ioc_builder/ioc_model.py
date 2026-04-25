from __future__ import annotations

from dataclasses import asdict, dataclass, field


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

    def to_summary(self) -> dict[str, object]:
        payload = asdict(self)
        payload["used_pins"] = sorted(dict.fromkeys(self.used_pins))
        payload["required_peripherals"] = sorted(dict.fromkeys(self.required_peripherals))
        return payload


def _append_unique(sequence: list[str], value: str) -> None:
    if value not in sequence:
        sequence.append(value)


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
        if intent.get("type") == "uart" and intent.get("role") == "device_to_pc_tx":
            uart_profile = board_profile["uart_host_console"]
            instance = str(intent.get("instance_preference") or uart_profile["instance"])
            tx_pin = str(uart_profile["tx_pin"])
            rx_pin = str(uart_profile["rx_pin"])
            _append_unique(model.required_peripherals, instance)
            _append_unique(model.used_pins, tx_pin)
            _append_unique(model.used_pins, rx_pin)
            model.generated_labels[tx_pin] = "USART_TX"
            model.generated_labels[rx_pin] = "USART_RX"
            model.bindings.append(
                {
                    "type": "uart",
                    "role": "device_to_pc_tx",
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
            model.codegen_hints.append(f"Generate MX_{instance}_UART_Init and a simple transmit smoke path for host-side verification.")
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
            _append_unique(model.interrupt_requirements, "GPIO_EXTI13")
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
                    },
                }
            )
            model.codegen_hints.append("Generate the EXTI user button path so firmware can react to a hardware event.")

    return model