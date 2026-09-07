"""Read-only media validation shared by registration, compile and upload.

The image contract is deliberately strict about geometry. A card renderer can
resize a bitmap, but it must never silently turn a 2:3 asset into a 3:1 asset
or squeeze the glyphs inside an information image. Pixel inspection remains
read-only; this module never draws, crops, removes backgrounds, or rewrites an
asset.
"""
from math import isfinite
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


BACKGROUND_POLICIES = {
    "preserve_source_background",
    "allow_transparent_background",
}


def _parse_aspect_ratio(value: Any) -> Optional[Tuple[float, float, str]]:
    """Return width, height and a stable label for a ratio such as 2:3."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not isfinite(number) or number <= 0:
            raise ValueError("aspect ratio must be a positive finite number")
        return number, 1.0, str(value)
    text = str(value).strip()
    if ":" in text:
        left, right = (part.strip() for part in text.split(":", 1))
        try:
            width, height = float(left), float(right)
        except ValueError as exc:
            raise ValueError(f"invalid aspect ratio: {value}") from exc
        if not all(isfinite(item) and item > 0 for item in (width, height)):
            raise ValueError(f"invalid aspect ratio: {value}")
        return width, height, f"{left}:{right}"
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"invalid aspect ratio: {value}") from exc
    if not isfinite(number) or number <= 0:
        raise ValueError(f"invalid aspect ratio: {value}")
    return number, 1.0, text


def inspect_asset(path: Path, expected_format: Optional[str] = None) -> Dict[str, Any]:
    from PIL import Image, UnidentifiedImageError
    path = Path(path)
    size = path.stat().st_size
    if not 0 < size <= 10 * 1024 * 1024:
        raise ValueError("media must be non-empty and at most 10 MiB")
    try:
        with Image.open(path) as img:
            fmt = str(img.format or "").upper()
            if expected_format and fmt != expected_format.upper():
                raise ValueError(f"expected real {expected_format}, found {fmt}")
            if fmt not in {"PNG", "JPEG", "WEBP", "GIF", "TIFF", "BMP", "ICO"}:
                raise ValueError(f"unsupported image format: {fmt}")
            width, height = img.size
            edge = 2000 if fmt == "GIF" else 12000
            if min(width, height) < 1 or max(width, height) > edge:
                raise ValueError(f"{fmt} dimensions must be at most {edge}x{edge}")
            img.verify()
        duration = 0
        with Image.open(path) as img:
            frames = int(getattr(img, "n_frames", 1))
            loop = img.info.get("loop")
            mode = str(getattr(img, "mode", ""))
            rgba = img.convert("RGBA")
            alpha_channel = rgba.getchannel("A")
            alpha_extrema = alpha_channel.getextrema()
            alpha_histogram = alpha_channel.histogram()
            pixel_count = max(width * height, 1)
            transparent_pixels = sum(alpha_histogram[:255])
            partial_alpha_pixels = sum(alpha_histogram[1:255])
            # Decode all frames so truncated late frames do not pass on magic alone.
            for frame in range(frames):
                img.seek(frame)
                img.load()
                duration += int(img.info.get("duration", 0) or 0)
        if expected_format == "GIF" and (frames < 2 or duration <= 0):
            raise ValueError("animated GIF requires at least two frames with positive duration")
    except (UnidentifiedImageError, OSError, EOFError, SyntaxError) as exc:
        raise ValueError(f"invalid or truncated media: {path.name}: {exc}") from exc
    return {
        "format": fmt,
        "mode": mode,
        "width": width,
        "height": height,
        "aspect_ratio": round(width / height, 6),
        "bytes": size,
        "alpha_extrema": list(alpha_extrema),
        "has_transparency": alpha_extrema[0] < 255,
        "transparent_pixel_ratio": round(transparent_pixels / pixel_count, 6),
        "partial_alpha_pixel_ratio": round(partial_alpha_pixels / pixel_count, 6),
        "frame_count": frames,
        "animated": frames > 1,
        "duration_ms": duration,
        "loop": loop,
    }


def validate_image_contract(
    path: Path,
    *,
    expected_aspect_ratio: Any = None,
    aspect_ratio_tolerance: float = 0.025,
    allow_crop: bool = False,
    background_policy: str = "preserve_source_background",
    source_kind: str = "ai_generated",
    expected_format: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate geometry and background policy without modifying the image.

    preserve_source_background is the default. For an AI-generated hero this
    means an opaque, complete composition; for a user-supplied real_image it
    means preserve the supplied pixels, including any existing alpha. Explicit
    transparent output remains an opt-in policy and is never inferred from
    mobile layout.
    """
    if background_policy not in BACKGROUND_POLICIES:
        raise ValueError(
            "background_policy must be one of "
            + ", ".join(sorted(BACKGROUND_POLICIES))
        )
    if aspect_ratio_tolerance < 0 or not isfinite(float(aspect_ratio_tolerance)):
        raise ValueError("aspect_ratio_tolerance must be a non-negative finite number")

    inspection = inspect_asset(path, expected_format)
    expected = _parse_aspect_ratio(expected_aspect_ratio)
    actual_ratio = float(inspection["aspect_ratio"])
    expected_ratio = expected[0] / expected[1] if expected else None
    ratio_delta = (
        abs(actual_ratio / expected_ratio - 1.0)
        if expected_ratio
        else None
    )
    errors = []
    warnings = []
    if expected_ratio and ratio_delta is not None and ratio_delta > float(aspect_ratio_tolerance):
        message = (
            f"asset aspect ratio {actual_ratio:.6f} does not match the "
            f"contract {expected[2]} within {float(aspect_ratio_tolerance):.3f}"
        )
        if allow_crop:
            warnings.append(message + "; crop is explicitly allowed, so geometry is not treated as distortion")
        else:
            errors.append(message + "; regenerate or choose a matching canvas, never stretch the asset")

    source_kind = str(source_kind or "ai_generated").strip() or "ai_generated"
    if (
        source_kind == "ai_generated"
        and background_policy == "preserve_source_background"
        and inspection["has_transparency"]
    ):
        errors.append(
            "AI-generated hero must preserve a complete opaque background by default; "
            "do not remove the background or introduce transparency without explicit opt-in"
        )

    return {
        "schema": "doubao-feishu-image-contract/1",
        "ok": not errors,
        "source_kind": source_kind,
        "background_policy": background_policy,
        "background_removal": (
            "disabled"
            if background_policy == "preserve_source_background"
            else "explicit_opt_in_required"
        ),
        "expected_aspect_ratio": expected[2] if expected else None,
        "actual_aspect_ratio": inspection["aspect_ratio"],
        "aspect_ratio_tolerance": float(aspect_ratio_tolerance),
        "aspect_ratio_delta": round(ratio_delta, 6) if ratio_delta is not None else None,
        "allow_crop": bool(allow_crop),
        "text_integrity_policy": "preserve_glyph_aspect_ratio_no_non_uniform_scaling",
        "text_integrity_review_required": True,
        "inspection": inspection,
        "errors": errors,
        "warnings": warnings,
    }


def asset_error(path: Path, expected_format: Optional[str] = None) -> Optional[str]:
    try:
        inspect_asset(path, expected_format)
    except (OSError, ValueError, ImportError) as exc:
        return str(exc)
    return None
