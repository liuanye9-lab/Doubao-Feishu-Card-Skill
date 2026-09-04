#!/usr/bin/env python3
"""Create a Doubao Work import ZIP with one top-level Skill directory."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL = "doubao-feishu-card"
EXCLUDED_PARTS = {".git", ".pytest_cache", "__pycache__", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if relative.parts and relative.parts[0] in {"dist", "outputs"}:
        return False
    return path.is_file()


def package(output: Path) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in ROOT.rglob("*") if should_include(path))
    required = {"SKILL.md", "agents/openai.yaml", "presets/runtime-profile.json"}
    present = {path.relative_to(ROOT).as_posix() for path in files}
    missing = sorted(required - present)
    if missing:
        raise ValueError(f"missing required Skill files: {', '.join(missing)}")
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            archive.write(path, f"{TOP_LEVEL}/{relative}")
    return output


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package doubao-feishu-card for Doubao Work import")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "doubao-feishu-card.zip")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        output = package(parse_args(argv).output)
        print(output)
        return 0
    except (OSError, ValueError) as exc:
        print(f"package_skill.py: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
