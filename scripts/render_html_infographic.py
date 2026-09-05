#!/usr/bin/env python3
"""Render a self-contained HTML infographic to a PNG with a local browser.

This is a deterministic export step, not a CardKit renderer and not a way to
put HTML/JS into a card.  The browser is intentionally discovered locally so
the generated image can be reproduced without a remote service.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence
from urllib.parse import quote

from asset_validation import asset_error


def find_browser() -> str:
    candidates = [
        os.environ.get("HTML_SHOT_BROWSER"),
        os.environ.get("CHROME_BIN"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("microsoft-edge"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("未找到 Chrome/Chromium/Edge；可设置 HTML_SHOT_BROWSER 指向浏览器可执行文件")


def render(
    html_path: str,
    output: str,
    *,
    width: int = 1200,
    height: int = 1800,
    scale: float = 2.0,
    browser: Optional[str] = None,
) -> dict:
    html_file = Path(html_path).expanduser().resolve()
    output_file = Path(output).expanduser().resolve()
    if html_file.suffix.lower() != ".html":
        raise ValueError("HTML 信息图源文件必须使用 .html 扩展名")
    if not html_file.is_file():
        raise ValueError(f"HTML source not found: {html_file}")
    if width < 320 or height < 320 or width > 4000 or height > 8000:
        raise ValueError("viewport must be 320–4000px wide and 320–8000px high")
    if scale <= 0 or scale > 4:
        raise ValueError("scale must be between 0 and 4")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    browser_path = browser or find_browser()
    url = "file://" + quote(str(html_file))
    command = [
        browser_path,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--allow-file-access-from-files",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1200",
        f"--force-device-scale-factor={scale:g}",
        f"--window-size={width},{height}",
        f"--screenshot={output_file}",
        url,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    if completed.returncode != 0 or not output_file.is_file():
        detail = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
        raise RuntimeError(f"HTML → PNG 渲染失败: {detail[-2000:]}")
    error = asset_error(output_file, "PNG")
    if error:
        raise ValueError(f"rendered PNG validation failed: {error}")
    return {
        "html": str(html_file),
        "output": str(output_file),
        "renderer": browser_path,
        "viewport": {"width": width, "height": height, "scale": scale},
        "command": command,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a self-contained Feishu HTML infographic to hero.png")
    parser.add_argument("--html", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=1800)
    parser.add_argument("--scale", type=float, default=2.0)
    parser.add_argument("--browser")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        print(render(args.html, args.output, width=args.width, height=args.height, scale=args.scale, browser=args.browser))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"render_html_infographic.py: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
