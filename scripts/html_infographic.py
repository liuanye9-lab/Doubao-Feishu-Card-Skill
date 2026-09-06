#!/usr/bin/env python3
"""Source-locked HTML infographic fallback for dense Feishu card visuals.

The normal visual path remains the host image model.  This module is only used
when a card contains enough structured copy that exact typography, data binding
or a chart would be more reliable in HTML than in a generated bitmap.  The
HTML is deliberately self-contained and is rendered to ``hero.png`` by the
separate browser screenshot command; it never becomes Card JSON or an
interactive surface.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
HTML_RENDER_STRATEGY = "html_infographic_to_png"
NATIVE_MODEL_STRATEGY = "native_model"
HTML_TEXT_POLICY = "html_selected_text_and_layout"
HTML_SCHEMA = "feishu-card-html-infographic/1"
HTML_PROVENANCE_SCHEMA = "feishu-card-html-render-provenance/1"


def html_source_is_safe(html_path: Path) -> bool:
    """Allow only the self-contained, static HTML emitted by this route."""
    try:
        source = Path(html_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    if f'data-render-strategy="{HTML_RENDER_STRATEGY}"' not in source:
        return False
    return not bool(re.search(
        r"<\s*(?:script|iframe|object|embed)\b|"
        r"(?:src|href)\s*=\s*[\"'](?:https?:|//|javascript:|data:)",
        source,
        flags=re.IGNORECASE,
    ))


def _text(value: Any) -> str:
    value = "" if value is None else str(value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"https?://\S+", "", value)
    return re.sub(r"\s+", " ", value).strip(" \t\r\n：:")


def _compact(value: Any, limit: int = 112) -> str:
    value = _text(value)
    if len(value) <= limit:
        return value
    clauses = [part.strip() for part in re.split(r"[。！？；;]", value) if part.strip()]
    if clauses and len(clauses[0]) <= limit:
        return clauses[0]
    cut = max(value.rfind(mark, 0, limit + 1) for mark in ("，", "、", " "))
    return (value[:cut] if cut >= max(24, limit // 2) else value[:limit]).rstrip() + "…"


def _flatten(blocks: Iterable[Any]) -> Iterable[Dict[str, Any]]:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        yield block
        if block.get("type") == "columns":
            for column in block.get("columns", []):
                if isinstance(column, dict):
                    yield from _flatten(column.get("blocks", []))


def _source(spec: Mapping[str, Any]) -> str:
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), Mapping) else {}
    return str(analysis.get("source_text") or "")


def _visual_title(spec: Mapping[str, Any]) -> str:
    """Keep the hero heading short even when the source title is a paragraph."""
    candidate = _text(spec.get("title"))
    if not candidate:
        return "信息图"
    if len(candidate) <= 42 and not re.search(r"[。！？；;]", candidate):
        return candidate
    prefix = re.split(r"[：:|｜]", candidate, maxsplit=1)[0].strip()
    if 2 <= len(prefix) <= 32:
        return prefix
    first_clause = re.split(r"[。！？；;]", candidate, maxsplit=1)[0].strip()
    return _compact(first_clause or candidate, 32)


def _media_policy(spec: Mapping[str, Any]) -> Dict[str, Any]:
    analysis = spec.get("analysis") if isinstance(spec.get("analysis"), Mapping) else {}
    design = analysis.get("design_plan") if isinstance(analysis, Mapping) else {}
    media = design.get("media_policy") if isinstance(design, Mapping) else {}
    return dict(media) if isinstance(media, Mapping) else {}


def current_render_strategy(spec: Mapping[str, Any]) -> str:
    """Read the persisted strategy without silently changing a resumed spec."""
    hero = spec.get("hero") if isinstance(spec.get("hero"), Mapping) else {}
    media = _media_policy(spec)
    for value in (
        spec.get("render_strategy"),
        hero.get("render_strategy"),
        media.get("render_strategy"),
    ):
        value = str(value or "").strip().lower()
        if value in {HTML_RENDER_STRATEGY, "html_to_png", "html"}:
            return HTML_RENDER_STRATEGY
        if value in {NATIVE_MODEL_STRATEGY, "model", "native", "image_model"}:
            return NATIVE_MODEL_STRATEGY
    return ""


def _is_dense_candidate(spec: Mapping[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """Detect dense *structured* copy, not merely a long paragraph.

    A metric-only card remains model-first: modern raster models can make a
    strong visual for a few short values.  HTML is reserved for several
    sections, relationships or a source-backed chart where deterministic
    typography materially improves fidelity.
    """
    source = _source(spec)
    allocation = spec.get("information_allocation") if isinstance(spec.get("information_allocation"), Mapping) else {}
    image = allocation.get("image") if isinstance(allocation, Mapping) else {}
    image_items = image.get("include") if isinstance(image, Mapping) and isinstance(image.get("include"), list) else []
    flat = list(_flatten(spec.get("blocks") if isinstance(spec.get("blocks"), list) else []))
    section_count = sum(1 for block in flat if block.get("type") == "section")
    timeline_count = sum(1 for block in flat if block.get("type") == "timeline")
    metric_count = sum(
        len(block.get("items", []))
        for block in flat
        if block.get("type") == "metrics" and isinstance(block.get("items"), list)
    )
    relationship_count = sum(
        1 for item in image_items
        if isinstance(item, Mapping) and item.get("role") in {"relationship", "stage", "fact"}
    )
    visual = spec.get("visual_spec") if isinstance(spec.get("visual_spec"), Mapping) else {}
    chart = visual.get("chart") if isinstance(visual, Mapping) else None
    case_signal = bool(
        spec.get("scene") == "case-showcase"
        or ((allocation.get("signals") or {}).get("case_signal") if isinstance(allocation, Mapping) and isinstance(allocation.get("signals"), Mapping) else False)
        or relationship_count >= 3
    )
    has_motion = bool((spec.get("motion_spec") or {}).get("selected")) if isinstance(spec.get("motion_spec"), Mapping) else False
    reasons: List[str] = []
    dense = False
    if not has_motion and source and section_count >= 3 and len(source) >= 340 and case_signal:
        dense = True
        reasons.append("case sections and relationship nodes need exact type/layout")
    if not has_motion and source and section_count >= 2 and len(source) >= 720:
        dense = True
        reasons.append("long source with multiple structured sections")
    chart_items = chart.get("items") if isinstance(chart, Mapping) and isinstance(chart.get("items"), list) else []
    if not has_motion and chart and isinstance(chart, Mapping) and len(chart_items) >= 3 and section_count >= 2:
        dense = True
        reasons.append("source-backed chart plus supporting sections")
    if not has_motion and metric_count >= 5 and section_count >= 2 and len(source) >= 620:
        dense = True
        reasons.append("many metrics plus explanatory sections")
    return dense, {
        "source_chars": len(source),
        "section_count": section_count,
        "timeline_count": timeline_count,
        "metric_count": metric_count,
        "relationship_count": relationship_count,
        "image_item_count": len(image_items),
        "chart_type": chart.get("type") if isinstance(chart, Mapping) else None,
        "motion_selected": has_motion,
        "reasons": reasons,
    }


def choose_render_strategy(
    spec: Dict[str, Any],
    *,
    explicit_strategy: Optional[str] = None,
    allow_auto: bool = True,
) -> str:
    """Persist model-first/HTML-fallback routing in every relevant contract."""
    hero = spec.get("hero")
    if not isinstance(hero, dict):
        return "none"
    current = current_render_strategy(spec)
    requested = str(explicit_strategy or "").strip().lower()
    if requested in {"html", "html_to_png", HTML_RENDER_STRATEGY}:
        strategy = HTML_RENDER_STRATEGY
        reason = "用户显式选择 HTML → PNG 信息图"
        signals: Dict[str, Any] = {}
    elif requested in {"native", "model", "native_model", "image_model"}:
        strategy = NATIVE_MODEL_STRATEGY
        reason = "用户显式选择模型生图"
        signals = {}
    elif current:
        strategy = current
        reason = "沿用已保存的视觉渲染策略，resume 不重排"
        signals = {}
    elif allow_auto:
        dense, signals = _is_dense_candidate(spec)
        strategy = HTML_RENDER_STRATEGY if dense else NATIVE_MODEL_STRATEGY
        reason = "；".join(signals.get("reasons") or []) if dense else "默认模型生图优先；内容未达到 HTML 信息图阈值"
    else:
        strategy = NATIVE_MODEL_STRATEGY
        reason = "显式图片模式/无图约束抑制自动 HTML 分流"
        signals = {}

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
    if isinstance(spec.get("information_allocation"), dict):
        image = spec["information_allocation"].setdefault("image", {})
        if isinstance(image, dict):
            image["render_strategy"] = strategy
            image["render_reason"] = reason
    decision_log = analysis.setdefault("decision_log", [])
    if isinstance(decision_log, list):
        entry: Dict[str, Any] = {
            "decision": "applied",
            "component": "visual_render_strategy",
            "selected": strategy,
            "reason": reason,
            "model_first": True,
            "html_is_fallback_only": True,
        }
        if signals:
            entry["signals"] = signals
        decision_log.append(entry)
    return strategy


def _safe_color(value: Any, fallback: str) -> str:
    value = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value) or re.fullmatch(r"rgba?\([^)]{1,48}\)", value):
        return value
    return fallback


def _palette(spec: Mapping[str, Any]) -> Dict[str, str]:
    fallback = {
        "background": "#F6F5F1",
        "body": "#FBFAF4",
        "ink": "#15171A",
        "muted": "#667180",
        "accent": "#214DFA",
        "warm": "#EACD76",
        "header": "#F5F5F3",
        "glass": "#EAF1FF",
        "gradient": "#F0F5FF",
    }
    preset = str(spec.get("preset") or "").strip()
    try:
        registry = json.loads((ROOT / "presets" / "preset-index.json").read_text(encoding="utf-8"))
        aliases = registry.get("aliases") if isinstance(registry.get("aliases"), Mapping) else {}
        preset = str(aliases.get(preset) or preset)
        for item in registry.get("presets", []):
            if isinstance(item, Mapping) and item.get("id") == preset:
                gallery = item.get("gallery") if isinstance(item.get("gallery"), Mapping) else {}
                fallback.update({
                    "background": _safe_color(gallery.get("background_hex"), fallback["background"]),
                    "body": _safe_color(gallery.get("body_hex"), fallback["body"]),
                    "ink": _safe_color(gallery.get("ink_hex"), fallback["ink"]),
                    "muted": _safe_color(gallery.get("muted_hex"), fallback["muted"]),
                    "accent": _safe_color(gallery.get("accent_hex"), fallback["accent"]),
                    "header": str(gallery.get("header_fill") or gallery.get("header_gradient") or fallback["header"]),
                    "glass": _safe_color(gallery.get("glass_hex"), fallback["glass"]),
                    "gradient": _safe_color(gallery.get("gradient_hex"), fallback["gradient"]),
                })
                break
    except (OSError, ValueError, TypeError):
        pass
    fallback["warm"] = _safe_color("#EACD76", fallback["warm"])
    return fallback


def _split_label(value: Any) -> Tuple[str, str]:
    text = _compact(value)
    match = re.match(r"^([^：:|｜]{1,26})[：:|｜]\s*(.*)$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", text


def _metric_items(spec: Mapping[str, Any]) -> List[Dict[str, Any]]:
    visual = spec.get("visual_spec") if isinstance(spec.get("visual_spec"), Mapping) else {}
    values = visual.get("metrics") if isinstance(visual, Mapping) else []
    if isinstance(values, list) and values:
        return [dict(item) for item in values if isinstance(item, Mapping)]
    output: List[Dict[str, Any]] = []
    for block in _flatten(spec.get("blocks") if isinstance(spec.get("blocks"), list) else []):
        if block.get("type") != "metrics" or not isinstance(block.get("items"), list):
            continue
        for item in block["items"]:
            if isinstance(item, Mapping):
                output.append({"label": item.get("label"), "display": item.get("value"), "source_text": item.get("source_text")})
    return output


def _chart_markup(chart: Mapping[str, Any], palette: Mapping[str, str]) -> str:
    chart_type = str(chart.get("type") or "bar").lower()
    raw_values = chart.get("items") if isinstance(chart.get("items"), list) else []
    values = [item for item in raw_values if isinstance(item, Mapping) and item.get("value") is not None]
    if not values:
        return ""
    title = html_lib.escape(_text(chart.get("title") or "📊 关键指标"))
    colors = [palette.get("accent", "#214DFA"), palette.get("ink", "#15171A"), palette.get("warm", "#EACD76"), "#5AA4AE", "#955539", "#8A9BFF"]
    if chart_type == "pie":
        total = sum(float(item.get("value") or 0) for item in values)
        if total <= 0:
            return ""
        cursor = 0.0
        stops = []
        for index, item in enumerate(values):
            start = cursor
            cursor += float(item.get("value") or 0) / total * 360
            stops.append(f"{colors[index % len(colors)]} {start:.2f}deg {cursor:.2f}deg")
        legend = "".join(
            f'<div class="legend"><i style="background:{colors[index % len(colors)]}"></i><span>{html_lib.escape(_text(item.get("category")))}</span><b>{html_lib.escape(_text(item.get("display") or item.get("value")))}</b></div>'
            for index, item in enumerate(values)
        )
        return f'<section class="chart-section pie-section"><div class="section-kicker">{title}</div><div class="pie-layout"><div class="donut" style="background:conic-gradient({", ".join(stops)})"><div class="donut-hole"></div></div><div class="legend-list">{legend}</div></div></section>'
    maximum = max(abs(float(item.get("value") or 0)) for item in values) or 1
    rows = "".join(
        f'<div class="bar-row"><div class="bar-label">{html_lib.escape(_text(item.get("category")))}</div><div class="bar-track"><span style="width:{min(100, abs(float(item.get("value") or 0)) / maximum * 100):.2f}%;background:{colors[index % len(colors)]}"></span></div><div class="bar-value">{html_lib.escape(_text(item.get("display") or item.get("value")))}</div></div>'
        for index, item in enumerate(values)
    )
    return f'<section class="chart-section"><div class="section-kicker">{title}</div><div class="bar-list">{rows}</div></section>'


def _signal_markup(spec: Mapping[str, Any]) -> str:
    allocation = spec.get("information_allocation") if isinstance(spec.get("information_allocation"), Mapping) else {}
    image = allocation.get("image") if isinstance(allocation, Mapping) else {}
    items = image.get("include") if isinstance(image, Mapping) and isinstance(image.get("include"), list) else []
    selected = [item for item in items if isinstance(item, Mapping) and item.get("role") != "title"][:5]
    if not selected:
        return ""
    role_labels = {"relationship": "关系", "stage": "阶段", "fact": "事实", "metric": "指标", "quote": "观点"}
    cells: List[str] = []
    for index, item in enumerate(selected, start=1):
        label, body = _split_label(item.get("text"))
        visible = body or _compact(item.get("text"), 100)
        role = str(item.get("role") or "fact")
        if role == "metric":
            cells.append(f'<div class="signal metric-signal"><div class="signal-index">{index:02d}</div><div><div class="signal-label">{html_lib.escape(label or "指标")}</div><div class="signal-value">{html_lib.escape(visible)}</div></div></div>')
        else:
            cells.append(f'<div class="signal"><div class="signal-index">{index:02d}</div><div><div class="signal-label">{html_lib.escape(label or role_labels.get(role, "事实"))}</div><div class="signal-body">{html_lib.escape(visible)}</div></div></div>')
    layout_class = "single" if len(cells) == 1 else ""
    return f'<section class="signal-grid {layout_class}">{"".join(cells)}</section>'


def _block_markup(block: Mapping[str, Any], palette: Mapping[str, str], *, summary: str) -> str:
    kind = str(block.get("type") or "")
    if kind in {"buttons", "div"}:
        return ""
    if kind == "metrics":
        visual = block.get("chart")
        if isinstance(visual, Mapping):
            return _chart_markup(visual, palette)
        items = block.get("items") if isinstance(block.get("items"), list) else []
        if not items:
            items = _metric_items({"visual_spec": {"metrics": []}, "blocks": [block]})
        cells = []
        for item in items[:6]:
            if not isinstance(item, Mapping):
                continue
            display = item.get("display") if item.get("display") is not None else item.get("value")
            cells.append(f'<div class="metric-card"><div class="metric-label">{html_lib.escape(_text(item.get("label")))}</div><div class="metric-value">{html_lib.escape(_text(display))}</div></div>')
        return f'<section class="content-section"><div class="section-kicker">指标</div><div class="metric-grid">{"".join(cells)}</div></section>' if cells else ""
    if kind == "facts":
        items = block.get("items") if isinstance(block.get("items"), list) else []
        cells = []
        for item in items[:8]:
            if not isinstance(item, Mapping):
                continue
            cells.append(f'<div class="fact-row"><span>{html_lib.escape(_text(item.get("label")))}</span><b>{html_lib.escape(_compact(item.get("value"), 86))}</b></div>')
        return f'<section class="content-section"><div class="fact-grid">{"".join(cells)}</div></section>' if cells else ""
    if kind in {"section", "highlight"}:
        title = _text(block.get("title") or block.get("label"))
        body = str(block.get("body") or block.get("content") or block.get("text") or "")
        lines = [line.strip(" -*•\t") for line in body.splitlines() if line.strip()]
        if not lines and body.strip():
            lines = [body.strip()]
        lines = [_compact(line, 150) for line in lines[:4]]
        if not lines:
            return ""
        content = "".join(f'<li>{html_lib.escape(line)}</li>' for line in lines)
        return f'<section class="content-section section-card"><div class="section-kicker">{html_lib.escape(title or "要点")}</div><ul>{content}</ul></section>'
    if kind == "timeline":
        items = block.get("items") if isinstance(block.get("items"), list) else []
        rows = []
        for item in items[:6]:
            if not isinstance(item, Mapping):
                continue
            date = _text(item.get("date"))
            title = _text(item.get("title"))
            body = _compact(item.get("body") or item.get("content"), 120)
            body_markup = f'<div class="timeline-body">{html_lib.escape(body)}</div>' if body and title else ""
            rows.append(f'<div class="timeline-row"><div class="timeline-date">{html_lib.escape(date)}</div><div><div class="timeline-title">{html_lib.escape(title or body)}</div>{body_markup}</div></div>')
        return f'<section class="content-section timeline-section"><div class="section-kicker">节点</div>{"".join(rows)}</section>' if rows else ""
    if kind == "quote":
        quote = _compact(block.get("text") or block.get("content"), 180)
        return f'<section class="quote-section"><div class="quote-mark">“</div><div>{html_lib.escape(quote)}</div></section>' if quote else ""
    if kind == "text":
        content = _compact(block.get("content") or block.get("text"), 180)
        if not content or content == summary:
            return ""
        return f'<section class="content-section intro-note">{html_lib.escape(content)}</section>'
    return ""


def build_html_design_prompt(spec: Mapping[str, Any], *, brand_context: str = "") -> str:
    allocation = spec.get("information_allocation") if isinstance(spec.get("information_allocation"), Mapping) else {}
    image = allocation.get("image") if isinstance(allocation, Mapping) else {}
    whitelist = [item.get("text") for item in image.get("include", []) if isinstance(item, Mapping)] if isinstance(image, Mapping) else []
    return f"""# HTML 信息图设计提示词

