import json
import hashlib
import sys
import tempfile
import unittest
from media_fixtures import write_test_png
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from auto_layout import build_auto_spec  # noqa: E402
from asset_validation import validate_image_contract  # noqa: E402
from preview_card import EditorState, contains_tag  # noqa: E402


class PreviewCardTests(unittest.TestCase):
    def test_local_preview_displays_complete_seedream_image_but_is_not_sendable(self) -> None:
        spec = build_auto_spec(
            "AI先锋大赛\n"
            "时间线：\n"
            "8月24日-9月4日：\n"
            "- 8月25日多维表格培训\n"
            "9月15日：\n"
            "- 提交作品\n",
            design_plan={"media_policy": {"need_hero": True}},
        )
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            bundle = Path(temp_dir)
            spec_path = bundle / "demo.spec.json"
            card_path = bundle / "demo.card"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            image_path = bundle / "hero.png"
            write_test_png(image_path)
            prompt_path = bundle / "demo.image-prompt.md"
            prompt_path.write_text("Seedream 5.0 Pro-class test prompt\n", encoding="utf-8")
            (bundle / "hero-generation.json").write_text(
                json.dumps({
                    "tool": "doubao.image_gen",
                    "generation_family": "seedream-class",
                    "generation_mode": "seedream_5_pro_direct_full_card",
                    "text_policy": "seedream_5_pro_direct_selected_text_and_layout",
                    "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                    "prompt_file": str(prompt_path),
                    "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
                    "asset_contract": validate_image_contract(
                        image_path,
                        expected_aspect_ratio="2:3",
                        expected_format="PNG",
                    ),
                }),
                encoding="utf-8",
            )
            state = EditorState(spec_path, card_path, spec_path)
            result = state.preview(spec)

        self.assertTrue(result["report"]["local_visual"]["displayed"])
        self.assertFalse(result["report"]["sendable"])
        self.assertTrue(contains_tag(result["card"], {"img"}))
        image = next(item for item in result["card"]["body"]["elements"] if item.get("tag") == "img")
        self.assertEqual(image["local_preview_src"], "/api/visual")


if __name__ == "__main__":
    unittest.main()
