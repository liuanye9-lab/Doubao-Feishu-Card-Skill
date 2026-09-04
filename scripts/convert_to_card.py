#!/usr/bin/env python3
"""Convert raw Card 2.0 JSON or an existing wrapper into CardKit files.

This is the standalone converter absorbed from the CardKit importer Skill.
It deliberately emits sidecars instead of overwriting a raw API card.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

# Make both ``python scripts/convert_to_card.py`` and
# ``from scripts.convert_to_card import ...`` work from the repository root.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cardkit_format import CARDKIT_MAX_BYTES, extract_dsl, normalize_dsl, safe_card_name, wrap_card
from validate_card import validate


def convert_one(path: Path, outdir: Path, forced_name: Optional[str] = None) -> dict:
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    dsl, wrapped_name, variables = extract_dsl(source)
    normalized, fixes = normalize_dsl(dsl)
    header_title = normalized.get("header", {}).get("title", {}) if isinstance(normalized.get("header"), dict) else {}
    derived = header_title.get("content") if isinstance(header_title, dict) else None
    name = str(forced_name or wrapped_name or derived or path.stem).strip() or "card"
    base = safe_card_name(name)
    wrapper = wrap_card(normalized, name, variables)
    outdir.mkdir(parents=True, exist_ok=True)
    card_path = outdir / f"{base}.card"
    json_path = outdir / f"{base}_card.json"
    payload = json.dumps(wrapper, ensure_ascii=False, indent=2) + "\n"
    for target in (card_path, json_path):
        target.write_text(payload, encoding="utf-8")
    validation = validate(normalized, surface="raw")
    return {
        "input": str(path),
        "name": name,
        "card_path": str(card_path),
        "json_path": str(json_path),
        "fixes": fixes,
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
        "elements": validation.get("stats", {}).get("elements", 0),
        "file_size_bytes": card_path.stat().st_size,
        "size_ok": card_path.stat().st_size <= CARDKIT_MAX_BYTES,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert raw Feishu Card 2.0 JSON to a CardKit import wrapper")
    parser.add_argument("inputs", nargs="+", help="raw .card/.json or an existing CardKit wrapper")
    parser.add_argument("--outdir", default=".")
    parser.add_argument("--name")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    ok = True
    for input_value in args.inputs:
        path = Path(input_value).expanduser().resolve()
        print(f"\n=== {path} ===")
        try:
            result = convert_one(path, Path(args.outdir).expanduser().resolve(), args.name if len(args.inputs) == 1 else None)
        except (OSError, ValueError) as exc:
            ok = False
            print(f"[FAIL] {exc}")
            continue
        for fix in result["fixes"]:
            print(f"[FIX] {fix}")
        for warning in result["warnings"]:
            print(f"[WARN] {warning}")
        if result["errors"]:
            ok = False
            for error in result["errors"]:
                print(f"[ERROR] {error}")
        if not result["size_ok"]:
            ok = False
            print(f"[ERROR] CardKit file exceeds {CARDKIT_MAX_BYTES} bytes")
        if not result["errors"] and result["size_ok"]:
            print(f"[OK] validation passed; elements={result['elements']}")
        print(f"CardKit .card: {result['card_path']}")
        print(f"JSON transfer: {result['json_path']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
