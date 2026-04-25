from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from stm32cubep_mcp.knowledge.cubemx_db import (
    build_cubemx_db_index,
    dma_request_mappings,
    find_board_baseline,
    find_mcu,
    list_board_iocs,
    list_family_config_files,
    pins_for_signal,
    signals_for_pin,
)


class CubeMxDbIndexTests(unittest.TestCase):
    def _write_fixture_db(self, root: Path) -> None:
        boards_root = root / "plugins" / "boardmanager" / "boards"
        mcu_root = root / "mcu"
        config_root = mcu_root / "config"
        ll_root = config_root / "llConfig"
        boards_root.mkdir(parents=True)
        ll_root.mkdir(parents=True)

        (boards_root / "B40_Nucleo_NUCLEO-L476RG_STM32L476RG_Board_AllConfig.ioc").write_text(
            "\n".join(
                [
                    "#MicroXplorer Configuration settings - do not modify",
                    "Mcu.Name=STM32L476R(C-E-G)Tx",
                    "ProjectManager.ProjectName=NUCLEO-L476RG",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        (mcu_root / "STM32L476R(C-E-G)Tx.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<Mcu ClockTree="STM32L4" DBVersion="V3.0" Family="STM32L4" Line="STM32L4x6" Package="LQFP64" RefName="STM32L476R(C-E-G)Tx" xmlns="http://mcd.rou.st.com/modules.php?name=mcu">
  <IP InstanceName="RCC" Name="RCC" Version="STM32L4_rcc_v1_0"/>
  <IP ConfigFile="TIM-STM32L4xx" InstanceName="TIM1" Name="TIM1_8L4" Version="gptimer2_v3_x_Cube"/>
  <IP InstanceName="USART2" Name="USART" Version="sci3_v1_1_Cube"/>
  <Pin Name="PA2"><Signal Name="USART2_TX"/></Pin>
  <Pin Name="PA3"><Signal Name="USART2_RX"/></Pin>
  <Pin Name="PA10"><Signal Name="TIM1_CH3"/></Pin>
</Mcu>
""",
            encoding="utf-8",
        )

        (config_root / "TIM-STM32L4xx_Configs.xml").write_text("<IP Name=\"TIM\"/>", encoding="utf-8")
        (config_root / "DMA-STM32L4xx_Configs.xml").write_text("<IP Name=\"DMA\"/>", encoding="utf-8")
        (ll_root / "DMA-STM32L4xx_DefMapping.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<Root>
  <Item Name="Request" NewName="PeriphRequest" NewValue="LL_DMAMUX_REQ_TIM1_CH3" Type="RefParameter" Value="DMA_REQUEST_TIM1_CH3"/>
</Root>
""",
            encoding="utf-8",
        )

    def test_build_cubemx_db_index_collects_board_mcu_and_dma_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_root = Path(temp_dir) / "db"
            cache_root = Path(temp_dir) / "cache"
            self._write_fixture_db(db_root)

            index = build_cubemx_db_index(db_root=db_root, cache_root=cache_root)

            self.assertEqual(index["index_version"], "2026-04-25.phase1.v1")
            self.assertEqual(len(list_board_iocs(index)), 1)
            self.assertIsNotNone(find_board_baseline(index, "NUCLEO-L476RG"))
            self.assertIsNotNone(find_mcu(index, "STM32L476R(C-E-G)Tx"))
            self.assertEqual(signals_for_pin(index, "STM32L476R(C-E-G)Tx", "PA2"), ["USART2_TX"])
            self.assertEqual(pins_for_signal(index, "STM32L476R(C-E-G)Tx", "TIM1_CH3"), ["PA10"])
            self.assertEqual(sorted(list_family_config_files(index, "STM32L4xx")), ["DMA-STM32L4xx_Configs.xml", "TIM-STM32L4xx_Configs.xml"])

            dma_entries = dma_request_mappings(index, "STM32L4xx")
            self.assertEqual(len(dma_entries), 1)
            self.assertEqual(dma_entries[0]["Value"], "DMA_REQUEST_TIM1_CH3")
            self.assertTrue((cache_root / "cubemx_db_index.json").is_file())
            cached_index = json.loads((cache_root / "cubemx_db_index.json").read_text(encoding="utf-8"))
            self.assertEqual(cached_index["index_version"], index["index_version"])


if __name__ == "__main__":
    unittest.main()
