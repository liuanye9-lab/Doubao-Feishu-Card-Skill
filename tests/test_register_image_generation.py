import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from register_image_generation import register  # noqa: E402


class RegisterImageGenerationTests(unittest.TestCase):
    def test_register_keeps_configured_seedream_profile_separate_from_observed_id(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            bundle = Path(temp_dir)
            image_path = bundle / "hero.png"
            prompt_path = bundle / "demo.image-prompt.md"
            manifest_path = bundle / "hero-generation.json"
            image_path.write_bytes(b"banner-seedream")
            prompt_path.write_text("banner prompt\n", encoding="utf-8")
            manifest = register(
                str(image_path),
                prompt=str(prompt_path),
                output=str(manifest_path),
                generation_mode="seedream_5_pro_banner_plus_native_card",
                text_policy="seedream_5_pro_banner_selected_text_and_layout",
            )

        self.assertEqual(manifest["model_id"], "platform-managed")
        self.assertEqual(manifest["generation_model"], "seedream-5.0-pro")
        self.assertEqual(manifest["generation_model_label"], "Seedream 5.0 Pro")
        self.assertEqual(manifest["generation_model_source"], "configured_profile_pending_runtime_observation")
        self.assertEqual(manifest["model_id_source"], "platform_managed_fallback")

    def test_register_rejects_mismatched_banner_text_policy(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as temp_dir:
            bundle = Path(temp_dir)
            image_path = bundle / "hero.png"
            prompt_path = bundle / "demo.image-prompt.md"
            image_path.write_bytes(b"banner-seedream")
            prompt_path.write_text("banner prompt\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                register(
                    str(image_path),
                    prompt=str(prompt_path),
                    generation_mode="seedream_5_pro_banner_plus_native_card",
                    text_policy="seedream_5_pro_direct_selected_text_and_layout",
                )


if __name__ == "__main__":
    unittest.main()
