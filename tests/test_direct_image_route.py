import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from doubao_pipeline import run_pipeline  # noqa: E402
from html_infographic import build_html_artifact, choose_render_strategy  # noqa: E402


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


class DirectImageRouteTests(unittest.TestCase):
    def test_dense_copy_stays_direct_and_creates_no_html_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(DENSE_COPY, Path(temp_dir), name="dense-direct", requested_scene="case-showcase")
            bundle = Path(temp_dir) / "dense-direct"

        self.assertEqual(report["media"]["render_strategy"], "native_model")
        self.assertNotIn("html_infographic", report)
        self.assertNotIn("html_render_plan", report)
        self.assertFalse(list(bundle.glob("*.infographic.html")))
        self.assertFalse(list(bundle.glob("*.html-prompt.md")))
        self.assertFalse(list(bundle.glob("*.html-render-plan.json")))

    def test_legacy_html_request_migrates_to_direct_model(self) -> None:
        spec = {"hero": {}, "render_strategy": "html_infographic_to_png"}
        self.assertEqual(choose_render_strategy(spec, explicit_strategy="html_infographic_to_png"), "native_model")
        self.assertEqual(spec["render_strategy"], "native_model")

    def test_html_builder_is_retired(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "HTML→PNG 信息图路径已移除"):
            build_html_artifact({}, Path("/tmp/should-not-be-written.html"))


if __name__ == "__main__":
    unittest.main()
