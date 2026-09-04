import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cardkit_format import extract_dsl, safe_card_name, write_cardkit_bundle  # noqa: E402
from validate_card import validate  # noqa: E402


class CardKitFormatTests(unittest.TestCase):
    def test_raw_card_gets_a_web_editor_wrapper_without_changing_raw(self) -> None:
        raw = {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {"title": {"tag": "plain_text", "content": "合并测试"}},
            "body": {"elements": []},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "demo.card"
            raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            result = write_cardkit_bundle(raw_path, card_name="合并测试", base_name="demo")
            wrapper = json.loads(Path(result["cardkit_card"]).read_text(encoding="utf-8"))
            self.assertEqual(json.loads(raw_path.read_text(encoding="utf-8")), raw)

        self.assertEqual(list(wrapper), ["name", "dsl", "variables"])
        self.assertEqual(wrapper["name"], "合并测试")
        self.assertEqual(wrapper["dsl"]["schema"], "2.0")
        self.assertEqual(wrapper["variables"], [])
        self.assertTrue(result["validation"]["ok"])
        self.assertEqual(result["cardkit_card"].split("/")[-1], "demo.cardkit.card")

    def test_converter_normalizes_dirty_wrapper_and_is_idempotent(self) -> None:
        dirty = {
            "name": "原名",
            "dsl": json.dumps({
                "schema": 2.0,
                "config": {"update_multi": False},
                "card_link": {"url": ""},
                "header": {"title": {"tag": "plain_text", "content": "原名"}},
                "body": {"elements": []},
            }, ensure_ascii=False),
            "variables": ["x"],
        }
        dsl, name, variables = extract_dsl(dirty)
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "dirty.json"
            raw_path.write_text(json.dumps(dirty, ensure_ascii=False), encoding="utf-8")
            raw_path2 = Path(temp_dir) / "raw.card"
            raw_path2.write_text(json.dumps({**dsl, "schema": "2.0"}, ensure_ascii=False), encoding="utf-8")
            first = write_cardkit_bundle(raw_path, Path(temp_dir), card_name=name, base_name="first", variables=variables)
            second = write_cardkit_bundle(raw_path2, Path(temp_dir), card_name="原名", base_name="second", variables=["x"])

        self.assertEqual(first["variables"], ["x"])
        self.assertIn('schema normalized to "2.0"', first["fixes"])
        self.assertIn("removed empty card_link", first["fixes"])
        self.assertIn("config.update_multi normalized to true", first["fixes"])
        self.assertTrue(first["validation"]["ok"])
        self.assertTrue(second["validation"]["ok"])

    def test_converter_removes_legacy_cardkit_color_aliases(self) -> None:
        raw = {
            "schema": "2.0",
            "config": {
                "update_multi": True,
                "style": {"color": {"brand_accent": {"light_mode": "rgba(66,102,102,1)"}}},
            },
            "header": {"title": {"tag": "plain_text", "content": "颜色兼容"}},
            "body": {"elements": [{
                "tag": "div",
                "text": {"tag": "plain_text", "content": "标签", "text_color": "brand_accent"},
            }]},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "legacy.card"
            raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            result = write_cardkit_bundle(raw_path, Path(temp_dir), card_name="颜色兼容", base_name="legacy")
            wrapper = json.loads(Path(result["cardkit_card"]).read_text(encoding="utf-8"))

        self.assertTrue(result["validation"]["ok"])
        self.assertIn("normalized legacy text_color", " ".join(result["fixes"]))
        self.assertIn("removed non-portable custom config.style.color", result["fixes"])
        self.assertNotIn("brand_accent", json.dumps(wrapper, ensure_ascii=False))
        self.assertEqual(wrapper["dsl"]["body"]["elements"][0]["text"]["text_color"], "blue")

    def test_cardkit_filename_is_cross_platform_safe(self) -> None:
        self.assertEqual(safe_card_name("CON"), "untitled")
        self.assertEqual(safe_card_name("a/b:c*?"), "a_b_c_")
        self.assertLessEqual(len(safe_card_name("x" * 300)) + len(".card"), 200)

    def test_validator_accepts_cardkit_wrapper_and_enforces_house_rules(self) -> None:
        raw = {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {"title": {"tag": "plain_text", "content": "测试"}},
            "body": {"elements": [{
                "tag": "collapsible_panel",
                "header": {
                    "title": {"tag": "plain_text", "content": "详情"},
                    "icon": {"tag": "standard_icon", "token": "down_outlined", "color": "grey"},
                    "icon_position": "right",
                    "icon_expanded_angle": -180,
                },
                "elements": [],
            }]},
        }
        wrapper = {"name": "测试", "dsl": raw, "variables": []}
        self.assertTrue(validate(wrapper)["ok"])
        bad = json.loads(json.dumps(wrapper))
        bad["dsl"]["body"]["elements"][0]["header"].pop("icon")
        self.assertFalse(validate(bad)["ok"])
        self.assertTrue(any("header.icon" in error for error in validate(bad)["errors"]))


if __name__ == "__main__":
    unittest.main()
