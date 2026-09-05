#!/usr/bin/env python3
"""Package only maintained Skill assets, never user inputs or runtime output."""
from __future__ import annotations
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
TOP_LEVEL = "doubao-feishu-card"
ROOT_FILES = {".gitignore", "README.md", "SKILL.md", "requirements.txt"}
ASSET_DIRS = {"agents", "scripts", "references", "presets", "scenes", "examples", "tests"}
EXCLUDED = {".git", "__pycache__", ".pytest_cache", ".DS_Store", "node_modules"}

def should_include(path):
    relative = path.relative_to(ROOT)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != ROOT):
        return False
    if any(part in EXCLUDED for part in relative.parts):
        return False
    if relative.as_posix() == "outputs/.gitkeep":
        return path.is_file()
    if len(relative.parts) == 1:
        return relative.name in ROOT_FILES and path.is_file()
    if relative.parts[0] not in ASSET_DIRS or any(part.startswith(".") for part in relative.parts):
        return False
    return path.is_file() and path.suffix in {".py", ".ts", ".md", ".json", ".yaml", ".yml", ".card", ".txt"}

def package(output):
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in ROOT.rglob("*") if path.resolve() != output and should_include(path))
    present = {p.relative_to(ROOT).as_posix() for p in files}
    required = {"SKILL.md", "requirements.txt", "presets/runtime-profile.json"}
    if not required.issubset(present):
        raise ValueError("Missing required package files: " + str(sorted(required - present)))
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, f"{TOP_LEVEL}/{path.relative_to(ROOT).as_posix()}")
        if "outputs/.gitkeep" not in present:
            archive.writestr(f"{TOP_LEVEL}/outputs/.gitkeep", "")
    return output

def main(argv=None):
    parser = argparse.ArgumentParser(description="Package a portable Feishu Card Skill")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / (TOP_LEVEL + ".zip"))
    try:
        print(package(parser.parse_args(argv).output))
        return 0
    except (OSError, ValueError) as exc:
        print(f"package_skill.py: {exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
