from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stm32cubep_mcp.debug import server


class FakePopen:
    def __init__(self, command: list[str], **kwargs: object) -> None:
        self.command = command
        self.kwargs = kwargs
        self.pid = 4242
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: int | None = None) -> int:
        if self.returncode is None:
            raise subprocess.TimeoutExpired(cmd=self.command, timeout=timeout or 0)
        return self.returncode


class DebugServerSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        server.cleanup_all_sessions()

    def tearDown(self) -> None:
        server.cleanup_all_sessions()

    def sample_tools_config(self, tool_path: str) -> dict[str, object]:
        gdb_path = str(Path(tool_path).with_name("arm-none-eabi-gdb.exe"))
        return {
            "data": {
                "tools": {
                    "stlink_gdb_server": {
                        "env_var": "STM32_STLINK_GDB_SERVER_PATH",
                        "executable_name": "ST-LINK_gdbserver.exe",
                        "candidates": {
                            "windows": [tool_path],
                        },
                    },
                    "arm_gdb": {
                        "env_var": "STM32_ARM_GDB_PATH",
                        "executable_name": "arm-none-eabi-gdb.exe",
                        "candidates": {
                            "windows": [gdb_path],
                        },
                    }
                }
            }
        }

    def sample_project_metadata(self) -> dict[str, object]:
        return {
            "data": {
                "board": {
                    "mcu": "STM32L476RG",
                    "connect_defaults": {
                        "frequency_khz": 4000,
                    }
                },
                "build": {
                    "artifact": str(Path.cwd() / "UART_ReceptionToIdle_CircularDMA.axf"),
                },
                "debug": {
                    "server": "stlink-gdb-server",
                    "elf_path": "UART_ReceptionToIdle_CircularDMA.axf",
                    "gdb_port": 55001,
                    "swo_port": 55002,
                },
            }
        }

    def sample_svd_text(self) -> str:
        return """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<device>
    <name>STM32L476</name>
    <peripherals>
        <peripheral>
            <name>USART1</name>
            <baseAddress>0x40013800</baseAddress>
            <registers>
                <register>
                    <name>CR1</name>
                    <addressOffset>0x0</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>RE</name><bitOffset>2</bitOffset><bitWidth>1</bitWidth></field>
                        <field><name>TE</name><bitOffset>3</bitOffset><bitWidth>1</bitWidth></field>
                        <field><name>PCE</name><bitOffset>10</bitOffset><bitWidth>1</bitWidth></field>
                        <field><name>OVER8</name><bitOffset>15</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
                <register>
                    <name>CR2</name>
                    <addressOffset>0x4</addressOffset>
                    <size>32</size>
                </register>
                <register>
                    <name>CR3</name>
                    <addressOffset>0x8</addressOffset>
                    <size>32</size>
                </register>
                <register>
                    <name>BRR</name>
                    <addressOffset>0xC</addressOffset>
                    <size>32</size>
                </register>
            </registers>
        </peripheral>
        <peripheral>
            <name>RCC</name>
            <baseAddress>0x40021000</baseAddress>
            <registers>
                <register><name>CR</name><addressOffset>0x0</addressOffset><size>32</size></register>
                <register>
                    <name>CFGR</name>
                    <addressOffset>0x8</addressOffset>
                    <size>32</size>
                    <fields>
                        <field>
                            <name>SWS</name>
                            <bitOffset>2</bitOffset>
                            <bitWidth>2</bitWidth>
                            <enumeratedValues>
                                <enumeratedValue><name>MSI</name><value>0</value></enumeratedValue>
                                <enumeratedValue><name>HSI16</name><value>1</value></enumeratedValue>
                                <enumeratedValue><name>HSE</name><value>2</value></enumeratedValue>
                                <enumeratedValue><name>PLL</name><value>3</value></enumeratedValue>
                            </enumeratedValues>
                        </field>
                        <field><name>HPRE</name><bitOffset>4</bitOffset><bitWidth>4</bitWidth></field>
                        <field><name>PPRE1</name><bitOffset>8</bitOffset><bitWidth>3</bitWidth></field>
                        <field><name>PPRE2</name><bitOffset>11</bitOffset><bitWidth>3</bitWidth></field>
                    </fields>
                </register>
                <register><name>PLLCFGR</name><addressOffset>0xC</addressOffset><size>32</size></register>
                <register><name>CCIPR</name><addressOffset>0x88</addressOffset><size>32</size></register>
            </registers>
        </peripheral>
        <peripheral>
            <name>SPI1</name>
            <baseAddress>0x40013000</baseAddress>
            <registers>
                <register>
                    <name>CR1</name>
                    <addressOffset>0x0</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>CPHA</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>
                        <field><name>CPOL</name><bitOffset>1</bitOffset><bitWidth>1</bitWidth></field>
                        <field><name>MSTR</name><bitOffset>2</bitOffset><bitWidth>1</bitWidth></field>
                        <field><name>BR</name><bitOffset>3</bitOffset><bitWidth>3</bitWidth></field>
                        <field><name>SPE</name><bitOffset>6</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
            </registers>
        </peripheral>
        <peripheral>
            <name>I2C1</name>
            <baseAddress>0x40005400</baseAddress>
            <registers>
                <register>
                    <name>CR1</name>
                    <addressOffset>0x0</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>PE</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
                <register>
                    <name>TIMINGR</name>
                    <addressOffset>0x10</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>SCLL</name><bitOffset>0</bitOffset><bitWidth>8</bitWidth></field>
                        <field><name>SCLH</name><bitOffset>8</bitOffset><bitWidth>8</bitWidth></field>
                        <field><name>SDADEL</name><bitOffset>16</bitOffset><bitWidth>4</bitWidth></field>
                        <field><name>SCLDEL</name><bitOffset>20</bitOffset><bitWidth>4</bitWidth></field>
                        <field><name>PRESC</name><bitOffset>28</bitOffset><bitWidth>4</bitWidth></field>
                    </fields>
                </register>
            </registers>
        </peripheral>
        <peripheral>
            <name>TIM2</name>
            <baseAddress>0x40000000</baseAddress>
            <registers>
                <register>
                    <name>CR1</name>
                    <addressOffset>0x0</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>CEN</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>
                        <field><name>DIR</name><bitOffset>4</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
                <register><name>PSC</name><addressOffset>0x28</addressOffset><size>32</size></register>
                <register><name>ARR</name><addressOffset>0x2C</addressOffset><size>32</size></register>
            </registers>
        </peripheral>
        <peripheral>
            <name>GPIOA</name>
            <baseAddress>0x48000000</baseAddress>
            <registers>
                <register>
                    <name>MODER</name>
                    <addressOffset>0x0</addressOffset>
                    <size>32</size>
                    <fields>
                        <field>
                            <name>MODER5</name>
                            <bitOffset>10</bitOffset>
                            <bitWidth>2</bitWidth>
                            <enumeratedValues>
                                <enumeratedValue><name>Input</name><value>0</value></enumeratedValue>
                                <enumeratedValue><name>Output</name><value>1</value></enumeratedValue>
                                <enumeratedValue><name>Alternate</name><value>2</value></enumeratedValue>
                                <enumeratedValue><name>Analog</name><value>3</value></enumeratedValue>
                            </enumeratedValues>
                        </field>
                    </fields>
                </register>
                <register>
                    <name>OTYPER</name>
                    <addressOffset>0x4</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>OT5</name><bitOffset>5</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
                <register>
                    <name>PUPDR</name>
                    <addressOffset>0xC</addressOffset>
                    <size>32</size>
                    <fields>
                        <field>
                            <name>PUPDR5</name>
                            <bitOffset>10</bitOffset>
                            <bitWidth>2</bitWidth>
                            <enumeratedValues>
                                <enumeratedValue><name>None</name><value>0</value></enumeratedValue>
                                <enumeratedValue><name>PullUp</name><value>1</value></enumeratedValue>
                                <enumeratedValue><name>PullDown</name><value>2</value></enumeratedValue>
                            </enumeratedValues>
                        </field>
                    </fields>
                </register>
                <register>
                    <name>IDR</name>
                    <addressOffset>0x10</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>IDR5</name><bitOffset>5</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
                <register>
                    <name>ODR</name>
                    <addressOffset>0x14</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>ODR5</name><bitOffset>5</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
                <register>
                    <name>AFRL</name>
                    <addressOffset>0x20</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>AFRL5</name><bitOffset>20</bitOffset><bitWidth>4</bitWidth></field>
                    </fields>
                </register>
            </registers>
        </peripheral>
        <peripheral>
            <name>ADC1</name>
            <baseAddress>0x50040000</baseAddress>
            <registers>
                <register>
                    <name>CR</name>
                    <addressOffset>0x08</addressOffset>
                    <size>32</size>
                    <fields>
                        <field><name>ADEN</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>
                    </fields>
                </register>
                <register>
                    <name>CFGR</name>
                    <addressOffset>0x0C</addressOffset>
                    <size>32</size>
                    <fields>
                        <field>
                            <name>RES</name>
                            <bitOffset>3</bitOffset>
                            <bitWidth>2</bitWidth>
                            <enumeratedValues>
                                <enumeratedValue><name>12-bit</name><value>0</value></enumeratedValue>
                                <enumeratedValue><name>10-bit</name><value>1</value></enumeratedValue>
                                <enumeratedValue><name>8-bit</name><value>2</value></enumeratedValue>
                                <enumeratedValue><name>6-bit</name><value>3</value></enumeratedValue>
                            </enumeratedValues>
                        </field>
                    </fields>
                </register>
            </registers>
        </peripheral>
    </peripherals>
</device>
"""

    def test_resolve_stlink_gdb_server_path_uses_tools_config_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")

            with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                    self.assertEqual(server.resolve_stlink_gdb_server_path(), str(tool_path))

    def test_collect_debug_capabilities_reports_tool_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")
            gdb_path = Path(temp_dir) / "arm-none-eabi-gdb.exe"
            gdb_path.write_text("stub", encoding="utf-8")

            with patch("stm32cubep_mcp.debug.server.shared.load_project_metadata", return_value=self.sample_project_metadata()):
                with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                    with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                        with patch("stm32cubep_mcp.debug.server.run_debug_command", side_effect=[
                            {"success": True, "stdout": "ST-LINK GDB server 7.10", "stderr": "", "exit_code": 0, "command": [str(tool_path), "--version"]},
                            {"success": True, "stdout": "GNU gdb 13.2", "stderr": "", "exit_code": 0, "command": [str(gdb_path), "--version"]},
                        ]):
                            result = server.stm32_debug_capabilities()

        self.assertTrue(result["implemented"])
        self.assertEqual(result["tool_path"], str(tool_path))
        self.assertEqual(result["gdb_path"], str(gdb_path))
        self.assertTrue(result["capabilities"]["gdb_client"])
        self.assertTrue(result["capabilities"]["snapshots"])

    def test_stm32_debug_launch_status_and_stop_manage_session(self) -> None:
        fake_process = FakePopen(["tool"])

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")

            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                with patch("stm32cubep_mcp.debug.server.shared.load_project_metadata", return_value=self.sample_project_metadata()):
                    with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                        with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                            with patch("stm32cubep_mcp.debug.server.subprocess.Popen", return_value=fake_process):
                                with patch("stm32cubep_mcp.debug.server.is_tcp_port_open", return_value=True):
                                    launch_result = server.stm32_debug_launch(session_name="phase1")
                                    self.assertTrue(launch_result["success"])
                                    self.assertEqual(launch_result["session"]["pid"], 4242)

                                    status_result = server.stm32_debug_status(session_name="phase1")
                                    self.assertTrue(status_result["success"])
                                    self.assertTrue(status_result["session"]["running"])

                                    stop_result = server.stm32_debug_stop(session_name="phase1")
                                    self.assertTrue(stop_result["success"])
                                    self.assertEqual(stop_result["session"]["exit_code"], 0)

    def test_stm32_debug_launch_can_disable_swo(self) -> None:
        fake_process = FakePopen(["tool"])

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")

            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                with patch("stm32cubep_mcp.debug.server.shared.load_project_metadata", return_value=self.sample_project_metadata()):
                    with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                        with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                            with patch("stm32cubep_mcp.debug.server.subprocess.Popen", return_value=fake_process):
                                with patch("stm32cubep_mcp.debug.server.is_tcp_port_open", return_value=True):
                                    launch_result = server.stm32_debug_launch(session_name="no-swo", enable_swo=False)
                                    stop_result = server.stm32_debug_stop(session_name="no-swo")

        self.assertTrue(launch_result["success"])
        self.assertTrue(stop_result["success"])
        self.assertIn("-z", launch_result["session"]["command"])
        self.assertIn("0", launch_result["session"]["command"])

    def test_stm32_debug_list_debuggers_parses_serial_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")

            with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                    with patch("stm32cubep_mcp.debug.server.run_debug_command", return_value={
                        "success": True,
                        "exit_code": 0,
                        "command": [str(tool_path), "-q"],
                        "stdout": "Connected debuggers:\n066DFF485754727567021514\n1234567890ABCDEF",
                        "stderr": "",
                    }):
                        result = server.stm32_debug_list_debuggers()

        self.assertTrue(result["success"])
        self.assertEqual(result["debuggers"], ["066DFF485754727567021514", "1234567890ABCDEF"])

    def test_select_launch_ports_falls_back_when_preferred_ports_are_unavailable(self) -> None:
        with patch("stm32cubep_mcp.debug.server.can_bind_tcp_port", side_effect=lambda port: port in {55001, 55002}):
            port_number, swo_port, used_fallback = server.select_launch_ports(61234, 61235)

        self.assertEqual(port_number, 55001)
        self.assertEqual(swo_port, 55002)
        self.assertTrue(used_fallback)

    def test_stm32_debug_gdb_version_reports_resolved_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")
            gdb_path = Path(temp_dir) / "arm-none-eabi-gdb.exe"
            gdb_path.write_text("stub", encoding="utf-8")

            with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                    with patch("stm32cubep_mcp.debug.server.run_debug_command", return_value={
                        "success": True,
                        "exit_code": 0,
                        "command": [str(gdb_path), "--version"],
                        "stdout": "GNU gdb 13.2\nCopyright",
                        "stderr": "",
                    }):
                        result = server.stm32_debug_gdb_version()

        self.assertTrue(result["success"])
        self.assertEqual(result["tool_path"], str(gdb_path))
        self.assertEqual(result["version"], "GNU gdb 13.2")

    def test_stm32_debug_snapshot_collects_structured_sections(self) -> None:
        fake_process = FakePopen(["tool"])

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")
            gdb_path = Path(temp_dir) / "arm-none-eabi-gdb.exe"
            gdb_path.write_text("stub", encoding="utf-8")
            transcript = "\n".join([
                "=== REGISTERS ===",
                "pc             0x8000123",
                "sp             0x20001000",
                "=== BACKTRACE ===",
                "#0  SysTick_Handler () at main.c:42",
                "#1  main () at main.c:88",
                "=== STACK ===",
                "0x20001000: 0x20000000 0x08000123 0x00000001 0x00000002",
            ])

            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir}):
                with patch("stm32cubep_mcp.debug.server.shared.load_project_metadata", return_value=self.sample_project_metadata()):
                    with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                        with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                            with patch("stm32cubep_mcp.debug.server.subprocess.Popen", return_value=fake_process):
                                with patch("stm32cubep_mcp.debug.server.is_tcp_port_open", return_value=True):
                                    with patch("stm32cubep_mcp.debug.server.run_debug_command", return_value={
                                        "success": True,
                                        "exit_code": 0,
                                        "command": [str(gdb_path), "--batch"],
                                        "stdout": transcript,
                                        "stderr": "",
                                    }):
                                        launch_result = server.stm32_debug_launch(session_name="phase2")
                                        snapshot_result = server.stm32_debug_snapshot(session_name="phase2")
                                        stop_result = server.stm32_debug_stop(session_name="phase2")

        self.assertTrue(launch_result["success"])
        self.assertTrue(snapshot_result["success"])
        self.assertEqual(snapshot_result["registers"]["pc"], "0x8000123")
        self.assertEqual(snapshot_result["registers"]["sp"], "0x20001000")
        self.assertEqual(snapshot_result["backtrace"][0], "#0  SysTick_Handler () at main.c:42")
        self.assertEqual(snapshot_result["stack"][0], "0x20001000: 0x20000000 0x08000123 0x00000001 0x00000002")
        self.assertTrue(stop_result["success"])

    def test_stm32_debug_inspect_peripheral_reads_live_registers(self) -> None:
        fake_process = FakePopen(["tool"])

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")
            gdb_path = Path(temp_dir) / "arm-none-eabi-gdb.exe"
            gdb_path.write_text("stub", encoding="utf-8")
            svd_path = Path(temp_dir) / "STM32L476.svd"
            svd_path.write_text(self.sample_svd_text(), encoding="utf-8")
            transcript = "\n".join([
                "=== REGISTERS ===",
                "CR1=0x0000000c",
                "CR2=0x00000000",
                "CR3=0x00000000",
                "BRR=0x0000208d",
            ])

            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir, "STM32_SVD_PATH": str(svd_path)}):
                with patch("stm32cubep_mcp.debug.server.shared.load_project_metadata", return_value=self.sample_project_metadata()):
                    with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                        with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                            with patch("stm32cubep_mcp.debug.server.subprocess.Popen", return_value=fake_process):
                                with patch("stm32cubep_mcp.debug.server.is_tcp_port_open", return_value=True):
                                    with patch("stm32cubep_mcp.debug.server.run_debug_command", return_value={
                                        "success": True,
                                        "exit_code": 0,
                                        "command": [str(gdb_path), "--batch"],
                                        "stdout": transcript,
                                        "stderr": "",
                                    }):
                                        launch_result = server.stm32_debug_launch(session_name="inspect")
                                        inspect_result = server.stm32_debug_inspect_peripheral(session_name="inspect", peripheral="USART1")
                                        stop_result = server.stm32_debug_stop(session_name="inspect")

        self.assertTrue(launch_result["success"])
        self.assertTrue(inspect_result["success"])
        self.assertEqual(inspect_result["registers"]["CR1"]["value"], 12)
        self.assertEqual(inspect_result["registers"]["CR1"]["fields"]["TE"]["value"], 1)
        self.assertEqual(inspect_result["registers"]["CR1"]["fields"]["RE"]["value"], 1)
        self.assertTrue(stop_result["success"])

    def test_stm32_debug_answer_question_reports_uart_baudrate(self) -> None:
        fake_process = FakePopen(["tool"])

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")
            gdb_path = Path(temp_dir) / "arm-none-eabi-gdb.exe"
            gdb_path.write_text("stub", encoding="utf-8")
            svd_path = Path(temp_dir) / "STM32L476.svd"
            svd_path.write_text(self.sample_svd_text(), encoding="utf-8")
            register_transcript = "\n".join([
                "=== REGISTERS ===",
                "CR1=0x0000000c",
                "CR2=0x00000000",
                "CR3=0x00000000",
                "BRR=0x0000208d",
            ])
            rcc_transcript = "\n".join([
                "=== RCC ===",
                "RCC_CR=0x00000060",
                "RCC_CFGR=0x0000000c",
                "RCC_PLLCFGR=0x00002801",
                "RCC_CCIPR=0x00000000",
            ])

            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir, "STM32_SVD_PATH": str(svd_path)}):
                with patch("stm32cubep_mcp.debug.server.shared.load_project_metadata", return_value=self.sample_project_metadata()):
                    with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                        with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                            with patch("stm32cubep_mcp.debug.server.subprocess.Popen", return_value=fake_process):
                                with patch("stm32cubep_mcp.debug.server.is_tcp_port_open", return_value=True):
                                    with patch("stm32cubep_mcp.debug.server.run_debug_command", side_effect=[
                                        {"success": True, "exit_code": 0, "command": [str(gdb_path), "--batch"], "stdout": register_transcript, "stderr": ""},
                                        {"success": True, "exit_code": 0, "command": [str(gdb_path), "--batch"], "stdout": rcc_transcript, "stderr": ""},
                                    ]):
                                        launch_result = server.stm32_debug_launch(session_name="answer")
                                        answer_result = server.stm32_debug_answer_question("what is baudrate set in uart1", session_name="answer")
                                        stop_result = server.stm32_debug_stop(session_name="answer")

        self.assertTrue(launch_result["success"])
        self.assertTrue(answer_result["success"])
        self.assertEqual(answer_result["configuration"]["baud_rate"], 9600)
        self.assertIn("Estimated baud rate is 9600", str(answer_result["answer"]))
        self.assertTrue(stop_result["success"])

    def test_stm32_debug_answer_question_reports_semantic_field_answers(self) -> None:
        fake_process = FakePopen(["tool"])

        with tempfile.TemporaryDirectory() as temp_dir:
            tool_path = Path(temp_dir) / "ST-LINK_gdbserver.exe"
            tool_path.write_text("stub", encoding="utf-8")
            gdb_path = Path(temp_dir) / "arm-none-eabi-gdb.exe"
            gdb_path.write_text("stub", encoding="utf-8")
            svd_path = Path(temp_dir) / "STM32L476.svd"
            svd_path.write_text(self.sample_svd_text(), encoding="utf-8")
            transcripts = [
                "\n".join([
                    "=== REGISTERS ===",
                    "CCIPR=0x00000000",
                    "CFGR=0x00000000",
                    "CR=0x00000060",
                    "PLLCFGR=0x00002801",
                ]),
                "\n".join([
                    "=== REGISTERS ===",
                    "CR1=0x00000056",
                ]),
                "\n".join([
                    "=== REGISTERS ===",
                    "CR1=0x00000001",
                    "TIMINGR=0x30420f13",
                ]),
                "\n".join([
                    "=== REGISTERS ===",
                    "ARR=0x000003e7",
                    "CR1=0x00000001",
                    "PSC=0x0000004f",
                ]),
                "\n".join([
                    "=== REGISTERS ===",
                    "AFRL=0x00200000",
                    "IDR=0x00000020",
                    "MODER=0x00000800",
                    "ODR=0x00000020",
                    "OTYPER=0x00000000",
                    "PUPDR=0x00000400",
                ]),
                "\n".join([
                    "=== REGISTERS ===",
                    "CFGR=0x00000008",
                    "CR=0x00000001",
                ]),
            ]

            transcript_iter = iter(transcripts)

            def fake_run_debug_command(command: list[str], timeout_seconds: int) -> dict[str, object]:
                transcript = next(transcript_iter)
                return {
                    "success": True,
                    "exit_code": 0,
                    "command": command,
                    "stdout": transcript,
                    "stderr": "",
                }

            with patch.dict("os.environ", {"STM32CUBEP_MCP_LOG_DIR": temp_dir, "STM32_SVD_PATH": str(svd_path)}):
                with patch("stm32cubep_mcp.debug.server.shared.load_project_metadata", return_value=self.sample_project_metadata()):
                    with patch("stm32cubep_mcp.debug.server.shared.load_tools_local_config", return_value=self.sample_tools_config(str(tool_path))):
                        with patch("stm32cubep_mcp.debug.server.shared.host_platform_name", return_value="windows"):
                            with patch("stm32cubep_mcp.debug.server.subprocess.Popen", return_value=fake_process):
                                with patch("stm32cubep_mcp.debug.server.is_tcp_port_open", return_value=True):
                                    with patch("stm32cubep_mcp.debug.server.run_debug_command", side_effect=fake_run_debug_command):
                                        launch_result = server.stm32_debug_launch(session_name="semantic")
                                        rcc_result = server.stm32_debug_answer_question("what is the clock source in rcc", session_name="semantic")
                                        spi_result = server.stm32_debug_answer_question("what is spi1 cpol and cpha", session_name="semantic")
                                        i2c_result = server.stm32_debug_answer_question("show i2c1 timing prescaler", session_name="semantic")
                                        tim_result = server.stm32_debug_answer_question("what is tim2 prescaler", session_name="semantic")
                                        gpio_result = server.stm32_debug_answer_question("what is gpioa pin 5 mode", session_name="semantic")
                                        adc_result = server.stm32_debug_answer_question("what is adc1 resolution", session_name="semantic")
                                        stop_result = server.stm32_debug_stop(session_name="semantic")

        self.assertTrue(launch_result["success"])
        self.assertIn("SWS = 0 (MSI)", str(rcc_result["answer"]))
        self.assertIn("CPOL = 1", str(spi_result["answer"]))
        self.assertIn("CPHA = 0", str(spi_result["answer"]))
        self.assertIn("PRESC = 3", str(i2c_result["answer"]))
        self.assertIn("PSC", str(tim_result["answer"]))
        self.assertIn("MODER5 = 2 (Alternate)", str(gpio_result["answer"]))
        self.assertIn("RES = 1 (10-bit)", str(adc_result["answer"]))
        self.assertTrue(stop_result["success"])


if __name__ == "__main__":
    unittest.main()