import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from register_motion_generation import register  # noqa: E402


def write_gif(path: Path) -> None:
    frames = [
        Image.new("RGB", (240, 360), (31, 86, 176)),
        Image.new("RGB", (240, 360), (44, 164, 132)),
    ]
    frames[0].save(path, format="GIF", save_all=True, append_images=frames[1:], duration=180, loop=0)


@unittest.skipIf(Image is None, "Pillow is required for GIF tests")
class RegisterMotionGenerationTests(unittest.TestCase):
    def test_registers_real_animated_gif_and_prompt_hash(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            bundle = Path(temp_dir)
            gif_path = bundle / "hero.gif"
            prompt_path = bundle / f"{bundle.name}.motion-prompt.md"
            write_gif(gif_path)
            prompt_path.write_text("Seedance 2.5 direct GIF task\n", encoding="utf-8")
            expected_hash = hashlib.sha256(gif_path.read_bytes()).hexdigest()

            manifest = register(str(gif_path), prompt=str(prompt_path))
            self.assertTrue((gif_path.parent / "hero-motion-generation.json").is_file())

        self.assertEqual(manifest["generation_family"], "seedance-class")
        self.assertEqual(manifest["generation_model_label"], "Seedance 2.5")
        self.assertEqual(manifest["generation_mode"], "seedance_2_5_direct_gif")
        self.assertEqual(manifest["output_format"], "gif")
        self.assertTrue(manifest["inspection"]["animated"])
        self.assertEqual(manifest["inspection"]["frame_count"], 2)
        self.assertEqual(manifest["asset_sha256"], expected_hash)

    def test_rejects_non_animated_gif(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            bundle = Path(temp_dir)
            gif_path = bundle / "hero.gif"
            Image.new("RGB", (240, 360), (31, 86, 176)).save(gif_path, format="GIF")
            prompt_path = bundle / f"{bundle.name}.motion-prompt.md"
            prompt_path.write_text("Seedance 2.5 direct GIF task\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "at least two frames"):
                register(str(gif_path), prompt=str(prompt_path))


if __name__ == "__main__":
    unittest.main()
