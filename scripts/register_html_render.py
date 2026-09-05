#!/usr/bin/env python3
"""Register browser-rendered HTML infographic provenance for hero.png."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from asset_validation import inspect_asset
from html_infographic import HTML_PROVENANCE_SCHEMA, HTML_RENDER_STRATEGY, HTML_TEXT_POLICY, html_source_is_safe


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register(
    image: str,
    html_source: str,
    *,
    prompt: Optional[str] = None,
    output: Optional[str] = None,
    renderer: str = "headless Chrome-family browser",
    width: int = 1200,
    height: int = 1800,
    scale: float = 2.0,
) -> Dict[str, Any]:
    image_path = Path(image).expanduser().resolve()
    html_path = Path(html_source).expanduser().resolve()
    if image_path.name != "hero.png":
        raise ValueError("HTML 信息图导出的最终图片必须命名为 hero.png")
    if not image_path.is_file():
        raise ValueError(f"image file not found: {image_path}")
    if not html_path.is_file() or html_path.suffix.lower() != ".html":
        raise ValueError(f"HTML source not found or not .html: {html_path}")
    if not html_source_is_safe(html_path):
        raise ValueError("HTML must be self-contained, static, and marked for html_infographic_to_png")
    inspection = inspect_asset(image_path, "PNG")
    prompt_path = Path(prompt).expanduser().resolve() if prompt else html_path.with_name(f"{html_path.stem}.html-prompt.md")
    if not prompt_path.is_file():
        raise ValueError(f"HTML design prompt not found: {prompt_path}")
    output_path = Path(output).expanduser().resolve() if output else image_path.with_name("hero-generation.json")
    manifest: Dict[str, Any] = {
        "schema": HTML_PROVENANCE_SCHEMA,
        "tool": "html_to_png",
        "generation_family": "html-render",
        "render_strategy": HTML_RENDER_STRATEGY,
        "generation_model": None,
        "generation_model_label": None,
        "generation_mode": HTML_RENDER_STRATEGY,
        "text_policy": HTML_TEXT_POLICY,
        "asset": str(image_path),
        "asset_name": "hero.png",
        "image_sha256": sha256(image_path),
        "inspection": inspection,
        "html_file": str(html_path),
        "html_sha256": sha256(html_path),
        "prompt_file": str(prompt_path),
        "prompt_sha256": sha256(prompt_path),
        "renderer": renderer,
        "viewport": {"width": width, "height": height, "scale": scale},
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "source_locked": True,
        "post_processing": "none",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name("." + output_path.name + ".tmp")
    temp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(output_path)
    return manifest


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register HTML → PNG provenance for hero.png")
    parser.add_argument("--image", required=True)
    parser.add_argument("--html", required=True, dest="html_source")
    parser.add_argument("--prompt")
    parser.add_argument("--output")
    parser.add_argument("--renderer", default="headless Chrome-family browser")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=1800)
    parser.add_argument("--scale", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        print(json.dumps(register(args.image, args.html_source, prompt=args.prompt, output=args.output, renderer=args.renderer, width=args.width, height=args.height, scale=args.scale), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
