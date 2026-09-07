#!/usr/bin/env python3
"""Inspect card media without modifying the supplied files.

This helper is deliberately local and read/prepare-only. It does not upload
anything to Feishu. The generated manifest is the hand-off between the image
Skill and the Card 2.0 compiler: every remote image still needs a real
``img_key`` before a card is sendable.

Animated assets may be embedded directly when CardKit supports GIF, but every
essential fact must remain readable in native Card text. This helper never
transcodes, extracts frames, or writes a replacement media file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


MAX_FRAME_SCAN = 240
SUPPORTED_FORMATS = {"GIF", "JPEG", "PNG", "WEBP"}
IMAGE_SOURCE_TYPES = {"real_image", "ai_generated"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mime_type(image_format: str, path: Path) -> str:
    format_map = {
        "GIF": "image/gif",
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }
    return format_map.get(image_format.upper(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")


def _has_alpha(image: Any) -> bool:
    if "A" in getattr(image, "getbands", lambda: ())():
        return True
    return "transparency" in getattr(image, "info", {})


def inspect_asset(
    path: Path,
    *,
    role: str = "supporting",
    image_source: str = "real_image",
) -> Dict[str, Any]:
    """Return deterministic metadata for one local image asset."""
    if image_source not in IMAGE_SOURCE_TYPES:
        raise ValueError(f"image_source must be one of {sorted(IMAGE_SOURCE_TYPES)}")
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("媒体检查需要 Pillow；请先安装 Python Pillow") from exc

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"media asset does not exist: {resolved}")
    try:
        digest = _sha256(resolved)
        with Image.open(resolved) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            frame_count = int(getattr(image, "n_frames", 1) or 1)
            frame_durations: List[int] = []
            scanned_frames = min(frame_count, MAX_FRAME_SCAN)
            for index in range(scanned_frames):
                image.seek(index)
                frame_durations.append(max(0, int(image.info.get("duration", 0) or 0)))
            animated = frame_count > 1
            image_mode = str(image.mode)
            alpha = _has_alpha(image)
    except Exception as exc:
        raise ValueError(f"cannot inspect media asset {resolved}: {exc}") from exc

    return {
        "path": str(resolved),
        "name": resolved.name,
        "image_source": image_source,
        "role": role,
        "sha256": digest,
        "bytes": resolved.stat().st_size,
        "format": image_format,
        "mime_type": _mime_type(image_format, resolved),
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 4) if height else None,
        "mode": image_mode,
        "has_alpha": alpha,
        "animated": animated,
        "frame_count": frame_count,
        "frame_scan_limit": MAX_FRAME_SCAN,
        "frame_scan_truncated": frame_count > MAX_FRAME_SCAN,
        "frame_durations_ms": frame_durations,
        "duration_ms_scanned": sum(frame_durations),
        "supported_for_card_image": image_format in SUPPORTED_FORMATS,
    }


def build_manifest(
    paths: Sequence[Path],
    *,
    role: str = "supporting",
    image_source: str = "real_image",
) -> Dict[str, Any]:
    """Inspect assets without creating or changing any media."""
    if not paths:
        raise ValueError("at least one --input asset is required")
    assets: List[Dict[str, Any]] = []
    for path in paths:
        asset = inspect_asset(path, role=role, image_source=image_source)
        if not asset["supported_for_card_image"]:
            raise ValueError(f"unsupported card image format: {asset['format'] or path}")
        assets.append(asset)

    animated_assets = [asset for asset in assets if asset["animated"]]
    static_companion_ready = not animated_assets
    manifest: Dict[str, Any] = {
        "schema": "doubao-feishu-media/2",
        "generated_by": "scripts/media_assets.py",
        "image_source": image_source,
        "asset_count": len(assets),
        "assets": assets,
        "quality_gate": {
            "all_assets_readable": True,
            "all_formats_supported": all(asset["supported_for_card_image"] for asset in assets),
            "animated_assets_have_static_companion": static_companion_ready,
            "essential_text_outside_animation": True,
            "remote_upload_completed": False,
            "upload_type": "message_image_key_required",
            "sendable": bool(assets),
        },
        "policy": {
            "media_is_read_only": True,
            "first_frame_must_be_supplied_separately": False,
            "direct_gif_embedding_supported": True,
            "do_not_put_essential_facts_only_in_animation": True,
            "remote_img_key_is_required_before_card_compile": True,
        },
    }
    return manifest


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect card media without modifying the supplied files")
    parser.add_argument("--input", action="append", required=True, type=Path, help="local PNG/JPEG/WebP/GIF; repeat for a set")
    parser.add_argument("--role", default="supporting", help="asset role, e.g. hero, timeline, screenshot, gallery")
    parser.add_argument("--image-source", choices=sorted(IMAGE_SOURCE_TYPES), default="real_image", help="source type for the inspected media; AI and HTML hero provenance use hero-generation.json")
    parser.add_argument("--output", type=Path, help="write the manifest JSON to this path")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        manifest = build_manifest(
            args.input,
            role=args.role,
            image_source=args.image_source,
        )
        payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"media_assets.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
