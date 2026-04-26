from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from stm32cubep_mcp.tools import cubemx_monitor


class CubeMxMonitorTests(unittest.TestCase):
    def test_collect_tree_state_and_diff_tree_state_detect_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            before = cubemx_monitor.collect_tree_state(root)
            file_path = root / "Core" / "Src" / "main.c"
            file_path.parent.mkdir(parents=True)
            file_path.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            after = cubemx_monitor.collect_tree_state(root)

        diff = cubemx_monitor.diff_tree_state(before, after)

        self.assertIn(str(file_path), diff["new_files"])
        self.assertFalse(diff["deleted_files"])

    def test_wait_for_completion_marker_reports_progress_and_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            marker_path = Path(temp_dir) / "STM32CubeIDE" / ".project"
            marker_path.parent.mkdir(parents=True)
            progress_callback = Mock()

            def create_marker(_: float) -> None:
                marker_path.write_text("project", encoding="utf-8")

            result = cubemx_monitor.wait_for_completion_marker(
                marker_path,
                timeout_seconds=5,
                initial_exists=False,
                initial_mtime=None,
                poll_interval_seconds=0.01,
                progress_callback=progress_callback,
                sleep_fn=create_marker,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "created")
        progress_callback.assert_called()


if __name__ == "__main__":
    unittest.main()
