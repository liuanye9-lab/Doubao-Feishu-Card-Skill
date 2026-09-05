"""Read-only media validation shared by registration, compile and upload."""
from pathlib import Path
from typing import Any, Dict, Optional


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
            alpha_extrema = img.convert("RGBA").getchannel("A").getextrema()
            # Decode all frames so truncated late frames do not pass on magic alone.
            for frame in range(frames):
                img.seek(frame)
                img.load()
                duration += int(img.info.get("duration", 0) or 0)
        if expected_format == "GIF" and (frames < 2 or duration <= 0):
            raise ValueError("animated GIF requires at least two frames with positive duration")
    except (UnidentifiedImageError, OSError, EOFError, SyntaxError) as exc:
        raise ValueError(f"invalid or truncated media: {path.name}: {exc}") from exc
    return {"format": fmt, "width": width, "height": height, "bytes": size,
            "alpha_extrema": list(alpha_extrema), "has_transparency": alpha_extrema[0] < 255,
            "frame_count": frames, "animated": frames > 1, "duration_ms": duration, "loop": loop}


def asset_error(path: Path, expected_format: Optional[str] = None) -> Optional[str]:
    try:
        inspect_asset(path, expected_format)
    except (OSError, ValueError, ImportError) as exc:
        return str(exc)
    return None
