import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prompt_router import route_prompt_presets  # noqa: E402


class PromptRouterTests(unittest.TestCase):
    def test_training_timeline_copy_selects_composable_recipes(self) -> None:
        result = route_prompt_presets(
            "AI先锋大赛开营\n培训时间线：学习、提交作品、决赛路演\n课程安排和时间表"
        )

        self.assertEqual(result["primary_content_profile"], "timeline")
        self.assertIn("timeline", result["selected_profiles"])
        self.assertIn("training", result["selected_profiles"])
        self.assertEqual(result["reference_template"], "training-notice")
        self.assertEqual(result["media_mode"], "static")
        self.assertTrue(result["source_locked"])
        self.assertTrue(result["prompt_fragments"])
        self.assertEqual(result["generation_family"], "seedream-class")
        self.assertEqual(result["generation_tool"], "doubao.image_gen")
        self.assertEqual(result["generation_model"], "seedream-5.0-pro")
        self.assertEqual(result["generation_model_label"], "Seedream 5.0 Pro")
        self.assertIn("seedream_5_pro_banner_plus_native_card", result["supported_image_generation_modes"])
        self.assertEqual(result["image_layout"], "reference_card_banner")
        self.assertEqual(result["image_roles"][:3], ["cover", "information_carrier", "text_companion"])
        self.assertIn("Guizang Social Card Skill", " ".join(result["auto_actions"]))
        self.assertIn("baoyu-skills", " ".join(result["auto_actions"]))
        self.assertEqual(result["upstream_method_pass"]["execution"], "attempt_if_available")

    def test_explicit_timeline_image_request_keeps_full_infographic_mode(self) -> None:
        result = route_prompt_presets("请把活动时间线图片直接生成成时间轴信息图")

        self.assertEqual(result["image_layout"], "timeline_infographic_inside_illustration")

    def test_switcher_is_selected_over_gif_when_both_are_requested(self) -> None:
        result = route_prompt_presets("课程图片轮播，支持动图和上一张/下一张", media_mode="switcher")

        self.assertEqual(result["media_mode"], "switcher")
        self.assertIn("image-switcher", result["selected_profiles"])
        self.assertNotIn("gif-motion", result["selected_profiles"])
        self.assertIn("application Bot", " ".join(result["auto_actions"]))

    def test_negated_media_words_do_not_trigger_media_profiles(self) -> None:
        result = route_prompt_presets("课程通知\n不要轮播，也不需要动图，使用静态首图即可")

        self.assertEqual(result["media_mode"], "static")
        self.assertNotIn("image-switcher", result["selected_profiles"])
        self.assertNotIn("gif-motion", result["selected_profiles"])

    def test_explicit_gallery_mode_forces_gallery_prompt(self) -> None:
        result = route_prompt_presets("课程案例", media_mode="gallery")

        self.assertEqual(result["media_mode"], "gallery")
        self.assertIn("gallery", result["selected_profiles"])
        self.assertIn(result["layout_id"], {"training-modules-with-schedule", "case-context-method-result"})

    def test_auto_visual_packs_choose_baoyu_and_guizang_for_timeline_training(self) -> None:
        result = route_prompt_presets(
            "AI先锋大赛开营\n培训时间线：学习、提交作品、决赛路演\n"
            "0824-0904：多维表格培训和智能体培训\n0915：提交初赛作品"
        )

        visual = result["visual_skill_routing"]
        self.assertTrue(visual["auto_selected"])
        self.assertEqual(visual["style_id"], "blueprint-timeline")
        self.assertEqual(visual["visual_layout"], "linear-progression")
        self.assertEqual(visual["selected_packs"], ["baoyu-infographic", "guizang-social-swiss"])
        self.assertEqual(visual["runtime"]["provider"], "doubao-work.builtin-image")
        self.assertEqual(visual["runtime"]["post_processing"], "none")
        self.assertIn("blueprint-style", result["selected_profiles"])

    def test_explicit_style_overrides_visual_style_but_keeps_content_structure(self) -> None:
        result = route_prompt_presets("请把活动时间线做成墨色研究札记风格，保留日期和阶段动作")

        visual = result["visual_skill_routing"]
        self.assertFalse(visual["style_auto_selected"])
        self.assertEqual(visual["style_id"], "ink-research-note")
        self.assertEqual(result["style_profile"], "ink-editorial-style")
        self.assertEqual(visual["selection_rule"], "timeline-training-path")
        self.assertIn("baoyu-infographic", visual["selected_packs"])

    def test_gallery_auto_routes_to_current_baoyu_xhs_pack(self) -> None:
        result = route_prompt_presets("一组多图系列作品，统一色板，每张图表达一个信息任务", media_mode="gallery")

        visual = result["visual_skill_routing"]
        self.assertEqual(visual["selection_rule"], "static-series-gallery")
        self.assertEqual(visual["style_id"], "xhs-editorial-magazine")
        self.assertIn("baoyu-xhs-images", visual["selected_packs"])
        self.assertIn("guizang-social-editorial", visual["selected_packs"])


if __name__ == "__main__":
    unittest.main()
