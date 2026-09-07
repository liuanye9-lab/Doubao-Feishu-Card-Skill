"""Finalize the saved editable spec without rerouting or losing user edits."""
import argparse
import hashlib
import importlib
import json
import shlex
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def attach_delivery_evidence(report):
    """Bind readiness to actual files and an explicit human/model visual review."""
    edition = "doubao" if "doubao" in report else "codex"
    provider = report[edition]
    card = Path(report["card"])
    contract = provider.get("card_image_contract", {})
    required = bool(provider.get("image_required"))
    asset = Path(contract.get("final_asset") or card.with_name("hero.png"))
    render_strategy = str(provider.get("render_strategy") or contract.get("render_strategy") or "").strip()
    if render_strategy in {"html_infographic_to_png", "html_to_png", "html"}:
        render_strategy = "native_model"
    record = card.with_name(card.stem + ".visual-review.json")
    fingerprints = {"card_sha256": digest(card),
                    "asset_sha256": digest(asset) if required and asset.is_file() else None}
    try:
        review = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        review = {}
    reviewed = not required or (isinstance(review, dict) and review.get("decision") == "pass"
                                and bool(review.get("notes"))
                                and all(review.get(k) == v for k, v in fingerprints.items()))
    report["artifact_fingerprints"] = fingerprints
    report["visual_review"] = {"required": required, "passed": reviewed, "record": str(record),
                               "scope": "manual inspection of final media and native card layout"}
    report["readiness"]["visual_review_ready"] = reviewed
    if not reviewed:
        if report["status"] == "ready":
            report["status"] = "needs_visual_review"
        for field in ("sendable", "cardkit_entity_ready", "cardkit_editor_ready"):
            report["readiness"][field] = False
        blockers = report["readiness"].setdefault("blockers", [])
        if "final visual review is pending or stale" not in blockers:
            blockers.append("final visual review is pending or stale")
    motion = bool(provider.get("seedance_required"))
    prompt = report.get("motion_prompt") if motion else report.get("image_prompt")
    ready = report["readiness"].get("image_ready")
    report["media_task"] = {
        "required": required, "kind": "gif" if motion else "image",
        "render_strategy": render_strategy or ("native_model" if required else "none"),
        "tool_hint": provider.get("generation_tool"),
        "model_label": provider.get("generation_model_label"), "prompt_file": prompt,
        "output_file": str(asset) if required else None,
        "next_action": ("complete" if report["status"] == "ready" else
                        "inspect_media_and_card_then_record_review" if ready and not reviewed else
                        "invoke_host_generation_tool_then_register_and_upload" if required else
                        "fix_report_blockers"),
        "art_direction": {"file": str(Path(__file__).resolve().parents[1] / "presets/image-art-direction.json"),
                          "style": "five-production-templates", "font": "refined modern sans-serif", "transparency_allowed": True},
        "host_tool_must_be_discovered": True,
        "configuration_is_not_observed_model_evidence": True,
    }
    next_steps = report.setdefault("next_steps", {})
    next_steps["recompile_with_key"] = ("python3 scripts/stable_card.py --resume "
        + shlex.quote(str(report["editable_spec"])) + " --hero-img-key '<real_img_key>'")
    next_steps["record_visual_review"] = ("python3 scripts/finalize_card.py --spec "
        + shlex.quote(str(report["editable_spec"]))
        + " --record-review --notes '<actual inspection findings>'")
    return report


