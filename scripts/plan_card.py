#!/usr/bin/env python3
"""Deterministic content-to-Card-2.0 design planner.

The planner is deliberately pure Python and side-effect free.  It recommends
media and components, but never claims that an image, callback backend, or
remote CardKit artifact already exists.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from content_intelligence import analyze_content
from prompt_router import route_prompt_presets
from summary_extraction import classify_content, extract_structured_sections
from visual_spec import build_chart_plan, extract_metrics

URL_RE = re.compile(r"(?:https?://|lark://|feishu://)[^\s<>\"'“”‘’]+", re.I)
DATE_RE = re.compile(
    r"(?:20\d{2}[年./-])?\d{1,2}(?:月|[./-])\d{1,2}(?:日|号)?|"
    r"\d{1,2}月(?:初|上旬|中旬|下旬|底)|"
    r"(?<![\dA-Za-z])(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?![\dA-Za-z])|"
    r"(?:周[一二三四五六日天]|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
    re.I,
)
NUMBER_RE = re.compile(r"(?<![\w])(?:\d+(?:\.\d+)?%?|\d+(?:\.\d+)?(?:万|亿|倍|人|项|次|天|小时|h|k|m))(?![\w])", re.I)
METRIC_LINE_RE = re.compile(r"^\s*([^：:|｜\t]{1,14})\s*[：:]\s*([+-]?\d+(?:\.\d+)?(?:%|万|亿|倍|人|项|次|天|小时|分钟|min|h|k|m)?)\s*$", re.I)
LIST_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)、])\s+")
STEP_MARKER_RE = re.compile(r"^\s*(?:第\s*[一二三四五六七八九十]+\s*步|步骤\s*\d+|step\s*\d+|\d+\s*[.)、])\s*", re.I)
HEADING_RE = re.compile(r"^\s*(?:#{1,4}\s+|【[^】]{1,30}】\s*$)")
IMAGE_MARKER_RE = re.compile(r"!\[[^]]*]\([^)]+\)|\bimg_[A-Za-z0-9_-]+\b", re.I)

WARNING_WORDS = ("截止", "最后", "务必", "必须", "紧急", "重要", "风险", "警告", "逾期", "deadline", "urgent", "warning", "must")
HIGHLIGHT_TITLE_RE = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?:核心价值|一句话价值|为什么值得看|关键结论|结论|重点|亮点|结果(?:/价值)?|注意|提醒|风险|当前阶段|下一步|行动建议)\s*(?:[：:]|$)",
    re.I,
)
VISUAL_WORDS = ("案例", "作品", "展示", "画廊", "海报", "品牌", "视觉", "产品", "设计", "摄影", "氛围", "showcase", "portfolio", "gallery", "brand", "visual", "product")
STEP_WORDS = ("步骤", "流程", "阶段", "节点", "日程", "第一步", "第二步", "step", "phase", "timeline", "schedule")
COMPARE_WORDS = ("对比", "同比", "环比", "差异", "vs", "versus", "before", "after", "compare")
CTA_WORDS = ("报名", "提交", "查看", "打开", "下载", "领取", "申请", "预约", "确认", "参与", "register", "submit", "view", "download", "apply", "join")
TRAINING_WORDS = ("培训", "课程", "学习", "讲师", "作业", "training", "course", "workshop")
RECAP_WORDS = ("复盘", "总结", "数据", "指标", "增长", "转化", "同比", "环比", "recap", "report", "metrics")
MEDIA_SWITCH_WORDS = ("轮播", "图片切换", "切换图片", "图集切换", "上一张", "下一张", "carousel", "image switch", "image-switcher")
MOTION_WORDS = ("动图", "GIF", "动画", "动态底图", "animated", "motion")
MEDIA_NEGATION_RE = re.compile(r"(?:不要|不需要|无需|不用|去掉|取消)\s*(?:生成)?\s*(?:图片|配图|海报|封面|首图|信息图|动图|GIF|动画|轮播|图集|多图)", re.I)

ARCHETYPE_PRESETS = {
    "editorial": "olive-editorial",
    "cinematic": "black-gold-stage",
    "dashboard": "blueprint-blue",
    "alert": "pioneer-red",
    "minimal-luxury": "oriental-ink",
}


def _contains(text: str, words: tuple[str, ...]) -> List[str]:
    lowered = text.lower()
    return [word for word in words if word.lower() in lowered]


def _deep_merge(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _scene(text: str, signals: Dict[str, Any]) -> str:
    lowered = text.lower()
    title = str(signals.get("title", "")).lower()
    training_hits = sum(lowered.count(word.lower()) for word in TRAINING_WORDS)
    if _contains(text, RECAP_WORDS) and signals["metric_count"] >= 2:
        return "event-recap"
    if any(word in title for word in ("培训", "课程", "training", "workshop")):
        return "training-notice"
    if any(word in title for word in ("时间线", "流程", "日程", "timeline", "schedule")) and (signals["date_count"] or signals["step_count"]):
        return "activity-timeline"
    if any(word in title for word in ("提醒", "待办", "截止", "deadline", "reminder")) and signals["date_count"]:
        return "task-reminder"
    if signals["warning_count"] and signals["date_count"]:
        return "task-reminder"
    if training_hits >= 2:
        return "training-notice"
    submission_intent = any(word in title for word in ("征集", "提交", "投稿", "submission")) or any(
        word in lowered for word in ("提交入口", "提交要求", "提交内容", "开放提交", "作品征集", "投稿入口")
    )
    if submission_intent:
        return "submission-call"
    if any(word in lowered for word in ("评审", "评分", "review")):
        return "review-notice"
    if any(word in lowered for word in ("决赛", "路演", "final")):
        return "finals-stage"
    if any(word in lowered for word in ("获奖", "颁奖", "结果公布", "winner")):
        return "result-announcement"
    if any(word in title for word in ("报名", "招募", "register")):
        return "prelaunch-promo"
    if signals["date_count"] >= 2 or signals["step_count"] >= 2:
        return "activity-timeline"
    if _contains(text, VISUAL_WORDS):
        return "case-showcase"
    if any(word in lowered for word in ("报名", "招募", "发布", "开启", "register", "launch")):
        return "prelaunch-promo"
    if signals["date_count"]:
        return "event-info"
    return "custom"


def _component(name: str, priority: int, reason: str, selected: bool = True) -> Dict[str, Any]:
    return {"component": name, "priority": priority, "selected": selected, "reason": reason}


def plan_card(
    text: str,
    override: Optional[Mapping[str, Any]] = None,
    *,
    requested_scene: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a stable, explainable design plan for Chinese or English copy."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text cannot be empty")
    # Keep the exact input for provenance.  BOM cleanup is display-only and
    # must never change the source hash or the human audit record.
    source = text
    display_source = source.replace("\ufeff", "")
    lines = [line.strip() for line in display_source.splitlines() if line.strip()]
    title = lines[0].lstrip("# ").strip() if lines else ""
    body_lines = lines[1:]
    urls = URL_RE.findall(source)
    dates = DATE_RE.findall(source)
    metric_records = extract_metrics(source)
    metrics = [str(item["source_text"]) for item in metric_records]
    chart_plan = build_chart_plan(source, metric_records)
    warning_hits = _contains(source, WARNING_WORDS)
    highlight_lines = [line for line in body_lines if HIGHLIGHT_TITLE_RE.search(line)]
    visual_hits = _contains(source, VISUAL_WORDS)
    step_hits = _contains(source, STEP_WORDS)
    explicit_step_lines = [line for line in body_lines if STEP_MARKER_RE.match(line)]
    compare_hits = _contains(source, COMPARE_WORDS)
    cta_hits = _contains(source, CTA_WORDS)
    image_markers = IMAGE_MARKER_RE.findall(source)
    table_rows = [line for line in body_lines if line.count("|") >= 2 or line.count("\t") >= 2]
    dated_event_lines = [
        line for line in body_lines
        if DATE_RE.search(line)
        and not re.match(r"^\s*(?:时间|日期|活动时间|培训时间|截止时间|报名时间|提交时间)\s*[：:]", line)
        and not any(word.lower() in line.lower() for word in WARNING_WORDS)
    ]
    list_count = sum(bool(LIST_RE.match(line)) for line in body_lines)
    heading_count = sum(bool(HEADING_RE.match(line) or (len(line) <= 28 and line.endswith(("：", ":")))) for line in body_lines)
    paragraph_count = len([part for part in re.split(r"\n\s*\n", source) if part.strip()])
    char_count = len(source.strip())
    signals = {
        "title": title,
        "line_count": len(lines),
        "paragraph_count": paragraph_count,
        "heading_count": heading_count,
        "list_count": list_count,
        "date_count": len(dates),
        "metric_count": len(metrics),
        "url_count": len(urls),
        "cta_count": len(set(cta_hits)),
        "warning_count": len(set(warning_hits)),
        "highlight_signal_count": len(highlight_lines),
        "visual_signal_count": len(set(visual_hits)),
        "step_count": max(len(set(step_hits)), len(explicit_step_lines)),
        "comparison_signal_count": len(set(compare_hits)),
        "table_row_count": len(table_rows),
        "image_marker_count": len(image_markers),
        "character_count": char_count,
        "languages": [lang for lang, present in (("zh", bool(re.search(r"[\u4e00-\u9fff]", source))), ("en", bool(re.search(r"[A-Za-z]", source)))) if present],
    }
    scene = requested_scene or _scene(source, signals)
    content_analysis = analyze_content(source, scene=scene)
    summary_mode = classify_content(source)
    summary_structure = extract_structured_sections(source, summary_mode["mode"])
    signals["content_mode"] = summary_mode["mode"]
    signals["content_mode_confidence"] = summary_mode["confidence"]
    is_long = char_count > 520 or len(lines) > 10
    is_short = char_count <= 180 and len(lines) <= 5
    reliable_table = len(table_rows) >= 2
    visual_showcase = bool(visual_hits) and scene == "case-showcase"
    media_negated = bool(MEDIA_NEGATION_RE.search(source))
    need_gallery = not media_negated and (len(image_markers) >= 2 or sum(word.lower() in source.lower() for word in ("多图", "组图", "系列作品", "gallery", "portfolio")) >= 1)
    need_switcher = not media_negated and any(word.lower() in source.lower() for word in MEDIA_SWITCH_WORDS)
    need_motion = not media_negated and any(word.lower() in source.lower() for word in MOTION_WORDS)
    allocation = content_analysis.get("information_allocation", {})
    allocation_signals = allocation.get("signals", {}) if isinstance(allocation, dict) else {}
    explicit_step_count = int(allocation_signals.get("explicit_step_count", 0) or 0)
    # A single dated event may still deserve a native timeline row; the image
    # allocator remains stricter and only promotes a real sequence/relationship
    # to Seedream 5.0 Pro.
    timeline = len(dates) >= 2 or explicit_step_count >= 2 or bool(dated_event_lines)
    image_recommended = bool(isinstance(allocation, dict) and isinstance(allocation.get("image"), dict) and allocation["image"].get("use"))
    need_hero = (image_recommended or need_switcher or need_motion) and not need_gallery
    button_suggestions = content_analysis.get("button_suggestions", [])
    button_ready = any(isinstance(item, dict) and item.get("button_eligible") and item.get("selected") for item in button_suggestions)
    button_pending = any(isinstance(item, dict) and item.get("surface") == "needs_url_or_callback" for item in button_suggestions)
    prompt_media_mode = "switcher" if need_switcher else "gif" if need_motion else "gallery" if need_gallery else "static"
    # Only an explicit caller request should override keyword-based prompt
    # precedence.  Auto-routed notices keep the historical timeline-vs-
    # training score, while ``--scene case-showcase`` becomes a hard route.
    prompt_recipe = route_prompt_presets(source, media_mode=prompt_media_mode, scene=requested_scene)
    allocation_reason = str(
        allocation.get("image", {}).get("reason")
        if isinstance(allocation, dict) and isinstance(allocation.get("image"), dict)
        else ""
    )

    if warning_hits:
        archetype = "alert"
    elif len(metrics) >= 2 or scene == "event-recap":
        archetype = "dashboard"
    elif visual_showcase and any(word.lower() in source.lower() for word in ("路演", "发布", "舞台", "氛围", "cinematic")):
        archetype = "cinematic"
    elif visual_showcase or is_long:
        archetype = "editorial"
    else:
        archetype = "minimal-luxury"

    components: List[Dict[str, Any]] = []
    if warning_hits:
        components.append(_component("status_tag", 1, "检测到截止/重要/风险词，首屏需要状态锚点"))
    if highlight_lines:
        components.append(_component("highlight", 2, "检测到结论/价值/重点标题；用少量原生色面建立文字层级"))
    if timeline:
        components.append(_component("timeline", 1, "检测到多个日期或阶段信号"))
    elif dates:
        components.append(_component("facts", 2, "仅有少量日期，使用事实块比时间线更紧凑"))
        components.append(_component("timeline", 5, "单一日期不足以形成时间线", False))
    if metrics:
        components.append(_component("metrics", 1 if len(metrics) >= 2 else 2, "检测到短标签与数值指标"))
    if chart_plan:
        components.append(_component("chart", 1, "检测到至少两个同口径真实数值，使用原生 CardKit 图表"))
    if reliable_table:
        components.append(_component("table", 2, "检测到至少两行结构一致的分隔数据"))
    elif compare_hits:
        components.append(_component("section", 2, "存在对比语义，但无法可靠解析表格，降级为纵向 section"))
        components.append(_component("table", 5, "对比数据边界不够可靠", False))
    if need_switcher:
        components.append(_component("media_switcher", 2, "检测到图片切换/轮播意图；使用 application-bot callback 更新当前 img_key，不伪装成客户端原生轮播"))
    elif need_gallery:
        components.append(_component("image_combination", 2, "检测到多图/系列作品信号；Card 2.0 使用多图组合而非轮播"))
    elif need_hero:
        components.append(_component("hero", 2, allocation_reason or "存在适合用图片快速表达的主题关系"))
    components.append(_component("section", 3, "保留原文层级并使用移动端纵向阅读"))
    if is_long:
        components.append(_component("collapsible_panel", 5, "默认不把完整长文放入卡片；全文保留在 source.txt 或真实来源链接", False))
    if button_ready:
        components.append(_component("buttons", 2, "检测到真实 URL 且上下文包含明确下一步；保留一个主按钮和最多一个次按钮"))
    elif button_pending:
        components.append(_component("buttons", 4, "检测到行动语义但没有真实目标；不生成按钮，等待 URL 或 application Bot 回调", False))
    if any(len(line) > 36 for line in metrics):
        components.append(_component("three_columns", 5, "指标文本过长，未使用三列", False))

    explicit_pages = bool(re.search(r"分页|下一页|上一页|第\s*\d+\s*页|page\s*\d+", source, re.I))
    navigation = {
        "mode": "callback_card_update" if explicit_pages else "single_page",
        "requires_backend": explicit_pages,
        "reason": "文本明确要求分页；Card 2.0 无通用原生页面翻转，只能由 callback 更新卡片状态" if explicit_pages else "优先单页阅读；Card 2.0 无通用原生页面翻转或图片轮播",
        "button_budget": "最多一个 primary + 一个 secondary；没有真实 URL 不生成跳转按钮",
    }
    if need_switcher:
        navigation["mode"] = "callback_media_switcher"
        navigation["requires_backend"] = True
        navigation["reason"] = "图片切换不是客户端原生轮播；由 application-bot callback 更新当前图片，首张静态图作为无后端 fallback"
    elif is_long and not explicit_pages:
        navigation["mode"] = "concise_card_plus_source"
        navigation["reason"] = "卡片只保留摘要、3–5 个关键点、指标/图表和 CTA；全文保留在 source.txt，有真实来源链接时用按钮打开"

    density = "low" if is_short else "high" if is_long else "medium"
    focus_mode = (
        "timeline-first" if timeline and len(dates) >= 2 else
        "deadline-first" if warning_hits else
        "action-first" if button_ready else
        "reference-first" if urls else
        "topic-first"
    )
    evidence = []
    for kind, values in (
        ("dates", dates[:6]), ("metrics", metrics[:6]), ("warnings", warning_hits[:6]),
        ("visual_words", visual_hits[:6]), ("steps", (explicit_step_lines or step_hits)[:6]), ("comparisons", compare_hits[:6]),
        ("urls", urls[:6]),
    ):
        if values:
            evidence.append({"signal": kind, "matches": values})
    evidence.append({"signal": "size", "characters": char_count, "lines": len(lines)})

    confidence = 0.52
    confidence += min(0.18, 0.04 * len(evidence))
    confidence += 0.08 if scene != "custom" else 0
    confidence += 0.07 if timeline or metrics or need_hero or reliable_table else 0
    plan: Dict[str, Any] = {
        "planner": "deterministic-baseline-v2",
        "content_shape": signals,
        "scene": scene,
        "content_mode": summary_mode["mode"],
        "content_mode_confidence": summary_mode["confidence"],
        "content_mode_reason": summary_mode["reason"],
        "summary_structure": summary_structure,
        "visual_archetype": archetype,
        "recommended_preset": ARCHETYPE_PRESETS[archetype],
        "information_density": density,
        "hierarchy": {
            "primary": [title] + (["截止/风险状态"] if warning_hits else []) + (["关键指标"] if metrics else []),
            "secondary": [item for item, active in (("时间线", timeline), ("行动入口", button_ready), ("案例视觉", need_hero)) if active],
            "supporting": ["说明段落"] + (["长篇细节"] if is_long else []),
        },
        "focus_mode": focus_mode,
        "content_intelligence": content_analysis,
        "information_allocation": allocation,
        "content_policy": content_analysis["rewrite_policy"],
        "attention_map": content_analysis["attention_map"],
        "button_suggestions": content_analysis["button_suggestions"],
        "media_policy": {
            "need_hero": need_hero and not need_gallery,
            "need_gallery": need_gallery,
            "need_switcher": need_switcher,
            "motion": "gif" if need_motion else "static",
            "static_first_frame_required": need_motion,
            "application_bot_required": need_switcher,
            "reason": "图片切换需要 application-bot callback 更新卡片状态；无后端时退回首张静态图" if need_switcher else ("动图必须配静态首帧，且关键信息不能只存在动画中" if need_motion else ("多作品/多图片应使用 img_combination，不称为轮播" if need_gallery else (allocation_reason if need_hero and allocation_reason else "默认生成一张主题信息视觉；只有用户明确要求无图才跳过"))),
            "aspect_ratio": "5:3 reference banner" if need_hero else ("1:1 tiles" if need_gallery else None),
            "prompt_brief": (f"为“{title}”生成 Seedream 5.0 Pro 一次性完成的当前模式最终图片资产、无水印；图片只承载 information_allocation.image.include 中的短标题、关系节点、关键指标和必要 quote，严禁按钮、CTA 标签或伪交互；原生 Card 只保留精简摘要、关键点、图表和真实行动，长段落与完整事实保留在 source.txt；不要生成无字底图，不要后处理。" if need_hero or need_gallery else None),
            "information_carrier": content_analysis["media_plan"]["information_carrier"],
            "not_decorative": content_analysis["media_plan"].get("not_decorative", False),
            "visual_job": content_analysis["media_plan"].get("visual_job"),
            "composition": content_analysis["media_plan"].get("composition"),
            "role": content_analysis["media_plan"].get("role"),
            "source_spans": content_analysis["media_plan"].get("source_spans", []),
            "native_text_pairing": content_analysis["media_plan"].get("native_text_pairing"),
            "facts_must_remain_in_text": True,
            "text_in_image": content_analysis["media_plan"].get("text_in_image", "seedream_5_pro_direct_selected_text_and_layout") if need_hero else "none",
            "image_text_layout": content_analysis["media_plan"].get("image_text_layout", "reference_card_banner") if need_hero else None,
            "functional_text_source": content_analysis["media_plan"].get("functional_text_source") if need_hero else None,
            "media_role": content_analysis["media_plan"]["mode"],
            "generated": False,
            "uploaded": False,
            "prompt_profile": prompt_recipe["primary_profile"],
            "prompt_profiles": prompt_recipe["selected_profiles"],
            "prompt_layout": prompt_recipe["layout_id"],
            "visual_skill_packs": prompt_recipe.get("visual_skill_routing", {}).get("selected_packs", []),
            "visual_style": prompt_recipe.get("visual_skill_routing", {}).get("style_id"),
            "visual_layout": prompt_recipe.get("visual_skill_routing", {}).get("visual_layout"),
        },
        "prompt_routing": prompt_recipe,
        "component_strategy": sorted(components, key=lambda item: (item["priority"], not item["selected"])),
        "fold_strategy": {
            "mode": "concise_card_plus_source" if is_long else "none",
            "use_collapsible_panel": False,
            "keep_visible": ["一句摘要", "3–5 个关键点", "关键指标/图表", "主行动"],
            "collapse": [],
            "reason": "长文不入卡片折叠区；保留在 source.txt 或通过真实来源链接打开" if is_long else "内容长度适合单页直接呈现",
        },
        "navigation_strategy": navigation,
        "interaction_strategy": {
            "actions": "media_switcher" if need_switcher else ("buttons" if button_ready else "none"),
            "max_primary_actions": 1,
            "max_visible_actions": 2 if not need_switcher else 4,
            "requires_backend": explicit_pages or need_switcher,
            "reason": "图片切换和分页状态只能由 application-bot callback 后端更新" if (explicit_pages or need_switcher) else ("只对真实 URL 且有明确动作语义的链接生成 open_url；被动参考链接保留为行内链接" if button_ready else ("存在链接但没有明确下一步，保留为行内参考" if urls else "没有真实目标就不生成按钮")),
        },
        "long_text_policy": content_analysis["long_text_policy"],
        "media_plan": content_analysis["media_plan"],
        "promotion_copy": content_analysis["promotion_copy"],
        "mobile_constraints": [
            "正文优先单列", "指标最多两列自动换行", "默认使用 3–6 个节制的语义 Emoji，每个关键模块最多一个", "单个可见文字块不超过 220 字，卡片只保留摘要、3–5 个关键点和行动", "最多一个 primary + 一个 secondary CTA", "真实数据优先图表，流程/对比优先信息图；不编造数值",
        ],
        "quality_contract": {
            "source_text_is_canonical": True,
            "factual_text_changed": False,
            "no_unapproved_rewrite": True,
            "dates_display": "几月几日",
            "emoji_aliases": "explicit aliases are preserved; semantic is the default and adds at most six structural markers",
            "visible_text_policy": "summary + 3-5 key points + metrics/chart + CTA; full source stays in source.txt or a real source URL",
            "no_redundant_prose": "exact/high-confidence duplicate only; uncertain similarity is surfaced for review",
        },
        "confidence": round(min(confidence, 0.95), 2),
        "evidence": evidence,
    }
    if override:
        if not isinstance(override, Mapping):
            raise ValueError("design_plan override must be an object")
        plan = _deep_merge(plan, override)
        plan["planner"] = "deterministic-baseline-v2+semantic-override"
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False, description="Plan a Feishu Card 2.0 layout without external LLM calls")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--text-file")
    parser.add_argument("--override", help="JSON file containing planning/design_plan overrides")
    parser.add_argument("--output", help="write plan JSON; stdout when omitted")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        text = args.text if args.text is not None else Path(args.text_file).read_text(encoding="utf-8")
        override = None
        if args.override:
            raw = json.loads(Path(args.override).read_text(encoding="utf-8"))
            override = raw.get("design_plan", raw.get("planning", raw)) if isinstance(raw, dict) else raw
        plan = plan_card(text, override)
        payload = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"plan_card.py: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
