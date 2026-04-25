from __future__ import annotations

from copy import deepcopy

BOARD_PROFILES = {
    "NUCLEO-L476RG": {
        "mcu": "STM32L476RGTx",
        "seed_mcu_name": "STM32L476R(C-E-G)Tx",
        "uart_host_console": {
            "instance": "USART2",
            "tx_pin": "PA2",
            "rx_pin": "PA3",
            "gpio_mode": "Asynchronous",
        },
        "user_led": {
            "pin": "PA5",
            "signal": "GPIO_Output",
            "label": "LD2 [green Led]",
        },
        "user_button": {
            "pin": "PC13",
            "signal": "GPXTI13",
            "label": "B1 [Blue PushButton]",
        },
    },
}

OFFICIAL_BOARD_SEEDS = {
    "NUCLEO-L476RG": [
        "File.Version=6",
        "Mcu.Family=STM32L4",
        "Mcu.Name=STM32L476R(C-E-G)Tx",
        "Mcu.IP0=NVIC",
        "Mcu.IP1=RCC",
        "Mcu.IP2=SYS",
        "Mcu.IP3=USART2",
        "Mcu.IPNb=4",
        "Mcu.Pin0=PC13",
        "Mcu.Pin1=PC14-OSC32_IN",
        "Mcu.Pin2=PC15-OSC32_OUT",
        "Mcu.Pin3=PH0-OSC_IN",
        "Mcu.Pin4=PH1-OSC_OUT",
        "Mcu.Pin5=PA2",
        "Mcu.Pin6=PA3",
        "Mcu.Pin7=PA5",
        "Mcu.Pin8=PA13",
        "Mcu.Pin9=PA14",
        "Mcu.Pin10=PB3",
        "Mcu.Pin11=VP_SYS_VS_Systick",
        "Mcu.PinsNb=12",
        "PA2.GPIOParameters=GPIO_Label",
        "PA2.GPIO_Label=USART_TX",
        "PA2.Mode=Asynchronous",
        "PA2.Signal=USART2_TX",
        "PA3.GPIOParameters=GPIO_Label",
        "PA3.GPIO_Label=USART_RX",
        "PA3.Mode=Asynchronous",
        "PA3.Signal=USART2_RX",
        "PA5.GPIOParameters=GPIO_Label",
        "PA5.GPIO_Label=LD2 [green Led]",
        "PA5.Signal=GPIO_Output",
        "PC13.GPIOParameters=GPIO_Label",
        "PC13.GPIO_Label=B1 [Blue PushButton]",
        "PC13.Signal=GPXTI13",
        "SH.GPXTI13.0=GPIO_EXTI13",
        "SH.GPXTI13.ConfNb=1",
        "ProjectManager.ToolChain=STM32CubeIDE",
        "ProjectManager.TargetToolchain=STM32CubeIDE",
        "board=NUCLEO-L476RG",
        "boardIOC=true",
    ],
}


def get_board_profile(board_id: str) -> dict[str, object] | None:
    profile = BOARD_PROFILES.get(board_id)
    if profile is None:
        return None
    return deepcopy(profile)


def get_board_seed_lines(board_id: str) -> list[str] | None:
    seed_lines = OFFICIAL_BOARD_SEEDS.get(board_id)
    if seed_lines is None:
        return None
    return list(seed_lines)