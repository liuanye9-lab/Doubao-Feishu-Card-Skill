import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from motion_strategy import build_motion_prompt, build_motion_spec  # noqa: E402


class MotionStrategyTests(unittest.TestCase):
    def test_multi_step_process_auto_selects_seedance_gif(self) -> None:
        source = "工单闭环\n第1步：接收\n第2步：分类\n第3步：处理\n第4步：回访"
        spec = build_motion_spec(source, title="工单闭环")

        self.assertTrue(spec["selected"])
        self.assertTrue(spec["auto_selected"])
        self.assertEqual(spec["generation_model_label"], "Seedance 2.5")
        self.assertEqual(spec["target_asset"], "hero.gif")
        self.assertEqual(spec["output_format"], "gif")
        self.assertGreaterEqual(spec["score"], spec["threshold"])

    def test_static_metrics_stay_with_seedream(self) -> None:
        spec = build_motion_spec("经营看板\n完成率：95%\n节省时间：30%\n满意度：4.8")

        self.assertFalse(spec["selected"])
        self.assertEqual(spec["generation_model_label"], "Seedream 5.0 Pro")
        self.assertEqual(spec["target_asset"], "hero.png")

    def test_explicit_no_motion_overrides_sequence(self) -> None:
        source = "不要动图。第1步：接收；第2步：处理；第3步：关闭。"
        spec = build_motion_spec(source, force_motion=True)

        self.assertFalse(spec["selected"])
        self.assertEqual(spec["reasons"], ["source explicitly disables motion"])

    def test_motion_prompt_forbids_fake_actions_and_local_conversion(self) -> None:
        spec = build_motion_spec("动态展示：从接收→处理→关闭", title="处理流程")
        prompt = build_motion_prompt(spec)

        self.assertIn("Seedance 2.5", prompt)
        self.assertIn("Return GIF directly", prompt)
        self.assertIn("do not return MP4 for local conversion", prompt)
        self.assertIn("Do not draw buttons", prompt)


if __name__ == "__main__":
    unittest.main()
