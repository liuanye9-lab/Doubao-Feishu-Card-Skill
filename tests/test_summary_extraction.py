import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from summary_extraction import classify_content, extract_structured_sections  # noqa: E402


class SummaryExtractionTests(unittest.TestCase):
    def test_notice_keeps_schedule_and_actions_source_locked(self) -> None:
        source = "活动通知\n报名截止9月15日\n请提交作品"
        result = extract_structured_sections(source)
        self.assertEqual(result["mode"], "notice")
        rendered = [item["text"] for section in result["sections"] for item in section["items"]]
        self.assertEqual(rendered, ["活动通知", "报名截止9月15日", "请提交作品"])
        self.assertEqual(result["unassigned_source_lines"], [])

    def test_meeting_summary_uses_topic_confirmed_and_todo_buckets(self) -> None:
        source = "会议纪要\n讨论上线时间\n确认周五发布\n待办：小王补充文档"
        result = extract_structured_sections(source)
        self.assertEqual(result["mode"], "meeting_summary")
        by_id = {section["id"]: section for section in result["sections"]}
        self.assertIn("讨论上线时间", [item["text"] for item in by_id["topics"]["items"]])
        self.assertIn("确认周五发布", [item["text"] for item in by_id["confirmed"]["items"]])
        self.assertIn("待办：小王补充文档", [item["text"] for item in by_id["todo"]["items"]])

    def test_work_report_does_not_invent_owner_or_deadline(self) -> None:
        source = "本周工作总结\n已完成数据清洗\n进行中：看板验收\n下一步：补充说明"
        result = extract_structured_sections(source)
        self.assertEqual(result["mode"], "work_report")
        text = "\n".join(item["text"] for section in result["sections"] for item in section["items"])
        self.assertNotIn("负责人", text)
        self.assertNotIn("DDL", text)
        self.assertIn("数据清洗", text)
        self.assertIn("看板验收", text)

    def test_explicit_mode_is_supported_for_low_ambiguity_routing(self) -> None:
        result = classify_content("任意内容", explicit_mode="meeting_summary")
        self.assertEqual(result["mode"], "meeting_summary")
        self.assertEqual(result["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
