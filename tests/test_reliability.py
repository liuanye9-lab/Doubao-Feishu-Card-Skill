"""Regression contracts. Synthetic assets and mocked APIs are not production evidence."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from media_fixtures import write_test_png
from asset_validation import inspect_asset
from visual_spec import parse_metric_line, build_chart_plan, extract_relationship_nodes
from doubao_pipeline import run_pipeline
from finalize_card import resume, record_review
from register_image_generation import register
import feishu_cli
import package_skill

COPY = "项目进展\n本周已完成数据整理，下一步进行评审。\n查看详情：https://open.feishu.cn"

class ReliabilityTests(unittest.TestCase):
    def test_case_image_whitelist_includes_qualified_metrics(self):
        from content_intelligence import build_information_allocation
        source = "带教案例\n完成率：95%以上\n耗时：减少70%"
        allocation = build_information_allocation(source, scene="case-showcase", title="带教案例", blocks=[])
        texts = [item["text"] for item in allocation["image"]["include"]]
        self.assertIn("完成率：95%以上", texts)
        self.assertIn("耗时：减少70%", texts)

    def test_emoji_prefixed_case_sections_reach_image_relationships(self):
        from content_intelligence import build_image_text_items

        blocks = [
            {"type": "section", "title": "⚠️ 背景", "body": "资料分散，查找成本高。"},
            {"type": "section", "title": "🛠️ 做法", "body": "1. 统一入口\n2. 建立索引。"},
            {"type": "section", "title": "🏆 结果", "body": "查找时间缩短70%。"},
        ]
        labels = [item["text"] for item in build_image_text_items(blocks, "案例复盘")]
        self.assertIn("背景：资料分散，查找成本高", labels)
        self.assertIn("做法：统一入口", labels)
        self.assertIn("结果：查找时间缩短70%", labels)

    def test_image_art_direction_is_single_refined_material_brief(self):
        from image_art_direction import build_image_prompt
        prompt = build_image_prompt({"information_allocation": {"image": {"include": [
            {"role": "metric", "text": "完成率：95%以上"}]}}}, {"generation_family": "image2-class"})
        self.assertIn("Apple 官网式现代主义极简", prompt)
        self.assertIn("no decorative gradients", prompt)
        self.assertIn("medium-weight headings", prompt)
        self.assertIn("SAME regular-weight size", prompt)
        self.assertIn("Transparency is allowed", prompt)
        self.assertIn("translucent frosted glass", prompt)
        self.assertIn("controlled gradients are allowed", prompt)
        self.assertNotIn("alpha 255 everywhere", prompt)
        self.assertIn("95%以上", prompt)
        self.assertIn("never invent extra rows", prompt)
        self.assertNotIn("All four", prompt)

    def test_process_prompt_keeps_sequence_without_requiring_statistics(self):
        from image_art_direction import build_image_prompt
        prompt = build_image_prompt({"information_allocation": {"image": {"include": [
            {"role": "stage", "text": "接收"}, {"role": "stage", "text": "处理"}]}}}, {})
        self.assertIn("stages stay in source order", prompt)
        self.assertIn("source-backed relationship diagrams", prompt)
        self.assertNotIn("four clean editorial rows", prompt)

    def test_cardkit_delivery_does_not_require_bot_preview(self):
        from card_studio_contract import build_stability_contract
        contract = build_stability_contract()
        self.assertIn("Bot preview only if explicitly requested", contract["remote_delivery_contract"])
        self.assertFalse(any(step.startswith("preview_bot_then") for step in contract["execution_order"]))

    def test_thousands_and_units_preserved(self):
        metric = parse_metric_line("预算：1,200元")
        self.assertEqual(metric["value"], 1200)
        self.assertEqual(metric["unit"], "元")
        self.assertEqual(parse_metric_line("预算：1，250.5万元")["value"], 1250.5)

    def test_visual_format_is_not_a_numeric_metric(self):
        self.assertIsNone(parse_metric_line("形式：3D 楼层导览 + 岗位视角"))
        self.assertIsNone(parse_metric_line("版本：v3.2"))

    def test_qualified_metrics_are_not_absolute_bars(self):
        source = "完成率：95%以上\n耗时：减少70%\n上岗周期：缩短30%"
        self.assertIsNone(build_chart_plan(source))
        self.assertFalse(parse_metric_line("成本：10—20元")["chart_eligible"])
        self.assertFalse(parse_metric_line("涨幅：约8%")["chart_eligible"])

    def test_valid_values_still_generate_bar_line_and_pie(self):
        self.assertEqual(build_chart_plan("甲组：1,200元\n乙组：800元")["type"], "bar")
        self.assertEqual(build_chart_plan("1月：10人\n2月：12人")["type"], "line")
        self.assertEqual(build_chart_plan("份额\n甲组：60%\n乙组：40%")["type"], "pie")
        self.assertNotEqual(build_chart_plan("份额\n甲组：60%\n乙组：42%")["type"], "pie")
        self.assertIsNone(build_chart_plan("甲组：10人\n乙组：20元"))

    def test_steps_and_dates_reach_visual_plan(self):
        nodes = extract_relationship_nodes("第1步：接收\n第2步：分类\n第3步：处理")
        self.assertEqual([n["text"] for n in nodes], ["接收", "分类", "处理"])
        self.assertEqual(extract_relationship_nodes("9月1日：开营")[0]["label"], "9月1日")

    def test_transparent_infographic_is_allowed_and_recorded(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hero.png"
            Image.new("RGBA", (200, 300), (0, 0, 0, 0)).save(path)
            inspection = inspect_asset(path, "PNG")
            self.assertTrue(inspection["has_transparency"])
            self.assertEqual(inspection["alpha_extrema"], [0, 0])

    def test_fake_png_is_rejected_by_registration_and_upload(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            path = Path(tmp) / "hero.png"
            path.write_bytes(b"not a PNG")
            with self.assertRaises(ValueError):
                register(str(path))
            with patch.object(feishu_cli, "_run_cli") as remote:
                self.assertEqual(feishu_cli.upload_image(str(path), dry_run=True)["status"], "invalid_media")
                remote.assert_not_called()

    def test_missing_prompt_hash_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            report = run_pipeline(COPY, Path(tmp), name="hash")
            bundle = Path(report["card"]).parent
            path = bundle / "hero.png"
            write_test_png(path)
            register(str(path), prompt=report["image_prompt"])
            manifest = bundle / "hero-generation.json"
            data = json.loads(manifest.read_text())
            data.pop("prompt_sha256")
            manifest.write_text(json.dumps(data))
            report = resume(report["editable_spec"], "img_test_only")
            self.assertFalse(report["readiness"]["image_ready"])
            self.assertIsNotNone(feishu_cli._image_upload_gate(path))

    def test_resume_preserves_manual_copy_button_and_requires_fresh_review(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            report = run_pipeline(COPY, Path(tmp), name="resume")
            spec_path = Path(report["editable_spec"])
            spec = json.loads(spec_path.read_text())
            spec["blocks"].append({"type": "section", "title": "📌 下一步", "body": "进行评审"})
            spec_path.write_text(json.dumps(spec, ensure_ascii=False))
            path = spec_path.parent / "hero.png"
            write_test_png(path)
            register(str(path), prompt=report["image_prompt"])
            report = resume(str(spec_path), "img_contract_test")
            self.assertEqual(report["status"], "needs_visual_review")
            card = json.loads(Path(report["card"]).read_text())
            self.assertIn("进行评审", json.dumps(card, ensure_ascii=False))
            self.assertIn("https://open.feishu.cn", json.dumps(card))
            self.assertEqual(json.loads(spec_path.read_text())["scene"], spec["scene"])
            self.assertEqual(feishu_cli._image_readiness_gate(Path(report["card"]))["status"], "visual_review_required")
            with self.assertRaises(ValueError):
                record_review(str(spec_path), "Notes alone must not pass.")
            report = record_review(str(spec_path), "Synthetic fixture review for gate contract only.", desktop=path, mobile=path)
            self.assertTrue(report["readiness"]["visual_review_ready"])
            edition = "doubao" if "doubao" in report else "codex"
            self.assertTrue(report[edition]["card_image_contract"]["status"].startswith("embedded_"))
            manifest = json.loads(spec_path.with_name("resume.cardkit-import.json").read_text())
            self.assertEqual(manifest["status"], "ready_for_cardkit_import")
            self.assertTrue(manifest["ai_generation_ready"])
            self.assertIsNone(feishu_cli._image_readiness_gate(Path(report["card"])))
            card["header"]["title"]["content"] += "修改"
            Path(report["card"]).write_text(json.dumps(card))
            self.assertEqual(feishu_cli._image_readiness_gate(Path(report["card"]))["status"], "stale_artifact")

    def test_changed_canonical_source_cannot_keep_old_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = run_pipeline(COPY, Path(tmp), name="source")
            path = Path(report["editable_spec"])
            spec = json.loads(path.read_text())
            spec["analysis"]["source_text"] += "篡改"
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "source hash"):
                resume(str(path))

    def test_json_import_never_calls_remote(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text((ROOT / "tests/fixtures/minimal.card").read_text())
            with patch.object(feishu_cli, "_run_byted_cli") as remote:
                result = feishu_cli.push_cardkit(str(path), dry_run=True)
                self.assertEqual(result["status"], "unsupported_extension")
                remote.assert_not_called()

    def test_color_normalization_cannot_leave_old_bytes_for_import(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as tmp:
            card = json.loads((ROOT / "tests/fixtures/minimal.card").read_text())
            card["body"]["elements"][0]["text_color"] = "brand_accent"
            path = Path(tmp) / "legacy.card"
            path.write_text(json.dumps(card))
            with patch.object(feishu_cli, "_run_byted_cli") as remote:
                self.assertEqual(feishu_cli.push_cardkit(str(path), dry_run=True)["status"], "recompile_required")
                remote.assert_not_called()

    def test_package_allows_clean_unpack_and_excludes_user_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = package_skill.package(Path(tmp) / "skill.zip")
            with ZipFile(output) as archive:
                self.assertIn(package_skill.TOP_LEVEL + "/outputs/.gitkeep", archive.namelist())
                self.assertFalse(any("/inputs/" in n or "/.env" in n for n in archive.namelist()))
                archive.extractall(Path(tmp) / "unpack")
            extracted = Path(tmp) / "unpack" / package_skill.TOP_LEVEL
            proc = subprocess.run([sys.executable, "scripts/stable_card.py", "--text", COPY,
                                   "--name", "smoke", "--no-image"], cwd=extracted, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["status"], "ready")
            self.assertFalse(package_skill.should_include(ROOT / "inputs/private.txt"))
            self.assertFalse(package_skill.should_include(ROOT / ".env"))
