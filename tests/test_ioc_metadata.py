from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stm32cubep_mcp.ioc import metadata


class IocMetadataTests(unittest.TestCase):
    def test_parse_ioc_properties_skips_comments_and_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ioc_path = Path(temp_dir) / "board.ioc"
            ioc_path.write_text(
                "\n".join([
                    "# comment",
                    "",
                    "ProjectManager.ProjectName=board",
                    "Mcu.Name=STM32L476RGTx",
                ]),
                encoding="utf-8",
            )

            result = metadata.parse_ioc_properties(ioc_path)

        self.assertEqual(result["ProjectManager.ProjectName"], "board")
        self.assertEqual(result["Mcu.Name"], "STM32L476RGTx")
        self.assertNotIn("# comment", result)

    def test_summarize_ioc_collects_pins_labels_and_peripherals(self) -> None:
        ioc_path = Path("C:/work/board.ioc")
        properties = {
            "File.Version": "6",
            "MxCube.Version": "6.11.0",
            "Mcu.Name": "STM32L476RGTx",
            "ProjectManager.ProjectName": "board",
            "ProjectManager.ToolChain": "STM32CubeIDE",
            "PA2.Signal": "USART2_TX",
            "PA2.GPIO_Label": "VCP_TX",
            "IP0": "USART2",
        }

        result = metadata.summarize_ioc(ioc_path, properties)

        self.assertEqual(result["ioc_file"], "board.ioc")
        self.assertEqual(result["project"]["name"], "board")
        self.assertIn("USART2", result["peripherals"])
        self.assertEqual(result["gpio_labels"]["PA2"], "VCP_TX")
        self.assertEqual(result["pins"][0]["signal"], "USART2_TX")


if __name__ == "__main__":
    unittest.main()
