from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from stm32cubep_mcp import server

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIRMWARE_PATH = WORKSPACE_ROOT / "UART_ReceptionToIdle_CircularDMA.axf"
MISMATCH_FIRMWARE_PATH = WORKSPACE_ROOT / "XNUCLEO-F103RB-binary.axf"
RUN_INTEGRATION = os.environ.get("STM32CUBEP_RUN_INTEGRATION") == "1"


@unittest.skipUnless(RUN_INTEGRATION, "Set STM32CUBEP_RUN_INTEGRATION=1 to run hardware integration tests.")
class HardwareIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        firmware_path = Path(os.environ.get("STM32CUBEP_TEST_FIRMWARE", str(DEFAULT_FIRMWARE_PATH)))
        if not firmware_path.is_file():
            raise unittest.SkipTest(f"Firmware file not found: {firmware_path}")
        cls.firmware_path = firmware_path
        cls.mismatch_firmware_path = MISMATCH_FIRMWARE_PATH
        if not cls.mismatch_firmware_path.is_file():
            raise unittest.SkipTest(f"Mismatch firmware file not found: {cls.mismatch_firmware_path}")

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.firmware_path.is_file():
            restore_result = server.stm32_flash_firmware(file_path=str(cls.firmware_path), timeout_seconds=300)
            if not restore_result["success"]:
                raise AssertionError(json.dumps(restore_result, indent=2))

    def assertSuccessfulResult(self, result: dict[str, object], operation: str) -> None:
        self.assertTrue(result["success"], msg=json.dumps(result, indent=2))
        self.assertEqual(result["operation"], operation)
        self.assertTrue(Path(str(result["log_file"])).is_file())

    def test_programmer_version_real(self) -> None:
        result = server.stm32_programmer_version(timeout_seconds=15)
        self.assertSuccessfulResult(result, "programmer_version")
        self.assertIn("STM32CubeProgrammer version", str(result["stdout"]))

    def test_connect_real(self) -> None:
        result = server.connect_to_attached_stm32_device(timeout_seconds=30)
        self.assertSuccessfulResult(result, "connect")
        self.assertIn("Device name", str(result["stdout"]))

    def test_download_real_axf(self) -> None:
        result = server.stm32_download(file_path=str(self.firmware_path), timeout_seconds=240)
        self.assertSuccessfulResult(result, "download")
        self.assertIn("--download", result["command"])

    def test_flash_firmware_real(self) -> None:
        result = server.stm32_flash_firmware(file_path=str(self.firmware_path), timeout_seconds=300)
        self.assertSuccessfulResult(result, "flash_firmware")
        self.assertIn("--erase", result["command"])
        self.assertIn("--download", result["command"])
        self.assertIn("--go", result["command"])

    def test_go_real_after_download(self) -> None:
        result = server.stm32_go(timeout_seconds=30)
        self.assertSuccessfulResult(result, "go")

    def test_wrong_target_flash_reports_mismatch(self) -> None:
        result = server.stm32_flash_firmware(file_path=str(self.mismatch_firmware_path), timeout_seconds=300)
        self.assertFalse(result["success"], msg=json.dumps(result, indent=2))
        self.assertEqual(result["message"], "this does not match to the attached target")
        self.assertIn("target_mismatch", result)
        self.assertIn("Core is halted", str(result["post_action_check"]["stdout"]))

