"""Legacy compatibility for the retired HTML-to-image route.

The production workflow now uses direct Seedream output (or a supplied
``real_image``). This module only migrates old specs and fails stale callers;
it never writes, renders, or accepts HTML imagery.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional


HTML_RENDER_STRATEGY = "html_infographic_to_png"
NATIVE_MODEL_STRATEGY = "native_model"
HTML_TEXT_POLICY = "html_route_removed"


def html_source_is_safe(html_path: Path) -> bool:
    """HTML is no longer a valid image source."""
    return False


def current_render_strategy(spec: Mapping[str, Any]) -> str:
    """Read a persisted route and migrate historical HTML values to native."""
    hero = spec.get("hero") if isinstance(spec.get("hero"), Mapping) else {}
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), Mapping) else {}
    design = analysis.get("design_plan") if isinstance(analysis, Mapping) else {}
    media = design.get("media_policy") if isinstance(design, Mapping) else {}
    for value in (spec.get("render_strategy"), hero.get("render_strategy"), media.get("render_strategy")):
        value = str(value or "").strip().lower()
        if value in {HTML_RENDER_STRATEGY, "html_to_png", "html"}:
            return NATIVE_MODEL_STRATEGY
        if value in {NATIVE_MODEL_STRATEGY, "model", "native", "image_model"}:
            return NATIVE_MODEL_STRATEGY
    return ""


def choose_render_strategy(
    spec: Dict[str, Any],
    *,
    explicit_strategy: Optional[str] = None,
    allow_auto: bool = True,
) -> str:
    """Always select direct model output and migrate legacy HTML requests."""
    hero = spec.get("hero")
    if not isinstance(hero, dict):
        return "none"
    requested = str(explicit_strategy or "").strip().lower()
    legacy = requested in {HTML_RENDER_STRATEGY, "html_to_png", "html"}
    strategy = NATIVE_MODEL_STRATEGY
    reason = "HTML→PNG 路径已移除，历史请求已迁移为模型直出" if legacy else "统一使用宿主图片模型直出；文字密度由原生 Card 高亮块承载"
    analysis = spec.setdefault("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
        spec["analysis"] = analysis
    design = analysis.setdefault("design_plan", {})
    if not isinstance(design, dict):
        design = {}
        analysis["design_plan"] = design
    media = design.setdefault("media_policy", {})
    if not isinstance(media, dict):
        media = {}
        design["media_policy"] = media
    contract = spec.setdefault("visual_contract", {})
    if not isinstance(contract, dict):
        contract = {}
        spec["visual_contract"] = contract
    spec["render_strategy"] = strategy
    hero["render_strategy"] = strategy
    media["render_strategy"] = strategy
    contract["render_strategy"] = strategy
    allocation = spec.get("information_allocation")
    if isinstance(allocation, dict):
        image = allocation.setdefault("image", {})
        if isinstance(image, dict):
            image["render_strategy"] = strategy
            image["render_reason"] = reason
    decision_log = analysis.setdefault("decision_log", [])
    if isinstance(decision_log, list):
        decision_log.append({
            "decision": "applied",
            "component": "visual_render_strategy",
            "selected": strategy,
            "reason": reason,
            "model_first": True,
            "html_to_png_removed": True,
        })
    return strategy


def build_html_artifact(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Fail closed so no caller can recreate the removed HTML artifact."""
    raise RuntimeError("HTML→PNG 信息图路径已移除，请使用 Seedream 5.0 Pro 直出图片")


def html_render_gate(
    image_path: Path,
    manifest_path: Path,
    html_path: Path,
    *,
    required: bool,
) -> Dict[str, Any]:
    """Expose a migration error for historical callers."""
    return {
        "required": required,
        "manifest": str(manifest_path),
        "image": str(image_path),
        "html": str(html_path),
        "ready": False,
        "render_strategy": HTML_RENDER_STRATEGY,
        "status": "html_route_removed",
        "error": "HTML→PNG 信息图路径已移除，请使用 Seedream 5.0 Pro 直出图片",
    }
