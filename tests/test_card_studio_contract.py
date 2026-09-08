import sys
import unittest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from card_studio_contract import (  # noqa: E402
    build_generation_workflow,
    build_input_brief,
    build_quality_gates,
)


class CardStudioContractTests(unittest.TestCase):
    def _card(self):
        return {
            "schema": "2.0",
            "config": {"update_multi": True, "summary": {"content": "案例展示与人工巡检"}},
            "header": {"title": {"tag": "plain_text", "content": "案例展示"}},
            "body": {"direction": "vertical", "elements": [{"tag": "markdown", "content": "⚠️ 问题与做法"}]},
        }

    def test_input_brief_keeps_recipient_as_context(self):
        brief = build_input_brief(
            "案例展示\n问题：人工巡检",
            purpose="作品提交",
            recipient="大赛群",
            material_kind="document_extract",
        )

        self.assertEqual(brief["material"]["canonical_source"], "source_text")
        self.assertEqual(brief["purpose"]["role"], "layout_and_content_context_only")
        self.assertEqual(brief["recipient"]["role"], "delivery_context_only")
        self.assertIn("explicitly resolved and confirmed", brief["delivery_target_policy"])

    def test_image_cta_is_manual_and_cardkit_requires_same_dsl(self):
        card = self._card()
        wrapper = {"name": "案例展示", "dsl": card, "variables": []}
        validation = {
            "ok": True,
            "stats": {
                "buttons": 0,
                "callbacks": 0,
                "visible_text_chars": 7,
                "max_text_block_chars": 7,
                "emoji_count": 1,
                "charts": 0,
            },
        }
        spec = {
            "blocks": [{"type": "text", "content": "⚠️ 问题与做法"}],
            "emoji_mode": "semantic",
            "visual_spec": {
                "image_required": True,
                "visual_type": "thematic",
                "information_carrier": True,
                "not_decorative": True,
                "information_purpose": "把来源主张转成可读信息锚点",
                "visual_job": "展示来源主张",
                "source_spans": [{"role": "claim", "text": "问题：人工巡检"}],
            },
            "analysis": {"source_text": "案例展示\n问题：人工巡检", "source_locked": True, "source_sha256": "sha"},
        }

        gates = build_quality_gates(
            card,
            spec,
            validation,
            wrapper=wrapper,
            cardkit_valid=True,
            image_required=True,
            visual_output_ready=True,
            image_ready=True,
        )
        by_id = {item["id"]: item for item in gates["gates"]}

        self.assertEqual(by_id["cardkit_parity"]["status"], "pass")
        self.assertEqual(by_id["image_cta_separation"]["status"], "manual_review")
        self.assertTrue(gates["structural_passed"])
        self.assertNotIn("image_cta_separation", [item["id"] for item in gates["gates"] if item["required"]])

        workflow = build_generation_workflow(
            gates,
            validation_ok=True,
            scene_contract_ok=True,
            image_required=True,
            visual_output_ready=True,
            image_ready=False,
            cardkit_valid=True,
        )
        self.assertEqual(workflow["stages"][-1]["status"], "needs_media")

    def test_image_information_contract_blocks_decorative_or_unplanned_visuals(self):
        card = self._card()
        wrapper = {"name": "案例展示", "dsl": card, "variables": []}
        validation = {"ok": True, "stats": {"visible_text_chars": 7, "max_text_block_chars": 7, "emoji_count": 1, "buttons": 0, "callbacks": 0, "charts": 0}}
        gates = build_quality_gates(
            card,
            {
                "blocks": [{"type": "text", "content": "⚠️ 问题与做法"}],
                "emoji_mode": "semantic",
                "visual_spec": {"image_required": True, "visual_type": "thematic"},
                "analysis": {"source_text": "案例展示\n问题：人工巡检", "source_locked": True, "source_sha256": "sha"},
            },
            validation,
            wrapper=wrapper,
            cardkit_valid=True,
            image_required=True,
            visual_output_ready=True,
            image_ready=True,
        )
        by_id = {item["id"]: item for item in gates["gates"]}
        self.assertEqual(by_id["image_information_contract"]["status"], "blocked")
        self.assertIn("image_information_contract", gates["structural_failures"])


if __name__ == "__main__":
    unittest.main()
