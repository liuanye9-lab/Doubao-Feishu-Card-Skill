#!/usr/bin/env python3
"""Source-backed visual planning for compact Feishu cards.

The module never invents values.  It extracts comparable metrics and compact
relationship nodes from the canonical source, then emits both an editable
visual specification and (when safe) a native CardKit chart block.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple


METRIC_LINE_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?P<label>[^：:|\t]{1,24})\s*[：:]\s*(?P<display>[^\n]{1,48})\s*$"
)
NUMBER_RE = re.compile(r"(?P<number>[+-]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?)")
NON_METRIC_LABEL_RE = re.compile(
    r"日期|时间|截止|地点|地址|链接|姓名|创建人|状态|编号|主题|形式|对象|名称|介绍|版本|ID|URL",
    re.I,
)
FLOW_LABEL_RE = re.compile(
    r"^\s*(?:#{1,4}\s*)?(?P<label>背景(?:/痛点)?|痛点|问题|做法|方法|方案|结果(?:/价值)?|成果|价值|前后对比|下一步|阶段|步骤)\s*[：:]\s*(?P<body>.+)$"
)
BRAND_ASSET_RE = re.compile(
    r"校徽|徽标|logo|标志|品牌资产|品牌规范|校名|学校|大学|学院|附中|中学|官方",
    re.I,
)
INFORMATION_IMAGE_REQUEST_RE = re.compile(
    r"(?:文字.{0,10}(?:图片|图像|视觉)|信息.{0,10}(?:可视化|承载)|"
    r"(?:图片|图像).{0,10}(?:承载|表达).{0,10}(?:文字|信息)|图文|信息图)",
    re.I,
)
URL_RE = re.compile(r"(?:https?://|lark://|feishu://)\S+", re.I)
DATE_LIKE_RE = re.compile(r"(?:20\d{2}[年./-]\d{1,2}|\d{1,2}月\d{1,2}|\d{1,2}[./-]\d{1,2})")


def _number(value: str) -> Optional[float]:
    match = NUMBER_RE.search(value)
    if not match:
        return None
    number = float(match.group("number").replace(",", "").replace("，", ""))
    return int(number) if number.is_integer() else number


def _unit_family(value: str) -> Tuple[str, str]:
    lowered = value.lower()
    if "pct" in lowered or "百分点" in value:
        return "percentage_point", "pct"
    if "%" in value or "百分比" in value:
        return "percent", "%"
    for unit in ("亿元", "万元", "元", "万小时", "万次", "万人", "分钟", "min", "小时", "h", "天", "人", "项", "次", "个", "家", "门店", "区域", "万", "亿", "倍"):
        if unit.lower() in lowered:
            return f"unit:{unit.lower()}", unit
    return "number", ""


def parse_metric_line(line: str, source_line: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Parse one source metric whose display value contains a real number."""
    match = METRIC_LINE_RE.match(str(line or ""))
    if not match:
        return None
    label = re.sub(r"\s+", " ", match.group("label")).strip()
    display = re.sub(r"\s+", " ", match.group("display")).strip()
    if NON_METRIC_LABEL_RE.search(label):
        return None
    value = _number(display)
    if value is None:
        return None
    family, unit = _unit_family(display)
    numeric_tokens = NUMBER_RE.findall(display)
    bounded = bool(re.search(r"以上|以下|至少|至多|超过|不足|约|大于|小于|[<>≤≥～~]|\d\s*[-—至]\s*\d", display))
    change = bool(re.search(r"提升|增长|增加|减少|下降|降低|缩短|节省|同比|环比", display + label))
    qualified = bounded or change or len(numeric_tokens) != 1
    if len(numeric_tokens) != 1:
        value = None
    return {
        "chart_eligible": not qualified,
        "chart_exclusion": "限定值、区间或变化率保留原文指标，不作为绝对值比较" if qualified else None,
        "label": label,
        "display": display,
        "value": value,
        "unit": unit,
        "unit_family": family,
        "source_text": str(line).strip(),
        "source_line": source_line,
    }


def extract_metrics(source: str) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    for index, line in enumerate(str(source or "").splitlines(), start=1):
        metric = parse_metric_line(line, index)
        if not metric:
            continue
        key = (metric["label"], metric["display"])
        if key in seen:
            continue
        seen.add(key)
        metrics.append(metric)
    return metrics