渲染策略：{HTML_RENDER_STRATEGY}（仅作为模型生图失败风险较高的文字密集信息图 fallback；纯视觉首图仍优先交给宿主图片模型）。
视觉方向：保留现有 template={spec.get('template_id') or spec.get('preset') or 'apple-minimal'} 的选定模板与共享 Apple 官网式现代主义层级纪律，但升级为高级信息设计：中等字重现代无衬线、轻盈数字、克制配色、1.5 倍留白、透明磨砂玻璃、轻微动态模糊、低饱和渐变光晕、通栏/细线分隔；不得使用廉价高饱和渐变、无意义卡片墙或硬边重阴影。
品牌上下文：{brand_context.strip() or '未提供额外品牌事实，仅使用当前 preset token。'}

硬约束：
- 只使用 source/spec 与 information_allocation.image.include 中的来源锁定文字、数字和关系；不能补写事实、结果、单位或 URL。
- 使用自包含 HTML/CSS，所有字体、颜色和布局声明写在文件内；禁止外链资源、网络字体、脚本交互和动态数据。
- 将长文拆成标题、指标、节点、关系、图表和短句；不要输出密密麻麻的段落墙。
- 允许 1–3 个有信息作用的磨砂玻璃层：标题锚点、证据窗口、图表台或流程节点；玻璃层必须帮助分组或引导阅读，不能只是装饰。
- 可使用 backdrop-filter blur、柔和环境阴影、内侧高光和受控渐变建立空间感；所有文字、数字、日期和图表标签必须清晰锐利。
- 真实按钮、CTA、链接和回调只能留在原生 Card，不得画进图片。
- 图表只能复用 visual_spec/chart 的真实数据；没有可比较数据时使用指标排版，不制造比例。
- 输出固定尺寸、适配移动端的单张视觉图，后续由浏览器截图为 hero.png；HTML 文件保留为可编辑源与溯源证据。

