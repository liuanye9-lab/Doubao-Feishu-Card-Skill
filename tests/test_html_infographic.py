import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from doubao_pipeline import run_pipeline  # noqa: E402
from feishu_cli import _image_upload_gate  # noqa: E402
from finalize_card import resume  # noqa: E402
from html_infographic import html_source_is_safe  # noqa: E402


DENSE_COPY = """象上汇｜AI驱动的师徒带教数字化管理体系
一句话介绍：针对汤泉行业员工流失率高、师徒带教过程不可视的痛点，基于飞书多维表格与智能体搭建数字化管理体系。
带教完成率：95%以上
独立上岗周期：缩短30%
3个月留存率：提升20pct
人资管理耗时：减少70%
# 业务痛点
带教过程黑盒化，师傅每天教了什么、徒弟掌握多少没有记录；不同师傅带教内容、节奏和质量差异大；新人缺乏及时反馈，试用期流失率偏高。
# 核心功能模块
模块一：标准化带教计划模板，按岗位预置四周计划并自动匹配师傅。
模块二：师徒每日双向打卡，智能体自动提醒并识别评分差异。
模块三：每周生成带教复盘报告，汇总完成率、掌握度趋势和异常名单。
模块四：月底生成评估报告，给出转正、延长带教或重点关注建议。
# 核心价值
构建每日打卡、每周复盘、月度评估到转正建议的闭环，让带教进度可视、质量可量、问题可预警。"""


class HtmlInfographicTests(unittest.TestCase):
    def test_dense_structured_copy_auto_routes_to_html_png_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(
                DENSE_COPY,
                Path(temp_dir),
                name="dense-html",
                requested_scene="case-showcase",
            )
            bundle = Path(temp_dir) / "dense-html"
            html_path = bundle / "dense-html.infographic.html"
            image_path = bundle / "hero.png"
            manifest_path = bundle / "hero-generation.json"

            self.assertEqual(report["media"]["render_strategy"], "html_infographic_to_png")
            self.assertTrue(html_path.is_file())
            self.assertTrue(image_path.is_file())
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["tool"], "html_to_png")
            self.assertEqual(manifest["render_strategy"], "html_infographic_to_png")
            self.assertTrue(report["html_infographic"]["generation"]["ready"])
            self.assertIsNone(_image_upload_gate(image_path))

            resumed = resume(report["editable_spec"])

        self.assertEqual(resumed["media_task"]["render_strategy"], "html_infographic_to_png")
        self.assertEqual(resumed["media_task"]["tool_hint"], "html_to_png")
        self.assertTrue(resumed["readiness"]["html_render_ready"])
        self.assertFalse(resumed["readiness"]["image_ready"])

    def test_short_copy_keeps_native_model_first_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(
                "产品发布\n9月4日 14:00 开始\n三项能力：自动整理、可视化表达、一步发送",
                Path(temp_dir),
                name="short-native",
            )

        self.assertEqual(report["media"]["render_strategy"], "native_model")
        self.assertEqual(report["html_infographic"]["status"], "not_selected")
        self.assertFalse((Path(temp_dir) / "short-native" / "short-native.infographic.html").exists())

    def test_html_route_rejects_scripts_and_external_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "unsafe.html"
            html_path.write_text(
                '<main data-render-strategy="html_infographic_to_png">'
                '<script>document.body.innerHTML = "bad"</script>'
                '<img src="https://example.com/remote.png">'
                "</main>",
                encoding="utf-8",
            )

            self.assertFalse(html_source_is_safe(html_path))


if __name__ == "__main__":
    unittest.main()
