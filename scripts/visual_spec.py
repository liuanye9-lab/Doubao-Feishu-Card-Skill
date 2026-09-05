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


def build_visual_spec(source: str, *, title: str = "", no_image: bool = False) -> Dict[str, Any]:
    """Return the editable source for Seedream 5.0 Pro and native chart generation."""
    metrics = extract_metrics(source)
    chart = build_chart_plan(source, metrics)
    nodes = extract_relationship_nodes(source)
    value = str(source or "")
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
