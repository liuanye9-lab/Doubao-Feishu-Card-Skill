#!/usr/bin/env python3
"""Single stable entry point for the unified Feishu Card Skill.

This facade intentionally exposes the small set of inputs that affect a
card's result and always runs the stable-v1 pipeline.  It does not perform
remote writes; direct CardKit import (and optional Bot preview) remains an
explicit delivery phase after the local gates pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from card_studio_contract import STABILITY_PROFILE
from doubao_pipeline import _console_summary, _load_design_plan, run_pipeline


ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stable-v1 natural-language-to-Feishu-Card workflow"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="card copy")
    source.add_argument("--text-file", help="UTF-8 card copy file")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--name", default="card")
    parser.add_argument("--brand-context", default="")
    parser.add_argument("--brand-context-file")
    parser.add_argument("--scene", help="optional explicit scene, e.g. case-showcase")
    parser.add_argument("--preset", help="optional explicit registered visual preset")
    parser.add_argument("--design-plan", help="JSON file containing design_plan overrides")
    parser.add_argument("--hero-img-key", help="real img_key returned by Feishu image upload")
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="use the explicit sendable native-Card fallback",
    )
    parser.add_argument(
        "--motion",
        choices=("auto", "on", "off"),
        default="auto",
        help="auto routes motion-worthy copy to Seedance 2.5 GIF; on/off explicitly override",
    )
    parser.add_argument(
        "--emoji-mode",
        choices=("auto", "aliases", "semantic", "off"),
        default="semantic",
    )
    parser.add_argument("--link-mode", choices=("button", "inline"), default="button")
    parser.add_argument("--purpose", help="layout/content context only")
    parser.add_argument("--recipient", help="delivery context only; not a remote target")
    parser.add_argument(
        "--material-kind",
        choices=("plain_text", "document_extract", "table_extract", "reference_image", "card_json"),
        default="plain_text",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="only write and print the three local layout proposals",
    )
    parser.add_argument(
        "--layout",
        choices=("banner-led", "infographic-led", "text-led"),
        help="select one local layout proposal without an interactive step",
    )
    return parser.parse_args(argv)


def _output_dir(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        text = args.text if args.text is not None else Path(args.text_file).read_text(encoding="utf-8")
        brand_context = args.brand_context
        if args.brand_context_file:
            brand_context = Path(args.brand_context_file).read_text(encoding="utf-8")
        if args.propose or args.layout:
            # The stable facade delegates proposal/selection handling to the
            # same pipeline parser so the public entry point remains singular.
            from doubao_pipeline import main as pipeline_main

            delegated = [
                "--text" if args.text is not None else "--text-file",
                args.text if args.text is not None else args.text_file,
                "--output-dir",
                args.output_dir,
                "--name",
                args.name,
            ]
            if args.brand_context:
                delegated.extend(["--brand-context", args.brand_context])
            if args.brand_context_file:
                delegated.extend(["--brand-context-file", args.brand_context_file])
            if args.scene:
                delegated.extend(["--scene", args.scene])
            if args.preset:
                delegated.extend(["--preset", args.preset])
            if args.design_plan:
                delegated.extend(["--design-plan", args.design_plan])
            if args.hero_img_key:
                delegated.extend(["--hero-img-key", args.hero_img_key])
            if args.no_image:
                delegated.append("--no-image")
            if args.motion != "auto":
                delegated.extend(["--motion", args.motion])
            if args.emoji_mode != "semantic":
                delegated.extend(["--emoji-mode", args.emoji_mode])
            if args.link_mode != "button":
                delegated.extend(["--link-mode", args.link_mode])
            if args.purpose:
                delegated.extend(["--purpose", args.purpose])
            if args.recipient:
                delegated.extend(["--recipient", args.recipient])
            if args.material_kind != "plain_text":
                delegated.extend(["--material-kind", args.material_kind])
            if args.propose:
                delegated.append("--propose")
            if args.layout:
                delegated.extend(["--layout", args.layout])
            return pipeline_main(delegated)
        report = run_pipeline(
            text,
            _output_dir(args.output_dir),
            name=args.name,
            brand_context=brand_context,
            hero_img_key=args.hero_img_key,
            requested_scene=args.scene,
            requested_preset=args.preset,
            design_plan=_load_design_plan(args.design_plan),
            no_image=args.no_image,
            force_motion=None if args.motion == "auto" else args.motion == "on",
            emoji_mode=args.emoji_mode,
            link_mode=args.link_mode,
            purpose=args.purpose,
            recipient=args.recipient,
            material_kind=args.material_kind,
            workflow_profile=STABILITY_PROFILE,
        )
        summary = _console_summary(report)
        summary["workflow_profile"] = STABILITY_PROFILE
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if report["status"] != "blocked" else 2
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"stable_card.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
