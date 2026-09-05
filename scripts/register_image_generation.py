#!/usr/bin/env python3
"""Register the provenance of a 豆包工作 Seedream 5.0 Pro-generated card bitmap.

The default pipeline treats ``hero.png`` as the selected final Seedream 5.0 Pro image,
including its selected information text and layout. The manifest records the
observable tool, the configured Seedream 5.0 Pro profile, and does not claim a
provider/model ID that the host did not expose.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from runtime_profile import image_mode_config, image_runtime, supported_image_modes


from asset_validation import inspect_asset

ROOT = Path(__file__).resolve().parents[1]


def _inside_root(value: str) -> Path:
    path = Path(value).expanduser()
    path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"path must stay inside the Skill directory: {path}") from exc
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register(
    image: str,
    *,
    prompt: Optional[str] = None,
    output: Optional[str] = None,
    tool: str = "doubao.image_gen",
    generation_family: str = "seedream-class",
    model_id: str = "platform-managed",
    text_policy: str = "seedream_5_pro_direct_selected_text_and_layout",
    generation_mode: Optional[str] = None,
) -> Dict[str, Any]:
    runtime = image_runtime()
    resolved_mode = generation_mode
    if not resolved_mode:
        for candidate in supported_image_modes():
            if image_mode_config(candidate).get("text_policy") == text_policy:
                resolved_mode = candidate
                break
    if not resolved_mode or resolved_mode not in supported_image_modes():
        raise ValueError(
            f"generation_mode must be one of {', '.join(supported_image_modes())}"
        )
    expected_policy = str(image_mode_config(resolved_mode).get("text_policy") or "")
    if text_policy != expected_policy:
        raise ValueError(
            f"text_policy must be {expected_policy} for generation_mode={resolved_mode}"
        )
    configured_model = str(runtime.get("generation_model") or "seedream-5.0-pro")
    configured_model_label = str(runtime.get("generation_model_label") or "Seedream 5.0 Pro")
    image_path = _inside_root(image)
    if not image_path.is_file():
        raise ValueError(f"image file not found: {image_path}")
    if image_path.name != "hero.png":
        raise ValueError("the selected Seedream 5.0 Pro asset must be named hero.png")
    inspection = inspect_asset(image_path, "PNG")
    prompt_path = _inside_root(prompt) if prompt else image_path.with_name(f"{image_path.parent.name}.image-prompt.md")
    if not prompt_path.is_file():
        raise ValueError(f"prompt file not found: {prompt_path}")
    output_path = _inside_root(output) if output else image_path.with_name("hero-generation.json")
    manifest: Dict[str, Any] = {
        "schema": "doubao-feishu-image-provenance/1",
        "tool": tool,
        "generation_family": generation_family,
        "model_id": model_id,
        "generation_model": configured_model,
        "generation_model_label": configured_model_label,
        "generation_model_source": "configured_profile_pending_runtime_observation",
        "generation_mode": resolved_mode,
        "model_id_source": (
            "explicit_registration_argument"
            if model_id != "platform-managed"
            else "platform_managed_fallback"
        ),
        "asset": str(image_path),
        "asset_name": image_path.name,
        "image_sha256": _sha256(image_path),
        "inspection": inspection,
        "prompt_file": str(prompt_path),
        "prompt_sha256": _sha256(prompt_path),
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "text_policy": text_policy,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register 豆包工作 Seedream 5.0 Pro provenance for hero.png")
    parser.add_argument("--image", required=True, help="Seedream 5.0 Pro-generated final image or banner, normally hero.png")
    parser.add_argument("--prompt", help="image prompt markdown; defaults to sibling *.image-prompt.md")
    parser.add_argument("--output", help="manifest path; defaults to sibling hero-generation.json")
    parser.add_argument("--tool", default="doubao.image_gen")
    parser.add_argument("--generation-family", default="seedream-class")
    parser.add_argument("--model-id", default="platform-managed")
    parser.add_argument("--text-policy", default="seedream_5_pro_direct_selected_text_and_layout")
    parser.add_argument("--generation-mode", choices=supported_image_modes())
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        manifest = register(
            args.image,
            prompt=args.prompt,
            output=args.output,
            tool=args.tool,
            generation_family=args.generation_family,
            model_id=args.model_id,
            text_policy=args.text_policy,
            generation_mode=args.generation_mode,
        )
        print(json.dumps({"ok": True, **manifest}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