def _comparable_metrics(metrics: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for metric in metrics:
        if metric.get("chart_eligible", True) and metric.get("value") is not None:
            groups[str(metric.get("unit_family") or "number")].append(metric)
    candidates = [group for group in groups.values() if len(group) >= 2]
    if not candidates:
        return []
    candidates.sort(key=lambda group: (-len(group), int(group[0].get("source_line") or 0)))
    return candidates[0][:6]


def _chart_type(source: str, metrics: Sequence[Dict[str, Any]]) -> str:
    value = str(source or "")
    total = sum(float(item.get("value") or 0) for item in metrics)
    if (re.search(r"占比|构成|分布|份额", value) and abs(total - 100) <= 0.01
            and metrics[0].get("unit_family") == "percent"
            and all(float(item["value"]) >= 0 for item in metrics)):
        return "pie"
    time_label_re = re.compile(r"(?:20\d{2}|第?[一二三四五六七八九十\d]+(?:周|月|季)|\d{1,2}月)")
    time_label_count = sum(
        1 for item in metrics if time_label_re.search(str(item.get("label") or ""))
    )
    if len(metrics) >= 2 and time_label_count == len(metrics):
        return "line"
    return "bar"


def build_chart_plan(source: str, metrics: Optional[Sequence[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    selected = _comparable_metrics(list(metrics or extract_metrics(source)))
    if not selected:
        return None
    chart_type = _chart_type(source, selected)
    values = [
        {
            "category": str(item["label"]),
            "value": item["value"],
            "display": str(item["display"]),
            "source_line": item.get("source_line"),
        }
        for item in selected
    ]
    chart_spec: Dict[str, Any] = {
        "type": chart_type,
        "data": [{"id": "source_metrics", "values": values}],
        "title": {"visible": True, "text": "📊 关键指标" + (f"（{selected[0]['unit']}）" if selected[0].get("unit") else "")},
        "label": {"visible": True},
        "tooltip": {"visible": True},
    }
    if chart_type == "pie":
        chart_spec.update({"categoryField": "category", "valueField": "value", "outerRadius": 0.82})
    else:
        chart_spec.update({"xField": "category", "yField": "value"})
        if chart_type == "bar":
            chart_spec["direction"] = "horizontal"
            chart_spec["xField"] = "value"
            chart_spec["yField"] = "category"
        else:
            chart_spec["point"] = {"visible": True}
    return {
        "type": chart_type,
        "title": "📊 关键指标",
        "unit_family": selected[0].get("unit_family"),
        "unit": selected[0].get("unit"),
        "items": values,
        "source_lines": [item.get("source_line") for item in selected if item.get("source_line")],
        "source_text": [str(item.get("source_text") or "") for item in selected],
        "chart_spec": chart_spec,
        "grounding": "all numeric values are parsed from source_text; mixed-unit rows are excluded",
    }


def _compact_clause(value: str, limit: int = 72) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    candidates = [part.strip() for part in re.split(r"[。！？；;]", text) if part.strip()]
    if candidates and len(candidates[0]) <= limit:
        return candidates[0]
    cut = max(text.rfind(mark, 0, limit + 1) for mark in ("，", "、", " "))
    return (text[:cut] if cut >= max(24, limit // 2) else text[:limit]).rstrip() + "…"


def extract_relationship_nodes(source: str) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    for index, line in enumerate(str(source or "").splitlines(), start=1):
        match = re.match(r"^\s*(?:第(?P<step>[一二三四五六七八九十\d]+)步|(?P<date>\d{1,2}月\d{1,2}日(?:[—-]\d{1,2}月\d{1,2}日)?))\s*[：:]\s*(?P<body>.+)$", line)
        if match:
            nodes.append({"label": f"第{match.group('step')}步" if match.group('step') else match.group('date'),
                          "text": _compact_clause(match.group("body")), "source_text": line.strip(), "source_line": index})
            if len(nodes) >= 5:
                break
            continue
        match = FLOW_LABEL_RE.match(line)
        if not match:
            continue
        nodes.append({
            "label": match.group("label").lstrip("# ").strip(),
            "text": _compact_clause(match.group("body")),
            "source_text": line.strip(),
            "source_line": index,
        })
        if len(nodes) >= 5:
            break
    return nodes


def _heading_like(line: str) -> str:
    value = re.sub(r"^\s*#{1,6}\s*", "", str(line or "")).strip()
    if not value or len(value) > 28:
        return ""
    if re.search(r"[。！？；;，,：:]", value):
        return ""
    if re.match(r"^(?:[-*•]|\d+[.)、])\s*", value):
        return ""
    if re.search(r"\d", value):
        return ""
    return value


def _information_clause(value: str, limit: int = 72) -> str:
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", str(value or "")).strip()
    return _compact_clause(text, limit=limit)


def extract_information_spans(source: str, title: str = "") -> List[Dict[str, Any]]:
    """Extract source-backed spans that give an image an actual information job.

    This is deliberately conservative: the returned display text may be
    compacted for a bitmap, but every span keeps its original source line(s).
    It is the missing contract between a long native Card and a useful visual.
    """
    lines = [line.strip() for line in str(source or "").splitlines()]
    spans: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(role: str, text: str, source_text: str, source_line: int, source_lines: Optional[List[int]] = None) -> None:
        display = re.sub(r"\s+", " ", str(text or "")).strip()
        if not display or display in seen:
            return
        seen.add(display)
        spans.append({
            "role": role,
            "text": display,
            "source_text": str(source_text or "").strip(),
            "source_line": source_line,
            "source_lines": list(source_lines or [source_line]),
        })

    clean_title = re.sub(r"^\s*#{1,6}\s*", "", str(title or "")).strip()
    if clean_title:
        add("title", clean_title, clean_title, 1)

    for index, raw_line in enumerate(lines, start=1):
        heading = _heading_like(raw_line)
        if heading == clean_title:
            continue
        if heading and heading != clean_title:
            following_index = next(
                (cursor for cursor in range(index, len(lines)) if lines[cursor].strip()),
                None,
            )
            if following_index is not None:
                following = lines[following_index].strip()
                if not _heading_like(following) and not DATE_LIKE_RE.search(following):
                    clause = _information_clause(following, 58)
                    if clause:
                        add("section", f"{heading}：{clause}", raw_line + "\n" + following, index, [index, following_index + 1])
                        continue
            add("section", heading, raw_line, index)
            continue
        if re.match(r"^\s*(?:[-*•]|\d+[.)、])\s+", raw_line):
            clause = _information_clause(raw_line, 64)
            if clause:
                add("point", clause, raw_line, index)
        elif not DATE_LIKE_RE.search(raw_line) and len(raw_line) >= 12 and len(spans) < 8:
            clause = _information_clause(raw_line, 72)
            if clause and not URL_RE.search(clause):
                add("claim", clause, raw_line, index)
        if len(spans) >= 8:
            break

    return spans[:8]


def _brand_asset_policy(source: str, brand_context: str = "") -> Dict[str, Any]:
    context = "\n".join(part for part in (str(source or ""), str(brand_context or "")) if part.strip())
    exact_required = bool(BRAND_ASSET_RE.search(context))
    provided_assets = []
    for line in str(brand_context or "").splitlines():
        if re.search(r"(?:asset|素材|logo|校徽|徽标|图片)\s*[:：]", line, re.I):
            provided_assets.append(line.strip())
    return {
        "exact_asset_required": exact_required,
        "provided_assets": provided_assets[:8],
        "use_original_asset_when_available": True,
        "do_not_redraw_logo": True,
        "unverified_brand_fallback": "未提供原始品牌资产时不生成相似校徽、校名或官方标志；保留为来源文字并进入人工复核",
    }


def _information_purpose(value: str, chart: Optional[Dict[str, Any]], nodes: Sequence[Dict[str, Any]], spans: Sequence[Dict[str, Any]], no_image: bool) -> str:
    if no_image:
        return "不使用图片；原生 Card 保留可编辑事实和真实行动"
    if chart:
        return "把来源锁定的指标、单位和比较关系转成可读的数据视觉"
    if nodes:
        return "把来源锁定的日期、阶段、动作和先后关系转成可读顺序"
    if sum(1 for item in spans if item.get("role") == "section") >= 2:
        return "把来源锁定的主题、分组和核心主张转成首屏信息层级"
    return "把来源锁定的标题与核心主张转成一个可验证的信息锚点"


def _visual_job(value: str, chart: Optional[Dict[str, Any]], nodes: Sequence[Dict[str, Any]], spans: Sequence[Dict[str, Any]], no_image: bool) -> str:
    if no_image:
        return "不设置图片任务"
    if chart:
        return "按同口径标签、数值和单位组织比较，不添加装饰性数据"
    if nodes:
        return "沿单一阅读路径组织日期/阶段/动作，保留来源顺序和下一节点"
    if sum(1 for item in spans if item.get("role") == "section") >= 2:
        return "用标题、分组和短主张组织信息区，不把全文截图或做成抽象概念图"
    return "用标题和一条来源主张建立主题锚点，不用空泛氛围替代信息"


def build_visual_spec(source: str, *, title: str = "", no_image: bool = False, brand_context: str = "") -> Dict[str, Any]:
    """Return the editable source for Seedream 5.0 Pro and native chart generation."""
    metrics = extract_metrics(source)
    chart = build_chart_plan(source, metrics)
    nodes = extract_relationship_nodes(source)
    value = str(source or "")
    spans = extract_information_spans(value, title)
    purpose = _information_purpose(value, chart, nodes, spans, no_image)
    visual_job = _visual_job(value, chart, nodes, spans, no_image)
    dense_signal = (
        len(value) >= 600
        or len(nodes) >= 3
        or sum(1 for item in spans if item.get("role") == "section") >= 3
        or bool(INFORMATION_IMAGE_REQUEST_RE.search(value))
    )
    content_nodes: List[Dict[str, Any]] = []
    for item in list(nodes) + list(spans):
        key = (str(item.get("label") or item.get("role") or ""), str(item.get("text") or ""))
        if any((str(existing.get("label") or existing.get("role") or ""), str(existing.get("text") or "")) == key for existing in content_nodes):
            continue
        content_nodes.append(dict(item))
    must_show = [str(item.get("text") or "") for item in spans[:6] if str(item.get("text") or "").strip()]
    if chart:
        visual_type = f"data_{chart['type']}"
    elif len(nodes) >= 2 and re.search(r"前后|对比", value):
        visual_type = "comparison_infographic"
    elif len(nodes) >= 2:
        visual_type = "process_or_relationship_infographic"
    elif re.search(r"流程|阶段|步骤|时间线", value):
        visual_type = "process_infographic"
    else:
        visual_type = "thematic_information_visual"
    return {
        "schema": "doubao-feishu-card-visual-spec/1",
        "editable": True,
        "source_locked": True,
        "title": title,
        "image_required": not no_image,
        "visual_type": "none" if no_image else visual_type,
        "selection_rule": "real data -> chart; process -> flow; comparison -> comparison; otherwise thematic information visual",
        "metrics": metrics,
        "chart": chart,
        "relationship_nodes": nodes,
        "information_carrier": not no_image,
        "not_decorative": not no_image,
        "information_purpose": purpose,
        "visual_job": visual_job,
        "source_spans": spans,
        "content_nodes": content_nodes[:10],
        "must_show": must_show,
        "must_not_show": [
            "抽象科技装饰或没有信息作用的概念图",
            "未提供的校徽、Logo、品牌字样或学校身份暗示",
            "按钮、CTA 胶囊、二维码、URL 或伪交互",
            "来源没有给出的数字、日期、排名、结果或承诺",
        ],
        "brand_asset_policy": _brand_asset_policy(value, brand_context),
        "mobile_readability": {
            "reference_display_width_px": 360,
            "safe_margin": "至少 6% 画布边距",
            "minimum_role": "标题、日期、单位、限定词和节点必须可读",
            "overflow_policy": "信息过密时拆成首图/时间线/分组图，不能缩成微型字",
        },
        "recommended_panels": [
            {
                "id": "cover_identity",
                "purpose": "主题、身份和一条来源核心主张",
                "source_roles": ["title", "claim", "section"],
            },
            *([{
                "id": "ordered_process",
                "purpose": "日期、阶段、动作和先后关系",
                "source_roles": ["stage", "relationship"],
            }] if nodes else []),
            *([{
                "id": "grouped_information",
                "purpose": "活动介绍、权益、赛道或安全边界等分组信息",
                "source_roles": ["section", "point"],
            }] if sum(1 for item in spans if item.get("role") in {"section", "point"}) >= 2 else []),
        ],
        "preferred_render": "information_infographic" if dense_signal and not no_image else "banner_or_infographic",
        "raster_output": "hero.png" if not no_image else None,
        "native_pairing": "title, concise summary, key points, chart, and buttons remain editable CardKit components",
        "no_invention": "missing values remain missing; do not infer numbers, labels, links, or outcomes",
    }


def chart_block_from_plan(chart: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not chart:
        return None
    return {
        "type": "chart",
        "title": chart.get("title"),
        "chart_spec": chart.get("chart_spec"),
        "aspect_ratio": "4:3",
        "color_theme": "brand",
        "source_text": "\n".join(chart.get("source_text") or []),
        "source_lines": chart.get("source_lines") or [],
        "grounded": True,
    }
