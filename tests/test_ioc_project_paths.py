from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stm32cubep_mcp.ioc import project_paths


class IocProjectPathsTests(unittest.TestCase):
    def test_configured_ioc_path_resolves_relative_to_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cwd = Path(temp_dir)
            relative_ioc = Path("generated") / "board.ioc"
            expected = (cwd / relative_ioc).resolve()

            result = project_paths.configured_ioc_path(
                lambda: {"ioc_path": str(relative_ioc)},
                cwd=cwd,
            )

        self.assertEqual(result, str(expected))

    def test_discover_ioc_path_prefers_requested_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            requested_path = Path(temp_dir) / "requested.ioc"
            requested_path.write_text("stub", encoding="utf-8")
            configured_path = Path(temp_dir) / "configured.ioc"
            configured_path.write_text("stub", encoding="utf-8")

            result = project_paths.discover_ioc_path(
                str(requested_path),
                configured_ioc_path_fn=lambda: str(configured_path),
            )

        self.assertEqual(result["resolved_path"], str(requested_path.resolve()))
        self.assertEqual(result["resolution_source"], "requested")

    def test_resolve_completion_markers_uses_ioc_toolchain_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            project_root.mkdir()
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text("ProjectManager.ToolChainLocation=Projects\n", encoding="utf-8")

            markers = project_paths.resolve_completion_markers(project_root, ioc_path, "board")

        self.assertEqual(
            markers,
            [
                (project_root / "Projects" / "STM32CubeIDE" / ".project").resolve(),
                (project_root / "Projects" / "STM32CubeIDE" / ".cproject").resolve(),
                (project_root / "board" / "Projects" / "STM32CubeIDE" / ".project").resolve(),
                (project_root / "board" / "Projects" / "STM32CubeIDE" / ".cproject").resolve(),
            ],
        )


if __name__ == "__main__":
    unittest.main()
