import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_card import KNOWN_TAGS, validate  # noqa: E402


class SourceSchemaReferenceTests(unittest.TestCase):
    def test_public_schema_and_registry_are_source_backed_without_internal_id(self):
        schema = json.loads((ROOT / "references" / "card-schema.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "presets" / "card-studio-registry.json").read_text(encoding="utf-8"))

        self.assertEqual(schema["$id"], "urn:doubao-feishu-card:card-schema-2.0")
        self.assertNotIn("code.byted.org", json.dumps(schema, ensure_ascii=False))
        self.assertEqual(registry["source_use"], "public-safe-reference")
        self.assertTrue(registry["card_schema"]["default_config"]["summary_required_for_delivery"])
        self.assertTrue((ROOT / "scripts" / "validate_card_schema.ts").is_file())

    def test_schema_component_tags_are_known_to_public_validator(self):
        schema = json.loads((ROOT / "references" / "card-schema.json").read_text(encoding="utf-8"))
        tags = set()

        def visit(value):
            if isinstance(value, dict):
                properties = value.get("properties")
                tag = properties.get("tag") if isinstance(properties, dict) else None
                if isinstance(tag, dict):
                    if "const" in tag:
                        tags.add(tag["const"])
                    tags.update(item for item in tag.get("enum", []) if isinstance(item, str))
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(schema)
        self.assertTrue(tags <= KNOWN_TAGS)
        self.assertIn("button", tags)
        self.assertIn("collapsible_panel", tags)
        self.assertIn("picker_date", tags)

    def test_source_nesting_rule_rejects_table_and_form_inside_column(self):
        card = {
            "schema": "2.0",
            "config": {"update_multi": True},
            "header": {"title": {"tag": "plain_text", "content": "嵌套检查"}},
            "body": {
                "elements": [
                    {
                        "tag": "column_set",
                        "flex_mode": "flow",
                        "columns": [
                            {
                                "tag": "column",
                                "width": "weighted",
                                "weight": 1,
                                "elements": [
                                    {"tag": "table", "columns": [{"name": "事项"}], "rows": []},
                                    {"tag": "form", "name": "nested", "elements": []},
                                ],
                            }
                        ],
                    }
                ]
            },
        }

        result = validate(card)
        self.assertFalse(result["ok"])
        self.assertTrue(any("table components are only supported" in item for item in result["errors"]))
        self.assertTrue(any("form containers are only supported" in item for item in result["errors"]))


if __name__ == "__main__":
    unittest.main()
