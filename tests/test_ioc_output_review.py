from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stm32cubep_mcp.ioc import output_review


class IocOutputReviewTests(unittest.TestCase):
    def sample_project_descriptor(self) -> str:
        return """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<projectDescription>
    <name>UART_TwoBoards_ComPolling</name>
    <linkedResources>
        <link>
            <name>Application/User/Core/main.c</name>
            <type>1</type>
            <locationURI>PARENT-1-PROJECT_LOC/Core/Src/main.c</locationURI>
        </link>
    </linkedResources>
</projectDescription>
"""

    def test_collect_output_review_reports_mismatch_against_core_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "project"
            project_root.mkdir()
            ioc_path = project_root / "board.ioc"
            ioc_path.write_text("ProjectManager.ProjectName=board\n", encoding="utf-8")
            (project_root / ".mxproject").write_text(
                "\n".join([
                    "[PreviousGenFiles]",
                    "AdvancedFolderStructure=true",
                    "HeaderPath#0=..\\Core\\Inc",
                    "SourcePath#0=..\\Core\\Src",
                    "",
                ]),
                encoding="utf-8",
            )
            output_root = Path(temp_dir) / "generated"
            (output_root / "Inc").mkdir(parents=True)
            (output_root / "Src").mkdir(parents=True)
            (output_root / "STM32CubeIDE").mkdir()
            (output_root / "STM32CubeIDE" / ".project").write_text(self.sample_project_descriptor(), encoding="utf-8")
            (output_root / "STM32CubeIDE" / ".cproject").write_text(
                """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<cproject>
    <option valueType=\"includePath\">
        <listOptionValue builtIn=\"false\" value=\"../../Core/Inc\"/>
    </option>
</cproject>
""",
                encoding="utf-8",
            )

            result = output_review.collect_output_review(ioc_path, output_root)

        self.assertIn("Inc/", result["top_level_entries"])
        self.assertIn("Src/", result["top_level_entries"])
        self.assertTrue(result["mismatches"])

    def test_collect_build_layout_summary_reads_injected_metadata(self) -> None:
        generation_root = Path("C:/work/generated")

        result = output_review.collect_build_layout_summary(
            generation_root,
            load_build_metadata_fn=lambda: {
                "workspace": "C:/work/ws",
                "project_path": "C:/work/generated/STM32CubeIDE",
                "project_name": "board",
                "artifact": "C:/work/generated/STM32CubeIDE/Debug/board.elf",
                "default_configuration": "Debug",
            },
        )

        self.assertEqual(result["generation_root"], str(generation_root))
        self.assertEqual(result["build"]["project_name"], "board")
        self.assertEqual(
            result["structure"]["cubeide_project_dir"],
            str(generation_root / "STM32CubeIDE"),
        )


if __name__ == "__main__":
    unittest.main()
