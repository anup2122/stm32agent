from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stm32cubep_mcp.ioc import script_builder


class IocScriptBuilderTests(unittest.TestCase):
    def test_resolve_cubemx_project_inputs_uses_metadata_and_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "board-project"
            project_root.mkdir()
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text("stub", encoding="utf-8")

            result = script_builder.resolve_cubemx_project_inputs(
                ioc_path=str(ioc_path),
                project_name="board",
                project_toolchain="STM32CubeIDE",
                project_path=str(project_root),
                discover_ioc_path_fn=lambda requested: {
                    "requested_path": requested,
                    "configured_path": None,
                    "resolved_path": str(ioc_path),
                    "resolution_source": "requested",
                },
                load_cubemx_metadata_fn=lambda: {},
                load_build_metadata_fn=lambda: {},
                resolve_completion_marker_fn=lambda project_path, resolved_ioc, project_name: project_path / "STM32CubeIDE" / ".project",
                resolve_completion_markers_fn=lambda project_path, resolved_ioc, project_name: [
                    project_path / "STM32CubeIDE" / ".project",
                    project_path / "STM32CubeIDE" / ".cproject",
                ],
            )

        self.assertEqual(result["ioc_path"], str(ioc_path.resolve()))
        self.assertEqual(result["project_name"], "board")
        self.assertEqual(result["project_toolchain"], "STM32CubeIDE")
        self.assertEqual(result["project_path"], str(project_root.resolve()))
        self.assertEqual(result["script_path"], str((project_root / "script.txt").resolve()))
        self.assertFalse(result["missing_fields"])

    def test_build_cubemx_script_includes_expected_commands(self) -> None:
        ioc_path = Path("C:/work/board.ioc")
        project_path = Path("C:/work/generated")

        script = script_builder.build_cubemx_script(ioc_path, "board", "STM32CubeIDE", project_path)

        self.assertIn(f'config load "{ioc_path}"', script)
        self.assertIn('project name "board"', script)
        self.assertIn('project toolchain "STM32CubeIDE"', script)
        self.assertIn(f'project path "{project_path}"', script)
        self.assertIn("project generate", script)
        self.assertTrue(script.endswith("exit_mx\n"))

    def test_resolve_cubemx_project_inputs_prefers_requested_ioc_directory_over_configured_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            requested_root = Path(temp_dir) / "requested"
            requested_root.mkdir()
            ioc_path = requested_root / "tim1_dma_spec.ioc"
            ioc_path.write_text("stub", encoding="utf-8")

            result = script_builder.resolve_cubemx_project_inputs(
                ioc_path=str(ioc_path),
                project_name="tim1_dma_spec",
                project_toolchain="STM32CubeIDE",
                discover_ioc_path_fn=lambda requested: {
                    "requested_path": requested,
                    "configured_path": "C:/stale/generated/blink.ioc",
                    "resolved_path": str(ioc_path),
                    "resolution_source": "requested",
                },
                load_cubemx_metadata_fn=lambda: {
                    "project_path": "C:/stale/generated/blink",
                    "script_path": "C:/stale/generated/blink/script.txt",
                    "project_name": "NUCLEO-L476RG-blink",
                },
                load_build_metadata_fn=lambda: {"project_name": "NUCLEO-L476RG-blink"},
                resolve_completion_marker_fn=lambda project_path, resolved_ioc, project_name: project_path / "STM32CubeIDE" / ".project",
                resolve_completion_markers_fn=lambda project_path, resolved_ioc, project_name: [
                    project_path / "STM32CubeIDE" / ".project",
                    project_path / "STM32CubeIDE" / ".cproject",
                ],
            )

        self.assertEqual(result["project_name"], "tim1_dma_spec")
        self.assertEqual(result["project_path"], str(requested_root.resolve()))
        self.assertEqual(result["script_path"], str((requested_root / "script.txt").resolve()))

    def test_resolve_generation_root_prefers_explicit_output_root(self) -> None:
        ioc_path = Path("C:/work/board.ioc")

        result = script_builder.resolve_generation_root(
            ioc_path,
            output_root="C:/external/generated",
            load_cubemx_metadata_fn=lambda: {"project_path": "C:/ignored"},
        )

        self.assertEqual(result, Path("C:/external/generated").resolve())


if __name__ == "__main__":
    unittest.main()
