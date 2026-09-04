#!/usr/bin/env python3
"""Doubao Work text -> Seedream/Seedance Feishu Card 2.0 pipeline.

Static information visuals use Seedream 5.0 Pro. Motion-worthy timelines,
processes, demonstrations, and state transitions automatically route to a
Seedance 2.5 GIF. This module never fabricates facts or performs local media
composition, text overlays, video-to-GIF conversion, or post-processing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from auto_layout import build_auto_spec, build_image_text_checklist  # noqa: E402
from cardkit_format import CARDKIT_MAX_BYTES, write_cardkit_bundle  # noqa: E402
from card_studio_contract import (  # noqa: E402
    STABILITY_PROFILE,
    build_generation_workflow,
    build_input_brief,
    build_quality_gates,
    build_stability_contract,
)
from content_intelligence import NO_IMAGE_RE, URL_RE, build_information_allocation, clean_url  # noqa: E402
from generate_card import compile_outputs, contains_placeholder, load_preset_registry  # noqa: E402
from generate_style import build_style_document, infer_style  # noqa: E402
from motion_strategy import build_motion_prompt, build_motion_spec  # noqa: E402
from runtime_profile import (  # noqa: E402
    default_image_mode,
    default_motion_mode,
    image_mode_config,
    image_runtime,
    motion_mode_config,
    motion_runtime,
)
from validate_card import validate  # noqa: E402


DEFAULT_DESIGN_PLAN: Dict[str, Any] = {
    "media_policy": {
        "image_generation_mode": "seedream_5_pro_direct_full_card",
        "need_hero": True,
        "need_gallery": False,
        "reason": "默认每张卡片生成至少一张信息视觉：真实数据用图表，流程用流程信息图，对比用对比信息图，其他用主题信息视觉；只有用户明确要求无图才跳过",
        "information_carrier": True,
        "not_decorative": True,
        "native_text_pairing": "image immediately before or beside the native block it explains",
        "facts_must_remain_in_text": True,
        "default_visual_required": True,
    }
}

IMAGE_ROLES = [
    "cover",
    "information_carrier",
    "text_companion",
]

DIRECT_SEEDREAM_MODE = "seedream_5_pro_direct_full_card"
DIRECT_SEEDREAM_TEXT_MODE = "seedream_5_pro_direct_selected_text_and_layout"
BANNER_SEEDREAM_MODE = "seedream_5_pro_banner_plus_native_card"
BANNER_SEEDREAM_TEXT_MODE = "seedream_5_pro_banner_selected_text_and_layout"
SUPPORTED_IMAGE_MODES = (DIRECT_SEEDREAM_MODE, BANNER_SEEDREAM_MODE)
DIRECT_SEEDANCE_GIF_MODE = "seedance_2_5_direct_gif"


def _runtime_image_profile() -> Dict[str, Any]:
    try:
        return image_runtime()
    except ValueError:
        return {
            "provider": "doubao.image_gen",
            "generation_tool": "doubao.image_gen",
            "generation_family": "seedream-class",
            "generation_model": "seedream-5.0-pro",
            "generation_model_label": "Seedream 5.0 Pro",
            "default_mode": DIRECT_SEEDREAM_MODE,
        }


def _runtime_motion_profile() -> Dict[str, Any]:
    try:
        return motion_runtime()
    except ValueError:
        return {
            "provider": "doubao-work.builtin-video",
            "generation_tool": "doubao.video_gen",
            "generation_family": "seedance-class",
            "generation_model": "seedance-2.5",
            "generation_model_label": "Seedance 2.5",
            "default_mode": DIRECT_SEEDANCE_GIF_MODE,
            "output_format": "gif",
        }


def _mode_config(mode: str) -> Dict[str, Any]:
    try:
        return image_mode_config(mode)
    except ValueError:
        if mode == DIRECT_SEEDREAM_MODE:
            return {
                "text_policy": DIRECT_SEEDREAM_TEXT_MODE,
                "roles": list(IMAGE_ROLES),
                "aspect_ratio": "2:3",
            }
        if mode == BANNER_SEEDREAM_MODE:
            return {
                "text_policy": BANNER_SEEDREAM_TEXT_MODE,
                "roles": ["banner", "information_carrier", "text_companion"],
                "aspect_ratio": "3:1",
            }
        raise


def _default_image_mode() -> str:
    try:
        mode = default_image_mode()
    except ValueError:
        mode = DIRECT_SEEDREAM_MODE
    return mode if mode in SUPPORTED_IMAGE_MODES else DIRECT_SEEDREAM_MODE


def _image_generation_mode(spec: Mapping[str, Any]) -> str:
    """Return the selected Doubao generated-image path."""
    explicit = str(spec.get("image_generation_mode") or "").strip()
    if explicit and explicit not in SUPPORTED_IMAGE_MODES:
        raise ValueError(f"image_generation_mode must be one of {', '.join(SUPPORTED_IMAGE_MODES)}")
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), Mapping) else {}
    plan = analysis.get("design_plan") if isinstance(analysis, Mapping) else {}
    media = plan.get("media_policy") if isinstance(plan, Mapping) else {}
    planned = str(media.get("image_generation_mode") or _default_image_mode()).strip()
    if planned not in SUPPORTED_IMAGE_MODES:
        raise ValueError(
            f"media_policy.image_generation_mode must be one of {', '.join(SUPPORTED_IMAGE_MODES)}"
        )
    return explicit or planned


def _refresh_functional_text_contract(spec: Dict[str, Any]) -> None:
    """Refresh the source-backed Seedream 5.0 Pro proofing checklist after transforms."""
    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        return
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), dict) else {}
    source_text = str(analysis.get("source_text") or "")
    existing_allocation = build_information_allocation(
        source_text,
        scene=spec.get("scene") if isinstance(spec.get("scene"), str) else None,
        title=str(spec.get("title") or ""),
        blocks=blocks,
        button_suggestions=analysis.get("button_suggestions") if isinstance(analysis, dict) else None,
        supplied_media=(spec.get("media_contract") or {}).get("image_source") == "real_image" if isinstance(spec.get("media_contract"), dict) else False,
        explicit_media=isinstance(spec.get("hero"), dict),
        force_no_image=not isinstance(spec.get("hero"), dict),
    )
    labels = build_image_text_checklist(blocks, str(spec.get("title") or ""), allocation=existing_allocation)
    has_hero = isinstance(spec.get("hero"), dict)
    generation_mode = _image_generation_mode(spec) if has_hero else _default_image_mode()
    mode = (
        str(_mode_config(generation_mode).get("text_policy") or DIRECT_SEEDREAM_TEXT_MODE)
        if has_hero and labels
        else "none"
    )
    contract = spec.setdefault("visual_contract", {})
    if not isinstance(contract, dict):
        contract = {}
        spec["visual_contract"] = contract
    contract["text_in_image"] = mode
    contract["functional_text"] = labels if mode != "none" else []
    contract["functional_text_source_locked"] = mode != "none"
    analysis = spec.get("analysis")
    image_text_layout = generation_mode if mode != "none" else None
    contract["image_text_layout"] = image_text_layout if mode != "none" else None
    contract["image_text_scope"] = (
        "the Seedream 5.0 Pro model must render only the source-backed text selected by information_allocation.image.include; native Card keeps a concise editable summary and key facts while source.txt keeps the complete source; no post-processing text layer is allowed"
        if mode != "none"
        else None
    )

    design = analysis.get("design_plan") if isinstance(analysis, dict) else None
    media = design.get("media_policy") if isinstance(design, dict) else None
    if isinstance(media, dict):
        media["text_in_image"] = mode
        media["functional_text"] = labels if mode != "none" else []
        media["functional_text_source_locked"] = mode != "none"
        media["image_text_layout"] = image_text_layout if mode != "none" else None
        media["information_allocation"] = existing_allocation
    hero = spec.get("hero")
    if isinstance(hero, dict) and mode != "none":
        hero["text_in_image"] = mode
        hero["functional_text"] = labels
        hero["functional_text_source_locked"] = True
        hero["image_text_layout"] = image_text_layout
        hero["image_generation_mode"] = generation_mode
        hero["information_allocation"] = existing_allocation
    if isinstance(analysis, dict):
        analysis["information_allocation"] = existing_allocation
    spec["information_allocation"] = existing_allocation


def _direct_seedream_visual_status(
    image_path: Path,
    *,
    required: bool,
    generation: Mapping[str, Any],
    mode: str = DIRECT_SEEDREAM_MODE,
) -> Dict[str, Any]:
    """Describe the selected final Seedream 5.0 Pro asset without another renderer."""
    result: Dict[str, Any] = {
        "required": required,
        "mode": mode,
        "path": str(image_path),
        "ready": False,
        "post_processing": "none",
        "text_and_layout_source": "Seedream 5.0 Pro model",
        "manual_visual_review_required": True,
    }
    if not required:
        result["status"] = "not_required"
        return result
    if not image_path.is_file():
        result["status"] = "seedream_image_missing"
        result["error"] = f"Seedream 5.0 Pro image not found: {image_path}"
        return result
    if not bool(generation.get("ready")):
        result["status"] = "seedream_provenance_not_ready"
        result["error"] = str(generation.get("error") or "Seedream 5.0 Pro provenance gate failed")
        return result
    result.update({
        "status": "visual_output_ready_for_visual_review",
        "ready": True,
        "exact_text_verification": "manual_visual_review_required",
        "aspect_ratio": _mode_config(mode).get("aspect_ratio"),
    })
    return result


def _ai_generation_gate(
    image_path: Path,
    manifest_path: Path,
    *,
    required: bool,
    generation_mode: str = DIRECT_SEEDREAM_MODE,
) -> Dict[str, Any]:
    """Verify that the final image came through the selected Seedream 5.0 Pro step."""
    result: Dict[str, Any] = {
        "required": required,
        "manifest": str(manifest_path),
        "image": str(image_path),
        "ready": False,
    }
    if not required:
        result["status"] = "not_required"
        return result
    if not image_path.is_file():
        result["status"] = "image_missing"
        return result
    if not manifest_path.is_file():
        result["status"] = "provenance_manifest_missing"
        result["error"] = "hero-generation.json is required for an image-led card"
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["status"] = "provenance_manifest_invalid"
        result["error"] = str(exc)
        return result
    if not isinstance(manifest, dict):
        result["status"] = "provenance_manifest_invalid"
        result["error"] = "hero-generation.json must be an object"
        return result
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    tool = str(manifest.get("tool") or "").strip()
    generation_family = str(manifest.get("generation_family") or "").strip().lower()
    prompt_value = Path(str(manifest.get("prompt_file") or ""))
    prompt_path = prompt_value if prompt_value.is_absolute() else manifest_path.parent / prompt_value
    tool_ok = tool in {"doubao.image_gen", "image_gen", "seedream"} or tool.endswith(".image_gen")
    family_ok = generation_family.startswith("seedream") or generation_family in {"image-gen", "image-generation"}
    result.update({
        "manifest_data": manifest,
        "image_sha256": image_sha256,
        "tool_ok": tool_ok,
        "generation_family_ok": family_ok,
    })
    expected_text_policy = str(_mode_config(generation_mode).get("text_policy") or DIRECT_SEEDREAM_TEXT_MODE)
    manifest_mode = str(manifest.get("generation_mode") or generation_mode).strip()
    if (
        manifest.get("asset_name") not in {None, "hero.png"}
        or manifest_mode != generation_mode
        or manifest.get("text_policy") != expected_text_policy
        or manifest.get("image_sha256") != image_sha256
    ):
        result["status"] = "provenance_asset_mismatch"
        result["error"] = "hero-generation.json does not identify the selected final Seedream 5.0 Pro image mode"
        return result
    prompt_hash_ok = True
    if manifest.get("prompt_sha256") and prompt_path.is_file():
        prompt_hash_ok = manifest.get("prompt_sha256") == hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    result["prompt_hash_ok"] = prompt_hash_ok
    if not tool_ok or not family_ok or not prompt_path.is_file() or not prompt_hash_ok:
        result["status"] = "provenance_contract_failed"
        result["error"] = "manifest must identify an Seedream 5.0 Pro-class image tool, the selected mode, a matching prompt file, and a valid prompt hash when supplied"
        return result
    result["status"] = "ready"
    result["ready"] = True
    return result


def _motion_generation_gate(
    asset_path: Path,
    manifest_path: Path,
    *,
    required: bool,
    generation_mode: str = DIRECT_SEEDANCE_GIF_MODE,
) -> Dict[str, Any]:
    """Verify a direct Seedance 2.5 animated GIF and its observed provenance."""
    result: Dict[str, Any] = {
        "required": required,
        "manifest": str(manifest_path),
        "asset": str(asset_path),
        "ready": False,
        "post_processing": "none",
    }
    if not required:
        result["status"] = "not_required"
        return result
    if not asset_path.is_file():
        result["status"] = "gif_missing"
        return result
    if not asset_path.read_bytes()[:6] in {b"GIF87a", b"GIF89a"}:
        result["status"] = "gif_container_invalid"
        result["error"] = "hero.gif must be a real GIF returned by the Doubao Work motion tool"
        return result
    if not manifest_path.is_file():
        result["status"] = "motion_provenance_missing"
        result["error"] = "hero-motion-generation.json is required for a Seedance GIF"
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result["status"] = "motion_provenance_invalid"
        result["error"] = str(exc)
        return result
    if not isinstance(manifest, dict):
        result["status"] = "motion_provenance_invalid"
        result["error"] = "hero-motion-generation.json must be an object"
        return result
    asset_sha256 = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    tool = str(manifest.get("tool") or "").strip()
    family = str(manifest.get("generation_family") or "").strip().lower()
    prompt_value = Path(str(manifest.get("prompt_file") or ""))
    prompt_path = prompt_value if prompt_value.is_absolute() else manifest_path.parent / prompt_value
    tool_ok = tool in {"doubao.video_gen", "video_gen", "motion_gen", "animation_gen"} or tool.endswith((".video_gen", ".motion_gen", ".animation_gen"))
    family_ok = family.startswith("seedance") or family in {"video-generation", "motion-generation"}
    inspection = manifest.get("inspection") if isinstance(manifest.get("inspection"), Mapping) else {}
    prompt_hash_ok = bool(prompt_path.is_file())
    if prompt_hash_ok and manifest.get("prompt_sha256"):
        prompt_hash_ok = manifest.get("prompt_sha256") == hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    contract_ok = (
        manifest.get("asset_name") == "hero.gif"
        and manifest.get("asset_sha256") == asset_sha256
        and str(manifest.get("generation_mode") or "") == generation_mode
        and str(manifest.get("output_format") or "").lower() == "gif"
        and bool(inspection.get("animated"))
        and int(inspection.get("frame_count") or 0) >= 2
    )
    result.update({
        "manifest_data": manifest,
        "asset_sha256": asset_sha256,
        "tool_ok": tool_ok,
        "generation_family_ok": family_ok,
        "prompt_hash_ok": prompt_hash_ok,
        "animated": bool(inspection.get("animated")),
        "frame_count": inspection.get("frame_count"),
    })
    if not contract_ok or not tool_ok or not family_ok or not prompt_hash_ok:
        result["status"] = "motion_provenance_failed"
        result["error"] = "manifest must identify a real Seedance-class direct GIF, matching prompt, hash, and animated frame inspection"
        return result
    result["status"] = "ready"
    result["ready"] = True
    return result


def _focused_title(text: str, current: str) -> Optional[str]:
    """Prefer an event/product title over a long greeting when one is clear."""
    first = current.strip()
    greeting = bool(re.match(r"^(?:hello|hi|hey|嗨|你好|大家好|各位|朋友们)", first, re.I))
    if not greeting and len(first) <= 18:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[1:7]:
        clean = re.sub(r"\[[^\]]+\]", "", line)
        for anchor in ("AI先锋大赛", "先锋大赛"):
            position = clean.find(anchor)
            if position >= 0:
                candidate = re.split(r"[，。！？!?；;]", clean[position:])[0].strip()
                if candidate:
                    return candidate[:32]
        if re.search(r"开营|培训|活动|通知|发布|报名", clean):
            candidate = re.split(r"[，。！？!?；;]", clean)[0].strip()
            candidate = re.sub(r"^(?:感谢大家[^！!。]*[！!。]|我们)", "", candidate).strip()
            if candidate and len(candidate) <= 32:
                return candidate
    return None


def _apply_title_focus(spec: Dict[str, Any], text: str) -> None:
    analysis = spec.get("analysis")
    if not isinstance(analysis, dict):
        return
    current = str(spec.get("title") or "").strip()
    focused = _focused_title(text, current)
    if not focused or focused == current:
        return
    spec["title"] = focused
    hero = spec.get("hero")
    if isinstance(hero, dict):
        hero["alt"] = f"{focused}首图"
    transformations = analysis.setdefault("transformations", [])
    if isinstance(transformations, list):
        transformations.append({
            "kind": "title_focus",
            "source": current,
            "output": focused,
            "reason": "首行是问候语；从后续明确的大赛/活动语义提取卡片标题，不改变正文事实",
        })
    plan = analysis.get("design_plan")
    if isinstance(plan, dict):
        content_shape = plan.get("content_shape")
        if isinstance(content_shape, dict):
            content_shape["title"] = focused
        hierarchy = plan.get("hierarchy")
        if isinstance(hierarchy, dict) and isinstance(hierarchy.get("primary"), list):
            primary = hierarchy["primary"]
            if primary and primary[0] == current:
                primary[0] = focused


def _quote_marker(value: Any) -> bool:
    return bool(re.search(r"赵总|CEO|首席执行官|理念|金句|寄语", str(value or ""), re.I))


def _promote_quote_block(spec: Dict[str, Any]) -> bool:
    """Keep an explicitly marked leadership quote outside long-text folding."""
    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        return False
    promoted: Optional[Dict[str, Any]] = None
    retained: list[Dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("type", block.get("kind", ""))).lower()
        if kind in {"collapse", "collapsible_panel"}:
            children = block.get("blocks", block.get("elements", []))
            if not isinstance(children, list):
                retained.append(block)
                continue
            kept_children: list[Dict[str, Any]] = []
            for child in children:
                if (
                    isinstance(child, dict)
                    and str(child.get("type", child.get("kind", ""))).lower() == "section"
                    and _quote_marker(child.get("title"))
                    and child.get("body")
                ):
                    if promoted is None:
                        promoted = {
                            "type": "quote",
                            "eyebrow": "赵总理念" if "赵总" in str(child.get("title")) else "重要寄语",
                            "title": str(child.get("title") or "").rstrip("：:"),
                            "text": child.get("body"),
                            "emphasis": "heading",
                            "source_text": child.get("body"),
                        }
                    continue
                if isinstance(child, dict):
                    kept_children.append(child)
            if kept_children:
                updated = dict(block)
                updated["blocks"] = kept_children
                retained.append(updated)
            continue
        if kind == "section" and _quote_marker(block.get("title")) and block.get("body") and promoted is None:
            promoted = {
                "type": "quote",
                "eyebrow": "赵总理念" if "赵总" in str(block.get("title")) else "重要寄语",
                "title": str(block.get("title") or "").rstrip("：:"),
                "text": block.get("body"),
                "emphasis": "heading",
                "source_text": block.get("body"),
            }
            continue
        retained.append(block)
    if promoted is None:
        return False
    retained.append(promoted)
    spec["blocks"] = retained
    analysis = spec.get("analysis")
    if isinstance(analysis, dict):
        transformations = analysis.setdefault("transformations", [])
        if isinstance(transformations, list):
            transformations.append({
                "kind": "prominent_quote",
                "source": promoted.get("source_text"),
                "output": "quote block outside collapsible panel",
                "reason": "用户明确要求 CEO 理念位于显著区域；保留原文并避免被长文折叠",
            })
        plan = analysis.get("design_plan")
        if isinstance(plan, dict):
            strategy = plan.setdefault("component_strategy", [])
            if isinstance(strategy, list):
                strategy.append({
                    "component": "quote",
                    "priority": 1,
                    "selected": True,
                    "reason": "明确标记的领导寄语保持首屏后显著可见",
                    "status": "applied",
                })
    return True


def _deep_merge(base: Mapping[str, Any], override: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {str(key): value for key, value in base.items()}
    if not override:
        return result
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    return safe or "card"


def _resolve_output_dir(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def _set_image_key(spec: Dict[str, Any], image_key: str) -> None:
    hero = spec.get("hero")
    if not isinstance(hero, dict):
        hero = {
            "alt": f"{spec.get('title', '卡片')}首图",
            "asset_kind": "image",
            "motion": "static editorial hero",
        }
        spec["hero"] = hero
    hero["img_key"] = image_key.strip()
    design = spec.get("analysis", {}).get("design_plan") if isinstance(spec.get("analysis"), dict) else None
    if isinstance(design, dict):
        media = design.setdefault("media_policy", {})
        if isinstance(media, dict):
            media["generated"] = True
            media["uploaded"] = True


def _degrade_to_no_image(spec: Dict[str, Any], *, reason: Optional[str] = None) -> None:
    spec.pop("hero", None)
    analysis = spec.setdefault("analysis", {})
    design = analysis.get("design_plan") if isinstance(analysis, dict) else None
    if isinstance(design, dict):
        media = design.setdefault("media_policy", {})
        if isinstance(media, dict):
            media["need_hero"] = False
            media["generated"] = False
            media["uploaded"] = False
            media["status"] = "degraded_no_image"
    decision_log = analysis.setdefault("decision_log", [])
    if isinstance(decision_log, list):
        decision_log.append({
            "decision": "degraded",
            "component": "hero",
            "reason": reason or "用户显式选择无图 fallback；原生 Card 保留精简摘要和真实行动，完整事实仍在 source.txt",
        })


def _preset_color_line(preset_id: str) -> str:
    """Use the selected preset palette instead of hardcoding one visual."""
    fallback = (
        "Color/material: restrained two-tone palette with generous white space and "
        "one accent family; crisp edges, soft rounded modules, no visual noise."
    )
    try:
        registry = load_preset_registry()
    except (OSError, ValueError, json.JSONDecodeError):
        return fallback
    presets = registry.get("presets") if isinstance(registry, dict) else None
    entry = next(
        (
            item for item in presets
            if isinstance(item, dict) and str(item.get("id") or "") == preset_id
        ),
        None,
    ) if isinstance(presets, list) else None
    if not isinstance(entry, dict):
        return fallback
    gallery = entry.get("gallery") if isinstance(entry.get("gallery"), dict) else {}
    accent = str(gallery.get("accent_hex") or "").strip()
    background = str(gallery.get("background_hex") or "").strip()
    ink = str(gallery.get("ink_hex") or "").strip()
    name = str(entry.get("name") or preset_id).strip()
    if not (accent and background and ink):
        return fallback
    return (
        f"Color/material: follow the '{name}' palette — background {background}, "
        f"ink {ink}, single accent {accent}; subtle depth, crisp edges, soft rounded "
        "modules, generous white space, no visual noise."
    )


def _banner_image_prompt(spec: Dict[str, Any], *, brand_context: str = "") -> str:
    """Build a one-pass horizontal banner prompt paired with native Card text."""
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), dict) else {}
    plan = analysis.get("design_plan") if isinstance(analysis, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    media = plan.get("media_policy") if isinstance(plan.get("media_policy"), dict) else {}
    visual_contract = spec.get("visual_contract") if isinstance(spec.get("visual_contract"), dict) else {}
    prompt_contract = spec.get("prompt_routing") if isinstance(spec.get("prompt_routing"), dict) else {}
    allocation = spec.get("information_allocation") if isinstance(spec.get("information_allocation"), dict) else {}
    image_allocation = allocation.get("image") if isinstance(allocation.get("image"), dict) else {}
    image_items = image_allocation.get("include") if isinstance(image_allocation.get("include"), list) else []
    image_text = "\n".join(
        f"- visible text (metadata role={item.get('role', 'label')}): {item.get('text', '')}"
        for item in image_items
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ) or "(no image text; generate only the visual concept)"
    preset = str(spec.get("preset") or plan.get("recommended_preset") or "modern-oriental-signal")
    scene = str(spec.get("scene") or "custom")
    source = str(analysis.get("source_text") or "")
    input_brief = spec.get("input_brief") if isinstance(spec.get("input_brief"), dict) else {}
    purpose_context = input_brief.get("purpose") if isinstance(input_brief.get("purpose"), dict) else {}
    recipient_context = input_brief.get("recipient") if isinstance(input_brief.get("recipient"), dict) else {}
    visual_routing = prompt_contract.get("visual_skill_routing") if isinstance(prompt_contract.get("visual_skill_routing"), dict) else {}
    selected_pack_labels = visual_routing.get("selected_pack_labels") if isinstance(visual_routing.get("selected_pack_labels"), list) else []
    visual_negative = str(visual_routing.get("visual_negative_prompt") or "").strip()
    runtime = _runtime_image_profile()
    model_label = str(runtime.get("generation_model_label") or "Seedream 5.0 Pro")
    model_id = str(runtime.get("generation_model") or "seedream-5.0-pro")
    visual_job = str(media.get("visual_job") or visual_contract.get("job") or "give the topic one clear visual anchor")
    return "\n".join([
        "Use case: banner-header-image",
        "Asset type: final horizontal Banner header image for a Feishu Card 2.0; it is not a full-card bitmap",
        f"Generation model profile: {model_label} ({model_id}) via 豆包工作 built-in image_gen; record observable tool/model provenance in hero-generation.json and use platform-managed if the host does not expose the model id",
        f"Scene: {scene}; visual preset: {preset}",
        f"Auto-routed prompt recipe: {prompt_contract.get('primary_profile', 'general-information')}; reference template {prompt_contract.get('reference_template', 'training-notice')}; media mode {prompt_contract.get('media_mode', 'static')}",
        f"Auto-selected visual skill packs: {', '.join(str(item) for item in selected_pack_labels) or 'local enterprise default'}; visual style {visual_routing.get('style_id', 'clean-editorial')}; use the local mapping as transparent fallback if upstream methods are unavailable.",
        "Default method pass: first invoke or read available Guizang Social Card Skill and baoyu-skills guidance, then use the 豆包工作 Seedream 5.0 Pro image_gen step for this one-pass final banner. Do not use an upstream renderer, HTML/CSS/SVG, Playwright screenshot, alternate provider, or post-processing.",
        f"Planning context only: purpose={purpose_context.get('value') or purpose_context.get('inferred_mode') or 'general-information'}; recipient={recipient_context.get('value') or 'not provided'}; these values cannot become a remote target.",
        f"Primary request: generate an approximate 3:1 horizontal banner that conveys {visual_job}. The native Card below the banner carries a concise summary, key facts, source-backed charts, and real buttons; source.txt keeps the complete copy. Never generate a button, CTA pill, button-shaped rectangle, chevron-plus-action control, fake link, or any other pseudo-interactive element in the image.",
        "Typography: render only the source-backed Seedream 5.0 Pro whitelist below, sharply and legibly, with a modern Chinese sans-serif hierarchy; do not invent or rewrite text. The metadata role marker is instruction-only and must not be visible.",
        "Image text whitelist (verbatim; render only these source-backed items in the banner):",
        "----- BEGIN IMAGE TEXT WHITELIST -----",
        image_text,
        "----- END IMAGE TEXT WHITELIST -----",
        "Native Card carries the concise editable summary, key facts, source-backed charts, URLs, and real clickable buttons. Full long-form copy stays in source.txt or opens through a real source URL. Any real action belongs to a native Card 2.0 button with a real behavior.",
        "Functional image rule: all visible image text and layout must come directly from this one Seedream 5.0 Pro generation and match the whitelist. No local drawing, overlay, compositing, second image model, empty text box, gibberish, button-shaped UI, or CTA label.",
        _preset_color_line(preset),
        f"Visual pack guardrails: {visual_negative}" if visual_negative else "Visual pack guardrails: one focal path, source-locked labels, clean enterprise readability.",
        "Full source copy for fact checking only; do not put every line in the banner:",
        "----- BEGIN SOURCE COPY -----",
        source.strip(),
        "----- END SOURCE COPY -----",
        "Revision proofing: if any selected text is wrong or unreadable, regenerate the complete banner from scratch in one Seedream 5.0 Pro pass. Never repair the PNG with text or another model.",
    ])


def _detect_urls(text: str) -> list[Dict[str, Any]]:
    """Extract source URLs and classify native-button candidates."""
    matches = list(URL_RE.finditer(text))
    seen: set[str] = set()
    buttons: list[Dict[str, Any]] = []
    for match in matches:
        raw_url = match.group(0)
        url = clean_url(raw_url)
        if not url or url in seen:
            continue
        seen.add(url)
        index = match.start()
        before = text[max(0, index - 24):index]
        if any(token in before for token in ("作品", "案例", "查看", "详情")):
            label = "查看作品" if "作品" in before else "查看详情"
        elif any(token in before for token in ("报名", "注册")):
            label = "立即报名"
        elif "下载" in before:
            label = "下载资料"
        elif any(token in before for token in ("访问", "打开")):
            label = "访问链接"
        else:
            label = "查看链接"
        action_context = any(
            token in before
            for token in ("请", "立即", "点击", "前往", "进入", "填写", "领取", "报名", "注册", "下载", "预约", "查看", "打开", "访问", "提交")
        )
        passive_context = any(
            token in before
            for token in ("参考", "来源", "原文", "详情见", "链接如下", "地址如下", "参见", "详见")
        )
        buttons.append({
            "label": label,
            "url": url,
            "button_eligible": bool(action_context and not passive_context),
            "label_source": "source_action_context" if action_context else "source_descriptive_context",
        })
    return buttons


LAYOUT_PROPOSALS: list[Dict[str, Any]] = [
    {
        "id": "banner-led",
        "name": "Banner 首图主导",
        "description": "Seedream 5.0 Pro 一次性生成横幅首图，原生 Card 紧随其后承载摘要、关键事实、图表和真实按钮。",
        "image_mode": BANNER_SEEDREAM_MODE,
        "image_text_mode": BANNER_SEEDREAM_TEXT_MODE,
        "aspect_ratio": "3:1",
        "image_role": "banner",
    },
    {
        "id": "infographic-led",
        "name": "信息图主导",
        "description": "Seedream 5.0 Pro 一次性生成竖版关系信息图，适合时间线、案例、指标和阶段结构。",
        "image_mode": DIRECT_SEEDREAM_MODE,
        "image_text_mode": DIRECT_SEEDREAM_TEXT_MODE,
        "aspect_ratio": "2:3",
        "image_role": "information_carrier",
    },
    {
        "id": "text-led",
        "name": "文字主导 + 横幅锚点",
        "description": "原生 Card 承载精简摘要、关键点、图表和按钮，Seedream 5.0 Pro 只生成轻量横幅主题锚点；全文保留在 source.txt。",
        "image_mode": BANNER_SEEDREAM_MODE,
        "image_text_mode": BANNER_SEEDREAM_TEXT_MODE,
        "aspect_ratio": "3:1",
        "image_role": "text_companion",
    },
]


def _generate_proposals(text: str, spec: Mapping[str, Any]) -> list[Dict[str, Any]]:
    scene = str(spec.get("scene") or "custom")
    detected_urls = _detect_urls(text)
    return [
        {
            **template,
            "scene": scene,
            "detected_urls": detected_urls,
            "buttons": detected_urls,
        }
        for template in LAYOUT_PROPOSALS
    ]


def _merge_detected_url_buttons(spec: Dict[str, Any], detected_urls: Sequence[Mapping[str, Any]]) -> None:
    """Merge selected source URLs into native buttons without bypassing gates."""
    if not detected_urls:
        return
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), dict) else {}
    suggestions = analysis.get("button_suggestions") if isinstance(analysis, dict) else []
    approved_urls = {
        str(item.get("url"))
        for item in suggestions
        if isinstance(item, dict)
        and item.get("button_eligible")
        and item.get("selected")
        and item.get("url")
    } if isinstance(suggestions, list) else set()
    design = analysis.get("design_plan") if isinstance(analysis, dict) else {}
    component_strategy = design.get("component_strategy") if isinstance(design, dict) else []
    if any(
        isinstance(component, dict)
        and str(component.get("component") or "").lower() == "buttons"
        and component.get("selected") is False
        for component in component_strategy
    ):
        return
    if not approved_urls:
        return
    blocks = spec.setdefault("blocks", [])
    if not isinstance(blocks, list):
        return
    button_blocks = [
        block for block in blocks
        if isinstance(block, dict) and block.get("type") == "buttons"
    ]
    if not button_blocks:
        blocks.append({"type": "buttons", "items": []})
        button_blocks = [blocks[-1]]
    for block in button_blocks:
        items = block.get("items")
        if not isinstance(items, list):
            items = []
            block["items"] = items
        existing = {
            str(item.get("url"))
            for item in items
            if isinstance(item, dict) and item.get("url")
        }
        for detected in detected_urls:
            url = str(detected.get("url") or "").strip()
            if not url or url not in approved_urls or url in existing:
                continue
            items.append({
                "text": str(detected.get("label") or "查看链接"),
                "url": url,
                "type": "default",
                "auto_generated": True,
            })
            existing.add(url)


def _image_prompt(spec: Dict[str, Any], *, brand_context: str = "") -> str:
    hero = spec.get("hero") if isinstance(spec.get("hero"), dict) else {}
    generation_mode = str(
        hero.get("image_generation_mode")
        or spec.get("image_generation_mode")
        or _default_image_mode()
    ).strip()
    if generation_mode == BANNER_SEEDREAM_MODE:
        return _banner_image_prompt(spec, brand_context=brand_context)
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), dict) else {}
    plan = analysis.get("design_plan") if isinstance(analysis, dict) else {}
    if not isinstance(plan, dict):
        plan = {}
    media = plan.get("media_policy") if isinstance(plan.get("media_policy"), dict) else {}
    visual_contract = spec.get("visual_contract") if isinstance(spec.get("visual_contract"), dict) else {}
    prompt_contract = spec.get("prompt_routing") if isinstance(spec.get("prompt_routing"), dict) else {}
    allocation = spec.get("information_allocation") if isinstance(spec.get("information_allocation"), dict) else {}
    image_allocation = allocation.get("image") if isinstance(allocation.get("image"), dict) else {}
    native_allocation = allocation.get("native_card") if isinstance(allocation.get("native_card"), dict) else {}
    image_items = image_allocation.get("include") if isinstance(image_allocation.get("include"), list) else []
    image_text = "\n".join(
        f"- visible text (metadata role={item.get('role', 'label')}): {item.get('text', '')}"
        for item in image_items
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ) or "(no image text; do not invent any)"
    native_prompt_allocation = {
        key: value for key, value in native_allocation.items() if key != "buttons"
    }
    preset = str(spec.get("preset") or plan.get("recommended_preset") or "modern-oriental-signal")
    scene = str(spec.get("scene") or "custom")
    brief = str(media.get("prompt_brief") or "")
    style = infer_style(str(analysis.get("source_text") or spec.get("title") or ""), brand_context, preset)
    source = str(analysis.get("source_text") or "")
    input_brief = spec.get("input_brief") if isinstance(spec.get("input_brief"), dict) else {}
    purpose_context = input_brief.get("purpose") if isinstance(input_brief.get("purpose"), dict) else {}
    recipient_context = input_brief.get("recipient") if isinstance(input_brief.get("recipient"), dict) else {}
    if re.search(r"培训|时间线|阶段|提交|辅导|路演|开营", source):
        default_concept = "a calm visual progression from learning and experimentation to submission, coaching, and a final presentation"
    elif re.search(r"案例|问题|做法|结果|复盘", source):
        default_concept = "an information-bearing relationship map from a real-world problem to action, result, and review"
    elif re.search(r"提醒|截止|务必|报名|通知", source):
        default_concept = "a focused visual signal for the notice's priority, timing, and next action"
    else:
        default_concept = "an abstract visual map of the card's topic, grouping, and next action"
    routed_fragments = prompt_contract.get("prompt_fragments") if isinstance(prompt_contract.get("prompt_fragments"), list) else []
    routed_concept = " ".join(str(item).strip() for item in routed_fragments if str(item).strip())
    visual_routing = prompt_contract.get("visual_skill_routing") if isinstance(prompt_contract.get("visual_skill_routing"), dict) else {}
    visual_fragments = visual_routing.get("visual_prompt_fragments") if isinstance(visual_routing.get("visual_prompt_fragments"), list) else []
    visual_concept = " ".join(str(item).strip() for item in visual_fragments if str(item).strip())
    concept = " ".join(part for part in (brief, routed_concept or default_concept, visual_concept) if part)
    visual_job = str(media.get("visual_job") or visual_contract.get("job") or "give the topic one clear information anchor")
    composition = str(media.get("composition") or visual_contract.get("composition") or "one clear object or relationship")
    role = str(media.get("role") or visual_contract.get("role") or "information_anchor")
    selected_pack_labels = visual_routing.get("selected_pack_labels") if isinstance(visual_routing.get("selected_pack_labels"), list) else []
    visual_negative = str(visual_routing.get("visual_negative_prompt") or "").strip()
    runtime = _runtime_image_profile()
    model_label = str(runtime.get("generation_model_label") or "Seedream 5.0 Pro")
    model_id = str(runtime.get("generation_model") or "seedream-5.0-pro")
    direct_prompt_lines = [
            "Use case: infographic-diagram",
            "Asset type: final Feishu Card 2.0 bitmap, generated as one complete image",
            f"Generation model profile: {model_label} ({model_id}) via 豆包工作 built-in image_gen; record observable tool/model provenance in hero-generation.json and use platform-managed if the host does not expose the model id",
            f"Scene: {scene}; visual preset: {preset}",
            f"Auto-routed prompt recipe: {prompt_contract.get('primary_profile', 'general-information')}; reference template {prompt_contract.get('reference_template', 'training-notice')}; media mode {prompt_contract.get('media_mode', 'static')}",
            f"Auto-selected visual skill packs: {', '.join(str(item) for item in selected_pack_labels) or 'local enterprise default'}; visual style {visual_routing.get('style_id', 'clean-editorial')}; visual layout {visual_routing.get('visual_layout', 'single-information-anchor')}. These are the local record of the default Guizang Social Card Skill + baoyu-skills method pass; if those upstream skills are unavailable, use this mapping as the transparent fallback and do not claim external execution.",
            "Default upstream method pass: first invoke or read the available Guizang Social Card Skill and baoyu-skills guidance for content type, information architecture, visual language, and quality gates; then use 豆包工作 Seedream 5.0 Pro for the final bitmap. Never use an upstream renderer or alternate image provider.",
            f"Planning context only: purpose={purpose_context.get('value') or purpose_context.get('inferred_mode') or 'general-information'}; recipient={recipient_context.get('value') or 'not provided'}. These values may guide hierarchy and tone but must not change source facts or silently become a remote delivery target.",
            "Primary request: Generate the final information-bearing Feishu card image in one Seedream 5.0 Pro pass. The model itself must perform the visual concept, information architecture, typography, Chinese text rendering, spacing, timeline/flow layout, and quote treatment. Never generate a button, CTA pill, button-shaped rectangle, chevron-plus-action control, or any other fake interactive element in the image. Do not create an intermediate image for another renderer.",
            "Reference design language: absorb the five supplied Feishu card examples as a light enterprise information card: compact header, strong but calm title hierarchy, coherent visual metaphor, aligned information modules, clear stage progression, and restrained semantic icons. Do not copy their brand, logo, person, watermark, button, CTA, or text.",
            f"Composition: portrait mobile-safe card, high-resolution, clean outer margin, light background, one coherent visual story for the allocated task: {visual_job}. Build only the relationship, status, evidence, or stage structure that the allocation names. Keep the native Card as a concise editable summary and keep the complete source in source.txt; do not turn every paragraph into image text.",
            "Typography: render every character in the Seedream 5.0 Pro text whitelist below sharply and legibly. Use a modern Chinese sans-serif hierarchy, consistent baseline alignment, generous line spacing, and enough contrast for mobile reading. Do not invent or rewrite any whitelisted text. Text not in the whitelist belongs to the native Card and must not be squeezed into the bitmap.",
            "Whitelist metadata such as role names, parentheses, brackets, and the phrase 'metadata role=' is instruction-only; never render those metadata markers as visible image text.",
            "Image text whitelist (verbatim; render only these source-backed items):",
            "----- BEGIN IMAGE TEXT WHITELIST -----",
            image_text,
            "----- END IMAGE TEXT WHITELIST -----",
            "Native Card allocation (reference only; keep these facts in the editable Card, not automatically in the bitmap):",
            json.dumps(native_prompt_allocation, ensure_ascii=False, indent=2),
            "Native Card buttons are intentionally omitted from this image prompt. Any real action must be a separate native Card 2.0 button with a real URL or implemented application-bot contract.",
            "Full source copy (verbatim reference for fact checking; do not put every line into the bitmap):",
            "----- BEGIN SOURCE COPY -----",
            source.strip(),
            "----- END SOURCE COPY -----",
            "Functional image rule: all visible image text and layout must come directly from this Seedream 5.0 Pro generation and must match the whitelist. Do not depend on HTML, CSS, SVG, Pillow, a deterministic overlay, another image model, or post-generation compositing. Do not leave placeholder text, pseudo-letters, gibberish, fake UI text, empty text boxes, buttons, CTA labels, or button-shaped controls.",
            "Functional CTA rule: images are non-interactive. Never render a button, CTA pill, link-like control, action label presented as clickable, or chevron-plus-action control in the bitmap. The native Card layer alone may contain a button, and only when its URL/callback/form actually works.",
            "Quality bar: final deliverable must look like a professionally designed Feishu information card, with a clear visual relationship and a small amount of useful image text. Re-read the whitelist and source after rendering; check every selected date, stage, metric, and quote for exactness while leaving native-only paragraphs and all real actions out of the bitmap.",
            "Color/material: light blue, lilac, white, and one restrained accent family; subtle depth, crisp edges, soft rounded modules, no visual noise.",
            f"Visual pack guardrails: {visual_negative}" if visual_negative else "Visual pack guardrails: preserve the selected information relationship, one focal path, and source-locked labels.",
            "Avoid: blank white rectangles, unreadable microtype, dense illegible paragraphs, repeated emoji, random icons, generic gradients without structure, fake brand marks, watermarks, contradictory dates, missing lines, AI gibberish, button-shaped UI, CTA pills, link-like controls, and any post-processing step.",
            "Revision proofing requirements: regenerate the complete image from scratch in one Seedream 5.0 Pro pass when the selected image text is wrong or unreadable. Preserve each whitelisted text item exactly, including dates, Chinese punctuation, literal bracket aliases, selected timeline actions, and selected quote text. Do not add native-only paragraphs, URLs, button labels, or any fake interaction; before finishing, proofread the bitmap against both the IMAGE TEXT WHITELIST and the full SOURCE COPY.",
    ]
    return "\n".join(direct_prompt_lines)


def _compile_once(
    spec: Dict[str, Any],
    *,
    card_path: Path,
    spec_path: Path,
    style_path: Path,
    brand_context: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    card, compile_report = compile_outputs(
        spec,
        card_path,
        editable_spec=spec_path,
        persist_assets=True,
        brand_context=brand_context,
        style_output=style_path,
    )
    compile_report["cardkit_import_command"] = (
        f"python3 scripts/feishu_cli.py push-cardkit --card {shlex.quote(str(card_path))} "
        f"--name {shlex.quote(str(spec.get('title') or card_path.stem))} --dry-run"
    )
    surface = "application-bot" if compile_report.get("callbacks") else "raw"
    validation = validate(card, surface=surface)
    return card, compile_report, validation


def _contains_tag(value: Any, tags: set[str]) -> bool:
    """Return whether a compiled Card contains one of the requested tags."""
    if isinstance(value, dict):
        if value.get("tag") in tags:
            return True
        return any(_contains_tag(item, tags) for item in value.values())
    if isinstance(value, list):
        return any(_contains_tag(item, tags) for item in value)
    return False


def run_pipeline(
    text: str,
    output_dir: Path,
    *,
    name: str = "card",
    brand_context: str = "",
    hero_img_key: Optional[str] = None,
    requested_scene: Optional[str] = None,
    requested_preset: Optional[str] = None,
    design_plan: Optional[Mapping[str, Any]] = None,
    no_image: bool = False,
    force_motion: Optional[bool] = None,
    emoji_mode: str = "semantic",
    link_mode: str = "button",
    purpose: Optional[str] = None,
    recipient: Optional[str] = None,
    material_kind: str = "plain_text",
    workflow_profile: str = STABILITY_PROFILE,
) -> Dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text cannot be empty")
    if link_mode not in {"button", "inline"}:
        raise ValueError("link_mode must be button or inline")
    if not str(material_kind or "").strip():
        raise ValueError("material_kind cannot be empty")
    if workflow_profile != STABILITY_PROFILE:
        raise ValueError(f"workflow_profile must be {STABILITY_PROFILE}")

    safe_name = _safe_name(name)
    bundle = output_dir / safe_name
    bundle.mkdir(parents=True, exist_ok=True)
    source_path = bundle / f"{safe_name}.source.txt"
    plan_path = bundle / f"{safe_name}.plan.json"
    spec_path = bundle / f"{safe_name}.spec.json"
    card_path = bundle / f"{safe_name}.card"
    style_path = bundle / f"{safe_name}.style.md"
    image_prompt_path = bundle / f"{safe_name}.image-prompt.md"
    visual_spec_path = bundle / f"{safe_name}.visual-spec.json"
    motion_prompt_path = bundle / f"{safe_name}.motion-prompt.md"
    motion_spec_path = bundle / f"{safe_name}.motion-spec.json"
    image_generation_manifest_path = bundle / "hero-generation.json"
    motion_generation_manifest_path = bundle / "hero-motion-generation.json"
    prompt_routing_path = bundle / f"{safe_name}.prompt-routing.json"
    report_path = bundle / f"{safe_name}.report.json"
    cardkit_manifest_path = bundle / f"{safe_name}.cardkit-import.json"
    preview_record_path = bundle / f"{safe_name}.preview.json"
    cardkit_result_path = bundle / f"{safe_name}.cardkit-import-result.json"
    proposals_path = bundle / f"{safe_name}.proposals.json"

    _write_text(source_path, text)
    input_brief = build_input_brief(
        text,
        purpose=purpose,
        recipient=recipient,
        material_kind=material_kind,
    )
    effective_plan = _deep_merge(DEFAULT_DESIGN_PLAN, design_plan)
    explicit_media_mode = None
    if isinstance(design_plan, Mapping):
        requested_media = design_plan.get("media_policy")
        if isinstance(requested_media, Mapping):
            requested_mode = str(requested_media.get("image_generation_mode") or "").strip()
            if requested_mode:
                explicit_media_mode = requested_mode
    if explicit_media_mode:
        # An explicit mode is a user-selected image layout, not merely a
        # reporting preference. Keep the default auto-allocation conservative,
        # but make direct mode selection actually request its image asset.
        effective_plan = _deep_merge(
            effective_plan,
            {"media_policy": {
                "need_hero": True,
                "information_carrier": True,
                "not_decorative": True,
            }},
        )
    explicit_no_image = no_image or bool(NO_IMAGE_RE.search(text))
    if explicit_no_image:
        effective_plan = _deep_merge(effective_plan, {"media_policy": {"need_hero": False, "explicit_no_image": True}})

    spec = build_auto_spec(
        text,
        requested_scene=requested_scene,
        requested_preset=requested_preset,
        design_plan=effective_plan,
        emoji_mode=emoji_mode,
        link_mode=link_mode,
    )
    detected_urls = _detect_urls(text)
    if link_mode == "button":
        _merge_detected_url_buttons(spec, detected_urls)
    spec["detected_urls"] = detected_urls
    proposals = _generate_proposals(text, spec)
    _write_json(
        proposals_path,
        {"proposals": proposals, "detected_urls": detected_urls, "source": str(source_path)},
    )
    analysis = spec.setdefault("analysis", {})
    if not isinstance(analysis, dict):
        raise ValueError("auto layout analysis must be an object")
    spec["input_brief"] = input_brief
    stability_contract = build_stability_contract()
    spec["workflow_profile"] = workflow_profile
    spec["stability_contract"] = stability_contract
    analysis["input_brief"] = input_brief
    analysis["workflow_profile"] = workflow_profile
    analysis["stability_contract"] = stability_contract
    if not input_brief["purpose"].get("value"):
        input_brief["purpose"]["inferred_mode"] = spec.get("content_mode") or spec.get("scene") or "general-information"
    _apply_title_focus(spec, text)
    planned_design = spec.get("analysis", {}).get("design_plan") if isinstance(spec.get("analysis"), dict) else None
    media_policy = planned_design.get("media_policy") if isinstance(planned_design, Mapping) else None
    image_requested = (
        not explicit_no_image
        and isinstance(media_policy, Mapping)
        and bool(media_policy.get("need_hero", False))
    )
    image_generation_mode = _image_generation_mode(spec) if image_requested else "none"
    spec["image_generation_mode"] = image_generation_mode if image_requested else "none"
    preliminary_hero = spec.get("hero") if isinstance(spec.get("hero"), dict) else {}
    preliminary_media = spec.get("media_contract") if isinstance(spec.get("media_contract"), dict) else {}
    preliminary_source = str(preliminary_hero.get("image_source") or preliminary_media.get("image_source") or "ai_generated")
    motion_spec = build_motion_spec(
        text,
        title=str(spec.get("title") or ""),
        visual_spec=spec.get("visual_spec") if isinstance(spec.get("visual_spec"), Mapping) else {},
        image_required=image_requested and preliminary_source != "real_image",
        force_motion=force_motion,
    )
    motion_selected = bool(motion_spec.get("selected"))
    motion_generation_mode = default_motion_mode() if motion_selected else "none"
    if motion_selected:
        motion_spec["generation_mode"] = motion_generation_mode
        motion_mode = motion_mode_config(motion_generation_mode)
        motion_runtime_config = _runtime_motion_profile()
        runtime = motion_runtime_config
        selected_roles = list(motion_mode.get("roles") or ["cover", "information_carrier", "motion_explainer"])
    else:
        runtime = _runtime_image_profile()
        selected_roles = list(_mode_config(image_generation_mode).get("roles") or IMAGE_ROLES) if image_requested else []
    generation_tool = str(runtime.get("generation_tool") or runtime.get("provider") or "doubao.image_gen")
    generation_family = str(runtime.get("generation_family") or "seedream-class")
    generation_model = str(runtime.get("generation_model") or ("seedance-2.5" if motion_selected else "seedream-5.0-pro"))
    generation_model_label = str(runtime.get("generation_model_label") or ("Seedance 2.5" if motion_selected else "Seedream 5.0 Pro"))
    final_asset_path = bundle / ("hero.gif" if motion_selected else "hero.png")
    active_prompt_path = motion_prompt_path if motion_selected else image_prompt_path
    generation_manifest_path = motion_generation_manifest_path if motion_selected else image_generation_manifest_path
    active_generation_mode = motion_generation_mode if motion_selected else image_generation_mode
    spec["motion_spec"] = motion_spec
    spec["media_generation_mode"] = active_generation_mode if image_requested else "none"
    if motion_selected:
        media_contract = spec.setdefault("media_contract", {})
        if isinstance(media_contract, dict):
            media_contract.update({
                "mode": "gif",
                "asset_kind": "gif",
                "motion_auto_selected": force_motion is None,
                "static_first_frame_required": False,
                "essential_text_outside_animation": True,
                "generation_tool": generation_tool,
                "generation_model": generation_model,
                "generation_model_label": generation_model_label,
            })
        hero_node = spec.get("hero")
        if isinstance(hero_node, dict):
            hero_node.update({
                "asset_kind": "gif",
                "generation_tool": generation_tool,
                "generation_model": generation_model,
                "generation_model_label": generation_model_label,
                "motion_generation_mode": motion_generation_mode,
            })
    analysis["doubao_mode"] = {
        "media_generation": "built_in_video_gen_direct_gif" if motion_selected else "built_in_image_gen",
        "generation_tool": generation_tool,
        "generation_family": generation_family,
        "generation_model": generation_model,
        "generation_model_label": generation_model_label,
        "model_id_source": runtime.get("model_id_source"),
        "generation_provenance": generation_manifest_path.name,
        "image_generation_mode": image_generation_mode if image_requested else "none",
        "motion_generation_mode": motion_generation_mode,
        "motion_auto_selected": motion_selected and force_motion is None,
        "motion_reasons": motion_spec.get("reasons"),
        "final_upload_asset": final_asset_path.name if image_requested else None,
        "image_upload": "lark-cli im images create",
        "cardkit_delivery": "python3 scripts/feishu_cli.py push-cardkit (Byte CLI Web-backed CardKit template)",
        "api_cardkit_delivery": "lark-cli api POST /open-apis/cardkit/v1/cards (explicit API Entity only)",
        "image_text_layout": image_generation_mode,
        "source_locked": image_requested,
        "source_copy_in_prompt": image_requested,
        "native_text_fallback": True,
        "image_source_types": ["real_image", "ai_generated"],
        "ai_image_roles": selected_roles or IMAGE_ROLES,
        "media_mode": "gif" if motion_selected else "static",
        "requires_application_bot": bool((spec.get("media_contract") or {}).get("requires_application_bot")) if isinstance(spec.get("media_contract"), dict) else False,
        "media_manifest_command": "python3 scripts/media_assets.py --input <asset> --output <bundle>/<name>.media-manifest.json",
    }
    decision_log = analysis.setdefault("decision_log", [])
    if isinstance(decision_log, list):
        decision_log.append({
            "decision": "applied",
            "component": "information_allocation",
            "reason": "先由规则判断媒体/原生 Card/按钮的职责；静态用 Seedream 5.0 Pro，动态价值足够时自动用 Seedance 2.5 GIF；原生 Card 保留精简摘要、关键事实与图表，完整原文留在 source.txt",
        })
        decision_log.append({
            "decision": "applied" if motion_selected else "not_selected",
            "component": "automatic_motion_routing",
            "reason": "; ".join(str(item) for item in motion_spec.get("reasons", [])),
            "score": motion_spec.get("score"),
            "threshold": motion_spec.get("threshold"),
        })

    if image_requested and spec.get("timeline_first"):
        spec["timeline_first"] = False
        if isinstance(decision_log, list):
            decision_log.append({
                "decision": "applied",
                "component": "image_first_order",
                "reason": "豆包工作 图片优先版将首图放在时间线前；时间线仍保留完整事实顺序",
            })
    if explicit_no_image:
        _degrade_to_no_image(spec)
    elif not image_requested:
        _degrade_to_no_image(spec, reason="设计计划选择无图；原生 Card 保留精简摘要和真实行动，完整事实仍在 source.txt")
    elif hero_img_key:
        _set_image_key(spec, hero_img_key)

    plan = analysis.get("design_plan")
    if not isinstance(plan, dict):
        raise ValueError("auto layout did not return analysis.design_plan")
    plan_media = plan.get("media_policy")
    if isinstance(plan_media, dict):
        plan_media.update({
            "motion_mode": "gif" if motion_selected else "static",
            "motion_auto_selected": motion_selected and force_motion is None,
            "motion_generation_mode": motion_generation_mode,
            "final_asset": final_asset_path.name if image_requested else None,
            "generation_tool": generation_tool if image_requested else None,
            "generation_model": generation_model if image_requested else None,
            "generation_model_label": generation_model_label if image_requested else None,
        })
    # The planner selects a hero only when a visual relationship or explicit
    # media request is useful. The asset is still separately gated by a real
    # uploaded img_key.
    component_strategy = plan.get("component_strategy")
    if isinstance(component_strategy, list) and image_requested:
        for component in component_strategy:
            if isinstance(component, dict) and component.get("component") == "hero":
                component["selected"] = True
                component["status"] = "applied"
                component["reason"] = "豆包工作 默认首图策略已写入 spec；等待内置生图和真实 img_key"
                break
    _promote_quote_block(spec)
    _refresh_functional_text_contract(spec)
    visual_contract = spec.get("visual_contract") if isinstance(spec.get("visual_contract"), dict) else {}
    if isinstance(analysis.get("doubao_mode"), dict):
        analysis["doubao_mode"]["image_text_layout"] = visual_contract.get("image_text_layout") or image_generation_mode
        analysis["doubao_mode"]["image_generation_mode"] = image_generation_mode
        analysis["doubao_mode"]["media_generation_mode"] = active_generation_mode
    hero = spec.get("hero") if isinstance(spec.get("hero"), dict) else {}
    media_contract = spec.get("media_contract") if isinstance(spec.get("media_contract"), dict) else {}
    image_source = str(hero.get("image_source") or media_contract.get("image_source") or "ai_generated") if image_requested else "none"
    if image_source not in {"real_image", "ai_generated"}:
        image_source = "ai_generated" if image_requested else "none"
    image_roles = hero.get("image_roles") if isinstance(hero.get("image_roles"), list) else media_contract.get("image_roles")
    image_roles = [str(item) for item in image_roles if str(item).strip()] if isinstance(image_roles, list) else []
    if image_requested and not image_roles:
        image_roles = list(selected_roles or IMAGE_ROLES)
    motion_selected = motion_selected and image_source == "ai_generated"
    seedream_required = image_requested and image_source == "ai_generated" and not motion_selected
    seedance_required = image_requested and image_source == "ai_generated" and motion_selected
    ai_generation_required = seedream_required or seedance_required
    analysis_doubao_mode = analysis.get("doubao_mode")
    if isinstance(analysis_doubao_mode, dict):
        analysis_doubao_mode.update({
            "image_source": image_source,
            "image_roles": image_roles,
            "ai_generation_required": ai_generation_required,
            "generation_model": generation_model,
            "generation_model_label": generation_model_label,
            "generation_tool": generation_tool,
            "generation_family": generation_family,
        })
    _write_text(image_prompt_path, _image_prompt(spec, brand_context=brand_context))
    _write_text(motion_prompt_path, build_motion_prompt(motion_spec))
    seedream_generation = _ai_generation_gate(
        bundle / "hero.png",
        image_generation_manifest_path,
        required=seedream_required,
        generation_mode=image_generation_mode if image_requested else DIRECT_SEEDREAM_MODE,
    )
    seedream_output = _direct_seedream_visual_status(
        bundle / "hero.png",
        required=seedream_required,
        generation=seedream_generation,
        mode=image_generation_mode if image_requested else DIRECT_SEEDREAM_MODE,
    )
    seedance_generation = _motion_generation_gate(
        bundle / "hero.gif",
        motion_generation_manifest_path,
        required=seedance_required,
        generation_mode=motion_generation_mode if motion_selected else DIRECT_SEEDANCE_GIF_MODE,
    )
    seedance_output = {
        "required": seedance_required,
        "mode": motion_generation_mode if motion_selected else "none",
        "path": str(bundle / "hero.gif"),
        "ready": bool(seedance_generation.get("ready")),
        "status": "seedance_gif_ready_for_visual_review" if seedance_generation.get("ready") else seedance_generation.get("status"),
        "post_processing": "none",
        "manual_visual_review_required": seedance_required,
    }
    ai_generation = seedance_generation if motion_selected else seedream_generation
    _write_json(plan_path, plan)
    _write_json(prompt_routing_path, spec.get("prompt_routing", {}))
    _write_json(visual_spec_path, spec.get("visual_spec", {}))
    _write_json(motion_spec_path, motion_spec)

    card, compile_report, validation = _compile_once(
        spec,
        card_path=card_path,
        spec_path=spec_path,
        style_path=style_path,
        brand_context=brand_context,
    )

    # Some inferred lifecycle scenes have required fields that a short copy
    # does not provide. A safe custom-card fallback keeps the source and all
    # visible facts while avoiding a false claim of scene completeness.
    scene_contract = compile_report.get("scene_contract")
    if isinstance(scene_contract, dict) and not scene_contract.get("ok", False):
        missing = [str(item) for item in scene_contract.get("missing_fields", [])]
        previous_scene = spec.get("scene")
        spec["scene"] = None
        spec["type"] = "custom"
        plan["scene"] = "custom"
        if isinstance(decision_log, list):
            decision_log.append({
                "decision": "degraded",
                "component": "scene",
                "reason": f"{previous_scene} 缺少场景契约字段 {', '.join(missing)}；已降级为 custom",
            })
        analysis["route_fallback"] = {
            "from_scene": previous_scene,
            "to_scene": "custom",
            "missing_fields": missing,
            "policy": "preserve_source_and_report_degradation",
        }
        _write_json(plan_path, plan)
        card, compile_report, validation = _compile_once(
            spec,
            card_path=card_path,
            spec_path=spec_path,
            style_path=style_path,
            brand_context=brand_context,
        )
        scene_contract = compile_report.get("scene_contract")

    route_contract = spec.get("route_contract")
    if isinstance(route_contract, dict):
        route_contract["final_scene"] = spec.get("scene")
        route_contract["fallback"] = analysis.get("route_fallback") if isinstance(analysis, dict) else None

    # CardKit's browser importer expects an editable envelope, while the
    # existing raw .card remains the API/Bot payload.  Generate both from the
    # final compiled card so the web file cannot drift from what is previewed.
    cardkit_bundle = write_cardkit_bundle(
        card_path,
        bundle,
        card_name=str(spec.get("title") or safe_name),
        base_name=safe_name,
    )
    cardkit_card_path = Path(cardkit_bundle["cardkit_card"])
    cardkit_json_path = Path(cardkit_bundle["cardkit_json"])
    cardkit_validation = cardkit_bundle.get("validation") if isinstance(cardkit_bundle.get("validation"), dict) else {}
    cardkit_valid = bool(cardkit_validation.get("ok"))

    scene_contract_ok = scene_contract is None or bool(scene_contract.get("ok"))
    image_required = image_requested
    image_key_ready = image_required and bool(hero_img_key) and not bool(compile_report.get("asset_plan"))
    ai_generation_ready = not ai_generation_required or bool(ai_generation.get("ready"))
    seedream_output_ready = not seedream_required or bool(seedream_output.get("ready"))
    seedance_output_ready = not seedance_required or bool(seedance_output.get("ready"))
    visual_output_ready = not image_requested or (ai_generation_ready and seedream_output_ready and seedance_output_ready)
    card_image_embedded = image_required and _contains_tag(card, {"img"})
    image_ready = image_key_ready and visual_output_ready and card_image_embedded
    valid = bool(validation.get("ok")) and scene_contract_ok and not contains_placeholder(card)
    sendable = bool(compile_report.get("sendable")) and bool(validation.get("ok")) and scene_contract_ok
    needs_media = image_required and not image_ready
    image_gate_clear = not image_required or image_ready
    cardkit_max_bytes = CARDKIT_MAX_BYTES
    cardkit_file_size_bytes = cardkit_card_path.stat().st_size
    cardkit_size_ok = cardkit_file_size_bytes <= cardkit_max_bytes
    cardkit_editor_blockers: list[str] = []
    if not valid:
        cardkit_editor_blockers.append("card validation must pass before CardKit delivery")
    if not cardkit_valid:
        cardkit_editor_blockers.append("CardKit wrapper validation must pass before CardKit delivery")
    if not image_gate_clear:
        if not visual_output_ready:
            cardkit_editor_blockers.append(
                f"the selected {generation_model_label} final {'GIF' if motion_selected else 'image'} is required before CardKit delivery"
            )
        if not ai_generation_ready:
            cardkit_editor_blockers.append(f"{generation_model_label} final asset and provenance manifest are required")
        if not image_key_ready:
            cardkit_editor_blockers.append("real Feishu img_key for the final image is required before CardKit delivery")
    if not cardkit_size_ok:
        cardkit_editor_blockers.append(f"CardKit wrapper file exceeds the 300 KB limit ({cardkit_file_size_bytes} bytes)")
    blockers = list(validation.get("errors", []))
    if not scene_contract_ok:
        blockers.append("scene contract is not satisfied")
    if needs_media:
        if not visual_output_ready:
            blockers.append(f"the selected {generation_model_label} final asset is required for the media-led card")
        if not ai_generation_ready:
            blockers.append(f"{generation_model_label} generation is required before the selected final asset can be accepted")
        if not image_key_ready:
            blockers.append("real img_key upload is required for the default visual card")
    if not sendable and not needs_media:
        blockers.append("compiled card is not sendable")

    final_image_path = final_asset_path
    if not image_required:
        image_contract_status = "not_required"
    elif card_image_embedded and image_ready:
        image_contract_status = "embedded_seedance_gif" if motion_selected else "embedded_seedream_image"
    elif visual_output_ready and not card_image_embedded:
        image_contract_status = "visual_output_ready_waiting_real_img_key"
    elif final_image_path.is_file() and not visual_output_ready:
        image_contract_status = "visual_output_blocked"
    else:
        image_contract_status = "seedance_gif_required" if motion_selected else "seedream_image_required"
    card_image_contract = {
        "status": image_contract_status,
        "image_generation_mode": image_generation_mode,
        "media_generation_mode": active_generation_mode,
        "media_kind": "gif" if motion_selected else "image",
        "motion_auto_selected": motion_selected and force_motion is None,
        "post_processing": "none",
        "image_text_layout": (
            visual_contract.get("image_text_layout")
            or (media_policy.get("image_text_layout") if isinstance(media_policy, Mapping) else None)
            or DIRECT_SEEDREAM_MODE
        ),
        "image_source": image_source,
        "image_roles": image_roles,
        "final_asset": str(final_image_path),
        "final_asset_role": (
            "seedance_gif_plus_native_card_components"
            if motion_selected
            else (
                "seedream_banner_plus_native_card_components"
                if image_generation_mode == BANNER_SEEDREAM_MODE
                else "seedream_information_visual_plus_native_card_components"
            )
        ),
        "final_asset_exists": final_image_path.is_file(),
        "final_asset_contains_functional_text": visual_output_ready,
        "manual_visual_review_required": bool(image_requested),
        "card_image_embedded": card_image_embedded,
        "real_img_key_supplied": bool(hero_img_key and image_required),
        "ai_generation_required": ai_generation_required,
        "ai_generation_manifest": str(generation_manifest_path) if ai_generation_required else None,
    }

    quality_gates = build_quality_gates(
        card,
        spec,
        validation,
        wrapper=cardkit_bundle.get("wrapper") if isinstance(cardkit_bundle, Mapping) else None,
        cardkit_valid=cardkit_valid,
        scene_contract_ok=scene_contract_ok,
        image_required=image_required,
        visual_output_ready=visual_output_ready,
        image_ready=image_ready,
    )
    generation_workflow = build_generation_workflow(
        quality_gates,
        validation_ok=bool(validation.get("ok")),
        scene_contract_ok=scene_contract_ok,
        image_required=image_required,
        visual_output_ready=visual_output_ready,
        image_ready=image_ready,
        cardkit_valid=cardkit_valid,
    )
    spec["quality_gates"] = quality_gates
    spec["generation_workflow"] = generation_workflow
    analysis["quality_gates"] = quality_gates
    analysis["generation_workflow"] = generation_workflow
    _write_json(spec_path, spec)
    if not bool(quality_gates.get("structural_passed", quality_gates.get("required_passed"))):
        valid = False
        sendable = False
        structural_failures = ", ".join(str(item) for item in quality_gates.get("structural_failures", []))
        blockers.append(f"Card Studio structural quality gates failed: {structural_failures or 'unknown'}")
        cardkit_editor_blockers.append("Card Studio structural quality gates must pass before remote delivery")

    cardkit_name = str(spec.get("title") or safe_name)
    cardkit_adapter_dry_run = (
        f"python3 scripts/feishu_cli.py push-cardkit --card {shlex.quote(str(card_path))} "
        f"--name {shlex.quote(cardkit_name)} --dry-run"
    )
    cardkit_adapter_confirmed = (
        f"python3 scripts/feishu_cli.py push-cardkit --card {shlex.quote(str(card_path))} "
        f"--name {shlex.quote(cardkit_name)} --confirm --record {shlex.quote(str(cardkit_result_path))}"
    )
    cardkit_cli_dry_run = (
        f"bytedcli -j feishu cardkit template import --file {shlex.quote(str(card_path))} "
        f"--name {shlex.quote(cardkit_name)} --dry-run"
    )
    delivery_workflow = {
        "name": "cardkit_direct_import",
        "mode": "cardkit_first",
        "single_preflight": True,
        "single_confirmation_gate": True,
        "order": [
            "validate_raw_card_and_cardkit_wrapper",
            "check_cardkit_session_and_delivery_target",
            "upload_image_and_recompile_if_needed",
            "import_cardkit_directly",
            "verify_cardkit_template_get_and_list",
            "optionally_preview_card_via_feishu_cli",
        ],
        "surfaces": {
            "cardkit_import": "bytedcli_web_backed_template_import_or_logged_in_browser_ui",
            "bot_preview": "optional_feishu_cli_application_bot",
        },
        "raw_card": str(card_path),
        "cardkit_wrapper": str(cardkit_card_path),
        "preview_record": str(preview_record_path),
        "cardkit_result": str(cardkit_result_path),
        "preview_optional": True,
        "direct_import_command": cardkit_adapter_confirmed,
        "direct_import_dry_run_command": cardkit_adapter_dry_run,
        "preview_command": (
            f"python3 scripts/feishu_cli.py preview-card --card {shlex.quote(str(card_path))} "
            f"--as bot --confirm --record {shlex.quote(str(preview_record_path))}"
        ),
        "browser_import": (
            "CardKit CLI 不可用时，在已登录 https://open.larkoffice.com/cardkit 的浏览器中，使用可见‘导入卡片’→‘新建卡片’→上传 "
            f"{shlex.quote(str(cardkit_card_path))} →填写精确 card_name→开始导入→按名称打开编辑页"
        ),
        "cardkit_import": {
            "preferred": "bytedcli_web_backed_template_import",
            "adapter": "scripts/feishu_cli.py push-cardkit",
            "input": str(card_path),
            "input_dialect": "raw_card_2_0_json",
            "dry_run_command": cardkit_cli_dry_run,
            "adapter_dry_run_command": cardkit_adapter_dry_run,
            "requires": [
                "bytedcli -j auth status",
                "Feishu CardKit web session (ByteCloud auth alone is insufficient)",
            ],
            "remote_write_after_confirmation": True,
            "response_evidence": ["template_id", "template get readback", "template list match"],
            "fallback": "logged_in_browser_ui_with_cardkit_wrapper",
            "fallback_input": str(cardkit_card_path),
            "runtime_card_id_is_not_template_id": True,
        },
        "success_evidence": [
            "CardKit CLI 路径：响应含 template_id，且 template get 成功、template list 命中同一模板",
            "浏览器路径：我的卡片列表出现完全匹配的 card_name，且可以进入编辑页",
            "如用户明确要求 Bot 预览，再额外记录 preview_record.status=preview_sent 和 message_id",
        ],
        "partial_states": [
            "cardkit_import_pending",
            "cardkit_imported_bot_preview_pending",
            "bot_preview_pending_optional",
        ],
        "api_entity_note": "create-cardkit API Card Entity 不能替代 CardKit 模板导入；只有用户明确要求 API Entity 时才调用",
    }

    status = "blocked" if not valid else (
        "needs_gif" if needs_media and motion_selected else ("needs_image" if needs_media else "ready")
    )
    report: Dict[str, Any] = {
        "status": status,
        "workflow_profile": workflow_profile,
        "stability_contract": stability_contract,
        "card": str(card_path),
        "editable_spec": str(spec_path),
        "report": str(report_path),
        "source": str(source_path),
        "style": str(style_path),
        "image_prompt": str(image_prompt_path),
        "visual_spec": str(visual_spec_path),
        "motion_prompt": str(motion_prompt_path),
        "motion_spec": str(motion_spec_path),
        "motion_selection": motion_spec,
        "ai_generation": ai_generation,
        "prompt_routing_file": str(prompt_routing_path),
        "input_brief": input_brief,
        "information_allocation": spec.get("information_allocation", {}),
        "plan": str(plan_path),
        "validation": validation,
        "quality_gates": quality_gates,
        "generation_workflow": generation_workflow,
        "compile": compile_report,
        "delivery_workflow": delivery_workflow,
        "cardkit_bundle": {
            key: value for key, value in cardkit_bundle.items() if key != "wrapper"
        },
        "cardkit_raw_card": str(card_path),
        "cardkit_import_file": str(cardkit_card_path),
        "scene_contract": scene_contract,
        "detected_urls": detected_urls,
        "button_intake": {
            "status": "ready" if any(item.get("button_eligible") for item in detected_urls) else "ask_before_generation_when_not_already_confirmed",
            "question": "是否需要补充按钮？如需要，请描述按钮功能或提供真实链接。",
            "policy": "没有真实 URL 或已实现 callback/form 时不生成按钮",
        },
        "proposals_file": str(proposals_path),
        "proposals": proposals,
        "media": {
            "mode": "gif" if motion_selected else "static",
            "motion_auto_selected": motion_selected and force_motion is None,
            "motion_reasons": motion_spec.get("reasons"),
            "media_generation_mode": active_generation_mode,
            "image_generation_mode": image_generation_mode,
            "image_source": image_source,
            "image_roles": image_roles,
            "generation_family": generation_family if image_source == "ai_generated" else None,
            "generation_tool": generation_tool if image_source == "ai_generated" else None,
            "generation_model": generation_model if image_source == "ai_generated" else None,
            "generation_model_label": generation_model_label if image_source == "ai_generated" else None,
            "model_id_source": runtime.get("model_id_source") if image_source == "ai_generated" else None,
            "reference_image_tool": runtime.get("reference_image_tool") if image_source == "ai_generated" else None,
            "requires_application_bot": bool((spec.get("media_contract") or {}).get("requires_application_bot")) if isinstance(spec.get("media_contract"), dict) else False,
            "static_first_frame_required": False if motion_selected else bool((spec.get("media_contract") or {}).get("static_first_frame_required")) if isinstance(spec.get("media_contract"), dict) else False,
            "essential_text_outside_animation": True,
            "final_asset": str(final_image_path),
            "manifest_path": str(bundle / f"{safe_name}.media-manifest.json"),
            "manifest_status": "not_run",
        },
        "prompt_routing": spec.get("prompt_routing") if isinstance(spec.get("prompt_routing"), dict) else None,
        "information_allocation": spec.get("information_allocation", {}),
        "doubao": {
            "input_brief": input_brief,
            "quality_gates": quality_gates,
            "generation_workflow": generation_workflow,
            "media_mode": "built_in_seedance_direct_gif_then_lark_cli_upload" if motion_selected else "built_in_seedream_image_then_lark_cli_upload",
            "generation_tool": generation_tool,
            "generation_family": generation_family,
            "generation_model": generation_model,
            "generation_model_label": generation_model_label,
            "model_id_source": runtime.get("model_id_source"),
            "runtime_profile": str((ROOT / "presets" / "runtime-profile.json").relative_to(ROOT)),
            "image_generation_mode": image_generation_mode,
            "motion_generation_mode": motion_generation_mode,
            "motion_auto_selected": motion_selected and force_motion is None,
            "seedream_required": seedream_required,
            "seedance_required": seedance_required,
            "visual_output_ready": visual_output_ready,
            "image_required": image_required,
            "image_ready": image_ready,
            "seedream_output_ready": seedream_output_ready,
            "seedance_output_ready": seedance_output_ready,
            "seedream_output": seedream_output,
            "seedance_output": seedance_output,
            "ai_generation_required": ai_generation_required,
            "image_source": image_source,
            "image_roles": image_roles,
            "ai_generation_ready": ai_generation_ready,
            "ai_generation_manifest": str(generation_manifest_path),
            "hero_img_key_supplied": bool(hero_img_key and image_required),
            "card_image_contract": card_image_contract,
            "delivery_workflow": delivery_workflow,
            "remote_writes": "disabled_by_default",
            "cardkit_editor_url": "https://open.larkoffice.com/cardkit",
            "cardkit_editor_import_mode": "bytedcli_web_backed_or_browser_ui_direct",
            "html_preview": "optional_debug_only",
            "cardkit_file_size_bytes": cardkit_file_size_bytes,
            "cardkit_file_size_ok": cardkit_size_ok,
            "forwardable": True,
        },
        "delivery_options": {
            "cardkit_import": {
                "description": "直接导入 CardKit 模板并回读 template_id/list/get（默认交付路径）",
                "command": cardkit_adapter_confirmed,
                "dry_run_command": cardkit_adapter_dry_run,
                "cli_dry_run": cardkit_cli_dry_run,
                "browser_fallback": f"在已登录 https://open.larkoffice.com/cardkit 的浏览器中导入 {shlex.quote(str(cardkit_card_path))}",
                "requires_confirmation": True,
                "requires_cardkit_session": True,
                "success_evidence": ["template_id", "template get", "template list 命中同一模板"],
            },
            "bot_preview": {
                "description": "可选：用应用 Bot 预览 Card 2.0；不作为 CardKit 导入前置条件",
                "command": f"python3 scripts/feishu_cli.py preview-card --card {shlex.quote(str(card_path))} --as bot --confirm --record {shlex.quote(str(preview_record_path))}",
                "dry_run_command": f"python3 scripts/feishu_cli.py preview-card --card {shlex.quote(str(card_path))} --as bot --dry-run",
                "requires_bot": True,
                "optional": True,
                "required_for_cardkit": False,
            },
            "screenshot_preview": {
                "description": "已降级为可选本地调试预览，不属于默认交付",
                "command": f"python3 scripts/preview_card.py --spec {shlex.quote(str(spec_path))} --output {shlex.quote(str(card_path))}",
                "requires_bot": False,
                "enabled": False,
                "optional": True,
                "not_part_of_delivery": True,
            },
        },
        "readiness": {
            "valid": valid,
            "image_ready": image_ready,
            "seedream_output_ready": seedream_output_ready,
            "seedance_output_ready": seedance_output_ready,
            "visual_output_ready": visual_output_ready,
            "sendable": sendable and image_gate_clear,
            "cardkit_entity_ready": valid and sendable and image_gate_clear,
            "cardkit_editor_ready": valid and cardkit_valid and image_gate_clear and cardkit_size_ok,
            "blockers": list(dict.fromkeys(blockers)),
            "cardkit_editor_blockers": cardkit_editor_blockers,
        },
        "next_steps": {
            "generate_media": (
                f"强制下一步（{status} 不是成品）：读取 {shlex.quote(str(motion_spec_path))} 与 {shlex.quote(str(motion_prompt_path))}，通过豆包工作内置 Seedance 2.5 工具直接生成循环 GIF 并保存为 {shlex.quote(str(bundle / 'hero.gif'))}；禁止本地视频转 GIF、按钮、CTA、伪交互和编造信息"
                if motion_selected
                else f"强制下一步（{status} 不是成品）：读取 {shlex.quote(str(visual_spec_path))} 与 {shlex.quote(str(image_prompt_path))}，通过豆包工作内置 Seedream 5.0 Pro 一次性生成 {('横幅首图' if image_generation_mode == BANNER_SEEDREAM_MODE else '竖版信息图')}并保存为 {shlex.quote(str(bundle / 'hero.png'))}；只使用来源白名单文字"
            ),
            "register_generated_media": (
                f"python3 scripts/register_motion_generation.py --asset {shlex.quote(str(bundle / 'hero.gif'))} --prompt {shlex.quote(str(motion_prompt_path))} --output {shlex.quote(str(motion_generation_manifest_path))} --generation-mode {shlex.quote(motion_generation_mode)}"
                if motion_selected
                else f"python3 scripts/register_image_generation.py --image {shlex.quote(str(bundle / 'hero.png'))} --prompt {shlex.quote(str(image_prompt_path))} --output {shlex.quote(str(image_generation_manifest_path))} --generation-family {shlex.quote(generation_family)} --generation-mode {shlex.quote(image_generation_mode if image_requested else DIRECT_SEEDREAM_MODE)} --text-policy {shlex.quote(str(_mode_config(image_generation_mode if image_requested else DIRECT_SEEDREAM_MODE).get('text_policy') or DIRECT_SEEDREAM_TEXT_MODE))}"
            ),
            "inspect_media": f"python3 scripts/media_assets.py --input <asset> --output {shlex.quote(str(bundle / f'{safe_name}.media-manifest.json'))}",
            "inspect_prompt_routing": f"python3 scripts/prompt_router.py --text-file {shlex.quote(str(source_path))}",
            "view_proposals": f"查看三版布局方案：{shlex.quote(str(proposals_path))}；选择后用 --layout banner-led、--layout infographic-led 或 --layout text-led 重跑",
            "upload_image": f"python3 scripts/feishu_cli.py upload-image --image {shlex.quote(str(final_image_path))} --as bot --dry-run",
            "recompile_with_key": f"python3 scripts/doubao_pipeline.py --text-file {shlex.quote(str(source_path))} --output-dir {shlex.quote(str(output_dir))} --name {shlex.quote(safe_name)} --hero-img-key <real_img_key>",
            "push_cardkit": cardkit_adapter_dry_run,
            "create_cardkit": f"python3 scripts/feishu_cli.py create-cardkit --card {shlex.quote(str(card_path))} --as bot --dry-run",
            "import_to_cardkit_cli": (
                f"bytedcli -j feishu cardkit template import --file {shlex.quote(str(card_path))} "
                f"--name {shlex.quote(str(spec.get('title') or safe_name))} --dry-run"
            ),
            "preview_bot": f"python3 scripts/feishu_cli.py preview-card --card {shlex.quote(str(card_path))} --as bot --dry-run",
            "import_to_cardkit_editor": f"使用已登录浏览器打开 https://open.larkoffice.com/cardkit，在‘导入卡片’中选择‘新建卡片’，上传 {shlex.quote(str(cardkit_card_path))}，填写卡片名称并点击‘开始导入’；再按名称打开编辑页验收",
            "deliver_cardkit": (
                "一次确认后直接执行 CardKit 导入：必要时 upload-image 并用真实 img_key 重新编译；执行 "
                f"{cardkit_adapter_confirmed}，回读 template_id、template get 和 template list。"
                "只有 CLI 会话不可用时才切换到已登录浏览器导入同源 .cardkit.card wrapper。"
            ),
            "deliver_preview_and_cardkit": (
                "兼容别名：一次确认后先直接导入 CardKit 并回读模板证据；如用户同时明确要求 Bot 预览，再执行 "
                f"python3 scripts/feishu_cli.py preview-card --card {shlex.quote(str(card_path))} --as bot --confirm --record {shlex.quote(str(preview_record_path))}"
            ),
            "preview": f"仅在明确要求本地调试时使用：python3 scripts/preview_card.py --spec {shlex.quote(str(spec_path))} --output {shlex.quote(str(card_path))}",
        },
    }
    cardkit_manifest = {
        "status": "ready_for_cardkit_import" if valid and cardkit_valid and image_gate_clear and cardkit_size_ok else "blocked",
        "workflow_profile": workflow_profile,
        "stability_contract": stability_contract,
        "mode": "cardkit_direct",
        "execution": "bytedcli_web_backed_or_browser_ui",
        "editor_url": "https://open.larkoffice.com/cardkit",
        "card": str(cardkit_card_path),
        "api_card": str(card_path),
        "cardkit_json": str(cardkit_json_path),
        "card_name": str(spec.get("title") or safe_name),
        "input_brief": input_brief,
        "visual_spec": str(visual_spec_path),
        "motion_spec": str(motion_spec_path),
        "motion_prompt": str(motion_prompt_path),
        "motion_selection": motion_spec,
        "quality_gates": quality_gates,
        "generation_workflow": generation_workflow,
        "image_source": image_source,
        "image_roles": image_roles,
        "seedream_output": seedream_output,
        "seedance_output": seedance_output,
        "ai_generation": ai_generation,
        "ai_generation_ready": ai_generation_ready,
        "seedream_output_ready": seedream_output_ready,
        "seedance_output_ready": seedance_output_ready,
        "visual_output_ready": visual_output_ready,
        "final_visual_asset": str(final_image_path),
        "file_size_bytes": cardkit_file_size_bytes,
        "max_file_size_bytes": cardkit_max_bytes,
        "size_ok": cardkit_size_ok,
        "wrapper_validation": cardkit_validation,
        "wrapper_fixes": cardkit_bundle.get("fixes", []),
        "delivery_workflow": delivery_workflow,
        "automation": {
            "preflight": [
                "一次性检查 raw .card、CardKit wrapper、卡片名称、图片/真实 img_key 门禁和 CardKit 会话",
                f"执行 {cardkit_adapter_dry_run}",
                "只有用户明确要求 Bot 预览时，才额外检查应用 Bot 和本人目标",
            ],
            "confirmation": "single_confirmation_gate_for_all_remote_writes",
            "execution_order": [
                "直接用 Byte CLI Web-backed CardKit template import 导入 raw .card",
                "回读 template_id、template get 和 template list；若 CLI 会话不可用，改用已登录浏览器导入 .cardkit.card wrapper",
                "仅在用户明确要求时，用应用 Bot 发送可转发预览并回读 message_id",
            ],
            "cardkit_cli": delivery_workflow["cardkit_import"],
            "cardkit_cli_optional": delivery_workflow["cardkit_import"],
            "visible_steps": [
                "点击‘导入卡片’",
                "保持‘新建卡片’，选择本 manifest 的 CardKit 包装 .card 文件",
                "填写 card_name；分组仅在用户指定时选择",
                "点击‘开始导入’",
                "回到‘我的卡片’，按 card_name 打开编辑页",
            ],
            "success_evidence": [
                "CLI 路径：响应含 template_id，且 template list/get 回读同一模板",
                "浏览器路径：我的卡片列表出现完全匹配的 card_name，且可以进入编辑页",
            ],
        },
        "verification": {
            "required": [
                "one_of: cardkit_template_id_and_list_get | my_cards_name_visible_and_editor_page_openable",
            ],
            "content_checks": ["功能性信息视觉（标题/日期/阶段动作）", "图片或 GIF 内的主要关系", "quote（如有）", "按钮（如有）", "GIF/图集/切换器的 provenance 与媒体 manifest（如有）"],
        },
        "blockers": cardkit_editor_blockers,
        "bot_preview_command": f"python3 scripts/feishu_cli.py preview-card --card {shlex.quote(str(card_path))} --as bot --dry-run",
        "cardkit_cli_dry_run_command": delivery_workflow["cardkit_import"]["dry_run_command"],
        "note": "默认直接导入 CardKit：raw .card 供 Byte CLI 模板导入，CLI 不可用时使用同源 .cardkit.card wrapper 网页导入；HTML 仅保留为可选本地调试，Bot 预览仅在用户明确要求时执行。lark-cli Card Entity 不能替代模板导入。图片内文字和排版来自 Seedream 5.0 Pro 整图直出；图片禁止按钮、CTA 和伪交互，改文案后必须重新调用 Seedream 5.0 Pro 并重新上传。",
    }
    _write_json(cardkit_manifest_path, cardkit_manifest)
    report["cardkit_editor_import"] = str(cardkit_manifest_path)
    _write_json(report_path, report)
    return report


def _console_summary(report: Mapping[str, Any]) -> Dict[str, Any]:
    readiness = report.get("readiness") if isinstance(report.get("readiness"), Mapping) else {}
    return {
        "status": report.get("status"),
        "card": report.get("card"),
        "editable_spec": report.get("editable_spec"),
        "image_prompt": report.get("image_prompt"),
        "visual_spec": report.get("visual_spec"),
        "motion_prompt": report.get("motion_prompt"),
        "motion_spec": report.get("motion_spec"),
        "motion_selection": report.get("motion_selection"),
        "report": report.get("report"),
        "detected_urls": report.get("detected_urls"),
        "proposals_file": report.get("proposals_file"),
        "proposals": report.get("proposals"),
        "delivery_options": report.get("delivery_options"),
        "cardkit_editor_import": report.get("cardkit_editor_import"),
        "input_brief": report.get("input_brief"),
        "quality_gates": report.get("quality_gates"),
        "generation_workflow": report.get("generation_workflow"),
        "delivery_workflow": report.get("delivery_workflow"),
        "validation_ok": bool((report.get("validation") or {}).get("ok")) if isinstance(report.get("validation"), Mapping) else False,
        "readiness": readiness,
    }


def _load_design_plan(path_value: Optional[str]) -> Optional[Mapping[str, Any]]:
    if not path_value:
        return None
    raw = json.loads(Path(path_value).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("design plan JSON must be an object")
    value = raw.get("design_plan", raw.get("planning", raw))
    if not isinstance(value, dict):
        raise ValueError("design plan must be an object")
    return value


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="豆包工作 image-led Feishu Card 2.0 pipeline")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="card copy")
    source.add_argument("--text-file", help="UTF-8 card copy file")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--name", default="card")
    parser.add_argument("--brand-context", default="")
    parser.add_argument("--brand-context-file")
    parser.add_argument("--scene")
    parser.add_argument("--preset")
    parser.add_argument("--design-plan", help="JSON file containing design_plan overrides")
    parser.add_argument("--hero-img-key", help="real img_key returned by Feishu image upload")
    parser.add_argument("--no-image", action="store_true", help="explicitly degrade to a sendable no-image fallback")
    parser.add_argument(
        "--motion",
        choices=("auto", "on", "off"),
        default="auto",
        help="automatically choose Seedance 2.5 GIF, or explicitly force/disable motion",
    )
    parser.add_argument("--emoji-mode", choices=("auto", "aliases", "semantic", "off"), default="semantic", help="default adds 3–6 restrained structural Emoji; use off to disable")
    parser.add_argument("--link-mode", choices=("button", "inline"), default="button")
    parser.add_argument("--purpose", help="optional purpose/context for layout and QA; does not alter source facts")
    parser.add_argument("--recipient", help="optional recipient context; not a remote delivery target")
    parser.add_argument(
        "--material-kind",
        choices=("plain_text", "document_extract", "table_extract", "reference_image", "card_json"),
        default="plain_text",
        help="kind of canonical material supplied to the pipeline",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="only write and print the three local layout proposals; do not generate or deliver a card",
    )
    parser.add_argument(
        "--layout",
        choices=("banner-led", "infographic-led", "text-led"),
        help="select one local layout proposal without an interactive step",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        text = args.text if args.text is not None else Path(args.text_file).read_text(encoding="utf-8")
        brand_context = args.brand_context
        if args.brand_context_file:
            brand_context = Path(args.brand_context_file).read_text(encoding="utf-8")
        design_plan = _load_design_plan(args.design_plan)
        if args.layout:
            chosen = next((item for item in LAYOUT_PROPOSALS if item.get("id") == args.layout), None)
            if chosen is None:
                raise ValueError(f"unknown layout: {args.layout}")
            layout_override = {"media_policy": {
                "image_generation_mode": chosen["image_mode"],
                "need_hero": True,
                "information_carrier": True,
                "not_decorative": True,
            }}
            design_plan = _deep_merge(design_plan or {}, layout_override)
        if args.propose:
            output_dir = _resolve_output_dir(args.output_dir)
            safe_name = _safe_name(args.name)
            bundle = output_dir / safe_name
            bundle.mkdir(parents=True, exist_ok=True)
            source_path = bundle / f"{safe_name}.source.txt"
            proposals_path = bundle / f"{safe_name}.proposals.json"
            _write_text(source_path, text)
            spec = build_auto_spec(
                text,
                requested_scene=args.scene,
                requested_preset=args.preset,
                design_plan=_deep_merge(DEFAULT_DESIGN_PLAN, design_plan),
                emoji_mode=args.emoji_mode,
                link_mode=args.link_mode,
            )
            detected_urls = _detect_urls(text)
            proposals = _generate_proposals(text, spec)
            payload = {
                "proposals": proposals,
                "detected_urls": detected_urls,
                "proposals_file": str(proposals_path),
            }
            _write_json(
                proposals_path,
                {"proposals": proposals, "detected_urls": detected_urls, "source": str(source_path)},
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        report = run_pipeline(
            text,
            _resolve_output_dir(args.output_dir),
            name=args.name,
            brand_context=brand_context,
            hero_img_key=args.hero_img_key,
            requested_scene=args.scene,
            requested_preset=args.preset,
            design_plan=design_plan,
            no_image=args.no_image,
            force_motion=None if args.motion == "auto" else args.motion == "on",
            emoji_mode=args.emoji_mode,
            link_mode=args.link_mode,
            purpose=args.purpose,
            recipient=args.recipient,
            material_kind=args.material_kind,
        )
        print(json.dumps(_console_summary(report), ensure_ascii=False, indent=2))
        return 0 if report["status"] != "blocked" else 2
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"doubao_pipeline.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
