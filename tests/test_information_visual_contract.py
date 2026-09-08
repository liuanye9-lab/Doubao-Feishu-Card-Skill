import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from doubao_pipeline import run_pipeline  # noqa: E402
from visual_spec import build_visual_spec  # noqa: E402


SOURCE = """# 清华附中 AI先锋·智教焕新教师通知

## 活动定位

活动希望让每一个教育好想法，都能被 AI 放大；AI 只是手段，教育价值才是目的。

## 活动介绍

围绕真实教育问题，孵化可真实使用、可复用、可推广的智能化应用方案。

## 教师可以获得什么

- 全程陪伴式支持
- 场景库、模板库和提示词库

## 六大赛道

以智助教、以智助学、以智助评、以智助育、以智助研、以智助管。

## 活动节奏

- 8月28日：活动启动预热；
- 9月17日：专场培训；
- 8月28日—9月24日：报名征集想法；
- 8月28日—10月28日：原型搭建与实践验证。
"""


class InformationVisualContractTests(unittest.TestCase):
    def test_visual_spec_requires_a_source_backed_information_job(self):
        spec = build_visual_spec(SOURCE, title="清华附中 AI先锋·智教焕新教师通知", brand_context="清华附中\nasset: logo.png")
        self.assertTrue(spec["information_carrier"])
        self.assertTrue(spec["not_decorative"])
        self.assertTrue(spec["information_purpose"])
        self.assertTrue(spec["visual_job"])
        self.assertEqual(spec["preferred_render"], "information_infographic")
        self.assertGreaterEqual(len(spec["source_spans"]), 3)
        self.assertTrue(spec["brand_asset_policy"]["exact_asset_required"])
        self.assertIn("抽象科技装饰", spec["must_not_show"][0])

    def test_dense_notice_uses_portrait_information_mode_and_prompt_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(
                SOURCE,
                Path(temp_dir),
                name="information-card",
                brand_context="清华附中\nasset: logo.png",
            )
            bundle = Path(temp_dir) / "information-card"
            visual = json.loads((bundle / "information-card.visual-spec.json").read_text(encoding="utf-8"))
            prompt = (bundle / "information-card.image-prompt.md").read_text(encoding="utf-8")

        self.assertEqual(report["doubao"]["image_generation_mode"], "seedream_5_pro_direct_full_card")
        self.assertEqual(visual["preferred_render"], "information_infographic")
        self.assertIn("information-bearing", prompt)
        self.assertIn("not an abstract concept illustration", prompt)
        self.assertIn("When an original logo", prompt)
        self.assertIn("cover / ordered process / grouped information panels", prompt)


if __name__ == "__main__":
    unittest.main()
