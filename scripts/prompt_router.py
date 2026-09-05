#!/usr/bin/env python3
"""Route ordinary card copy to prebuilt Seedream 5.0 Pro and interaction prompts.

The router is deterministic and local. It never changes source facts. It
selects small, maintained prompt fragments from ``presets/prompt-presets.json``
so a user can simply mention a timeline, training course, GIF, gallery, or
image switcher in normal copy; the main pipeline then injects the full source
copy as a fact-checking reference alongside the selected image-text whitelist in one Seedream 5.0 Pro generation prompt.

It also records the default upstream method pass: when the environment exposes
Guizang Social Card Skill or baoyu-skills, try to call/read them before selecting
the local visual capability pack. If they are unavailable, the local mapping is
the transparent fallback. The default bitmap provider remains 豆包工作's built-in
Seedream 5.0 Pro path. The main pipeline may select a controlled, self-contained
HTML→PNG fallback for dense structured infographics; it never invokes an
upstream compositor or alternate image model.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from runtime_profile import default_image_mode, image_runtime, supported_image_modes


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "presets" / "prompt-presets.json"
VISUAL_SKILL_REGISTRY_PATH = ROOT / "presets" / "visual-skill-packs.json"
MEDIA_MODES = {"static", "gallery", "gif", "switcher"}
REFERENCE_TEMPLATES = {
    "case-study": "case-showcase",
    "metrics-dashboard": "case-showcase",
    "screenshot-explainer": "course-recap",
    "training": "course-schedule",
    "timeline": "training-notice",
    "general-information": "training-notice",
}
REFERENCE_IMAGE_LAYOUTS = {
    "case-showcase": "reference_card_banner",
    "course-schedule": "reference_card_banner",
    "training-notice": "reference_card_banner",
    "course-recap": "reference_card_banner",
}
SCENE_CONTENT_PROFILES = {
    "case-showcase": "case-study",
    "event-recap": "metrics-dashboard",
    "training-notice": "training",
    "activity-timeline": "timeline",
}
EXPLICIT_TIMELINE_IMAGE_RE = re.compile(
    r"(?:时间轴|时间线)\s*(?:图片|图|信息图|海报)|(?:把|将).{0,8}(?:时间轴|时间线).{0,8}(?:画|生成|放进).{0,8}(?:图片|图)",
    re.I,
)
NEGATION_RE = re.compile(
    r"(?:不需要|不必|不要|无需|无须|不用|不做|禁止|别|without|no|not)\s*$",
    re.I,
)


def load_prompt_registry() -> Dict[str, Any]:
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"prompt preset registry is unavailable: {REGISTRY_PATH}") from exc
    if not isinstance(registry, dict) or not isinstance(registry.get("profiles"), list):
        raise ValueError("prompt preset registry must contain a profiles array")
    return registry


def load_visual_skill_registry() -> Dict[str, Any]:
    """Load the local upstream-method translation registry."""
    try:
        registry = json.loads(VISUAL_SKILL_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"visual skill pack registry is unavailable: {VISUAL_SKILL_REGISTRY_PATH}") from exc
    if not isinstance(registry, dict) or not isinstance(registry.get("packs"), list):
        raise ValueError("visual skill pack registry must contain a packs array")
    if not isinstance(registry.get("selection_rules"), list):
        raise ValueError("visual skill pack registry must contain selection_rules")
    return registry


def _trigger_matches(text: str, trigger: str) -> List[str]:
    """Return non-negated occurrences of one trigger phrase."""
    if not trigger.strip():
        return []
    flags = re.I if re.search(r"[A-Za-z]", trigger) else 0
    matches: List[str] = []
    for match in re.finditer(re.escape(trigger), text, flags):
        prefix = text[max(0, match.start() - 12) : match.start()]
        if NEGATION_RE.search(prefix):
            continue
        matches.append(match.group(0))
    return matches


def _profile_match(text: str, profile: Mapping[str, Any], index: int) -> Optional[Dict[str, Any]]:
    triggers = profile.get("triggers") if isinstance(profile.get("triggers"), list) else []
    matched_terms: List[str] = []
    score = 0
    for raw_trigger in triggers:
        trigger = str(raw_trigger).strip()
        hits = _trigger_matches(text, trigger)
        if not hits:
            continue
        matched_terms.append(trigger)
        # Longer phrases are more informative than single-character hits;
        # repeated mentions add a little confidence but never dominate.
        score += (2 if len(trigger) > 1 else 1) * min(len(hits), 2)
    if not matched_terms:
        return None
    return {
        "id": str(profile.get("id") or f"profile_{index}"),
        "kind": str(profile.get("kind") or "content"),
        "label": str(profile.get("label") or profile.get("id") or "预制提示词"),
        "priority": int(profile.get("priority", 0) or 0),
        "score": score,
        "matched_terms": matched_terms,
        "layout_id": profile.get("layout_id"),
        "mode": profile.get("mode"),
        "prompt": str(profile.get("prompt") or "").strip(),
        "negative": str(profile.get("negative") or "").strip(),
        "auto_actions": [str(item) for item in profile.get("auto_actions", []) if str(item).strip()]
        if isinstance(profile.get("auto_actions"), list)
        else [],
        "_index": index,
    }


def _materialize_profile(
    profile: Mapping[str, Any],
    index: int,
    *,
    matched_terms: Optional[Sequence[str]] = None,
    score: int = 0,
) -> Dict[str, Any]:
    """Create a profile record for a deterministic auto-selection."""
    return {
        "id": str(profile.get("id") or f"profile_{index}"),
        "kind": str(profile.get("kind") or "content"),
        "label": str(profile.get("label") or profile.get("id") or "预制提示词"),
        "priority": int(profile.get("priority", 0) or 0),
        "score": int(score),
        "matched_terms": [str(item) for item in (matched_terms or []) if str(item).strip()],
        "layout_id": profile.get("layout_id"),
        "mode": profile.get("mode"),
        "prompt": str(profile.get("prompt") or "").strip(),
        "negative": str(profile.get("negative") or "").strip(),
        "auto_actions": [str(item) for item in profile.get("auto_actions", []) if str(item).strip()]
        if isinstance(profile.get("auto_actions"), list)
        else [],
        "_index": index,
    }


def _sort_key(item: Mapping[str, Any]) -> Tuple[int, int, int]:
    # Profile priority expresses semantic specificity (timeline beats generic
    # training when both are present); score breaks ties within a category.
    return (int(item.get("priority", 0)), int(item.get("score", 0)), -int(item.get("_index", 0)))


def _rule_matches(
    rule: Mapping[str, Any],
    content_ids: set[str],
    media_mode: str,
) -> bool:
    required = {str(item) for item in rule.get("when_content_all", []) if str(item).strip()}
    any_content = {str(item) for item in rule.get("when_content_any", []) if str(item).strip()}
    any_media = {str(item) for item in rule.get("when_media_any", []) if str(item).strip()}
    excluded_media = {str(item) for item in rule.get("when_media_not", []) if str(item).strip()}
    if required and not required.issubset(content_ids):
        return False
    if any_content and not (any_content & content_ids):
        return False
    if any_media and media_mode not in any_media:
        return False
    if media_mode in excluded_media:
        return False
    return True


def route_visual_skill_packs(
    text: str,
    *,
    content_ids: Sequence[str],
    media_mode: str = "static",
    explicit_style_profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Route upstream visual methods into a reproducible local prompt contract.

    Content structure is selected first. Guizang Social Card Skill and
    baoyu-skills are the default upstream method pass when available; the
    local registry is the transparent fallback. An explicit local style
    profile only overrides visual language and never discards source-backed
    structure.
    """
    registry = load_visual_skill_registry()
    normalized_content = {str(item) for item in content_ids if str(item).strip()}
    packs = [item for item in registry.get("packs", []) if isinstance(item, dict)]
    packs_by_id = {str(item.get("id")): item for item in packs if str(item.get("id") or "").strip()}
    rules = [item for item in registry.get("selection_rules", []) if isinstance(item, dict)]
    matching_rules = [item for item in rules if _rule_matches(item, normalized_content, media_mode)]
    # A case/metrics relationship is more specific than a generic training
    # hit.  Keep the forced case route from inheriting a course visual merely
    # because the source mentions onboarding or learning.
    if media_mode == "gallery":
        rule = next((item for item in matching_rules if item.get("id") == "static-series-gallery"), None)
    elif normalized_content & {"case-study", "metrics-dashboard"}:
        rule = next((item for item in matching_rules if item.get("id") == "case-metrics-evidence"), None)
    else:
        rule = matching_rules[0] if matching_rules else None
    if rule is None:
        raise ValueError("visual skill pack registry has no matching selection rule")

    explicit_style = None
    style_map = registry.get("style_profile_map", {})
    if not isinstance(style_map, dict):
        style_map = {}
    if explicit_style_profile_id:
        for local_style_id, mapping in style_map.items():
            if isinstance(mapping, dict) and mapping.get("prompt_profile_id") == explicit_style_profile_id:
                explicit_style = (str(local_style_id), mapping)
                break

    selected_style_id = str((explicit_style[0] if explicit_style else rule.get("style_id")) or "clean-editorial")
    style_mapping = style_map.get(selected_style_id) if isinstance(style_map.get(selected_style_id), dict) else {}
    prompt_profile_id = str(
        (explicit_style[1].get("prompt_profile_id") if explicit_style else rule.get("prompt_profile_id"))
        or style_mapping.get("prompt_profile_id")
        or "clean-editorial-style"
    )
    base_pack_ids = [str(item) for item in rule.get("pack_ids", []) if str(item).strip()]
    if not base_pack_ids:
        base_pack_ids = [str(item) for item in style_mapping.get("pack_ids", []) if str(item).strip()]
    selected_pack_ids: List[str] = []
    for pack_id in base_pack_ids:
        if pack_id in packs_by_id and pack_id not in selected_pack_ids:
            selected_pack_ids.append(pack_id)
    max_packs = int(registry.get("policy", {}).get("max_selected_packs", 2) or 2)
    selected_pack_ids = selected_pack_ids[:max_packs]
    selected_pack_records = [packs_by_id[pack_id] for pack_id in selected_pack_ids]

    source_summaries = []
    visual_prompt_fragments: List[str] = []
    visual_negative_fragments: List[str] = []
    for pack in selected_pack_records:
        source = pack.get("source") if isinstance(pack.get("source"), dict) else {}
        references = source.get("references") if isinstance(source.get("references"), list) else []
        source_summaries.append({
            "id": str(pack.get("id")),
            "label": str(pack.get("label") or pack.get("id")),
            "repository": source.get("repository"),
            "skill": source.get("skill") or (references[0] if references else None),
            "role": pack.get("role"),
        })
        if str(pack.get("prompt") or "").strip():
            visual_prompt_fragments.append(str(pack["prompt"]).strip())
        if str(pack.get("negative") or "").strip():
            visual_negative_fragments.append(str(pack["negative"]).strip())

    automatic = explicit_style is None
    reason = str(rule.get("selection_reason") or "按内容关系选择本地视觉能力包")
    if explicit_style:
        reason = f"用户显式选择 {explicit_style[0]}；保留“{rule.get('id', '内容规则')}”的结构能力，只覆盖视觉语言。"
    runtime = dict(registry.get("runtime", {})) if isinstance(registry.get("runtime"), Mapping) else {}
    runtime_profile = image_runtime()
    runtime.update({
        "provider": runtime_profile.get("provider", runtime.get("provider", "doubao.image_gen")),
        "generation_tool": runtime_profile.get("generation_tool", "doubao.image_gen"),
        "generation_family": runtime_profile.get("generation_family", "seedream-class"),
        "generation_model": runtime_profile.get("generation_model", "seedream-5.0-pro"),
        "generation_model_label": runtime_profile.get("generation_model_label", "Seedream 5.0 Pro"),
        "generation_mode": runtime_profile.get("default_mode", "seedream_5_pro_direct_full_card"),
        "supported_generation_modes": list(supported_image_modes()),
    })
    return {
        "router": "doubao-feishu-visual-skill-router/1",
        "registry": str(VISUAL_SKILL_REGISTRY_PATH.relative_to(ROOT)),
        "selection_rule": str(rule.get("id") or "unknown"),
        "selected_packs": selected_pack_ids,
        "selected_pack_labels": [str(item.get("label") or item.get("id")) for item in selected_pack_records],
        "source_packs": source_summaries,
        "style_id": selected_style_id,
        "prompt_profile_id": prompt_profile_id,
        "visual_layout": str(rule.get("visual_layout") or "single-information-anchor"),
        "auto_selected": automatic,
        "style_auto_selected": automatic,
        "style_selection_reason": reason,
        "visual_prompt_fragments": visual_prompt_fragments,
        "visual_negative_prompt": "; ".join(visual_negative_fragments),
        "runtime": runtime,
        "upstream_method_pass": registry.get("upstream_method_pass", {}),
        "source_locked": bool(registry.get("runtime", {}).get("source_locked", True)),
        "auto_actions": [
            "默认先调用或读取 Guizang Social Card Skill 与 baoyu-skills 的可用方法",
            "上游 Skill 不可调用时使用本地等价映射，并在路由记录降级",
            "默认实际位图仍由 豆包工作 内置 Seedream 5.0 Pro 一次生成",
            "仅文字密集结构化信息图可由主 pipeline 选择自包含 HTML → PNG fallback",
            "不执行上游 HTML/CSS/SVG/Canvas/Pillow 渲染器或 alternate provider",
            "图片不绘制按钮、CTA 控件或伪交互；真实行为只在原生 Card",
        ],
        "selection_reason": reason,
    }


