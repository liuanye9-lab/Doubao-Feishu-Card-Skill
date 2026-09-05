import json
import hashlib
import tempfile
import sys
import unittest
from media_fixtures import write_test_png
from pathlib import Path
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import feishu_cli  # noqa: E402
from cardkit_format import wrap_card  # noqa: E402
from register_motion_generation import register as register_motion  # noqa: E402


FIXTURE = ROOT / "tests" / "fixtures" / "minimal.card"


class FeishuCliAdapterTests(unittest.TestCase):
    def test_decode_json_skips_cli_notice(self) -> None:
        self.assertEqual(feishu_cli._decode_json("notice\n{\"ok\":true}"), {"ok": True})

    def test_create_cardkit_requires_confirmation_for_remote_write(self) -> None:
        with patch.object(feishu_cli, "_run_cli") as run_cli:
            result = feishu_cli.create_cardkit(str(FIXTURE), identity="bot")

        self.assertEqual(result["status"], "confirmation_required")
        run_cli.assert_not_called()

    def test_upload_image_requires_confirmation_for_remote_write(self) -> None:
        with patch.object(feishu_cli, "_run_cli") as run_cli:
            result = feishu_cli.upload_image(str(FIXTURE), identity="bot")

        self.assertEqual(result["status"], "confirmation_required")
        run_cli.assert_not_called()

    def test_upload_image_rejects_unregistered_hero(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            image_path = Path(temp_dir) / "hero.png"
            write_test_png(image_path)
            with patch.object(feishu_cli, "_run_cli") as run_cli:
                result = feishu_cli.upload_image(str(image_path), identity="bot", dry_run=True)

        self.assertEqual(result["status"], "visual_provenance_missing")
        self.assertIn("Seedream 5.0 Pro 一次性完整卡片图片", result["message"])
        run_cli.assert_not_called()

    def test_upload_image_accepts_verified_direct_seedream_hero(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "hero.png"
            write_test_png(image_path)
            prompt_path = temp_path / "prompt.md"
            prompt_path.write_text("Seedream 5.0 Pro direct full card prompt\n", encoding="utf-8")
            (temp_path / "hero-generation.json").write_text(
                json.dumps({
                    "tool": "doubao.image_gen",
                    "generation_family": "seedream-class",
                    "text_policy": "seedream_5_pro_direct_selected_text_and_layout",
                    "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                    "prompt_file": str(prompt_path),
                    "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
                }),
                encoding="utf-8",
            )
            with patch.object(
                feishu_cli,
                "_run_cli",
                return_value=(0, {"ok": True, "data": {"image_key": "img_direct"}}, ""),
            ) as run_cli:
                result = feishu_cli.upload_image(str(image_path), identity="bot", dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["image_key"], "img_direct")
        run_cli.assert_called_once()

    def test_upload_image_accepts_verified_banner_seedream_hero(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "hero.png"
            write_test_png(image_path)
            prompt_path = temp_path / "prompt.md"
            prompt_path.write_text("Seedream 5.0 Pro banner prompt\n", encoding="utf-8")
            (temp_path / "hero-generation.json").write_text(
                json.dumps({
                    "tool": "doubao.image_gen",
                    "generation_family": "seedream-class",
                    "generation_mode": "seedream_5_pro_banner_plus_native_card",
                    "text_policy": "seedream_5_pro_banner_selected_text_and_layout",
                    "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                    "prompt_file": str(prompt_path),
                    "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
                }),
                encoding="utf-8",
            )
            with patch.object(
                feishu_cli,
                "_run_cli",
                return_value=(0, {"ok": True, "data": {"image_key": "img_banner"}}, ""),
            ) as run_cli:
                result = feishu_cli.upload_image(str(image_path), identity="bot", dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["image_key"], "img_banner")
        run_cli.assert_called_once()

    @unittest.skipIf(Image is None, "Pillow is required for GIF tests")
    def test_upload_image_accepts_verified_seedance_gif(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            image_path = temp_path / "hero.gif"
            frames = [
                Image.new("RGB", (240, 360), (31, 86, 176)),
                Image.new("RGB", (240, 360), (44, 164, 132)),
            ]
            frames[0].save(
                image_path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=180,
                loop=0,
            )
            prompt_path = temp_path / f"{temp_path.name}.motion-prompt.md"
            prompt_path.write_text("Seedance 2.5 direct GIF task\n", encoding="utf-8")
            register_motion(str(image_path), prompt=str(prompt_path))
            with patch.object(
                feishu_cli,
                "_run_cli",
                return_value=(0, {"ok": True, "data": {"image_key": "img_motion"}}, ""),
            ) as run_cli:
                result = feishu_cli.upload_image(str(image_path), identity="bot", dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["image_key"], "img_motion")
        run_cli.assert_called_once()

    def test_remote_card_action_blocks_unfinished_image_bundle(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            card_path = temp_path / "gated.card"
            card_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            (temp_path / "gated.report.json").write_text(
                json.dumps({
                    "doubao": {"image_required": True},
                    "readiness": {"image_ready": False, "seedream_output_ready": False},
                }),
                encoding="utf-8",
            )
            with patch.object(feishu_cli, "_run_cli") as run_cli:
                result = feishu_cli.create_cardkit(str(card_path), dry_run=True)

        self.assertEqual(result["status"], "image_required")
        self.assertIn("Seedream 5.0 Pro 直出的 hero.png", result["message"])
        run_cli.assert_not_called()

    def test_create_cardkit_dry_run_reads_card_id(self) -> None:
        payload = {"ok": True, "data": {"card_id": "card_test"}}
        with patch.object(feishu_cli, "_run_cli", return_value=(0, payload, "")) as run_cli:
            result = feishu_cli.create_cardkit(str(FIXTURE), identity="bot", dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["card_id"], "card_test")
        args, kwargs = run_cli.call_args
        self.assertIn("/open-apis/cardkit/v1/cards", args[0])
        request = json.loads(kwargs["stdin"])
        self.assertEqual(request["type"], "card_json")
        self.assertEqual(json.loads(request["data"])["schema"], "2.0")

    def test_push_cardkit_reads_web_backed_card_id_as_template_id(self) -> None:
        payload = {
            "status": "success",
            "data": {"result": {"card_id": "template_from_web_backed_import"}},
        }

        self.assertEqual(
            feishu_cli._template_id_from(payload),
            "template_from_web_backed_import",
        )

    def test_push_cardkit_requires_confirmation_for_remote_write(self) -> None:
        with patch.object(feishu_cli, "_run_byted_cli") as run_cli:
            result = feishu_cli.push_cardkit(str(FIXTURE))

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["card_name"], "测试卡片")
        run_cli.assert_not_called()

    def test_push_cardkit_dry_run_uses_raw_card_and_name(self) -> None:
        payload = {"status": "success", "data": {"template_id": "tpl_test"}}
        with patch.object(feishu_cli, "_run_byted_cli", return_value=(0, payload, "")) as run_cli:
            result = feishu_cli.push_cardkit(str(FIXTURE), dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["template_id"], "tpl_test")
        args, kwargs = run_cli.call_args
        self.assertEqual(args[0][:4], ["feishu", "cardkit", "template", "import"])
        self.assertIn("--file", args[0])
        self.assertIn("--name", args[0])
        self.assertEqual(kwargs["dry_run"], True)

    def test_push_cardkit_verifies_template_get_and_list(self) -> None:
        def fake_byted(args, **kwargs):
            if args[3] == "import":
                return 0, {"status": "success", "data": {"template_id": "tpl_verified"}}, ""
            if args[3] == "get":
                return 0, {"status": "success", "data": {"template_id": "tpl_verified", "name": "测试卡片"}}, ""
            if args[3] == "list":
                return 0, {"status": "success", "data": {"items": [{"template_id": "tpl_verified", "name": "测试卡片"}]}}, ""
            raise AssertionError(args)

        with patch.object(feishu_cli, "_run_byted_cli", side_effect=fake_byted) as run_cli:
            result = feishu_cli.push_cardkit(str(FIXTURE), confirm=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "cardkit_imported")
        self.assertTrue(result["evidence"]["template_list_match"])
        self.assertEqual(run_cli.call_count, 3)

    def test_push_cardkit_rejects_web_wrapper(self) -> None:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            wrapper_path = Path(temp_dir) / "wrapped.cardkit.card"
            wrapper_path.write_text(json.dumps(wrap_card(raw, "包装卡片"), ensure_ascii=False), encoding="utf-8")
            with patch.object(feishu_cli, "_run_byted_cli") as run_cli:
                result = feishu_cli.push_cardkit(str(wrapper_path), dry_run=True)

        self.assertEqual(result["status"], "unsupported_input")
        run_cli.assert_not_called()

    def test_cli_accepts_cardkit_wrapper_for_api_delivery(self) -> None:
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            wrapper_path = Path(temp_dir) / "wrapped.card"
            wrapper_path.write_text(json.dumps(wrap_card(raw, "包装卡片"), ensure_ascii=False), encoding="utf-8")
            with patch.object(feishu_cli, "_run_cli", return_value=(0, {"ok": True, "data": {"card_id": "wrapped"}}, "")):
                result = feishu_cli.create_cardkit(str(wrapper_path), dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["card_id"], "wrapped")

    def test_create_cardkit_rejects_user_identity(self) -> None:
        with patch.object(feishu_cli, "_run_cli") as run_cli:
            result = feishu_cli.create_cardkit(str(FIXTURE), identity="user", dry_run=True)

        self.assertEqual(result["status"], "unsupported_identity")
        run_cli.assert_not_called()

    def test_send_card_dry_run_uses_chat_id(self) -> None:
        payload = {"ok": True, "data": {"message_id": "om_test"}}
        with patch.object(feishu_cli, "_run_cli", return_value=(0, payload, "")) as run_cli:
            result = feishu_cli.send_card(str(FIXTURE), chat_id="oc_test", dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["message_id"], "om_test")
        args, _ = run_cli.call_args
        self.assertIn("--chat-id", args[0])
        self.assertIn("oc_test", args[0])

    def test_preview_card_dry_run_targets_current_user_with_bot(self) -> None:
        def fake_cli(args, **kwargs):
            if args[:2] == ["whoami", "--as"] and args[2] == "bot":
                return 0, {"available": True, "tokenStatus": "ready"}, ""
            if args[:2] == ["whoami", "--as"] and args[2] == "user":
                return 0, {
                    "available": True,
                    "tokenStatus": "ready",
                    "onBehalfOf": {"openId": "ou_current"},
                }, ""
            return 0, {"ok": True, "data": {"message_id": "om_preview"}}, ""

        with patch.object(feishu_cli, "_run_cli", side_effect=fake_cli) as run_cli:
            result = feishu_cli.preview_card(str(FIXTURE), dry_run=True)

        self.assertEqual(result["status"], "preview_only")
        self.assertEqual(result["user_id"], "ou_current")
        self.assertTrue(result["forwardable"])
        message_args = run_cli.call_args_list[-1].args[0]
        self.assertIn("--user-id", message_args)
        self.assertIn("ou_current", message_args)
        self.assertIn("--idempotency-key", message_args)

    def test_cli_status_requires_doctor_bot_and_user(self) -> None:
        def fake_cli(args, **kwargs):
            if args == ["doctor"]:
                return 0, {"ok": True, "checks": {"config": "ok"}}, ""
            if args[:2] == ["whoami", "--as"] and args[2] == "bot":
                return 0, {"available": True, "tokenStatus": "ready"}, ""
            if args[:2] == ["whoami", "--as"] and args[2] == "user":
                return 0, {
                    "available": True,
                    "tokenStatus": "ready",
                    "onBehalfOf": {"openId": "ou_current"},
                }, ""
            raise AssertionError(args)

        with patch.object(feishu_cli, "_run_cli", side_effect=fake_cli) as run_cli:
            result = feishu_cli.cli_status()

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["on_behalf_of"]["openId"], "ou_current")
        self.assertEqual(run_cli.call_args_list[0].args[0], ["doctor"])

    def test_record_cardkit_import_writes_only_verified_import(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            temp_path = Path(temp_dir)
            manifest_path = temp_path / "demo.cardkit-import.json"
            manifest_path.write_text(
                json.dumps({
                    "card": str(temp_path / "demo.card"),
                    "card_name": "AI先锋大赛",
                    "page_url": "https://open.larkoffice.com/cardkit",
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            invalid = feishu_cli.record_cardkit_import(
                str(manifest_path),
                status="imported",
                observed_name="AI先锋大赛（副本）",
                editor_opened=True,
            )
            self.assertEqual(invalid["status"], "invalid_evidence")
            self.assertFalse((temp_path / "demo.cardkit-import-result.json").exists())

            pending = feishu_cli.record_cardkit_import(
                str(manifest_path),
                status="pending",
                observed_name="AI先锋大赛",
                editor_opened=False,
            )
            self.assertEqual(pending["status"], "pending")

            imported = feishu_cli.record_cardkit_import(
                str(manifest_path),
                status="imported",
                observed_name="AI先锋大赛",
                editor_opened=True,
                page_url="https://open.larkoffice.com/cardkit",
            )
            self.assertEqual(imported["status"], "imported")
            evidence = json.loads((temp_path / "demo.cardkit-import-result.json").read_text(encoding="utf-8"))
            self.assertTrue(evidence["evidence"]["my_cards_name_visible"])
            self.assertTrue(evidence["evidence"]["editor_page_openable"])


if __name__ == "__main__":
    unittest.main()
