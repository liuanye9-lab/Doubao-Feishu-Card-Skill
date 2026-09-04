#!/usr/bin/env python3
"""Source-locked automatic motion routing for Doubao Work Feishu cards."""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional


EXPLICIT_MOTION_RE = re.compile(r"动图|GIF|动画|动态|视频|演示动画|motion|animated", re.I)
NO_MOTION_RE = re.compile(r"(?:不要|不需要|无需|不用|去掉|取消)\s*(?:视频|动图|GIF|动画|动态)|\bno[- ]?motion\b", re.I)
TIMELINE_RE = re.compile(r"时间线|阶段|第[一二三四五六七八九十\d]+步|\d{1,2}月\d{1,2}日|\d{1,2}[./-]\d{1,2}")
PROCESS_RE = re.compile(r"流程|步骤|闭环|路径|操作|教程|指引|巡检|处理链路|工作流")
TRANSITION_RE = re.compile(r"前后对比|从.+到|变化|演进|升级|转化|流转|状态切换|进度")
STATIC_ONLY_RE = re.compile(r"(?:仅|只)(?:展示|保留)?\s*(?:数据|指标|表格|名单|公告|结果)|静态(?:卡片|图片)")


def _sequence_count(source: str) -> int:
    numbered = len(re.findall(r"(?:^|\n)\s*(?:\d+[.、)]|第[一二三四五六七八九十\d]+步)", source))
    arrows = len(re.findall(r"→|->|=>", source))
    dated = len(re.findall(r"(?:^|\n)[^\n]{0,18}(?:\d{1,2}月\d{1,2}日|\d{1,2}[./-]\d{1,2})", source))
    return max(numbered, arrows + 1 if arrows else 0, dated)


def build_motion_spec(
    source: str,
    *,
    title: str = "",
    visual_spec: Optional[Mapping[str, Any]] = None,
    image_required: bool = True,
    force_motion: Optional[bool] = None,
) -> Dict[str, Any]:
    """Choose Seedance only when motion adds explanatory value."""
    text = str(source or "")
    reasons: list[str] = []
    score = 0
    sequence_count = _sequence_count(text)
    nodes = list((visual_spec or {}).get("relationship_nodes") or [])

    explicit_no_motion = bool(NO_MOTION_RE.search(text))
    explicit_motion = bool(EXPLICIT_MOTION_RE.search(text)) and not explicit_no_motion
    if explicit_motion:
        score += 8
        reasons.append("source explicitly requests motion")
    if sequence_count >= 3 or TIMELINE_RE.search(text):
        score += 3
        reasons.append("timeline or multi-stage sequence")
    if PROCESS_RE.search(text) and (sequence_count >= 2 or len(nodes) >= 3):
        score += 3
        reasons.append("multi-step process benefits from animated progression")
    if TRANSITION_RE.search(text):
        score += 3
        reasons.append("before-after or state transition")
    if len(nodes) >= 4:
        score += 2
        reasons.append("source-backed relationship nodes can animate in order")
    if STATIC_ONLY_RE.search(text):
        score -= 4
        reasons.append("source emphasizes static information")

    selected = bool(image_required and score >= 4)
    if force_motion is not None:
        selected = bool(force_motion and image_required)
        reasons.append("caller explicitly selected motion" if force_motion else "caller explicitly selected static media")
    if explicit_no_motion:
        selected = False
        reasons = ["source explicitly disables motion"]
    if not image_required:
        selected = False
        reasons = ["visual media is disabled"]

    selected_nodes = [
        {"label": str(node.get("label") or ""), "text": str(node.get("text") or ""), "source_line": node.get("source_line")}
        for node in nodes[:5]
        if isinstance(node, Mapping)
    ]
    return {
        "schema": "doubao-feishu-card-motion-spec/1",
        "source_locked": True,
        "auto_selected": force_motion is None,
        "selected": selected,
        "score": score,
        "threshold": 4,
        "reasons": reasons or ["static information visual is clearer"],
        "title": title,
        "generation_mode": "seedance_2_5_direct_gif" if selected else "static_seedream",
        "generation_tool": "doubao.video_gen" if selected else "doubao.image_gen",
        "generation_model": "seedance-2.5" if selected else "seedream-5.0-pro",
        "generation_model_label": "Seedance 2.5" if selected else "Seedream 5.0 Pro",
        "target_asset": "hero.gif" if selected else "hero.png",
        "output_format": "gif" if selected else "png",
        "sequence_count": sequence_count,
        "relationship_nodes": selected_nodes,
        "duration_seconds": 6 if selected else 0,
        "loop": bool(selected),
        "essential_facts_policy": "native Card must preserve every essential fact; GIF may not be the only carrier",
        "no_invention": "animate only source-backed objects, labels, order, and values",
        "no_local_conversion": "request GIF directly from Seedance 2.5; do not convert video to GIF locally",
    }


def build_motion_prompt(spec: Mapping[str, Any]) -> str:
    """Build a compact host-facing prompt from the editable motion spec."""
    nodes = [
        f"- {item.get('label')}: {item.get('text')}"
        for item in spec.get("relationship_nodes", [])
        if isinstance(item, Mapping) and (item.get("label") or item.get("text"))
    ]
    facts = "\n".join(nodes) if nodes else "- Use only the source-backed visual relationships in the paired visual spec."
    return "\n".join([
        "# Seedance 2.5 GIF task",
        "",
        f"Title: {spec.get('title') or 'Feishu information card'}",
        "Output: directly generate a seamless looping GIF, portrait 2:3, about 6 seconds.",
        "Purpose: explain progression, state change, or operation rhythm for a Feishu CardKit card.",
        "",
        "Source-backed sequence:",
        facts,
        "",
        "Constraints:",
        "- Use Seedance 2.5 through Doubao Work's built-in video/motion tool.",
        "- Return GIF directly; do not return MP4 for local conversion.",
        "- Keep motion calm, legible, mobile-safe, and loopable.",
        "- Do not invent numbers, dates, steps, people, outcomes, URLs, logos, or UI states.",
        "- Do not draw buttons, CTA pills, forms, fake links, or interactive controls.",
        "- Essential facts, charts, and actions remain native CardKit components.",
    ]) + "\n"
