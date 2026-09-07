"""Layout regressions use synthetic source and URLs; no remote writes or model calls."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from layout_coordination import coordinate_layout, choose_image_mode
from generate_card import build_card
from validate_card import validate
from image_art_direction import build_image_prompt

SOURCE = """培训示例
# 课程亮点
真实业务流程拆解。
立即预约：https://open.feishu.cn
# 课程收获
配套提示词与实操素材。
查看材料：https://open.larksuite.com
"""
def sample():
    return {"title": "培训示例", "preset": "olive-editorial", "type": "custom", "suppress_generated_labels": True,
            "analysis": {"source_text": SOURCE, "design_plan": {"media_policy": {}}},
            "blocks": [{"type": "section", "title": "🔎 课程亮点", "body": "真实业务流程拆解。"},
                       {"type": "section", "title": "📖 课程收获", "body": "配套提示词与实操素材。"},
                       {"type": "buttons", "items": [
                           {"text": "立即预约", "url": "https://open.feishu.cn", "style": "primary"},
                           {"text": "查看材料", "url": "https://open.larksuite.com", "style": "secondary"}]}]}

class LayoutCoordinationTests(unittest.TestCase):
    def test_source_backed_actions_stay_with_their_modules(self):
        spec = sample()
        original_source = spec["analysis"]["source_text"]
        coordinate_layout(spec)
        self.assertEqual(len(spec["blocks"]), 2)
        self.assertEqual(spec["blocks"][0]["actions"][0]["url"], "https://open.feishu.cn")
        self.assertEqual(spec["blocks"][1]["actions"][0]["url"], "https://open.larksuite.com")
        self.assertEqual(spec["analysis"]["source_text"], original_source)
        self.assertEqual(spec["preset"], "olive-editorial")
        from generate_card import spec_field_present
        self.assertTrue(spec_field_present(spec, "buttons"))
        before = copy.deepcopy(spec)
        coordinate_layout(spec)
        self.assertEqual(spec, before)

    def test_ambiguous_duplicate_url_stays_global(self):
        spec = sample()
        spec["analysis"]["source_text"] += "\n参考：https://open.feishu.cn"
        coordinate_layout(spec)
        self.assertNotIn("actions", spec["blocks"][0])
        self.assertEqual(spec["blocks"][-1]["type"], "buttons")
        self.assertEqual(spec["blocks"][-1]["items"][0]["url"], "https://open.feishu.cn")

    def test_omitted_heading_is_a_boundary_and_overview_is_global(self):
        spec = sample()
        spec["analysis"]["source_text"] = SOURCE.replace("立即预约：", "# 已省略模块\n立即预约：")
        spec["blocks"][-1]["items"][1]["text"] = "查看全部材料"
        coordinate_layout(spec)
        self.assertTrue(all("actions" not in block for block in spec["blocks"][:2]))
        self.assertEqual(len(spec["blocks"][-1]["items"]), 2)

    def test_native_module_keeps_title_copy_and_real_button_together(self):
        spec = sample()
        coordinate_layout(spec)
        with tempfile.TemporaryDirectory() as tmp:
            card, _, contracts = build_card(spec, Path(tmp) / "test.card", persist_assets=False)
        self.assertEqual(contracts, [])
        self.assertTrue(validate(card)["ok"])
        groups = card["body"]["elements"]
        self.assertEqual(len(groups), 2)
        for group in groups:
            column = group["columns"][0]
            self.assertEqual([node["tag"] for node in column["elements"]], ["markdown", "markdown", "button"])
            self.assertEqual(column["padding"], "10px 12px")
            self.assertEqual(column["vertical_spacing"], "4px")
            self.assertIn("background_style", column)

    def test_full_image_fit_and_explicit_crop_are_preserved(self):
        for requested, expected in [(None, "fit_horizontal"), ("crop_top", "crop_top")]:
            spec = sample()
            spec["hero"] = {"img_key": "img_synthetic_layout_fixture", "alt": "test"}
            if requested:
                spec["hero"]["scale_type"] = requested
            coordinate_layout(spec)
            with tempfile.TemporaryDirectory() as tmp:
                card, _, _ = build_card(spec, Path(tmp) / "test.card", persist_assets=False)
            self.assertEqual(card["body"]["elements"][0]["scale_type"], expected)

    def test_notification_route_changes_geometry_not_style(self):
        spec = sample()
        spec.update(scene="training-notice", hero={}, image_art_direction="keep user font")
        choose_image_mode(spec, explicit_mode=None, banner_mode="test_banner")
        self.assertEqual(spec["image_generation_mode"], "test_banner")
        self.assertEqual(spec["preset"], "olive-editorial")
        self.assertEqual(spec["image_art_direction"], "keep user font")

    def test_explicit_mode_and_rich_diagram_are_not_overridden(self):
        for explicit, rich in [("user_mode", False), (None, True)]:
            spec = sample()
            spec.update(scene="training-notice", hero={}, image_generation_mode="user_mode")
            if rich:
                spec["information_allocation"] = {"image": {"include": [
                    {"role": "stage", "text": str(i)} for i in range(3)]}}
            choose_image_mode(spec, explicit_mode=explicit, banner_mode="test_banner")
            self.assertEqual(spec["image_generation_mode"], "user_mode")

    def test_banner_whitelist_is_small_and_retains_provenance(self):
        spec = sample()
        items = [{"role": "title", "text": "培训示例", "source_lines": [1]},
                 {"role": "fact", "text": "真实业务流程拆解", "source_lines": [3]},
                 {"role": "fact", "text": "配套提示词与实操素材", "source_lines": [6]},
                 {"role": "quote", "text": "很长的说明" * 12, "source_lines": [6]}]
        spec.update(hero={}, information_allocation={"image": {"use": True, "include": items}})
        coordinate_layout(spec, banner=True)
        selected = spec["information_allocation"]["image"]["include"]
        self.assertEqual(selected, items[:3])
        self.assertEqual(spec["hero"]["functional_text"], selected)
        self.assertEqual(spec["analysis"]["design_plan"]["media_policy"]["aspect_ratio"], "3:1")
        self.assertIn("横幅", spec["information_allocation"]["image"]["job"])
        prompt = build_image_prompt(spec, {}, banner=True)
        whitelist = prompt.split("----- BEGIN IMAGE TEXT WHITELIST -----")[1].split("----- END IMAGE TEXT WHITELIST -----")[0]
        self.assertNotIn("很长的说明", whitelist)

    def test_explicit_action_label_does_not_confuse_viewing_with_submitting(self):
        from content_intelligence import infer_action_label, suggest_buttons
        self.assertEqual(infer_action_label("查看已提交案例： "), "查看已提交案例")
        self.assertEqual(infer_action_label("我也要提交案例： "), "我也要提交案例")
        suggestions = suggest_buttons(["查看已提交案例：https://open.feishu.cn",
                                       "我也要提交案例：https://open.larksuite.com"])
        self.assertEqual(suggestions[0]["button_kind"], "secondary")
        self.assertEqual(suggestions[1]["button_kind"], "primary")

    def test_metric_banner_uses_one_focal_stat_with_compact_native_facts(self):
        spec = sample()
        spec["hero"] = {}
        spec["lead"] = "配套提示词与实操素材。"
        spec["blocks"].insert(0, {"type": "metrics", "items": [{"label": "完成率", "value": "95%以上"}]})
        spec["blocks"].insert(1, {"type": "text", "content": spec["lead"]})
        items = [{"role": "title", "text": "培训示例", "source_lines": [1]},
                 {"role": "metric", "text": "完成率：95%以上", "source_lines": [2]},
                 {"role": "metric", "text": "上岗周期：缩短30%", "source_lines": [3]}]
        spec["information_allocation"] = {"image": {"use": True, "include": items}}
        coordinate_layout(spec, banner=True)
        self.assertEqual(len(spec["information_allocation"]["image"]["include"]), 2)
        self.assertEqual(spec["blocks"][0]["content"], spec["lead"])
        self.assertTrue(spec["blocks"][1]["compact"])
        with tempfile.TemporaryDirectory() as tmp:
            card, _, _ = build_card(spec, Path(tmp) / "test.card", persist_assets=False)
        self.assertTrue(validate(card)["ok"])
        self.assertIn("95%以上", json.dumps(card, ensure_ascii=False))

    def test_fresh_notification_pipeline_has_one_coherent_layout_contract(self):
        import importlib
        pipeline = importlib.import_module("codex_pipeline" if (ROOT / "scripts/codex_pipeline.py").exists() else "doubao_pipeline")
        source = "培训示例\n完成率：95%以上\n耗时：减少70%\n# 课程亮点\n真实业务流程拆解。\n查看材料：https://open.feishu.cn"
        with tempfile.TemporaryDirectory() as tmp:
            report = pipeline.run_pipeline(source, Path(tmp), name="notice", requested_scene="training-notice")
            spec = json.loads(Path(report["editable_spec"]).read_text())
        self.assertIn("banner", spec["image_generation_mode"])
        self.assertEqual(spec["layout_coordination"]["image_layout"], "banner-led")
        self.assertEqual(spec["analysis"]["design_plan"]["media_policy"]["aspect_ratio"], "3:1")
        allocation = spec["information_allocation"]
        self.assertEqual(len([item for item in allocation["image"]["include"] if item["role"] == "metric"]), 1)
        self.assertEqual(allocation["image"]["text_policy"], spec["visual_contract"]["text_in_image"])
        self.assertIn(3, allocation["native_card"]["image_excluded_source_lines"])
        self.assertNotIn(2, allocation["native_card"]["image_excluded_source_lines"])
        self.assertEqual(spec["analysis"]["source_text"], source)
        self.assertFalse(report["readiness"]["cardkit_editor_ready"])

    def test_parallel_columns_emit_spacing_and_inherit_no_fake_surface(self):
        spec = {"title": "并列模块示例", "type": "custom", "suppress_generated_labels": True, "blocks": [
            {"type": "columns", "flex_mode": "stretch", "columns": [
                {"blocks": [{"type": "text", "text": "课程亮点"}]},
                {"blocks": [{"type": "text", "text": "课程收获"}]}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            card, _, _ = build_card(spec, Path(tmp) / "test.card", persist_assets=False)
        group = card["body"]["elements"][0]
        self.assertTrue(validate(card)["ok"])
        self.assertEqual(group["flex_mode"], "stretch")
        self.assertEqual(group["horizontal_spacing"], "12px")
        self.assertTrue(all(col["weight"] == 1 and col["padding"] == "0px" for col in group["columns"]))
