import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - the Skill runtime installs Pillow
    Image = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from auto_layout import build_auto_spec  # noqa: E402
from generate_card import build_card, compile_outputs  # noqa: E402
from media_assets import build_manifest  # noqa: E402
from validate_card import validate  # noqa: E402


class MediaAssetTests(unittest.TestCase):
    def test_animated_asset_is_inspected_without_writing_a_static_frame(self) -> None:
        if Image is None:
            self.skipTest("Pillow is required for media tests")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = [
                Image.new("RGBA", (320, 180), (26, 74, 110, 255)),
                Image.new("RGBA", (320, 180), (116, 67, 150, 255)),
            ]
            gif_path = root / "course-motion.gif"
            frames[0].save(
                gif_path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=[120, 180],
                loop=0,
            )

            manifest_without_fallback = build_manifest([gif_path])
            manifest = build_manifest([gif_path])
            written = root / "manifest.json"
            written.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            companion_dir_exists = (root / "fallbacks").exists()

        asset = manifest["assets"][0]
        self.assertEqual(manifest["image_source"], "real_image")
        self.assertEqual(asset["image_source"], "real_image")
        self.assertTrue(asset["animated"])
        self.assertEqual(asset["frame_count"], 2)
        self.assertEqual(asset["duration_ms_scanned"], 300)
        self.assertTrue(manifest_without_fallback["quality_gate"]["sendable"])
        self.assertFalse(manifest["quality_gate"]["animated_assets_have_static_companion"])
        self.assertTrue(manifest["quality_gate"]["sendable"])
        self.assertTrue(manifest["policy"]["direct_gif_embedding_supported"])
        self.assertFalse(companion_dir_exists)

    def test_switcher_spec_requires_application_bot_and_real_img_keys(self) -> None:
        spec = {
            "type": "custom",
            "title": "课程视觉预览",
            "summary": "课程视觉预览",
            "blocks": [
                {
                    "type": "media_switcher",
                    "id": "course_visuals",
                    "active_index": 0,
                    "items": [
                        {"id": "overview", "label": "课程总览", "img_key": "img_overview_key", "alt": "课程总览"},
                        {"id": "path", "label": "学习路径", "img_key": "img_path_key", "alt": "学习路径"},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            card, _hero_plan, contracts = build_card(spec, root / "switcher")
            compiled_card, compile_report = compile_outputs(spec, root / "compiled.card")
            interaction = json.loads((root / "compiled.interaction.json").read_text(encoding="utf-8"))

        application_result = validate(compiled_card, surface="application-bot")
        custom_result = validate(compiled_card, surface="custom-bot")
        self.assertTrue(application_result["ok"], application_result["errors"])
        self.assertFalse(custom_result["ok"])
        self.assertEqual(application_result["stats"]["images"], 1)
        self.assertEqual(application_result["stats"]["buttons"], 2)
        self.assertEqual(application_result["stats"]["callbacks"], 2)
        self.assertEqual(len(contracts), 2)
        self.assertEqual(compile_report["callbacks"], 2)
        self.assertEqual(len(interaction["actions"]), 2)
        self.assertTrue(all(item["action"] == "switch_media" for item in contracts))
        self.assertEqual(
            {target for target in ("overview", "path") if target in json.dumps(compiled_card, ensure_ascii=False)},
            {"overview", "path"},
        )

    def test_auto_layout_records_switcher_contract_before_assets_exist(self) -> None:
        spec = build_auto_spec("课程宣传\n需要支持图片切换：课程总览、学习路径")
        contract = spec["media_contract"]
        design = spec["analysis"]["design_plan"]
        switcher = next(item for item in design["component_strategy"] if item["component"] == "media_switcher")

        self.assertEqual(contract["mode"], "switcher")
        self.assertTrue(contract["requires_application_bot"])
        self.assertTrue(spec["analysis"]["media_requests"][0]["requires_application_bot"])
        self.assertEqual(design["navigation_strategy"]["mode"], "callback_media_switcher")
        self.assertEqual(switcher["status"], "needs_assets")


if __name__ == "__main__":
    unittest.main()