图片文字白名单：
{json.dumps(whitelist, ensure_ascii=False, indent=2)}
"""


def build_html_artifact(
    spec: Mapping[str, Any],
    html_path: Path,
    *,
    brand_context: str = "",
) -> Dict[str, Any]:
    """Write an editable, self-contained HTML infographic and return its plan."""
    html_path = Path(html_path)
    palette = _palette(spec)
    title = _visual_title(spec)
    summary = _compact(spec.get("lead") or "", 88)
    if not summary:
        for block in _flatten(spec.get("blocks") if isinstance(spec.get("blocks"), list) else []):
            if block.get("type") == "text":
                summary = _compact(block.get("content") or block.get("text"), 88)
                if summary:
                    break
    visual = spec.get("visual_spec") if isinstance(spec.get("visual_spec"), Mapping) else {}
    chart = visual.get("chart") if isinstance(visual, Mapping) and isinstance(visual.get("chart"), Mapping) else None
    sections: List[str] = []
    if chart:
        sections.append(_chart_markup(chart, palette))
    else:
        metrics = _metric_items(spec)
        if len(metrics) >= 2:
            cells = "".join(
                f'<div class="metric-card"><div class="metric-label">{html_lib.escape(_text(item.get("label")))}</div><div class="metric-value">{html_lib.escape(_text(item.get("display") or item.get("value")))}</div></div>'
                for item in metrics[:6]
            )
            sections.append(f'<section class="content-section"><div class="section-kicker">指标</div><div class="metric-grid">{cells}</div></section>')
    for block in _flatten(spec.get("blocks") if isinstance(spec.get("blocks"), list) else []):
        if len(sections) >= 9:
            break
        rendered = _block_markup(block, palette, summary=summary)
        if rendered and rendered not in sections:
            sections.append(rendered)
    if not sections:
        source = _source(spec)
        clauses = [part.strip() for part in re.split(r"[。！？；;]", source) if part.strip()]
        for index, clause in enumerate(clauses[:4], start=1):
            match = re.match(r"^([^：:|｜]{1,18})[：:|｜]\s*(.*)$", clause)
            label = match.group(1).strip() if match else f"要点 {index}"
            value = match.group(2).strip() if match else clause
            sections.append(
                f'<section class="content-section section-card"><div class="section-kicker">{html_lib.escape(label)}</div>'
                f'<ul><li>{html_lib.escape(_compact(value, 120))}</li></ul></section>'
            )
        if not sections:
            sections.append(f'<section class="content-section intro-note">{html_lib.escape(summary or title)}</section>')
    html_path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(sections)
    source_chars = len(_source(spec))
    signal_markup = _signal_markup(spec)
    signal_present = bool(signal_markup)
    aliases = {}
    registry_data: Dict[str, Any] = {}
    try:
        registry_data = json.loads((ROOT / "presets" / "preset-index.json").read_text(encoding="utf-8"))
        aliases = registry_data.get("aliases") if isinstance(registry_data.get("aliases"), dict) else {}
    except (OSError, ValueError, TypeError):
        aliases = {}
    template_id = str(aliases.get(spec.get("template_id") or spec.get("preset") or "") or spec.get("template_id") or spec.get("preset") or "apple-minimal")
    template_name = template_id
    for item in registry_data.get("presets", []):
        if isinstance(item, Mapping) and item.get("id") == template_id:
            template_name = str(item.get("name") or template_id)
            break
    template_class = re.sub(r"[^a-z0-9-]", "-", template_id.lower()).strip("-") or "apple-minimal"
    page_height = max(
        1200,
        min(3600, int(620 + len(sections) * 145 + (140 if signal_present else 0) + min(1500, source_chars * 0.36))),
    )
    document = f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_lib.escape(title)}</title>
  <style>
    :root {{ --bg:{palette['background']}; --paper:{palette['body']}; --ink:{palette['ink']}; --muted:{palette['muted']}; --accent:{palette['accent']}; --warm:{palette['warm']}; --header:{palette['header']}; --glass:{palette['glass']}; --gradient:{palette['gradient']}; }}
    * {{ box-sizing:border-box; }}
    @page {{ size:1200px {page_height}px; margin:0; }}
    html, body {{ margin:0; width:1200px; min-height:{page_height}px; background:var(--bg); color:var(--ink); }}
    body {{ font-family:"Noto Sans SC","Source Han Sans SC","PingFang SC","Helvetica Neue",Arial,sans-serif; -webkit-font-smoothing:antialiased; font-variant-numeric:tabular-nums; }}
    main {{ width:1200px; min-height:{page_height}px; padding:96px 104px 120px; background:radial-gradient(circle at 100% 0%, var(--gradient) 0%, transparent 28%), radial-gradient(circle at 0% 100%, var(--glass) 0%, transparent 24%), linear-gradient(135deg, var(--paper) 0%, #FFFFFF 54%, var(--bg) 100%); position:relative; overflow:hidden; }}
    main::before, main::after {{ content:""; position:absolute; z-index:0; border-radius:999px; pointer-events:none; filter:blur(26px); opacity:.28; }}
    main::before {{ width:420px; height:420px; top:-180px; right:-100px; background:radial-gradient(circle, var(--accent) 0%, transparent 68%); }}
    main::after {{ width:360px; height:360px; bottom:-180px; left:-90px; background:radial-gradient(circle, var(--glass) 0%, transparent 70%); }}
    header, section {{ position:relative; z-index:1; }}
    header {{ padding:42px 46px 46px; background:linear-gradient(135deg, rgba(255,255,255,.80), rgba(255,255,255,.42)), var(--header); color:var(--ink); min-height:238px; display:flex; flex-direction:column; justify-content:flex-end; border:1px solid rgba(255,255,255,.78); border-radius:24px; box-shadow:0 22px 80px rgba(17,24,39,.09), inset 0 1px 0 rgba(255,255,255,.92); backdrop-filter:blur(22px) saturate(122%); }}
    .eyebrow {{ align-self:flex-start; color:var(--accent); font-size:20px; letter-spacing:.10em; text-transform:uppercase; margin-bottom:28px; padding:10px 16px; border:1px solid rgba(255,255,255,.82); border-radius:999px; background:linear-gradient(135deg, rgba(255,255,255,.68), rgba(255,255,255,.30)); box-shadow:inset 0 1px 0 rgba(255,255,255,.88); font-weight:600; }}
    h1 {{ margin:0; max-width:1000px; font-size:64px; line-height:1.16; letter-spacing:-.035em; font-weight:600; }}
    .summary {{ margin-top:28px; max-width:920px; color:var(--muted); font-size:26px; line-height:1.5; }}
    .signal-grid {{ margin:58px 0 0; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:22px; }}
    .signal-grid.single {{ grid-template-columns:1fr; }}
    .signal {{ min-height:138px; display:grid; grid-template-columns:60px 1fr; gap:18px; padding:30px 28px; border:1px solid rgba(255,255,255,.72); border-radius:20px; background:linear-gradient(135deg, rgba(255,255,255,.70), rgba(255,255,255,.32)), var(--glass); box-shadow:0 18px 54px rgba(17,24,39,.07), inset 0 1px 0 rgba(255,255,255,.90); backdrop-filter:blur(18px) saturate(118%); }}
    .signal-index {{ color:var(--accent); font-size:22px; font-weight:500; }}
    .signal-label, .section-kicker, .metric-label {{ color:var(--muted); font-size:21px; line-height:1.25; letter-spacing:.02em; }}
    .signal-body {{ margin-top:14px; font-size:28px; line-height:1.42; font-weight:400; }}
    .signal-value {{ margin-top:10px; color:var(--accent); font-size:36px; line-height:1.15; font-weight:400; }}
    .content-section, .chart-section {{ margin-top:64px; padding:30px 34px 34px; border:1px solid rgba(255,255,255,.76); border-radius:22px; background:linear-gradient(135deg, rgba(255,255,255,.74), rgba(255,255,255,.35)), var(--glass); box-shadow:0 20px 68px rgba(17,24,39,.08), inset 0 1px 0 rgba(255,255,255,.92); backdrop-filter:blur(20px) saturate(120%); }}
    .section-kicker {{ color:var(--ink); font-size:25px; font-weight:600; margin-bottom:24px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); column-gap:64px; row-gap:0; }}
    .metric-card {{ min-height:142px; padding:28px 24px; background:linear-gradient(135deg, rgba(255,255,255,.50), rgba(255,255,255,.18)); border:1px solid rgba(255,255,255,.64); border-radius:16px; box-shadow:inset 0 1px 0 rgba(255,255,255,.72); }}
    .metric-value {{ margin-top:16px; font-size:44px; line-height:1.12; font-weight:400; color:var(--ink); }}
    .fact-grid {{ display:grid; grid-template-columns:1fr; gap:12px; }}
    .fact-row {{ display:grid; grid-template-columns:32% 68%; gap:18px; padding:20px 22px; border:1px solid rgba(255,255,255,.64); border-radius:16px; background:linear-gradient(135deg, rgba(255,255,255,.48), rgba(255,255,255,.18)); font-size:24px; line-height:1.45; }}
    .fact-row span {{ color:var(--muted); }} .fact-row b {{ font-weight:400; }}
    .section-card ul {{ margin:0; padding:0; list-style:none; display:grid; gap:18px; }}
    .section-card li {{ position:relative; padding-left:0; font-size:26px; line-height:1.5; }}
    .section-card li::before {{ content:none; }}
    .timeline-section {{ display:grid; gap:0; }}
    .timeline-row {{ display:grid; grid-template-columns:220px 1fr; gap:32px; padding:26px 22px; border-bottom:1px solid rgba(21,23,26,.16); background:linear-gradient(90deg, rgba(255,255,255,.36), transparent); }}
    .timeline-date {{ color:var(--accent); font-size:29px; font-weight:500; }}
    .timeline-title {{ font-size:29px; line-height:1.4; }} .timeline-body {{ margin-top:10px; color:var(--muted); font-size:23px; line-height:1.5; }}
    .quote-section {{ margin-top:70px; padding:32px 34px; background:linear-gradient(135deg, rgba(255,255,255,.68), rgba(255,255,255,.28)), var(--glass); color:var(--ink); border:1px solid rgba(255,255,255,.76); border-left:4px solid var(--accent); border-radius:22px; box-shadow:0 18px 58px rgba(17,24,39,.07), inset 0 1px 0 rgba(255,255,255,.88); backdrop-filter:blur(18px) saturate(118%); display:grid; grid-template-columns:72px 1fr; gap:18px; font-size:31px; line-height:1.48; }}
    .quote-mark {{ color:var(--accent); font-size:70px; line-height:.8; }}
    .intro-note {{ font-size:26px; line-height:1.48; color:var(--ink); }}
    .bar-list {{ display:grid; gap:19px; }}
    .bar-row {{ display:grid; grid-template-columns:250px 1fr 150px; align-items:center; gap:16px; font-size:22px; }}
    .bar-label {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--muted); }}
    .bar-track {{ height:16px; background:rgba(21,23,26,.09); overflow:hidden; border-radius:999px; box-shadow:inset 0 1px 3px rgba(17,24,39,.08); }} .bar-track span {{ display:block; height:100%; border-radius:999px; background:linear-gradient(90deg, var(--accent), var(--gradient)); box-shadow:0 0 22px rgba(50,107,255,.22); }} .bar-value {{ text-align:right; font-size:24px; }}
    .pie-layout {{ display:grid; grid-template-columns:360px 1fr; align-items:center; gap:56px; }}
    .donut {{ width:330px; height:330px; border-radius:50%; display:grid; place-items:center; box-shadow:0 18px 50px rgba(17,24,39,.12), 0 0 40px rgba(50,107,255,.13); }} .donut-hole {{ width:160px; height:160px; border-radius:50%; background:linear-gradient(135deg, rgba(255,255,255,.88), rgba(255,255,255,.52)), var(--paper); border:1px solid rgba(255,255,255,.82); box-shadow:inset 0 1px 0 rgba(255,255,255,.90); }}
    .legend-list {{ display:grid; gap:15px; }} .legend {{ display:grid; grid-template-columns:18px 1fr auto; gap:12px; align-items:center; padding:14px 16px; border:1px solid rgba(255,255,255,.62); border-radius:14px; background:rgba(255,255,255,.34); font-size:22px; }} .legend i {{ width:18px; height:18px; display:block; border-radius:50%; box-shadow:0 0 18px currentColor; }} .legend b {{ font-weight:400; color:var(--accent); }}
  </style>
</head>
<body>
  <main class="template-{template_class}" data-template="{html_lib.escape(template_id)}" data-render-strategy="{HTML_RENDER_STRATEGY}">
    <header>
      <div class="eyebrow">{html_lib.escape(template_name)}</div>
      <h1>{html_lib.escape(title)}</h1>
      {f'<div class="summary">{html_lib.escape(summary)}</div>' if summary else ''}
    </header>
    {signal_markup}
    {body}
  </main>
</body>
</html>
'''
    html_path.write_text(document, encoding="utf-8")
    digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
    return {
        "schema": HTML_SCHEMA,
        "strategy": HTML_RENDER_STRATEGY,
        "html_file": str(html_path),
        "html_sha256": digest,
        "viewport": {"width": 1200, "height": page_height, "scale": 2},
        "template_id": template_id,
        "template_name": template_name,
        "renderer": "headless Chrome-family browser",
        "output_file": str(html_path.with_name("hero.png")),
        "source_locked": True,
        "source_sha256": hashlib.sha256(_source(spec).encode("utf-8")).hexdigest(),
        "text_policy": HTML_TEXT_POLICY,
        "prompt": build_html_design_prompt(spec, brand_context=brand_context),
        "no_interaction": True,
        "no_external_assets": True,
    }


def html_render_gate(
    image_path: Path,
    manifest_path: Path,
    html_path: Path,
    *,
    required: bool,
) -> Dict[str, Any]:
    """Verify the browser-rendered PNG and its HTML/source provenance."""
    from asset_validation import asset_error

    result: Dict[str, Any] = {
        "required": required,
        "manifest": str(manifest_path),
        "image": str(image_path),
        "html": str(html_path),
        "ready": False,
        "render_strategy": HTML_RENDER_STRATEGY,
        "post_processing": "none",
    }
    if not required:
        result["status"] = "not_required"
        return result
    if not html_path.is_file():
        result.update(status="html_source_missing", error="HTML 信息图源文件不存在")
        return result
    if not html_source_is_safe(html_path):
        result.update(status="html_source_contract_failed", error="HTML 必须包含本路由标记，且不得含脚本或外部资源")
        return result
    if not image_path.is_file():
        result.update(status="image_missing", error="HTML 信息图导出的 hero.png 不存在")
        return result
    if not manifest_path.is_file():
        result.update(status="provenance_manifest_missing", error="HTML → PNG 完成后必须登记 hero-generation.json")
        return result
    media_error = asset_error(image_path, "PNG")
    if media_error:
        result.update(status="invalid_image", error=media_error)
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.update(status="provenance_manifest_invalid", error=str(exc))
        return result
    if not isinstance(manifest, dict):
        result.update(status="provenance_manifest_invalid", error="hero-generation.json must be an object")
        return result
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    html_sha256 = hashlib.sha256(html_path.read_bytes()).hexdigest()
    prompt_value = Path(str(manifest.get("prompt_file") or ""))
    prompt_path = prompt_value if prompt_value.is_absolute() else manifest_path.parent / prompt_value
    prompt_hash_ok = bool(manifest.get("prompt_sha256")) and prompt_path.is_file()
    if prompt_hash_ok:
        prompt_hash_ok = manifest.get("prompt_sha256") == hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    contract_ok = (
        manifest.get("schema") == HTML_PROVENANCE_SCHEMA
        and manifest.get("tool") == "html_to_png"
        and manifest.get("generation_family") == "html-render"
        and manifest.get("render_strategy") == HTML_RENDER_STRATEGY
        and manifest.get("asset_name") == "hero.png"
        and manifest.get("image_sha256") == image_sha256
        and manifest.get("html_sha256") == html_sha256
        and prompt_hash_ok
    )
    result.update({
        "manifest_data": manifest,
        "image_sha256": image_sha256,
        "html_sha256": html_sha256,
        "prompt_hash_ok": prompt_hash_ok,
        "contract_ok": contract_ok,
    })
    if not contract_ok:
        result.update(status="provenance_contract_failed", error="HTML 源文件、渲染模式、PNG 哈希或提示词哈希不匹配")
        return result
    result.update(status="ready", ready=True, exact_text_verification="browser-rendered HTML text; manual visual review required")
    return result