def route_prompt_presets(
    text: str,
    *,
    media_mode: Optional[str] = None,
    scene: Optional[str] = None,
) -> Dict[str, Any]:
    """Select a compact prompt recipe from ordinary card copy."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text cannot be empty")
    if media_mode is not None and media_mode not in MEDIA_MODES:
        raise ValueError(f"media_mode must be one of {sorted(MEDIA_MODES)}")

    registry = load_prompt_registry()
    runtime_profile = image_runtime()
    profiles = [item for item in registry["profiles"] if isinstance(item, dict)]
    matches: List[Dict[str, Any]] = []
    for index, profile in enumerate(profiles):
        found = _profile_match(text, profile, index)
        if found:
            matches.append(found)

    content_matches = sorted((item for item in matches if item["kind"] == "content"), key=_sort_key, reverse=True)
    anchor_matches = sorted((item for item in matches if item["kind"] == "anchor"), key=_sort_key, reverse=True)
    media_matches = sorted((item for item in matches if item["kind"] == "media"), key=_sort_key, reverse=True)
    style_matches = sorted((item for item in matches if item["kind"] == "style"), key=_sort_key, reverse=True)

    max_content = int(registry.get("policy", {}).get("max_content_profiles", 2) or 2)
    max_anchor = int(registry.get("policy", {}).get("max_anchor_profiles", 1) or 1)
    max_style = int(registry.get("policy", {}).get("max_style_profiles", 1) or 1)
    max_media = int(registry.get("policy", {}).get("max_media_profiles", 1) or 1)
    forced_profile_id = SCENE_CONTENT_PROFILES.get(str(scene or "").strip())
    forced_profile = next((item for item in content_matches if item.get("id") == forced_profile_id), None) if forced_profile_id else None
    if forced_profile is None and forced_profile_id:
        forced_definition = next((item for item in profiles if item.get("id") == forced_profile_id), None)
        if forced_definition is not None:
            forced_profile = _materialize_profile(
                forced_definition,
                profiles.index(forced_definition),
                matched_terms=[f"scene:{scene}"],
            )
    if forced_profile is not None:
        selected_content = [forced_profile]
        selected_content.extend(
            item for item in content_matches
            if item.get("id") != forced_profile.get("id")
        )
        selected_content = selected_content[:max_content]
    else:
        selected_content = content_matches[:max_content]
    if not selected_content:
        default_id = str(registry.get("default_profile") or "general-information")
        default_profile = next((item for item in profiles if item.get("id") == default_id), None)
        if default_profile is None:
            raise ValueError(f"default prompt profile is missing: {default_id}")
        selected_content = [_materialize_profile(default_profile, profiles.index(default_profile))]
    selected_anchors = anchor_matches[:max_anchor]

    selected_media: List[Dict[str, Any]] = []
    if media_mode and media_mode != "static":
        forced = next((item for item in media_matches if item.get("mode") == media_mode), None)
        if forced is None:
            forced_profile = next((item for item in profiles if item.get("kind") == "media" and item.get("mode") == media_mode), None)
            if forced_profile is not None:
                forced = {
                    "id": str(forced_profile.get("id") or "media_profile"),
                    "kind": "media",
                    "label": str(forced_profile.get("label") or forced_profile.get("id") or "媒体提示词"),
                    "priority": int(forced_profile.get("priority", 0) or 0),
                    "score": 0,
                    "matched_terms": [],
                    "layout_id": forced_profile.get("layout_id"),
                    "mode": forced_profile.get("mode"),
                    "prompt": str(forced_profile.get("prompt") or "").strip(),
                    "negative": str(forced_profile.get("negative") or "").strip(),
                    "auto_actions": [str(item) for item in forced_profile.get("auto_actions", []) if str(item).strip()]
                    if isinstance(forced_profile.get("auto_actions"), list)
                    else [],
                    "_index": profiles.index(forced_profile),
                }
        if forced:
            forced["matched_terms"] = [f"media_mode:{media_mode}"] + list(forced.get("matched_terms", []))
            forced["score"] = max(int(forced.get("score", 0)), 1)
            selected_media = [forced]
    elif media_matches:
        selected_media = media_matches[:max_media]

    content_ids = {str(item.get("id")) for item in selected_content}
    actual_media_mode = media_mode or (selected_media[0].get("mode") if selected_media else "static")
    visual_skill_routing = route_visual_skill_packs(
        text,
        content_ids=sorted(content_ids),
        media_mode=actual_media_mode,
        explicit_style_profile_id=style_matches[0]["id"] if style_matches else None,
    )
    selected_styles = style_matches[:max_style]
    if not selected_styles:
        auto_style_id = str(visual_skill_routing.get("prompt_profile_id") or "")
        auto_style_profile = next((item for item in profiles if item.get("id") == auto_style_id), None)
        if auto_style_profile is not None:
            selected_styles = [_materialize_profile(
                auto_style_profile,
                profiles.index(auto_style_profile),
                matched_terms=[f"auto:{visual_skill_routing.get('style_id', 'clean-editorial')}"],
            )]
    selected = selected_content + selected_anchors + selected_media + selected_styles
    selected_ids = [str(item["id"]) for item in selected]
    prompt_fragments = [item["prompt"] for item in selected if item.get("prompt")]
    negative_fragments = []
    auto_actions: List[str] = []
    for item in selected:
        negative = str(item.get("negative") or "").strip()
        if negative and negative not in negative_fragments:
            negative_fragments.append(negative)
        for action in item.get("auto_actions", []):
            if action not in auto_actions:
                auto_actions.append(action)
    for action in visual_skill_routing.get("auto_actions", []):
        if action not in auto_actions:
            auto_actions.append(action)

    primary_content = selected_content[0]
    primary = selected[0] if selected else primary_content
    style_profile = selected_styles[0] if selected_styles else None
    if "case-study" in content_ids or "metrics-dashboard" in content_ids:
        reference_template = "case-showcase"
    elif "screenshot-explainer" in content_ids:
        reference_template = "course-recap"
    elif "training" in content_ids and "timeline" in content_ids:
        reference_template = "training-notice"
    else:
        reference_template = REFERENCE_TEMPLATES.get(str(primary_content.get("id")), "training-notice")
    # Keep the semantic visual layout for recipe selection; the stable
    # pipeline may explicitly choose the full-card or banner Seedream 5.0 Pro mode.
    image_layout = (
        "timeline_infographic_inside_illustration"
        if EXPLICIT_TIMELINE_IMAGE_RE.search(text)
        else REFERENCE_IMAGE_LAYOUTS.get(reference_template, "reference_card_banner")
    )
    matched_profiles = [
        {key: value for key, value in item.items() if key != "_index"}
        for item in sorted(matches, key=_sort_key, reverse=True)
    ]
    return {
        "router": "doubao-feishu-prompt-router/1",
        "registry": str(REGISTRY_PATH.relative_to(ROOT)),
        "media_mode": media_mode or (selected_media[0].get("mode") if selected_media else "static"),
        "primary_profile": primary["id"],
        "primary_content_profile": primary_content["id"],
        "style_profile": style_profile["id"] if style_profile else None,
        "layout_id": primary_content.get("layout_id"),
        "reference_template": reference_template,
        "image_layout": image_layout,
        "selected_profiles": selected_ids,
        "matched_profiles": matched_profiles,
        "visual_skill_routing": visual_skill_routing,
        "prompt_fragments": prompt_fragments,
        "visual_prompt_fragments": visual_skill_routing.get("visual_prompt_fragments", []),
        "negative_prompt": "; ".join(negative_fragments),
        "visual_negative_prompt": visual_skill_routing.get("visual_negative_prompt", ""),
        "upstream_method_pass": visual_skill_routing.get("upstream_method_pass", {}),
        "auto_actions": auto_actions,
        "trigger_summary": "、".join(str(item["label"]) for item in selected if item.get("label")),
        "source_locked": True,
        "image_generation_mode": str(runtime_profile.get("default_mode") or default_image_mode()),
        "supported_image_generation_modes": list(supported_image_modes()),
        "text_policy": str(registry.get("policy", {}).get("text_policy") or "seedream_5_pro_direct_selected_text_and_layout"),
        "image_source_types": list(registry.get("policy", {}).get("image_source_types") or ["real_image", "ai_generated"]),
        "generation_tool": str(runtime_profile.get("generation_tool") or runtime_profile.get("provider") or "doubao.image_gen"),
        "generation_family": str(runtime_profile.get("generation_family") or registry.get("policy", {}).get("ai_generation_family") or "seedream-class"),
        "generation_model": str(runtime_profile.get("generation_model") or "seedream-5.0-pro"),
        "generation_model_label": str(runtime_profile.get("generation_model_label") or "Seedream 5.0 Pro"),
        "model_id_source": runtime_profile.get("model_id_source"),
        "image_roles": list(registry.get("policy", {}).get("image_roles") or ["cover", "information_carrier", "text_companion"]),
    }


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route card copy to prebuilt visual prompts")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--text-file", type=Path)
    parser.add_argument("--media-mode", choices=sorted(MEDIA_MODES))
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        text = args.text if args.text is not None else args.text_file.read_text(encoding="utf-8")
        result = route_prompt_presets(text, media_mode=args.media_mode)
        payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"prompt_router.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
