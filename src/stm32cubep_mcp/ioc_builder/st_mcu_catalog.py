from __future__ import annotations

from copy import deepcopy

MCU_METADATA_BY_BOARD = {
    "NUCLEO-L476RG": {
        "target_mcu": "STM32L476RGTx",
        "grouped_mcu_name": "STM32L476R(C-E-G)Tx",
        "grouped_xml_filename": "STM32L476R(C-E-G)Tx.xml",
        "peripherals": {
            "USART2": {
                "pins": {
                    "tx": "PA2",
                    "rx": "PA3",
                },
                "ip_parameters": ["VirtualMode-Asynchronous", "BaudRate"],
            },
        },
        "pin_capabilities": {
            "PA2": ["USART2_TX"],
            "PA3": ["USART2_RX"],
            "PA5": ["GPIO_Output"],
            "PC13": ["GPXTI13"],
            "PA13": ["SYS_JTMS-SWDIO"],
            "PA14": ["SYS_JTCK-SWCLK"],
        },
        "gpio_modes": ["Asynchronous"],
        "ip_option_values": {
            "USART2.VirtualMode-Asynchronous": ["VM_ASYNC"],
        },
        "reserved_board_pins": [
            "PC13",
            "PC14-OSC32_IN",
            "PC15-OSC32_OUT",
            "PH0-OSC_IN",
            "PH1-OSC_OUT",
            "PA5",
            "PA13",
            "PA14",
            "PB3",
            "VP_SYS_VS_Systick",
        ],
    },
}


def resolve_mcu_metadata(board_id: str, mcu_name: str) -> dict[str, object] | None:
    metadata = MCU_METADATA_BY_BOARD.get(board_id)
    if metadata is None:
        return None
    resolved = deepcopy(metadata)
    resolved["requested_mcu"] = mcu_name
    return resolved