def resume(spec_value, hero_img_key=None):
    spec_path = Path(spec_value).expanduser().resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    stem = spec_path.name.removesuffix(".spec.json")
    report_path = spec_path.with_name(stem + ".report.json")
    old = json.loads(report_path.read_text(encoding="utf-8"))
    edition = "doubao" if "doubao" in old else "codex"
    pipeline = importlib.import_module(edition + "_pipeline")
    analysis = spec.get("analysis") or {}
    source = str(analysis.get("source_text") or "")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != analysis.get("source_sha256"):
        raise ValueError("source hash mismatch; restore the canonical source or create a new source-locked bundle")
    if hero_img_key:
        pipeline._set_image_key(spec, hero_img_key)
    card_path = spec_path.with_name(stem + ".card")
    # Resume only the saved spec; preserve scene, preset, user-edited copy and buttons.
    card, compiled, validation = pipeline._compile_once(
        spec, card_path=card_path, spec_path=spec_path,
        style_path=spec_path.with_name(stem + ".style.md"), brand_context="")
    from cardkit_format import write_cardkit_bundle
    wrapper = write_cardkit_bundle(card_path, card_name=spec.get("title"), base_name=stem)
    provider = old[edition]
    required = bool(provider.get("image_required"))
    motion = bool(provider.get("seedance_required"))
    contract = provider.get("card_image_contract") if isinstance(provider.get("card_image_contract"), dict) else {}
    render_strategy = str(provider.get("render_strategy") or contract.get("render_strategy") or spec.get("render_strategy") or "").strip()
    if render_strategy in {"html_infographic_to_png", "html_to_png", "html"}:
        render_strategy = "native_model"
    if motion:
        generation = pipeline._motion_generation_gate(card_path.with_name("hero.gif"),
            card_path.with_name("hero-motion-generation.json"), required=required)
    else:
        generation = pipeline._ai_generation_gate(card_path.with_name("hero.png"),
            card_path.with_name("hero-generation.json"), required=required,
            generation_mode=spec.get("image_generation_mode") or pipeline.DIRECT_IMAGE2_MODE
            if edition == "codex" else spec.get("image_generation_mode") or pipeline.DIRECT_SEEDREAM_MODE)
    asset_ready = not required or bool(generation.get("ready"))
    key_ready = bool((spec.get("hero") or {}).get("img_key")) and pipeline._contains_tag(card, {"img"})
    image_ready = required and asset_ready and key_ready
    scene_ok = not compiled.get("scene_contract") or compiled["scene_contract"].get("ok", False)
    from card_studio_contract import build_quality_gates, build_generation_workflow
    gates = build_quality_gates(card, spec, validation, wrapper=wrapper["wrapper"],
        cardkit_valid=wrapper["validation"]["ok"], scene_contract_ok=scene_ok,
        image_required=required, **{("visual_output_ready" if edition == "doubao" else "image2_ready"): asset_ready},
        image_ready=image_ready)
    valid = bool(validation["ok"] and scene_ok and gates["structural_passed"] and wrapper["size_ok"])
    workflow = build_generation_workflow(gates, validation_ok=validation["ok"], scene_contract_ok=scene_ok,
        image_required=required, **{("visual_output_ready" if edition == "doubao" else "image2_ready"): asset_ready},
        image_ready=image_ready, cardkit_valid=wrapper["validation"]["ok"])
    spec["quality_gates"] = gates
    spec["generation_workflow"] = workflow
    write_json(spec_path, spec)
    old["generation_workflow"] = workflow
    old.update(status="blocked" if not valid else ("needs_gif" if motion else "needs_image")
               if required and not image_ready else "ready", card=str(card_path), editable_spec=str(spec_path),
               validation=validation, compile=compiled, quality_gates=gates, ai_generation=generation)
    old["readiness"] = {"valid": valid, "image_ready": image_ready,
                       "visual_output_ready": asset_ready,
                       "image2_output_ready": asset_ready if edition == "codex" else True,
                       "seedream_output_ready": asset_ready if edition == "doubao" and not motion else True,
                       "seedance_output_ready": asset_ready if motion else True,
                       "sendable": valid and bool(compiled.get("sendable")) and (not required or image_ready),
                       "cardkit_editor_ready": valid and (not required or image_ready),
                       "cardkit_entity_ready": valid and (not required or image_ready),
                       "blockers": list(validation.get("errors", [])) + ([] if asset_ready else [generation.get("error") or generation.get("status")])}
    provider["quality_gates"] = gates
    provider["image_ready"] = image_ready
    provider["visual_output_ready" if edition == "doubao" else "image2_ready"] = asset_ready
    provider["render_strategy"] = render_strategy
    contract = provider["card_image_contract"]
    asset_path = card_path.with_name("hero.gif" if motion else "hero.png")
    embedded_status = (
        "embedded_image2_card_image" if edition == "codex" else
        "embedded_seedance_gif" if motion else "embedded_seedream_image"
    )
    waiting_status = "visual_output_ready_waiting_real_img_key"
    contract.update(status="not_required" if not required else embedded_status if image_ready else
                    waiting_status if asset_ready else generation.get("status"),
                    card_image_embedded=key_ready, real_img_key_supplied=key_ready,
                    final_asset=str(asset_path), final_asset_exists=asset_path.is_file(),
                    final_asset_contains_functional_text=required and asset_ready,
                    render_strategy=render_strategy)
    provider["ai_generation_ready"] = asset_ready
    provider["hero_img_key_supplied"] = key_ready
    old["cardkit_import_file"] = wrapper["cardkit_card"]
    attach_delivery_evidence(old)
    manifest_path = spec_path.with_name(stem + ".cardkit-import.json")
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update(status="ready_for_cardkit_import" if old["readiness"]["cardkit_editor_ready"] else "blocked",
                        readiness=old["readiness"], quality_gates=gates, visual_review=old["visual_review"],
                        generation_workflow=workflow, blockers=old["readiness"]["blockers"],
                        card=wrapper["cardkit_card"], api_card=str(card_path),
                        card_name=wrapper["card_name"], wrapper_validation=wrapper["validation"],
                        file_size_bytes=wrapper["file_size_bytes"], size_ok=wrapper["size_ok"],
                        ai_generation=generation, ai_generation_ready=asset_ready)
        for field in ("image2_output_ready", "seedream_output_ready", "seedance_output_ready", "visual_output_ready"):
            if field in manifest:
                manifest[field] = old["readiness"][field]
        # Do not retain earlier draft inspection errors after the media has changed.
        for field in ("image2_output", "seedream_output", "seedance_output"):
            if field in manifest:
                manifest[field].update(ready=asset_ready, status=generation.get("status"),
                                       error=generation.get("error"))
        write_json(manifest_path, manifest)
    write_json(report_path, old)
    return old


def record_review(spec_value, notes):
    spec_path = Path(spec_value).expanduser().resolve()
    if not notes or not notes.strip():
        raise ValueError("record actual visual findings after inspecting the image and native card")
    report_path = spec_path.with_name(spec_path.name.removesuffix(".spec.json") + ".report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report["readiness"].get("image_ready"):
        raise ValueError("compile with the verified media and real img_key before reviewing the final card")
    evidence = report["artifact_fingerprints"]
    record = Path(report["visual_review"]["record"])
    write_json(record, {**evidence, "decision": "pass", "notes": notes.strip(),
                        "reviewer": "calling agent after visual inspection"})
    return resume(str(spec_path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--hero-img-key")
    parser.add_argument("--record-review", action="store_true")
    parser.add_argument("--notes")
    args = parser.parse_args()
    try:
        result = record_review(args.spec, args.notes) if args.record_review else resume(args.spec, args.hero_img_key)
        print(json.dumps({"status": result["status"], "card": result["card"],
                          "readiness": result["readiness"], "media_task": result["media_task"]}, ensure_ascii=False, indent=2))
        return 2 if result["status"] == "blocked" else 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
