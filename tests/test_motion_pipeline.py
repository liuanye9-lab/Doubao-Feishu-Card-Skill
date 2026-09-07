import json
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

from doubao_pipeline import run_pipeline  # noqa: E402
from register_motion_generation import register  # noqa: E402


PROCESS_COPY = (
    "客户工单处理闭环\n"
    "第1步：接收问题\n"
    "第2步：智能分类\n"
    "第3步：分派处理\n"
    "第4步：回访关闭\n"
    "查看详情：https://open.feishu.cn"
)


def write_gif(path: Path) -> None:
    frames = [
        Image.new("RGB", (240, 360), (31, 86, 176)),
        Image.new("RGB", (240, 360), (44, 164, 132)),
    ]
    frames[0].save(path, format="GIF", save_all=True, append_images=frames[1:], duration=180, loop=0)


@unittest.skipIf(Image is None, "Pillow is required for GIF tests")
class MotionPipelineTests(unittest.TestCase):
    def test_process_copy_auto_routes_to_seedance_and_needs_gif(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            report = run_pipeline(PROCESS_COPY, Path(temp_dir), name="motion")
            bundle = Path(temp_dir) / "motion"

            self.assertEqual(report["status"], "needs_gif")
            self.assertTrue(report["motion_selection"]["selected"])
            self.assertTrue(report["motion_selection"]["auto_selected"])
            self.assertEqual(report["media"]["generation_model_label"], "Seedance 2.5")
            self.assertTrue(report["doubao"]["seedance_required"])
            self.assertFalse(report["doubao"]["seedream_required"])
            self.assertEqual(Path(report["media"]["final_asset"]), bundle / "hero.gif")
            self.assertTrue((bundle / "motion.motion-spec.json").is_file())
            self.assertTrue((bundle / "motion.motion-prompt.md").is_file())
            self.assertIn("register_motion_generation.py", report["next_steps"]["register_generated_media"])

    def test_motion_can_be_forced_off(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            report = run_pipeline(PROCESS_COPY, Path(temp_dir), name="static", force_motion=False)

        self.assertEqual(report["status"], "needs_image")
        self.assertFalse(report["motion_selection"]["selected"])
        self.assertTrue(report["doubao"]["seedream_required"])
        self.assertFalse(report["doubao"]["seedance_required"])

    def test_registered_seedance_gif_with_img_key_compiles_ready_card(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            output_dir = Path(temp_dir)
            first = run_pipeline(PROCESS_COPY, output_dir, name="ready-motion")
            bundle = output_dir / "ready-motion"
            gif_path = bundle / "hero.gif"
            prompt_path = bundle / "ready-motion.motion-prompt.md"
            write_gif(gif_path)
            register(str(gif_path), prompt=str(prompt_path))

            report = run_pipeline(
                PROCESS_COPY,
                output_dir,
                name="ready-motion",
                hero_img_key="img_seedance_gif_test",
            )
            from finalize_card import record_review
            from media_fixtures import write_test_png
            screenshot = bundle / 'synthetic-review.png'
            write_test_png(screenshot)
            report = record_review(report["editable_spec"], "Synthetic GIF fixture, not a real Seedance run.", desktop=screenshot, mobile=screenshot)
            card = json.loads((bundle / "ready-motion.card").read_text(encoding="utf-8"))

        self.assertEqual(first["status"], "needs_gif")
        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["readiness"]["sendable"])
        self.assertTrue(report["readiness"]["seedance_output_ready"])
        self.assertEqual(report["doubao"]["card_image_contract"]["status"], "embedded_seedance_gif")
        image = next(item for item in card["body"]["elements"] if item.get("tag") == "img")
        self.assertEqual(image["img_key"], "img_seedance_gif_test")


if __name__ == "__main__":
    unittest.main()
