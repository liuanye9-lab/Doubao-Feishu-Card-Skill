import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_skill import package  # noqa: E402


class PackageSkillTests(unittest.TestCase):
    def test_package_has_single_importable_top_level_and_no_runtime_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = package(Path(temp_dir) / "doubao-feishu-card.zip")
            with ZipFile(output) as archive:
                names = archive.namelist()

        self.assertIn("doubao-feishu-card/SKILL.md", names)
        self.assertIn("doubao-feishu-card/agents/openai.yaml", names)
        self.assertIn("doubao-feishu-card/scripts/stable_card.py", names)
        self.assertIn("doubao-feishu-card/scripts/motion_strategy.py", names)
        self.assertIn("doubao-feishu-card/scripts/register_motion_generation.py", names)
        self.assertTrue(all(name.startswith("doubao-feishu-card/") for name in names))
        self.assertFalse(any("/.git/" in name or ("/outputs/" in name and not name.endswith("/outputs/.gitkeep")) or "__pycache__" in name for name in names))


if __name__ == "__main__":
    unittest.main()
