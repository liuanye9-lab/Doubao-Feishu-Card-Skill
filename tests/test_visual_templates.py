from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from auto_layout import build_auto_spec  # noqa: E402
from generate_card import load_preset_registry, resolve_preset  # noqa: E402
from html_infographic import choose_render_strategy  # noqa: E402
from image_art_direction import build_image_prompt  # noqa: E402
from runtime_profile import image_runtime  # noqa: E402


class VisualTemplateSystemTests(unittest.TestCase):
    def test_registry_contains_exactly_five_production_templates(self) -> None:
        registry = load_preset_registry()
        ids = [item["id"] for item in registry["presets"]]
        self.assertEqual(
            ids,
            ["apple-minimal", "swiss-grid", "modern-editorial", "data-narrative", "product-showcase"],
        )
        self.assertTrue(registry["template_contract"]["auto_select"])
        self.assertEqual(registry["template_contract"]["spacing_multiplier"], 1.5)
        self.assertIn("禁止", registry["template_contract"]["gradient"])
        self.assertIn("磨砂玻璃", registry["template_contract"]["container_policy"])
        for preset in registry["presets"]:
            self.assertTrue(preset["design_system"].get("material_language"))
            self.assertIn("glass_hex", preset["gallery"])

    def test_content_auto_selection_maps_to_the_five_templates(self) -> None:
        cases = [
            ("活动信息\n时间：6月20日\n地点：线上会议", "event-info", "apple-minimal"),
            ("活动时间线\n6月20日 报名\n6月28日 提交\n7月5日 展示", "activity-timeline", "swiss-grid"),
            ("作品案例\n问题：信息分散\n做法：统一流程\n结果：效率提升", "case-showcase", "modern-editorial"),
            ("活动复盘\n完成率：95%\n满意度：88%\n转化率：42%", "event-recap", "data-narrative"),
            ("产品发布\n价值：让团队更快完成审核\n提交入口：https://example.com/submit", "prelaunch-promo", "product-showcase"),
        ]
        for source, scene, expected in cases:
            with self.subTest(scene=scene):
                spec = build_auto_spec(source, requested_scene=scene)
                self.assertEqual(spec["template_id"], expected)
                self.assertEqual(spec["template_selection"]["mode"], "scene_default")

    def test_explicit_template_and_legacy_alias_are_supported(self) -> None:
        spec = build_auto_spec("作品案例\n做法：统一流程\n结果：节省时间", requested_preset="apple-minimal")
        self.assertEqual(spec["template_id"], "apple-minimal")
        self.assertEqual(spec["template_selection"]["mode"], "explicit")
        legacy = {"preset": "olive-editorial", "theme": ""}
        resolved = resolve_preset(legacy)
        self.assertEqual(resolved["id"], "modern-editorial")

    def test_prompt_uses_selected_template_and_route_is_direct_only(self) -> None:
        source = "作品案例\n问题：资料分散\n做法：统一入口\n结果：查找时间缩短\n经验：先统一信息结构。"
        spec = build_auto_spec(source, requested_scene="case-showcase", requested_preset="modern-editorial")
        prompt = build_image_prompt(spec, image_runtime())
        self.assertIn("现代杂志编辑风", prompt)
        self.assertIn("Apple 官网式现代主义极简", prompt)
        self.assertIn("translucent frosted glass", prompt)
        self.assertIn("controlled gradients are allowed", prompt)
        self.assertEqual(choose_render_strategy(spec), "native_model")
        self.assertEqual(spec["render_strategy"], "native_model")


if __name__ == "__main__":
    unittest.main()
