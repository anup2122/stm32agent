from __future__ import annotations

from copy import deepcopy
import re

from ..ioc.db_index import local_cubemx_db_index
from ..knowledge.cubemx_db import dma_request_mappings, find_mcu, list_family_config_files

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
            "WWDG": {
                "instance": "WWDG",
                "ip_parameters": ["Prescaler", "Window", "Counter", "EWIMode"],
            },
            "RTC": {
                "instance": "RTC",
                "ip_parameters": [
                    "HourFormat",
                    "AsynchPrediv",
                    "SynchPrediv",
                    "OutPut",
                    "OutPutPolarity",
                    "OutPutType",
                ],
            },
        },
        "pin_capabilities": {
            "PA2": ["USART2_TX"],
            "PA3": ["USART2_RX"],
            "PA5": ["GPIO_Output"],
            "PC13": ["GPXTI13"],
            "PA13": ["SYS_JTMS-SWDIO"],
            "PA14": ["SYS_JTCK-SWCLK"],
            "VP_WWDG_VS_WWDG": ["WWDG_VS_WWDG"],
            "VP_RTC_VS_RTC_Activate": ["RTC_VS_RTC_Activate"],
            "VP_RTC_VS_RTC_Alarm_A_Intern": ["RTC_VS_RTC_Alarm_A_Intern"],
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
        "timer_dma_bindings": {
            "TIM1_CH3": {
                "dma_request_name": "TIM1_CH3",
                "dma_instance": "DMA1_Channel7",
                "dma_irq": "DMA1_Channel7_IRQn",
                "direction": "DMA_MEMORY_TO_PERIPH",
                "periph_inc": "DMA_PINC_DISABLE",
                "mem_inc": "DMA_MINC_ENABLE",
                "periph_data_alignment": "DMA_PDATAALIGN_WORD",
                "mem_data_alignment": "DMA_MDATAALIGN_WORD",
                "mode": "DMA_CIRCULAR",
                "priority": "DMA_PRIORITY_HIGH",
                "polarity": "HAL_DMAMUX_REQUEST_GEN_RISING",
                "request_number": 1,
                "request_parameters": (
                    "Instance,Direction,PeriphInc,MemInc,PeriphDataAlignment,"
                    "MemDataAlignment,Mode,Priority,SignalID,Polarity,RequestNumber,"
                    "SyncSignalID,SyncPolarity,SyncEnable,EventEnable,SyncRequestNumber"
                ),
                "signal_id": "NONE",
                "sync_enable": "DISABLE",
                "sync_polarity": "HAL_DMAMUX_SYNC_NO_EVENT",
                "sync_request_number": 1,
                "sync_signal_id": "NONE",
                "event_enable": "DISABLE",
                "reference": "STM32Cube_FW_L4_V1.18.2/TIM/TIM_DMA",
            },
        },
    },
}


def _family_key_candidates(metadata: dict[str, object], entry: dict[str, object]) -> list[str]:
    candidates: list[str] = []

    for raw_value in (
        entry.get("line"),
        entry.get("family"),
        metadata.get("grouped_xml_filename"),
    ):
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        upper_value = raw_value.upper()
        if upper_value.startswith("STM32L4") and "STM32L4XX" not in candidates:
            candidates.append("STM32L4xx")

    return candidates


def _shared_signal_aliases(signal_name: str) -> list[str]:
    aliases: list[str] = []
    if re.fullmatch(r"TIM\d+_(?:CH\d+|ETR)", signal_name, flags=re.IGNORECASE):
        aliases.append(f"S_{signal_name}")
    return aliases


def _merge_dynamic_cubemx_db_metadata(metadata: dict[str, object]) -> dict[str, object]:
    grouped_mcu_name = metadata.get("grouped_mcu_name")
    requested_mcu = metadata.get("requested_mcu")
    index = local_cubemx_db_index()

    entry = None
    if isinstance(grouped_mcu_name, str) and grouped_mcu_name.strip():
        entry = find_mcu(index, grouped_mcu_name)
    if entry is None and isinstance(requested_mcu, str) and requested_mcu.strip():
        entry = find_mcu(index, requested_mcu)
    if entry is None:
        return metadata

    pin_capabilities = metadata.get("pin_capabilities", {})
    if not isinstance(pin_capabilities, dict):
        pin_capabilities = {}
        metadata["pin_capabilities"] = pin_capabilities

    signal_pins = entry.get("signal_pins")
    if isinstance(signal_pins, dict):
        metadata["signal_pins"] = deepcopy(signal_pins)

    pin_signals = entry.get("pin_signals")
    if isinstance(pin_signals, dict):
        metadata["pin_signals"] = deepcopy(pin_signals)
        for pin_name, signals in pin_signals.items():
            if not isinstance(pin_name, str) or not isinstance(signals, list):
                continue
            merged_signals = [
                signal_name
                for signal_name in pin_capabilities.get(pin_name, [])
                if isinstance(signal_name, str)
            ]
            for signal_name in signals:
                if not isinstance(signal_name, str):
                    continue
                if signal_name not in merged_signals:
                    merged_signals.append(signal_name)
                for alias in _shared_signal_aliases(signal_name):
                    if alias not in merged_signals:
                        merged_signals.append(alias)
            pin_capabilities[pin_name] = merged_signals

    peripherals = metadata.get("peripherals", {})
    if not isinstance(peripherals, dict):
        peripherals = {}
        metadata["peripherals"] = peripherals

    ips = entry.get("ips")
    if isinstance(ips, list):
        metadata["available_ips"] = [ip for ip in ips if isinstance(ip, str)]
        for instance_name in metadata["available_ips"]:
            peripherals.setdefault(instance_name, {"instance": instance_name})

    metadata["family"] = entry.get("family")
    metadata["line"] = entry.get("line")
    metadata["package"] = entry.get("package")
    metadata["cubemx_db_resolved"] = True

    family_key: str | None = None
    for candidate in _family_key_candidates(metadata, entry):
        config_files = list_family_config_files(index, candidate)
        if config_files:
            family_key = candidate
            metadata["family_config_files"] = config_files
            metadata["dma_request_mappings"] = dma_request_mappings(index, candidate)
            break
    if family_key is not None:
        metadata["family_key"] = family_key

    return metadata


def resolve_mcu_metadata(board_id: str, mcu_name: str) -> dict[str, object] | None:
    metadata = MCU_METADATA_BY_BOARD.get(board_id)
    if metadata is None:
        return None
    resolved = deepcopy(metadata)
    resolved["requested_mcu"] = mcu_name
    return _merge_dynamic_cubemx_db_metadata(resolved)
